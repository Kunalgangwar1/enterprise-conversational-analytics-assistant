"""Representative mode, route, and response-contract evaluation."""

from app.core.chat_modes import ChatModeKey
from app.evaluation.models import EvaluationDataset, EvaluationSuiteResult, OrchestrationCase
from app.evaluation.suites.base import SuiteContext, evaluate_cases, mean_case_metric, pass_fail
from app.evaluation.suites.fakes import ModelPayloadLLM
from app.llm.factory import create_llm_client
from app.routing.intent_router import IntentRouterAgent
from app.routing.models import InternalRoute, LLMIntentDecision
from app.routing.supervisor import SupervisorMultiAgent

_RESPONSE_TYPES = {
    InternalRoute.SQL: "sql",
    InternalRoute.FORECASTING: "forecast",
    InternalRoute.DATA_DISCOVERY: "data_discovery",
    InternalRoute.KNOWLEDGE_CATALOG: "knowledge_catalog",
    InternalRoute.DATA_QUALITY: "data_quality",
    InternalRoute.SEMANTICA: "semantica",
    InternalRoute.CHAT: "message",
    InternalRoute.HELP: "message",
    InternalRoute.GROUP_ACCESS: "message",
}


def evaluate(dataset: EvaluationDataset, context: SuiteContext) -> EvaluationSuiteResult:
    def one(raw_case):
        case = OrchestrationCase.model_validate(raw_case)
        expected_route = InternalRoute(case.expected_route)
        llm = (
            create_llm_client(context.settings)
            if context.profile.value == "live"
            else ModelPayloadLLM(
                {LLMIntentDecision: {"intent": expected_route.value, "confidence": 0.95}}
            )
        )
        decision = SupervisorMultiAgent(IntentRouterAgent(llm)).route(
            case.question, ChatModeKey(case.selected_mode)
        )
        response_type = _RESPONSE_TYPES[decision.route]
        route_ok = decision.route is expected_route
        response_ok = response_type == case.expected_response_type
        return pass_fail(
            case,
            route_ok and response_ok,
            metrics={"route_contract": float(route_ok), "response_contract": float(response_ok)},
            expected=f"{case.expected_route}/{case.expected_response_type}",
            actual=f"{decision.route.value}/{response_type}",
        )

    return evaluate_cases(
        dataset,
        one,
        lambda items: {
            "route_contract_accuracy": mean_case_metric(items, "route_contract"),
            "response_contract_accuracy": mean_case_metric(items, "response_contract"),
        },
    )
