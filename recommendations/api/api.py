from fastapi import APIRouter, Depends
from ..services.trending_service import TrendingService,BestSellerService
from recommendations.adapters.meili.searcher import search_meili
from fastapi import APIRouter, Query, HTTPException, Request
from typing import List, Optional
from recommendations.adapters.meili.client import client  




router = APIRouter(prefix="/recommendations", tags=["Recommendations"])
trendingService=TrendingService()
bestSellerService = BestSellerService()


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



@router.post("/best-seller/train")
def train_best_seller(payload: dict):

    client = payload.get("Client")
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