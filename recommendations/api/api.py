from fastapi import APIRouter, Depends
from ..services.trending_service import TrendingService
from recommendations.services.dealofday_service import DealOfDayService
from recommendations.services.fbt_service import FrequentlyBoughtTogetherService
from typing import List
from fastapi import Query
from pydantic import BaseModel


from ..services.trending_service import TrendingService,BestSellerService
from recommendations.adapters.meili.searcher import search_meili
from fastapi import APIRouter, Query, HTTPException, Request
from typing import List, Optional
from recommendations.adapters.meili.client import client  
from ..services.popular_category_service import PopularCategoryService
from ..schemas.schema import TrainTrendingRequest, TrainRecommendationsRequest
from recommendations.services.dealofday_service import DealOfDayService
from typing import List


router = APIRouter(prefix="/recommendations", tags=["Recommendations"])
trendingService=TrendingService()
categoryService=PopularCategoryService()
bestSellerService = BestSellerService()
dealOfDayService=DealOfDayService()

fbtService = FrequentlyBoughtTogetherService()


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
    
    result = dealofdayService.trainDealOfDay(settings,client,levels)
    
    return result

@router.post("/trending/train-fbt")
def train_fbt(payload:dict):
    client = payload.get("client")
    settings = payload.get("settings")
    print("Settings : ",settings)
    result = FrequentlyBoughtTogetherService().trainFrequentlyBoughtTogether(settings,client)
    
    return result

@router.get("/fetch/fbt")
def recommendation(index_name: str, product_id: str, top_n: int = 5):
    print("Index name:", index_name)

    result = fbtService.fetch_fbt_products(
        product_id=product_id,
        index_name=index_name,
        top_n=top_n
    )

    return result

@router.get("/fetch/dealofday/l1")
def fetch_dod_l1(
    l1: List[str] = Query(...),
    size: int = 5,
    index_name: str = ""
):
    title_case_list = [item.title() for item in l1]
    offset = 0

    response = dealOfDayService.dealofday_fetch_l1(
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
    
    response = dealOfDayService.dealofday_fetch_l2(
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
    response = dealOfDayService.dealofday_fetch_l3(
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
    l3: List[str] = Query(...),
    size: int = 5,
    index_name: str = Query(...)
):
    title_case_list_l1 = [item.title() for item in l1]
    title_case_list_l2 = [item.title() for item in l2]
    title_case_list_l3 = [item.title() for item in l3]
    offset=0
    response = dealOfDayService.dealofday_fetch(
        index_name=index_name,
        l1list=title_case_list_l1,
        l2list=title_case_list_l2,
        l3list=title_case_list_l3,
        limit=size,
        offset=offset
    )
    return response




@router.post("/best-seller/train")
def train_best_seller(payload: dict):

    client = payload.get("client")
    settings = payload.get("settings", {})
    time_window = payload.get("time_window", {})

    result = bestSellerService.trainBestSellerProducts(settings, time_window, client)

    return result

@router.get("/bestseller/all")
def fetch_all_bestsellers(size: int = 20):

    results = search_meili(
        index_name="best_sellers",
        limit=size
    )

    return results


# index = client.index("best_sellers")
# index.update_filterable_attributes(["category_l3"])
# from recommendations.adapters.meili.client import client

# index = client.index("best_sellers")

# index.update_filterable_attributes([
#     "category_l3",
#     "skuid"
# ])
@router.get("/bestseller/label3")
def fetch_bs_label3(
    request: Request,
    l3: Optional[List[str]] = Query(default=None),

    size: int = 100
):
    
    allowed_params = {"l3", "size"}
    if not set(request.query_params.keys()).issubset(allowed_params):
        raise HTTPException(
            status_code=400,
            detail="Only 'l3' and 'size' parameters are allowed"
            
        )

    l3_list = [item.lower().strip() for item in l3 or [] if item]

    if not l3_list:
        raise HTTPException(
            status_code=400,
            detail="l3 parameter is required"
        )

   
    filter_values = ",".join([f'"{item}"' for item in l3_list])
    filter_query = f"category_l3 IN [{filter_values}]"

    response = search_meili(
        index_name="best_sellers",
        query="",             
        filters=filter_query,
        limit=size,
        offset=0
    )

    if not response.get("hits"):
        raise HTTPException(
            status_code=404,
            detail=f"No products found for category_l3: {', '.join(l3_list)}"
        )

    return {
        "count": len(response["hits"]),
        "data": response["hits"]
    }




@router.get("/bestseller/skuid")
def fetch_bs_product_id(
    request: Request,
    skuid: Optional[List[str]] = Query(default=None)
    ):
    allowed_params = {"skuid"}
    if not set(request.query_params.keys()).issubset(allowed_params):
        raise HTTPException(
            status_code=400,
            detail="Only 'skuid' parameters are allowed"
        )

    skuid_list = [item.strip() for item in skuid or [] if item]

    if not skuid_list:
        raise HTTPException(
            status_code=400,
            detail="skuid parameter is required"
        )

    filter_values = ",".join([f'"{item}"' for item in skuid_list])
    filter_query = f"skuid IN [{filter_values}]"

    response = search_meili(
        index_name="best_sellers",
        query="",
        filters=filter_query,
        limit=len(skuid_list)
    )

    if not response.get("hits"):
        raise HTTPException(
            status_code=404,
            detail=f"No products found for skuid: {', '.join(skuid_list)}"
        )
    return {
        "count": len(response["hits"]),
        "data": response["hits"]
    }