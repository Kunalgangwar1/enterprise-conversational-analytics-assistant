"""Local-only app entry point replacing paid LLM calls with a deterministic fake."""

from app.chat.models import ChatRequest, ChatTurnResult, SQLChatPayload, SQLChatResponse
from app.core.chat_modes import ChatModeKey
from app.core.config import Settings
from app.db.query.factory import build_query_executor
from app.llm.base import StructuredModel
from app.llm.models import LLMMessage, LLMRequest, LLMResponse, LLMRole
from app.main import create_app
from app.routing.models import InternalRoute
from app.sql_results.chart import ChartMetadataBuilder
from app.sql_results.preview import SQLSummaryPreviewBuilder
from app.sql_results.service import SQLExecutionService
from app.sql_results.summarizer import SQLResultSummarizer
from app.sql_results.token_resolver import SQLTokenResolver


class FakeLLM:
    """Network-free LLM contract used solely by the performance target."""

    def generate(self, request: LLMRequest) -> LLMResponse:
        del request
        return LLMResponse(
            text="Deterministic synthetic SQL response.",
            provider="performance_fake",
            model="performance_fake_v1",
            elapsed_ms=0,
        )

    def generate_structured(
        self, request: LLMRequest, response_model: type[StructuredModel]
    ) -> StructuredModel:
        del request
        return response_model.model_validate({"summary": "Synthetic query result returned."})

    def close(self) -> None:
        pass


class FakeLLMChatOrchestrator:
    def __init__(self) -> None:
        self.llm = FakeLLM()

    def run(self, payload: ChatRequest, state: object, principal: object) -> ChatTurnResult:
        del state, principal
        llm_response = self.llm.generate(
            LLMRequest(messages=[LLMMessage(role=LLMRole.USER, content=payload.message)])
        )
        sql = "SELECT COUNT(*) AS row_count FROM claims"
        response = SQLChatResponse(
            selected_mode=ChatModeKey.SQL,
            route=InternalRoute.SQL,
            content=llm_response.text,
            latency_ms=0,
            payload=SQLChatPayload(
                sql=sql,
                selected_domains=("claims",),
                selected_tables=("claims",),
            ),
        )
        return ChatTurnResult(response=response, accepted_sql=sql)


settings = Settings(app_env="test", auth_mode="development", rate_limit_requests=10_000)
fake_llm = FakeLLM()
sql_service = SQLExecutionService(
    build_query_executor(settings),
    SQLTokenResolver(),
    SQLResultSummarizer(
        lambda: fake_llm,
        SQLSummaryPreviewBuilder(
            max_rows=settings.sql_result_summary_max_rows,
            max_chars=settings.sql_result_summary_max_chars,
        ),
    ),
    ChartMetadataBuilder(),
)
app = create_app(
    settings,
    chat_orchestrator=FakeLLMChatOrchestrator(),
    sql_execution_service=sql_service,
)
