"""Composition helpers for deterministic dashboard analytics."""

from app.core.config import Settings
from app.dashboards.repository import DashboardRepository
from app.dashboards.service import DashboardService
from app.db.query.factory import build_query_executor


def build_dashboard_service(settings: Settings) -> DashboardService:
    """Build the dashboard on the existing read-only QueryExecutor boundary."""

    repository = DashboardRepository(
        build_query_executor(settings),
        top_n=settings.dashboard_top_n,
    )
    return DashboardService(repository)
