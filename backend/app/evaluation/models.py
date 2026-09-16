"""Typed evaluation datasets, results, metrics, and regression contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
MetricDirection = Literal["higher_is_better", "lower_is_better"]


class EvaluationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvaluationProfile(StrEnum):
    OFFLINE = "offline"
    INTEGRATION = "integration"
    LIVE = "live"


class CaseStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


class RegressionStatus(StrEnum):
    PASS = "PASS"
    REGRESSION = "REGRESSION"
    IMPROVEMENT = "IMPROVEMENT"
    UNCHANGED = "UNCHANGED"


class BaseEvaluationCase(EvaluationModel):
    case_id: NonBlank
    suite: NonBlank
    description: NonBlank
    question: NonBlank
    tags: tuple[NonBlank, ...] = ()


class RoutingCase(BaseEvaluationCase):
    expected_route: NonBlank


class NLP2SQLCase(BaseEvaluationCase):
    selected_domains: tuple[NonBlank, ...]
    selected_tables: tuple[NonBlank, ...]
    candidate_sql: NonBlank
    reference_sql: NonBlank
    candidate_result: list[dict[str, Any]] = Field(default_factory=list)
    reference_result: list[dict[str, Any]] = Field(default_factory=list)
    order_sensitive: bool = False
    numeric_tolerance: float = Field(default=0.0, ge=0)


class SQLSafetyCase(BaseEvaluationCase):
    sql: NonBlank
    should_accept: bool = False


class DiscoveryCase(BaseEvaluationCase):
    expected_datasets: tuple[NonBlank, ...] = ()
    k: int = Field(default=5, ge=1)


class RetrievalCase(BaseEvaluationCase):
    expected_evidence_ids: tuple[NonBlank, ...] = ()
    acceptable_evidence_ids: tuple[NonBlank, ...] = ()
    k: int = Field(default=5, ge=1)
    expect_no_evidence: bool = False


class SemanticaCase(RetrievalCase):
    seed_node_id: NonBlank


class AdvancedReasoningCase(BaseEvaluationCase):
    tool_names: tuple[NonBlank, ...] = Field(min_length=1)
    expected_tool_names: tuple[NonBlank, ...] = Field(min_length=1)
    forbidden_tools: tuple[NonBlank, ...] = ()
    maximum_tool_calls: int = Field(default=5, ge=1)
    reflection_expected: bool = False


class MultiHopCase(BaseEvaluationCase):
    hops: tuple[dict[str, Any], ...] = Field(min_length=1)
    min_hops: int = Field(ge=1)
    max_hops: int = Field(ge=1)
    expected_final: float
    actual_final: float
    numeric_tolerance: float = Field(default=0.0, ge=0)
    candidate_sql: str | None = None
    reference_sql: str | None = None

    @model_validator(mode="after")
    def valid_hop_bounds(self) -> MultiHopCase:
        if self.min_hops > self.max_hops:
            raise ValueError("min_hops cannot exceed max_hops")
        return self


class ForecastingCase(BaseEvaluationCase):
    frequency: Literal["day", "week", "month"]
    history: tuple[float, ...] = Field(min_length=8)
    future: tuple[float, ...] = Field(min_length=1)
    integration_sql: str | None = None


class OrchestrationCase(BaseEvaluationCase):
    selected_mode: NonBlank
    expected_route: NonBlank
    expected_response_type: NonBlank


class PrivacyCase(BaseEvaluationCase):
    protected_values: tuple[NonBlank, ...] = Field(min_length=1)
    expected_identifier_occurrences: int = Field(default=0, ge=0)
    expected_email_occurrences: int = Field(default=0, ge=0)
    expected_phone_occurrences: int = Field(default=0, ge=0)


CaseType = (
    RoutingCase
    | NLP2SQLCase
    | SQLSafetyCase
    | DiscoveryCase
    | RetrievalCase
    | SemanticaCase
    | AdvancedReasoningCase
    | MultiHopCase
    | ForecastingCase
    | OrchestrationCase
    | PrivacyCase
)


class EvaluationDataset(EvaluationModel):
    dataset_version: NonBlank
    suite: NonBlank
    cases: tuple[CaseType, ...]


class EvaluationCaseResult(EvaluationModel):
    case_id: NonBlank
    suite: NonBlank
    status: CaseStatus
    elapsed_ms: float = Field(ge=0)
    metrics: dict[str, float] = Field(default_factory=dict)
    expected: str | None = None
    actual: str | None = None
    error_type: str | None = None
    error: str | None = None
    provider_error: bool = False


class EvaluationSuiteResult(EvaluationModel):
    suite: NonBlank
    dataset_version: NonBlank
    cases: tuple[EvaluationCaseResult, ...]
    metrics: dict[str, float] = Field(default_factory=dict)
    details: dict[str, Any] = Field(default_factory=dict)


class EvaluationMetric(EvaluationModel):
    name: NonBlank
    value: float
    direction: MetricDirection = "higher_is_better"
    hard_gate: bool = False


class TokenUsage(EvaluationModel):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class EvaluationRunMetadata(EvaluationModel):
    run_id: NonBlank
    timestamp: datetime
    profile: EvaluationProfile
    dataset_versions: dict[str, str]
    git_commit_sha: str | None = None
    python_version: NonBlank
    llm_provider: str | None = None
    llm_model: str | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    random_seed: int


class RegressionPolicy(EvaluationModel):
    metric: NonBlank
    direction: MetricDirection
    allowed_degradation: float = Field(default=0.0, ge=0)
    hard_gate: bool = False


class RegressionResult(EvaluationModel):
    metric: NonBlank
    baseline_value: float
    current_value: float
    difference: float
    allowed_degradation: float
    status: RegressionStatus


class RegressionSummary(EvaluationModel):
    status: RegressionStatus
    results: tuple[RegressionResult, ...] = ()


class EvaluationRunReport(EvaluationModel):
    metadata: EvaluationRunMetadata
    suites: tuple[EvaluationSuiteResult, ...]
    metrics: tuple[EvaluationMetric, ...]
    total_cases: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    skipped: int = Field(ge=0)
    errors: int = Field(ge=0)
    pass_rate: float = Field(ge=0, le=1)
    latency_ms: dict[str, float]
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    regression: RegressionSummary | None = None

    @property
    def exit_code(self) -> int:
        gated_metric_failure = any(
            metric.hard_gate and metric.value != 0 for metric in self.metrics
        )
        regression = self.regression and self.regression.status is RegressionStatus.REGRESSION
        return int(bool(self.failed or self.errors or gated_metric_failure or regression))
