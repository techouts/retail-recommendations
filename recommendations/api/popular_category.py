from ..services.popular_category_service import PopularCategoryService
from fastapi import APIRouter, HTTPException, Query
from typing import List
from fastapi import APIRouter, Depends


router = APIRouter()
bestSellerService = PopularCategoryService()

@router.post("/train")
def train_popular_category(payload: dict):

    client = payload.get("client")
    settings = payload.get("settings", {})

    if not client:
        raise HTTPException(status_code=400, detail="client is required")

    try:
        return bestSellerService.train_popular_category(
            settings,
            client   
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@router.get("/fetch")
def fetch_all_categories(
    client: str,   
    limit: int = 10,
    
    
):
    try:
        return bestSellerService.fetch_all_categories(client, limit)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@router.get("/category")
def fetch_categories(
    client: str = Query(...),
    category_l1: str | None = Query(default=None),
    category_l2: str | None = Query(default=None),
    category_l3: str | None = Query(default=None),
    category_l4: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100)
):
    try:
        filters = {
            k: v for k, v in {
                "category_l1": category_l1,
                "category_l2": category_l2,
                "category_l3": category_l3,
                "category_l4": category_l4,
            }.items() if v is not None
        }

        return bestSellerService.fetch_categories_by_filters(
            client=client,
            filters=filters,
            limit=limit
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    


