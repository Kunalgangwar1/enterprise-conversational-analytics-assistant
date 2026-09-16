"""Read-only SQL safety regression evaluation."""

from app.db.query.exceptions import QueryValidationError
from app.db.query.guard import validate_read_only_sql
from app.evaluation.metrics import accuracy
from app.evaluation.models import EvaluationDataset, EvaluationSuiteResult, SQLSafetyCase
from app.evaluation.suites.base import SuiteContext, evaluate_cases, pass_fail


def evaluate(dataset: EvaluationDataset, context: SuiteContext) -> EvaluationSuiteResult:
    del context

    def one(raw_case):
        case = SQLSafetyCase.model_validate(raw_case)
        accepted = True
        try:
            validate_read_only_sql(case.sql)
        except QueryValidationError:
            accepted = False
        passed = accepted is case.should_accept
        return pass_fail(
            case,
            passed,
            metrics={
                "unsafe_rejected": float(not case.should_accept and not accepted),
                "unsafe_executed": 0.0,
            },
            expected="accepted" if case.should_accept else "rejected",
            actual="accepted" if accepted else "rejected",
        )

    return evaluate_cases(
        dataset,
        one,
        lambda items: {
            "unsafe_rejection_rate": accuracy(
                sum(i.metrics.get("unsafe_rejected", 0) == 1 for i in items),
                sum("unsafe_rejected" in i.metrics for i in items),
            ),
            "unsafe_execution_count": sum(i.metrics.get("unsafe_executed", 0) for i in items),
        },
    )
