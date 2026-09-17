"""Track constructed external-provider clients for process shutdown."""

from __future__ import annotations

from threading import Lock
from typing import Protocol, TypeVar
from weakref import WeakSet


class Closable(Protocol):
    def close(self) -> None: ...


_lock = Lock()
_resources: WeakSet[Closable] = WeakSet()
_ClosableT = TypeVar("_ClosableT", bound=Closable)


def register_provider_resource(resource: _ClosableT) -> _ClosableT:
    with _lock:
        _resources.add(resource)
    return resource


def close_provider_resources() -> None:
    with _lock:
        resources = list(_resources)
        _resources.clear()
    for resource in resources:
        try:
            resource.close()
        except Exception:
            # Shutdown is best effort; provider errors must not block application termination.
            continue
