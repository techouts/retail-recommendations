from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

from .client import client

logger = logging.getLogger(__name__)


def _get_filterable_attributes(docs: list[dict]) -> list[str]:
    """
    Dynamically detect all category_lN keys from the documents,
    so the filterable attribute list works regardless of depth (L3, L4, ...).
    Also includes fixed fields like brand, is_trending, etc.
    """
    fixed = ["brand", "is_trending", "is_threshold_relaxed", "selling_price"]
 
    if not docs:
        return fixed
 
    # Collect all category_lN keys that appear in any document
    category_keys = sorted(
        {k for doc in docs for k in doc if k.startswith("category_l") and k[len("category_l"):].isdigit()},
        key=lambda k: int(k[len("category_l"):]),
    )
 
    return category_keys + fixed
 


def _clean_doc(doc: dict) -> dict:
    """
    Normalise a single document:
      - Rename skuid → sku (Meili primary key convention)
      - Convert numpy scalar types to Python natives
      - Replace NaN/None safely
    """
    clean: dict = {}
    for k, v in doc.items():
        key = "sku" if k == "skuid" else k

        if isinstance(v, float) and (pd.isna(v) or v != v):  # NaN check
            clean[key] = None
        elif isinstance(v, (np.float32, np.float64)):
            clean[key] = float(v)
        elif isinstance(v, (np.int32, np.int64)):
            clean[key] = int(v)
        elif isinstance(v, np.bool_):
            clean[key] = bool(v)
        else:
            clean[key] = v

    return clean


def push_to_meili(
    docs: list[dict],
    index_name: str,
    primary_key: Optional[str] = "sku",
) -> None:
    """
    Push documents to Meilisearch using an atomic index-swap pattern:

      1. Push to a staging index  ({index_name}_staging)
      2. Swap staging ↔ live atomically
      3. Delete the old (now-staging) index

    This guarantees the live index is never in a partial/dirty state.
    Falls back to direct push if the swap API is unavailable.
    """
    if not docs:
        logger.warning("push_to_meili called with empty docs for index '%s' — skipping.", index_name)
        return

    clean_docs = [_clean_doc(d) for d in docs]
    filterable = _get_filterable_attributes(docs)
    logger.info(
        "Pushing %d docs to '%s' | filterable attrs: %s",
        len(clean_docs), index_name, filterable,
    )

    staging_name = f"{index_name}_staging"

    # ── Ensure staging index exists ──
    if client.indices.exists(index=staging_name):
        client.delete_index(staging_name)
        logger.debug("Deleted pre-existing staging index '%s'", staging_name)
    else:
        logger.debug("Staging index '%s' does not exist, nothing to delete", staging_name)

    client.create_index(staging_name, {"primaryKey": primary_key})
    staging_index = client.index(staging_name)

    # ── Set filterable attributes ──
    task = staging_index.update_filterable_attributes(filterable)
    client.wait_for_task(task.task_uid)
    logger.debug("Filterable attributes set: %s", filterable)

    # ── Push documents ──
    task = staging_index.add_documents(clean_docs)
    logger.info("Indexing task submitted — task_uid=%s", task.task_uid)
    result = client.wait_for_task(task.task_uid)

    if result.status != "succeeded":
        raise RuntimeError(
            f"Meilisearch indexing failed for '{staging_name}': {result.error}"
        )
    logger.info("Indexed %d documents into staging '%s'", len(clean_docs), staging_name)

    # ── Atomic swap: staging ↔ live ──
    try:
        swap_task = client.swap_indexes([{"indexes": [index_name, staging_name]}])
        client.wait_for_task(swap_task.task_uid)
        logger.info("Atomically swapped '%s' ↔ '%s'", staging_name, index_name)

        # Clean up old (now-staging) index
        client.delete_index(staging_name)
        logger.debug("Cleaned up old staging index '%s'", staging_name)

    except Exception as swap_err:
        # Meilisearch cloud / older versions may not support swap — fall back
        logger.warning(
            "Index swap not available (%s) — falling back to direct push into '%s'.",
            swap_err, index_name,
        )
        try:
            client.get_index(index_name)
        except Exception:
            client.create_index(index_name, {"primaryKey": primary_key})

        live_index = client.index(index_name)
        task = live_index.update_filterable_attributes(filterable)
        client.wait_for_task(task.task_uid)

        task = live_index.add_documents(clean_docs)
        result = client.wait_for_task(task.task_uid)
        if result.status != "succeeded":
            raise RuntimeError(
                f"Fallback push failed for '{index_name}': {result.error}"
            ) from swap_err

    stats = client.index(index_name).get_stats()
    logger.info("Final index stats for '%s': %s", index_name, stats)


def push_to_meili_fbt(
    docs: list[dict],
    index_name: str,
    primary_key: str = "skuid_A",
) -> None:
    """
    Push Frequently Bought Together documents.
    Uses direct delete-recreate (FBT index is always fully rebuilt).
    """
    if not docs:
        logger.warning("push_to_meili_fbt called with empty docs — skipping.")
        return

    try:
        client.delete_index(index_name)
        logger.debug("Deleted existing FBT index '%s'", index_name)
    except Exception:
        pass

    client.create_index(index_name, {"primaryKey": primary_key})
    index = client.index(index_name)

    # Detect filterable keys dynamically from FBT docs too
    fbt_fixed = ["skuid_A", "brand_A", "is_trending"]
    fbt_cat_keys = sorted(
        {k for doc in docs for k in doc if k.startswith("l") and k[1:].isdigit() and len(k) == 2},
        key=lambda k: int(k[1:]),
    )
    filterable = fbt_cat_keys + fbt_fixed

    task = index.update_filterable_attributes(filterable)
    client.wait_for_task(task.task_uid)

    task = index.add_documents(docs)
    logger.info("FBT indexing task submitted — task_uid=%s", task.task_uid)
    result = client.wait_for_task(task.task_uid)

    if result.status != "succeeded":
        raise RuntimeError(f"FBT indexing failed for '{index_name}': {result.error}")

    logger.info("FBT index '%s' ready. Stats: %s", index_name, index.get_stats())