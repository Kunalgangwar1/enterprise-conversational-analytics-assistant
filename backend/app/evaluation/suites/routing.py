"""Supervisor/IntentRouter accuracy evaluation."""

from collections import Counter, defaultdict

from app.core.chat_modes import ChatModeKey
from app.evaluation.metrics import accuracy
from app.evaluation.models import EvaluationDataset, EvaluationSuiteResult, RoutingCase
from app.evaluation.suites.base import SuiteContext, evaluate_cases, pass_fail
from app.evaluation.suites.fakes import ModelPayloadLLM
from app.llm.factory import create_llm_client
from app.routing.intent_router import IntentRouterAgent
from app.routing.models import InternalRoute, LLMIntentDecision
from app.routing.supervisor import SupervisorMultiAgent


def evaluate(dataset: EvaluationDataset, context: SuiteContext) -> EvaluationSuiteResult:
    confusion: dict[str, Counter[str]] = defaultdict(Counter)

    def one(raw_case):
        case = RoutingCase.model_validate(raw_case)
        expected = InternalRoute(case.expected_route)
        llm = (
            create_llm_client(context.settings)
            if context.profile.value == "live"
            else ModelPayloadLLM(
                {LLMIntentDecision: {"intent": expected.value, "confidence": 0.95}}
            )
        )
        actual = (
            SupervisorMultiAgent(IntentRouterAgent(llm))
            .route(case.question, ChatModeKey.AUTO)
            .route
        )
        confusion[expected.value][actual.value] += 1
        return pass_fail(
            case,
            actual is expected,
            metrics={"correct": float(actual is expected)},
            expected=expected.value,
            actual=actual.value,
        )

    result = evaluate_cases(
        dataset,
        one,
        lambda items: {
            "routing_accuracy": accuracy(sum(i.status.value == "passed" for i in items), len(items))
        },
    )
    flattened = {
        f"confusion.{expected}.{actual}": float(count)
        for expected, values in sorted(confusion.items())
        for actual, count in sorted(values.items())
    }
    return result.model_copy(
        update={
            "metrics": {**result.metrics, **flattened},
            "details": {
                "confusion_matrix": {
                    expected: dict(sorted(actual.items()))
                    for expected, actual in sorted(confusion.items())
                }
            },
        }
    )
