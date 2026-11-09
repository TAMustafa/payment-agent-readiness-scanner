"""Minimal OpenRouter client (plain httpx; approved by Tarek 2026-11-09 instead of a LangChain
wrapper, because V1 needs raw fields: usage.cost, annotations, server-tool parameters, 402).

Only ever talks to https://openrouter.ai — never to a shop. Docs (read 2026-11-09):
- chat + web search server tool: https://openrouter.ai/docs/guides/features/server-tools/web-search
- usage/cost in every response: https://openrouter.ai/docs/guides/guides/usage-accounting
- key limits + 402: https://openrouter.ai/docs/api-reference/limits
- live prices: GET https://openrouter.ai/api/v1/models (public)
"""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlsplit

import httpx

from scanner import __version__

BASE_URL = "https://openrouter.ai/api/v1"
ALLOWED_HOST = "openrouter.ai"
MAX_RETRY_AFTER_S = 15.0


class OpenRouterError(Exception):
    pass


class BudgetExhausted(OpenRouterError):
    """HTTP 402: key limit or credits used up. Stop all remaining calls."""


class OpenRouterClient:
    def __init__(
        self,
        api_key: str,
        *,
        timeout_s: float = 90.0,
        contact_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "X-Title": "AgentReadyScanner",
            "User-Agent": f"AgentReadyScanner/{__version__}",
        }
        if contact_url:
            headers["HTTP-Referer"] = contact_url
        self._client = httpx.AsyncClient(
            base_url=BASE_URL, headers=headers, timeout=timeout_s, transport=transport
        )

    async def __aenter__(self) -> OpenRouterClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._client.aclose()

    def _check_host(self, path: str) -> None:
        host = urlsplit(str(self._client.base_url.join(path))).hostname
        if host != ALLOWED_HOST:  # defence in depth: V1 must never contact anything else
            raise OpenRouterError(f"refusing request to {host}")

    async def model_prices(self, model_ids: list[str]) -> dict[str, dict[str, float]]:
        """Live USD prices per model: prompt/completion per token, web_search per search."""
        self._check_host("/models")
        resp = await self._client.get("/models")
        resp.raise_for_status()
        out: dict[str, dict[str, float]] = {}
        for m in resp.json().get("data", []):
            if m.get("id") in model_ids:
                p = m.get("pricing") or {}
                out[m["id"]] = {
                    k: float(p.get(k) or 0)
                    for k in ("prompt", "completion", "web_search", "request")
                }
        return out

    async def month_usage(self) -> float | None:
        """USD used by this key this month (GET /key usage_monthly), None if unavailable."""
        self._check_host("/key")
        try:
            resp = await self._client.get("/key")
            resp.raise_for_status()
            value = resp.json().get("data", {}).get("usage_monthly")
            return float(value) if value is not None else None
        except (httpx.HTTPError, ValueError):
            return None

    async def chat(
        self,
        model: str,
        prompt: str,
        *,
        engine: str = "native",
        max_uses: int = 1,
        data_collection: str = "deny",
    ) -> dict[str, Any]:
        """One question with the web-search server tool. Returns the raw response JSON."""
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "tools": [
                {
                    "type": "openrouter:web_search",
                    "parameters": {"engine": engine, "max_uses": max_uses},
                }
            ],
            "provider": {"data_collection": data_collection},
        }
        self._check_host("/chat/completions")
        for attempt in range(3):
            resp = await self._client.post("/chat/completions", json=body)
            if resp.status_code == 402:
                source = _error_meta(resp).get("limit_source", "credits/limit")
                raise BudgetExhausted(f"OpenRouter refused: budget exhausted ({source})")
            if resp.status_code == 429 and attempt < 2:
                await asyncio.sleep(_retry_after(resp))
                continue
            if resp.status_code >= 400:
                raise OpenRouterError(f"HTTP {resp.status_code}: {resp.text[:200]}")
            data: dict[str, Any] = resp.json()
            return data
        raise OpenRouterError("rate limited (HTTP 429) after retries")


def _error_meta(resp: httpx.Response) -> dict[str, Any]:
    try:
        meta = resp.json().get("error", {}).get("metadata") or {}
        return meta if isinstance(meta, dict) else {}
    except ValueError:
        return {}


def _retry_after(resp: httpx.Response) -> float:
    value = resp.headers.get("retry-after", "")
    return min(float(value), MAX_RETRY_AFTER_S) if value.strip().isdigit() else 2.0
