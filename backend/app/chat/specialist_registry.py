"""Lazy typed access to existing specialist implementations."""

from collections.abc import Callable
from typing import Generic, TypeVar

from app.chat.exceptions import SpecialistUnavailableError
from app.data_discovery.search import DataDiscoveryService
from app.data_quality.agent import DataQualityAgent
from app.forecasting.agent import ForecastingAgent
from app.knowledge_catalog.agent import KnowledgeCatalogAgent
from app.nlp2sql.agent import NLP2SQLAgent
from app.nlp2sql.multihop.agent import MultiHopNLP2SQLAgent
from app.semantica.agent import SemanticaAgent

Specialist = TypeVar("Specialist")


class _LazySpecialist(Generic[Specialist]):
    def __init__(self, provider: Callable[[], Specialist] | None) -> None:
        self._provider = provider
        self._instance: Specialist | None = None

    def get(self, label: str) -> Specialist:
        if self._provider is None:
            raise SpecialistUnavailableError(f"{label} is not currently available")
        if self._instance is None:
            self._instance = self._provider()
        return self._instance


class ChatSpecialistRegistry:
    """Hold application-provided specialists without constructing unused providers."""

    def __init__(
        self,
        *,
        nlp2sql: Callable[[], NLP2SQLAgent] | None = None,
        multihop: Callable[[], MultiHopNLP2SQLAgent] | None = None,
        forecasting: Callable[[], ForecastingAgent] | None = None,
        data_discovery: Callable[[], DataDiscoveryService] | None = None,
        knowledge_catalog: Callable[[], KnowledgeCatalogAgent] | None = None,
        data_quality: Callable[[], DataQualityAgent] | None = None,
        semantica: Callable[[], SemanticaAgent] | None = None,
    ) -> None:
        self._nlp2sql = _LazySpecialist(nlp2sql)
        self._multihop = _LazySpecialist(multihop)
        self._forecasting = _LazySpecialist(forecasting)
        self._data_discovery = _LazySpecialist(data_discovery)
        self._knowledge_catalog = _LazySpecialist(knowledge_catalog)
        self._data_quality = _LazySpecialist(data_quality)
        self._semantica = _LazySpecialist(semantica)

    def nlp2sql(self) -> NLP2SQLAgent:
        return self._nlp2sql.get("Standard SQL")

    def multihop(self) -> MultiHopNLP2SQLAgent:
        return self._multihop.get("Advanced SQL")

    def forecasting(self) -> ForecastingAgent:
        return self._forecasting.get("Forecasting")

    def data_discovery(self) -> DataDiscoveryService:
        return self._data_discovery.get("Data Discovery")

    def knowledge_catalog(self) -> KnowledgeCatalogAgent:
        return self._knowledge_catalog.get("Knowledge Catalog")

    def data_quality(self) -> DataQualityAgent:
        return self._data_quality.get("Data Quality")

    def semantica(self) -> SemanticaAgent:
        return self._semantica.get("Semantica")
