"""Typed loading for local functionality flags."""

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "functionality_flags.yaml"


class FeatureFlagConfigurationError(RuntimeError):
    """Raised when the feature flag file cannot be loaded or validated."""


class _FeatureFlagModel(BaseModel):
    """Strict, immutable base model for feature flag configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class UIFeatureFlags(_FeatureFlagModel):
    """Feature visibility settings safe to expose to the frontend."""

    follow_up_questions_show: bool
    context_button: bool
    chat_latency_badge: bool
    knowledge_graph_tools_show: bool


class ToolFeatureFlags(_FeatureFlagModel):
    """Specialist tool availability settings safe to expose to clients."""

    sql: bool
    forecasting: bool
    group_access: bool
    data_discovery: bool
    knowledge_catalog: bool
    semantica: bool
    data_quality: bool


class RetrievalFeatureFlags(_FeatureFlagModel):
    """Retrieval strategy rollout settings."""

    hierarchical_rag: bool
    vector_rag: bool


class ReasoningFeatureFlags(_FeatureFlagModel):
    """Advanced reasoning rollout settings."""

    deep_agent_single_intent_enabled: bool
    deep_agent_min_confidence: float = Field(ge=0.0, le=1.0)
    deep_agent_eligible_routes: list[str]
    deep_agent_max_subtasks: int = Field(ge=1)
    nlp2sql_multihop_enabled: bool
    nlp2sql_multihop_max_hops: int = Field(ge=1)
    nlp2sql_multihop_max_rows_per_hop: int = Field(ge=1)
    nlp2sql_multihop_total_row_budget: int = Field(ge=1)
    nlp2sql_multihop_total_timeout_seconds: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_multihop_row_budget(self) -> "ReasoningFeatureFlags":
        if self.nlp2sql_multihop_total_row_budget < self.nlp2sql_multihop_max_rows_per_hop:
            raise ValueError(
                "NLP2SQL multihop total row budget must be at least the per-hop row limit"
            )
        return self


class ObservabilityFeatureFlags(_FeatureFlagModel):
    """Observability integration rollout settings."""

    otel_enabled: bool
    langfuse_enabled: bool
    mlflow_enabled: bool
    agentops_enabled: bool


class FunctionalityFlags(_FeatureFlagModel):
    """Complete validated functionality flag configuration."""

    ui: UIFeatureFlags
    tools: ToolFeatureFlags
    retrieval: RetrievalFeatureFlags
    reasoning: ReasoningFeatureFlags
    observability: ObservabilityFeatureFlags


def load_feature_flags(config_path: Path) -> FunctionalityFlags:
    """Load and validate feature flags from a YAML file."""
    try:
        raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FeatureFlagConfigurationError(
            f"Feature flag configuration file not found: {config_path}"
        ) from exc
    except OSError as exc:
        raise FeatureFlagConfigurationError(
            f"Unable to read feature flag configuration file: {config_path}"
        ) from exc
    except yaml.YAMLError as exc:
        raise FeatureFlagConfigurationError(
            f"Malformed YAML in feature flag configuration file: {config_path}"
        ) from exc

    try:
        return FunctionalityFlags.model_validate(raw_config)
    except ValidationError as exc:
        raise FeatureFlagConfigurationError(
            f"Invalid feature flag configuration in {config_path}: {exc}"
        ) from exc


@lru_cache(maxsize=1)
def get_feature_flags() -> FunctionalityFlags:
    """Return the cached, validated default functionality flags."""
    return load_feature_flags(_DEFAULT_CONFIG_PATH)
