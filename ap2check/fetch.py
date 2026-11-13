"""Polite, read-only fetcher for a merchant's public discovery documents.

Rules (CLAUDE.md "Non-negotiable rules"):
- GET only. The fetcher is the only network code in the package (tests/test_safety.py).
- Identifies as AP2ReadinessCheck/<version> (+contact URL); never impersonates an agent.
- HTTPS only; redirects are never followed. UCP: consumers "MUST NOT follow redirects (3xx)"
  and "MUST reject URLs not served over HTTPS"
  (https://ucp.dev/2026-08-25/specification/overview/ #fetching). A redirect is reported.
- Refuses private / local / special-use addresses, both by name and after DNS resolution,
  because the website lets anyone submit a URL (SSRF guard). Limit: DNS rebinding between our
  lookup and httpx's own lookup is not prevented; redirects are off, which removes the
  common bypass.
- Respects robots.txt for our own product token; at most 1 request/second per host; a small
  fixed request budget per check; body read capped; Set-Cookie dropped; no cookie jar.
"""

from __future__ import annotations

import asyncio
import ipaddress
import os
import socket
import time
from collections.abc import Awaitable, Callable
from types import TracebackType
from urllib.parse import urlsplit

import httpx

from ap2check import __version__
from ap2check.models import FetchedResource, RequestLog
from ap2check.robots import RobotsTxt, robots_from_resource

ROBOTS_TOKEN = "AP2ReadinessCheck"
DEFAULT_CONTACT_URL = "https://contact-url-not-configured.invalid"
MAX_BODY_BYTES = 1_000_000  # UCP consumers must accept >= 128 KiB; we read more to report size
MAX_REQUESTS = 6  # robots.txt + ucp + agent card, with room for retries of none
TIMEOUT_S = 10.0
_LOCAL_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home.arpa", ".test")

Resolver = Callable[[str], Awaitable[list[str]]]


def default_user_agent() -> str:
    contact = os.environ.get("AP2CHECK_CONTACT_URL", DEFAULT_CONTACT_URL)
    return f"{ROBOTS_TOKEN}/{__version__} (+{contact})"


def private_host(host: str | None) -> bool:
    """True for names/literals that are never a public merchant: localhost, private,
    link-local or reserved IPs (cloud metadata 169.254.169.254), local-only suffixes."""
    h = (host or "").lower().strip("[]").rstrip(".")
    if not h:
        return True
    try:
        return not ipaddress.ip_address(h).is_global
    except ValueError:
        pass
    last = h.rsplit(".", 1)[-1]
    return (
        "." not in h  # single-label names only resolve locally
        or h.endswith(_LOCAL_SUFFIXES)
        or last.isdigit()  # odd IPv4 spellings (127.1): no TLD is numeric
        or last.startswith("0x")
    )


async def system_resolver(host: str) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    return sorted({str(info[4][0]) for info in infos})


class Fetcher:
    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        resolver: Resolver = system_resolver,
        min_interval_s: float = 1.0,
        max_requests: int = MAX_REQUESTS,
    ) -> None:
        self.user_agent = default_user_agent()
        self.min_interval_s = min_interval_s
        self.max_requests = max_requests
        self.log: list[RequestLog] = []
        self._resolver = resolver
        self._robots: dict[str, RobotsTxt | None] = {}
        self._resolved_ok: dict[str, str | None] = {}  # host -> refusal reason or None
        self._last: dict[str, float] = {}
        self._client = httpx.AsyncClient(
            headers={"User-Agent": self.user_agent, "Accept": "application/json"},
            timeout=TIMEOUT_S,
            follow_redirects=False,
            transport=transport,
        )

    async def __aenter__(self) -> Fetcher:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._client.aclose()

    async def _refusal(self, host: str) -> str | None:
        if private_host(host):
            return f"refused: private or local address ({host})"
        if host not in self._resolved_ok:
            try:
                addrs = await self._resolver(host)
            except OSError as exc:
                self._resolved_ok[host] = f"DNS lookup failed for {host}: {exc}"
            else:
                bad = [a for a in addrs if private_host(a)]
                self._resolved_ok[host] = (
                    f"refused: {host} resolves to a private address ({bad[0]})"
                    if bad or not addrs
                    else None
                )
        return self._resolved_ok[host]

    async def get(self, url: str, *, respect_robots: bool = True) -> FetchedResource:
        """GET `url`. Never raises for network/HTTP problems; they land in `.error`."""
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if parts.scheme != "https":
            return self._logged(FetchedResource(url=url, error="refused: not https"))
        refusal = await self._refusal(host)
        if refusal:
            return self._logged(FetchedResource(url=url, error=refusal))
        if respect_robots:
            robots = await self._robots_for(f"https://{parts.netloc}")
            if robots is not None and not robots.is_allowed(ROBOTS_TOKEN, url):
                return self._logged(
                    FetchedResource(url=url, error=f"disallowed by robots.txt for {ROBOTS_TOKEN}")
                )
        return await self._send(url, host)

    async def _robots_for(self, origin: str) -> RobotsTxt | None:
        if origin not in self._robots:
            res = await self._send(f"{origin}/robots.txt", urlsplit(origin).hostname or "")
            self._robots[origin] = robots_from_resource(res) if res.status_code else None
        return self._robots[origin]

    async def _send(self, url: str, host: str) -> FetchedResource:
        if len(self.log) >= self.max_requests:
            return self._logged(FetchedResource(url=url, error="request budget exhausted"))
        wait = self._last.get(host, 0.0) + self.min_interval_s - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            async with asyncio.timeout(TIMEOUT_S):
                async with self._client.stream("GET", url) as resp:
                    raw, truncated = await _read_capped(resp)
        except TimeoutError:
            return self._logged(FetchedResource(url=url, error=f"timeout after {TIMEOUT_S:g} s"))
        except httpx.HTTPError as exc:
            return self._logged(FetchedResource(url=url, error=f"{type(exc).__name__}: {exc}"))
        finally:
            self._last[host] = time.monotonic()
        headers = {k.lower(): v for k, v in resp.headers.items() if k.lower() != "set-cookie"}
        body = raw.decode(resp.encoding or "utf-8", errors="replace") if raw else None
        return self._logged(
            FetchedResource(
                url=url,
                status_code=resp.status_code,
                headers=headers,
                body=body,
                truncated=truncated,
            )
        )

    def _logged(self, res: FetchedResource) -> FetchedResource:
        self.log.append(RequestLog(url=res.url, status=res.status_code, error=res.error))
        return res


async def _read_capped(resp: httpx.Response) -> tuple[bytes, bool]:
    buf = bytearray()
    async for chunk in resp.aiter_bytes():
        buf.extend(chunk)
        if len(buf) > MAX_BODY_BYTES:
            return bytes(buf[:MAX_BODY_BYTES]), True
    return bytes(buf), False
