from fastapi import APIRouter, Depends
from ..services.trending_service import TrendingService

router = APIRouter(prefix="/recommendations", tags=["Recommendations"])
trendingService=TrendingService()


@router.post("/trending/train-trending")
def train_trending(payload: dict):
    """
    Expected payload:
    {
        "client": "beauty",
        "settings": {
            "business_sales_weight": 0.5,
            "business_views_weight": 0.1,
            "business_cart_weight": 0.3,
            "business_wish_weight": 0.1,
            "threshold_value": 64,
            "min_threshold_relaxed": 40
        }
    }
    """

    client = payload.get("Client")
    settings = payload.get("settings")

    result = trendingService.trainTrendingProducts(settings, client)

    return result