from fastapi import APIRouter
from .api import trending,bestseller
from .api import popular_category,popular_brand

router=APIRouter(prefix="/recommendations", tags=["Recommendations"])


router.include_router(
    trending.router,
    prefix="/trending",
    tags=["Trending"]
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

# Popular brand 
router.include_router(
    popular_brand.router,
    prefix="/popular_brand",
    tags=["PopularBrand"]
)

