from fastapi import APIRouter
from .api import trending, fbt

router=APIRouter(prefix="/recommendations", tags=["Recommendations"])


router.include_router(
    trending.router,
    prefix="/trending",
    tags=["Trending"]
)



# router.include_router(
#     fbt.router,
#     prefix="/fbt",
#     tags=["Frequentlty Brought Together"]
# )