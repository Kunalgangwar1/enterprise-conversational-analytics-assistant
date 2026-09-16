"""Deterministic aggregate-only forecast scope policy."""

import re

from app.forecasting.exceptions import ForecastScopeError

_INDIVIDUAL = re.compile(
    r"\b(?:member\s+T\d+|patient|individual|this\s+(?:person|member|patient)|my|me)\b",
    re.I,
)
_CLINICAL_OUTCOME = re.compile(
    r"\b(?:diagnos(?:is|e)|hospitali[sz](?:ation|ed)|mortality|death|survival|"
    r"treatment\s+recommendation|clinical\s+outcome|disease\s+risk)\b",
    re.I,
)


class ForecastScopePolicy:
    """Reject individual clinical prediction while allowing aggregate operations."""

    def require_supported(self, safe_question: str) -> None:
        if _INDIVIDUAL.search(safe_question) and _CLINICAL_OUTCOME.search(safe_question):
            raise ForecastScopeError(
                "Phase 17 supports aggregate operational forecasts, not individual clinical "
                "predictions"
            )
