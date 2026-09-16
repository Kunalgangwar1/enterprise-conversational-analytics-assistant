from pathlib import Path

import pytest

from app.core.config import Settings
from app.evaluation.config import DEFAULT_EVAL_ROOT, EvaluationConfig
from app.evaluation.models import EvaluationProfile
from app.evaluation.run import build_parser
from app.evaluation.runner import run_evaluation
from app.llm.exceptions import LLMConfigurationError


def test_cli_profile_and_filters_parse() -> None:
    args = build_parser().parse_args(
        ["--profile", "integration", "--suite", "routing", "--case-id", "route-001"]
    )

    assert args.profile == "integration"
    assert args.suite == "routing"
    assert args.case_id == "route-001"


def test_complete_offline_run_is_network_free_and_passes(tmp_path: Path, monkeypatch) -> None:
    def fail_provider(*args, **kwargs):
        raise AssertionError("offline evaluation attempted provider construction")

    monkeypatch.setattr("app.evaluation.suites.routing.create_llm_client", fail_provider)
    monkeypatch.setattr("app.evaluation.suites.nlp2sql.create_llm_client", fail_provider)
    report = run_evaluation(
        profile=EvaluationProfile.OFFLINE,
        settings=Settings(),
        config=EvaluationConfig(eval_root=DEFAULT_EVAL_ROOT, output_dir=tmp_path, random_seed=42),
    )

    assert report.total_cases == 68
    assert report.passed == 68
    assert report.failed == 0
    assert report.errors == 0
    assert report.exit_code == 0
    assert report.metadata.random_seed == 42
    routing = next(item for item in report.suites if item.suite == "routing")
    assert routing.details["confusion_matrix"]["forecasting"]["forecasting"] == 2


def test_live_profile_fails_clearly_without_credentials(tmp_path: Path) -> None:
    settings = Settings(
        llm_provider="gemini",
        embedding_provider="gemini",
        gemini_api_key=None,
    )

    with pytest.raises(LLMConfigurationError, match="GEMINI_API_KEY"):
        run_evaluation(
            profile=EvaluationProfile.LIVE,
            settings=settings,
            config=EvaluationConfig(
                eval_root=DEFAULT_EVAL_ROOT,
                output_dir=tmp_path,
                random_seed=42,
            ),
            suite="routing",
        )
