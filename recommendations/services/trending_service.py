from ..exceptions.exceptions import BadRequestException, PipelineException
from ..pipelines.trending_pipeline import run_trending_pipeline

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
    

    # def trendingDataPreview(self,client:str):
    #     try:
