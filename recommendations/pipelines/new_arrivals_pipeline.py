import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import logging

from ..adapters.es.indexer import push_to_es
from ..utils.pipeline_utils import load_csv_from_s3
from .utils import normalize_df

logger = logging.getLogger(__name__)


# -------------------- UTIL --------------------

def parse_datetime(df, col):
    if col not in df.columns:
        df[col] = pd.Timestamp.now()
    df[col] = pd.to_datetime(df[col], format="%d-%m-%Y %H:%M", errors="coerce")

def normalize(series):
    if len(series) == 0 or series.max() == series.min():
        return pd.Series([0] * len(series), index=series.index)
    return (series - series.min()) / (series.max() - series.min())


def df_to_docs(df):
    df = df.replace([np.nan, np.inf, -np.inf], None)
    return df.to_dict(orient="records")


# -------------------- PIPELINE --------------------

def run_new_arrivals_pipeline(settings: dict, client: str):

    logger.info("=========== NEW ARRIVALS PIPELINE STARTED ===========")

    s3_path = os.getenv("S3_PATH", "s3://retail-search")

    # -------------------- LOAD --------------------
    catalog     = normalize_df(load_csv_from_s3(s3_path, client, "catalog"))
    analytics = normalize_df(load_csv_from_s3(s3_path, client, "analytics")) 
    logger.info(f"Loaded Catalog: {len(catalog)} | Events: {len(analytics )}")

    # -------------------- CLEAN --------------------
    for df in [catalog, analytics ]:
        df.columns = df.columns.str.strip()

    # ✅ Required columns safety
    if "skuid" not in catalog.columns:
        raise ValueError("catalog must have 'skuid'")

    if "skuid" not in analytics .columns:
        raise ValueError("analytics  must have 'skuid'")

    # ✅ category cleanup
    catalog["category_l3"] = (
        catalog.get("category_l3", "unknown")
        .astype(str)
        .str.lower()
        .str.strip()
        .fillna("unknown")
    )

    # ✅ brand safety
    if "brand" not in catalog.columns:
        catalog["brand"] = "unknown"
    else:
        catalog["brand"] = catalog["brand"].fillna("unknown")

    # ✅ datetime parsing
    parse_datetime(catalog, "catalog_entry_date")
    parse_datetime(analytics , "timestamp")

    # ✅ event type cleaning
    analytics ["event_type"] = (
        analytics .get("event_type", "")
        .astype(str)
        .str.lower()
        .str.strip()
    )

    # -------------------- RECENCY --------------------
    now = datetime.now()

    catalog["age_days"] = (now - catalog["catalog_entry_date"]).dt.days

    def recency_decay(age):
        if age <= 7: return 1.0
        elif age <= 14: return 0.75
        elif age <= 30: return 0.50
        elif age <= 45: return 0.25
        return 0

    catalog["recency_decay"] = catalog["age_days"].apply(recency_decay)

    # keep only new products
    catalog = catalog[catalog["age_days"] <= 45]

    # -------------------- SPLIT EVENTS --------------------
    views     = analytics [analytics ["event_type"] == "view"]
    cart      = analytics [analytics ["event_type"] == "cart"]
    wishlist  = analytics [analytics ["event_type"] == "wishlist"]

    # -------------------- TIME WINDOWS --------------------
    def filter_window(df, days):
        return df[df["timestamp"] >= now - timedelta(days=days)]

    views_24h = filter_window(views, 1)
    views_3d  = filter_window(views, 3)

    cart_24h = filter_window(cart, 1)
    cart_3d  = filter_window(cart, 3)

    wish_3d = filter_window(wishlist, 3)
    wish_7d = filter_window(wishlist, 7)

    # -------------------- AGGREGATION --------------------
    def agg(df, name):
        if df.empty:
            return pd.DataFrame(columns=["skuid", name])
        return df.groupby("skuid").size().reset_index(name=name)

    df = catalog.copy()

    for d in [
        agg(views_24h, "views_24h"),
        agg(views_3d, "views_3d"),
        agg(cart_24h, "cart_24h"),
        agg(cart_3d, "cart_3d"),
        agg(wish_3d, "wish_3d"),
        agg(wish_7d, "wish_7d")
    ]:
        df = df.merge(d, on="skuid", how="left")

    df = df.fillna(0)

    # -------------------- SIGNALS --------------------
    df["views_score"] = 0.7 * df["views_24h"] + 0.3 * df["views_3d"]
    df["cart_score"]  = 0.6 * df["cart_24h"] + 0.4 * df["cart_3d"]
    df["wish_score"]  = 0.5 * df["wish_3d"] + 0.5 * df["wish_7d"]

    # fallback similarity
    df["similar_score"] = df.groupby("category_l3")["views_score"].transform("mean")

    # -------------------- NORMALIZATION --------------------
    df["norm_views"] = df.groupby("category_l3")["views_score"].transform(normalize)
    df["norm_cart"]  = df.groupby("category_l3")["cart_score"].transform(normalize)
    df["norm_wish"]  = df.groupby("category_l3")["wish_score"].transform(normalize)
    df["norm_sim"]   = df.groupby("category_l3")["similar_score"].transform(normalize)

    # -------------------- FINAL SCORE --------------------
    df["base_score"] = (
        0.35 * df["norm_views"] +
        0.30 * df["norm_cart"] +
        0.20 * df["norm_wish"] +
        0.15 * df["norm_sim"]
    )

    df["final_score"] = df["base_score"] * df["recency_decay"]

    # -------------------- FILTER --------------------
    threshold = settings.get("threshold", 0.55)
    df = df[df["final_score"] >= threshold]

    # -------------------- TOP N --------------------
    top_n = settings.get("top_n", 10)
    df["rank"] = df.groupby("category_l3")["final_score"].rank(method="first", ascending=False)
    df = df[df["rank"] <= top_n]

    # -------------------- FINAL OUTPUT --------------------
    result_df = df[["skuid", "category_l3", "brand", "final_score"]]

    docs = df_to_docs(result_df)

    logger.info(f"Final docs: {len(docs)}")

    # -------------------- PUSH --------------------
    if docs:
        push_to_es(
            INDEX_PREFIX=f"{client}_new_arrivals_retail",
            ALIAS_NAME=f"{client}_new_arrivals_retail",
            docs=docs
        )

    logger.info("=========== PIPELINE COMPLETED ===========")

    return docs