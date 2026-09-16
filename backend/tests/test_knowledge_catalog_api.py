"""Specialist Knowledge Catalog API contract and privacy tests."""

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.knowledge_catalog.agent import KnowledgeCatalogAgent
from app.knowledge_catalog.context_builder import KnowledgeContextBuilder
from app.knowledge_catalog.models import KnowledgeEvidence, RetrievalMethod, RetrievalResult
from app.main import create_app
from tests.knowledge_catalog.fakes import StubRetriever
from tests.llm.fakes import FakeLLMClient


def test_knowledge_catalog_query_is_typed_private_and_cited() -> None:
    fake = FakeLLMClient(
        structured_payload={"answer": "Guidance for T001.", "citation_ids": ["e1"]}
    )
    application = create_app(
        Settings(app_env="test"),
        knowledge_catalog_agent=_agent(fake),
    )

    with TestClient(application) as client:
        response = client.post(
            "/api/knowledge-catalog/query",
            json={"question": "Claims for M000245; email alice@example.com"},
        )
        health = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "answer": "Guidance for M000245.",
        "retrieval_method": "hierarchical",
        "citations": [
            {
                "id": "e1",
                "title": "Claims Dataset",
                "section": "Financial measures",
                "source_path": "datasets/claims.md",
            }
        ],
    }
    visible = "\n".join(message.content for message in fake.requests[0].messages)
    assert "T001" in visible and "[EMAIL]" in visible
    assert "M000245" not in visible and "alice@example.com" not in visible
    assert "vector" not in response.text and "mapping" not in response.text
    assert health.status_code == 200


def test_empty_question_and_extra_fields_are_rejected() -> None:
    application = create_app(
        Settings(app_env="test"), knowledge_catalog_agent=_agent(FakeLLMClient())
    )

    with TestClient(application) as client:
        blank = client.post("/api/knowledge-catalog/query", json={"question": "   "})
        extra = client.post(
            "/api/knowledge-catalog/query",
            json={"question": "claims", "sql": "select 1"},
        )

    assert blank.status_code == 422
    assert extra.status_code == 422


def test_openapi_exposes_specialist_and_chat_routes() -> None:
    application = create_app(Settings(app_env="test"))
    paths = application.openapi()["paths"]

    assert "/api/knowledge-catalog/query" in paths
    assert "/chat" in paths
    response_schema = paths["/api/knowledge-catalog/query"]["post"]["responses"]["200"]
    assert "KnowledgeCatalogResult" in str(response_schema)


def _agent(fake: FakeLLMClient) -> KnowledgeCatalogAgent:
    evidence = KnowledgeEvidence(
        evidence_id="e1",
        node_id="dataset_claims",
        title="Claims Dataset",
        section="Financial measures",
        source_path="datasets/claims.md",
        text="Allowed amount is the eligible amount.",
        retrieval_method=RetrievalMethod.HIERARCHICAL,
        rank=1,
    )
    return KnowledgeCatalogAgent(
        retriever=StubRetriever(
            RetrievalResult(
                evidence=(evidence,),
                retrieval_method=RetrievalMethod.HIERARCHICAL,
                sufficient=True,
                confidence=0.9,
            )
        ),
        context_builder=KnowledgeContextBuilder(max_chars=1_000),
        llm_client_factory=lambda: fake,
    )
