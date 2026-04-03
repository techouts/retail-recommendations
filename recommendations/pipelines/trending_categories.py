import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from ..utils.pipeline_utils import load_csv, normalize
from ..adapters.meili.indexer import push_to_meili
from types import SimpleNamespace


def ensure_datetime(df: pd.DataFrame, col: str):
    if col in df.columns:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def aggregate_signals(
    df: pd.DataFrame,
    value_col: str,
    time_24h: datetime,
    time_3d: datetime,
    time_7d: datetime,
) -> pd.DataFrame:
    df_24h = df[df["created_at"] >= time_24h]
    df_3d  = df[df["created_at"] >= time_3d]
    df_7d  = df[df["created_at"] >= time_7d]

    agg_24h = df_24h.groupby("skuid")[value_col].sum().rename("24h")
    agg_3d  = df_3d.groupby("skuid")[value_col].sum().rename("3d")
    agg_7d  = df_7d.groupby("skuid")[value_col].sum().rename("7d")

    return pd.concat([agg_24h, agg_3d, agg_7d], axis=1).fillna(0).reset_index()


def run_category_trending_pipeline(TrendingWeights: dict, client: str):

    # ------------------------------------------------------------------
    # Step 1: Load data
    # ------------------------------------------------------------------
    catalog_df     = load_csv("catalog.csv")
    analytics_df   = load_csv("analytics.csv")
    fulfillment_df = load_csv("fullfillment.csv")
    inventory_df   = load_csv("inventory.csv")

    for df, col in [
        (analytics_df,   "created_at"),
        (fulfillment_df, "created_at"),
        (catalog_df,     "created_at"),
        (inventory_df,   "created_at"),
    ]:
        ensure_datetime(df, col)

    now      = datetime.now()
    time_24h = now - timedelta(hours=24)
    time_3d  = now - timedelta(days=3)
    time_7d  = now - timedelta(days=7)

    # ------------------------------------------------------------------
    # Step 2: Stock eligibility filter
    # ------------------------------------------------------------------
    stock_totals    = inventory_df.groupby("skuid", as_index=False)["stock_quantity"].sum()
    eligible_skuids = stock_totals.loc[stock_totals["stock_quantity"] > 2, "skuid"]

    analytics_filtered = analytics_df[analytics_df["skuid"].isin(eligible_skuids)]

    if "status" in fulfillment_df.columns:
        fulfillment_filtered = fulfillment_df[
            fulfillment_df["skuid"].isin(eligible_skuids) &
            (fulfillment_df["status"].astype(str).str.lower() != "cancelled")
        ]
    else:
        fulfillment_filtered = fulfillment_df[fulfillment_df["skuid"].isin(eligible_skuids)]

    # ------------------------------------------------------------------
    # Step 3: Aggregate signals
    # ------------------------------------------------------------------
    sales_agg = aggregate_signals(fulfillment_filtered, "quantity",        time_24h, time_3d, time_7d)
    views_agg = aggregate_signals(analytics_filtered,   "view_count",      time_24h, time_3d, time_7d)
    cart_agg  = aggregate_signals(analytics_filtered,   "addtocart_count", time_24h, time_3d, time_7d)
    wish_agg  = aggregate_signals(analytics_filtered,   "wishlist_count",  time_24h, time_3d, time_7d)

    sales_agg.columns = ["skuid", "24h_sales", "3d_sales", "7d_sales"]
    views_agg.columns = ["skuid", "24h_views", "3d_views", "7d_views"]
    cart_agg.columns  = ["skuid", "24h_cart",  "3d_cart",  "7d_cart"]
    wish_agg.columns  = ["skuid", "24h_wish",  "3d_wish",  "7d_wish"]

    merged = (
        sales_agg
        .merge(views_agg, on="skuid", how="left")
        .merge(cart_agg,  on="skuid", how="left")
        .merge(wish_agg,  on="skuid", how="left")
        .fillna(0)
    )

    # ------------------------------------------------------------------
    # Step 4: Weights
    # ------------------------------------------------------------------
    weights = SimpleNamespace(**TrendingWeights)

    internal_weights = {
        "sales": {"24h": getattr(weights, "internal_sales_24h", 40), "3d": getattr(weights, "internal_sales_3d", 30),  "7d": getattr(weights, "internal_sales_7d", 30)},
        "views": {"24h": getattr(weights, "internal_views_24h", 40), "3d": getattr(weights, "internal_views_3d", 40),  "7d": getattr(weights, "internal_views_7d", 20)},
        "cart":  {"24h": getattr(weights, "internal_cart_24h",  40), "3d": getattr(weights, "internal_cart_3d",  30),  "7d": getattr(weights, "internal_cart_7d",  30)},
        "wish":  {"24h": getattr(weights, "internal_wish_24h",  40), "3d": getattr(weights, "internal_wish_3d",  30),  "7d": getattr(weights, "internal_wish_7d",  30)},
    }

    business_weights = {
        "sales": weights.business_sales_weight or 0.5,
        "views": weights.business_views_weight or 0.1,
        "cart":  weights.business_cart_weight  or 0.3,
        "wish":  weights.business_wish_weight  or 0.1,
    }

    threshold_value       = weights.threshold_value       or 64
    min_threshold_relaxed = weights.min_threshold_relaxed or 30

    # ------------------------------------------------------------------
    # Step 5: Weighted metric per skuid
    # ------------------------------------------------------------------
    for metric in ["sales", "views", "cart", "wish"]:
        merged[f"weighted_{metric}"] = 0.0
        for period, w in internal_weights[metric].items():
            col = f"{period}_{metric}"
            merged[f"weighted_{metric}"] += (w or 0.0) * merged.get(col, pd.Series(0.0, index=merged.index))

    catalog_with_metrics = catalog_df.merge(merged, on="skuid", how="inner")

    # ------------------------------------------------------------------
    # Step 6: Per-category scoring (normalization scoped per L2)
    # ------------------------------------------------------------------
    all_category_results = []

    l2_values = catalog_with_metrics["category_l2"].dropna().unique()
    print(f"[INFO] Processing {len(l2_values)} category_l2 groups...")

    for l2_val in l2_values:
        cat_df = catalog_with_metrics[
            catalog_with_metrics["category_l2"] == l2_val
        ].copy().reset_index(drop=True)

        if cat_df.empty:
            print(f"[WARN] No products for category_l2='{l2_val}', skipping.")
            continue

        for metric in ["sales", "views", "cart", "wish"]:
            cat_df[f"norm_{metric}"] = normalize(cat_df[f"weighted_{metric}"])

        cat_df["trending_score"] = 0.0
        for metric, bw in business_weights.items():
            cat_df[f"norm_with_{metric}"] = (bw or 0.0) * cat_df[f"norm_{metric}"]
            cat_df["trending_score"]      += cat_df[f"norm_with_{metric}"]

        cat_df["trending_score"]       *= 100
        cat_df["is_trending"]           = cat_df["trending_score"] >= threshold_value
        cat_df["is_threshold_relaxed"]  = False

        print(f"[INFO] category_l2='{l2_val}' | total={len(cat_df)} | trending={cat_df['is_trending'].sum()}")

        # Step 7: Hard cap — top 10 per L3
        trending_only = cat_df[cat_df["is_trending"]].copy()
        capped_l3 = (
            trending_only
            .sort_values(by=["category_l3", "trending_score"], ascending=[True, False])
            .groupby("category_l3", sort=False)
            .head(10)
            .reset_index(drop=True)
        )
        l3_counts = capped_l3["category_l3"].value_counts().to_dict()

        # Step 8: Fallback — ensure at least 10 per L2
        selected     = capped_l3.copy()
        selected_ids = set(selected["skuid"].astype(str).tolist())
        curr_count   = len(selected)

        if curr_count < 10:
            deficit    = 10 - curr_count
            candidates = (
                cat_df[
                    (~cat_df["skuid"].astype(str).isin(selected_ids)) &
                    (cat_df["trending_score"] >= min_threshold_relaxed) &
                    (cat_df["trending_score"] < threshold_value) &
                    (~cat_df["is_trending"])
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
                if l3_counts.get(cand_l3, 0) >= 10:
                    continue

                cand_copy = cand.copy()
                cand_copy["is_threshold_relaxed"] = True
                cand_copy["is_trending"]           = False
                picks.append(cand_copy)

                l3_counts[cand_l3] = l3_counts.get(cand_l3, 0) + 1
                deficit -= 1

            if picks:
                selected = pd.concat([selected, pd.DataFrame(picks)], ignore_index=True)

        selected["category_l2_group"] = l2_val
        all_category_results.append(selected)

    # ------------------------------------------------------------------
    # Step 9: Combine ALL categories → push to ONE single index
    # ------------------------------------------------------------------
    if not all_category_results:
        print("[WARN] No category trending data produced. Returning empty.")
        return {}

    final_all = pd.concat(
        [blk for blk in all_category_results if not blk.empty],
        ignore_index=True
    )

    final_all = (
        final_all
        .drop_duplicates(subset=["skuid"])
        .sort_values(by=["category_l2", "trending_score"], ascending=[True, False])
        .reset_index(drop=True)
    )

    final_all = final_all.replace([np.inf, -np.inf], None)
    final_all = final_all.where(final_all.notna(), None)

    meili_cols = [
        "skuid", "category_l1", "category_l2", "category_l3",
        "display_title", "brand", "selling_price",
        "trending_score", "is_trending", "is_threshold_relaxed",
        "category_l2_group","image_urls"
    ]
    available_cols = [c for c in meili_cols if c in final_all.columns]
    docs = final_all[available_cols].to_dict(orient="records")

    # Single index, no primary key
    index_name = f"{client}_trending_category_products"
    push_to_meili(docs=docs, index_name=index_name)
    print(f"[INFO] Pushed {len(docs)} total docs → index '{index_name}'")

    # Summary per L2 for the response
    summary = {}
    for l2_val, grp in final_all.groupby("category_l2"):
        summary[l2_val] = {
            "total":    len(grp),
            "trending": int(grp["is_trending"].sum()),
            "relaxed":  int(grp["is_threshold_relaxed"].sum()),
        }
    summary["_index"]      = index_name
    summary["_total_docs"] = len(docs)

    return summary