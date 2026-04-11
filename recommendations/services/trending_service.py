from ..exceptions.exceptions import BadRequestException, PipelineException
from ..pipelines.trending_pipeline import run_trending_pipeline
from ..pipelines.trending_categories import run_category_trending_pipeline
from ..adapters.meili.searcher import search_meili
from ..pipelines.best_seller_pipeline import run_bestseller_pipeline


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
    

    def getTrendingProducts(self,client:str,filters: dict ={}, limit: int=20, page: int=0):

        try:
            filter_parts=[f'{k}={v}' for k,v in filters.items()]
            filter_str = " AND ".join(filter_parts) if filter_parts else None
            offset = (page - 1) * limit
            response=search_meili(f"{client}_trending_products",
                                  filters=filter_str,
                                  limit=limit,
                                  offset=offset)

            return {
                "count": len(response),
                "data":response
            }
        except Exception as e:
            raise PipelineException(f"fetching trending products failed {str(e)}")
        



