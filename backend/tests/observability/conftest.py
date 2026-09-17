from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.observability.metrics import ApplicationMetrics, set_metrics
from app.observability.tracing import set_tracer


@pytest.fixture(autouse=True)
def reset_observability_globals() -> Iterator[None]:
    set_metrics(ApplicationMetrics(None))
    set_tracer(None)
    yield
    set_metrics(ApplicationMetrics(None))
    set_tracer(None)
