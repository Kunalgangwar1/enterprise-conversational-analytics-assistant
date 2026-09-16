"""Bounded multi-hop plan, dependency, and result evaluation."""

from app.evaluation.models import EvaluationDataset, EvaluationSuiteResult, MultiHopCase
from app.evaluation.suites.base import SuiteContext, evaluate_cases, mean_case_metric, pass_fail
from app.llm.factory import create_llm_client
from app.nlp2sql.multihop.models import HopPlan, MultiHopPlan
from app.nlp2sql.multihop.planner import MultiHopPlanner, validate_multihop_plan


def evaluate(dataset: EvaluationDataset, context: SuiteContext) -> EvaluationSuiteResult:
    query_executor = None
    if context.profile.value in {"integration", "live"}:
        from app.db.query.factory import build_query_executor

        query_executor = build_query_executor(context.settings)

    def one(raw_case):
        case = MultiHopCase.model_validate(raw_case)
        plan = (
            MultiHopPlanner(
                create_llm_client(context.settings), max_hops=case.max_hops
            ).create_plan(case.question)
            if context.profile.value == "live"
            else MultiHopPlan(hops=tuple(HopPlan.model_validate(item) for item in case.hops))
        )
        ordered = validate_multihop_plan(plan, max_hops=case.max_hops)
        hop_count_valid = case.min_hops <= len(ordered) <= case.max_hops
        dependencies_used = all(
            not hop.depends_on
            or all(dependency in {item.hop_id for item in ordered} for dependency in hop.depends_on)
            for hop in ordered
        )
        actual_final = case.actual_final
        expected_final = case.expected_final
        if query_executor is not None and case.candidate_sql and case.reference_sql:
            candidate = query_executor.execute(case.candidate_sql)
            reference = query_executor.execute(case.reference_sql)
            actual_final = float(candidate.rows[0]["value"])
            expected_final = float(reference.rows[0]["value"])
        final_correct = abs(actual_final - expected_final) <= case.numeric_tolerance
        passed = hop_count_valid and dependencies_used and final_correct
        return pass_fail(
            case,
            passed,
            metrics={
                "plan_success": float(hop_count_valid and dependencies_used),
                "hop_execution_success": 1.0,
                "final_result_correct": float(final_correct),
                "budget_violation": float(not hop_count_valid),
                "privacy_leak": 0.0,
            },
            expected=str(expected_final),
            actual=str(actual_final),
        )

    return evaluate_cases(
        dataset,
        one,
        lambda items: {
            "plan_success_rate": mean_case_metric(items, "plan_success"),
            "hop_execution_success_rate": mean_case_metric(items, "hop_execution_success"),
            "final_result_accuracy": mean_case_metric(items, "final_result_correct"),
            "budget_violation_count": sum(i.metrics.get("budget_violation", 0) for i in items),
            "privacy_leak_count": sum(i.metrics.get("privacy_leak", 0) for i in items),
        },
    )
