from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from ..utils.pipeline_utils import load_csv_from_s3, normalize
from ..adapters.es.indexer import push_to_es
from .utils import normalize_df

import os

logger = logging.getLogger(__name__)



# Config Model

class NewArrivalsWeightsModel(BaseModel):

    # Internal signal weights
    internal_views_24h: float = 0.7
    internal_views_3d: float = 0.3

    internal_cart_24h: float = 0.6
    internal_cart_3d: float = 0.4

    internal_wish_3d: float = 0.5
    internal_wish_7d: float = 0.5

    # Business weights
    business_views_weight: float = 0.35
    business_cart_weight: float = 0.30
    business_wish_weight: float = 0.20
    business_similarity_weight: float = 0.15

    threshold_value: float = 0.55

    max_age_days: int = 30
    fallback_age_days: int = 45

    min_stock: int = 1



# Deep clean
def deep_clean(obj: Any) -> Any:

    if isinstance(obj, dict):
        return {k: deep_clean(v) for k, v in obj.items()}

    if isinstance(obj, list):
        return [deep_clean(v) for v in obj]

    if isinstance(obj, (np.float32, np.float64, float)):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return float(obj)

    if isinstance(obj, (np.int32, np.int64)):
        return int(obj)

    if isinstance(obj, (np.bool_,)):
        return bool(obj)

    if isinstance(obj, (type(pd.NaT), type(None))):
        return None

    try:
        if pd.isna(obj):
            return None
    except Exception:
        pass

    return obj



# Load CSVs


def load_and_normalise(client: str):

    s3_path = os.getenv("S3_PATH", "s3://retail-search")

    catalog_df = normalize_df(
        load_csv_from_s3(s3_path, client, "catalog")
    )

    analytics_df = normalize_df(
        load_csv_from_s3(s3_path, client, "analytics")
    )

    inventory_df = normalize_df(
        load_csv_from_s3(s3_path, client, "inventory")
    )

    fulfillment_df = normalize_df(
        load_csv_from_s3(s3_path, client, "fulfillment")
    )

    return (
        catalog_df,
        analytics_df,
        inventory_df,
        fulfillment_df
    )



# Eligible SKU Filtering

def get_eligible_products(
    catalog_df: pd.DataFrame,
    inventory_df: pd.DataFrame,
    max_age_days: int,
    min_stock: int
):

    stock_totals = (
        inventory_df
        .groupby("skuid", as_index=False)["stock_quantity"]
        .sum()
    )

    eligible_stock = stock_totals[
        stock_totals["stock_quantity"] > min_stock
    ]["skuid"]

    catalog_df["created_at"] = pd.to_datetime(
    catalog_df["created_at"],
    errors="coerce",
    dayfirst=True
)

    catalog_df["age_days"] = (
    datetime.now() - catalog_df["created_at"]
    ).dt.days

    eligible_products = catalog_df[
        (catalog_df["skuid"].isin(eligible_stock)) &
        (catalog_df["age_days"] <= max_age_days)
    ].copy()

    if "status" in eligible_products.columns:
        eligible_products = eligible_products[
            eligible_products["status"]
            .astype(str)
            .str.lower() == "active"
        ]

    logger.info(
        "Eligible new arrival products=%d",
        len(eligible_products)
    )

    return eligible_products


# Aggregate Signals

def aggregate_signal(
    df: pd.DataFrame,
    value_col: str,
    time_filter: datetime
):

    if value_col not in df.columns:
        return pd.DataFrame(columns=["skuid", value_col])

    temp = df[
        df["created_at"] >= time_filter
    ]

    agg = (
        temp
        .groupby("skuid")[value_col]
        .sum()
        .reset_index()
    )

    return agg



# Compute Signals


def compute_signals(
    analytics_df: pd.DataFrame,
    eligible_skuids: pd.Series
):

    now = datetime.now()

    time_24h = now - timedelta(hours=24)
    time_3d = now - timedelta(days=3)
    time_7d = now - timedelta(days=7)

    analytics_df["created_at"] = pd.to_datetime(
        analytics_df["created_at"],
        errors="coerce"
    )

    analytics_df = analytics_df[
        analytics_df["skuid"].isin(eligible_skuids)
    ]

    # Views
    views_24h = aggregate_signal(
        analytics_df,
        "view_count",
        time_24h
    ).rename(columns={"view_count": "views_24h"})

    views_3d = aggregate_signal(
        analytics_df,
        "view_count",
        time_3d
    ).rename(columns={"view_count": "views_3d"})

    # Cart
    cart_24h = aggregate_signal(
        analytics_df,
        "addtocart_count",
        time_24h
    ).rename(columns={"addtocart_count": "cart_24h"})

    cart_3d = aggregate_signal(
        analytics_df,
        "addtocart_count",
        time_3d
    ).rename(columns={"addtocart_count": "cart_3d"})

    # Wishlist
    wish_3d = aggregate_signal(
        analytics_df,
        "wishlist_count",
        time_3d
    ).rename(columns={"wishlist_count": "wish_3d"})

    wish_7d = aggregate_signal(
        analytics_df,
        "wishlist_count",
        time_7d
    ).rename(columns={"wishlist_count": "wish_7d"})

    merged = (
        views_24h
        .merge(views_3d, on="skuid", how="outer")
        .merge(cart_24h, on="skuid", how="outer")
        .merge(cart_3d, on="skuid", how="outer")
        .merge(wish_3d, on="skuid", how="outer")
        .merge(wish_7d, on="skuid", how="outer")
        .fillna(0)
    )

    return merged



# Recency Decay


def get_recency_decay(age):

    if age <= 7:
        return 1.0

    elif age <= 14:
        return 0.75

    elif age <= 30:
        return 0.50

    else:
        return 0.25



# Score Products


def score_products(
    signal_df: pd.DataFrame,
    catalog_df: pd.DataFrame,
    weights: NewArrivalsWeightsModel
):

    df = signal_df.copy()

    # Weighted Signals

    df["weighted_views"] = (
        (weights.internal_views_24h * df["views_24h"]) +
        (weights.internal_views_3d * df["views_3d"])
    )

    df["weighted_cart"] = (
        (weights.internal_cart_24h * df["cart_24h"]) +
        (weights.internal_cart_3d * df["cart_3d"])
    )

    df["weighted_wish"] = (
        (weights.internal_wish_3d * df["wish_3d"]) +
        (weights.internal_wish_7d * df["wish_7d"])
    )

    # Normalize

    df["norm_views"] = normalize(df["weighted_views"])
    df["norm_cart"] = normalize(df["weighted_cart"])
    df["norm_wish"] = normalize(df["weighted_wish"])

    # Similarity placeholder
    df["similarity_score"] = 0.50

    # Base Score

    df["base_score"] = (
        (weights.business_views_weight * df["norm_views"]) +
        (weights.business_cart_weight * df["norm_cart"]) +
        (weights.business_wish_weight * df["norm_wish"]) +
        (
            weights.business_similarity_weight *
            df["similarity_score"]
        )
    )

    # Merge age info

    df = df.merge(
        catalog_df[["skuid", "age_days"]],
        on="skuid",
        how="left"
    )

    # Recency Decay

    df["recency_decay"] = df["age_days"].apply(
        get_recency_decay
    )

    # Personalization placeholder
    df["personalization_boost"] = 1.0

    # Final Score

    df["new_arrival_score"] = (
        df["base_score"] *
        df["recency_decay"] *
        df["personalization_boost"]
    )

    # Threshold

    df["is_new_arrival"] = (
        df["new_arrival_score"] >=
        weights.threshold_value
    )

    return df



# Build ES Docs


def build_es_docs(
    final_df: pd.DataFrame
):

    cols = [
          "skuid",
    "product_name",
    "brand",
    "selling_price",

    "views_24h",
    "views_3d",

    "cart_24h",
    "cart_3d",

    "wish_3d",
    "wish_7d",

    "weighted_views",
    "weighted_cart",
    "weighted_wish",

    "norm_views",
    "norm_cart",
    "norm_wish",

    "similarity_score",
    "base_score",
    "recency_decay",
    "personalization_boost",

    "new_arrival_score",
    "is_new_arrival",

    "category_l1",
    "category_l2",
    "category_l3",

    "age_days",
    "catalog_entry_date",
    "image_urls"
    ]

    cols = [c for c in cols if c in final_df.columns]

    subset = final_df[cols].copy()

    subset = subset.replace(
        [np.inf, -np.inf],
        np.nan
    )

    subset = subset.where(
        subset.notna(),
        None
    )

    docs = deep_clean(
        subset.to_dict(orient="records")
    )

    return docs



# Main Pipeline


def run_new_arrivals_pipeline(
    new_arrivals_weights: dict,
    client: str
):

    weights = NewArrivalsWeightsModel(
        **new_arrivals_weights
    )

    logger.info(
        "Starting new arrivals pipeline client=%s",
        client
    )

    # Load CSVs

    (
        catalog_df,
        analytics_df,
        inventory_df,
        fulfillment_df
    ) = load_and_normalise(client)

    # Eligible products

    eligible_products = get_eligible_products(
        catalog_df,
        inventory_df,
        weights.max_age_days,
        weights.min_stock
    )

    if eligible_products.empty:
        logger.warning("No eligible products")
        return []

    eligible_skuids = eligible_products["skuid"]

    # Signals

    signal_df = compute_signals(
        analytics_df,
        eligible_skuids
    )

    # Score

    scored_df = score_products(
        signal_df,
        eligible_products,
        weights
    )

    # Merge catalog

    final_df = eligible_products.merge(
        scored_df,
        on="skuid",
        how="inner"
    )

    final_df = final_df[
        final_df["is_new_arrival"]
    ]

    print(scored_df["is_new_arrival"].value_counts())

    print(
        scored_df[
            ["skuid", "new_arrival_score", "is_new_arrival"]
        ]
    )

    print(
        final_df[
            ["skuid", "product_name", "new_arrival_score"]
        ]
    )
    if final_df.empty:
        logger.warning("No new arrivals after scoring")
        return []

    # Build docs

    docs = build_es_docs(final_df)

    if not docs:
        logger.warning("No docs generated")
        return []

    # Push to Elasticsearch

    push_to_es(
        INDEX_PREFIX=f"{client}_new_arrivals",
        ALIAS_NAME=f"{client}_new_arrivals",
        docs=docs
    )

    logger.info(
        "New arrivals pipeline completed docs=%d",
        len(docs)
    )

    return docs