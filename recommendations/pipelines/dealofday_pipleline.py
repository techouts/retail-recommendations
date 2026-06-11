import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from ..utils.pipeline_utils import load_csv_from_s3, normalize
from ..adapters.meili.indexer import push_to_meili
from types import SimpleNamespace
from .utils import normalize_df
from ..adapters.es.indexer import push_to_es

import logging

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)



def df_to_es_docs(df: pd.DataFrame) -> list[dict]:
    
    df = df.replace([np.nan, np.inf, -np.inf], None)
    return df.to_dict(orient="records")



from datetime import datetime as dt
def run_dod_pipeline(DealOfDayWeights : dict , client : str , levels : list):
        
    dod_weights = SimpleNamespace(**DealOfDayWeights)
    
    logger.info(f"Dod weights: {dod_weights}")
    
    s3_path = os.getenv("S3_PATH", "s3://retail-search")

    # Load CSVs from S3 by client
    catalog         = normalize_df(load_csv_from_s3(s3_path, client, "catalog"))
    inventory       =  normalize_df(load_csv_from_s3(s3_path, client, "inventory"))
    analytics       = normalize_df(load_csv_from_s3(s3_path, client, "analytics"))
    customer_rating = normalize_df(load_csv_from_s3(s3_path, client, "customer_rating"))
    pmr             = normalize_df(load_csv_from_s3(s3_path, client, "pmr"))

    logger.info(f"Catalog rows: {len(catalog)}")
    logger.info(f"Inventory rows: {len(inventory)}")
    logger.info(f"Analytics rows: {len(analytics)}")
    logger.info(f"Ratings rows: {len(customer_rating)}")

    catalog["created_at"] = pd.to_datetime(catalog["created_at"], errors="coerce")
    # pmr["discount_enddate"] = pd.to_datetime(pmr["discount_enddate"], errors="coerce")
    pmr["discount_enddate"] = pd.to_datetime(
    pmr["discount_enddate"],
    errors="coerce",
    dayfirst=True
)

    def normalize(series):
        if series.max() == series.min():
            return pd.Series([0.5] * len(series), index=series.index)   
        return (series - series.min()) / (series.max() - series.min())

    # Filter PMR data
    # pmrdf = pmr[
    #     (pmr["discount_enddate"].dt.date >= dt.today().date()) &
    #     (pmr["discount_price"].between(dod_weights.min_discount_threshold, dod_weights.max_discount_threshold))
    # ].copy()
    
    pmrdf = pmr.copy()
    pmrdf = pmrdf.sort_values("discount_price", ascending=False)
    pmrdf = pmrdf.drop_duplicates(subset=["skuid"], keep="first")
    pmrdf["discount_enddate"] = pd.to_datetime(pmrdf["discount_enddate"], errors="coerce", dayfirst=True)
    pmrdf = pmrdf[pmrdf["discount_enddate"].dt.date >= dt.today().date()]
    logger.info(f"Today date: {dt.today().date()}")
    logger.debug(f"pmrdf:\n{pmrdf.head(100).to_string()}")
    
    # Filter catalog by L3 and PMR SKUs
    if levels:
        catalogdf = catalog[
            (catalog["category_l3"].isin(levels)) &
            (catalog["skuid"].isin(pmrdf["skuid"]))
        ].copy()
    else:
        catalogdf = catalog[
            catalog["skuid"].isin(pmrdf["skuid"])
        ].copy()
    catalogdf["is_new"] = (dt.today() - catalogdf["created_at"]).dt.days <= dod_weights.new_product_window_days

    logger.debug(f"catalog df:\n{catalogdf.head(10).to_string()}")

    
    # Inventory filter
    inventorydf = inventory[inventory["skuid"].isin(catalogdf["skuid"])].copy()
    
    logger.debug(f"Inventory df 1:\n{inventorydf.head(10).to_string()}")
    
    inventorydf = inventorydf.groupby("skuid").agg(total_quantity=("stock_quantity", "sum")).reset_index()
    
    logger.debug(f"Inventory df 2:\n{inventorydf.head(10).to_string()}")

    inventorydf = inventorydf[inventorydf["total_quantity"] >= dod_weights.min_stock]
    
    logger.debug(f"Inventory df 3:\n{inventorydf.head(10).to_string()}")
    print("PMR:", len(pmrdf))
    print("Catalog:", len(catalogdf))
    print("Inventory:", len(inventorydf))
    print("PMR:", len(pmrdf))
    print("Catalog:", len(catalogdf))
    print("Inventory:", len(inventorydf))

    # Analytics aggregation
    analyticsdf = analytics[analytics["skuid"].isin(inventorydf["skuid"])].copy()
    
    logger.debug(f"Analytics 1:\n{analyticsdf.head(10).to_string()}")

    analyticsdf.columns = analyticsdf.columns.str.lower().str.strip()

        #  Rename columns to match pipeline expectation
    analyticsdf.rename(columns={
            "views": "view_count",
            "view": "view_count",
            "add_to_cart": "addtocart_count",
            "addtocart": "addtocart_count",
            "sku": "skuid",
            "sku_id": "skuid"
        }, inplace=True)

        #  Ensure required columns exist
    for col in ["skuid", "view_count", "addtocart_count"]:
        if col not in analyticsdf.columns:
                analyticsdf[col] = 0

    analyticsdf = analyticsdf.groupby("skuid")[["addtocart_count", "view_count"]].sum().reset_index()
    #  Normalize column names
    
    
    logger.debug(f"Analytics 2:\n{analyticsdf.head(10).to_string()}")

    # Ratings aggregation
    ratingdf = customer_rating[customer_rating["skuid"].isin(inventorydf["skuid"])].copy()
    
    logger.debug(f"Ratings df:\n{ratingdf.head(10).to_string()}")
    
    ratingdf = ratingdf.groupby("skuid").agg(
        review_count=("skuid", "count"),
        avg_rating=("rating", "mean")
    ).reset_index()
    
    # ratingdf = ratingdf[ratingdf["avg_rating"] >= dod_weights.rating_threshold]

    logger.info("Ratings df:\n%s", ratingdf.head(10))
    # Merge all data
    resultdf = (
        catalogdf.merge(pmrdf, on="skuid", how="left")
                 .merge(inventorydf, on="skuid", how="left")
                 .merge(analyticsdf, on="skuid", how="left")
                 .merge(ratingdf, on="skuid", how="left")
    )
    resultdf = resultdf.loc[:, ~resultdf.columns.str.endswith(('_x', '_y'))]
    
    resultdf["review_count"] = resultdf["review_count"].fillna(0)
    resultdf["avg_rating"] = resultdf["avg_rating"].fillna(0)

    
    logger.debug(f"Resultdf:\n{resultdf.head(10).to_string()}")
    
    
    # Adaptive review filtering
    filtered = resultdf[resultdf["review_count"] >= dod_weights.min_reviews].copy()
    
    logger.debug(f"filtered df:\n{filtered.head(25).to_string()}")
    logger.info(f"Null category count: {filtered['category_l3'].isna().sum()}")
    
    count_after_filter = filtered.groupby("category_l3").agg(
        count=("skuid", "count"),
        skuid=("skuid", lambda x: list(x))
    ).reset_index()
    
    logger.info(f"Filtered results:\n{count_after_filter}")
    
    # Debug log: track relaxed review logic per L3
    final_df_list = []
    relaxed_review_log = []

    for k, v, skuid in count_after_filter.itertuples(index=False):
        if v > 0:
            temp_df = resultdf[(resultdf["category_l3"] == k) & (resultdf["skuid"].isin(skuid))].copy()
            temp_df["relaxed_review"] = False
            relaxed_review_log.append({"l3": k, "relaxed_review": False, "qualified_skus": len(skuid)})
        else:
            temp_df = resultdf[resultdf["category_l3"]  == k].copy()
            temp_df["relaxed_review"] = True
            relaxed_review_log.append({"l3": k, "relaxed_review": True, "qualified_skus": 0})
        final_df_list.append(temp_df)

    final_df = pd.concat(final_df_list, ignore_index=True) if final_df_list else pd.DataFrame()

   
    for entry in relaxed_review_log:
       logger.info(f"L3: {entry['l3']} | Relaxed: {entry['relaxed_review']} | Qualified SKUs: {entry['qualified_skus']}")

    # Normalize and score
    if not final_df.empty:
        final_df["normalized_views"] = normalize(final_df["view_count"])
        final_df["normalized_addtocart"] = normalize(final_df["addtocart_count"])
        final_df["normalized_rating"] = normalize(final_df["avg_rating"])
        final_df["normalized_reviews"] = normalize(final_df["review_count"])

        final_df["score"] = (
            dod_weights.reviews_weight * final_df["normalized_reviews"] +
            dod_weights.views_weight * final_df["normalized_views"] +
            dod_weights.addtocart_weight * final_df["normalized_addtocart"] +
            dod_weights.rating_weight * final_df["normalized_rating"]
        ) * 100

        final_df = final_df[final_df["score"] >= dod_weights.final_score_threshold].copy()
        print("After Score Filter:", len(final_df))
    logger.debug(f"Final df:\n{final_df.head(10).to_string()}")

    # L3 capped selection
    final_list = []
    if not final_df.empty:
        total_to_show = min(len(final_df), 50)
        
        l3_groups = final_df["category_l3"].unique()
        per_cat = max(1, round(total_to_show / len(l3_groups)))

        for l3 in l3_groups:
            subset = final_df[final_df["category_l3"] == l3].copy()

            print(f"L3={l3}")
            print("Subset Count:", len(subset))

            new_prod = subset[subset["is_new"]]
            top_by_score = subset.sort_values(by="score", ascending=False)

            if not new_prod.empty:
                pick = pd.concat([
                    new_prod.head(1),
                    top_by_score.head(per_cat - 1)
                ]).drop_duplicates("skuid")
            else:
                pick = top_by_score.head(per_cat)

            print("Pick Count:", len(pick))
            print(pick[["skuid", "score"]])

            final_list.append(pick)

            print("Final List Length:", len(final_list))
            print("Before Final Selection:", len(final_df))
            print("Score Stats:")
            print(final_df["score"].describe())

            print("Top Scores:")
            print(
                final_df[["skuid", "score"]]
                .sort_values("score", ascending=False)
                .head(20)
            )
            print("LEVELS:", levels)
            print("CATALOGDF:", catalogdf.shape)
            print("INVENTORYDF:", inventorydf.shape)
            print("ANALYTICSDF:", analyticsdf.shape)
            print("RATINGDF:", ratingdf.shape)
            print("RESULTDF:", resultdf.shape)
            print("FILTERED:", filtered.shape)
            print("FINAL_LIST:", len(final_list))
    final_df = pd.concat(final_list, ignore_index=True) if final_list else pd.DataFrame()
    
    logger.info(f"Final df columns: {list(final_df.columns)}")
    
    logger.debug(f"Final df full:\n{final_df.to_string()}")
    
    for col in final_df.select_dtypes(include=["datetime64[ns]"]).columns:
        final_df[col] = final_df[col].astype(str)
    
    # Save to DB and push to ES
    # values = final_df['l3'].tolist()
    
    # es_df = final_df[[
    #         "sku", "l1", "l2", "l3", "title", "brand", "pmr_price",
    #         "pmr_discount", "is_new", "name", "discount_enddate",
    #         "avg_rating", "relaxed_review", "score"
    #     ]].copy()
    
    
    final_df = final_df.rename(columns={
        "skuid": "sku",
        "product_name": "title",
        "category_l1": "l1",
        "category_l2": "l2",
        "category_l3": "l3",
        "discount_price": "pmr_discount",
        "addtocart_count": "addtocart",
        "view_count": "views",
        "stock_status": "availability"
    })
    if final_df.empty:
        logger.warning("Final dataframe is empty")
        return {"data": []}

    es_df = final_df[[
    'sku', 'title', 'l1', 'l2', 'l3', 'brand', 'availability',
    'is_new', 'pmr_discount',
    'discount_enddate', 'total_quantity', 'addtocart', 'views',
    'review_count', 'avg_rating', 'relaxed_review',
    'normalized_views', 'normalized_addtocart',
    'normalized_rating', 'normalized_reviews', 'score'
]].copy()
    
    
    docs = df_to_es_docs(es_df)
 
    push_to_es(
        INDEX_PREFIX=f"{client}_deal_of_day",
        ALIAS_NAME=f"{client}_deal_of_day",
        docs=docs
    )    
    
    #  ms
    # push_to_meili(
    #         docs=docs,
    #         index_name=f"{client}_deal_of_day"
    #     )
    
    # # return final_df.to_dict(orient="records")
    # return docs
    
    
    #  es
    if not final_df.empty:
        docs = df_to_es_docs(es_df)
        push_to_es(docs=docs, ALIAS_NAME="dod_recommendations", INDEX_PREFIX="deal_of_the_day")
        logger.info("Final selection pushed to ES")
    else:
        logger.warning("No final products to push to ES")
    return {"data": docs}