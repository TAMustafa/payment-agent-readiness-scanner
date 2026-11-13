"""Pydantic models shared by the fetcher, the checks, the CLI and the web API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

CheckStatus = Literal["pass", "warn", "fail", "not_applicable", "error"]
Stage = Literal["discovery", "checkout", "ap2", "a2a", "signature"]
VerdictLevel = Literal[
    "not_discoverable",  # no UCP profile and no A2A card with the AP2 extension
    "no_ap2",  # discoverable, but AP2 not declared
    "incomplete",  # AP2 declared, but something an agent needs is broken
    "untested",  # declared and well-formed; merchant signature not tested (no sample)
    "signature_failed",  # a sample was given and its signature did not verify
    "ready",  # declared, well-formed, sample signature verified
    "unknown",  # the shop could not be read (blocked, timeout, robots)
]


class FetchedResource(BaseModel):
    url: str
    status_code: int | None = None  # None = network error / not fetched
    headers: dict[str, str] = Field(default_factory=dict)  # lower-cased; Set-Cookie dropped
    body: str | None = None
    truncated: bool = False  # body was longer than the read cap
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status_code is not None and 200 <= self.status_code < 300 and bool(self.body)

    def unavailable_reason(self) -> str:
        return self.error or f"HTTP {self.status_code}"


class Evidence(BaseModel):
    url: str | None = None
    detail: str
    snippet: str | None = None


class CheckResult(BaseModel):
    id: str  # stable id from SPEC.md, e.g. "A1.ap2_capability"
    stage: Stage
    label: str
    status: CheckStatus
    evidence: list[Evidence]
    guidance: str  # fix text, shown when not "pass"
    spec: str  # URL of the spec section the check is based on


class Verdict(BaseModel):
    level: VerdictLevel
    title: str
    summary: str


class RequestLog(BaseModel):
    url: str
    status: int | None
    error: str | None = None


class Report(BaseModel):
    target: str  # https origin that was checked
    checked_at: str  # ISO 8601, UTC
    tool_version: str
    spec_versions: dict[str, str]
    verdict: Verdict
    results: list[CheckResult]
    requests: list[RequestLog]  # every request we sent, for transparency
    notes: list[str]  # standing caveats (protocol maturity, what cannot be tested)


class CheckInput(BaseModel):
    """Everything the checks read. Collected before any check runs; checks never fetch."""

    target: str
    profile: FetchedResource | None = None  # /.well-known/ucp
    profile_json: Any = None  # parsed body, or None
    agent_card: FetchedResource | None = None  # /.well-known/agent-card.json
    agent_card_json: Any = None
    sample: str | None = None  # merchant-supplied checkout response or checkout_jwt
