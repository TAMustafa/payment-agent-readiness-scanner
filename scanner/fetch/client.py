"""Polite, read-only HTTP client (CLAUDE.md rule 2).

- identifies as AgentReadyScanner/<version> (+contact URL)
- respects robots.txt for our own product token (once robots is registered for a host)
- max 1 request/second per host, hard request budget per scan
- GET only; Set-Cookie headers are dropped (no personal data stored)
"""

from __future__ import annotations

import asyncio
import gzip
import io
import os
import time
from types import TracebackType
from urllib.parse import urlsplit

import httpx

from scanner import __version__
from scanner.fetch.robots import RobotsTxt
from scanner.models import FetchedResource

ROBOTS_TOKEN = "AgentReadyScanner"
# .invalid is a reserved TLD (RFC 2606): an obvious placeholder until a real URL is set.
DEFAULT_CONTACT_URL = "https://contact-url-not-configured.invalid"
MAX_BODY_BYTES = 5_000_000
_DROP_HEADERS = {"set-cookie"}


def default_user_agent() -> str:
    contact = os.environ.get("SCANNER_CONTACT_URL", DEFAULT_CONTACT_URL)
    return f"{ROBOTS_TOKEN}/{__version__} (+{contact})"


class PoliteClient:
    def __init__(
        self,
        *,
        user_agent: str | None = None,
        min_interval_s: float = 1.0,
        max_requests: int = 40,
        timeout_s: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.user_agent = user_agent or default_user_agent()
        self.min_interval_s = min_interval_s
        self.max_requests = max_requests
        self.requests_made = 0
        self._robots: dict[str, RobotsTxt] = {}
        self._host_locks: dict[str, asyncio.Lock] = {}
        self._host_last: dict[str, float] = {}
        self._client = httpx.AsyncClient(
            headers={"User-Agent": self.user_agent},
            timeout=timeout_s,
            follow_redirects=True,
            max_redirects=5,
            transport=transport,
        )

    async def __aenter__(self) -> PoliteClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._client.aclose()

    def set_robots(self, host: str, robots: RobotsTxt) -> None:
        self._robots[host.lower()] = robots

    async def get(
        self,
        url: str,
        *,
        user_agent: str | None = None,
        respect_robots: bool = True,
    ) -> FetchedResource:
        """GET `url`. Never raises for network/HTTP problems; they land in `.error`."""
        host = (urlsplit(url).hostname or "").lower()
        if respect_robots:
            robots = self._robots.get(host)
            if robots is not None and not robots.is_allowed(ROBOTS_TOKEN, url):
                return FetchedResource(
                    url=url, error=f"disallowed by robots.txt for {ROBOTS_TOKEN}"
                )
        if self.requests_made >= self.max_requests:
            return FetchedResource(url=url, error=f"request budget ({self.max_requests}) exhausted")
        self.requests_made += 1

        headers = {"User-Agent": user_agent} if user_agent else None
        async with self._host_lock(host):
            await self._wait_turn(host)
            try:
                async with self._client.stream("GET", url, headers=headers) as resp:
                    raw = await _read_capped(resp)
            except httpx.HTTPError as exc:
                return FetchedResource(url=url, error=f"{type(exc).__name__}: {exc}")
            finally:
                self._host_last[host] = time.monotonic()

        return FetchedResource(
            url=url,
            final_url=str(resp.url),
            status_code=resp.status_code,
            headers={k: v for k, v in resp.headers.items() if k.lower() not in _DROP_HEADERS},
            body=_decode(raw, resp.encoding),
        )

    def _host_lock(self, host: str) -> asyncio.Lock:
        return self._host_locks.setdefault(host, asyncio.Lock())

    async def _wait_turn(self, host: str) -> None:
        last = self._host_last.get(host)
        if last is not None:
            delay = self.min_interval_s - (time.monotonic() - last)
            if delay > 0:
                await asyncio.sleep(delay)


async def _read_capped(resp: httpx.Response) -> bytes:
    buf = bytearray()
    async for chunk in resp.aiter_bytes():
        buf.extend(chunk)
        if len(buf) >= MAX_BODY_BYTES:
            break
    return bytes(buf[:MAX_BODY_BYTES])


def _decode(raw: bytes, encoding: str | None) -> str:
    if raw[:2] == b"\x1f\x8b":  # gzip file (e.g. sitemap.xml.gz), not Content-Encoding
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as gz:
                raw = gz.read(MAX_BODY_BYTES)
        except (OSError, EOFError):
            pass
    return raw.decode(encoding or "utf-8", errors="replace")
