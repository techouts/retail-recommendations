from ..exceptions.exceptions import BadRequestException, PipelineException
from ..pipelines.trending_pipeline import run_trending_pipeline
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
    

    # def trendingDataPreview(self,client:str):
    #     try:




class BestSellerService:

    def trainBestSellerProducts(self, weights: dict, time_window: dict, client: str):

        print("Best Seller Service Started")

        result_df = run_bestseller_pipeline(weights, time_window,client)

        print(" Pipeline Completed")

        return {
            "message": "Best Sellers training complete",
            "count": len(result_df),
            "client": client,
            "data": result_df.to_dict(orient="records")
        }