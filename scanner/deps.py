"""Runtime dependencies injected via LangGraph's context (kept out of state so state
stays serialisable and a checkpointer can be added later)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from scanner.fetch.client import PoliteClient


@dataclass
class ScanDeps:
    client: PoliteClient
    # Tests serve a fake shop to the headless browser through this Playwright route hook.
    browser_route_hook: Callable[[Any], Awaitable[None]] | None = None
    # Tests: fake OpenRouter (httpx MockTransport), config and ledger location for V1.
    openrouter_transport: Any = None
    visibility_config_path: str | None = None
    visibility_ledger_path: str | None = None
