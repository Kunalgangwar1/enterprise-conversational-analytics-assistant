"""Semantic, execution-based NLP-to-SQL evaluation."""

from app.db.query.guard import validate_read_only_sql
from app.evaluation.metrics import accuracy, results_equivalent
from app.evaluation.models import EvaluationDataset, EvaluationSuiteResult, NLP2SQLCase
from app.evaluation.suites.base import SuiteContext, evaluate_cases, mean_case_metric, pass_fail
from app.evaluation.suites.fakes import ModelPayloadLLM
from app.llm.factory import create_llm_client
from app.metadata.model_registry import build_model_metadata_registry
from app.nlp2sql.agent import NLP2SQLAgent
from app.nlp2sql.models import (
    DomainSelection,
    SQLGeneration,
    SQLSemanticAssessment,
    SQLValidationDecision,
    TableSelection,
)


def evaluate(dataset: EvaluationDataset, context: SuiteContext) -> EvaluationSuiteResult:
    registry = build_model_metadata_registry()
    query_executor = None
    if context.profile.value in {"integration", "live"}:
        from app.db.query.factory import build_query_executor

        query_executor = build_query_executor(context.settings)

    def one(raw_case):
        case = NLP2SQLCase.model_validate(raw_case)
        llm = (
            create_llm_client(context.settings)
            if context.profile.value == "live"
            else ModelPayloadLLM(
                {
                    DomainSelection: {"selected_domains": list(case.selected_domains)},
                    TableSelection: {"selected_tables": list(case.selected_tables)},
                    SQLGeneration: {"sql": case.candidate_sql},
                    SQLSemanticAssessment: {"score": 1.0, "issues": []},
                }
            )
        )
        generated = NLP2SQLAgent(registry, llm).generate_sql(case.question)
        accepted = generated.validation.decision is SQLValidationDecision.ACCEPT
        validate_read_only_sql(case.reference_sql)
        reference_hidden = all(
            case.reference_sql not in message.content
            for request in getattr(llm, "requests", [])
            for message in request.messages
        )
        if query_executor:
            candidate = query_executor.execute(generated.final_sql or generated.generated_sql)
            reference = query_executor.execute(case.reference_sql)
            left_columns, left_rows = candidate.columns, candidate.rows
            right_columns, right_rows = reference.columns, reference.rows
        else:
            left_rows, right_rows = case.candidate_result, case.reference_result
            left_columns = list(left_rows[0]) if left_rows else []
            right_columns = list(right_rows[0]) if right_rows else []
        equivalent = results_equivalent(
            left_columns,
            left_rows,
            right_columns,
            right_rows,
            order_sensitive=case.order_sensitive,
            numeric_tolerance=case.numeric_tolerance,
        )
        grounding = set(generated.selected_tables) == set(case.selected_tables)
        passed = accepted and equivalent and grounding and reference_hidden
        return pass_fail(
            case,
            passed,
            metrics={
                "generation_success": 1.0,
                "validation_accepted": float(accepted),
                "execution_success": 1.0,
                "result_equivalent": float(equivalent),
                "schema_grounded": float(grounding),
                "reference_sql_isolated": float(reference_hidden),
            },
            expected="equivalent read-only result",
            actual="equivalent" if equivalent else "different result",
        )

    def metrics(items):
        return {
            "generation_success_rate": mean_case_metric(items, "generation_success"),
            "validation_acceptance_rate": mean_case_metric(items, "validation_accepted"),
            "execution_success_rate": mean_case_metric(items, "execution_success"),
            "result_equivalence_accuracy": mean_case_metric(items, "result_equivalent"),
            "schema_grounding_accuracy": mean_case_metric(items, "schema_grounded"),
            "reference_sql_isolation_rate": mean_case_metric(items, "reference_sql_isolated"),
            "case_accuracy": accuracy(sum(i.status.value == "passed" for i in items), len(items)),
        }

    return evaluate_cases(dataset, one, metrics)
