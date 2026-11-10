"""LangGraph state for one scan."""

from __future__ import annotations

import operator
from datetime import datetime
from typing import Annotated, NotRequired, TypedDict

from scanner.models import (
    AgentEndpoints,
    AgentProbes,
    CheckoutProbe,
    CheckResult,
    PageSample,
    PlatformInfo,
    ScanContext,
    ScanOptions,
    ScanReport,
    SiteBasics,
    VisibilityResult,
)
from scanner.report.scoring import ScoreSummary


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
    agent_probes: NotRequired[AgentProbes]
    endpoints: NotRequired[AgentEndpoints]
    checkout: NotRequired[CheckoutProbe]
    visibility: NotRequired[VisibilityResult]
    # parallel check results are merged by list concatenation
    results: Annotated[list[CheckResult], operator.add]
    scoring: NotRequired[ScoreSummary]
    report: NotRequired[ScanReport]


class RunCheckInput(TypedDict):
    """Payload sent to one `run_check` invocation via the Send API."""

    check_id: str
    ctx: ScanContext
