"""Atomic local JSON implementation of the session-store contract."""

import os
import tempfile
from pathlib import Path
from threading import RLock

from pydantic import ValidationError

from app.sessions.exceptions import SessionStoreError
from app.sessions.identity import SessionIdentity, derive_session_storage_key
from app.sessions.models import SessionState


class JsonFileSessionStore:
    """Persist one validated JSON document per browser-session/tab pair."""

    def __init__(self, session_directory: Path) -> None:
        self._session_directory = session_directory
        self._lock = RLock()

    @property
    def session_directory(self) -> Path:
        """Return the configured generated-artifact directory."""

        return self._session_directory

    def load(self, identity: SessionIdentity) -> SessionState | None:
        """Load and validate state without recovering silently from corruption."""

        path = self.path_for(identity)
        with self._lock:
            try:
                payload = path.read_text(encoding="utf-8")
            except FileNotFoundError:
                return None
            except OSError as exc:
                raise SessionStoreError("unable to read persisted session state") from exc

            try:
                state = SessionState.model_validate_json(payload)
            except ValidationError as exc:
                raise SessionStoreError("persisted session state is corrupted") from exc

            if (
                state.browser_session_id != identity.browser_session_id
                or state.tab_id != identity.tab_id
            ):
                raise SessionStoreError("persisted session identity does not match its storage key")
            return state

    def save(self, state: SessionState) -> None:
        """Atomically replace a state file with complete validated JSON."""

        identity = SessionIdentity(
            browser_session_id=state.browser_session_id,
            tab_id=state.tab_id,
        )
        final_path = self.path_for(identity)
        temporary_path: Path | None = None

        with self._lock:
            try:
                # Refuse to replace unreadable/corrupted existing state silently.
                self.load(identity)
                self._session_directory.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=self._session_directory,
                    prefix=f".{final_path.name}.",
                    suffix=".tmp",
                    delete=False,
                ) as temporary_file:
                    temporary_path = Path(temporary_file.name)
                    temporary_file.write(state.model_dump_json(indent=2))
                    temporary_file.write("\n")
                    temporary_file.flush()
                    os.fsync(temporary_file.fileno())
                os.replace(temporary_path, final_path)
            except OSError as exc:
                raise SessionStoreError("unable to persist session state") from exc
            finally:
                if temporary_path is not None:
                    try:
                        temporary_path.unlink(missing_ok=True)
                    except OSError:
                        pass

    def delete(self, identity: SessionIdentity) -> None:
        """Delete a state document without failing when it is already absent."""

        with self._lock:
            try:
                self.path_for(identity).unlink(missing_ok=True)
            except OSError as exc:
                raise SessionStoreError("unable to delete persisted session state") from exc

    def path_for(self, identity: SessionIdentity) -> Path:
        """Return the safe hash-derived path for a validated identity."""

        storage_key = derive_session_storage_key(
            identity.browser_session_id,
            identity.tab_id,
        )
        return self._session_directory / f"session_{storage_key}.json"
