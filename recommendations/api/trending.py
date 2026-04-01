from fastapi import APIRouter, HTTPException, Query
from ..services.trending_service import TrendingService
from ..schemas.schema import TrainTrendingRequest

router = APIRouter()
service = TrendingService()


@router.post("/train")
def train_trending(payload:TrainTrendingRequest ):
    try:
        result = service.trainTrendingProducts(
            payload.settings,
            payload.Client
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.get("/data-preview")
def fetch_trending_products(client: str = Query(...)):
    try:
        result = service.getTrendingProducts(client)
        return result
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))
    
