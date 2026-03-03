from __future__ import annotations

import time
import uuid

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.domain.models import APIError
from app.http.routes_admin import router as admin_router
from app.http.routes_ai import router as ai_router
from app.http.routes_auth import router as auth_router
from app.http.routes_booking import router as booking_router
from app.http.routes_files import router as files_router
from app.http.routes_payments import router as payments_router
from app.http.routes_public import router as public_router
from app.security.rate_limit import limiter
from app.settings import settings
from app.http.routes_route import router as route_router
from app.http.routes_route_day import router as route_day_router
from app.api.client_progress import router as client_progress_router
from app.api.client_diagnostic import router as client_diagnostic_router

app = FastAPI(title=settings.app_name)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

structlog.configure(processors=[structlog.processors.JSONRenderer()])
logger = structlog.get_logger()


@app.middleware("http")
async def correlation_middleware(request: Request, call_next):
    correlation_id = request.headers.get("x-correlation-id", str(uuid.uuid4()))
    request.state.correlation_id = correlation_id
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["x-correlation-id"] = correlation_id
    logger.info(
        "request",
        correlation_id=correlation_id,
        path=request.url.path,
        method=request.method,
        duration_ms=(time.perf_counter() - start) * 1000,
    )
    return response


@app.exception_handler(APIError)
async def api_error_handler(_request: Request, exc: APIError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
    )


@app.exception_handler(RateLimitExceeded)
async def rl_handler(_request: Request, _exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"error": {"code": "RATE_LIMIT", "message": "Too many requests", "details": {}}},
    )


@app.get("/health")
def health():
    return {"data": {"status": "ok"}}


app.include_router(public_router)
app.include_router(auth_router)
app.include_router(ai_router)
app.include_router(booking_router)
app.include_router(payments_router)
app.include_router(admin_router)
app.include_router(files_router)
app.include_router(route_router)
app.include_router(route_day_router)
app.include_router(client_progress_router)
app.include_router(client_diagnostic_router)