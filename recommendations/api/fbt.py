from fastapi import APIRouter, HTTPException, Query
from ..services.fbt_service import FrequentlyBoughtTogetherService
from ..schemas.schema import TrainFbtProductsRequest

router = APIRouter()

# router=ApiRouter(include)
fbtService = FrequentlyBoughtTogetherService()

@router.post("/train")
def train_fbt(payload:TrainFbtProductsRequest):
    client = payload.client
    settings = payload.settings
    print("Settings : ",settings)
    result = fbtService.trainFrequentlyBoughtTogether(settings,client)
    
    return result

@router.get("/fetch")
def recommendation(payload: dict):
    index_name = payload.get("index_name")
    product_id = payload.get("product_id")
    top_n = payload.get("top_n", 5)
    result = fbtService.fetch_fbt_products(
        product_id,
        index_name,
        top_n
    )
    return result