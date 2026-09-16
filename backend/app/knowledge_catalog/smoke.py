"""Optional live Azure Knowledge Catalog smoke command."""

import sys

from app.core.config import get_settings
from app.knowledge_catalog.exceptions import EmbeddingConfigurationError, KnowledgeCatalogError
from app.knowledge_catalog.factory import build_knowledge_catalog_agent
from app.knowledge_catalog.index import build_index
from app.llm.exceptions import LLMConfigurationError
from app.llm.factory import create_llm_client


def main() -> None:
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        print('Usage: python -m app.knowledge_catalog.smoke "catalog question"')
        raise SystemExit(2)
    try:
        settings = get_settings()
        create_llm_client(settings)
        build_index(settings=settings)
        result = build_knowledge_catalog_agent(settings).answer(sys.argv[1].strip())
    except (LLMConfigurationError, EmbeddingConfigurationError) as exc:
        print(f"Live Knowledge Catalog smoke unavailable: {exc}")
        raise SystemExit(2) from exc
    except KnowledgeCatalogError as exc:
        print(f"Knowledge Catalog smoke failed: {exc}")
        raise SystemExit(1) from exc
    print(f"Retrieval method: {result.retrieval_method.value}")
    print(result.answer)
    for citation in result.citations:
        print(f"- {citation.id}: {citation.title} ({citation.source_path})")


if __name__ == "__main__":
    main()
