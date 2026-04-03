import math
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from ..utils.pipeline_utils import load_csv, normalize
from ..adapters.meili.indexer import push_to_meili
from types import SimpleNamespace


# BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# CSV_DIR = os.path.join(BASE_DIR, "data", "processed")


def deep_clean(obj):
    # Handle dict
    if isinstance(obj, dict):
        return {k: deep_clean(v) for k, v in obj.items()}
    
    # Handle list
    elif isinstance(obj, list):
        return [deep_clean(v) for v in obj]
    
    # Handle numpy types
    elif isinstance(obj, (np.float32, np.float64, float)):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return float(obj)
    
    # Handle pandas NaT
    elif pd.isna(obj):
        return None
    
    return obj


def ensure_datetime(df: pd.DataFrame, col: str):
    if col in df.columns:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    return df

def aggregate_signals(df: pd.DataFrame, value_col: str,
                time_24h: datetime, time_3d: datetime, time_7d: datetime,) -> pd.DataFrame:
    df_24h = df[df['created_at'] >= time_24h]
    df_3d = df[df['created_at'] >= time_3d]
    df_7d = df[df['created_at'] >= time_7d]

    agg_24h = df_24h.groupby("skuid")[value_col].sum().rename("24h")
    agg_3d = df_3d.groupby("skuid")[value_col].sum().rename("3d")
    agg_7d = df_7d.groupby("skuid")[value_col].sum().rename("7d")

    return pd.concat([agg_24h, agg_3d, agg_7d], axis=1).fillna(0).reset_index()


def run_trending_pipeline(TrendingWeights: dict,client: str):
    # Load data
    catalog_df     = load_csv("catalog.csv")
    analytics_df   = load_csv("analytics.csv")
    fulfillment_df = load_csv("fullfillment.csv")
    inventory_df   = load_csv("inventory.csv")
    

    analytics_df = ensure_datetime(analytics_df, "created_at")
    fulfillment_df = ensure_datetime(fulfillment_df, "created_at")
    catalog_df=ensure_datetime(catalog_df,"created_at")
    analytics_df=ensure_datetime(analytics_df,"created_at")
    inventory_df=ensure_datetime(inventory_df,"created_at")
    print(analytics_df)
    now = datetime.now()
    time_24h = now - timedelta(hours=24)
    time_3d  = now - timedelta(days=3)
    time_7d  = now - timedelta(days=7)

    stock_totals = inventory_df.groupby('skuid', as_index=False)['stock_quantity'].sum()
    
    eligible_products = stock_totals.loc[stock_totals['stock_quantity'] > 2, 'skuid']
    

    analytics_filtered = analytics_df[analytics_df['skuid'].isin(eligible_products)]
    
    if 'status' in fulfillment_df.columns:
        status_series = fulfillment_df['status'].astype(str).str.lower()
        fulfillment_filtered = fulfillment_df[
            (fulfillment_df['skuid'].isin(eligible_products)) &
            (status_series != 'cancelled')
        ]
    else:
        fulfillment_filtered = fulfillment_df[fulfillment_df['skuid'].isin(eligible_products)]
    
    sales_agg = aggregate_signals(fulfillment_filtered, "quantity", time_24h, time_3d, time_7d)
    sales_agg.columns = ['skuid', '24h_sales', '3d_sales', '7d_sales']

    views_agg = aggregate_signals(analytics_filtered, "view_count", time_24h, time_3d, time_7d)
    views_agg.columns = ['skuid', '24h_views', '3d_views', '7d_views']

    cart_agg = aggregate_signals(analytics_filtered, "addtocart_count", time_24h, time_3d, time_7d)
    cart_agg.columns = ['skuid', '24h_cart', '3d_cart', '7d_cart']

    wish_agg = aggregate_signals(analytics_filtered, "wishlist_count", time_24h, time_3d, time_7d)
    wish_agg.columns = ['skuid', '24h_wish', '3d_wish', '7d_wish']

    merged = (
        sales_agg
        .merge(views_agg, on="skuid", how="left")
        .merge(cart_agg,  on="skuid", how="left")
        .merge(wish_agg,  on="skuid", how="left")
        .fillna(0)
    )
    
    weights = SimpleNamespace(**TrendingWeights)
    

    internal_weights = {
        "sales": {"24h": getattr(weights, "internal_sales_24h", 40), "3d": getattr(weights,"internal_sales_3d",30), "7d": getattr(weights,"internal_sales_7d",30)},
        "views": {"24h":getattr(weights,"internal_views_24h",40), "3d": getattr(weights,"internal_views_3d",40), "7d": getattr(weights,"internal_views_7d",20)},
        "cart":  {"24h": getattr(weights,"internal_cart_24h",40),  "3d": getattr(weights,"internal_cart_3d",30),  "7d":getattr(weights,"internal_cart_7d",30)},
        "wish":  {"24h": getattr(weights,"internal_wish_24h",40),  "3d": getattr(weights,"internal_wish_3d",30),  "7d": getattr(weights,"internal_wish_7d",30)},
    }

    business_weights = {
        "sales": weights.business_sales_weight or 0.5,
        "views": weights.business_views_weight or 0.1,
        "cart":  weights.business_cart_weight  or 0.3,
        "wish":  weights.business_wish_weight  or 0.1,
    }

    threshold_value = weights.threshold_value or 64

    # ---------------------------
    # Step 3: Compute weighted metrics
    # ---------------------------
    for metric in ["sales", "views", "cart", "wish"]:
        merged[f"weighted_{metric}"] = 0.0
        for period, w in internal_weights[metric].items():
            merged[f"weighted_{metric}"] += (w or 0.0) * merged.get(f"{period}_{metric}", 0.0)
    
    # ---------------------------
    # Step 4: Compute trending_score
    # ---------------------------
    merged["trending_score"] = 0.0
    for metric, bw in business_weights.items():
        merged[f"norm_{metric}"] = normalize(merged[f"weighted_{metric}"])
        merged[f"norm_with_{metric}"] = (bw or 0.0) * merged[f"norm_{metric}"]
        merged["trending_score"] += merged[f"norm_with_{metric}"]

    
    merged["trending_score"] *= 100
    merged["is_trending"] = merged["trending_score"] >= threshold_value
    print("merged ",merged["trending_score"])
    merged["is_threshold_relaxed"] = False

    catalog_with_metrics = catalog_df.merge(merged, on="skuid", how="inner")
    
    # ---------------------------
    # Step 5: Hard cap per L3 = 10 trending products
    # ---------------------------
    trending_only = catalog_with_metrics[catalog_with_metrics["is_trending"]].copy()
    capped_trending_l3 = (
        trending_only
        .sort_values(by=["category_l3", "trending_score"], ascending=[True, False])
        .groupby("category_l3", sort=False)
        .head(10)
        .reset_index(drop=True)
    )
    l3_counts = capped_trending_l3["category_l3"].value_counts().to_dict()



    # ---------------------------
    # Step 6: Ensure at least 10 per L2 (fallback from same-L2 only)
    # ---------------------------
    min_threshold_relaxed = weights.min_threshold_relaxed
    print(min_threshold_relaxed)
    final_l2_blocks = []
    for l2_val in catalog_with_metrics["category_l2"].dropna().unique():
        selected = capped_trending_l3[capped_trending_l3["category_l2"] == l2_val].copy()
        selected_ids = set(selected["skuid"].astype(str).tolist())
        curr_count = len(selected)

        if curr_count < 10:
            deficit = 10 - curr_count
            candidates = (
                catalog_with_metrics[
                    
                    (catalog_with_metrics["category_l2"] == l2_val) &
                    (catalog_with_metrics["trending_score"] >= min_threshold_relaxed) &
                    (catalog_with_metrics["trending_score"] < threshold_value) &
                    (~catalog_with_metrics["skuid"].astype(str).isin(selected_ids)) &
                    (~catalog_with_metrics["is_trending"])
                ]
                .copy()
                .sort_values(by="trending_score", ascending=False)
            )

            picks = []
            for _, cand in candidates.iterrows():
                if deficit <= 0:
                    break
                cand_l3 = cand.get("category_l3")
                if pd.isna(cand_l3):
                    continue
                if l3_counts.get(cand_l3, 0) >= 10:  # enforce L3 cap
                    continue

                cand_copy = cand.copy()
                cand_copy["is_threshold_relaxed"] = True
                cand_copy["is_trending"] = False
                picks.append(cand_copy)

                l3_counts[cand_l3] = l3_counts.get(cand_l3, 0) + 1
                deficit -= 1

            selected = pd.concat([selected, pd.DataFrame(picks)], ignore_index=True)

        final_l2_blocks.append(selected)
    
    # ---------------------------
    # Step 7: Combine & save final selection
    # ---------------------------
    valid_blocks = [blk for blk in final_l2_blocks if not blk.empty]
    if not valid_blocks:
        print("⚠️ No data available after L2 processing. Returning empty result.")
        return []
    final_selected = (
        pd.concat([blk for blk in final_l2_blocks if not blk.empty], ignore_index=True)
        if final_l2_blocks else pd.DataFrame(columns=catalog_with_metrics.columns)
    )
    final_selected = final_selected.drop_duplicates(subset=["skuid"]) \
                               .sort_values(by="trending_score", ascending=False)

    if not final_selected.empty:

        #  Fix JSON issues
        final_selected = final_selected.replace([np.inf, -np.inf], None)
        final_selected = final_selected.where(final_selected.notna(), None)

        meili_df = final_selected[[
            "skuid", "category_l1", "category_l2", "category_l3",
            "display_title", "brand", "selling_price",
            "trending_score", "is_trending", "is_threshold_relaxed","image_urls"
        ]].copy()
        records = final_selected.to_dict(orient="records")

        
        docs = meili_df.to_dict(orient="records")

        if not docs:
            print("⚠️ meili_df is empty. No docs to push.")
            return []

        docs = deep_clean(docs)

        if not docs:
            print("⚠️ After deep_clean, no valid docs remain.")
            # fallback: push top N by trending_score
            top_df = meili_df.sort_values(by="trending_score", ascending=False).head(50)
            docs = deep_clean(top_df.to_dict(orient="records"))

        push_to_meili(
            docs=docs,
            index_name=f"{client}_trending_products"
        )

        return docs

    return []   