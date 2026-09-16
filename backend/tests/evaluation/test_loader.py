from pathlib import Path

import pytest

from app.evaluation.loader import EvaluationDatasetError, load_dataset, load_datasets


def test_loads_typed_versioned_dataset(tmp_path: Path) -> None:
    path = tmp_path / "routing.yaml"
    path.write_text(
        "dataset_version: '1.2'\nsuite: routing\ncases:\n"
        "  - case_id: route-test-001\n"
        "    description: test route\n"
        "    question: hello\n"
        "    expected_route: chat\n",
        encoding="utf-8",
    )

    dataset = load_dataset(path)

    assert dataset.dataset_version == "1.2"
    assert dataset.cases[0].case_id == "route-test-001"


def test_rejects_duplicate_ids_within_dataset(tmp_path: Path) -> None:
    path = tmp_path / "routing.yaml"
    path.write_text(
        "dataset_version: '1.0'\nsuite: routing\ncases:\n"
        "  - {case_id: duplicate, description: one, question: hello, expected_route: chat}\n"
        "  - {case_id: duplicate, description: two, question: help, expected_route: help}\n",
        encoding="utf-8",
    )

    with pytest.raises(EvaluationDatasetError, match="Duplicate case ID"):
        load_dataset(path)


def test_rejects_duplicate_ids_across_datasets(tmp_path: Path) -> None:
    (tmp_path / "routing.yaml").write_text(
        "dataset_version: '1.0'\nsuite: routing\ncases:\n"
        "  - {case_id: shared, description: one, question: hello, expected_route: chat}\n",
        encoding="utf-8",
    )
    (tmp_path / "sql_safety.yaml").write_text(
        "dataset_version: '1.0'\nsuite: sql_safety\ncases:\n"
        "  - {case_id: shared, description: two, question: reject, sql: 'DROP TABLE claims'}\n",
        encoding="utf-8",
    )

    with pytest.raises(EvaluationDatasetError, match="globally unique"):
        load_datasets(tmp_path)
