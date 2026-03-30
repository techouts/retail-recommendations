from fastapi import APIRouter, Depends
from ..services.trending_service import TrendingService
from recommendations.services.dealofday_service import DealOfDayService , dealofday_fetch_l1 , dealofday_fetch_l2 ,dealofday_fetch_l3, dealofday_fetch
from typing import List
from fastapi import Query

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

@router.post("/trending/train-dealofday")
def train_dealofday(payload: dict):
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
    client = payload.get("client")
    settings = payload.get("settings")
    levels = payload.get("levels")
    
    print("Settings : ",settings)
    
    result = DealOfDayService().trainDealOfDay(settings,client,levels)
    
    return result

@router.get("/fetch/dealofday/l1")
def fetch_dod_l1(
    l1: List[str] = Query(...),
    size: int = 5,
    index_name: str = ""
):
    title_case_list = [item.title() for item in l1]
    offset = 0

    response = dealofday_fetch_l1(
        index_name=index_name,
        l1list=title_case_list,
        limit=size,
        offset=offset
    )

    return response
    
    
@router.get("/fetch/dealofday/l2")
def fetch_dod_l2(
  l2: List[str] = Query(...),
  size: int = 5,
  index_name: str = ""  
):
    title_case_list = [item.title() for item in l2]
    offset=0
    
    response = dealofday_fetch_l2(
        index_name=index_name,
        l2list=title_case_list,
        limit=size,
        offset=offset
    )
    
    return response
    
@router.get("/fetch/dealofday/l3")
def fetch_dod_l3(
    l3: List[str] = Query(...),
    size: int =5,
    index_name: str = ""
):
    title_case_list = [item.title() for item in l3]
    offset=0
    response = dealofday_fetch_l3(
        index_name=index_name,
        l3list=title_case_list,
        limit=size,
        offset=offset
    )
    return response

@router.get("/fetch/dealofday/")
def fetch_dod(
    l1: List[str] = Query(...),
    l2: List[str] = Query(...),
    size: int = 5,
    index_name: str = Query(...)
):
    title_case_list_l1 = [item.title() for item in l1]
    title_case_list_l2 = [item.title() for item in l2]
    offset=0
    response = dealofday_fetch(
        index_name=index_name,
        l1list=title_case_list_l1,
        l2list=title_case_list_l2,
        limit=size,
        offset=offset
    )
    return response