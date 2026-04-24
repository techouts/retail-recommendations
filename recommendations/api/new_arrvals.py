from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List
from ..services.new_arravls import NewArrivalsService

from recommendations.security import fetch_rate_limit

router = APIRouter()
newArrivalsService = NewArrivalsService()


# -------------------- TRAIN NEW ARRIVALS --------------------
@router.post("/train")
def new_arrivals(payload: dict):

    client = payload.get("client")
    settings = payload.get("settings", {})

    if not client:
        raise HTTPException(status_code=400, detail="client is required")

    try:
        return newArrivalsService.train_new_arrivals(settings, client)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -------------------- FETCH ALL --------------------
@router.get("/all")
def fetch_all_new_arrivals(
    client: str,
    size: int = 20,
    _: None = Depends(fetch_rate_limit)
):

    try:
        return newArrivalsService.fetch_all(client, size)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -------------------- FETCH BY L3 --------------------
@router.get("/label3")
def fetch_na_label3(
    client: str,
    l3: List[str] = Query(...),
    size: int = 100,
    _: None = Depends(fetch_rate_limit)
):
    l3_list = [item.lower().strip() for item in l3 if item]

    if not l3_list:
        raise HTTPException(status_code=400, detail="l3 parameter is required")

    try:
        response = newArrivalsService.fetch_by_l3(client, l3_list, size)

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


# -------------------- FETCH BY SKUID --------------------
@router.get("/skuid")
def fetch_na_product_id(
    client: str,
    skuid: List[str] = Query(...),
    _: None = Depends(fetch_rate_limit)
):
    skuid_list = [item.strip() for item in skuid if item]

    if not skuid_list:
        raise HTTPException(status_code=400, detail="skuid parameter is required")

    try:
        response = newArrivalsService.fetch_by_skuid(client, skuid_list)

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