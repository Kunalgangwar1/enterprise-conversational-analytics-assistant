"""Dependency-aware readiness checks that never call external AI providers."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from app.observability.metrics import get_metrics


@dataclass(frozen=True, slots=True)
class ReadinessProbe:
    """One fixed-name internal dependency probe."""

    dependency: str
    check: Callable[[], object]


class ReadinessService:
    """Run bounded internal probes and report only an aggregate safe result."""

    def __init__(self, probes: Iterable[ReadinessProbe]) -> None:
        self._probes = tuple(probes)

    def is_ready(self) -> bool:
        ready = True
        for probe in self._probes:
            try:
                probe.check()
            except Exception:
                ready = False
                get_metrics().record(
                    "readiness.failed",
                    attributes={"dependency": probe.dependency},
                )
        return ready
