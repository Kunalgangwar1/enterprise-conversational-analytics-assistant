"""Deterministic metadata discovery tests."""

from app.data_discovery.models import DatasetRegistration
from app.data_discovery.search import DataDiscoveryService


def test_registry_represents_all_seven_valid_synthetic_datasets(
    registrations: tuple[DatasetRegistration, ...],
) -> None:
    assert {item.table for item in registrations} == {
        "members",
        "providers",
        "facilities",
        "encounters",
        "claims",
        "claim_lines",
        "appointments",
    }
    assert all(item.repository.startswith("datasets-") for item in registrations)
    assert all(item.domain and item.description and item.columns for item in registrations)


def test_expected_queries_rank_specific_datasets_first(
    registrations: tuple[DatasetRegistration, ...],
) -> None:
    service = DataDiscoveryService(registrations, top_k=5)

    assert (
        service.search("Which dataset contains provider specialty?").matches[0].table == "providers"
    )
    assert service.search("Find claim payment data.").matches[0].table == "claims"
    assert service.search("Where is appointment status?").matches[0].table == "appointments"


def test_exact_table_name_scores_strongly(registrations: tuple[DatasetRegistration, ...]) -> None:
    result = DataDiscoveryService(registrations, top_k=5).search("claim_lines")

    assert result.matches[0].table == "claim_lines"
    assert result.matches[0].score == 1.0


def test_unknown_and_broad_questions_do_not_invent_datasets(
    registrations: tuple[DatasetRegistration, ...],
) -> None:
    service = DataDiscoveryService(registrations, top_k=5)

    assert service.search("quantum banana orchestra").matches == ()
    assert service.search("Explain claims lineage.").matches == ()


def test_top_k_and_order_are_deterministic(registrations: tuple[DatasetRegistration, ...]) -> None:
    service = DataDiscoveryService(registrations, top_k=2)

    first = service.search("external id status")
    second = service.search("external id status")

    assert 0 < len(first.matches) <= 2
    assert first == second


def test_discovery_module_has_no_llm_embedding_or_query_executor_dependency() -> None:
    import app.data_discovery.search as module

    names = set(module.__dict__)
    assert "LLMClient" not in names
    assert "EmbeddingClient" not in names
    assert "QueryExecutor" not in names
