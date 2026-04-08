from fastapi import APIRouter, HTTPException, Query
from ..services.trending_service import TrendingService
from ..schemas.schema import TrainTrendingRequest

router = APIRouter()
service = TrendingService()


@router.post("/train")
def train_trending(payload:TrainTrendingRequest):
    try:
        
        
        result = service.trainTrendingProducts(
            payload.settings,
            payload.Client
        )
        
        return result
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.get("/data-preview")
def fetch_trending_products(
    client: str = Query(...),
    category_l1: str | None = Query(default=None),
    category_l2: str | None = Query(default=None),
    category_l3: str | None = Query(default=None),
    category_l4: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100)
):
    try:
        filters = {
            k: v for k, v in {
                "category_l1": category_l1,
                "category_l2": category_l2,
                "category_l3": category_l3,
                "category_l4": category_l4,
            }.items() if v is not None
        }
        result = service.getTrendingProducts(client, filters=filters, limit=limit,page=page)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))