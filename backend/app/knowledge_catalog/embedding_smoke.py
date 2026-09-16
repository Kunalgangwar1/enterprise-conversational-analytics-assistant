"""Optional harmless live smoke for the configured embedding provider."""

import sys

from app.knowledge_catalog.embeddings.factory import get_embedding_client
from app.knowledge_catalog.exceptions import EmbeddingConfigurationError, EmbeddingError


def main() -> int:
    try:
        client = get_embedding_client()
        vector = client.embed_query("synthetic healthcare analytics")
    except EmbeddingConfigurationError as exc:
        print(f"Embedding smoke is not configured: {exc}", file=sys.stderr)
        return 2
    except EmbeddingError as exc:
        print(f"Embedding smoke failed safely: {exc}", file=sys.stderr)
        return 1
    print(f"provider={client.provider_name}")
    print(f"model={client.model_name}")
    print(f"dimensions={len(vector)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
