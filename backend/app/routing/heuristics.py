"""Small deterministic policy for high-confidence routing cases."""

import re
from dataclasses import dataclass

from app.routing.models import InternalRoute


@dataclass(frozen=True, slots=True)
class HeuristicDecision:
    """Internal result returned only for a high-confidence rule match."""

    route: InternalRoute
    confidence: float
    reason_code: str


_GROUP_ACCESS_PATTERNS = (
    re.compile(r"\b(?:request|grant|obtain|need|get)\s+access\b"),
    re.compile(r"\bpermission\s+to\s+(?:view|access|use|query)\b"),
    re.compile(r"\b(?:role|group)(?:\s+membership)?\b.{0,50}\baccess\b"),
    re.compile(r"\bentitlements?\b"),
    re.compile(r"\bauthori[sz]ation\s+to\b"),
)
_DATA_QUALITY_PATTERNS = (
    re.compile(r"\bdata[ -]quality\b"),
    re.compile(r"\b(?:null|missing)\s+(?:values?|records?|rows?|fields?|columns?)\b"),
    re.compile(r"\bduplicate\s+(?:records?|rows?)\b"),
    re.compile(r"\bquality\s+rules?\b"),
    re.compile(r"\bfailed\s+validation\b"),
    re.compile(
        r"\b(?:completeness|validity|freshness|stale)\b.{0,50}\b(?:data|dataset|table|records?)\b"
    ),
    re.compile(r"\b(?:data|dataset|table|records?|claims?)\b.{0,50}\b(?:fresh|stale)\b"),
)
_SEMANTICA_PATTERN = re.compile(r"\bsemantica\b")
_HELP_PATTERNS = (
    re.compile(r"\bwhat\s+can\s+you\s+do\b"),
    re.compile(r"\bwhat\s+modes?\s+are\s+available\b"),
)
_CHAT_PATTERN = re.compile(r"^(?:hello|hi|hey|good\s+(?:morning|afternoon|evening))[!. ]*$")
_FORECAST_ACTION_PATTERN = re.compile(
    r"\b(?:forecasts?|forecasting|predict|prediction|projections?|project|projected|outlook|"
    r"future\s+trend)\b"
)
_FORECAST_HORIZON_PATTERN = re.compile(r"\bnext\s+(?:month|quarter|year)\b")
_ANALYTICAL_CONTEXT_PATTERN = re.compile(
    r"\b(?:claims?|payments?|paid|amounts?|costs?|volume|trend|utilization|appointments?|"
    r"encounters?|members?|providers?|enrollment|data|metric|total|average)\b"
)
_DISCOVERY_PATTERNS = (
    re.compile(r"\b(?:find|locate)\s+(?:a\s+|the\s+)?(?:dataset|table|schema|data\s+source)\b"),
    re.compile(r"\bwhich\s+(?:dataset|table)\s+(?:contains|has|includes)\b"),
    re.compile(r"\bwhere\s+is\s+(?:the\s+)?(?:schema|table|dataset)\b"),
    re.compile(r"\bwhere\s+can\s+i\s+find\s+(?:a\s+|the\s+)?(?:schema|table|dataset)\b"),
)
_BROAD_CATALOG_PATTERN = re.compile(
    r"\b(?:lineage|policy|policies|business\s+meaning|ontology|governance)\b"
)


def route_by_heuristic(safe_text: str) -> HeuristicDecision | None:
    """Return a decision only for deliberately narrow, high-confidence cases."""

    normalized = " ".join(safe_text.lower().split())
    ordered_rules = (
        _group_access_decision,
        _data_quality_decision,
        _semantica_decision,
        _help_decision,
        _chat_decision,
        _forecasting_decision,
        _data_discovery_decision,
    )
    for rule in ordered_rules:
        decision = rule(normalized)
        if decision is not None:
            return decision
    return None


def detect_forecasting_intent(safe_text: str) -> HeuristicDecision | None:
    """Detect a strong analytical forecast intent for SQL-mode sub-routing."""

    return _forecasting_decision(" ".join(safe_text.lower().split()))


def _matches_any(patterns: tuple[re.Pattern[str], ...], text: str) -> bool:
    return any(pattern.search(text) is not None for pattern in patterns)


def _group_access_decision(text: str) -> HeuristicDecision | None:
    if _matches_any(_GROUP_ACCESS_PATTERNS, text):
        return HeuristicDecision(InternalRoute.GROUP_ACCESS, 0.99, "access_language")
    return None


def _data_quality_decision(text: str) -> HeuristicDecision | None:
    if _matches_any(_DATA_QUALITY_PATTERNS, text):
        return HeuristicDecision(InternalRoute.DATA_QUALITY, 0.98, "data_quality_language")
    return None


def _semantica_decision(text: str) -> HeuristicDecision | None:
    if _SEMANTICA_PATTERN.search(text) is not None:
        return HeuristicDecision(InternalRoute.SEMANTICA, 1.0, "explicit_semantica")
    return None


def _help_decision(text: str) -> HeuristicDecision | None:
    if text.strip(".!? ") == "help" or _matches_any(_HELP_PATTERNS, text):
        return HeuristicDecision(InternalRoute.HELP, 1.0, "help_request")
    return None


def _chat_decision(text: str) -> HeuristicDecision | None:
    if _CHAT_PATTERN.fullmatch(text) is not None:
        return HeuristicDecision(InternalRoute.CHAT, 1.0, "simple_greeting")
    return None


def _forecasting_decision(text: str) -> HeuristicDecision | None:
    has_forecast_language = (
        _FORECAST_ACTION_PATTERN.search(text) is not None
        or _FORECAST_HORIZON_PATTERN.search(text) is not None
    )
    if has_forecast_language and _ANALYTICAL_CONTEXT_PATTERN.search(text) is not None:
        return HeuristicDecision(InternalRoute.FORECASTING, 0.98, "analytical_forecast")
    return None


def _data_discovery_decision(text: str) -> HeuristicDecision | None:
    if _BROAD_CATALOG_PATTERN.search(text) is not None:
        return None
    if _matches_any(_DISCOVERY_PATTERNS, text):
        return HeuristicDecision(InternalRoute.DATA_DISCOVERY, 0.97, "specific_data_lookup")
    return None
