from __future__ import annotations
import logging
import math
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field
from types import SimpleNamespace
from ..schemas.pipeline_schema import TrendingWeightsModel
from ..utils.pipeline_utils import load_csv, normalize
# from ..adapters.meili.indexer import push_to_meili
from ..adapters.es.indexer import push_to_es


logger = logging.getLogger(__name__)






def deep_clean(obj: Any) -> Any:
    """
    Recursively clean an object for JSON serialisation.
    Handles dicts, lists, numpy scalars, pandas NaT/NaN, and Python floats.
    Safe: only calls pd.isna on scalar types to avoid ambiguous truth-value errors.
    """
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

    # Only call pd.isna on safe scalar types — avoids ValueError on arrays
    if isinstance(obj, (type(pd.NaT), type(None))):
        return None
    try:
        if pd.isna(obj):
            return None
    except (TypeError, ValueError):
        pass  # array-like or un-checkable — leave as-is

    return obj


# ─────────────────────────────────────────────
# 3. Data loading and normalisation
# ─────────────────────────────────────────────

_COLUMN_ALIASES = {
    "sku_id":    "skuid",
    "timestamp": "created_at",
    "date":      "created_at",
    "createdat": "created_at",
}

_DATETIME_COLS = {"created_at"}


def _normalise_df(df: pd.DataFrame) -> pd.DataFrame:
    """Strip, lowercase, and unify column names."""
    df.columns = df.columns.str.strip().str.lower()
    df = df.rename(columns={k: v for k, v in _COLUMN_ALIASES.items() if k in df.columns})
    for col in _DATETIME_COLS:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def load_and_normalise() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load all source CSVs and normalise column names/types."""
    catalog_df     = _normalise_df(load_csv("catalog.csv"))
    analytics_df   = _normalise_df(load_csv("analytics.csv"))
    fulfillment_df = _normalise_df(load_csv("fulfillment.csv"))
    inventory_df   = _normalise_df(load_csv("inventory.csv"))

    logger.info(
        "Loaded rows — catalog=%d analytics=%d fulfillment=%d inventory=%d",
        len(catalog_df), len(analytics_df), len(fulfillment_df), len(inventory_df),
    )
    return catalog_df, analytics_df, fulfillment_df, inventory_df


# ─────────────────────────────────────────────
# 4. Eligible product filtering
# ─────────────────────────────────────────────

def get_eligible_skuids(inventory_df: pd.DataFrame, min_stock: int = 2) -> pd.Series:
    """Return skuids with total stock > min_stock."""
    stock_totals = inventory_df.groupby("skuid", as_index=False)["stock_quantity"].sum()
    eligible = stock_totals.loc[stock_totals["stock_quantity"] > min_stock, "skuid"]
    logger.info("Eligible skuids (stock > %d): %d", min_stock, len(eligible))
    return eligible


# ─────────────────────────────────────────────
# 5. Signal aggregation
# ─────────────────────────────────────────────

def _aggregate_one_signal(
    df: pd.DataFrame,
    value_col: str,
    time_24h: datetime,
    time_3d: datetime,
    time_7d: datetime,
    metric_name: str,
) -> pd.DataFrame:
    """
    Aggregate a single signal (e.g. view_count) across three time windows.
    Returns a DataFrame with columns: skuid, 24h_{metric}, 3d_{metric}, 7d_{metric}
    """
    if value_col not in df.columns:
        logger.warning("Column '%s' not found — filling signal '%s' with zeros.", value_col, metric_name)
        skuids = df["skuid"].unique() if "skuid" in df.columns else pd.Series([], dtype=str)
        empty = pd.DataFrame({"skuid": skuids})
        for period in ("24h", "3d", "7d"):
            empty[f"{period}_{metric_name}"] = 0.0
        return empty

    agg_24h = df[df["created_at"] >= time_24h].groupby("skuid")[value_col].sum().rename(f"24h_{metric_name}")
    agg_3d  = df[df["created_at"] >= time_3d ].groupby("skuid")[value_col].sum().rename(f"3d_{metric_name}")
    agg_7d  = df[df["created_at"] >= time_7d ].groupby("skuid")[value_col].sum().rename(f"7d_{metric_name}")

    return pd.concat([agg_24h, agg_3d, agg_7d], axis=1).fillna(0).reset_index()


def compute_signals(
    analytics_df: pd.DataFrame,
    fulfillment_df: pd.DataFrame,
    eligible_skuids: pd.Series,
    now: datetime,
) -> pd.DataFrame:
    """
    Compute all four signals for eligible products.
    Returns a merged DataFrame with all 12 signal columns.
    """
    time_24h = now - timedelta(hours=24)
    time_3d  = now - timedelta(days=3)
    time_7d  = now - timedelta(days=7)

    analytics_eligible   = analytics_df[analytics_df["skuid"].isin(eligible_skuids)]
    fulfillment_eligible = fulfillment_df[fulfillment_df["skuid"].isin(eligible_skuids)]

    # Exclude cancelled orders
    if "status" in fulfillment_eligible.columns:
        fulfillment_eligible = fulfillment_eligible[
            fulfillment_eligible["status"].astype(str).str.lower() != "cancelled"
        ]

    sales_agg = _aggregate_one_signal(fulfillment_eligible, "quantity",        time_24h, time_3d, time_7d, "sales")
    views_agg = _aggregate_one_signal(analytics_eligible,  "view_count",       time_24h, time_3d, time_7d, "views")
    cart_agg  = _aggregate_one_signal(analytics_eligible,  "addtocart_count",  time_24h, time_3d, time_7d, "cart")
    wish_agg  = _aggregate_one_signal(analytics_eligible,  "wishlist_count",   time_24h, time_3d, time_7d, "wish")

    merged = (
        sales_agg
        .merge(views_agg, on="skuid", how="outer")
        .merge(cart_agg,  on="skuid", how="outer")
        .merge(wish_agg,  on="skuid", how="outer")
        .fillna(0)
    )
    logger.info("Signal merge produced %d rows", len(merged))
    return merged


# ─────────────────────────────────────────────
# 6. Scoring
# ─────────────────────────────────────────────

_SIGNAL_PERIODS = {
    "sales": ["24h", "3d", "7d"],
    "views": ["24h", "3d", "7d"],
    "cart":  ["24h", "3d", "7d"],
    "wish":  ["24h", "3d", "7d"],
}

def score_products(merged: pd.DataFrame, weights: TrendingWeightsModel) -> pd.DataFrame:
    """
    Apply time-decay internal weights then business weights to produce trending_score.
    """
    internal_weights = {
        "sales": {"24h": weights.internal_sales_24h, "3d": weights.internal_sales_3d, "7d": weights.internal_sales_7d},
        "views": {"24h": weights.internal_views_24h, "3d": weights.internal_views_3d, "7d": weights.internal_views_7d},
        "cart":  {"24h": weights.internal_cart_24h,  "3d": weights.internal_cart_3d,  "7d": weights.internal_cart_7d},
        "wish":  {"24h": weights.internal_wish_24h,  "3d": weights.internal_wish_3d,  "7d": weights.internal_wish_7d},
    }
    business_weights = {
        "sales": weights.business_sales_weight,
        "views": weights.business_views_weight,
        "cart":  weights.business_cart_weight,
        "wish":  weights.business_wish_weight,
    }

    df = merged.copy()

    # Step A: time-decay weighted sum per signal
    for metric, periods in internal_weights.items():
        df[f"weighted_{metric}"] = 0.0
        for period, w in periods.items():
            col = f"{period}_{metric}"
            # ✅ Fixed: safe column access — no DataFrame.get() misuse
            signal_vals = df[col] if col in df.columns else 0.0
            df[f"weighted_{metric}"] += w * signal_vals

    # Step B: normalise + apply business weights
    df["trending_score"] = 0.0
    for metric, bw in business_weights.items():
        df[f"norm_{metric}"] = normalize(df[f"weighted_{metric}"])
        df["trending_score"] += bw * df[f"norm_{metric}"]

    df["trending_score"]  *= 100
    df["is_trending"]      = df["trending_score"] >= weights.threshold_value
    df["is_threshold_relaxed"] = False

    logger.info(
        "Scoring complete — trending=%d / total=%d (threshold=%.1f)",
        df["is_trending"].sum(), len(df), weights.threshold_value,
    )
    return df


# ─────────────────────────────────────────────
# 7. Dynamic category capping
# ─────────────────────────────────────────────

def _detect_category_levels(df: pd.DataFrame) -> list[str]:
    """
    Detect all category_lN columns that exist in the DataFrame.
    Returns them sorted: ['category_l1', 'category_l2', 'category_l3', 'category_l4', ...]
    Handles any depth — L2, L3, L4, or beyond.
    """
    levels = sorted(
        [c for c in df.columns if c.startswith("category_l") and c[len("category_l"):].isdigit()],
        key=lambda c: int(c[len("category_l"):])
    )
    logger.info("Detected category levels: %s", levels)
    return levels


def apply_caps_and_fill(
    catalog_with_metrics: pd.DataFrame,
    weights: TrendingWeightsModel,
) -> pd.DataFrame:
    """
    Dynamic category capping:

    1. Detect all category levels (L1→LN) from the catalog columns.
    2. Cap trending products at `max_per_leaf_category` per *leaf* level (deepest LN).
    3. For each L2 group, ensure at least `min_per_l2_category` products by
       pulling in sub-threshold candidates (respecting the leaf cap).

    Works correctly whether the data has L3, L4, or any depth.
    """
    cat_levels = _detect_category_levels(catalog_with_metrics)

    if len(cat_levels) < 2:
        logger.warning("Fewer than 2 category levels found — skipping cap logic.")
        return catalog_with_metrics[catalog_with_metrics["is_trending"]].copy()

    leaf_col = cat_levels[-1]   # deepest level, e.g. category_l4 or category_l3
    l2_col   = cat_levels[1]    # always category_l2 (index 1)

    max_per_leaf = weights.max_per_leaf_category
    min_per_l2   = weights.min_per_l2_category
    threshold    = weights.threshold_value
    min_relaxed  = weights.min_threshold_relaxed

    # ── Step A: cap trending products per leaf category ──
    trending_only = catalog_with_metrics[catalog_with_metrics["is_trending"]].copy()

    capped = (
        trending_only
        .sort_values(by=[leaf_col, "trending_score"], ascending=[True, False])
        .groupby(leaf_col, sort=False)
        .head(max_per_leaf)
        .reset_index(drop=True)
    )

    # Track counts per leaf so the fill pass can respect the same cap
    leaf_counts: dict[str, int] = capped[leaf_col].value_counts().to_dict()

    logger.info(
        "After leaf cap (%s ≤ %d): %d trending products across %d leaf categories",
        leaf_col, max_per_leaf, len(capped), len(leaf_counts),
    )

    # ── Step B: fill L2 groups to minimum ──
    final_blocks: list[pd.DataFrame] = []

    for l2_val in catalog_with_metrics[l2_col].dropna().unique():
        selected     = capped[capped[l2_col] == l2_val].copy()
        selected_ids = set(selected["skuid"].astype(str))
        deficit      = max(0, min_per_l2 - len(selected))

        if deficit > 0:
            candidates = (
                catalog_with_metrics[
                    (catalog_with_metrics[l2_col] == l2_val) &
                    (catalog_with_metrics["trending_score"] >= min_relaxed) &
                    (catalog_with_metrics["trending_score"] <  threshold) &
                    (~catalog_with_metrics["skuid"].astype(str).isin(selected_ids)) &
                    (~catalog_with_metrics["is_trending"])
                ]
                .sort_values("trending_score", ascending=False)
            )

            picks: list[pd.Series] = []
            for _, cand in candidates.iterrows():
                if deficit <= 0:
                    break
                cand_leaf = cand.get(leaf_col)
                if pd.isna(cand_leaf):
                    continue
                if leaf_counts.get(cand_leaf, 0) >= max_per_leaf:
                    continue

                row = cand.copy()
                row["is_threshold_relaxed"] = True
                row["is_trending"]          = False
                picks.append(row)

                leaf_counts[cand_leaf] = leaf_counts.get(cand_leaf, 0) + 1
                deficit -= 1

            if picks:
                selected = pd.concat([selected, pd.DataFrame(picks)], ignore_index=True)

        logger.debug("L2=%s final count=%d", l2_val, len(selected))
        final_blocks.append(selected)

    if not final_blocks:
        logger.warning("No blocks after fill pass — returning empty DataFrame.")
        return pd.DataFrame(columns=catalog_with_metrics.columns)

    result = (
        pd.concat(final_blocks, ignore_index=True)
        .drop_duplicates(subset=["skuid"])
        .sort_values("trending_score", ascending=False)
        .reset_index(drop=True)
    )
    logger.info("Final selection: %d products", len(result))
    return result


# ─────────────────────────────────────────────
# 8. Meili payload preparation
# ─────────────────────────────────────────────

_MEILI_BASE_COLS = [
    "skuid", "display_title", "brand", "selling_price",
    "trending_score", "is_trending", "is_threshold_relaxed", "image_urls",
]

def build_meili_docs(
    final_df: pd.DataFrame,
    cat_levels: list[str],
) -> list[dict]:
    """
    Select columns for Meilisearch, including all detected category levels dynamically.
    Applies deep_clean and returns a list of plain dicts.
    """
    # include whichever base cols actually exist
    cols = [c for c in _MEILI_BASE_COLS if c in final_df.columns]
    # add all detected category level columns
    cols += [c for c in cat_levels if c in final_df.columns]

    subset = final_df[cols].copy()

    # Replace inf/NaN at the DataFrame level before dict conversion
    subset = subset.replace([np.inf, -np.inf], np.nan)
    subset = subset.where(subset.notna(), None)

    docs = deep_clean(subset.to_dict(orient="records"))
    logger.info("Built %d Meilisearch documents", len(docs))
    return docs


# ─────────────────────────────────────────────
# 9. Main pipeline entry point
# ─────────────────────────────────────────────

def run_trending_pipeline(trending_weights: dict, client: str) -> list[dict]:
    """
    Orchestrates the full trending pipeline:

      1. Validate weights
      2. Load & normalise source data
      3. Filter eligible products
      4. Compute signals (sales, views, cart, wish) across 24h / 3d / 7d
      5. Score products
      6. Merge scores with catalog
      7. Apply dynamic category caps + L2 fill
      8. Build and push Meilisearch documents

    Returns the list of pushed documents (or [] on empty result).
    """
    # ── 1. Validate weights ──
    weights = TrendingWeightsModel(**trending_weights)
    logger.info("Pipeline started for client='%s' threshold=%.1f", client, weights.threshold_value)

    # ── 2. Load ──
    catalog_df, analytics_df, fulfillment_df, inventory_df = load_and_normalise()

    # ── 3. Eligible products ──
    eligible_skuids = get_eligible_skuids(inventory_df)
    if eligible_skuids.empty:
        logger.warning("No eligible products found — aborting pipeline.")
        return []

    # ── 4. Signals ──
    now    = datetime.now()
    merged = compute_signals(analytics_df, fulfillment_df, eligible_skuids, now)

    # ── 5. Score ──
    scored = score_products(merged, weights)

    # ── 6. Merge with catalog ──
    catalog_with_metrics = catalog_df.merge(scored, on="skuid", how="inner")
    if catalog_with_metrics.empty:
        logger.warning("No products survived catalog merge — aborting pipeline.")
        return []

    # ── 7. Cap & fill (dynamic category depth) ──
    cat_levels   = _detect_category_levels(catalog_with_metrics)
    final_df     = apply_caps_and_fill(catalog_with_metrics, weights)

    if final_df.empty:
        logger.warning("No products after cap/fill — aborting pipeline.")
        return []

    # ── 8. Build Meili docs ──
    docs = build_meili_docs(final_df, cat_levels)
    if not docs:
        logger.error("build_meili_docs returned empty list — nothing to push.")
        return []

    push_to_es(
    INDEX_PREFIX=f"{client}_trending_products",
    ALIAS_NAME=f"{client}_trending_products",
    docs=docs
)
    logger.info("Pipeline complete — pushed %d documents for client='%s'", len(docs), client)

    return docs