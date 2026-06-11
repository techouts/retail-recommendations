from fastapi import APIRouter, HTTPException, Query, Depends
from ..services.fbt_service import FrequentlyBoughtTogetherService
from ..schemas.schema import TrainFbtProductsRequest
from recommendations.security import fetch_rate_limit

router = APIRouter()

# router=ApiRouter(include)
fbtService = FrequentlyBoughtTogetherService()

@router.post("/train/")
def train_fbt(payload:TrainFbtProductsRequest):
    client = payload.Client
    settings = payload.settings
    result = fbtService.trainFrequentlyBoughtTogether(settings,client)
    
    return result

@router.get("/fetch")
def recommendation(
    client: str = Query(...),
    product_id: str = Query(...),
    top_n: int = Query(default=5, ge=1, le=50),
    _: None = Depends(fetch_rate_limit)
):
    try:
        index_name = f"{client}_fbt_products"
        result = fbtService.fetch_fbt_products(
            product_id,
            index_name,
            top_n
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))