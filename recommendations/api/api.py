from fastapi import APIRouter, HTTPException, Query
from ..services.trending_service import TrendingService
from ..services.popular_category_service import PopularCategoryService
from ..schemas.schema import TrainTrendingRequest, TrainRecommendationsRequest






router = APIRouter(prefix="/recommendations", tags=["Recommendations"])
trendingService=TrendingService()
categoryService=PopularCategoryService()


@router.post("/trending/train")
def train_trending(payload:TrainTrendingRequest ):
    try:
        result = trendingService.trainTrendingProducts(
            payload.settings,
            payload.Client
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.get("/trending/data-preview")
def fetch_trending_products(client: str = Query(...)):
    try:
        result = trendingService.getTrendingProducts(client)
        return result
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/popular_categories/train")
def train_popular_categories(payload: TrainRecommendationsRequest):
    try:
        result=categoryService.train_popular_category(
            payload.settings,
            payload.Client
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))