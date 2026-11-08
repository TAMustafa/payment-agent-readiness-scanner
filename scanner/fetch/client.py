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
MAX_RETRY_AFTER_S = 60.0  # honour up to this; longer waits end the fetch phase instead
MAX_BACKOFF_S = 4.0  # cap so a rate-limiting host cannot push a scan past its timeout
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
        max_probe_requests: int = 10,
        time_budget_s: float | None = None,
        timeout_s: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.user_agent = user_agent or default_user_agent()
        self.min_interval_s = min_interval_s
        self.max_requests = max_requests
        self.requests_made = 0
        # D2 re-fetches one page with AI user agents: separate small budget, not new pages.
        self.max_probe_requests = max_probe_requests
        self.probe_requests_made = 0
        # Stop fetching before the scan's hard timeout so a partial report still renders.
        self._deadline = time.monotonic() + time_budget_s if time_budget_s else None
        self.stopped_for_time = False
        self.reserve_hit = False  # a request was refused to protect a later step's time
        self._robots: dict[str, RobotsTxt] = {}
        self._host_locks: dict[str, asyncio.Lock] = {}
        self._host_last: dict[str, float] = {}
        self._host_interval: dict[str, float] = {}  # grows on HTTP 429 (adaptive backoff)
        self._host_not_before: dict[str, float] = {}  # from Retry-After
        self.rate_limited: dict[str, int] = {}  # host -> number of 429s seen
        self._timeout_s = timeout_s
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
        probe: bool = False,
        reserve_s: float = 0.0,
    ) -> FetchedResource:
        """GET `url`. Never raises for network/HTTP problems; they land in `.error`.

        `probe=True` counts against the probe budget (D2 user-agent re-fetches).
        `reserve_s`: refuse (without sending) if this request, including any rate-limit
        wait, would cut into the last `reserve_s` seconds kept for later steps.
        """
        host = (urlsplit(url).hostname or "").lower()
        if respect_robots:
            robots = self._robots.get(host)
            if robots is not None and not robots.is_allowed(ROBOTS_TOKEN, url):
                return FetchedResource(
                    url=url, error=f"disallowed by robots.txt for {ROBOTS_TOKEN}"
                )
        if probe:
            if self.probe_requests_made >= self.max_probe_requests:
                return FetchedResource(
                    url=url, error=f"probe budget ({self.max_probe_requests}) exhausted"
                )
            self.probe_requests_made += 1
        else:
            if self.requests_made >= self.max_requests:
                return FetchedResource(
                    url=url, error=f"request budget ({self.max_requests}) exhausted"
                )
            self.requests_made += 1

        headers = {"User-Agent": user_agent} if user_agent else None
        async with self._host_lock(host):
            if self._deadline is not None:
                finish = time.monotonic() + self._pending_wait(host) + self._timeout_s
                if finish > self._deadline:
                    self.stopped_for_time = True
                    return FetchedResource(url=url, error="scan time budget reached")
                if reserve_s and finish > self._deadline - reserve_s:
                    self.reserve_hit = True
                    return FetchedResource(
                        url=url, error="scan time budget reached (time kept for later steps)"
                    )
            await self._wait_turn(host)
            # Stateless requests: no cookies carried between fetches (deterministic results,
            # no session data kept).
            self._client.cookies.clear()
            try:
                async with self._client.stream("GET", url, headers=headers) as resp:
                    raw = await _read_capped(resp)
            except httpx.HTTPError as exc:
                return FetchedResource(url=url, error=f"{type(exc).__name__}: {exc}")
            finally:
                self._host_last[host] = time.monotonic()

        if resp.status_code == 429:
            # Polite backoff: the host says we are too fast -> double our interval for it.
            self.rate_limited[host] = self.rate_limited.get(host, 0) + 1
            current = self._host_interval.get(host, self.min_interval_s)
            retry_after = _retry_after_s(resp.headers.get("retry-after"))
            if retry_after:
                self._host_not_before[host] = time.monotonic() + retry_after
            self._host_interval[host] = min(
                max(current * 2, self.min_interval_s * 2), MAX_BACKOFF_S
            )

        return FetchedResource(
            url=url,
            final_url=str(resp.url),
            status_code=resp.status_code,
            headers={k: v for k, v in resp.headers.items() if k.lower() not in _DROP_HEADERS},
            cookie_names=_cookie_names(resp),
            body=_decode(raw, resp.encoding),
        )

    def _host_lock(self, host: str) -> asyncio.Lock:
        return self._host_locks.setdefault(host, asyncio.Lock())

    def time_left(self) -> float:
        """Seconds until the fetch deadline (inf when no time budget is set)."""
        if self._deadline is None:
            return float("inf")
        return self._deadline - time.monotonic()

    def _pending_wait(self, host: str) -> float:
        now = time.monotonic()
        wait = max(0.0, self._host_not_before.get(host, 0.0) - now)
        last = self._host_last.get(host)
        if last is not None:
            interval = self._host_interval.get(host, self.min_interval_s)
            wait = max(wait, interval - (now - last))
        return wait

    async def _wait_turn(self, host: str) -> None:
        delay = self._pending_wait(host)
        if delay > 0:
            await asyncio.sleep(delay)


def _retry_after_s(value: str | None) -> float | None:
    """Retry-After in seconds (RFC 9110 §10.2.3); HTTP-date form ignored. Capped."""
    if value is None or not value.strip().isdigit():
        return None
    return min(float(value.strip()), MAX_RETRY_AFTER_S)


def _cookie_names(resp: httpx.Response) -> list[str]:
    names = (c.split("=", 1)[0].strip() for c in resp.headers.get_list("set-cookie"))
    return sorted({n for n in names if n})


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
