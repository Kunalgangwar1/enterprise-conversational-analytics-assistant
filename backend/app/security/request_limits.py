"""Shared user-text constraints and a bounded ASGI request-body middleware."""

import json
import unicodedata
from typing import Annotated, Any

from pydantic import AfterValidator, StringConstraints

CHAT_MESSAGE_MAX_CHARS = 4_000
CUSTOM_CONTEXT_MAX_CHARS = 8_000
SPECIALIST_QUERY_MAX_CHARS = 4_000


def reject_control_characters(value: str) -> str:
    """Reject C0/C1 control data except normal multiline whitespace."""

    if any(
        unicodedata.category(character) == "Cc" and character not in "\t\n\r" for character in value
    ):
        raise ValueError("text contains unsupported control characters")
    return value


UserQuestion = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=SPECIALIST_QUERY_MAX_CHARS),
    AfterValidator(reject_control_characters),
]
ChatMessageText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=CHAT_MESSAGE_MAX_CHARS),
    AfterValidator(reject_control_characters),
]
CustomContextText = Annotated[
    str,
    StringConstraints(max_length=CUSTOM_CONTEXT_MAX_CHARS),
    AfterValidator(reject_control_characters),
]


class RequestBodyLimitMiddleware:
    """Buffer at most the configured bound and reject oversized streamed bodies."""

    def __init__(self, app: Any, *, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http" or scope.get("method") not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return

        body = bytearray()
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > self.max_body_bytes:
                await self._reject(send)
                return
            body.extend(chunk)
            more_body = message.get("more_body", False)

        replayed = False

        async def replay_receive() -> dict[str, Any]:
            nonlocal replayed
            if replayed:
                return {"type": "http.disconnect"}
            replayed = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, replay_receive, send)

    @staticmethod
    async def _reject(send: Any) -> None:
        content = json.dumps(
            {
                "error": {
                    "code": "request_too_large",
                    "message": "The request body exceeds the configured size limit.",
                }
            },
            separators=(",", ":"),
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(content)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": content})
