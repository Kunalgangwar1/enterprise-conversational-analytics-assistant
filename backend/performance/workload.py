"""Pure workload configuration kept importable without gevent monkey-patching."""

import os

REQUEST_NAMES = {
    "health": "GET /api/health",
    "discovery": "POST /api/data-discovery/query",
    "dashboard": "GET /api/dashboards/overview",
    "chat": "POST /chat (FakeLLM target required)",
    "sql": "POST /chat/execute-sql",
    "session": "POST /chat/select-mode",
}


def require_fake_llm_target() -> None:
    """Refuse any explicit attempt to enable live-provider load."""

    if os.getenv("PERFORMANCE_ALLOW_LIVE_LLM", "false").lower() == "true":
        raise RuntimeError("Performance harness refuses live/paid LLM execution")
