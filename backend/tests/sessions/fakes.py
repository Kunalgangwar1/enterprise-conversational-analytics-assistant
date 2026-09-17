"""Small deterministic Redis test double; no server or network is required."""

from collections.abc import Callable
from dataclasses import dataclass

from redis.exceptions import ConnectionError, WatchError


@dataclass
class _Entry:
    value: str
    expires_at: float


class FakeRedisBackend:
    """State shared by independent fake clients, like one Redis server."""

    def __init__(self) -> None:
        self.entries: dict[str, _Entry] = {}
        self.versions: dict[str, int] = {}
        self.now = 0.0
        self.unavailable = False
        self.watch_conflicts_remaining = 0
        self.conflict_hook: Callable[[], None] | None = None
        self.closed_clients = 0

    def advance(self, seconds: float) -> None:
        self.now += seconds

    def purge(self, key: str) -> None:
        entry = self.entries.get(key)
        if entry is not None and entry.expires_at <= self.now:
            del self.entries[key]
            self.versions[key] = self.versions.get(key, 0) + 1


class FakeRedisClient:
    """Subset of synchronous redis-py used by RedisSessionStore."""

    def __init__(self, backend: FakeRedisBackend) -> None:
        self.backend = backend
        self.closed = False

    def _ensure_available(self) -> None:
        if self.backend.unavailable:
            raise ConnectionError("synthetic Redis outage")

    def get(self, key: str) -> str | None:
        self._ensure_available()
        self.backend.purge(key)
        entry = self.backend.entries.get(key)
        return None if entry is None else entry.value

    def set(self, key: str, value: str, *, ex: int) -> bool:
        self._ensure_available()
        self.backend.entries[key] = _Entry(value, self.backend.now + ex)
        self.backend.versions[key] = self.backend.versions.get(key, 0) + 1
        return True

    def delete(self, key: str) -> int:
        self._ensure_available()
        existed = key in self.backend.entries
        self.backend.entries.pop(key, None)
        self.backend.versions[key] = self.backend.versions.get(key, 0) + 1
        return int(existed)

    def pipeline(self) -> "FakePipeline":
        self._ensure_available()
        return FakePipeline(self)

    def close(self) -> None:
        self.closed = True
        self.backend.closed_clients += 1

    def ping(self) -> bool:
        self._ensure_available()
        return True

    def ttl(self, key: str) -> int:
        self.backend.purge(key)
        entry = self.backend.entries.get(key)
        return -2 if entry is None else int(entry.expires_at - self.backend.now)


class FakePipeline:
    """Optimistic transaction behavior needed by the production store tests."""

    def __init__(self, client: FakeRedisClient) -> None:
        self.client = client
        self.watched: dict[str, int] = {}
        self.queued_sets: list[tuple[str, str, int]] = []

    def __enter__(self) -> "FakePipeline":
        return self

    def __exit__(self, *_args: object) -> None:
        self.queued_sets.clear()

    def watch(self, key: str) -> None:
        self.client._ensure_available()
        self.client.backend.purge(key)
        self.watched[key] = self.client.backend.versions.get(key, 0)

    def get(self, key: str) -> str | None:
        return self.client.get(key)

    def multi(self) -> None:
        self.client._ensure_available()

    def set(self, key: str, value: str, *, ex: int) -> "FakePipeline":
        self.queued_sets.append((key, value, ex))
        return self

    def execute(self) -> list[bool]:
        self.client._ensure_available()
        backend = self.client.backend
        if backend.watch_conflicts_remaining:
            backend.watch_conflicts_remaining -= 1
            hook = backend.conflict_hook
            backend.conflict_hook = None
            if hook is not None:
                hook()
            raise WatchError("synthetic conflict")
        for key, watched_version in self.watched.items():
            backend.purge(key)
            if backend.versions.get(key, 0) != watched_version:
                raise WatchError("synthetic version conflict")
        return [self.client.set(key, value, ex=ex) for key, value, ex in self.queued_sets]
