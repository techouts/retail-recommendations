from ..exceptions.exceptions import BadRequestException, PipelineException
from ..pipelines.trending_pipeline import run_trending_pipeline
from ..pipelines.trending_categories import run_category_trending_pipeline
from ..adapters.meili.searcher import search_meili

class TrendingService:

    def trainTrendingProducts(self, trending_settings: dict, client: str):
        try:
            data = run_category_trending_pipeline(trending_settings, client)

            return {
                "success": True,
                "count": len(data),
                "data": data
            }

        except Exception as e:
            raise PipelineException(f"Trending training failed: {str(e)}")
    

    def getTrendingProducts(self,client:str):
        try:
            response=search_meili(f"{client}_trending_products")
            return {
                "count": len(response),
                "data":response
            }
        except Exception as e:
            raise PipelineException(f"fetching trending products failed {str(e)}")
        

