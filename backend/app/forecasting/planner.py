"""LLM-assisted, typed planning for aggregate operational forecasts."""

from pydantic import ValidationError

from app.advanced_reasoning.security import contains_disallowed_executable_content
from app.forecasting.exceptions import ForecastHorizonError, ForecastPlanningError
from app.forecasting.models import ForecastPlan, ForecastPlanDraft
from app.forecasting.scope import ForecastScopePolicy
from app.llm.base import LLMClient
from app.llm.exceptions import LLMError
from app.llm.models import LLMMessage, LLMRequest, LLMRole

_SYSTEM_PROMPT = """You plan aggregate operational time-series forecasts.
Return only the requested structured fields. Identify a concise metric label, DAY/WEEK/MONTH
frequency, optional requested horizon, and a natural-language question that asks for exactly
one historical period column and one numeric aggregate value column. Do not write SQL, code,
URLs, clinical advice, individual predictions, or invented schema details. The historical
question must request chronological, complete history through the latest completed period, with
no more than {max_history_points} most recent periods."""


class ForecastPlanner:
    """Turn a privacy-safe aggregate question into a bounded typed plan."""

    def __init__(
        self,
        llm_client: LLMClient,
        *,
        default_horizon: int,
        max_horizon: int,
        max_history_points: int = 120,
        scope_policy: ForecastScopePolicy | None = None,
    ) -> None:
        self._llm_client = llm_client
        self._default_horizon = default_horizon
        self._max_horizon = max_horizon
        self._max_history_points = max_history_points
        self._scope_policy = scope_policy or ForecastScopePolicy()

    def plan(self, safe_question: str) -> ForecastPlan:
        """Validate scope and request a non-executable structured plan."""

        question = safe_question.strip()
        if not question:
            raise ForecastPlanningError("A privacy-safe forecasting question is required")
        self._scope_policy.require_supported(question)
        request = LLMRequest(
            messages=[
                LLMMessage(
                    role=LLMRole.SYSTEM,
                    content=_SYSTEM_PROMPT.format(max_history_points=self._max_history_points),
                ),
                LLMMessage(role=LLMRole.USER, content=question),
            ],
            temperature=0,
        )
        try:
            draft = self._llm_client.generate_structured(request, ForecastPlanDraft)
        except (LLMError, ValidationError, ValueError, TypeError) as exc:
            raise ForecastPlanningError("The forecast request could not be planned safely") from exc

        horizon = draft.horizon_periods or self._default_horizon
        if horizon > self._max_horizon:
            raise ForecastHorizonError(
                f"Forecast horizon cannot exceed {self._max_horizon} periods"
            )
        if contains_disallowed_executable_content(draft.historical_series_question):
            raise ForecastPlanningError("The forecast plan contained executable content")
        return ForecastPlan(
            metric_label=draft.metric_label,
            frequency=draft.frequency,
            horizon_periods=horizon,
            historical_series_question=draft.historical_series_question,
            description=draft.description,
            filters_description=draft.filters_description,
        )
