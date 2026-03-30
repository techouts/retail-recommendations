from fastapi import APIRouter, HTTPException
from ..schemas.schema import TrainDealOfDayRequest
from ..services.dealofday_service import DealOfDayService

router=APIRouter()
service = DealOfDayService()

# @router.post("/train")
# def train_dealofday(payload: TrainDealOfDayRequest):
#     try:
#     #   pass
#         result = service.trainDealOfDay(
#             payload.settings,
#             payload.client,
#             payload.levels
#         )
#         return result
#     except Exception as e:
#         raise HTTPException(status_code=401)
#     #  detail=str(e)