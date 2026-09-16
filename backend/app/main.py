"""FastAPI application factory and entry point."""

from fastapi import FastAPI

from app.api.errors import register_api_error_handlers
from app.api.router import api_router
from app.chat.orchestrator import ChatOrchestrator
from app.core.chat_modes import chat_mode_registry
from app.core.config import Settings, get_settings
from app.data_discovery.search import DataDiscoveryService
from app.data_quality.agent import DataQualityAgent
from app.knowledge_catalog.agent import KnowledgeCatalogAgent
from app.semantica.agent import SemanticaAgent
from app.sessions.json_store import JsonFileSessionStore
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
) -> FastAPI:
    """Create and configure the FastAPI application."""
    resolved_settings = settings or get_settings()
    resolved_session_store = session_store or JsonFileSessionStore(
        resolved_settings.artifacts_output_dir / "sessions"
    )
    application = FastAPI(
        title=resolved_settings.app_name,
        version="0.1.0",
    )
    application.state.settings = resolved_settings
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
    application.include_router(api_router)
    register_api_error_handlers(application)
    return application


app = create_app()
