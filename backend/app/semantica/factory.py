"""Lazy application composition for Semantica."""

from functools import partial

from app.core.config import Settings
from app.knowledge_catalog.context_builder import KnowledgeContextBuilder
from app.knowledge_catalog.embeddings.factory import create_embedding_client
from app.knowledge_catalog.models import RetrievalMethod
from app.knowledge_catalog.vector_store import LanceDBKnowledgeStore
from app.llm.factory import create_llm_client
from app.semantica.agent import SemanticaAgent
from app.semantica.graph import load_graph
from app.semantica.retriever import SemanticaRetriever


def build_semantica_agent(settings: Settings) -> SemanticaAgent:
    root = settings.artifacts_output_dir / "semantica"
    store = LanceDBKnowledgeStore(
        root / "lancedb",
        table_name="semantica_chunks",
        retrieval_method=RetrievalMethod.SEMANTICA_GRAPH,
        manifest_path=root / "index_manifest.json",
    )
    return SemanticaAgent(
        retriever=SemanticaRetriever(
            store=store,
            graph=load_graph(root / "adjacency.json"),
            embedding_client_factory=partial(create_embedding_client, settings),
            seed_top_k=settings.semantica_seed_top_k,
            max_hops=settings.semantica_max_hops,
            max_evidence=settings.semantica_max_evidence,
        ),
        context_builder=KnowledgeContextBuilder(max_chars=settings.knowledge_context_max_chars),
        llm_client_factory=partial(create_llm_client, settings),
    )
