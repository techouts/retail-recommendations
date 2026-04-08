from fastapi import APIRouter, HTTPException
from ..services.dealofday_service import DealOfDayService
from typing import List
from fastapi import Query
from ..schemas.schema import TrainDodRequest

router=APIRouter()
dealOfDayService=DealOfDayService()

@router.post("/train")
def train_dealofday(payload: TrainDodRequest):
    '''
    Expected payload:
    {
        "client":"ssb",
        "settings": {
            "id":2,
            "status": "active",
            "min_discount_threshold": 5.0,
            "max_discount_threshold": 35.0,
            "min_stock": 20,
            "rating_threshold": 4.2,
            "min_reviews": 10,
            "new_product_window_days": 25,
            "final_score_threshold": 50.0,
            "reviews_weight": 0.30,
            "views_weight": 0.20,
            "addtocart_weight": 0.25,
            "rating_weight": 0.25
        },
        "level":["clothing","Men","Shoes"]
    }
    '''
    client = payload.client
    settings = payload.settings
    levels = payload.levels
    
    print("Settings : ",settings)
    
    result = dealOfDayService.trainDealOfDay(settings,client,levels)
    
    return result

@router.get("/fetch/l1")
def fetch_dod_l1(
    l1: List[str] = Query(...),
    size: int = 5,
    index_name: str = ""
    ):
    title_case_list = [item.lower() for item in l1]
    offset = 0

    response = dealOfDayService.dealoftheday_fetch_l1(
        index_name,
        title_case_list,
        size
    )
    return response
    
    
@router.get("/fetch/l2")
def fetch_dod_l2(
    l2: List[str] = Query(...),
    size: int = 5,
    index_name: str = ""  
    ):
    # title_case_list = [item.lower() for item in l2]
    title_case_list = [item for item in l2]
    
    response = dealOfDayService.dealoftheday_fetch_l2(
        index_name,
        title_case_list,
        size,
    )
    return response
    

@router.get("/fetch/l3")
def fetch_dod_l3(
    l3: List[str] = Query(...),
    size: int =5,
    index_name: str = ""
):
    title_case_list = [item for item in l3]
    response = dealOfDayService.dealoftheday_fetch_l3(
        index_name,
        title_case_list,
        size,
    )
    return response


@router.get("/fetch_all")
def fetch_dod(
    size: int =5,
    index_name: str = Query(...)
):
    response = dealOfDayService.dealoftheday_fetch_all(
        index_name=index_name,
        size=size
    )
    return response
