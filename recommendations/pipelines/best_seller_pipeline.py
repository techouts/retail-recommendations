# import os
# import numpy as np
# import pandas as pd
# from datetime import datetime, timedelta
# import re
# from ..adapters.meili.indexer import push_to_meili


# BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# CSV_DIR = os.path.join(BASE_DIR, "data", "processed")

# print("CSV_DIR:", CSV_DIR)


# # ---------------------------
# # HELPERS
# # ---------------------------
# def parse_datetime(catalog, fulfillment, orders, analytics, inventory, returns):

#     if "created_at" not in fulfillment.columns:
#         fulfillment.rename(columns={"timestamp": "created_at"}, inplace=True)

#     if "created_at" not in orders.columns:
#         orders.rename(columns={"timestamp": "created_at"}, inplace=True)

#     if "created_at" not in inventory.columns:
#         inventory.rename(columns={"timestamp": "created_at"}, inplace=True)

#     if "created_at" not in returns.columns:
#         returns.rename(columns={"timestamp": "created_at"}, inplace=True)

#     if "timestamp" not in analytics.columns:
#         analytics.rename(columns={"created_at": "timestamp"}, inplace=True)

#     fulfillment["created_at"] = pd.to_datetime(fulfillment.get("created_at"), errors="coerce", dayfirst=True)
#     orders["created_at"] = pd.to_datetime(orders.get("created_at"), errors="coerce", dayfirst=True)
#     inventory["created_at"] = pd.to_datetime(inventory.get("created_at"), errors="coerce", dayfirst=True)
#     returns["created_at"] = pd.to_datetime(returns.get("created_at"), errors="coerce", dayfirst=True)
#     analytics["timestamp"] = pd.to_datetime(analytics.get("timestamp"), errors="coerce", dayfirst=True)


# def normalize(series):
#     if series.max() == series.min():
#         return pd.Series([0] * len(series))
#     return (series - series.min()) / (series.max() - series.min())


# def df_to_docs(df: pd.DataFrame):
#     df = df.replace([np.nan, np.inf, -np.inf], None)
#     return df.to_dict(orient="records")


# # ---------------------------
# # MAIN PIPELINE
# # ---------------------------
# def run_bestseller_pipeline(weights: dict, time_window: dict):

#     print(" BEST SELLER PIPELINE STARTED")

#     # Weights
#     sales_score = weights.get("sales_score", 0.35)
#     revenue_score = weights.get("revenue_score", 0.25)
#     stock_score = weights.get("stock_score", 0.20)
#     return_rate_score = weights.get("return_rate_score", 0.10)
#     customer_rating_score = weights.get("customer_rating_score", 0.10)

#     # ---------------------------
#     # Load CSVs
#     # ---------------------------
#     catalog = pd.read_csv(os.path.join(CSV_DIR, "catalog.csv"))
#     fulfillment = pd.read_csv(os.path.join(CSV_DIR, "fulfillment.csv"))
#     orders = pd.read_csv(os.path.join(CSV_DIR, "orders.csv"))
#     analytics = pd.read_csv(os.path.join(CSV_DIR, "analytics.csv"))
#     inventory = pd.read_csv(os.path.join(CSV_DIR, "inventory.csv"))
#     returns = pd.read_csv(os.path.join(CSV_DIR, "returns.csv"))

#     # ---------------------------
#     # FIX skuid
#     # ---------------------------
#     catalog.columns = catalog.columns.str.strip()
#     if "sku_id" in catalog.columns:
#         catalog.rename(columns={"sku_id": "skuid"}, inplace=True)

#     for df in [fulfillment, orders, inventory, returns, analytics]:
#         df.columns = df.columns.str.strip()
#         if "sku_id" in df.columns:
#             df.rename(columns={"sku_id": "skuid"}, inplace=True)

#     # seller fallback
#     for df in [fulfillment, orders, inventory, returns, analytics]:
#         if "seller_id" not in df.columns:
#             df["seller_id"] = "default_seller"

#     # ---------------------------
#     # FIX RATING
#     # ---------------------------
#     if "customer_rate" not in analytics.columns:
#         if "ratings" in analytics.columns:
#             analytics.rename(columns={"ratings": "customer_rate"}, inplace=True)
#         else:
#             analytics["customer_rate"] = 0

#     # ---------------------------
#     # DATETIME
#     # ---------------------------
#     parse_datetime(catalog, fulfillment, orders, analytics, inventory, returns)

#     # ---------------------------
#     # TIME WINDOW
#     # ---------------------------
#     TIME_WINDOW_CLEAN = {
#         re.sub(r"\s+", "", k.title()).strip(): v
#         for k, v in time_window.items() if v is not None
#     }

#     print("Available categories:", catalog["category_l3"].unique())
#     print("Input keys:", TIME_WINDOW_CLEAN.keys())

#     if "status" in fulfillment.columns:
#         fulfillment = fulfillment[~fulfillment["status"].str.lower().isin(["cancelled"])]

#     # ---------------------------
#     # DATA COLLECTION
#     # ---------------------------
#     fulfillment_dfs, orders_dfs, inventory_dfs, returns_dfs, analytics_dfs = [], [], [], [], []

#     for key, days in TIME_WINDOW_CLEAN.items():
#         cutoff_date = datetime.now() - timedelta(days=days)

#         valid_skus = catalog.loc[catalog["category_l3"] == key, ["skuid", "category_l3"]]

#         if valid_skus.empty:
#             print(f"⚠️ No category match for: {key} → using all SKUs")
#             valid_skus = catalog[["skuid", "category_l3"]]

#         fulfillment_dfs.append(
#             fulfillment[
#                 (fulfillment["created_at"] >= cutoff_date) &
#                 (fulfillment["skuid"].isin(valid_skus["skuid"]))
#             ].merge(valid_skus, on="skuid", how="left")
#         )

#         orders_dfs.append(
#             orders[
#                 (orders["created_at"] >= cutoff_date) &
#                 (orders["skuid"].isin(valid_skus["skuid"]))
#             ].merge(valid_skus, on="skuid", how="left")
#         )

#         inventory_dfs.append(
#             inventory[
#                 (inventory["created_at"] >= cutoff_date) &
#                 (inventory["skuid"].isin(valid_skus["skuid"]))
#             ].merge(valid_skus, on="skuid", how="left")
#         )

#         returns_dfs.append(
#             returns[
#                 (returns["created_at"] >= cutoff_date) &
#                 (returns["skuid"].isin(valid_skus["skuid"]))
#             ].merge(valid_skus, on="skuid", how="left")
#         )

#         analytics_dfs.append(
#             analytics[
#                 (analytics["timestamp"] >= cutoff_date) &
#                 (analytics["skuid"].isin(valid_skus["skuid"]))
#             ].merge(valid_skus, on="skuid", how="left")
#         )

#     # ---------------------------
#     # COMBINE
#     # ---------------------------
#     fulfillmentdf = pd.concat(fulfillment_dfs, ignore_index=True)
#     ordersdf = pd.concat(orders_dfs, ignore_index=True)
#     inventorydf = pd.concat(inventory_dfs, ignore_index=True)
#     returnsdf = pd.concat(returns_dfs, ignore_index=True)
#     analyticsdf = pd.concat(analytics_dfs, ignore_index=True)

#     # ---------------------------
#     # AGGREGATION
#     # ---------------------------
#     fulfillmentdf = fulfillmentdf.groupby(["skuid","seller_id","category_l3"]).agg(
#         sales_count=("quantity","sum")
#     ).reset_index()

#     ordersdf = ordersdf.groupby(["skuid","seller_id","category_l3"]).agg(
#         revenue=("price","sum")
#     ).reset_index()

#     inventorydf = inventorydf.groupby(["skuid","seller_id","category_l3"])["stock_quantity"].sum().reset_index()

#     returnsdf = returnsdf.groupby(["skuid","seller_id","category_l3"]).agg(
#         return_count=("seller_id","count")
#     ).reset_index()

#     analyticsdf = analyticsdf.groupby(["skuid","seller_id","category_l3"]).agg(
#         avg_rating=("customer_rate","mean")
#     ).reset_index()

#     # ---------------------------
#     # MERGE + SCORE
#     # ---------------------------
#     perf = (
#         fulfillmentdf
#         .merge(ordersdf, on=["skuid","seller_id","category_l3"], how="left")
#         .merge(inventorydf, on=["skuid","seller_id","category_l3"], how="left")
#         .merge(returnsdf, on=["skuid","seller_id","category_l3"], how="left")
#         .merge(analyticsdf, on=["skuid","seller_id","category_l3"], how="left")
#     ).fillna(0)

#     perf["return_rate_pct"] = (perf["return_count"] / perf["sales_count"].replace(0, pd.NA)) * 100

#     perf["norm_sales"] = normalize(perf["sales_count"])
#     perf["norm_revenue"] = normalize(perf["revenue"])
#     perf["norm_return"] = 1 - normalize(perf["return_rate_pct"].fillna(0))
#     perf["coverage"] = perf["stock_quantity"] / (perf["sales_count"] + 1e-6)
#     perf["norm_stock"] = normalize(perf["coverage"])

#     perf["final_score"] = (
#         perf["norm_sales"] * sales_score +
#         perf["norm_revenue"] * revenue_score +
#         perf["norm_stock"] * stock_score +
#         perf["norm_return"] * return_rate_score +
#         perf["avg_rating"] * customer_rating_score
#     ) * 100

#     # ---------------------------
#     # INDIVIDUAL SCORES
#     # ---------------------------
#     perf["sales_score_val"] = perf["norm_sales"] * sales_score * 100
#     perf["revenue_score_val"] = perf["norm_revenue"] * revenue_score * 100
#     perf["stock_score_val"] = perf["norm_stock"] * stock_score * 100
#     perf["return_score_val"] = perf["norm_return"] * return_rate_score * 100
#     perf["rating_score_val"] = perf["avg_rating"] * customer_rating_score * 100

#     # ---------------------------
#     # CLEAN MERGE
#     # ---------------------------
#     final_perf = perf.merge(
#         catalog.drop(columns=["category_l3"], errors="ignore"),
#         on="skuid",
#         how="left"
#     )

#     # ---------------------------
#     # FINAL OUTPUT
#     # ---------------------------
#     es_data = final_perf[[
#         "skuid",
#         "seller_id",
#         "category_l1",
#         "category_l2",
#         "category_l3",
#         "selling_price",
#         "product_name",
#         "brand",

#         # scores first
#         "sales_score_val",
#         "revenue_score_val",
#         "stock_score_val",
#         "return_score_val",
#         "rating_score_val",

#         # final score last
#         "final_score"
#     ]].fillna("")

#     es_data = es_data.rename(columns={
#         "selling_price": "price",
#         "product_name": "title",
#         "sales_score_val": "sales_score",
#         "revenue_score_val": "revenue_score",
#         "stock_score_val": "stock_score",
#         "return_score_val": "return_score",
#         "rating_score_val": "rating_score"
#     })

#     es_data = es_data.round(2)
#     es_data = es_data.sort_values(by="final_score", ascending=False)

#     # ---------------------------
#     # PUSH TO MEILI
#     # ---------------------------
#     push_to_meili(
#         docs=df_to_docs(es_data),
#         index_name="best_sellers"
#     )

#     return es_data



# import os
# import numpy as np
# import pandas as pd
# from datetime import datetime, timedelta
# from ..adapters.meili.indexer import push_to_meili

# BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# CSV_DIR = os.path.join(BASE_DIR, "data", "processed")



# # DATETIME FIX (FINAL)
# #Convert a column into proper datetime format safely,why we use this means for crated_at
# def parse_datetime(df, col):
#     if col not in df.columns:
#         df[col] = pd.Timestamp.now()

#     # Handles mixed formats safely (NO warning)
#     df[col] = pd.to_datetime(df[col], errors="coerce", format="mixed")


# # NORMALIZE,use for range [0 --> 1]
# def normalize(series):
#     if len(series) == 0 or series.max() == series.min():
#         return pd.Series([0] * len(series))
#     return (series - series.min()) / (series.max() - series.min())


# # DF → JSON,Convert DataFrame → JSON (API / MeiliSearch)
# def df_to_docs(df):
#     df = df.replace([np.nan, np.inf, -np.inf], None)
#     return df.to_dict(orient="records")



# # MAIN PIPELINE

# def run_bestseller_pipeline(weights: dict, time_window: dict):

#     print(" BEST SELLER PIPELINE STARTED")

   
#     # LOAD CSVs
    
#     catalog = pd.read_csv(os.path.join(CSV_DIR, "catalog.csv"))
#     fulfillment = pd.read_csv(os.path.join(CSV_DIR, "fulfillment.csv"))
#     orders = pd.read_csv(os.path.join(CSV_DIR, "orders.csv"))
#     analytics = pd.read_csv(os.path.join(CSV_DIR, "analytics.csv"))
#     inventory = pd.read_csv(os.path.join(CSV_DIR, "inventory.csv"))
#     returns = pd.read_csv(os.path.join(CSV_DIR, "returns.csv"))


#     # CLEAN COLUMNS
    
#     for df in [catalog, fulfillment, orders, analytics, inventory, returns]:
#         df.columns = df.columns.str.strip()
#         if "sku_id" in df.columns:
#             df.rename(columns={"sku_id": "skuid"}, inplace=True)

#     catalog["category_l3"] = catalog["category_l3"].astype(str).str.strip().str.lower()

#     for df in [fulfillment, orders, inventory, returns, analytics]:
#         if "seller_id" not in df.columns:
#             df["seller_id"] = "default_seller"

#     if "customer_rate" not in analytics.columns:
#         analytics["customer_rate"] = 0

    
#     # DATETIME
#     parse_datetime(fulfillment, "created_at")
#     parse_datetime(orders, "created_at")
#     parse_datetime(inventory, "created_at")
#     parse_datetime(returns, "created_at")
#     parse_datetime(analytics, "timestamp")

   
#     # WEIGHTS
#     sales_w = weights.get("sales_score", 0.35)
#     revenue_w = weights.get("revenue_score", 0.25)
#     stock_w = weights.get("stock_score", 0.20)
#     return_w = weights.get("return_rate_score", 0.10)
#     rating_w = weights.get("customer_rating_score", 0.10)
#     seller_w = weights.get("seller_score", 0.10)

   
#     # THRESHOLDS
    
#     sales_t = weights.get("sales_threshold", 0)
#     revenue_t = weights.get("revenue_threshold", 0)
#     stock_t = weights.get("stock_threshold", 0)
#     return_t = weights.get("return_rate_threshold", 100)
#     rating_t = weights.get("customer_rating_threshold", 0)
#     final_t = weights.get("final_score_threshold", 0)

    
#     # TIME WINDOW (FIXED)
    
#     f_list, o_list, i_list, r_list, a_list = [], [], [], [], []

#     for _, days in time_window.items():

#         cutoff = datetime.now() - timedelta(days=days)

#         valid_skus = catalog[["skuid", "category_l3"]]

#         f_list.append(fulfillment[(fulfillment["created_at"] >= cutoff) & (fulfillment["skuid"].isin(valid_skus["skuid"]))].merge(valid_skus))
#         o_list.append(orders[(orders["created_at"] >= cutoff) & (orders["skuid"].isin(valid_skus["skuid"]))].merge(valid_skus))
#         i_list.append(inventory[(inventory["created_at"] >= cutoff) & (inventory["skuid"].isin(valid_skus["skuid"]))].merge(valid_skus))
#         r_list.append(returns[(returns["created_at"] >= cutoff) & (returns["skuid"].isin(valid_skus["skuid"]))].merge(valid_skus))
#         a_list.append(analytics[(analytics["timestamp"] >= cutoff) & (analytics["skuid"].isin(valid_skus["skuid"]))].merge(valid_skus))

#     fulfillmentdf = pd.concat(f_list, ignore_index=True) #join the data row wise
#     ordersdf = pd.concat(o_list, ignore_index=True)
#     inventorydf = pd.concat(i_list, ignore_index=True)
#     returnsdf = pd.concat(r_list, ignore_index=True)
#     analyticsdf = pd.concat(a_list, ignore_index=True)

#     print("Fulfillment rows:", len(fulfillmentdf))

#     if fulfillmentdf.empty:
#         print(" No data after date filter")
#         return pd.DataFrame()

    
#     # AGGREGATION
#     fulfillmentdf = fulfillmentdf.groupby(["skuid","seller_id","category_l3"]).agg(sales_count=("quantity","sum")).reset_index()
#     ordersdf = ordersdf.groupby(["skuid","seller_id","category_l3"]).agg(revenue=("price","sum")).reset_index()
#     inventorydf = inventorydf.groupby(["skuid","seller_id","category_l3"])["stock_quantity"].sum().reset_index()
#     returnsdf = returnsdf.groupby(["skuid","seller_id","category_l3"]).agg(return_count=("seller_id","count")).reset_index()
#     analyticsdf = analyticsdf.groupby(["skuid","seller_id","category_l3"]).agg(avg_rating=("customer_rate","mean")).reset_index()

   
#     # MERGE
#     perf = (
#         fulfillmentdf
#         .merge(ordersdf, on=["skuid","seller_id","category_l3"], how="left")
#         .merge(inventorydf, on=["skuid","seller_id","category_l3"], how="left")
#         .merge(returnsdf, on=["skuid","seller_id","category_l3"], how="left")
#         .merge(analyticsdf, on=["skuid","seller_id","category_l3"], how="left")
#     ).fillna(0)

   
#     # SCORING
  
#     perf["return_rate_pct"] = (perf["return_count"] / perf["sales_count"].replace(0, pd.NA)) * 100
#     perf["return_rate_pct"] = perf["return_rate_pct"].fillna(0)

#     perf["norm_sales"] = normalize(perf["sales_count"])
#     perf["norm_revenue"] = normalize(perf["revenue"])
#     perf["norm_return"] = 1 - normalize(perf["return_rate_pct"])
#     perf["norm_stock"] = normalize(perf["stock_quantity"])
#     perf["norm_seller"] = normalize(perf["seller_score"])

#     perf["sales_score_val"] = perf["norm_sales"] * sales_w * 100
#     perf["revenue_score_val"] = perf["norm_revenue"] * revenue_w * 100
#     perf["stock_score_val"] = perf["norm_stock"] * stock_w * 100
#     perf["return_score_val"] = perf["norm_return"] * return_w * 100
#     perf["rating_score_val"] = perf["avg_rating"] * rating_w * 100
#     perf["seller_score_val"] = perf["norm_seller"] * seller_w * 100

#     perf["final_score"] = (
#         perf["sales_score_val"] +
#         perf["revenue_score_val"] +
#         perf["stock_score_val"] +
#         perf["return_score_val"] +
#         perf["rating_score_val"]+
#         perf["seller_score_val"]
#     )
#     perf["seller_score"] = perf.groupby("seller_id")["final_score"].transform("mean")
    
#     # SAVE ORIGINAL
  
#     original_perf = perf.copy()
#     print("Before filtering:", len(perf))

   
#     # SAFE FILTERING (FINAL)
   
#     def safe_filter(df, condition):
#         temp = df[condition]
#         return temp if len(temp) > 20 else df
#     if sales_t > 0:
#         perf = safe_filter(perf, perf["sales_count"] >= perf["sales_count"].quantile(sales_t / 100))
#     if revenue_t > 0:
#         perf = safe_filter(perf, perf["revenue"] >= perf["revenue"].quantile(revenue_t / 100))
#     if stock_t > 0:
#         perf = safe_filter(perf, perf["stock_quantity"] >= perf["stock_quantity"].quantile(stock_t / 100))
#     perf = safe_filter(perf, perf["return_rate_pct"] <= return_t)
#     if rating_t > 0:
#         perf = safe_filter(perf, perf["avg_rating"] >= rating_t)
#     if final_t > 0:
#         perf = safe_filter(perf, perf["final_score"] >= final_t)
#     print("After filtering:", len(perf))

   
#     # FALLBACK
   
#     if perf.empty:
#         print(" No data → using original scored data")
#         perf = original_perf.sort_values(by="final_score", ascending=False).head(50)

   
#     # FINAL MERGE
#     final_perf = perf.merge(
#         catalog.drop(columns=["category_l3"], errors="ignore"),
#         on="skuid",
#         how="left"
#     )

    
#     # OUTPUT
    
#     es_data = final_perf[[
#         "skuid","seller_id","category_l1","category_l2","category_l3",
#         "selling_price","product_name","brand",
#         "sales_score_val","revenue_score_val","stock_score_val",
#         "return_score_val","rating_score_val",
#         "final_score"
#     ]].fillna("")

#     es_data = es_data.rename(columns={
#         "selling_price": "price",
#         "product_name": "title"
#     })

#     es_data = es_data.sort_values(by="final_score", ascending=False)

#     push_to_meili(
#         docs=df_to_docs(es_data),
#         index_name="best_sellers"
#     )

#     return es_data

import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
# from ..adapters.meili.indexer import push_to_meili
# from ..es_utils.es_utils import push_to_es
from ..adapters.es.indexer import push_to_es



BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_DIR = os.path.join(BASE_DIR, "data", "processed")


# -------------------- UTIL FUNCTIONS --------------------

def parse_datetime(df, col):
    if col not in df.columns:
        df[col] = pd.Timestamp.now()
    df[col] = pd.to_datetime(df[col], errors="coerce", format="mixed")


def normalize(series):
    if len(series) == 0 or series.max() == series.min():
        return pd.Series([0] * len(series))
    return (series - series.min()) / (series.max() - series.min())


def df_to_docs(df):
    df = df.replace([np.nan, np.inf, -np.inf], None)
    return df.to_dict(orient="records")


# -------------------- MAIN PIPELINE --------------------

def run_bestseller_pipeline(weights: dict, time_window: dict,client: str):

    print("BEST SELLER PIPELINE STARTED")

    # LOAD DATA
    catalog = pd.read_csv(os.path.join(CSV_DIR, "catalog.csv"))
    fulfillment = pd.read_csv(os.path.join(CSV_DIR, "fulfillment.csv"))
    orders = pd.read_csv(os.path.join(CSV_DIR, "orders.csv"))
    analytics = pd.read_csv(os.path.join(CSV_DIR, "analytics.csv"))
    inventory = pd.read_csv(os.path.join(CSV_DIR, "inventory.csv"))
    returns = pd.read_csv(os.path.join(CSV_DIR, "returns.csv"))

    # CLEAN
    for df in [catalog, fulfillment, orders, analytics, inventory, returns]:
        df.columns = df.columns.str.strip()
        if "sku_id" in df.columns:
            df.rename(columns={"sku_id": "skuid"}, inplace=True)

    catalog["category_l3"] = catalog["category_l3"].astype(str).str.strip().str.lower()

    for df in [fulfillment, orders, inventory, returns, analytics]:
        if "seller_id" not in df.columns:
            df["seller_id"] = "default_seller"

    if "customer_rate" not in analytics.columns:
        analytics["customer_rate"] = 0

    # DATETIME
    parse_datetime(fulfillment, "created_at")
    parse_datetime(orders, "created_at")
    parse_datetime(inventory, "created_at")
    parse_datetime(returns, "created_at")
    parse_datetime(analytics, "timestamp")

    # WEIGHTS
    sales_w = weights.get("sales_score", 0.35)
    revenue_w = weights.get("revenue_score", 0.25)
    stock_w = weights.get("stock_score", 0.20)
    return_w = weights.get("return_rate_score", 0.10)
    rating_w = weights.get("customer_rating_score", 0.10)
    seller_w = weights.get("seller_score", 0.05)  # keep low

    # THRESHOLDS
    sales_t = weights.get("sales_threshold", 0)
    revenue_t = weights.get("revenue_threshold", 0)
    stock_t = weights.get("stock_threshold", 0)
    return_t = weights.get("return_rate_threshold", 100)
    rating_t = weights.get("customer_rating_threshold", 0)
    final_t = weights.get("final_score_threshold", 0)

    # TIME WINDOW
    f_list, o_list, i_list, r_list, a_list = [], [], [], [], []

    for _, days in time_window.items():
        cutoff = datetime.now() - timedelta(days=days)
        valid_skus = catalog[["skuid", "category_l3"]]

        f_list.append(fulfillment[(fulfillment["created_at"] >= cutoff) & (fulfillment["skuid"].isin(valid_skus["skuid"]))].merge(valid_skus))
        o_list.append(orders[(orders["created_at"] >= cutoff) & (orders["skuid"].isin(valid_skus["skuid"]))].merge(valid_skus))
        i_list.append(inventory[(inventory["created_at"] >= cutoff) & (inventory["skuid"].isin(valid_skus["skuid"]))].merge(valid_skus))
        r_list.append(returns[(returns["created_at"] >= cutoff) & (returns["skuid"].isin(valid_skus["skuid"]))].merge(valid_skus))
        a_list.append(analytics[(analytics["timestamp"] >= cutoff) & (analytics["skuid"].isin(valid_skus["skuid"]))].merge(valid_skus))

    fulfillmentdf = pd.concat(f_list, ignore_index=True)
    ordersdf = pd.concat(o_list, ignore_index=True)
    inventorydf = pd.concat(i_list, ignore_index=True)
    returnsdf = pd.concat(r_list, ignore_index=True)
    analyticsdf = pd.concat(a_list, ignore_index=True)

    if fulfillmentdf.empty:
        print("No data after date filter")
        return pd.DataFrame()

    # AGGREGATION
    fulfillmentdf = fulfillmentdf.groupby(["skuid","seller_id","category_l3"]).agg(sales_count=("quantity","sum")).reset_index()
    ordersdf = ordersdf.groupby(["skuid","seller_id","category_l3"]).agg(revenue=("price","sum")).reset_index()
    inventorydf = inventorydf.groupby(["skuid","seller_id","category_l3"])["stock_quantity"].sum().reset_index()
    returnsdf = returnsdf.groupby(["skuid","seller_id","category_l3"]).agg(return_count=("seller_id","count")).reset_index()
    analyticsdf = analyticsdf.groupby(["skuid","seller_id","category_l3"]).agg(avg_rating=("customer_rate","mean")).reset_index()

    # MERGE
    perf = (
        fulfillmentdf
        .merge(ordersdf, on=["skuid","seller_id","category_l3"], how="left")
        .merge(inventorydf, on=["skuid","seller_id","category_l3"], how="left")
        .merge(returnsdf, on=["skuid","seller_id","category_l3"], how="left")
        .merge(analyticsdf, on=["skuid","seller_id","category_l3"], how="left")
    ).fillna(0)

    # -------------------- SCORING --------------------

    perf["return_rate_pct"] = (perf["return_count"] / perf["sales_count"].replace(0, pd.NA)) * 100
    perf["return_rate_pct"] = perf["return_rate_pct"].fillna(0)

    perf["norm_sales"] = normalize(perf["sales_count"])
    perf["norm_revenue"] = normalize(perf["revenue"])
    perf["norm_return"] = 1 - normalize(perf["return_rate_pct"])
    perf["norm_stock"] = normalize(perf["stock_quantity"])

    # BASE SCORES
    perf["sales_score_val"] = perf["norm_sales"] * sales_w * 100
    perf["revenue_score_val"] = perf["norm_revenue"] * revenue_w * 100
    perf["stock_score_val"] = perf["norm_stock"] * stock_w * 100
    perf["return_score_val"] = perf["norm_return"] * return_w * 100
    perf["rating_score_val"] = perf["avg_rating"] * rating_w * 100

    perf["final_score"] = (
        perf["sales_score_val"] +
        perf["revenue_score_val"] +
        perf["stock_score_val"] +
        perf["return_score_val"] +
        perf["rating_score_val"]
    )

    
    perf["seller_score"] = perf.groupby("seller_id")["final_score"].transform("mean")
    perf["norm_seller"] = normalize(perf["seller_score"])
    perf["seller_score_val"] = perf["norm_seller"] * seller_w * 100

    # ADD TO FINAL SCORE
    perf["final_score"] = perf["final_score"] + perf["seller_score_val"]

    # -------------------- FILTERING --------------------

    original_perf = perf.copy()

    def safe_filter(df, condition):
        temp = df[condition]
        return temp if len(temp) > 20 else df

    if sales_t > 0:
        perf = safe_filter(perf, perf["sales_count"] >= perf["sales_count"].quantile(sales_t / 100))
    if revenue_t > 0:
        perf = safe_filter(perf, perf["revenue"] >= perf["revenue"].quantile(revenue_t / 100))
    if stock_t > 0:
        perf = safe_filter(perf, perf["stock_quantity"] >= perf["stock_quantity"].quantile(stock_t / 100))

    perf = safe_filter(perf, perf["return_rate_pct"] <= return_t)

    if rating_t > 0:
        perf = safe_filter(perf, perf["avg_rating"] >= rating_t)

    if final_t > 0:
        perf = safe_filter(perf, perf["final_score"] >= final_t)

    if perf.empty:
        perf = original_perf.sort_values(by="final_score", ascending=False).head(50)

    # FINAL MERGE
    final_perf = perf.merge(
        catalog.drop(columns=["category_l3"], errors="ignore"),
        on="skuid",
        how="left"
    )

    # # OUTPUT
    # es_data = final_perf[[
    #     "skuid","seller_id","category_l1","category_l2","category_l3",
    #     "selling_price","product_name","brand",
    #     "sales_score_val","revenue_score_val","stock_score_val",
    #     "return_score_val","rating_score_val",
    #     "seller_score_val",
    #     "final_score"
    # ]].fillna("")

    # es_data = es_data.rename(columns={
    #     "selling_price": "price",
    #     "product_name": "title"
    # })

    # es_data = es_data.sort_values(by="final_score", ascending=False)

    # push_to_meili(
    #     docs=df_to_docs(es_data),
    #     index_name=f"{client}best_sellers"
    # )

    # return es_data

    es_data = final_perf[[
    "skuid","seller_id","category_l1","category_l2","category_l3",
    "selling_price","product_name","brand",
    "sales_score_val","revenue_score_val","stock_score_val",
    "return_score_val","rating_score_val",
    "seller_score_val",
    "final_score"
]].fillna({
    "price": 0,
    "final_score": 0,
    "sales_score_val": 0,
    "revenue_score_val": 0,
    "stock_score_val": 0,
    "return_score_val": 0,
    "rating_score_val": 0,
    "seller_score_val": 0
})

    es_data = es_data.rename(columns={
        "selling_price": "price",
        "product_name": "title",
        "category_l1": "l1",
        "category_l2": "l2",
        "category_l3": "l3"
    })

    es_data = es_data.sort_values(by="final_score", ascending=False)

    docs = df_to_docs(es_data)

    #  Elasticsearch push
    push_to_es(
        INDEX_PREFIX=f"{client}_best_sellers",
        ALIAS_NAME=f"{client}_best_sellers",
        docs=docs
    )

    return es_data
