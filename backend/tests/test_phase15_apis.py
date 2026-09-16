"""Phase 15 specialist API contracts and privacy boundaries."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.data_discovery.factory import build_data_discovery_service
from app.data_quality.agent import DataQualityAgent
from app.data_quality.context_builder import DataQualityContextBuilder
from app.data_quality.loader import DataQualityLoader
from app.data_quality.retriever import DataQualityRetriever
from app.knowledge_catalog.context_builder import KnowledgeContextBuilder
from app.knowledge_catalog.models import KnowledgeEvidence, RetrievalMethod, RetrievalResult
from app.main import create_app
from app.semantica.agent import SemanticaAgent
from tests.knowledge_catalog.fakes import StubRetriever
from tests.llm.fakes import FakeLLMClient

_BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_all_phase15_routes_exist_and_reject_blank_questions() -> None:
    app = create_app(Settings(_env_file=None, app_env="test"))
    paths = set(app.openapi()["paths"])

    assert {
        "/api/data-discovery/query",
        "/api/data-quality/query",
        "/api/semantica/query",
    }.issubset(paths)
    assert "/api/health" in paths
    assert "/chat" in paths

    with TestClient(app) as client:
        for path in sorted(
            paths
            & {
                "/api/data-discovery/query",
                "/api/data-quality/query",
                "/api/semantica/query",
            }
        ):
            assert client.post(path, json={"question": "   "}).status_code == 422


def test_data_discovery_api_returns_metadata_only() -> None:
    settings = Settings(_env_file=None, app_env="test")
    app = create_app(
        settings,
        data_discovery_service=build_data_discovery_service(settings),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/data-discovery/query",
            json={"question": "Which dataset contains provider specialty?"},
        )

    assert response.status_code == 200
    assert response.json()["matches"][0]["table"] == "providers"
    assert "vector" not in response.text
    assert "row" not in response.text


def test_dq_and_semantica_api_citations_are_safe_and_private() -> None:
    dq_fake = FakeLLMClient(
        structured_payload={
            "answer": "Claims guidance for T001.",
            "citation_ids": ["dq_rules_claims"],
        }
    )
    sem_fake = FakeLLMClient(
        structured_payload={"answer": "Claims relation for T001.", "citation_ids": ["sem_1"]}
    )
    app = create_app(
        Settings(_env_file=None, app_env="test"),
        data_quality_agent=_dq_agent(dq_fake),
        semantica_agent=_semantica_agent(sem_fake),
    )
    payload = {"question": "Claims for M000245; email alice@example.com"}

    with TestClient(app) as client:
        dq_response = client.post("/api/data-quality/query", json=payload)
        sem_response = client.post("/api/semantica/query", json=payload)

    assert dq_response.status_code == sem_response.status_code == 200
    assert "M000245" in dq_response.json()["answer"]
    assert "M000245" in sem_response.json()["answer"]
    for response in (dq_response, sem_response):
        assert response.json()["citations"]
        assert all(
            forbidden not in response.text
            for forbidden in ("vector", "adjacency", "mapping", "api_key", "deployment")
        )
    for fake in (dq_fake, sem_fake):
        visible = "\n".join(message.content for message in fake.requests[0].messages)
        assert "T001" in visible and "[EMAIL]" in visible
        assert "M000245" not in visible and "alice@example.com" not in visible


def _dq_agent(fake: FakeLLMClient) -> DataQualityAgent:
    documents = DataQualityLoader(_BACKEND_ROOT / "data" / "data_quality").load()
    return DataQualityAgent(
        retriever=DataQualityRetriever(documents, top_k=5),
        context_builder=DataQualityContextBuilder(max_chars=4_000),
        llm_client_factory=lambda: fake,
    )


def _semantica_agent(fake: FakeLLMClient) -> SemanticaAgent:
    evidence = KnowledgeEvidence(
        evidence_id="sem_1",
        chunk_id="sem_1",
        node_id="dataset_claims",
        title="Claims",
        section="Relationships",
        source_path="datasets/claims.md",
        text="Claims reference synthetic members and providers.",
        retrieval_method=RetrievalMethod.SEMANTICA_GRAPH,
        rank=1,
        graph_distance=0,
        seed_rank=1,
    )
    return SemanticaAgent(
        retriever=StubRetriever(
            RetrievalResult(
                evidence=(evidence,),
                retrieval_method=RetrievalMethod.SEMANTICA_GRAPH,
                sufficient=True,
            )
        ),  # type: ignore[arg-type]
        context_builder=KnowledgeContextBuilder(max_chars=2_000),
        llm_client_factory=lambda: fake,
    )
