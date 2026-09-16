"""Lazy application composition for the Knowledge Catalog specialist."""

from functools import partial

from app.core.config import Settings
from app.core.feature_flags import FunctionalityFlags, get_feature_flags
from app.knowledge_catalog.agent import KnowledgeCatalogAgent
from app.knowledge_catalog.context_builder import KnowledgeContextBuilder
from app.knowledge_catalog.embeddings.factory import create_embedding_client
from app.knowledge_catalog.hierarchy import HierarchicalCatalogRetriever
from app.knowledge_catalog.hybrid_retriever import HybridCatalogRetriever
from app.knowledge_catalog.loader import CatalogLoader
from app.knowledge_catalog.retriever import KnowledgeCatalogRetriever
from app.knowledge_catalog.vector_store import LanceDBKnowledgeStore
from app.llm.factory import create_llm_client


def build_knowledge_catalog_agent(
    settings: Settings,
    flags: FunctionalityFlags | None = None,
) -> KnowledgeCatalogAgent:
    """Compose production components without constructing network clients."""

    resolved_flags = flags or get_feature_flags()
    hierarchy = CatalogLoader(settings.knowledge_catalog_dir).load()
    llm_factory = partial(create_llm_client, settings)
    store = LanceDBKnowledgeStore(settings.artifacts_output_dir / "knowledge_catalog" / "lancedb")
    hierarchical = HierarchicalCatalogRetriever(
        hierarchy=hierarchy,
        llm_client_factory=llm_factory,
        max_depth=settings.knowledge_hierarchy_max_depth,
        max_branches=settings.knowledge_hierarchy_max_branches,
        min_confidence=settings.knowledge_hierarchy_min_confidence,
        top_k=settings.knowledge_catalog_top_k,
    )
    hybrid = HybridCatalogRetriever(
        store=store,
        embedding_client_factory=partial(create_embedding_client, settings),
        top_k=settings.knowledge_catalog_top_k,
    )
    return KnowledgeCatalogAgent(
        retriever=KnowledgeCatalogRetriever(
            flags=resolved_flags.retrieval,
            hierarchical=hierarchical,
            hybrid=hybrid,
        ),
        context_builder=KnowledgeContextBuilder(max_chars=settings.knowledge_context_max_chars),
        llm_client_factory=llm_factory,
    )
