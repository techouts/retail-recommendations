from fastapi import (APIRouter,HTTPException,Query,Depends)
from  ..services.new_arrivals_services import ( NewArrivalsService)
from ..schemas.schema import (TrainNewArrivalsRequest)
from recommendations.security import (fetch_rate_limit)

router = APIRouter()
service = NewArrivalsService()

# Train New Arrivals

@router.post("/train")
def train_new_arrivals(
    payload: TrainNewArrivalsRequest
):

    try:

        result = service.trainNewArrivals(
            payload.settings,
            payload.Client
        )

        return result

    except Exception as e:

        raise HTTPException(
            status_code=401,
            detail=str(e)
        )



# Fetch New Arrivals

@router.get("/fetch")
def fetch_new_arrivals(
    client: str = Query(...),

    category_l1: str | None = Query(default=None),
    category_l2: str | None = Query(default=None),
    category_l3: str | None = Query(default=None),
    category_l4: str | None = Query(default=None),

    brand: str | None = Query(default=None),

    limit: int = Query(
        default=20,
        ge=1,
        le=100
    ),

    _: None = Depends(fetch_rate_limit)
):

    try:

        filters = {
            k: v for k, v in {

                "category_l1": category_l1,
                "category_l2": category_l2,
                "category_l3": category_l3,
                "category_l4": category_l4,
                "brand": brand,

            }.items() if v is not None
        }

        result = service.getNewArrivals(
            client,
            filters=filters,
            limit=limit
        )

        return result

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )