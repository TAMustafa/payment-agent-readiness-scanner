"""LangGraph state for one scan."""

from __future__ import annotations

import operator
from datetime import datetime
from typing import Annotated, NotRequired, TypedDict

from scanner.models import (
    CheckResult,
    PageSample,
    PlatformInfo,
    ScanContext,
    ScanOptions,
    ScanReport,
    SiteBasics,
)


class ScanState(TypedDict):
    # inputs
    url: str
    options: ScanOptions
    started_at: datetime
    # filled by nodes
    origin: NotRequired[str]
    basics: NotRequired[SiteBasics]
    platform: NotRequired[PlatformInfo]
    pages: NotRequired[PageSample]
    # parallel check results are merged by list concatenation
    results: Annotated[list[CheckResult], operator.add]
    score: NotRequired[float | None]
    excluded_checks: NotRequired[int]
    report: NotRequired[ScanReport]


class RunCheckInput(TypedDict):
    """Payload sent to one `run_check` invocation via the Send API."""

    check_id: str
    ctx: ScanContext
