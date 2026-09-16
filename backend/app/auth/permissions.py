"""Stable permission identifiers used by backend authorization checks."""

from enum import StrEnum


class Permission(StrEnum):
    CHAT_USE = "chat.use"
    DASHBOARD_READ = "dashboard.read"
    DATA_DISCOVERY_READ = "data_discovery.read"
    KNOWLEDGE_CATALOG_READ = "knowledge_catalog.read"
    DATA_QUALITY_READ = "data_quality.read"
    SEMANTICA_READ = "semantica.read"
    SQL_GENERATE = "sql.generate"
    SQL_EXECUTE = "sql.execute"
    SQL_ADVANCED = "sql.advanced"
    FORECAST_RUN = "forecast.run"
    GROUP_ACCESS_READ_SELF = "group_access.read_self"
    ADMIN_AUTHORIZATION_READ = "admin.authorization.read"
