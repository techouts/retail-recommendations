from ..exceptions.exceptions import BadRequestException, PipelineException
from ..pipelines.trending_pipeline import run_trending_pipeline
from ..pipelines.trending_categories import run_category_trending_pipeline
from ..adapters.meili.searcher import search_meili
from ..pipelines.best_seller_pipeline import run_bestseller_pipeline
from recommendations.adapters.es.searcher import search_es

class TrendingService:

    def trainTrendingProducts(self, trending_settings: dict, client: str):
        try:
            data = run_trending_pipeline(trending_settings, client)

            return {
                "success": True,
                "count": len(data),
                "data": data
            }

        except Exception as e:
            raise PipelineException(f"Trending training failed: {str(e)}")
    

    # def getTrendingProducts(self,client:str):
    #     try:
    #         response=search_es(f"{client}_trending_products")
    #         return {
    #             "count": len(response),
    #             "data":response
    #         }
    #     except Exception as e:
    #         raise PipelineException(f"fetching trending products failed {str(e)}")
    
    def getTrendingProducts(self, client: str, filters=None, limit=20):
        try:
            alias_name = f"{client}_trending_products"

            # 👉 If no filters
            if not filters:
                result = search_es(
                    alias_name,
                    limit=limit,
                    offset=0
                )
            else:
                must = []
                for field, value in filters.items():
                    must.append({
                        "match": {
                            field: {
                                "query": value,
                                "operator": "and"
                            }
                        }
                    })

                query = {
                    "query": {
                        "bool": {
                            "must": must
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
            raise Exception(f"fetching trending products failed {str(e)}")