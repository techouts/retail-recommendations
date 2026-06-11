from fastapi import APIRouter
from .api import trending,bestseller
from .api import popular_category
from .api import trending
from .api import dealofday , fbt , popular_brands,new_arrivals
from .api import s3_api


router=APIRouter(prefix="/recommendations", tags=["Recommendations"])


router.include_router(
    trending.router,
    prefix="/trending",
    tags=["Trending"]
)

router.include_router(
    dealofday.router,
    prefix="/dealofday",
    tags=["Dealofday"]
)

# Bestseller
router.include_router(
    bestseller.router,
    prefix="/bestseller", 
    tags=["BestSeller"]
)

# Popular Category 
router.include_router(
    popular_category.router,
    prefix="/popular_category",
    tags=["PopularCategory"]
)

router.include_router(
    fbt.router,
    prefix="/fbt",
    tags=["fbt"]
)

router.include_router(
    popular_brands.router,
    prefix="/popular_brands",
    tags=["popular brands"]
)

router.include_router(
    s3_api.router,
    prefix="/s3",
    tags=["s3 data"]
)

router.include_router(
    new_arrivals.router,
    prefix="/new_arrivals",
    tags=['new_arrivals']
)