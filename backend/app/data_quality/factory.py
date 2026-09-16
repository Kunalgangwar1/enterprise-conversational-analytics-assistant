"""Lazy application composition for Data Quality guidance."""

from functools import partial

from app.core.config import Settings
from app.data_quality.agent import DataQualityAgent
from app.data_quality.context_builder import DataQualityContextBuilder
from app.data_quality.loader import DataQualityLoader
from app.data_quality.retriever import DataQualityRetriever
from app.llm.factory import create_llm_client


def build_data_quality_agent(settings: Settings) -> DataQualityAgent:
    return DataQualityAgent(
        retriever=DataQualityRetriever(
            DataQualityLoader(settings.data_quality_dir).load(),
            top_k=settings.data_quality_top_k,
        ),
        context_builder=DataQualityContextBuilder(max_chars=settings.knowledge_context_max_chars),
        llm_client_factory=partial(create_llm_client, settings),
    )
