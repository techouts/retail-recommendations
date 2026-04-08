from ..pipelines.popular_categories import run_popular_categories_pipeline
from ..exceptions.exceptions import BadRequestException, PipelineException
from recommendations.adapters.meili.searcher import search_meili
import json
from typing import List
from recommendations.adapters.es.searcher import search_es

class PopularCategoryService:
    def train_popular_category(self,categorySettings: dict,client:str):
        try:
            data=run_popular_categories_pipeline(categorySettings,client)
            return {
                "success": True,
                "count": len(data),
                "data": data
            }
        except Exception as e:
            raise PipelineException(f"Trending training failed: {str(e)}")




    # def fetch_all_categories(self, client: str, limit: int = 10):
    #     try:
    #         # index_name = f"{client}_popular_categories"
    #         alias_name = f"{client}_popular_categories"

    #         response = search_es(
    #             index_name=alias_name,
    #             query="",
    #             limit=limit,
                
    #         )

    #         return response.get("hits", [])

    #     except Exception as e:
    #         raise Exception(f"Failed to fetch categories: {str(e)}")
        
   
    def fetch_all_categories(self, client: str, limit: int = 10):
        try:
            alias_name = f"{client}_popular_categories"
            print("alias_name",alias_name)

            result = search_es(
                alias_name,
                limit=limit,   
                offset=0
            )

            return {
                "count": result["nbHits"],   
                "data": result["hits"]      
            }

        except Exception as e:
            raise Exception(f"Failed to fetch categories: {str(e)}")

    # def fetch_categories_by_filters(
    #     self,
    #     client: str,
    #     filters: dict = None,
    #     limit: int = 20
    # ):
    #     try:
    #         alias_name = f"{client}_popular_categories"

    #         # Build filter query
    #         filter_query = None
    #         if filters:
    #             filter_list = [f'{k} = "{v}"' for k, v in filters.items()]
    #             filter_query = " AND ".join(filter_list)

    #         response = search_es(
    #             index_name=alias_name,
    #             query="",
    #             filters=filter_query,
    #             limit=limit,
                
    #         )

    #         return {
    #             "count": len(response.get("hits", [])),
    #             "data": response.get("hits", [])
    #         }

    #     except Exception as e:
    #         raise Exception(f"Failed to fetch filtered categories: {str(e)}")
        


    def fetch_categories_by_filters(self, client: str, filters=None, limit=20):
        try:
            alias_name = f"{client}_popular_categories"

            # No filters → simple fetch
            if not filters:
                result = search_es(
                    alias_name,
                    limit=limit,
                    offset=0
                )
                return {
                    "count": result["nbHits"],
                    "data": result["hits"]
                }

            # With filters
            query = {
                "query": {
                    "bool": {
                        "should": [
                            {"match": {field: value}}
                            for field, value in filters.items()
                        ],
                        "minimum_should_match": 1
                    }
                }
            }

            result = search_es(
                alias_name,
                query=query,
                limit=limit,
                offset=0
            )

            return {
                "count": result["nbHits"],
                "data": result["hits"]
            }

        except Exception as e:
            raise Exception(f"Failed to fetch filtered categories: {str(e)}")