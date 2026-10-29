from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.auth import ApiError
from app.config import settings
from app.document_routes import router as document_router
from app.fhir_routes import router as fhir_router
from app.intelligence_routes import router as intelligence_router
from app.message_routes import router as message_router
from app.platform_routes import router as platform_router
from app.routes import router
from app.scheduling_routes import router as scheduling_router
from app.tenancy_routes import router as tenancy_router
from app.trends_routes import router as trends_router
from app.consultation_routes import router as consultation_router
from app.clinical_ai_routes import router as clinical_ai_router
from app.demo_routes import router as demo_router
from app.timeline_routes import router as timeline_router
from app.workboard_routes import router as workboard_router
from app.telehealth_workflow_routes import router as telehealth_workflow_router
from app.ai_copilot_routes import router as ai_copilot_router
from app.rcm_routes import router as rcm_router
from app.subscription_routes import router as subscription_router
from app.fhir_r4_routes import router as fhir_r4_router
from app.interop_routes import router as interop_router
from app.ops_routes import router as ops_router
from app.hypercare_routes import router as hypercare_router
from app.agent_routes import router as agent_router
from app.security_hardening import RateLimitMiddleware, SecurityHeadersMiddleware

# Register FHIR / Extraction / RCM / Interop / Ops / Hypercare / Agent ORM tables on Base.metadata for create_all in tests.
import app.fhir_models  # noqa: F401
import app.rcm_models  # noqa: F401
import app.interop_models  # noqa: F401
import app.ops_models  # noqa: F401
import app.hypercare_models  # noqa: F401
import app.agent_models  # noqa: F401

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("healthomatix")

app = FastAPI(
    title="Healthomatix API",
    version="1.8.0",
    description=(
        "Tenant-aware clinic APIs. Scheduling is disabled unless explicitly "
        "enabled for an approved synthetic demonstration."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-Request-Id",
        "X-Demo-User",
        "X-Demo-Secret",
    ],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)


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
app.include_router(document_router)
app.include_router(fhir_router)
app.include_router(intelligence_router)
app.include_router(trends_router)
app.include_router(consultation_router)
app.include_router(clinical_ai_router)
app.include_router(message_router)
app.include_router(scheduling_router)
app.include_router(platform_router)
app.include_router(demo_router)
app.include_router(timeline_router)
app.include_router(workboard_router)
app.include_router(telehealth_workflow_router)
app.include_router(ai_copilot_router)
app.include_router(rcm_router)
app.include_router(subscription_router)
app.include_router(fhir_r4_router)
app.include_router(interop_router)
app.include_router(ops_router)
app.include_router(hypercare_router)
app.include_router(agent_router)
