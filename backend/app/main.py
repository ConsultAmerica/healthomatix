from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.auth import ApiError
from app.config import settings
from app.routes import router
from app.scheduling_routes import router as scheduling_router
from app.tenancy_routes import router as tenancy_router
from app.platform_routes import router as platform_router

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("healthomatix")

app = FastAPI(
    title="Healthomatix API",
    version="0.1.0",
    description=(
        "Tenant-aware clinic APIs. Scheduling is disabled unless explicitly "
        "enabled for an approved synthetic demonstration."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Request-Id"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = uuid.uuid4().hex
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    logger.info(
        "request_completed request_id=%s method=%s path=%s status=%s",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
    )
    return response


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, error: ApiError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "")
    return JSONResponse(
        status_code=error.status_code,
        content={
            "error": {
                "code": error.code,
                "message": error.message,
                "request_id": request_id,
            }
        },
        headers={"Cache-Control": "no-store"},
    )


app.include_router(router)
app.include_router(tenancy_router)
app.include_router(scheduling_router)
app.include_router(platform_router)
