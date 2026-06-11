from fastapi import APIRouter, HTTPException, Query, Depends
from ..services.popular_brands_service import PopularBrandsService
from ..schemas.schema import TrainPopularBrandsRequest
from recommendations.security import fetch_rate_limit

router = APIRouter()

pbService = PopularBrandsService()

@router.post("/train/")
def train_popular_brands(payload : TrainPopularBrandsRequest):
    client = payload.Client
    settings = payload.settings
    result = pbService.train_popular_brands_service(settings,client)
    
    return result

@router.get("/popular_brands")
def get_popular_brands(
    brand: str = Query(...),
    index_name: str = Query(default="ss3_popular_brands"),
    top_n: int = Query(default=5, ge=1, le=50),
    _: None = Depends(fetch_rate_limit)
):
    try:
        result = pbService.fetch_popular_brands(brand, index_name, top_n)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))