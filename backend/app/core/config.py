"""Environment-backed application configuration."""

from functools import lru_cache
from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, PostgresDsn, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.security.production_policy import validate_production_security

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Validated settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=_REPOSITORY_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Enterprise Conversational Analytics Assistant"
    app_env: str = "development"
    auth_mode: Literal["development", "oidc"] = "development"
    auth_dev_subject: str = "dev-user"
    auth_dev_email: str | None = "developer@example.invalid"
    auth_dev_display_name: str | None = "Local Developer"
    auth_dev_roles: str = "analyst"
    auth_oidc_issuer: str | None = None
    auth_oidc_audience: str | None = None
    auth_oidc_client_id: str | None = None
    auth_oidc_client_id_claim: str = Field(default="aud", min_length=1, max_length=128)
    auth_oidc_jwks_url: str | None = None
    auth_oidc_algorithms: str = "RS256"
    auth_oidc_roles_claim: str = "roles"
    auth_oidc_groups_claim: str = "groups"
    auth_oidc_scope_claim: str = "scope"
    auth_oidc_email_claim: str = "email"
    auth_oidc_display_name_claim: str = "name"
    auth_oidc_token_use: str | None = None
    auth_group_role_mapping: dict[str, Literal["viewer", "analyst", "admin"]] = Field(
        default_factory=dict
    )
    app_host: str = "127.0.0.1"
    app_port: int = Field(default=8000, ge=1, le=65_535)
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "console"
    observability_enabled: bool = False
    service_name: str = Field(
        default="enterprise-conversational-analytics-backend",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9._-]+$",
    )
    service_version: str = Field(default="0.1.0", min_length=1, max_length=64)
    otel_exporter_otlp_endpoint: str | None = None
    otel_exporter_otlp_protocol: Literal["http/protobuf"] = "http/protobuf"
    otel_trace_sample_ratio: float = Field(default=0.10, ge=0, le=1)
    otel_export_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    metrics_enabled: bool = True
    tracing_enabled: bool = True
    cors_allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    cors_allow_credentials: bool = True
    allowed_hosts: list[str] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "testserver"]
    )
    request_max_body_bytes: int = Field(default=65_536, ge=1_024, le=1_048_576)
    security_headers_enabled: bool = True
    hsts_enabled: bool = False
    hsts_max_age_seconds: int = Field(default=31_536_000, ge=1)
    api_docs_enabled: bool = True
    rate_limit_enabled: bool = True
    rate_limit_backend: Literal["memory", "redis"] = "memory"
    rate_limit_requests: int = Field(default=30, ge=1, le=10_000)
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=86_400)
    rate_limit_redis_url: SecretStr | None = None
    rate_limit_redis_key_prefix: str = Field(
        default="eca:rate",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9:_-]+$",
    )
    database_url: PostgresDsn = Field(
        default=PostgresDsn("postgresql+psycopg://postgres@localhost:5432/enterprise_analytics"),
        repr=False,
    )
    test_database_url: PostgresDsn | None = Field(default=None, repr=False)
    query_database_url: PostgresDsn | None = Field(default=None, repr=False)
    query_test_database_url: PostgresDsn | None = Field(default=None, repr=False)
    query_max_rows: int = Field(default=500, ge=1)
    query_timeout_ms: int = Field(default=5_000, ge=1)
    dashboard_top_n: int = Field(default=10, ge=1, le=50)
    eval_random_seed: int = Field(default=42, ge=0)
    sql_result_summary_max_rows: int = Field(default=50, ge=1)
    sql_result_summary_max_chars: int = Field(default=12_000, ge=1)
    knowledge_catalog_dir: Path = _REPOSITORY_ROOT / "backend" / "data" / "knowledge_catalog"
    embedding_provider: str = "gemini"
    gemini_api_key: SecretStr | None = None
    gemini_embedding_model: str = "gemini-embedding-2"
    azure_openai_embedding_deployment: str | None = None
    embedding_dimensions: int | None = Field(default=1_536, ge=1)
    knowledge_hierarchy_max_depth: int = Field(default=4, ge=1, le=20)
    knowledge_hierarchy_max_branches: int = Field(default=3, ge=1, le=20)
    knowledge_hierarchy_min_confidence: float = Field(default=0.60, ge=0, le=1)
    knowledge_catalog_top_k: int = Field(default=6, ge=1, le=50)
    knowledge_chunk_size_chars: int = Field(default=1_200, ge=100)
    knowledge_chunk_overlap_chars: int = Field(default=150, ge=0)
    knowledge_context_max_chars: int = Field(default=12_000, ge=500)
    knowledge_rerank_enabled: bool = False
    data_discovery_top_k: int = Field(default=5, ge=1, le=50)
    data_quality_dir: Path = _REPOSITORY_ROOT / "backend" / "data" / "data_quality"
    data_quality_top_k: int = Field(default=5, ge=1, le=50)
    semantica_chunk_size_chars: int = Field(default=900, ge=1)
    semantica_chunk_overlap_chars: int = Field(default=120, ge=0)
    semantica_seed_top_k: int = Field(default=4, ge=1, le=50)
    semantica_max_hops: int = Field(default=2, ge=0, le=2)
    semantica_max_evidence: int = Field(default=12, ge=1, le=100)
    llm_provider: str = "gemini"
    gemini_llm_model: str = "gemini-3.8-flash"
    azure_openai_endpoint: str | None = None
    azure_openai_api_key: SecretStr | None = None
    azure_openai_deployment: str | None = None
    llm_timeout_seconds: float = Field(default=30.0, gt=0)
    llm_max_retries: int = Field(default=2, ge=0)
    llm_max_output_tokens: int = Field(default=2_000, ge=1)
    intent_router_min_confidence: float = Field(default=0.60, ge=0, le=1)
    nlp2sql_max_domains: int = Field(default=3, ge=1)
    nlp2sql_max_tables: int = Field(default=5, ge=1)
    nlp2sql_accept_score: float = Field(default=0.80, ge=0, le=1)
    nlp2sql_rewrite_score: float = Field(default=0.50, ge=0, le=1)
    nlp2sql_max_rewrites: Literal[1] = 1
    forecast_default_horizon: int = Field(default=3, ge=1)
    forecast_max_horizon: int = Field(default=12, ge=1)
    forecast_min_history_points: int = Field(default=8, ge=4)
    forecast_max_history_points: int = Field(default=120, ge=4)
    forecast_backtest_points: int = Field(default=4, ge=2)
    forecast_moving_average_window: int = Field(default=3, ge=2)
    forecast_interval_z: float = Field(default=1.96, gt=0)
    artifacts_output_dir: Path = _REPOSITORY_ROOT / "backend" / "artifacts"
    session_cookie_name: str = Field(
        default="eca_session_id",
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    session_max_age_seconds: int = Field(default=86_400, ge=1)
    session_cookie_secure: bool = False
    session_store_backend: Literal["json", "redis"] = "json"
    session_redis_url: SecretStr | None = None
    session_redis_key_prefix: str = Field(
        default="eca:session",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9:_-]+$",
    )
    session_redis_max_update_retries: int = Field(default=5, ge=1, le=50)
    tab_id_header: str = Field(
        default="X-Tab-Id",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9-]+$",
    )

    @field_validator(
        "artifacts_output_dir", "knowledge_catalog_dir", "data_quality_dir", mode="before"
    )
    @classmethod
    def resolve_artifacts_output_dir(cls, value: str | Path) -> Path:
        """Resolve relative artifact paths consistently from the repository root."""

        path = Path(value).expanduser()
        return path if path.is_absolute() else _REPOSITORY_ROOT / path

    @field_validator("cors_allowed_origins", "allowed_hosts")
    @classmethod
    def normalize_security_allowlists(cls, values: list[str]) -> list[str]:
        """Normalize exact configured values and reject blank entries."""

        normalized = list(dict.fromkeys(value.strip() for value in values))
        if any(not value for value in normalized):
            raise ValueError("security allowlists cannot contain blank values")
        return normalized

    @field_validator("otel_exporter_otlp_endpoint")
    @classmethod
    def validate_otlp_endpoint(cls, value: str | None) -> str | None:
        """Accept only bounded HTTP(S) collector base URLs without embedded credentials."""

        if value is None or not value.strip():
            return None
        normalized = value.strip().rstrip("/")
        parsed = urlsplit(normalized)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or len(normalized) > 512
        ):
            raise ValueError("OTEL_EXPORTER_OTLP_ENDPOINT must be a safe HTTP(S) base URL")
        return normalized

    @model_validator(mode="after")
    def validate_knowledge_chunk_settings(self) -> Self:
        """Ensure deterministic chunk overlap cannot consume a whole chunk."""

        if self.knowledge_chunk_overlap_chars >= self.knowledge_chunk_size_chars:
            raise ValueError(
                "KNOWLEDGE_CHUNK_OVERLAP_CHARS must be lower than KNOWLEDGE_CHUNK_SIZE_CHARS"
            )
        if self.semantica_chunk_overlap_chars >= self.semantica_chunk_size_chars:
            raise ValueError(
                "SEMANTICA_CHUNK_OVERLAP_CHARS must be lower than SEMANTICA_CHUNK_SIZE_CHARS"
            )
        return self

    @model_validator(mode="after")
    def validate_nlp2sql_score_thresholds(self) -> Self:
        """Keep the rewrite and acceptance bands ordered and non-overlapping."""

        if self.nlp2sql_rewrite_score >= self.nlp2sql_accept_score:
            raise ValueError("NLP2SQL_REWRITE_SCORE must be lower than NLP2SQL_ACCEPT_SCORE")
        return self

    @model_validator(mode="after")
    def validate_forecast_settings(self) -> Self:
        """Keep forecast horizons, history, and holdout budgets internally consistent."""

        if self.forecast_max_horizon < self.forecast_default_horizon:
            raise ValueError("FORECAST_MAX_HORIZON must be at least FORECAST_DEFAULT_HORIZON")
        if self.forecast_max_history_points < self.forecast_min_history_points:
            raise ValueError(
                "FORECAST_MAX_HISTORY_POINTS must be at least FORECAST_MIN_HISTORY_POINTS"
            )
        if self.forecast_backtest_points >= self.forecast_min_history_points:
            raise ValueError(
                "FORECAST_BACKTEST_POINTS must be lower than FORECAST_MIN_HISTORY_POINTS"
            )
        return self

    @model_validator(mode="after")
    def validate_authentication_settings(self) -> Self:
        """Reject unsafe development auth and incomplete OIDC configurations."""

        environment = self.app_env.strip().lower()
        if self.auth_mode == "development" and environment not in {
            "local",
            "development",
            "dev",
            "test",
        }:
            raise ValueError("AUTH_MODE=development is not allowed outside local/test environments")
        if self.auth_mode == "oidc":
            missing = [
                name
                for name, value in {
                    "AUTH_OIDC_ISSUER": self.auth_oidc_issuer,
                    "AUTH_OIDC_JWKS_URL": self.auth_oidc_jwks_url,
                }.items()
                if not value
            ]
            if self.auth_oidc_audience is None and self.auth_oidc_client_id is None:
                missing.append("AUTH_OIDC_AUDIENCE or AUTH_OIDC_CLIENT_ID")
            if missing:
                raise ValueError(f"OIDC authentication requires: {', '.join(missing)}")
        return self

    @model_validator(mode="after")
    def validate_session_store_settings(self) -> Self:
        """Require Redis connection details only when the shared backend is selected."""

        if self.session_store_backend == "redis" and self.session_redis_url is None:
            raise ValueError("SESSION_REDIS_URL is required when SESSION_STORE_BACKEND=redis")
        return self

    @model_validator(mode="after")
    def validate_rate_limit_settings(self) -> Self:
        """Require a dedicated Redis URL only when shared limiting is enabled."""

        if (
            self.rate_limit_enabled
            and self.rate_limit_backend == "redis"
            and self.rate_limit_redis_url is None
        ):
            raise ValueError("RATE_LIMIT_REDIS_URL is required when RATE_LIMIT_BACKEND=redis")
        return self

    @model_validator(mode="after")
    def validate_production_policy(self) -> Self:
        """Apply centralized fail-closed production security policy."""

        validate_production_security(self)
        return self


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance for the running process."""
    return Settings()
