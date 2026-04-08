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

catalog = pd.read_csv(os.path.join(CSV_DIR,"catalog.csv.csv"))
inventory = pd.read_csv(os.path.join(CSV_DIR,"inventory.csv.csv"))
analytics = pd.read_csv(os.path.join(CSV_DIR,"analytics.csv.csv"))
customer_rating = pd.read_csv(os.path.join(CSV_DIR,"customer_rating.csv"))
pmr = pd.read_csv(os.path.join(CSV_DIR,"pmr.csv.csv"))

catalog["created_at"] = pd.to_datetime(catalog["created_at"], errors="coerce")
pmr["discount_enddate"] = pd.to_datetime(pmr["discount_enddate"], errors="coerce")

def normalize(series):
    if series.max() == series.min():
        return pd.Series([0.5] * len(series), index=series.index)   
    return (series - series.min()) / (series.max() - series.min())

# def get_dod_settings():
#     return DealOfTheDaySetting.objects.filter(id=1).first()


def df_to_es_docs(df: pd.DataFrame) -> list[dict]:
    
    df = df.replace([np.nan, np.inf, -np.inf], None)
    return df.to_dict(orient="records")



from datetime import datetime as dt
def run_dod_pipeline(DealOfDayWeights : dict , client : str , levels : list):
        
    dod_weights = SimpleNamespace(**DealOfDayWeights)
    
    print("Dod weights : ",dod_weights)
    # review_threshold = dod_weights.min_reviews
    
    date_str = '2026-06-10'
    date_obj = dt.strptime(date_str, '%Y-%m-%d').date()

    # Filter PMR data
    pmrdf = pmr[
        # (pmr["discount_enddate"].dt.date >= dt.today().date()) &
        (pmr["discount_enddate"].dt.date >= date_obj) &
        (pmr["discount_price"].between(dod_weights.min_discount_threshold, dod_weights.max_discount_threshold))
    ].copy()
    # print("PMR head : ", pmr.head(10))
    print("Today date : ",dt.today().date())
    print("pmrdf: ",pmrdf.head(100))
    # print("Catalog head : ",catalog.head(10))
    # Filter catalog by L3 and PMR SKUs
    catalogdf = catalog[
        (catalog["category_l3"].isin(levels)) & (catalog["sku_id"].isin(pmrdf["sku_id"]))
    ].copy()
    catalogdf["is_new"] = (dt.today() - catalogdf["created_at"]).dt.days <= dod_weights.new_product_window_days

    print("catalog df : ",catalogdf.head(10))
    
    # Inventory filter
    inventorydf = inventory[inventory["sku_id"].isin(catalogdf["sku_id"])].copy()
    
    print("Inventory df 1 : ",inventorydf.head(10))
    
    inventorydf = inventorydf.groupby("sku_id").agg(total_quantity=("stock_quantity", "sum")).reset_index()
    
    print("Inventory df 2: ",inventorydf.head(10))
    
    inventorydf = inventorydf[inventorydf["total_quantity"] >= dod_weights.min_stock]
    
    print("Inventory df 3 : ",inventorydf.head(10))

    # Analytics aggregation
    analyticsdf = analytics[analytics["sku_id"].isin(inventorydf["sku_id"])].copy()
    
    print("Analytics 1 : ",analyticsdf.head(10))
    
    analyticsdf = analyticsdf.groupby("sku_id")[["addtocart_count", "view_count"]].sum().reset_index()
    
    print("Analytics 2 : ",analyticsdf.head(10))

    # Ratings aggregation
    ratingdf = customer_rating[customer_rating["sku_id"].isin(inventorydf["sku_id"])].copy()
    
    print("Ratings df : ",ratingdf.head(10))
    
    ratingdf = ratingdf.groupby("sku_id").agg(
        review_count=("sku_id", "count"),
        avg_rating=("rating", "mean")
    ).reset_index()
    
    # ratingdf = ratingdf[ratingdf["avg_rating"] >= dod_weights.rating_threshold]

    print("Ratings df : ",ratingdf.head(10))
    # Merge all data
    resultdf = (
        catalogdf.merge(pmrdf, on="sku_id", how="left")
                 .merge(inventorydf, on="sku_id", how="left")
                 .merge(analyticsdf, on="sku_id", how="left")
                 .merge(ratingdf, on="sku_id", how="left")
    )
    resultdf = resultdf.loc[:, ~resultdf.columns.str.endswith(('_x', '_y'))]
    
    resultdf["review_count"] = resultdf["review_count"].fillna(0)
    resultdf["avg_rating"] = resultdf["avg_rating"].fillna(0)

    
    print("Resultdf : ",resultdf.head(10))
    dod_weights.min_reviews = 1
    
    # Adaptive review filtering
    filtered = resultdf[resultdf["review_count"] >= dod_weights.min_reviews].copy()
    
    print("filtered df 1 : ",filtered.head(25))
    
    print("sum : ",filtered["category_l3"].isna().sum())
    
    count_after_filter = filtered.groupby("category_l3").agg(
        count=("sku_id", "count"),
        skuid=("sku_id", lambda x: list(x))
    ).reset_index()
    
    print("Filtered results 2 : ",count_after_filter)
    
    # Debug log: track relaxed review logic per L3
    final_df_list = []
    relaxed_review_log = []

    for k, v, skuid in count_after_filter.itertuples(index=False):
        if v > 0:
            temp_df = resultdf[(resultdf["category_l3"] == k) & (resultdf["sku_id"].isin(skuid))].copy()
            temp_df["relaxed_review"] = False
            relaxed_review_log.append({"l3": k, "relaxed_review": False, "qualified_skus": len(skuid)})
        else:
            temp_df = resultdf[resultdf["category_l3"]  == k].copy()
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
    
    print("Final df : ",final_df.head(10))

    # L3 capped selection
    final_list = []
    if not final_df.empty:
        total_to_show = min(len(final_df), 12)
        l3_groups = final_df["category_l3"].unique()
        per_cat = max(1, round(total_to_show / len(l3_groups)))

        for l3 in l3_groups:
            subset = final_df[final_df["category_l3"] == l3].copy()
            new_prod = subset[subset["is_new"]]
            top_by_score = subset.sort_values(by="score", ascending=False)
            if not new_prod.empty:
                pick = pd.concat([new_prod.head(1), top_by_score.head(per_cat - 1)]).drop_duplicates("sku_id")
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
    #         "sku", "l1", "l2", "l3", "title", "brand", "pmr_price",
    #         "pmr_discount", "is_new", "name", "discount_enddate",
    #         "avg_rating", "relaxed_review", "score"
    #     ]].copy()
    
    final_df = final_df.rename(columns={
        "sku_id": "sku",
        "product_name": "title",
        "category_l1": "l1",
        "category_l2": "l2",
        "category_l3": "l3",
        "discount_price": "pmr_discount",
        "addtocart_count": "addtocart",
        "view_count": "views",
        "stock_status": "availability"
        })
    
    es_df = final_df[[
           'sku', 'title', 'l1', 'l2', 'l3', 'brand',  'availability',
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
        print("✅ Final selection pushed to ES (L3 capped, L2 fallback applied).")
    else:
        print("⚠️ No final products to push to ES.")
    return {"data": docs}