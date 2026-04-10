from fastapi import APIRouter, HTTPException, Query
from typing import List
from ..services.bestseller_service import BestSellerService
from fastapi import APIRouter, Depends
from recommendations.security import fetch_rate_limit


router = APIRouter()
bestSellerService = BestSellerService()


# TRAIN BEST SELLERS
@router.post("/train")
def train_best_seller(payload: dict):

    client = payload.get("Client")
    settings = payload.get("settings", {})
    time_window = payload.get("time_window", {})

    if not client:
        raise HTTPException(status_code=400, detail="client is required")

    try:
        return bestSellerService.train_best_sellers(settings, time_window, client)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@router.get("/all")
def fetch_all_bestsellers(client: str, size: int = 20, _: None = Depends(fetch_rate_limit)):

    try:
        return bestSellerService.fetch_all(client, size)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



from fastapi import Query

@router.get("/label3")
def fetch_bs_label3(
    client: str,
    l3: list[str] = Query(...),
    size: int = 100,
    _: None = Depends(fetch_rate_limit)
):
    l3_list = [item.lower().strip() for item in l3 if item]

    if not l3_list:
        raise HTTPException(status_code=400, detail="l3 parameter is required")

    try:
        response = bestSellerService.fetch_by_l3(client, l3_list, size)

        if not response.get("hits"):
            raise HTTPException(
                status_code=404,
                detail=f"No products found for category_l3: {', '.join(l3_list)}"
            )

        return {
            "count": len(response["hits"]),
            "data": response["hits"]
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# FETCH BY SKUID
from fastapi import Query, HTTPException

@router.get("/skuid")
def fetch_bs_product_id(
    client: str,
    skuid: list[str] = Query(...),
    _: None = Depends(fetch_rate_limit)
):
    skuid_list = [item.strip() for item in skuid if item]

    if not skuid_list:
        raise HTTPException(status_code=400, detail="skuid parameter is required")

    try:
        response = bestSellerService.fetch_by_skuid(client, skuid_list)  # ✅ correct

        if not response.get("hits"):
            raise HTTPException(
                status_code=404,
                detail=f"No products found for skuid: {', '.join(skuid_list)}"
            )

        return {
            "count": len(response["hits"]),
            "data": response["hits"]
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))