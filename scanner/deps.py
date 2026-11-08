"""Runtime dependencies injected via LangGraph's context (kept out of state so state
stays serialisable and a checkpointer can be added later)."""

from __future__ import annotations

from dataclasses import dataclass

from scanner.fetch.client import PoliteClient


@dataclass
class ScanDeps:
    client: PoliteClient
