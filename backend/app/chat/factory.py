"""Lazy credential-free construction for the unified chat orchestrator."""

from collections.abc import Callable
from functools import cache

from app.chat.orchestrator import ChatOrchestrator
from app.chat.specialist_registry import ChatSpecialistRegistry
from app.core.chat_modes import chat_mode_registry
from app.core.config import Settings
from app.core.feature_flags import get_feature_flags
from app.data_discovery.factory import build_data_discovery_service
from app.data_discovery.search import DataDiscoveryService
from app.data_quality.agent import DataQualityAgent
from app.data_quality.factory import build_data_quality_agent
from app.db.query.factory import build_query_executor
from app.forecasting.agent import ForecastingAgent
from app.forecasting.factory import build_forecasting_agent
from app.knowledge_catalog.agent import KnowledgeCatalogAgent
from app.knowledge_catalog.factory import build_knowledge_catalog_agent
from app.llm.base import LLMClient, StructuredModel
from app.llm.factory import create_llm_client
from app.llm.models import LLMRequest, LLMResponse
from app.metadata.model_registry import build_model_metadata_registry
from app.nlp2sql.agent import NLP2SQLAgent
from app.nlp2sql.multihop.agent import MultiHopNLP2SQLAgent
from app.nlp2sql.multihop.factory import build_multihop_agent
from app.routing.intent_router import IntentRouterAgent
from app.routing.supervisor import SupervisorMultiAgent
from app.semantica.agent import SemanticaAgent
from app.semantica.factory import build_semantica_agent


class DeferredLLMClient:
    """Delay credential validation until a model-backed operation actually runs."""

    def __init__(self, factory: Callable[[], LLMClient]) -> None:
        self._factory = factory
        self._client: LLMClient | None = None

    def _get(self) -> LLMClient:
        if self._client is None:
            self._client = self._factory()
        return self._client

    def generate(self, request: LLMRequest) -> LLMResponse:
        return self._get().generate(request)

    def generate_structured(
        self,
        request: LLMRequest,
        response_model: type[StructuredModel],
    ) -> StructuredModel:
        return self._get().generate_structured(request, response_model)

    def close(self) -> None:
        if self._client is not None:
            self._client.close()


def build_chat_orchestrator(
    settings: Settings,
    *,
    knowledge_catalog_agent: KnowledgeCatalogAgent | None = None,
    data_discovery_service: DataDiscoveryService | None = None,
    data_quality_agent: DataQualityAgent | None = None,
    semantica_agent: SemanticaAgent | None = None,
) -> ChatOrchestrator:
    """Compose specialists lazily so deterministic modes need no model credentials."""

    flags = get_feature_flags()
    llm = DeferredLLMClient(lambda: create_llm_client(settings))

    @cache
    def nlp2sql() -> NLP2SQLAgent:
        return NLP2SQLAgent(build_model_metadata_registry(), llm)

    @cache
    def query_executor():
        return build_query_executor(settings)

    @cache
    def multihop() -> MultiHopNLP2SQLAgent:
        return build_multihop_agent(
            settings=settings,
            flags=flags.reasoning,
            llm_client=llm,
            nlp2sql_agent=nlp2sql(),
            query_executor=query_executor(),
        )

    @cache
    def forecasting() -> ForecastingAgent:
        if not flags.tools.forecasting:
            from app.chat.exceptions import SpecialistUnavailableError

            raise SpecialistUnavailableError("Forecasting is disabled by rollout policy")
        return build_forecasting_agent(settings, llm, nlp2sql(), query_executor())

    registry = ChatSpecialistRegistry(
        nlp2sql=nlp2sql,
        multihop=multihop,
        forecasting=forecasting,
        data_discovery=lambda: data_discovery_service or build_data_discovery_service(settings),
        knowledge_catalog=lambda: (
            knowledge_catalog_agent or build_knowledge_catalog_agent(settings, flags)
        ),
        data_quality=lambda: data_quality_agent or build_data_quality_agent(settings),
        semantica=lambda: semantica_agent or build_semantica_agent(settings),
    )
    return ChatOrchestrator(
        SupervisorMultiAgent(IntentRouterAgent(llm)),
        registry,
        chat_mode_registry,
    )
