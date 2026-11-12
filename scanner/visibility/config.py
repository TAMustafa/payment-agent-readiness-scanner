"""Load config/visibility.toml into validated settings (stdlib tomllib, no new dependency)."""

from __future__ import annotations

import math
import tomllib
from pathlib import Path

from pydantic import BaseModel, Field

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "visibility.toml"


class Snapshot(BaseModel):
    prompt_per_m: float
    completion_per_m: float
    web_search: float


class Assistant(BaseModel):
    name: str
    model: str
    engine: str = "native"
    snapshot: Snapshot
    per_question_usd: float
    # Native search ignores max_uses; average searches per question seen live (estimate).
    expected_searches: float | None = None


class Budget(BaseModel):
    monthly_usd: float = Field(gt=0)
    per_scan_usd: float = Field(gt=0)
    ledger_path: str = "scans/visibility_ledger.jsonl"


class Run(BaseModel):
    brand_questions: int = 2
    category_questions: int = 8
    runs: int = Field(default=2, ge=1, le=3)
    language: str = "nl"
    country: str = "NL"
    max_searches_per_question: int = Field(default=1, ge=1)
    worst_case_searches: int = Field(default=2, ge=1)
    concurrency: int = Field(default=4, ge=1, le=10)
    timeout_s: float = 90.0
    # Until verified that usage.cost includes the search fee, add it ourselves: this can
    # only over-count, never under-count (conservative for the budget).
    add_search_fee_to_cost: bool = True


class Privacy(BaseModel):
    data_collection: str = "deny"


class VisibilityConfig(BaseModel):
    budget: Budget
    run: Run = Field(default_factory=Run)
    privacy: Privacy = Field(default_factory=Privacy)
    assistants: list[Assistant] = Field(min_length=1)

    def max_duration_s(self) -> float:
        """Upper bound for a V1 run: every call is cut off at `timeout_s`, and at most
        `concurrency` run at once. The CLI adds this to the scan's hard timeout."""
        calls = len(self.assistants) * self.run.runs
        calls *= self.run.brand_questions + self.run.category_questions
        return math.ceil(calls / self.run.concurrency) * self.run.timeout_s


def load_config(path: Path | None = None) -> VisibilityConfig:
    with open(path or DEFAULT_PATH, "rb") as f:
        return VisibilityConfig.model_validate(tomllib.load(f))
