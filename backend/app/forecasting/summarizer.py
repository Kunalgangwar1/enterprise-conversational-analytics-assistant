"""Privacy-bounded explanation of immutable deterministic forecasts."""

import json

from pydantic import ValidationError

from app.forecasting.models import (
    ForecastComputation,
    ForecastPlan,
    ForecastSummary,
)
from app.llm.base import LLMClient
from app.llm.exceptions import LLMError
from app.llm.models import LLMMessage, LLMRequest, LLMRole
from app.sql_results.models import SummarySource

_SYSTEM_PROMPT = """Explain the supplied aggregate operational forecast concisely.
The forecast numbers and dates are immutable deterministic application outputs: never change,
recalculate, or add to them. State that uncertainty intervals are approximate. Do not infer
causes, clinical significance, individual outcomes, or medical advice. Use only the protected
preview and structured forecast supplied by the application."""


class ForecastSummarizer:
    """Generate an optional narrative without granting the model numerical authority."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    def summarize(
        self,
        *,
        safe_question: str,
        plan: ForecastPlan,
        computation: ForecastComputation,
        protected_preview: str,
    ) -> tuple[str, SummarySource]:
        payload = {
            "safe_question": safe_question,
            "metric_label": plan.metric_label,
            "frequency": plan.frequency.value,
            "selected_model": computation.selected_model,
            "backtest_metrics": computation.backtest_metrics.model_dump(mode="json"),
            "forecast_points": [
                point.model_dump(mode="json") for point in computation.forecast_points
            ],
            "protected_historical_preview": protected_preview,
        }
        request = LLMRequest(
            messages=[
                LLMMessage(role=LLMRole.SYSTEM, content=_SYSTEM_PROMPT),
                LLMMessage(
                    role=LLMRole.USER,
                    content=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                ),
            ],
            temperature=0,
        )
        try:
            response = self._llm_client.generate_structured(request, ForecastSummary)
            summary = response.summary
            source = SummarySource.LLM
        except (LLMError, ValidationError, ValueError, TypeError):
            summary = self._fallback(plan, computation)
            source = SummarySource.DETERMINISTIC_FALLBACK
        if not any(word in summary.lower() for word in ("uncertain", "interval", "approximate")):
            summary = f"{summary} Uncertainty intervals are approximate."
        return summary, source

    @staticmethod
    def _fallback(plan: ForecastPlan, computation: ForecastComputation) -> str:
        first = computation.forecast_points[0]
        last = computation.forecast_points[-1]
        return (
            f"The {computation.selected_model} model forecasts {plan.metric_label} from "
            f"{first.predicted:.2f} on {first.period.isoformat()} to {last.predicted:.2f} on "
            f"{last.period.isoformat()}. Approximate uncertainty intervals widen by horizon; "
            "this aggregate operational forecast is not clinical advice."
        )
