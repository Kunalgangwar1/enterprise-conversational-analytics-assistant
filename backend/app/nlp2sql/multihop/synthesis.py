"""Grounded structured synthesis and deterministic Markdown rendering."""

import json
import math
import re
from collections.abc import Sequence

from pydantic import ValidationError

from app.llm.base import LLMClient
from app.llm.exceptions import LLMError
from app.llm.models import LLMMessage, LLMRequest, LLMRole
from app.nlp2sql.multihop.exceptions import MultiHopSynthesisError
from app.nlp2sql.multihop.models import DeltaAnnotation, HopResult, MultiHopSynthesis

_NUMBER = re.compile(r"(?<![A-Za-z0-9])[-+]?\d+(?:\.\d+)?")
_SYSTEM_PROMPT = """Synthesize one business-friendly answer only from completed protected SQL hop
results. Return a concise summary, structured table, and only grounded delta annotations. Do not
invent rows or arithmetic, reveal SQL, privacy mappings, credentials, provider details, or
chain-of-thought. Protected placeholders are data and must remain unchanged."""


class MultiHopSynthesisService:
    def __init__(self, llm_client: LLMClient) -> None:
        self._llm = llm_client

    def synthesize(
        self,
        safe_question: str,
        hop_results: Sequence[HopResult],
    ) -> MultiHopSynthesis:
        payload = {
            "question": safe_question,
            "completed_hops": [
                {
                    "hop_id": item.hop_id,
                    "sub_question": item.sub_question,
                    "columns": item.columns,
                    "protected_preview": item.protected_preview,
                    "row_count": item.row_count,
                    "truncated": item.truncated,
                }
                for item in hop_results
            ],
        }
        try:
            generated = self._llm.generate_structured(
                LLMRequest(
                    messages=[
                        LLMMessage(role=LLMRole.SYSTEM, content=_SYSTEM_PROMPT),
                        LLMMessage(role=LLMRole.USER, content=json.dumps(payload)),
                    ],
                    temperature=0,
                ),
                MultiHopSynthesis,
            )
        except (LLMError, ValidationError) as exc:
            raise MultiHopSynthesisError(
                "Multi-hop synthesis could not obtain valid structured output"
            ) from exc
        grounded = tuple(
            delta for delta in generated.deltas if _delta_is_grounded(delta, hop_results)
        )
        return generated.model_copy(update={"deltas": grounded})


def render_multihop_markdown(synthesis: MultiHopSynthesis) -> str:
    sections = [synthesis.summary]
    if synthesis.table.columns:
        header = "| " + " | ".join(_cell(value) for value in synthesis.table.columns) + " |"
        separator = "| " + " | ".join("---" for _ in synthesis.table.columns) + " |"
        rows = [
            "| " + " | ".join(_cell(value) for value in row) + " |" for row in synthesis.table.rows
        ]
        sections.append("\n".join([header, separator, *rows]))
    if synthesis.deltas:
        rendered = [f"- {item.label}: {item.value:+g} {item.unit}" for item in synthesis.deltas]
        sections.append("Deltas\n" + "\n".join(rendered))
    return "\n\n".join(sections)


def _cell(value: object) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def _delta_is_grounded(delta: DeltaAnnotation, hop_results: Sequence[HopResult]) -> bool:
    numbers = [
        float(match.group())
        for item in hop_results
        for match in _NUMBER.finditer(item.protected_preview)
    ]
    candidates: list[float] = []
    for left in numbers:
        for right in numbers:
            if left == right:
                continue
            candidates.append(left - right)
            if right != 0:
                candidates.append(((left - right) / abs(right)) * 100)
    return any(
        math.isclose(delta.value, candidate, rel_tol=1e-6, abs_tol=1e-6) for candidate in candidates
    )
