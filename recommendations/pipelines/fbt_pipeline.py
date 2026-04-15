import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from ..utils.pipeline_utils import load_csv_from_s3, normalize
from ..adapters.meili.indexer import push_to_meili , push_to_meili_fbt
from types import SimpleNamespace
from itertools import combinations
from collections import Counter
from .utils import df_to_es_docs
from ..adapters.es.indexer import push_to_es

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_DIR = os.path.join(BASE_DIR)

def product_pairs(grouped_orders):
    pair_counts = Counter()
    for product_list in grouped_orders:
        unq_product = set(product_list)
        if len(unq_product) > 1:
            for A, B in combinations(sorted(unq_product), 2):
                pair_counts[(A, B)] += 1
    return pd.DataFrame(pair_counts.items(), columns=["Pair", "OrderCount"])

def calculate_support(ordersdf, pairdf):
    
    total_orderss= ordersdf["order_id"].nunique()
    pairdf["Support"] = pairdf["OrderCount"] / total_orderss
    return pairdf

def calculate_confidence(ordersdf, pairdf):
    order_count_per_product = ordersdf.groupby("sku_id")["order_id"].nunique().to_dict()
    confidences = []
    for pair, order_count in zip(pairdf["Pair"], pairdf["OrderCount"]):
        A, B = pair
        conf_A_to_B = order_count / order_count_per_product.get(A, 1)
        conf_B_to_A = order_count / order_count_per_product.get(B, 1)
        confidences.append((pair, conf_A_to_B, conf_B_to_A))
    return pd.DataFrame(confidences, columns=["Pair", "Confidence(A→B)", "Confidence(B→A)"])

def calculate_lift(ordersdf, conf_df):
    total_orderss= ordersdf["order_id"].nunique()
    product_support = ordersdf.groupby("sku_id")["order_id"].nunique() / total_orderss
    lifts_A_to_B, lifts_B_to_A = [], []
    for _, row in conf_df.iterrows():
        A, B = row["Pair"]
        lift_A_B = row["Confidence(A→B)"] / product_support.get(B, 1e-9)
        lift_B_A = row["Confidence(B→A)"] / product_support.get(A, 1e-9)
        lifts_A_to_B.append(lift_A_B)
        lifts_B_to_A.append(lift_B_A)
    conf_df = conf_df.copy()
    conf_df["Lift(A→B)"] = lifts_A_to_B
    conf_df["Lift(B→A)"] = lifts_B_to_A
    return conf_df

def calculate_score(row):
    return (
        0.4 * row["Support"] +
        0.3 * row["Confidence(A→B)"] +
        0.3 * row["Lift(A→B)"]
    )
    

def merge_fbt_with_catalog(finaldf, catalogdf, price_tolerance):
    if finaldf.empty or "Pair" not in finaldf.columns:
        print("No pairs to merge with catalog.")
        return pd.DataFrame()
    finaldf = finaldf[finaldf["Pair"].apply(lambda x: isinstance(x, tuple) and len(x) == 2)]
    if finaldf.empty:
        print("No valid pairs after tuple check.")
        return pd.DataFrame()
    finaldf["skuid_A"] = finaldf["Pair"].apply(lambda x: x[0])
    finaldf["skuid_B"] = finaldf["Pair"].apply(lambda x: x[1])
    catalog_A = catalogdf.add_suffix("_A")
    merged_df = finaldf.merge(
        catalog_A, left_on="skuid_A", right_on="sku_id_A", how="left"
    )
    catalog_B = catalogdf.add_suffix("_B")
    merged_df = merged_df.merge(
        catalog_B, left_on="skuid_B", right_on="sku_id_B", how="left"
    )
    print("Pairs after catalog merge:", len(merged_df))

    # Filter by same l1
    # merged_df = merged_df.dropna(subset=["l1_A", "l1_B"])
    # merged_df = merged_df[merged_df["l1_A"] == merged_df["l1_B"]]
    
    merged_df = merged_df.dropna(subset=["category_l1_A", "category_l1_B"])
    merged_df = merged_df[
    merged_df["category_l1_A"] == merged_df["category_l1_B"]
    ]
    
    
    print("Pairs after l1 filter:", len(merged_df))

    # Filter by price tolerance (+-30%)
    # merged_df = merged_df[
    #     (abs(merged_df["price_A"] - merged_df["price_B"]) <= merged_df["price_A"] * price_tolerance)
    # ]
    
    merged_df = merged_df[
    (
        abs(merged_df["selling_price_A"] - merged_df["selling_price_B"])
        <= merged_df["selling_price_A"] * price_tolerance
    )
    ]
    
    print("Pairs after price tolerance filter:", len(merged_df))

    columns = (
        [col for col in merged_df.columns if col.endswith("_A")]
        + [col for col in merged_df.columns if col.endswith("_B")]
        + [
            "OrderCount",
            "Support",
            "Confidence(A→B)",
            "Confidence(B→A)",
            "Lift(A→B)",
            "Lift(B→A)",
            "score"
        ]
    )
    return merged_df[columns]

def fbt_group_to_es_doc(group):
    first = group.iloc[0]
    doc = {
        "skuid_A": first["skuid_A"],
        "product_name_A": first.get("product_name_A"),
        "l1_A": first.get("l1_A"),
        "l2_A": first.get("l2_A"),
        "l3_A": first.get("l3_A"),
        "title_A": first.get("title_A"),
        "price_A": first.get("price_A"),
        "discount_A": first.get("discount_A"),
        "status_A": first.get("status_A"),
        "availability_A": first.get("availability_A"),
        "brand_A": first.get("brand_A"),
        "timestamp_A": first.get("timestamp_A"),
        "pairs": [],
    }
    for _, row in group.iterrows():
        doc["pairs"].append(
            {
                "skuid_B": row["skuid_B"],
                "product_name_B": row.get("product_name_B"),
                "l1_B": row.get("l1_B"),                                                                                    
                "l2_B": row.get("l2_B"),
                "l3_B": row.get("l3_B"),
                "title_B": row.get("title_B"),
                "price_B": row.get("price_B"),
                "discount_B": row.get("discount_B"),
                "status_B": row.get("status_B"),
                "availability_B": row.get("availability_B"),
                "brand_B": row.get("brand_B"),
                "timestamp_B": row.get("timestamp_B"),                
                "pair_count": row["OrderCount"],
                "support": row["Support"],
                "confidence_a_to_b": row["Confidence(A→B)"],
                "confidence_b_to_a": row["Confidence(B→A)"],
                "lift_a_to_b": row["Lift(A→B)"],
                "lift_b_to_a": row["Lift(B→A)"],
                # "score": row["score"]
            }
        )
    return doc

def run_fbt_pipeline(fbt_weights : dict , client : str):
     
    weights = SimpleNamespace(**fbt_weights)
     
    FREQ_THRESHOLD = 3
    CONFIDENCE_MIN = weights.confidence_min
    LIFT_MIN = weights.lift_min
    PRICE_TOLERANCE = weights.price_tolerance
    
    s3_path = os.getenv("S3_PATH", "s3://retail-search")

    # Load CSVs from S3 by client
    catalog = load_csv_from_s3(s3_path, client, "catalog")
    orderss= load_csv_from_s3(s3_path, client, "orders")
    inventory = load_csv_from_s3(s3_path, client, "inventory")
    
    inventorydf = inventory[inventory["stock_quantity"] >= 1]
    catalogdf = catalog[catalog["sku_id"].isin(inventorydf["sku_id"])]
    orderssdf = orderss[orderss["sku_id"].isin(inventorydf["sku_id"])]
    print("Total orders:", orderssdf["order_id"].nunique())
    print("Order items distribution:")
    print(orderssdf.groupby("order_id")["sku_id"].count().value_counts())
    
    pairsdf = product_pairs(orderssdf.groupby("order_id")["sku_id"].apply(list))
    print("Pairs generated:", len(pairsdf))
    print(pairsdf.head())
    supportdf = calculate_support(orderssdf, pairsdf)
    # supportdf.to_csv("supportdf_debug.csv", index=False)
    
    # supportdf = supportdf[supportdf["OrderCount"] >= FREQ_THRESHOLD]
    
    # print("Pairs after support threshold:", len(supportdf))
    if supportdf.empty:
        print("⚠️ No FBT pairs found")
        return pd.DataFrame()
    conf_df = calculate_confidence(orderssdf, supportdf)
    
    # print("Confidence df : ",conf_df)
    
    conf_df = conf_df[
        (conf_df["Confidence(A→B)"] >= CONFIDENCE_MIN)
        | (conf_df["Confidence(B→A)"] >= CONFIDENCE_MIN)
    ]
    print("After confidence:", len(conf_df))
    # print("Pairs after confidence threshold:", len(conf_df))
    if conf_df.empty:
        # print("⚠️ No FBT pairs after confidence filter")
        return pd.DataFrame()
    
    liftdf = calculate_lift(orderssdf, conf_df)
    liftdf = liftdf[
        (liftdf["Lift(A→B)"] >= LIFT_MIN)
        | (liftdf["Lift(B→A)"] >= LIFT_MIN)
    ]
    print("After lift:", len(liftdf))
    # print("Lift df : ",liftdf)
    
    # print("Pairs after lift threshold:", len(liftdf))
    if liftdf.empty:
        print("⚠️ No FBT pairs after lift filter")
        return pd.DataFrame()
    
    
    finaldf = supportdf.merge(liftdf, on="Pair")
    finaldf["score"] = finaldf.apply(calculate_score, axis=1)
    
    # print("Final df : ",finaldf.head(10))
    
    merged = merge_fbt_with_catalog(finaldf, catalogdf, price_tolerance=PRICE_TOLERANCE)
    print("After merge:", len(merged))
    
    # print("Merged : ",merged.head(10))order
    
    if merged.empty:
        print("⚠️ No FBT pairs survived catalog/price/l1 filter")
        return pd.DataFrame()
    merged["sorted_pair"] = merged.apply(
        lambda r: tuple(sorted([r["skuid_A"], r["skuid_B"]])), axis=1
    )
    merged = merged.drop_duplicates(subset="sorted_pair").drop(columns=["sorted_pair"])
    # print("Merged : ",merged.head(10))
    
    
    # meili search
    
    grouped_docs = []
    for skuid_a, group in merged.groupby("skuid_A"):
        grouped_docs.append(fbt_group_to_es_doc(group))
        
    # print("Grouped docs : ",grouped_docs)
    
    # final_es=df_to_es_docs(grouped_docs)
    push_to_es(
        INDEX_PREFIX=f"{client}_fbt_products",
        ALIAS_NAME=f"{client}_fbt_products",
        docs=grouped_docs
    )    
    
    grouped_docs = []
    for skuid_a, group in merged.groupby("skuid_A"):
        grouped_docs.append(fbt_group_to_es_doc(group))
    # print("Grouped docs : ",grouped_docs)
    # Removed global FBT index write to avoid cross-client contamination.
    print(f"✅ Pushed {len(grouped_docs)} FBT docs to ES")
    return {"data": df_to_es_docs(merged)}
