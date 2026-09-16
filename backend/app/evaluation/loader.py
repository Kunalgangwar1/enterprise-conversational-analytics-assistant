"""Strict loader for version-controlled synthetic evaluation datasets."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from app.evaluation.models import (
    AdvancedReasoningCase,
    CaseType,
    DiscoveryCase,
    EvaluationDataset,
    ForecastingCase,
    MultiHopCase,
    NLP2SQLCase,
    OrchestrationCase,
    PrivacyCase,
    RetrievalCase,
    RoutingCase,
    SemanticaCase,
    SQLSafetyCase,
)

CASE_MODELS: dict[str, type[CaseType]] = {
    "routing": RoutingCase,
    "nlp2sql": NLP2SQLCase,
    "sql_safety": SQLSafetyCase,
    "data_discovery": DiscoveryCase,
    "knowledge_catalog": RetrievalCase,
    "data_quality": RetrievalCase,
    "semantica": SemanticaCase,
    "advanced_reasoning": AdvancedReasoningCase,
    "multihop": MultiHopCase,
    "forecasting": ForecastingCase,
    "orchestration": OrchestrationCase,
    "privacy": PrivacyCase,
}


class EvaluationDatasetError(ValueError):
    """A curated evaluation dataset is missing or invalid."""


def load_dataset(path: Path) -> EvaluationDataset:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise EvaluationDatasetError("Evaluation dataset must be a mapping")
        suite = str(raw.get("suite", ""))
        model = CASE_MODELS[suite]
        raw_cases = raw.get("cases")
        if not isinstance(raw_cases, list):
            raise EvaluationDatasetError("Evaluation dataset cases must be a list")
        cases = tuple(model.model_validate(_with_suite(item, suite)) for item in raw_cases)
        case_ids = [case.case_id for case in cases]
        if len(case_ids) != len(set(case_ids)):
            raise EvaluationDatasetError(f"Duplicate case ID in {path.name}")
        return EvaluationDataset(
            dataset_version=raw.get("dataset_version", ""), suite=suite, cases=cases
        )
    except (OSError, yaml.YAMLError, ValidationError, KeyError, TypeError) as exc:
        raise EvaluationDatasetError(f"Invalid evaluation dataset: {path}") from exc


def load_datasets(
    cases_dir: Path,
    *,
    suite: str | None = None,
    case_id: str | None = None,
) -> tuple[EvaluationDataset, ...]:
    paths = [cases_dir / f"{suite}.yaml"] if suite else sorted(cases_dir.glob("*.yaml"))
    datasets = [load_dataset(path) for path in paths]
    all_ids = [case.case_id for dataset in datasets for case in dataset.cases]
    if len(all_ids) != len(set(all_ids)):
        raise EvaluationDatasetError("Case IDs must be globally unique")
    if case_id:
        datasets = [
            dataset.model_copy(
                update={"cases": tuple(case for case in dataset.cases if case.case_id == case_id)}
            )
            for dataset in datasets
            if any(case.case_id == case_id for case in dataset.cases)
        ]
        if not datasets:
            raise EvaluationDatasetError(f"Unknown evaluation case ID: {case_id}")
    return tuple(datasets)


def _with_suite(value: Any, suite: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvaluationDatasetError("Each evaluation case must be a mapping")
    return {**value, "suite": suite}
