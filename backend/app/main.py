"""FastAPI application factory and entry point."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_api_error_handlers
from app.api.router import api_router
from app.auth.authorization import AuthorizationService
from app.auth.backend import AuthenticationBackend, build_authentication_backend
from app.chat.orchestrator import ChatOrchestrator
from app.core.chat_modes import chat_mode_registry
from app.core.config import Settings, get_settings
from app.dashboards.service import DashboardService
from app.data_discovery.search import DataDiscoveryService
from app.data_quality.agent import DataQualityAgent
from app.db.session import engine as database_engine
from app.knowledge_catalog.agent import KnowledgeCatalogAgent
from app.observability import initialize_observability
from app.observability.middleware import ObservabilityMiddleware
from app.reliability.readiness import ReadinessProbe, ReadinessService
from app.reliability.resources import close_provider_resources
from app.security.headers import SecurityHeadersMiddleware
from app.security.rate_limit import RateLimiter, build_rate_limiter
from app.security.request_limits import RequestBodyLimitMiddleware
from app.security.trusted_host import HealthProbeTrustedHostMiddleware
from app.semantica.agent import SemanticaAgent
from app.sessions.factory import build_session_store
from app.sessions.service import SessionService
from app.sessions.store import SessionStore
from app.sql_results.service import SQLExecutionService

logger = logging.getLogger(__name__)


def _database_readiness_check() -> None:
    with database_engine.connect() as connection:
        connection.exec_driver_sql("SELECT 1")


def _close_safely(resource: object | None, operation: str) -> None:
    if resource is None:
        return
    close = getattr(resource, "close", None)
    if close is None:
        return
    try:
        close()
    except Exception:
        logger.warning("Application resource shutdown failed", extra={"operation": operation})


def _dispose_database_safely() -> None:
    try:
        database_engine.dispose()
    except Exception:
        logger.warning("Application resource shutdown failed", extra={"operation": "database"})


def create_app(
    settings: Settings | None = None,
    session_store: SessionStore | None = None,
    sql_execution_service: SQLExecutionService | None = None,
    knowledge_catalog_agent: KnowledgeCatalogAgent | None = None,
    data_discovery_service: DataDiscoveryService | None = None,
    data_quality_agent: DataQualityAgent | None = None,
    semantica_agent: SemanticaAgent | None = None,
    chat_orchestrator: ChatOrchestrator | None = None,
    dashboard_service: DashboardService | None = None,
    authentication_backend: AuthenticationBackend | None = None,
    rate_limiter: RateLimiter | None = None,
    readiness_service: ReadinessService | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application."""
    resolved_settings = settings or get_settings()
    resolved_session_store = session_store or build_session_store(resolved_settings)
    resolved_rate_limiter = rate_limiter or build_rate_limiter(resolved_settings)
    observability = initialize_observability(resolved_settings)
    if readiness_service is None:
        readiness_probes = [ReadinessProbe("database", _database_readiness_check)]
        session_readiness = getattr(resolved_session_store, "check_readiness", None)
        if session_readiness is not None:
            readiness_probes.append(ReadinessProbe("redis_session", session_readiness))
        limiter_readiness = getattr(resolved_rate_limiter, "check_readiness", None)
        if limiter_readiness is not None:
            readiness_probes.append(ReadinessProbe("redis_rate_limit", limiter_readiness))
        readiness_service = ReadinessService(readiness_probes)

    @asynccontextmanager
    async def lifespan(_application: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            _close_safely(_application.state.sql_execution_service, "sql_execution")
            _close_safely(_application.state.dashboard_service, "dashboard")
            _close_safely(resolved_rate_limiter, "rate_limit")
            _close_safely(resolved_session_store, "session")
            close_provider_resources()
            _dispose_database_safely()
            observability.shutdown()

    application = FastAPI(
        title=resolved_settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if resolved_settings.api_docs_enabled else None,
        redoc_url="/redoc" if resolved_settings.api_docs_enabled else None,
        openapi_url="/openapi.json" if resolved_settings.api_docs_enabled else None,
    )
    application.state.settings = resolved_settings
    application.state.observability = observability
    authorization_service = AuthorizationService()
    application.state.authorization_service = authorization_service
    application.state.authentication_backend = (
        authentication_backend
        or build_authentication_backend(
            resolved_settings,
            authorization_service,
        )
    )
    application.state.rate_limiter = resolved_rate_limiter
    application.state.readiness_service = readiness_service
    application.state.session_service = SessionService(
        resolved_session_store,
        chat_mode_registry,
    )
    application.state.sql_execution_service = sql_execution_service
    application.state.knowledge_catalog_agent = knowledge_catalog_agent
    application.state.data_discovery_service = data_discovery_service
    application.state.data_quality_agent = data_quality_agent
    application.state.semantica_agent = semantica_agent
    application.state.chat_orchestrator = chat_orchestrator
    application.state.dashboard_service = dashboard_service
    application.include_router(api_router)
    register_api_error_handlers(application)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_allowed_origins,
        allow_credentials=resolved_settings.cors_allow_credentials,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=[
            "Accept",
            "Authorization",
            "Content-Type",
            resolved_settings.tab_id_header,
        ],
        expose_headers=["Retry-After", "X-Request-Id"],
    )
    application.add_middleware(
        HealthProbeTrustedHostMiddleware,
        allowed_hosts=resolved_settings.allowed_hosts,
    )
    application.add_middleware(
        RequestBodyLimitMiddleware,
        max_body_bytes=resolved_settings.request_max_body_bytes,
    )
    application.add_middleware(
        SecurityHeadersMiddleware,
        enabled=resolved_settings.security_headers_enabled,
        hsts_enabled=resolved_settings.hsts_enabled,
        hsts_max_age_seconds=resolved_settings.hsts_max_age_seconds,
    )
    application.add_middleware(ObservabilityMiddleware, runtime=observability)
    return application


app = create_app()
