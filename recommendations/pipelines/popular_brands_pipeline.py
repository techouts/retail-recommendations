import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from ..utils.pipeline_utils import load_csv_from_s3, normalize
from ..adapters.meili.indexer import push_to_meili , push_to_meili_fbt , push_to_meili_popular_brands
from types import SimpleNamespace
from itertools import combinations
from collections import Counter
import re
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
    catalog = load_csv_from_s3(s3_path, client, "catalog")
    orders = load_csv_from_s3(s3_path, client, "orders")
    analytics = load_csv_from_s3(s3_path, client, "analytics")
    customer_rating = load_csv_from_s3(s3_path, client, "customer_rating")
    inventory = load_csv_from_s3(s3_path, client, "inventory")

    
    orders = orders.merge(catalog[["sku_id", "brand"]], on="sku_id", how="left")
    analytics = analytics.merge(catalog[["sku_id", "brand"]], on="sku_id", how="left")
    customer_rating = customer_rating.merge(catalog[["sku_id", "brand"]], on="sku_id", how="left")
    inventory = inventory.merge(catalog[["sku_id", "brand"]], on="sku_id", how="left")
    
    orders_df = orders.groupby("brand").agg(
        total_orders=("order_id", "count")
    ).reset_index()
    
    print("catalog df : ",orders_df)
    
    analytics_df = analytics.groupby("brand").agg(
        total_views=("view_count", "sum"),
        total_cart=("addtocart_count", "sum")
    ).reset_index()
    
    print("Analytics df : ",analytics_df)
    
    ratings_df = customer_rating.groupby("brand").agg(
        avg_rating=("rating", "mean")
    ).reset_index()
    
    print("Rating df : ",ratings_df)
    
    inventory_df = inventory[inventory["stock_quantity"] > 0]

    inventory_df = inventory_df.groupby("brand").agg(
        available_products=("sku_id", "count")
    ).reset_index()
    
    print("Inventory df : ",inventory_df)
    
    df = orders_df.merge(analytics_df, on="brand", how="outer") \
              .merge(ratings_df, on="brand", how="outer") \
              .merge(inventory_df, on="brand", how="outer")

    df = df.fillna(0)
    
    # weights = PopularBrandWeights.objects.get(id=1)
    df = df[
        (df["total_orders"] >= weights.min_orders) &
        (df["avg_rating"] >= weights.min_rating)
    ]

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
    
    print("Df : ",df.head(10))
    
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
        
        
    #   --- meili search ---    
    # push_to_meili_popular_brands(
    #         docs=docs,
    #         index_name=f"{client}_popular_brands"
    #     )
    # return docs
    
    # --- es ---    
    if not df.empty:
        docs = df_to_es_docs(df)
        push_to_es(docs=docs, ALIAS_NAME="popular_brands", INDEX_PREFIX="popular-brands")

    return docs
        