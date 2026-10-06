"""Read-only HTTP client. Every connector uses this; it refuses write methods.

Allowed: GET. POST only to OAuth token endpoints and Microsoft Graph `/search/query`.
Bodies are never logged: only method, host, path, status and timing.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

import httpx

log = logging.getLogger(__name__)
# httpx logs full URLs (query strings can hold tokens); keep it quiet.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_RETRIES = 3


class WriteRefused(Exception):
    """A connector tried an HTTP method or endpoint that could change data."""


def post_allowed(url: str) -> bool:
    parts = urlsplit(url)
    path = parts.path.rstrip("/")
    if (
        path.endswith("/oauth2/v2.0/token")
        or path.endswith("/oauth2/token")
        or path.endswith("/token")
    ):
        return True
    return parts.hostname == "graph.microsoft.com" and path.endswith("/search/query")


class ReadOnlyClient:
    def __init__(
        self,
        base_url: str = "",
        headers: dict[str, str] | None = None,
        timeout: float = 20.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        backoff: float = 0.5,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url, headers=headers or {}, timeout=timeout, transport=transport
        )
        self._sleep = sleep
        self._backoff = backoff

    def get(
        self, url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None
    ) -> httpx.Response:
        return self._send("GET", url, params=params, headers=headers)

    def post(
        self, url: str, *, json: Any = None, data: Any = None, headers: dict[str, str] | None = None
    ) -> httpx.Response:
        full = str(self._client.base_url.join(url)) if self._client.base_url else url
        if not post_allowed(full):
            raise WriteRefused(
                f"POST is not allowed to {urlsplit(full).hostname}{urlsplit(full).path}"
            )
        return self._send("POST", url, json=json, data=data, headers=headers)

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        method = method.upper()
        if method == "GET":
            return self.get(url, **kwargs)
        if method == "POST":
            return self.post(url, **kwargs)
        raise WriteRefused(f"HTTP method {method} is not allowed (connectors are read only)")

    put = patch = delete = None  # type: ignore[assignment]  # explicit: no write helpers

    def _send(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        attempt = 0
        while True:
            started = time.monotonic()
            try:
                response = self._client.request(method, url, **kwargs)
            except httpx.TransportError as exc:
                if attempt >= MAX_RETRIES:
                    raise
                log.warning(
                    "http transport error", extra={"method": method, "error": type(exc).__name__}
                )
                self._wait(attempt, None)
                attempt += 1
                continue
            parts = urlsplit(str(response.request.url))
            log.info(
                "http",
                extra={
                    "method": method,
                    "host": parts.hostname,
                    "path": parts.path,
                    "status": response.status_code,
                    "ms": int((time.monotonic() - started) * 1000),
                },
            )
            if response.status_code in RETRY_STATUSES and attempt < MAX_RETRIES:
                self._wait(attempt, response.headers.get("Retry-After"))
                attempt += 1
                continue
            response.raise_for_status()
            return response

    def _wait(self, attempt: int, retry_after: str | None) -> None:
        delay = self._backoff * (2**attempt)
        if retry_after and retry_after.isdigit():
            delay = max(delay, float(retry_after))
        self._sleep(min(delay, 60.0))

    def close(self) -> None:
        self._client.close()
