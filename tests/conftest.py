"""Shared test helpers: fixture loading and an offline fake shop via httpx.MockTransport."""

from __future__ import annotations

from pathlib import Path

import httpx

FIXTURES = Path(__file__).parent / "fixtures"

Route = tuple[int, str | bytes] | tuple[int, str | bytes, dict[str, str]] | Exception


def fixture(rel: str) -> str:
    return (FIXTURES / rel).read_text(encoding="utf-8")


class FakeShop:
    """Maps absolute URLs to responses; anything unmapped is a 404. Records requests."""

    def __init__(self, routes: dict[str, Route] | None = None) -> None:
        self.routes: dict[str, Route] = dict(routes or {})
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        route = self.routes.get(str(request.url))
        if route is None:
            return httpx.Response(404, text="not found")
        if isinstance(route, Exception):
            raise route
        status, body, *rest = route
        headers = rest[0] if rest else {}
        content = body.encode() if isinstance(body, str) else body
        return httpx.Response(status, content=content, headers=headers)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)

    def paths(self) -> list[str]:
        return [r.url.path for r in self.requests]
