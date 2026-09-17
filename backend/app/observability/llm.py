"""Provider-neutral LLM telemetry decorator that never observes message content."""

from __future__ import annotations

from time import perf_counter

from app.llm.base import LLMClient, StructuredModel
from app.llm.models import LLMRequest, LLMResponse
from app.observability.metrics import get_metrics
from app.observability.tracing import start_span


class InstrumentedLLMClient:
    """Record bounded provider/model/operation signals around the shared LLM contract."""

    def __init__(self, client: LLMClient, *, provider: str, model: str) -> None:
        self._client = client
        self._provider = provider
        self._model = model

    def generate(self, request: LLMRequest) -> LLMResponse:
        started = perf_counter()
        attributes = self._attributes("generate")
        with start_span("llm.call", self._span_attributes("generate")) as span:
            try:
                response = self._client.generate(request)
            except Exception as exc:
                self._record_call("generate", "error", perf_counter() - started)
                span.set_attribute("error.type", type(exc).__name__[:128])
                raise
            self._record_call("generate", "success", perf_counter() - started)
            metrics = get_metrics()
            if response.usage.input_tokens is not None:
                metrics.record("llm.tokens.input", response.usage.input_tokens, attributes)
            if response.usage.output_tokens is not None:
                metrics.record("llm.tokens.output", response.usage.output_tokens, attributes)
            span.set_attribute("outcome", "success")
            return response

    def generate_structured(
        self,
        request: LLMRequest,
        response_model: type[StructuredModel],
    ) -> StructuredModel:
        started = perf_counter()
        with start_span("llm.call", self._span_attributes("generate_structured")) as span:
            try:
                response = self._client.generate_structured(request, response_model)
            except Exception as exc:
                self._record_call("generate_structured", "error", perf_counter() - started)
                span.set_attribute("error.type", type(exc).__name__[:128])
                raise
            self._record_call("generate_structured", "success", perf_counter() - started)
            span.set_attribute("outcome", "success")
            return response

    def close(self) -> None:
        close = getattr(self._client, "close", None)
        if callable(close):
            close()

    def _record_call(self, operation: str, outcome: str, duration: float) -> None:
        attributes = {**self._attributes(operation), "outcome": outcome}
        metrics = get_metrics()
        metrics.record("llm.requests", 1, attributes)
        metrics.record("llm.duration", duration, attributes)
        if outcome == "error":
            metrics.record("llm.errors", 1, attributes)

    def _attributes(self, operation: str) -> dict[str, str]:
        return {
            "provider": self._provider,
            "model": self._model,
            "operation": operation,
        }

    def _span_attributes(self, operation: str) -> dict[str, str]:
        return {
            "gen_ai.provider.name": self._provider,
            "gen_ai.request.model": self._model,
            "operation.name": operation,
        }
