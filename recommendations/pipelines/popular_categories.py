import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from types import SimpleNamespace
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from ..utils.pipeline_utils import load_csv_from_s3, normalize
from ..adapters.meili.indexer import push_to_meili
from ..adapters.meili.client import client as meili_client
from ..adapters.es.indexer import push_to_es

router = APIRouter()


# ===========================================================================
# UTILS
# ===========================================================================

def round_2(val):
    if val is None:
        return None
    return float(Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


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


# ===========================================================================
# PIPELINE
# ===========================================================================

def run_popular_categories_pipeline(PopularCategoryWeights: dict, client: str):

    weights = SimpleNamespace(**PopularCategoryWeights)

    score_w = getattr(weights, "score_weight", 0.5)
    avg_w   = getattr(weights, "avg_weight",   0.2)
    sku_w   = getattr(weights, "sku_weight",   0.1)
    sales_w = getattr(weights, "sales_weight", 0.15)
    views_w = getattr(weights, "views_weight", 0.05)

    top_k   = getattr(weights, "top_k_per_l2",     5)
    min_sku = getattr(weights, "min_sku_threshold", 2)

    s3_path = os.getenv("S3_PATH", "s3://retail-search")

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------
    catalog_df     = load_csv_from_s3(s3_path, client, "catalog")
    analytics_df   = load_csv_from_s3(s3_path, client, "analytics")
    fulfillment_df = load_csv_from_s3(s3_path, client, "fulfillment")
    inventory_df   = load_csv_from_s3(s3_path, client, "inventory")
  
  
    for df in [catalog_df, analytics_df, fulfillment_df, inventory_df]:
      
        df.columns = df.columns.str.strip().str.lower()
        if "sku_id" in df.columns:
            df.rename(columns={"sku_id": "skuid"}, inplace=True)
        elif "sku" in df.columns:
            df.rename(columns={"sku": "skuid"}, inplace=True)

        if "timestamp" in df.columns:
            df.rename(columns={"timestamp": "created_at"}, inplace=True)
        elif "date" in df.columns:
            df.rename(columns={"date": "created_at"}, inplace=True)
        elif "createdat" in df.columns:
            df.rename(columns={"createdat": "created_at"}, inplace=True)

        
        if "created_at" in df.columns:
            df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")

    for df in [catalog_df, analytics_df, fulfillment_df, inventory_df]:
        if "created_at" in df.columns:
            df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce", format="mixed")

    now      = datetime.now()
    time_24h = now - timedelta(hours=24)
    time_3d  = now - timedelta(days=3)
    time_7d  = now - timedelta(days=7)

    # ------------------------------------------------------------------
    # Stock filter
    # ------------------------------------------------------------------
    stock_totals      = inventory_df.groupby("skuid", as_index=False)["stock_quantity"].sum()
    eligible_products = stock_totals.loc[stock_totals["stock_quantity"] > 2, "skuid"]

    analytics_df   = analytics_df[analytics_df["skuid"].isin(eligible_products)]
    fulfillment_df = fulfillment_df[fulfillment_df["skuid"].isin(eligible_products)]

    if "status" in fulfillment_df.columns:
        fulfillment_df = fulfillment_df[
            fulfillment_df["status"].astype(str).str.lower() != "cancelled"
        ]

    # ------------------------------------------------------------------
    # Aggregate signals
    # ------------------------------------------------------------------
    sales_agg = aggregate_signals(fulfillment_df, "quantity",        time_24h, time_3d, time_7d)
    views_agg = aggregate_signals(analytics_df,   "view_count",      time_24h, time_3d, time_7d)
    cart_agg  = aggregate_signals(analytics_df,   "addtocart_count", time_24h, time_3d, time_7d)
    wish_agg  = aggregate_signals(analytics_df,   "wishlist_count",  time_24h, time_3d, time_7d)

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
    # Weighted signals (time decay: 24h=0.5, 3d=0.3, 7d=0.2)
    # ------------------------------------------------------------------
    for m in ["sales", "views", "cart", "wish"]:
        merged[f"weighted_{m}"] = (
            merged[f"24h_{m}"] * 0.5 +
            merged[f"3d_{m}"]  * 0.3 +
            merged[f"7d_{m}"]  * 0.2
        )

    # ------------------------------------------------------------------
    # skuid score
    # ------------------------------------------------------------------
    merged["sku_score"] = (
        normalize(merged["weighted_sales"]) * 0.5 +
        normalize(merged["weighted_views"]) * 0.2 +
        normalize(merged["weighted_cart"])  * 0.2 +
        normalize(merged["weighted_wish"])  * 0.1
    ) * 100

    # ------------------------------------------------------------------
    # Join catalog
    # ------------------------------------------------------------------
    df = catalog_df.merge(merged, on="skuid", how="inner")

    # ------------------------------------------------------------------
    # Category aggregation
    # ------------------------------------------------------------------
    category_df = df.groupby(
        ["category_l1", "category_l2", "category_l3"]
    ).agg(
        total_score =("sku_score",      "sum"),
        avg_score   =("sku_score",      "mean"),
        sku_count   =("skuid",          "nunique"),
        total_sales =("weighted_sales", "sum"),
        total_views =("weighted_views", "sum"),
    ).reset_index()

    category_df = category_df[category_df["sku_count"] >= min_sku]

    if category_df.empty:
        print("[WARN] No categories passed min_sku filter.")
        return []

    # ------------------------------------------------------------------
    # Category score
    # ------------------------------------------------------------------
    category_df["category_score"] = (
        normalize(category_df["total_score"]) * score_w +
        normalize(category_df["avg_score"])   * avg_w   +
        normalize(category_df["sku_count"])   * sku_w   +
        normalize(category_df["total_sales"]) * sales_w +
        normalize(category_df["total_views"]) * views_w
    ) * 100

    category_df = category_df.sort_values("category_score", ascending=False)

    # ------------------------------------------------------------------
    # Top-K per L2
    # ------------------------------------------------------------------
    final_categories = (
        category_df
        .groupby("category_l2", group_keys=False)
        .head(top_k)
        .reset_index(drop=True)
    )

    # ------------------------------------------------------------------
    # Clean + Round
    # ------------------------------------------------------------------
    final_categories = final_categories.replace([np.inf, -np.inf], None)
    final_categories = final_categories.where(final_categories.notna(), None)

    for col in ["total_score", "avg_score", "total_sales", "total_views", "category_score"]:
        if col in final_categories.columns:
            final_categories[col] = final_categories[col].apply(round_2)

    # ------------------------------------------------------------------
    # Unique ID -- sanitized for MeiliSearch
    # Only alphanumeric, hyphens, underscores allowed. Max 511 bytes.
    # ------------------------------------------------------------------
    def sanitize_id(val: str) -> str:
        import re as _re
        val = val.strip().replace(" ", "_")
        val = _re.sub(r"[^a-zA-Z0-9_-]", "", val)
        return val[:511]

    final_categories["id"] = (
        final_categories["category_l1"].astype(str).apply(sanitize_id) + "_" +
        final_categories["category_l2"].astype(str).apply(sanitize_id) + "_" +
        final_categories["category_l3"].astype(str).apply(sanitize_id)
    )

    # ------------------------------------------------------------------
    # Push to Meili
    # ------------------------------------------------------------------
    docs = final_categories[[
        "id", "category_l1", "category_l2", "category_l3",
        "category_score", "sku_count", "total_sales", "total_views","total_score"
    ]].to_dict(orient="records")

    print(f"[INFO] Pushing {len(docs)} popular category docs...")

  
    push_to_es(
        INDEX_PREFIX=f"{client}_popular_categories",
        ALIAS_NAME=f"{client}_popular_categories",
        docs=docs
    )   
    

    return final_categories.to_dict(orient="records")


# ===========================================================================
# MEILI INDEX CONFIGURATION
# ===========================================================================

def configure_popular_categories_index(tenant_id: str):
    """
    Sets MeiliSearch ranking + searchable + filterable attributes.
    Called automatically after every train. Safe to call multiple times.

    Ranking:
      1. words     — text match quality
      2. typo      — fewer typos rank higher
      3. attribute — l2 match > l3 match > l1 match
      4. sort      — then by category_score desc
      5. exactness — exact beats partial
    """
    index = meili_client.index(f"{tenant_id}_popular_categories")

    index.update_searchable_attributes(["category_l2", "category_l3", "category_l1"])

    index.update_ranking_rules(["words", "typo", "attribute", "sort", "exactness"])

    index.update_sortable_attributes(["category_score", "sku_count"])

    index.update_filterable_attributes(["category_l1", "category_l2", "category_l3"])

    print(f"[INFO] Index '{tenant_id}_popular_categories' configured.")


# ===========================================================================
# SERVICE
# ===========================================================================

class PopularCategoryService:

    def _get_index(self, tenant_id: str):
        return meili_client.index(f"{tenant_id}_popular_categories")

    def train_popular_category(self, settings: dict, tenant_id: str):
        result = run_popular_categories_pipeline(
            PopularCategoryWeights=settings,
            client=tenant_id,
        )
        try:
            configure_popular_categories_index(tenant_id)
        except Exception as e:
            print(f"[WARN] Index configuration failed: {e}")

        return {"success": True, "count": len(result), "data": result}

    def search_popular_categories(
        self,
        tenant_id: str,
        query: str,
        limit: int = 5,
        l1_filter: str = None,
    ) -> list:
        index = self._get_index(tenant_id)

        search_params = {
            "limit": limit,
            "sort":  ["category_score:desc"],
            "attributesToRetrieve": [
                "id", "category_l1", "category_l2", "category_l3",
                "category_score", "sku_count", "total_sales", "total_views",
            ],
            "attributesToHighlight": ["category_l2", "category_l3"],
            "highlightPreTag":  "<mark>",
            "highlightPostTag": "</mark>",
        }

        if l1_filter:
            search_params["filter"] = f'category_l1 = "{l1_filter}"'

        raw = index.search(query, search_params)
        return self._format_hits(raw.get("hits", []))

    def get_top_popular(
        self,
        tenant_id: str,
        limit: int = 5,
        l1_filter: str = None,
    ) -> list:
        index = self._get_index(tenant_id)

        search_params = {
            "limit": limit,
            "sort":  ["category_score:desc"],
            "attributesToRetrieve": [
                "id", "category_l1", "category_l2", "category_l3",
                "category_score", "sku_count", "total_sales", "total_views",
            ],
        }

        if l1_filter:
            search_params["filter"] = f'category_l1 = "{l1_filter}"'

        raw = index.search("", search_params)
        return self._format_hits(raw.get("hits", []))

    def _format_hits(self, hits: list) -> list:
        results = []
        for hit in hits:
            results.append({
                "id":             hit.get("id"),
                "label":          self._build_label(hit),
                "category_l1":    hit.get("category_l1"),
                "category_l2":    hit.get("category_l2"),
                "category_l3":    hit.get("category_l3"),
                "category_score": hit.get("category_score"),
                "sku_count":      hit.get("sku_count"),
                "total_sales":    hit.get("total_sales"),
                "total_views":    hit.get("total_views"),
                "_highlight":     hit.get("_formatted", {}),
            })
        return results

    def _build_label(self, hit: dict) -> str:
        l2 = hit.get("category_l2", "")
        l3 = hit.get("category_l3", "")
        if l3 and l3.lower() != l2.lower():
            return f"{l2} > {l3}"
        return l2


# ===========================================================================
# PYDANTIC SCHEMAS
# ===========================================================================

class TrainRecommendationsRequest(BaseModel):
    Client:   str
    settings: dict


# ===========================================================================
# ROUTES
# ===========================================================================

category_service = PopularCategoryService()

