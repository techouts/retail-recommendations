from fastapi import FastAPI, Request
from recommendations.router import router
from fastapi.responses import JSONResponse
from recommendations.exceptions.exceptions import AppException

app = FastAPI()
from fastapi import FastAPI, Request
from recommendations.router import router
from fastapi.responses import JSONResponse
from recommendations.exceptions.exceptions import AppException

app = FastAPI()

# ✅ ADD THIS LINE (VERY IMPORTANT)
app.include_router(router)


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": exc.status_code,
            "success": False,
            "error": exc.message
        }
    )

# @app.on_event("startup")
# def on_startup():
#     Base.metadata.create_all(bind=engine)

@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status":exc.status_code,
            "success": False,
            "error": exc.message
        }
    )


