from collections import defaultdict
import logging
import traceback
from elasticsearch import Elasticsearch, helpers
import numpy as np
import pandas as pd
from recommendations.adapters.es.client import get_es_client

from dotenv import load_dotenv
import os


# ELASTICSEARCH_HOST=14.192.1.134
# ELASTICSEARCH_PORT=9200



es = get_es_client()


def push_to_es(INDEX_PREFIX, ALIAS_NAME, docs: list[dict]):
    index = None
    backup_index = None
    try:
        logging.info(" Starting Elasticsearch index process...")
        

        if es.indices.exists(index=f"{INDEX_PREFIX}_a"):
            index = f"{INDEX_PREFIX}_b"
            backup_index = f"{INDEX_PREFIX}_a"
        elif es.indices.exists(index=f"{INDEX_PREFIX}_b"):
            index = f"{INDEX_PREFIX}_a"
            backup_index = f"{INDEX_PREFIX}_b"
        else:
            index = f"{INDEX_PREFIX}_a"
            logging.info(" No existing index found. Creating fresh A")

       
        if not es.indices.exists(index=index):
            es.indices.create(index=index)
            logging.info(f" Created index: {index}")

        
        actions = [{"_index": index, "_source": doc} for doc in docs]

        logging.info(f" Indexing {len(actions)} documents...")
        
        success, errors = helpers.bulk(
            client=es,
            actions=actions,
            raise_on_error=False,
            raise_on_exception=False,
            chunk_size=1000,
            stats_only=False
        )
        print("sucess",success,"errors",errors)

        logging.info(f" Successfully indexed: {success} documents")

        if errors:
            logging.warning(" Some errors occurred during bulk indexing:")
            es.indices.delete(index=index)
            for err in errors[:5]:
                logging.warning(err)
        else:
            logging.info(" All documents indexed successfully.")
            if backup_index and es.indices.exists(index=backup_index):
                es.indices.delete(index=backup_index)
            alias_actions = [{"add": {"index": index, "alias": ALIAS_NAME}}]
            es.indices.update_aliases(body={"actions": alias_actions})
       
        # alias_actions = []
        # alias_actions.append({"add": {"index": index, "alias": ALIAS_NAME}})

        # es.indices.update_aliases(body={"actions": alias_actions})
        logging.info(f" Alias '{ALIAS_NAME}' updated to point to index: {index}")

    except Exception as e:
        logging.error(f" Exception occurred: {e}")
        traceback.print_exc()
        if index and es.indices.exists(index=index):
            es.indices.delete(index=index)
            logging.info(f" Deleted partial index due to error: {index}")



def get_data_from_es(ALIAS_NAME)-> list[dict]:
    try:

        if not es.indices.exists_alias(name=ALIAS_NAME):
            print(f" Alias '{ALIAS_NAME}' does not exist.")
            return []
        response = es.search(
            index=ALIAS_NAME,
            body={"query": {"match_all": {}}},
            scroll="2m",
            size=10000  
        )
        scroll_id = response.get("_scroll_id")
        hits = response["hits"]["hits"]
        all_docs = [hit["_source"] for hit in hits]
        while True:
            scroll_response = es.scroll(scroll_id=scroll_id, scroll="2m")
            hits = scroll_response["hits"]["hits"]
            if not hits:
                break
            all_docs.extend([hit["_source"] for hit in hits])

        print(f" Retrieved {len(all_docs)} documents from alias '{ALIAS_NAME}'")
        return all_docs

    except Exception as e:
        print(f" Error fetching data from alias '{ALIAS_NAME}': {e}")
        traceback.print_exc()
        return []





# def fetch_by_l1(alias, l1, size=100):
#     if l1:
#         query = {
#             "query": {
#                 "term": {
#                     "l1.keyword": l1   # use .keyword so it matches exact string
#                 }
#             }
#         }
#     else:
#         query = {"query": {"match_all": {}}}

#     resp = es.search(index=alias, body=query, size=size)
#     return [hit["_source"] for hit in resp["hits"]["hits"]]


# # 2️⃣ Fetch by l1 + l2
# def fetch_by_l2(alias,  l2, size=100):
#     query = {
#         "query": {
#             "bool": {
#                 "must": [
#                     # {"term": {"l1.keyword": l1}},
#                     {"term": {"l2.keyword": l2}}
#                 ]
#             }
#         }
#     }
#     resp = es.search(index=alias, body=query, size=size)
#     return [hit["_source"] for hit in resp["hits"]["hits"]]


# # 3️⃣ Fetch by l1 + l2 + l3
# def fetch_by_l3(alias, l3, size=10):
#     query = {
#         "query": {
#             "bool": {
#                 "must": [
#                     # {"term": {"l1.keyword": l1}},
#                     # {"term": {"l2.keyword": l2}},
#                     {"term": {"l3.keyword": l3}}
#                 ]
#             }
#         }
#     }
#     resp = es.search(index=alias, body=query, size=size)
#     return [hit["_source"] for hit in resp["hits"]["hits"]]


# # 4️⃣ Fetch ALL
# def fetch_all(alias, size=1000):
#     query = {"query": {"match_all": {}}}
#     resp = es.search(index=alias, body=query, size=size)
#     return [hit["_source"] for hit in resp["hits"]["hits"]]


def hits_to_nested_format(hits):
    result = [{"category": []}]
    category_dict = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

    for src in hits:
        l1, l2, l3 = src["l1"], src["l2"], src["l3"]
        product = {
            "skuid": src["skuid"],
            "title": src["title"],
            "brand": src["brand"],
            "price": src["price"],
            "trending_score": src["trending_score"]
        }
        category_dict[l1][l2][l3].append(product)

    # Convert nested defaultdicts to the JSON format you want
    for l1_key, l2_map in category_dict.items():
        l1_list = []
        for l2_key, l3_map in l2_map.items():
            l2_list = []
            for l3_key, products in l3_map.items():
                l2_list.append({l3_key: products})
            l1_list.append({l2_key: l2_list})
        result[0]["category"].append({l1_key: l1_list})

    return result



def fetch_by_l1(alias, l1=None, size=100):
    if l1 is None or (isinstance(l1, list) and not l1):  # None or empty list → match_all
        query = {"query": {"match_all": {}}}
    elif isinstance(l1, list):  # multiple values
        query = {"query": {"terms": {"l1.keyword": l1}}}
    else:  # single value
        query = {"query": {"term": {"l1.keyword": l1}}}

    resp = es.search(index=alias, body=query, size=size)
    hits = [hit["_source"] for hit in resp["hits"]["hits"]]
    return hits_to_nested_format(hits)

# 2️⃣ Fetch by l2
def fetch_by_l2(alias, l2=None, size=100):
    if l2 is None or (isinstance(l2, list) and not l2):  # None or empty list → match_all
        query = {"query": {"match_all": {}}}
    elif isinstance(l2, list):  # multiple values
        query = {"query": {"terms": {"l2.keyword": l2}}}
    else:  # single value
        query = {"query": {"term": {"l2.keyword": l2}}}

    resp = es.search(index=alias, body=query, size=size)
    hits = [hit["_source"] for hit in resp["hits"]["hits"]]
    return hits_to_nested_format(hits)


def fetch_by_l3(alias, l3=None, size=100):
    if l3 is None or (isinstance(l3, list) and not l3):  # None or empty list → match_all
        query = {"query": {"match_all": {}}}
    elif isinstance(l3, list):  # multiple values
        query = {"query": {"terms": {"l3.keyword": l3}}}
    else:  # single value
        query = {"query": {"term": {"l3.keyword": l3}}}

    resp = es.search(index=alias, body=query, size=size)
    hits = [hit["_source"] for hit in resp["hits"]["hits"]]
    return hits_to_nested_format(hits)


def fetch_all(alias, size=1000):
    query = {"query": {"match_all": {}}}
    resp = es.search(index=alias, body=query, size=size)
    hits = [hit["_source"] for hit in resp["hits"]["hits"]]
    return hits_to_nested_format(hits)


# def fetch_by_levels(alias, l1=None, l2=None, l3=None, size=1000):
#     must_clauses = []
#     if l1:
#         must_clauses.append({"term": {"l1.keyword": l1}})
#     if l2:
#         must_clauses.append({"term": {"l2.keyword": l2}})
#     if l3:
#         must_clauses.append({"term": {"l3.keyword": l3}})

#     if must_clauses:
#         query = {"query": {"bool": {"must": must_clauses}}}
#     else:
#         query = {"query": {"match_all": {}}}

#     resp = es.search(index=alias, body=query, size=size)
#     hits = [hit["_source"] for hit in resp["hits"]["hits"]]
#     return hits_to_nested_format(hits)

# def fetch_by_levels(alias, l1=None, l2=None, l3=None, size=10):
#     used_siblings = False
#     collected_products = []

#     # Build the base must query
#     def build_query(l1=None, l2=None, l3=None):
#         must_clauses = []

#         if l1:
#             must_clauses.append({"term": {"l1": l1}})

#         if l2:
#             if isinstance(l2, list) and len(l2) > 1:
#                 must_clauses.append({"terms": {"l2": l2}})
#         else:
#             must_clauses.append({"term": {"l2": l2[0] if isinstance(l2, list) else l2}})

#         if l3:
#             if isinstance(l3, list) and len(l3) > 1:
#                 must_clauses.append({"terms": {"l3": l3}})
#         else:
#             must_clauses.append({"term": {"l3": l3[0] if isinstance(l3, list) else l3}})

#         return {
#             "query": {
#             "bool": {
#                 "must": must_clauses
#             }
#         }
#     }


#     # Step 1: Fetch from exact l3 first
#     if l3:
#         resp = es.search(index=alias, body=build_query(l1, l2, l3, limit=size))
#         hits = [hit["_source"] for hit in resp["hits"]["hits"]]
#         collected_products.extend(hits)

#     # Step 2: If less than required, fetch from sibling l3 (within same l2)
#     if l2 and len(collected_products) < size:
#         used_siblings = True

#         # Get all distinct l3s under the same l2
#         aggs_query = {
#             "size": 0,
#             "query": {"term": {"l2.keyword": l2}},
#             "aggs": {
#                 "unique_l3": {"terms": {"field": "l3.keyword", "size": 100}}
#             }
#         }
#         l3_aggs = es.search(index=alias, body=aggs_query)
#         all_l3_values = [b["key"] for b in l3_aggs["aggregations"]["unique_l3"]["buckets"]]

#         exclude_ids = [p["product_id"] for p in collected_products]
#         for sibling_l3 in all_l3_values:
#             if sibling_l3 == l3:
#                 continue
#             remaining = size - len(collected_products)
#             if remaining <= 0:
#                 break

#             resp = es.search(index=alias, body=build_query(l1, l2, sibling_l3, exclude_ids, limit=remaining))
#             hits = [hit["_source"] for hit in resp["hits"]["hits"]]
#             collected_products.extend(hits)
#             exclude_ids.extend([h["product_id"] for h in hits])

#     # Step 3: If still less, fetch from sibling l2 (within same l1)
#     if l1 and len(collected_products) < size:
#         used_siblings = True

#         # Get all distinct l2s under same l1
#         aggs_query = {
#             "size": 0,
#             "query": {"term": {"l1.keyword": l1}},
#             "aggs": {
#                 "unique_l2": {"terms": {"field": "l2.keyword", "size": 100}}
#             }
#         }
#         l2_aggs = es.search(index=alias, body=aggs_query)
#         all_l2_values = [b["key"] for b in l2_aggs["aggregations"]["unique_l2"]["buckets"]]

#         exclude_ids = [p["product_id"] for p in collected_products]
#         for sibling_l2 in all_l2_values:
#             if sibling_l2 == l2:
#                 continue
#             remaining = size - len(collected_products)
#             if remaining <= 0:
#                 break

#             resp = es.search(index=alias, body=build_query(l1, sibling_l2, None, exclude_ids, limit=remaining))
#             hits = [hit["_source"] for hit in resp["hits"]["hits"]]
#             collected_products.extend(hits)
#             exclude_ids.extend([h["product_id"] for h in hits])

#     return {
#         "products": collected_products,
#         "used_siblings": used_siblings
#     }






# def hits_to_nested_format(hits):
#     result = [{"category": []}]
#     category_dict = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

#     for src in hits:
#         l1, l2, l3 = src["l1"], src["l2"], src["l3"]
#         product = {
#             "skuid": src["skuid"],
#             "title": src["title"],
#             "brand": src["brand"],
#             "price": src["price"],
#             "trending_score": src["trending_score"]
#         }
#         category_dict[l1][l2][l3].append(product)

#     # Convert nested defaultdicts to the JSON format you want
#     for l1_key, l2_map in category_dict.items():
#         l1_list = []
#         for l2_key, l3_map in l2_map.items():
#             l2_list = []
#             for l3_key, products in l3_map.items():
#                 l2_list.append({l3_key: products})
#             l1_list.append({l2_key: l2_list})
#         result[0]["category"].append({l1_key: l1_list})

#     return result



# def fetch_by_l1(alias, l1=None, size=100):
#     if l1 is None or (isinstance(l1, list) and not l1):  # None or empty list → match_all
#         query = {"query": {"match_all": {}}}
#     elif isinstance(l1, list):  # multiple values
#         query = {"query": {"terms": {"l1.keyword": l1}}}
#     else:  # single value
#         query = {"query": {"term": {"l1.keyword": l1}}}

#     resp = es.search(index=alias, body=query, size=size)
#     hits = [hit["_source"] for hit in resp["hits"]["hits"]]
#     return hits_to_nested_format(hits)

# # 2️⃣ Fetch by l2
# def fetch_by_l2(alias, l2=None, size=100):
#     if l2 is None or (isinstance(l2, list) and not l2):  # None or empty list → match_all
#         query = {"query": {"match_all": {}}}
#     elif isinstance(l2, list):  # multiple values
#         query = {"query": {"terms": {"l2.keyword": l2}}}
#     else:  # single value
#         query = {"query": {"term": {"l2.keyword": l2}}}

#     resp = es.search(index=alias, body=query, size=size)
#     hits = [hit["_source"] for hit in resp["hits"]["hits"]]
#     return hits_to_nested_format(hits)


# def fetch_by_l3(alias, l3=None, size=100):
#     if l3 is None or (isinstance(l3, list) and not l3):  # None or empty list → match_all
#         query = {"query": {"match_all": {}}}
#     elif isinstance(l3, list):  # multiple values
#         query = {"query": {"terms": {"l3.keyword": l3}}}
#     else:  # single value
#         query = {"query": {"term": {"l3.keyword": l3}}}

#     resp = es.search(index=alias, body=query, size=size)
#     hits = [hit["_source"] for hit in resp["hits"]["hits"]]
#     return hits_to_nested_format(hits)


# def fetch_all(alias, size=1000):
#     query = {"query": {"match_all": {}}}
#     resp = es.search(index=alias, body=query, size=size)
#     hits = [hit["_source"] for hit in resp["hits"]["hits"]]
#     return hits_to_nested_format(hits)


# def fetch_by_levels(alias, l1=None, l2=None, l3=None,size=10):
#     print("sizedsfadfa",size)
#     used_siblings = False
#     collected_products = []

#     # Ensure lists for safe iteration
#     l1 = l1 if l1 else []
#     l2 = l2 if l2 else []
#     l3 = l3 if l3 else []

#     # ------------------------
#     # Step 0: Validate Hierarchy
#     # ------------------------
#     def hierarchy_exists(l1_list, l2_list, l3_list):
#         # Validate l2 under l1
#         if l1_list and l2_list:
#             aggs_query = {
#                 "size": 0,
#                 "query": {"terms": {"l1.keyword": l1_list}},
#                 "aggs": {"unique_l2": {"terms": {"field": "l2.keyword", "size": 1000}}}
#             }
#             res = es.search(index=alias, body=aggs_query)
#             valid_l2 = {b["key"] for b in res["aggregations"]["unique_l2"]["buckets"]}
#             if not any(v in valid_l2 for v in l2_list):
#                 return False

#         # Validate l3 under l2
#         if l2_list and l3_list:
#             valid_l3 = set()
#             for l2_val in l2_list:
#                 aggs_query = {
#                     "size": 0,
#                     "query": {"term": {"l2.keyword": l2_val}},
#                     "aggs": {"unique_l3": {"terms": {"field": "l3.keyword", "size": 1000}}}
#                 }
#                 res = es.search(index=alias, body=aggs_query)
#                 valid_l3.update([b["key"] for b in res["aggregations"]["unique_l3"]["buckets"]])
#             if not any(v in valid_l3 for v in l3_list):
#                 return False

#         # Validate l3 under l1 if l2 missing
#         if l1_list and l3_list and not l2_list:
#             valid_l3 = set()
#             for l1_val in l1_list:
#                 aggs_query = {
#                     "size": 0,
#                     "query": {"term": {"l1.keyword": l1_val}},
#                     "aggs": {"unique_l3": {"terms": {"field": "l3.keyword", "size": 1000}}}
#                 }
#                 res = es.search(index=alias, body=aggs_query)
#                 valid_l3.update([b["key"] for b in res["aggregations"]["unique_l3"]["buckets"]])
#             if not any(v in valid_l3 for v in l3_list):
#                 return False

#         return True

#     if not hierarchy_exists(l1, l2, l3):
#         return {"products": [], "used_siblings": False}

#     # ------------------------
#     # Rest of your existing function remains the same
#     # ------------------------
#     def build_query(l1=None, l2=None, l3=None, exclude_ids=None, limit=size):
#         must_clauses = []
        
#         if l1:
#             must_clauses.append({"terms": {"l1.keyword": l1}})
#         if l2:
#             must_clauses.append({"terms": {"l2.keyword": l2}})
#         if l3:
#             must_clauses.append({"terms": {"l3.keyword": l3}})

#         must_not = []
#         if exclude_ids:
#             must_not.append({"terms": {"product_id.keyword": exclude_ids}})

#         return {
#             "size": limit,
#             "query": {"bool": {"must": must_clauses, "must_not": must_not}},
#             "sort": [{"trending_score": {"order": "desc"}}]
#         }

#     # Step 1: Exact match
#     if l3 or l2 or l1:
#         resp = es.search(index=alias, body=build_query(l1, l2, l3, limit=size))
#         hits = [hit["_source"] for hit in resp["hits"]["hits"]]
#         collected_products.extend(hits)

#     # Step 2 & 3: Fallbacks
#     # Only apply sibling fallback if l2 or l3 was not explicitly requested
#     apply_siblings = not l3 and not (l2 and l1)
#     if apply_siblings:
#         # existing sibling logic here
#         pass  # keep your existing Step 2 & 3 fallback logic

#     return {"products": collected_products, "used_siblings": used_siblings}
