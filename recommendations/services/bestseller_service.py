import json
from typing import List
from ..pipelines.best_seller_pipeline import run_bestseller_pipeline
# from recommendations.adapters.meili.searcher import search_es

from recommendations.adapters.es.searcher import search_es

class BestSellerService:
    ALIAS="best_sellers_retail"
    def train_best_sellers(self, weights: dict, time_window: dict, client: str):
        if not client:
            raise ValueError("client is required")

        try:
            result_df = run_bestseller_pipeline(weights, time_window, client)

            return {
                "success": True,
                "message": "Best Sellers training complete",
                "count": len(result_df),
                "client": client,
                "data": result_df   
            }

        except Exception as e:
            raise Exception(f"Best Seller pipeline failed: {str(e)}")

    # -----------------------------
    # HELPER: GET INDEX NAME
    # -----------------------------
    def _get_index_name(self, client: str):
        return f"{client}_best_sellers_retail"

    # -----------------------------
    # FETCH ALL
    # -----------------------------
    
    # def fetch_all(self, client: str, size: int = 20):
    #     try:
    #         index_name = self._get_index_name(client)

    #         return search_es(
    #             index_name=index_name,
    #             limit=size
    #         )

    #     except Exception as e:
    #         raise Exception(f"Failed to fetch best sellers: {str(e)}")
    def fetch_all(self, client: str, size: int = 20):
        try:
            alias_name = f"{client}_best_sellers_retail"

            result = search_es(alias_name, limit=size, offset=0)

            return result["hits"]

        except Exception as e:
            raise Exception(f"Failed to fetch best sellers: {str(e)}")

    # -----------------------------
    # FETCH BY L3
    # -----------------------------
    # def fetch_by_l3(self, client: str, l3_list: List[str], size: int = 100):
    #     if not l3_list:
    #         raise ValueError("l3 list is required")

    #     try:
    #         alias_name = f"{client}_best_sellers_retail"

    #         filters = f"category_l3 IN {json.dumps(l3_list)}"

    #         response = search_es(
    #             index_name=alias_name,
    #             query="",
    #             filters=filters,
    #             limit=size,
    #             offset=0
    #         )

    #         return response

    #     except Exception as e:
    #         raise Exception(f"Failed to fetch by L3: {str(e)}")
    def fetch_by_l3(self, client: str, l3_list: list[str], size: int = 100):
        if not l3_list:
            raise ValueError("l3 list is required")

        try:
            alias_name = f"{client}_best_sellers_retail"

            query = {
                "query": {
                    "bool": {
                        "should": [
                            {"match": {"l3": item}}   # ✅ FIXED FIELD
                            for item in l3_list
                        ],
                        "minimum_should_match": 1
                    }
                }
            }

            result = search_es(alias_name, query=query, limit=size, offset=0)

            return result

        except Exception as e:
            raise Exception(f"Failed to fetch by L3: {str(e)}")
    # -----------------------------
    # FETCH BY SKUID
    # -----------------------------
    # def fetch_by_skuid(self, client: str, skuid_list: List[str]):
    #     if not skuid_list:
    #         raise ValueError("skuid list is required")

    #     try:
    #         index_name = self._get_index_name(client)

    #         filters = f"skuid IN {json.dumps(skuid_list)}"

    #         response = search_es(
    #             index_name=index_name,
    #             query="",
    #             filters=filters,
    #             limit=len(skuid_list)
    #         )

    #         return response

    #     except Exception as e:
    #         raise Exception(f"Failed to fetch by skuid: {str(e)}")
        
    def fetch_by_skuid(self, client: str, skuid_list: list[str]):
        if not skuid_list:
            raise ValueError("skuid list is required")

        try:
            alias_name = f"{client}_best_sellers_retail"

            query = {
                "query": {
                    "terms": {
                        "skuid.keyword": skuid_list   # ✅ BEST
                    }
                }
            }

            result = search_es(
                alias_name,
                query=query,
                limit=len(skuid_list),
                offset=0
            )

            return result

        except Exception as e:
            raise Exception(f"Failed to fetch by skuid: {str(e)}")