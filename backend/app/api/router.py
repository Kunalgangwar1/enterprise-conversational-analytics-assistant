"""Central composition point for all currently implemented API routers."""

from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.chat import router as chat_router
from app.api.routes.chat_modes import router as chat_modes_router
from app.api.routes.dashboards import router as dashboards_router
from app.api.routes.data_discovery import router as data_discovery_router
from app.api.routes.data_quality import router as data_quality_router
from app.api.routes.feature_flags import router as feature_flags_router
from app.api.routes.health import router as health_router
from app.api.routes.knowledge_catalog import router as knowledge_catalog_router
from app.api.routes.semantica import router as semantica_router
from app.api.routes.sessions import router as sessions_router
from app.api.routes.sql_execution import router as sql_execution_router

api_router = APIRouter()
versioned_api_router = APIRouter(prefix="/api")
versioned_api_router.include_router(health_router)
versioned_api_router.include_router(auth_router)
versioned_api_router.include_router(feature_flags_router)
versioned_api_router.include_router(chat_modes_router)
versioned_api_router.include_router(knowledge_catalog_router)
versioned_api_router.include_router(data_discovery_router)
versioned_api_router.include_router(data_quality_router)
versioned_api_router.include_router(semantica_router)
versioned_api_router.include_router(dashboards_router)

api_router.include_router(versioned_api_router)
api_router.include_router(sessions_router)
api_router.include_router(sql_execution_router)
api_router.include_router(chat_router)
