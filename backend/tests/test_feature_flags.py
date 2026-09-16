"""Tests for functionality flag loading, validation, and public APIs."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.core.feature_flags import (
    FeatureFlagConfigurationError,
    ReasoningFeatureFlags,
    get_feature_flags,
    load_feature_flags,
)
from app.main import create_app


def _valid_reasoning_flags(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "deep_agent_single_intent_enabled": False,
        "deep_agent_min_confidence": 0.8,
        "deep_agent_eligible_routes": ["sql", "knowledge_catalog"],
        "deep_agent_max_subtasks": 5,
        "nlp2sql_multihop_enabled": False,
        "nlp2sql_multihop_max_hops": 3,
        "nlp2sql_multihop_max_rows_per_hop": 100,
        "nlp2sql_multihop_total_row_budget": 250,
        "nlp2sql_multihop_total_timeout_seconds": 20,
    }
    values.update(overrides)
    return values


def test_get_feature_flags_loads_typed_yaml_values() -> None:
    get_feature_flags.cache_clear()

    flags = get_feature_flags()

    assert flags.reasoning.deep_agent_min_confidence == 0.8
    assert isinstance(flags.ui.follow_up_questions_show, bool)
    assert isinstance(flags.tools.sql, bool)
    assert isinstance(flags.reasoning.deep_agent_eligible_routes, list)
    assert all(isinstance(route, str) for route in flags.reasoning.deep_agent_eligible_routes)
    assert flags.retrieval.hierarchical_rag is True
    assert flags.retrieval.vector_rag is True


def test_ui_feature_flags_endpoint_exposes_only_safe_fields() -> None:
    test_app = create_app(Settings(app_name="Test Analytics API", app_env="test"))

    with TestClient(test_app) as client:
        response = client.get("/api/ui-feature-flags")

    assert response.status_code == 200
    assert set(response.json()) == {
        "follow_up_questions_show",
        "context_button",
        "chat_latency_badge",
        "knowledge_graph_tools_show",
    }


def test_tool_flags_endpoint_exposes_only_tool_availability() -> None:
    test_app = create_app(Settings(app_name="Test Analytics API", app_env="test"))

    with TestClient(test_app) as client:
        response = client.get("/api/tool-flags")

    assert response.status_code == 200
    assert set(response.json()) == {
        "sql",
        "forecasting",
        "group_access",
        "data_discovery",
        "knowledge_catalog",
        "semantica",
        "data_quality",
    }


def test_invalid_deep_agent_confidence_fails_validation() -> None:
    with pytest.raises(ValidationError):
        ReasoningFeatureFlags.model_validate(_valid_reasoning_flags(deep_agent_min_confidence=1.01))


def test_multihop_max_hops_below_one_fails_validation() -> None:
    with pytest.raises(ValidationError):
        ReasoningFeatureFlags.model_validate(_valid_reasoning_flags(nlp2sql_multihop_max_hops=0))


def test_multihop_total_rows_must_cover_one_hop() -> None:
    with pytest.raises(ValidationError):
        ReasoningFeatureFlags.model_validate(
            _valid_reasoning_flags(
                nlp2sql_multihop_max_rows_per_hop=100,
                nlp2sql_multihop_total_row_budget=99,
            )
        )


def test_missing_feature_flag_file_has_clear_error(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.yaml"

    with pytest.raises(FeatureFlagConfigurationError, match="not found"):
        load_feature_flags(missing_path)


def test_malformed_feature_flag_yaml_has_clear_error(tmp_path: Path) -> None:
    malformed_path = tmp_path / "malformed.yaml"
    malformed_path.write_text("ui: [unterminated", encoding="utf-8")

    with pytest.raises(FeatureFlagConfigurationError, match="Malformed YAML"):
        load_feature_flags(malformed_path)
