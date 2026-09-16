"""Optional internal live multi-hop smoke entry point."""

import argparse

from app.core.config import get_settings
from app.core.feature_flags import get_feature_flags
from app.db.query.factory import build_query_executor
from app.db.session import create_database_engine
from app.llm.factory import create_llm_client
from app.metadata.refresh import build_registry
from app.nlp2sql.agent import NLP2SQLAgent
from app.nlp2sql.multihop.factory import build_multihop_agent


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one configured multi-hop SQL smoke")
    parser.add_argument("question", help="Privacy-safe synthetic analytical question")
    args = parser.parse_args()
    settings = get_settings()
    flags = get_feature_flags().reasoning
    metadata_engine = create_database_engine(str(settings.database_url))
    try:
        llm_client = create_llm_client(settings)
        standard_agent = NLP2SQLAgent(build_registry(metadata_engine), llm_client)
        agent = build_multihop_agent(
            settings=settings,
            flags=flags,
            llm_client=llm_client,
            nlp2sql_agent=standard_agent,
            query_executor=build_query_executor(settings),
        )
        result = agent.run(args.question)
    finally:
        metadata_engine.dispose()
    print(result.answer_markdown)


if __name__ == "__main__":
    main()
