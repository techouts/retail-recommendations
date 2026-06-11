import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from ..utils.pipeline_utils import load_csv_from_s3, normalize
from ..adapters.meili.indexer import push_to_meili , push_to_meili_fbt , push_to_meili_popular_brands
from types import SimpleNamespace
from itertools import combinations
from collections import Counter
from .utils import normalize_df
import re
import logging
logger = logging.getLogger(__name__)
from ..es_utils.es_utils import push_to_es

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_DIR = os.path.join(BASE_DIR, "data", "processed")

def clean_brand_id(brand):
    return re.sub(r'[^a-zA-Z0-9_-]', '_', brand)

def df_to_es_docs(df: pd.DataFrame) -> list[dict]:
    
    df = df.replace([np.nan, np.inf, -np.inf], None)
    return df.to_dict(orient="records")


def run_popular_brands(popular_brands_weights : dict , client : str):
    
    weights = SimpleNamespace(**popular_brands_weights)
    
    s3_path = os.getenv("S3_PATH", "s3://retail-search")

    # Load CSVs from S3 by client
    catalog         = normalize_df(load_csv_from_s3(s3_path, client, "catalog"))
    orders          = normalize_df(load_csv_from_s3(s3_path, client, "orders"))
    analytics       = normalize_df(load_csv_from_s3(s3_path, client, "analytics"))
    customer_rating = normalize_df(load_csv_from_s3(s3_path, client, "customer_rating"))
    inventory       = normalize_df(load_csv_from_s3(s3_path, client, "inventory"))

    
    orders = orders.merge(catalog[["skuid", "brand"]], on="skuid", how="left")
    analytics = analytics.merge(catalog[["skuid", "brand"]], on="skuid", how="left")
    customer_rating = customer_rating.merge(catalog[["skuid", "brand"]], on="skuid", how="left")
    inventory = inventory.merge(catalog[["skuid", "brand"]], on="skuid", how="left")
    
    orders_df = orders.groupby("brand").agg(
        total_orders=("order_id", "count")
    ).reset_index()
    
    logger.info("Catalog df shape: %s", orders_df.shape)

    
    analytics_df = analytics.groupby("brand").agg(
        total_views=("view_count", "sum"),
        total_cart=("addtocart_count", "sum")
    ).reset_index()
    
    logger.info("Analytics df shape: %s", analytics_df.shape)

    
    ratings_df = customer_rating.groupby("brand").agg(
        avg_rating=("rating", "mean")
    ).reset_index()
    
    logger.info("Ratings df shape: %s", ratings_df.shape)

    
    inventory_df = inventory[inventory["stock_quantity"] > 0]

    inventory_df = inventory_df.groupby("brand").agg(
        available_products=("skuid", "count")
    ).reset_index()
    
    logger.info("Inventory df shape: %s", inventory_df.shape)


    
    df = orders_df.merge(analytics_df, on="brand", how="outer") \
              .merge(ratings_df, on="brand", how="outer") \
              .merge(inventory_df, on="brand", how="outer")

    df = df.fillna(0)
    print("Total brands before filter:", len(df))
    print("Unique brands before filter:", df["brand"].nunique())

    print(
        df[["brand", "total_orders", "avg_rating"]]
        .sort_values(["avg_rating", "total_orders"], ascending=False)
    )

    df = df[
        (df["total_orders"] >= weights.min_orders) &
        (df["avg_rating"] >= weights.min_rating)
    ]

    print("Total brands after filter:", len(df))
    print("Unique brands after filter:", df["brand"].nunique())

    print(
        df[["brand", "total_orders", "avg_rating"]]
        .sort_values(["avg_rating", "total_orders"], ascending=False)
    )
    
    def normalize(col):
        return (col - col.min()) / (col.max() - col.min() + 1e-9)

    df["norm_orders"] = normalize(df["total_orders"])
    df["norm_views"] = normalize(df["total_views"])
    df["norm_rating"] = normalize(df["avg_rating"])
    df["norm_cart"] = normalize(df["total_cart"])
    df["norm_availability"] = normalize(df["available_products"])
    
    df["score"] = (
        weights.sales_weight * df["norm_orders"] +
        weights.views_weight * df["norm_views"] +
        weights.rating_weight * df["norm_rating"] +
        weights.cart_weight * df["norm_cart"] +
        weights.availability_weight * df["norm_availability"]
    )
    
    df = df.sort_values(by="score", ascending=False)
    df["rank"] = range(1, len(df) + 1)
    
    logger.debug("DF sample:\n%s", df.head(10))
    
    docs = []

    for _, row in df.iterrows():
        doc = {
            "brand_id": clean_brand_id(row["brand"]),
            "rank": int(row["rank"]),
            "score": float(row["score"]),
            "total_orders": int(row["total_orders"]),
            "total_views": int(row["total_views"]),
            "avg_rating": float(row["avg_rating"]),
            "total_cart": int(row["total_cart"]),
            "available_products": int(row.get("available_products", 0)),
            "status": "active"
        }
        docs.append(doc)
        
        
    # #   --- meili search ---    
    # push_to_meili_popular_brands(
    #         docs=docs,
    #         index_name=f"{client}_popular_brands"
    #     )
    # return docs
    
    
    # --- es ---    
    if not df.empty:
        docs = df_to_es_docs(df)
        push_to_es(docs=docs, ALIAS_NAME=f"{client}_popular_brands", INDEX_PREFIX=f"{client}_popular-brands")

    return docs
        