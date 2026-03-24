from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.exceptions import AppError
from app.models import ErrorDetail
from app.routers.auth import router as auth_router

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "environment": settings.app_env}


app.include_router(auth_router, prefix="/api/v1")


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    body = {
        "success": False,
        "message": exc.message,
        "data": None,
        "error": ErrorDetail(code=exc.code, message=exc.message, details=exc.details).model_dump(),
    }
    return JSONResponse(status_code=exc.status_code, content=body)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    body = {
        "success": False,
        "message": "Validation failed",
        "data": None,
        "error": ErrorDetail(code="VALIDATION_ERROR", message="Validation failed", details=exc.errors()).model_dump(),
    }
    return JSONResponse(status_code=422, content=body)


@app.exception_handler(Exception)
async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    body = {
        "success": False,
        "message": "Internal server error",
        "data": None,
        "error": ErrorDetail(code="INTERNAL_SERVER_ERROR", message="Internal server error", details={"reason": str(exc)}).model_dump(),
    }
    return JSONResponse(status_code=500, content=body)
