import os
from unittest.mock import patch

import pytest

from performance.workload import REQUEST_NAMES, require_fake_llm_target


def test_request_names_are_stable_and_normalized() -> None:
    assert len(REQUEST_NAMES.values()) == len(set(REQUEST_NAMES.values()))
    assert all("?" not in name for name in REQUEST_NAMES.values())
    assert REQUEST_NAMES["chat"].endswith("FakeLLM target required)")


def test_workload_refuses_live_llm_flag() -> None:
    with patch.dict(os.environ, {"PERFORMANCE_ALLOW_LIVE_LLM": "true"}):
        with pytest.raises(RuntimeError, match="refuses live/paid"):
            require_fake_llm_target()
