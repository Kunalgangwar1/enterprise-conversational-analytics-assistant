"""FastAPI application factory and entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

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
from app.knowledge_catalog.agent import KnowledgeCatalogAgent
from app.semantica.agent import SemanticaAgent
from app.sessions.factory import build_session_store
from app.sessions.service import SessionService
from app.sessions.store import SessionStore
from app.sql_results.service import SQLExecutionService


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
) -> FastAPI:
    """Create and configure the FastAPI application."""
    resolved_settings = settings or get_settings()
    resolved_session_store = session_store or build_session_store(resolved_settings)

    @asynccontextmanager
    async def lifespan(_application: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            resolved_session_store.close()

    application = FastAPI(
        title=resolved_settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    authorization_service = AuthorizationService()
    application.state.authorization_service = authorization_service
    application.state.authentication_backend = (
        authentication_backend
        or build_authentication_backend(
            resolved_settings,
            authorization_service,
        )
    )
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
    return application


app = create_app()
