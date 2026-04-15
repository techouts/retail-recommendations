
import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from ..adapters.es.indexer import push_to_es
from ..utils.pipeline_utils import load_csv_from_s3, normalize
import logging
logger = logging.getLogger(__name__)
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_DIR = os.path.join(BASE_DIR, "data", "processed")


# -------------------- UTIL FUNCTIONS --------------------

def parse_datetime(df, col):
    if col not in df.columns:
        logger.info(f" {col} missing → default added")
        df[col] = pd.Timestamp.now()
    df[col] = pd.to_datetime(df[col], errors="coerce", format="mixed")


def normalize(series):
    if len(series) == 0 or series.max() == series.min():
        return pd.Series([0] * len(series), index=series.index)
    return (series - series.min()) / (series.max() - series.min())


def df_to_docs(df):
    df = df.replace([np.nan, np.inf, -np.inf], None)
    return df.to_dict(orient="records")


# -------------------- MAIN PIPELINE --------------------

def run_bestseller_pipeline(settings: dict, time_window: dict, client: str):

    logger.info("\n================ BEST SELLER PIPELINE STARTED ================\n")

    # -------------------- WEIGHTS --------------------
    weights = {
        "sales": settings.get("sales_count", 0.40),
        "revenue": settings.get("revenue", 0.25),
        "stock": settings.get("stock_quantity", 0.15),
        "return": settings.get("return_rate_score", 0.10),
        "rating": settings.get("customer_rating_score", 0.10),
    }
    logger.info(f"Weights: {weights}")

    # -------------------- THRESHOLDS --------------------
    sales_t = settings.get("sales_threshold", 0)
    revenue_t = settings.get("revenue_threshold", 0)
    stock_t = settings.get("stock_threshold", 0)
    return_t = settings.get("return_rate_threshold", 100)
    rating_t = settings.get("customer_rating_threshold", 0)
    final_t = settings.get("final_score_threshold", 0)

    logger.info(f"Thresholds: { { 
     'sales': sales_t,
     'revenue': revenue_t,
     'stock': stock_t,
     'return': return_t,
     'rating': rating_t,
     'final': final_t
 } }")

    # -------------------- LOAD DATA --------------------
    s3_path = os.getenv("S3_PATH", "s3://retail-search")

    catalog =load_csv_from_s3(s3_path, client, "catalog")
    fulfillment = load_csv_from_s3(s3_path,client,"fulfillment")
    orders = load_csv_from_s3(s3_path,client, "orders")
    analytics_rating = load_csv_from_s3(s3_path,client,"analytics_rating")
    inventory = load_csv_from_s3(s3_path,client,"inventory")
    returns = load_csv_from_s3(s3_path,client,"returns")

    logger.info(f"Loaded → Catalog:{len(catalog)} | Fulfillment:{len(fulfillment)}")

    # -------------------- CLEAN --------------------
    for df in [catalog, fulfillment, orders, analytics_rating, inventory, returns]:
        df.columns = df.columns.str.strip()
        if "sku_id" in df.columns:
            df.rename(columns={"sku_id": "skuid"}, inplace=True)

    #  FIX: ensure no null values
    catalog["category_l3"] = catalog["category_l3"].astype(str).str.lower().str.strip().fillna("unknown")
    if "brand" not in catalog.columns:
        catalog["brand"] = "unknown"
    else:
        catalog["brand"] = catalog["brand"].fillna("unknown")

    for df in [fulfillment, orders, inventory, returns, analytics_rating]:
        if "seller_id" not in df.columns:
            df["seller_id"] = "default_seller"

        if "customer_rate" not in analytics_rating.columns:
            analytics_rating["customer_rate"] = 0

    # -------------------- DATETIME --------------------
    parse_datetime(fulfillment, "created_at")
    parse_datetime(orders, "created_at")
    parse_datetime(inventory, "created_at")
    parse_datetime(returns, "created_at")
    parse_datetime(analytics_rating, "timestamp")

    orders["price"] = pd.to_numeric(orders["price"], errors="coerce").fillna(0)

    # -------------------- TIME WINDOW --------------------
    max_days = max(time_window.values()) if time_window else 30
    cutoff = datetime.now() - timedelta(days=max_days)

    logger.info(f"Using cutoff: {cutoff}")

    # -------------------- FILTER --------------------
    f = fulfillment[fulfillment["created_at"] >= cutoff]
    o = orders[orders["created_at"] >= cutoff]
    i = inventory[inventory["created_at"] >= cutoff]
    r = returns[returns["created_at"] >= cutoff]
    a = analytics_rating[analytics_rating["timestamp"] >= cutoff]

    logger.info(f"After time filter: {len(f)}")

    if f.empty:
        logger.info(" No data after time filter")
        return []

    # -------------------- AGGREGATION --------------------
    f = f.groupby(["skuid","seller_id"]).agg(sales_count=("quantity","sum")).reset_index()
    o = o.groupby(["skuid","seller_id"]).agg(revenue=("price","sum")).reset_index() if not o.empty else pd.DataFrame()
    i = i.groupby(["skuid","seller_id"])["stock_quantity"].sum().reset_index() if not i.empty else pd.DataFrame()
    r = r.groupby(["skuid","seller_id"]).agg(return_count=("seller_id","count")).reset_index() if not r.empty else pd.DataFrame()
    a = a.groupby(["skuid","seller_id"]).agg(avg_rating=("customer_rate","mean")).reset_index() if not a.empty else pd.DataFrame()

    perf = f
    for name, df in zip(["orders","inventory","returns","analytics_rating"], [o,i,r,a]):
        if not df.empty:
            df = df.drop(columns=["seller_id"], errors="ignore")   
            perf = perf.merge(df, on="skuid", how="left")
            logger.info(f"Merged {name}: {len(perf)}")

    perf = perf.fillna(0)

    #  IMPORTANT: bring category + brand only once
    perf = perf.merge(catalog[["skuid","category_l3","brand"]], on="skuid", how="left")

    logger.info(f"After merge: {len(perf)}")

    logger.info("After all merges:")
    logger.info(perf[["skuid","seller_id","revenue"]].head(10))

    # -------------------- RETURN RATE --------------------
    perf["return_rate_pct"] = (perf["return_count"] / perf["sales_count"].replace(0, np.nan)) * 100
    perf["return_rate_pct"] = perf["return_rate_pct"].fillna(0)

    # -------------------- NORMALIZATION --------------------
    perf["norm_sales"] = perf.groupby("category_l3")["sales_count"].transform(normalize)
    perf["norm_revenue"] = perf.groupby("category_l3")["revenue"].transform(normalize)
    perf["norm_stock"] = perf.groupby("category_l3")["stock_quantity"].transform(normalize)
    perf["norm_return"] = 1 - perf.groupby("category_l3")["return_rate_pct"].transform(normalize)
    perf["norm_rating"] = perf.groupby("category_l3")["avg_rating"].transform(normalize)

    logger.info("Normalization complete")

    # -------------------- SCORE --------------------
    perf["sales_count"] = perf["norm_sales"] * weights["sales"] * 100
    perf["revenue"] = perf["norm_revenue"] * weights["revenue"] * 100
    perf["stock_quantity"] = perf["norm_stock"] * weights["stock"] * 100
    perf["return_count"] = perf["norm_return"] * weights["return"] * 100
    perf["rating_score"] = perf["norm_rating"] * weights["rating"] * 100

    perf["final_score"] = (
        perf["sales_count"] +
        perf["revenue"] +
        perf["stock_quantity"] +
        perf["return_count"] +
        perf["rating_score"]
    )

    original_perf = perf.copy()

    # -------------------- THRESHOLD FILTER --------------------
    logger.info(f"Before filtering: {len(perf)}")

    def safe_filter(df, condition, name):
        temp = df[condition]
        logger.info(f"{name} filter → {len(temp)} rows")
        return temp if len(temp) > 20 else df

    if sales_t > 0:
        perf = safe_filter(perf, perf["sales_count"] >= perf["sales_count"].quantile(sales_t/100), "Sales")

    if revenue_t > 0:
        perf = safe_filter(perf, perf["revenue"] >= perf["revenue"].quantile(revenue_t/100), "Revenue")

    if stock_t > 0:
        perf = safe_filter(perf, perf["stock_quantity"] >= perf["stock_quantity"].quantile(stock_t/100), "Stock")

    perf = safe_filter(perf, perf["return_rate_pct"] <= return_t, "Return")

    if rating_t > 0:
        perf = safe_filter(perf, perf["avg_rating"] >= rating_t, "Rating")

    if final_t > 0:
        perf = safe_filter(perf, perf["final_score"] >= final_t, "Final Score")

    logger.info(f"After filtering: {len(perf)}")

    # -------------------- BRAND CAP --------------------
    perf["brand_rank"] = perf.groupby(["category_l3","brand"])["final_score"].rank(method="first", ascending=False)
    perf = perf[perf["brand_rank"] <= 3]

    logger.info(f"After brand cap: {len(perf)}")

    # -------------------- FALLBACK --------------------
    if perf.empty:
        logger.info(" fallback triggered")
        perf = original_perf.sort_values(by="final_score", ascending=False).head(50)

    # -------------------- FINAL OUTPUT --------------------sales_count_val
    final_perf = perf.merge(
        catalog.drop(columns=["category_l3","brand"], errors="ignore"),
        on="skuid",
        how="left"
    ).fillna("")

    #  ensure no empty values
    final_perf["category_l3"] = final_perf["category_l3"].replace("", "unknown")
    final_perf["brand"] = final_perf["brand"].replace("", "unknown")

    required_cols = [
        "skuid","seller_id","category_l1","category_l2","category_l3",
        "selling_price","product_name","brand",
        "sales_count","revenue","stock_quantity",
        "return_count","rating_score","final_score"
    ]

    for col in required_cols:
        if col not in final_perf.columns:
            final_perf[col] = ""

    es_data = final_perf[required_cols]

    es_data = es_data.rename(columns={
        "selling_price": "price",
        "product_name": "title",
        "category_l1": "l1",
        "category_l2": "l2",
        "category_l3": "label_column3"
    })

    es_data = es_data.sort_values(["label_column3","final_score"], ascending=[True, False]).round(2)

    docs = df_to_docs(es_data)

    logger.info(f"Final docs: {len(docs)}")

    # -------------------- PUSH --------------------
    if docs:
        logger.info(" pushing to ES...")
        push_to_es(
            INDEX_PREFIX=f"{client}_best_sellers_retail",
            ALIAS_NAME=f"{client}_best_sellers_retail",
            docs=docs
        )

    logger.info("\n================ PIPELINE COMPLETED =================\n")

    return docs