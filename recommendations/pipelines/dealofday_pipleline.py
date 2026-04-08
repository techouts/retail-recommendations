import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from ..utils.pipeline_utils import load_csv, normalize
from ..adapters.meili.indexer import push_to_meili
from types import SimpleNamespace
from ..adapters.es.indexer import push_to_es

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_DIR = os.path.join(BASE_DIR, "data", "processed")

catalog = pd.read_csv(os.path.join(CSV_DIR,"catalog.csv"))
inventory = pd.read_csv(os.path.join(CSV_DIR,"inventory.csv"))
analytics = pd.read_csv(os.path.join(CSV_DIR,"analytics.csv"))
customer_rating = pd.read_csv(os.path.join(CSV_DIR,"customer_rating.csv"))
pmr = pd.read_csv(os.path.join(CSV_DIR,"pmr.csv"))

catalog["created_at"] = pd.to_datetime(catalog["created_at"], errors="coerce")
pmr["discount_enddate"] = pd.to_datetime(pmr["discount_enddate"], errors="coerce")

def normalize(series):
    if series.max() == series.min():
        return pd.Series([0.5] * len(series), index=series.index)   
    return (series - series.min()) / (series.max() - series.min())

# def get_dod_settings():
#     return DealOfTheDaySetting.objects.filter(id=1).first()

from datetime import datetime as dt
def run_dod_pipeline(DealOfDayWeights : dict , client : str , levels : list):
    
    dod_weights = SimpleNamespace(**DealOfDayWeights)
    
    print("Dod weights : ",dod_weights)
    # review_threshold = dod_weights.min_reviews
    
    date_str = '2025-07-10'
    date_obj = dt.strptime(date_str, '%Y-%m-%d').date()

    # Filter PMR data
    pmrdf = pmr[    
        # (pmr["discount_enddate"].dt.date >= dt.today().date()) &
        (pmr["discount_enddate"].dt.date >= date_obj) &
        (pmr["pmr_discount"].between(dod_weights.min_discount_threshold, dod_weights.max_discount_threshold))
    ].copy()
    # print("PMR head : ", pmr.head(10))
    print("Today date : ",dt.today().date())
    print("pmrdf: ",pmrdf.head(10))
    # print("Catalog head : ",catalog.head(10))
    # Filter catalog by L3 and PMR SKUs
    catalogdf = catalog[
        (catalog["l3"].isin(levels)) & (catalog["skuid"].isin(pmrdf["skuid"]))
    ].copy()
    catalogdf["is_new"] = (dt.today() - catalogdf["created_at"]).dt.days <= dod_weights.new_product_window_days

    print("catalog df : ",catalogdf.head(10))
    
    # Inventory filter
    inventorydf = inventory[inventory["skuid"].isin(catalogdf["skuid"])].copy()
    inventorydf = inventorydf.groupby("skuid").agg(total_quantity=("quantity", "sum")).reset_index()
    inventorydf = inventorydf[inventorydf["total_quantity"] >= dod_weights.min_stock]
    
    print("Inventory df : ",inventorydf.head(10))

    # Analytics aggregation
    analyticsdf = analytics[analytics["skuid"].isin(inventorydf["skuid"])].copy()
    analyticsdf = analyticsdf.groupby("skuid")[["addtocart", "views"]].sum().reset_index()
    
    print("Analytics : ",analyticsdf.head(10))

    # Ratings aggregation
    ratingdf = customer_rating[customer_rating["skuid"].isin(inventorydf["skuid"])].copy()
    print("Ratings df : ",ratingdf.head(10))
    ratingdf = ratingdf.groupby("skuid").agg(
        review_count=("skuid", "count"),
        avg_rating=("rating", "mean")
    ).reset_index()
    
    # ratingdf = ratingdf[ratingdf["avg_rating"] >= dod_weights.rating_threshold]

    print("Ratings df : ",ratingdf.head(10))
    # Merge all data
    resultdf = (
        catalogdf.merge(pmrdf, on="skuid", how="left")
                 .merge(inventorydf, on="skuid", how="left")
                 .merge(analyticsdf, on="skuid", how="left")
                 .merge(ratingdf, on="skuid", how="left")
    )
    resultdf = resultdf.loc[:, ~resultdf.columns.str.endswith(('_x', '_y'))]
    
    print("Resultdf : ",resultdf.head(10))

    # Adaptive review filtering
    filtered = resultdf[resultdf["review_count"] >= dod_weights.min_reviews].copy()
    print("filtered df : ",resultdf.head(10))
    
    count_after_filter = filtered.groupby("l3").agg(
        count=("skuid", "count"),
        skuid=("skuid", lambda x: list(x))
    ).reset_index()
    
    print("Filtered results : ",count_after_filter.head(10))

    # Debug log: track relaxed review logic per L3
    final_df_list = []
    relaxed_review_log = []

    for k, v, skuid in count_after_filter.itertuples(index=False):
        if v > 0:
            temp_df = resultdf[(resultdf["l3"] == k) & (resultdf["skuid"].isin(skuid))].copy()
            temp_df["relaxed_review"] = False
            relaxed_review_log.append({"l3": k, "relaxed_review": False, "qualified_skus": len(skuid)})
        else:
            temp_df = resultdf[resultdf["l3"] == k].copy()
            temp_df["relaxed_review"] = True
            relaxed_review_log.append({"l3": k, "relaxed_review": True, "qualified_skus": 0})
        final_df_list.append(temp_df)

    final_df = pd.concat(final_df_list, ignore_index=True) if final_df_list else pd.DataFrame()

    # Print debug summary
    # print("🔍 Review Relaxation Summary:")
    for entry in relaxed_review_log:
        print(f"  - L3: {entry['l3']} | Relaxed: {entry['relaxed_review']} | Qualified SKUs: {entry['qualified_skus']}")

    # Normalize and score
    if not final_df.empty:
        final_df["normalized_views"] = normalize(final_df["views"])
        final_df["normalized_addtocart"] = normalize(final_df["addtocart"])
        final_df["normalized_rating"] = normalize(final_df["avg_rating"])
        final_df["normalized_reviews"] = normalize(final_df["review_count"])

        final_df["score"] = (
            dod_weights.reviews_weight * final_df["normalized_reviews"] +
            dod_weights.views_weight * final_df["normalized_views"] +
            dod_weights.addtocart_weight * final_df["normalized_addtocart"] +
            dod_weights.rating_weight * final_df["normalized_rating"]
        ) * 100

        final_df = final_df[final_df["score"] >= dod_weights.final_score_threshold].copy()

    # L3 capped selection
    final_list = []
    if not final_df.empty:
        total_to_show = min(len(final_df), 12)
        l3_groups = final_df["l3"].unique()
        per_cat = max(1, round(total_to_show / len(l3_groups)))

        for l3 in l3_groups:
            subset = final_df[final_df["l3"] == l3].copy()
            new_prod = subset[subset["is_new"]]
            top_by_score = subset.sort_values(by="score", ascending=False)
            if not new_prod.empty:
                pick = pd.concat([new_prod.head(1), top_by_score.head(per_cat - 1)]).drop_duplicates("skuid")
            else:
                pick = top_by_score.head(per_cat)
            final_list.append(pick)

    final_df = pd.concat(final_list, ignore_index=True) if final_list else pd.DataFrame()
    
    print("Final df columns : ",final_df.columns)
    
    print("Final df : ",final_df)
    
    for col in final_df.select_dtypes(include=["datetime64[ns]"]).columns:
        final_df[col] = final_df[col].astype(str)

    # Save to DB and push to ES
    # values = final_df['l3'].tolist()
    
    # es_df = final_df[[
    #         "skuid", "l1", "l2", "l3", "title", "brand", "pmr_price",
    #         "pmr_discount", "is_new", "name", "discount_enddate",
    #         "avg_rating", "relaxed_review", "score"
    #     ]].copy()
    
    es_df = final_df[[
           'skuid', 'title', 'l1', 'l2', 'l3', 'brand', 'status', 'availability',
       'is_new', 'name', 'price', 'pmr_price', 'pmr_discount',
       'discount_enddate', 'total_quantity', 'addtocart', 'views',
       'review_count', 'avg_rating', 'relaxed_review', 'normalized_views',
       'normalized_addtocart', 'normalized_rating', 'normalized_reviews',
       'score'
        ]].copy()
    
    
    docs = es_df.to_dict(orient="records")
 
    push_to_es(
        INDEX_PREFIX=f"{client}_deal_of_day",
        ALIAS_NAME=f"{client}_deal_of_day",
        docs=docs
    )    
    
    # return final_df.to_dict(orient="records")
    return docs