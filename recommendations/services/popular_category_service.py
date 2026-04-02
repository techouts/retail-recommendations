from ..pipelines.popular_categories import run_popular_categories_pipeline
from ..exceptions.exceptions import BadRequestException, PipelineException


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
    