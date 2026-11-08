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
