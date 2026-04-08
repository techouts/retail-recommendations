from fastapi import APIRouter, HTTPException, Query
from ..services.popular_brands_service import PopularBrandsService
from ..schemas.schema import TrainPopularBrandsRequest

router = APIRouter()

pbService = PopularBrandsService()

@router.post("/train")
def train_popular_brands(payload : TrainPopularBrandsRequest):
    client = payload.client
    settings = payload.settings
    result = pbService.train_popular_brands_service(settings,client)
    
    return result

@router.get("/popular_brands")
def get_popular_brands(payload : dict):
   index_name = payload.get("index_name")
   brand = payload.get("branch")
   top_n = payload.get("top_n",5)
   result = pbService.fetch_popular_brands(brand, index_name,top_n)
   return result