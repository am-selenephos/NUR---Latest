import logging
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.health import router as health_router
from app.api.v1.auth import router as auth_router
from app.core.config import get_settings
from app.core.logging import configure_logging, log, request_id_var
from app.services.password_delivery import build_password_reset_delivery

logger = logging.getLogger("nur.http")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Correlation ID + structured access log (bodies are never logged) + metrics."""

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        token = request_id_var.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        route = request.scope.get("route")
        route_path = getattr(route, "path", "unmatched")
        request.app.state.request_counters[(request.method, route_path, response.status_code)] += 1
        response.headers["x-request-id"] = rid
        log(logger, "request", method=request.method, path=request.url.path,
            status=response.status_code)
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("x-content-type-options", "nosniff")
        response.headers.setdefault("x-frame-options", "DENY")
        response.headers.setdefault("referrer-policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("permissions-policy", "camera=(), microphone=(), geolocation=(), payment=()")
        response.headers.setdefault("cross-origin-resource-policy", "same-origin")
        response.headers.setdefault("x-permitted-cross-domain-policies", "none")
        response.headers.setdefault("content-security-policy", "default-src 'none'")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("cache-control", "no-store")
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    app.state.ready = True
    app.state.redis = Redis.from_url(s.redis_url, decode_responses=True)
    # Bind the Agency Plane tool handlers. Without this the registry is empty in
    # the API process, so `GET /agentic/tools` reported every tool as
    # `bound: false` — describing the product as less capable than it is, from
    # the one surface an owner uses to check what NUR can do.
    from app.agentic.handlers import bind_all_handlers

    bind_all_handlers()
    try:
        yield
    finally:
        # Graceful shutdown. First stop reporting ready so a load balancer routes
        # new traffic away from this instance, then release both external
        # resources. Each release is guarded so a failure in one still runs the
        # next — a leaked connection pool must not survive because Redis close
        # raised.
        app.state.ready = False
        from app.db.session import dispose_engine
        try:
            await app.state.redis.aclose()
        finally:
            await dispose_engine()


def create_app() -> FastAPI:
    configure_logging()
    s = get_settings()
    app = FastAPI(title="NUR API", version="0.1.0", lifespan=lifespan,
                  docs_url="/docs" if s.app_env != "production" else None)
    app.state.request_counters = defaultdict(int)
    app.state.domain_counters = defaultdict(int)
    app.state.password_reset_delivery = build_password_reset_delivery(s)

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "content-type",
            "idempotency-key",
            "x-csrf-token",
            "x-request-id",
        ],
    )

    app.include_router(health_router)
    app.include_router(auth_router, prefix="/api/v1")
    from app.api.v1.password_recovery import router as password_recovery_router
    from app.api.v1.cognition import content as content_router, router as cognition_router
    from app.api.v1.community import router as community_router
    from app.api.v1.community_moderation import router as community_moderation_router
    from app.api.v1.community_social import router as community_social_router
    from app.api.v1.consultations import router as consultations_router
    from app.api.v1.hypotheses import router as hypotheses_router
    from app.api.v1.insights import router as insights_router
    from app.api.v1.orbits import router as orbits_router
    from app.api.v1.capsules import router as capsules_router
    from app.api.v1.profile import router as profile_router
    from app.api.v1.product_surfaces import router as product_surfaces_router
    from app.api.v1.glow import router as glow_router
    from app.api.v1.group_research import router as group_research_router
    from app.api.v1.feasibility import router as feasibility_router
    from app.api.v1.living import router as living_router
    from app.api.v1.map import router as map_router
    from app.api.v1.memory import router as memory_router
    from app.api.v1.notifications import router as notifications_router
    from app.api.v1.projects import router as projects_router
    from app.api.v1.ops import router as ops_router
    from app.api.v1.translations import router as translations_router
    from app.learning.routes import router as teach_nur_router
    from app.intelligence.routes import router as intelligence_router
    from app.api.v1.agentic import router as agentic_router
    from app.api.v1.timeline import router as timeline_router
    from app.api.v1.universe import router as universe_router
    from app.omega.routes import router as omega_router
    from app.billing.routes import router as billing_router
    app.include_router(cognition_router, prefix="/api/v1")
    app.include_router(password_recovery_router, prefix="/api/v1")
    app.include_router(community_router, prefix="/api/v1")
    app.include_router(community_social_router, prefix="/api/v1")
    app.include_router(community_moderation_router, prefix="/api/v1")
    app.include_router(consultations_router, prefix="/api/v1")
    app.include_router(content_router, prefix="/api/v1")
    app.include_router(hypotheses_router, prefix="/api/v1")
    app.include_router(insights_router, prefix="/api/v1")
    app.include_router(orbits_router, prefix="/api/v1")
    app.include_router(capsules_router, prefix="/api/v1")
    app.include_router(profile_router, prefix="/api/v1")
    app.include_router(product_surfaces_router, prefix="/api/v1")
    app.include_router(glow_router, prefix="/api/v1")
    app.include_router(group_research_router, prefix="/api/v1")
    app.include_router(feasibility_router, prefix="/api/v1")
    app.include_router(living_router, prefix="/api/v1")
    app.include_router(map_router, prefix="/api/v1")
    app.include_router(memory_router, prefix="/api/v1")
    app.include_router(teach_nur_router, prefix="/api/v1")
    app.include_router(intelligence_router, prefix="/api/v1")
    app.include_router(notifications_router, prefix="/api/v1")
    app.include_router(projects_router, prefix="/api/v1")
    app.include_router(ops_router, prefix="/api/v1")
    app.include_router(translations_router, prefix="/api/v1")
    app.include_router(timeline_router, prefix="/api/v1")
    app.include_router(agentic_router, prefix="/api/v1")
    app.include_router(universe_router, prefix="/api/v1")
    app.include_router(omega_router, prefix="/api/v1")
    app.include_router(billing_router, prefix="/api/v1")
    return app


app = create_app()
