from fastapi import APIRouter, HTTPException
from ..services.dealofday_service import DealOfDayService
from typing import List
from fastapi import Query, Depends
from ..schemas.schema import TrainDodRequest
from recommendations.security import fetch_rate_limit

router=APIRouter()
dealOfDayService=DealOfDayService()

@router.post("/train")
def train_dealofday(payload: TrainDodRequest):

    client = payload.Client
    settings = payload.settings
    levels = payload.levels
    
    print("Settings : ",settings)
    
    result = dealOfDayService.trainDealOfDay(settings,client,levels)
    
    return result

@router.get("/fetch/l1")
def fetch_dod_l1(
    l1: List[str] = Query(...),
    size: int = 5,
    index_name: str = Query(...),
    _: None = Depends(fetch_rate_limit)
    ):
    try:
        title_case_list = [item.lower() for item in l1 if item]
        if not title_case_list:
            raise HTTPException(status_code=400, detail="l1 parameter is required")

        response = dealOfDayService.dealoftheday_fetch_l1(
            index_name,
            title_case_list,
            size
        )
        return response
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    
@router.get("/fetch/l2")
def fetch_dod_l2(
    l2: List[str] = Query(...),
    size: int = 5,
    index_name: str = Query(...),
    _: None = Depends(fetch_rate_limit)
    ):
    try:
        title_case_list = [item for item in l2 if item]
        if not title_case_list:
            raise HTTPException(status_code=400, detail="l2 parameter is required")

        response = dealOfDayService.dealoftheday_fetch_l2(
            index_name,
            title_case_list,
            size,
        )
        return response
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@router.get("/fetch/l3")
def fetch_dod_l3(
    l3: List[str] = Query(...),
    size: int =5,
    index_name: str = Query(...),
    _: None = Depends(fetch_rate_limit)
):
    try:
        title_case_list = [item for item in l3 if item]
        if not title_case_list:
            raise HTTPException(status_code=400, detail="l3 parameter is required")

        response = dealOfDayService.dealoftheday_fetch_l3(
            index_name,
            title_case_list,
            size,
        )
        return response
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fetch_all")
def fetch_dod(
    size: int =5,
    index_name: str = Query(...),
    _: None = Depends(fetch_rate_limit)
):
    try:
        response = dealOfDayService.dealoftheday_fetch_all(
            index_name=index_name,
            size=size
        )
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
