from fastapi import APIRouter, HTTPException, Query
from ..services.trending_service import TrendingService
from ..services.popular_category_service import PopularCategoryService
from ..schemas.schema import TrainTrendingRequest, TrainRecommendationsRequest
from recommendations.services.dealofday_service import DealOfDayService , dealofday_fetch_l1 , dealofday_fetch_l2 ,dealofday_fetch_l3, dealofday_fetch
from typing import List


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
    return result

@router.post("/dealofday/train")
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
