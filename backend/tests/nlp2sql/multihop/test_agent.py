"""Two-hop execution, privacy, failure, synthesis, and graph tests."""

import pytest

from app.db.query.exceptions import QueryTimeoutError
from app.db.query.models import QueryExecutionResult
from app.llm.exceptions import LLMProviderError
from app.nlp2sql.models import SQLValidationDecision
from app.nlp2sql.multihop.agent import MultiHopNLP2SQLAgent
from app.nlp2sql.multihop.exceptions import (
    MultiHopBudgetExceededError,
    MultiHopExecutionError,
    MultiHopSynthesisError,
)
from app.nlp2sql.multihop.graph import MULTIHOP_NODE_SEQUENCE
from app.nlp2sql.multihop.models import DeltaAnnotation, MultiHopSynthesis, SynthesisTable
from app.nlp2sql.multihop.synthesis import render_multihop_markdown
from app.privacy.models import IdentifierType, TokenMappingEntry
from tests.llm.fakes import FakeLLMClient
from tests.nlp2sql.multihop.helpers import (
    RecordingBoundedExecutor,
    RecordingNLP2SQLAgent,
    nlp2sql_result,
)

FIRST_SQL = "SELECT facility_type, COUNT(*) AS claim_count FROM claims GROUP BY facility_type"
SECOND_SQL = (
    "SELECT facility_type, AVG(paid_amount) AS average_paid FROM claims GROUP BY facility_type"
)


def _query_result(rows: list[dict[str, object]]) -> QueryExecutionResult:
    return QueryExecutionResult(
        columns=list(rows[0]) if rows else [],
        rows=rows,
        row_count=len(rows),
        truncated=False,
        elapsed_ms=2,
    )


def _llm(*, include_token: bool = False, deltas: list[dict[str, object]] | None = None):
    winner = "T001" if include_token else "Hospital"
    return FakeLLMClient(
        structured_payloads=[
            {
                "hops": [
                    {
                        "hop_id": "h1",
                        "sub_question": "Find claim volume by facility type",
                        "depends_on": [],
                        "purpose": "Find the highest-volume type",
                    },
                    {
                        "hop_id": "h2",
                        "sub_question": "Compare average paid amount for the winner and others",
                        "depends_on": ["h1"],
                        "purpose": "Compare paid amounts",
                    },
                ]
            },
            {
                "summary": f"{winner} leads the comparison.",
                "table": {
                    "columns": ["Facility", "Average"],
                    "rows": [[winner, 100], ["Other", 80]],
                },
                "deltas": deltas or [],
            },
        ]
    )


def _agent(
    llm,
    nlp2sql,
    executor,
    *,
    total_rows: int = 5,
    clock=None,
) -> MultiHopNLP2SQLAgent:
    kwargs = {}
    if clock is not None:
        kwargs["clock"] = clock
    return MultiHopNLP2SQLAgent(
        enabled=True,
        llm_client=llm,
        nlp2sql_agent=nlp2sql,
        query_executor=executor,
        max_hops=3,
        max_rows_per_hop=3,
        total_row_budget=total_rows,
        total_timeout_seconds=20,
        query_timeout_ms=5_000,
        **kwargs,
    )


def test_two_hop_execution_is_ordered_bounded_and_synthesized_once() -> None:
    nlp2sql = RecordingNLP2SQLAgent([nlp2sql_result(FIRST_SQL), nlp2sql_result(SECOND_SQL)])
    executor = RecordingBoundedExecutor(
        [
            _query_result([{"facility_type": "Hospital", "claim_count": 10}]),
            _query_result(
                [
                    {"facility_type": "Hospital", "average_paid": 100},
                    {"facility_type": "Other", "average_paid": 80},
                ]
            ),
        ]
    )
    llm = _llm(
        deltas=[
            {"label": "Hospital versus other", "value": 25, "unit": "%", "direction": "up"},
            {"label": "Invented", "value": 999, "unit": "%", "direction": "up"},
        ]
    )
    agent = _agent(llm, nlp2sql, executor)

    result = agent.run(
        "Find the facility type with the highest claim volume, then compare paid amounts."
    )

    assert set(MULTIHOP_NODE_SEQUENCE) <= set(agent.graph.get_graph().nodes)
    assert len(nlp2sql.questions) == 2
    assert "Hospital" in nlp2sql.questions[1]
    assert [call[0] for call in executor.calls] == [FIRST_SQL, SECOND_SQL]
    assert all(call[1] <= 3 and call[2] <= 5_000 for call in executor.calls)
    assert result.budget.hops_executed == 2
    assert result.budget.total_rows_returned == 3
    assert [delta.value for delta in result.synthesis.deltas] == [25]
    assert "| Facility | Average |" in result.answer_markdown
    assert len(llm.requests) == 2


def test_inter_hop_and_synthesis_context_are_privacy_protected() -> None:
    mapping = TokenMappingEntry(
        token="T001",
        original_value="M000245",
        identifier_type=IdentifierType.MEMBER,
    )
    nlp2sql = RecordingNLP2SQLAgent([nlp2sql_result(FIRST_SQL), nlp2sql_result(SECOND_SQL)])
    executor = RecordingBoundedExecutor(
        [
            _query_result(
                [
                    {
                        "member_id": "M000245",
                        "email": "alice@example.com",
                        "phone": "212-555-0188",
                    }
                ]
            ),
            _query_result([{"average_paid": 100}]),
        ]
    )
    llm = _llm(include_token=True)

    result = _agent(llm, nlp2sql, executor).run("Safe question using T001", (mapping,))

    second_question = nlp2sql.questions[1]
    assert "T001" in second_question
    assert "[EMAIL]" in second_question
    assert "[PHONE]" in second_question
    assert "M000245" not in second_question
    assert "alice@example.com" not in second_question
    assert "212-555-0188" not in second_question
    llm_visible = "\n".join(
        message.content for request in llm.requests for message in request.messages
    )
    assert "alice@example.com" not in llm_visible
    assert "212-555-0188" not in llm_visible
    assert "M000245 leads" in result.answer_markdown


def test_rejected_first_hop_stops_dependent_execution_and_synthesis() -> None:
    nlp2sql = RecordingNLP2SQLAgent(
        [nlp2sql_result(FIRST_SQL, decision=SQLValidationDecision.REJECT)]
    )
    executor = RecordingBoundedExecutor([])
    llm = _llm()

    with pytest.raises(MultiHopExecutionError, match="accepted SQL"):
        _agent(llm, nlp2sql, executor).run("Safe question")

    assert len(nlp2sql.questions) == 1
    assert executor.calls == []
    assert len(llm.requests) == 1


def test_query_timeout_stops_dependent_hops() -> None:
    class TimeoutExecutor(RecordingBoundedExecutor):
        def execute(self, sql: str, *, max_rows=None, timeout_ms=None):
            self.calls.append((sql, max_rows, timeout_ms))
            raise QueryTimeoutError("timed out")

    nlp2sql = RecordingNLP2SQLAgent([nlp2sql_result(FIRST_SQL), nlp2sql_result(SECOND_SQL)])
    executor = TimeoutExecutor([])

    with pytest.raises(MultiHopExecutionError, match="could not be completed"):
        _agent(_llm(), nlp2sql, executor).run("Safe question")

    assert len(executor.calls) == 1
    assert len(nlp2sql.questions) == 1


def test_total_row_exhaustion_prevents_next_hop() -> None:
    nlp2sql = RecordingNLP2SQLAgent([nlp2sql_result(FIRST_SQL), nlp2sql_result(SECOND_SQL)])
    executor = RecordingBoundedExecutor([_query_result([{"value": 1}, {"value": 2}, {"value": 3}])])

    with pytest.raises(MultiHopBudgetExceededError, match="row budget"):
        _agent(_llm(), nlp2sql, executor, total_rows=3).run("Safe question")

    assert len(executor.calls) == 1
    assert len(nlp2sql.questions) == 1


def test_markdown_renderer_escapes_cells_and_supports_deltas() -> None:
    synthesis = MultiHopSynthesis(
        summary="Summary",
        table=SynthesisTable(columns=("Name",), rows=(("A|B",),)),
        deltas=(DeltaAnnotation(label="Change", value=-3.2, unit="percentage points"),),
    )

    rendered = render_multihop_markdown(synthesis)

    assert "A\\|B" in rendered
    assert "-3.2 percentage points" in rendered


def test_forecasting_question_is_rejected_before_planning() -> None:
    llm = _llm()
    agent = _agent(llm, RecordingNLP2SQLAgent([]), RecordingBoundedExecutor([]))

    with pytest.raises(MultiHopExecutionError, match="Forecasting"):
        agent.run("Forecast paid claims next quarter")

    assert llm.requests == []


@pytest.mark.parametrize(
    "decision",
    [SQLValidationDecision.REWRITE, SQLValidationDecision.REJECT],
)
def test_only_accepted_final_sql_can_execute(decision: SQLValidationDecision) -> None:
    nlp2sql = RecordingNLP2SQLAgent([nlp2sql_result(FIRST_SQL, decision=decision)])
    executor = RecordingBoundedExecutor([])

    with pytest.raises(MultiHopExecutionError, match="accepted SQL"):
        _agent(_llm(), nlp2sql, executor).run("Safe question")

    assert executor.calls == []


def test_tokenized_sql_resolves_only_at_query_boundary() -> None:
    mapping = TokenMappingEntry(
        token="T001",
        original_value="M000245",
        identifier_type=IdentifierType.MEMBER,
    )
    tokenized_sql = "SELECT 'T001' AS member_id"
    nlp2sql = RecordingNLP2SQLAgent([nlp2sql_result(tokenized_sql), nlp2sql_result(SECOND_SQL)])
    executor = RecordingBoundedExecutor(
        [_query_result([{"member_id": "M000245"}]), _query_result([{"average_paid": 10}])]
    )

    result = _agent(_llm(include_token=True), nlp2sql, executor).run(
        "Safe question for T001", (mapping,)
    )

    assert result.hops[0].safe_sql == tokenized_sql
    assert "M000245" in executor.calls[0][0]
    assert "T001" not in executor.calls[0][0]


def test_unresolved_sql_token_fails_closed() -> None:
    nlp2sql = RecordingNLP2SQLAgent([nlp2sql_result("SELECT 'T999' AS member_id")])
    executor = RecordingBoundedExecutor([])

    with pytest.raises(MultiHopExecutionError, match="could not be completed"):
        _agent(_llm(), nlp2sql, executor).run("Safe question")

    assert executor.calls == []


def test_synthesis_provider_failure_is_controlled() -> None:
    class FailingSynthesisLLM(FakeLLMClient):
        def generate_structured(self, request, response_model):
            if self.requests:
                raise LLMProviderError("provider unavailable")
            return super().generate_structured(request, response_model)

    llm = FailingSynthesisLLM(
        structured_payloads=[
            {
                "hops": [
                    {
                        "hop_id": "h1",
                        "sub_question": "Find claim volume by facility type",
                        "depends_on": [],
                        "purpose": "Find the highest-volume type",
                    },
                    {
                        "hop_id": "h2",
                        "sub_question": "Compare average paid amount",
                        "depends_on": ["h1"],
                        "purpose": "Compare paid amounts",
                    },
                ]
            }
        ]
    )
    nlp2sql = RecordingNLP2SQLAgent([nlp2sql_result(FIRST_SQL), nlp2sql_result(SECOND_SQL)])
    executor = RecordingBoundedExecutor(
        [_query_result([{"value": 1}]), _query_result([{"value": 2}])]
    )

    with pytest.raises(MultiHopSynthesisError):
        _agent(llm, nlp2sql, executor).run("Safe question")
