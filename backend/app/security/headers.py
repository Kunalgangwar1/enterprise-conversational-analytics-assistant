"""Response-header middleware for authenticated and sensitive API traffic."""

from typing import Any


class SecurityHeadersMiddleware:
    """Attach conservative API response headers without changing local transport."""

    def __init__(
        self,
        app: Any,
        *,
        enabled: bool,
        hsts_enabled: bool,
        hsts_max_age_seconds: int,
    ) -> None:
        self.app = app
        self.enabled = enabled
        self.hsts_enabled = hsts_enabled
        self.hsts_max_age_seconds = hsts_max_age_seconds

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http" or not self.enabled:
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                names = {name.lower() for name, _value in headers}
                additions = {
                    b"x-content-type-options": b"nosniff",
                    b"referrer-policy": b"no-referrer",
                    b"x-frame-options": b"DENY",
                    b"permissions-policy": b"camera=(), microphone=(), geolocation=(), payment=()",
                    b"cache-control": b"no-store",
                }
                path = scope.get("path", "")
                if path not in {"/docs", "/redoc", "/openapi.json"}:
                    additions[b"content-security-policy"] = (
                        b"default-src 'none'; frame-ancestors 'none'"
                    )
                if self.hsts_enabled:
                    additions[b"strict-transport-security"] = (
                        f"max-age={self.hsts_max_age_seconds}".encode()
                    )
                headers.extend(
                    (name, value) for name, value in additions.items() if name not in names
                )
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)
