from fastapi import APIRouter
from .api import trending

router=APIRouter(prefix="/recommendations", tags=["Recommendations"])


router.include_router(
    trending.router,
    prefix="/trending",
    tags=["Trending"]
)




router.include_router()