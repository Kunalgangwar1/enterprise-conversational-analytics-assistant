"""Optional harmless live smoke test for the configured LLM provider."""

import sys

from app.llm.exceptions import LLMConfigurationError, LLMError
from app.llm.factory import get_llm_client
from app.llm.models import LLMMessage, LLMRequest, LLMRole


def main() -> int:
    """Send a harmless prompt and print only safe result metadata."""

    try:
        client = get_llm_client()
        response = client.generate(
            LLMRequest(
                messages=[
                    LLMMessage(
                        role=LLMRole.USER,
                        content="Reply with exactly: OK",
                    )
                ]
            )
        )
    except LLMConfigurationError as exc:
        print(f"LLM smoke test is not configured: {exc}", file=sys.stderr)
        return 2
    except LLMError as exc:
        print(f"LLM smoke test failed safely: {exc}", file=sys.stderr)
        return 1

    print(f"provider={response.provider}")
    print(f"model={response.model}")
    print(f"text={response.text}")
    print(f"elapsed_ms={response.elapsed_ms:.2f}")
    print(f"input_tokens={response.usage.input_tokens}")
    print(f"output_tokens={response.usage.output_tokens}")
    print(f"total_tokens={response.usage.total_tokens}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
