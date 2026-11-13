"""FastAPI website: one page (static/index.html) and one JSON endpoint (POST /api/check).

Abuse limits, because anyone can submit any URL:
- per visitor IP: RATE_PER_IP checks per minute; per checked host: RATE_PER_TARGET per minute
  (so the site cannot be used to hammer a shop); at most MAX_CONCURRENT checks at once;
- the fetcher refuses private addresses, never follows redirects and sends GET only;
- request bodies are bounded (URL 2 kB, sample 256 kB).
Privacy: the pasted sample is never logged or stored; reports are not persisted.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ap2check import __version__
from ap2check.fetch import Resolver, system_resolver
from ap2check.models import Report
from ap2check.runner import InvalidTarget, check_merchant, normalise_target

STATIC = Path(__file__).parent / "static"
RATE_PER_IP = 6
RATE_PER_TARGET = 4
MAX_CONCURRENT = 4
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)


class CheckRequest(BaseModel):
    url: str = Field(max_length=2048)
    sample: str | None = Field(default=None, max_length=256_000)


class RateLimiter:
    """Sliding one-minute window per key, in memory (one process)."""

    def __init__(self, per_minute: int, clock: Callable[[], float] = time.monotonic) -> None:
        self.per_minute = per_minute
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = self._clock()
        hits = self._hits[key]
        while hits and now - hits[0] > 60:
            hits.popleft()
        if len(hits) >= self.per_minute:
            return False
        hits.append(now)
        return True


def create_app(
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    resolver: Resolver = system_resolver,
    min_interval_s: float = 1.0,
    clock: Callable[[], float] = time.monotonic,
) -> FastAPI:
    app = FastAPI(
        title="AP2 Readiness Check",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    per_ip = RateLimiter(RATE_PER_IP, clock)
    per_target = RateLimiter(RATE_PER_TARGET, clock)
    slots = asyncio.Semaphore(MAX_CONCURRENT)

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC / "index.html", media_type="text/html")

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.post("/api/check")
    async def api_check(body: CheckRequest, request: Request) -> Report:
        try:
            target = normalise_target(body.url)
        except InvalidTarget as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        client = request.client.host if request.client else "unknown"
        if not per_ip.allow(client):
            raise HTTPException(429, "Too many checks from your address; try again in a minute.")
        if not per_target.allow(target):
            raise HTTPException(
                429, "This shop was checked several times just now; try again in a minute."
            )
        if slots.locked():
            raise HTTPException(503, "The checker is busy; try again in a few seconds.")
        async with slots:
            return await check_merchant(
                target,
                body.sample,
                transport=transport,
                resolver=resolver,
                min_interval_s=min_interval_s,
            )

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


app = create_app()
