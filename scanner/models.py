"""Pydantic models shared across the scanner.

`Evidence` and `CheckResult` are the core contract from CLAUDE.md — do not change
their shape without asking first.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

CheckStatus = Literal["pass", "warn", "fail", "not_applicable", "error"]
Category = Literal["discovery", "data", "checkout", "protocol", "visibility"]
Effort = Literal["S", "M", "L"]
Platform = Literal["shopify", "woocommerce", "shopware6", "lightspeed", "magento", "other"]
Grade = Literal["Ready", "Partly ready", "Not ready"]


# --- Core check contract ---------------------------------------------------------------


class Evidence(BaseModel):
    url: str | None = None
    detail: str
    snippet: str | None = None


class CheckResult(BaseModel):
    id: str  # stable id from SPEC.md, e.g. "D1.robots_ai_crawlers"
    category: Category
    label: str
    status: CheckStatus
    weight: int  # from SPEC.md
    score_fraction: float = Field(ge=0.0, le=1.0)  # partial credit allowed
    evidence: list[Evidence]
    guidance: str  # fix text from checks/copy, shown when not "pass"
    effort: Effort


# --- Scan inputs -----------------------------------------------------------------------


class ScanOptions(BaseModel):
    checks: list[str] | None = None  # None = all enabled checks
    visibility: bool = False  # V1 costs money -> opt-in
    timeout_s: float = 120.0
    max_pages: int = 40
    lang: Literal["nl", "en"] = "nl"


# --- Fetched data (lives in state so checks never refetch) -----------------------------


class FetchedResource(BaseModel):
    url: str
    final_url: str | None = None  # after redirects
    status_code: int | None = None  # None = network error / not fetched
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None
    error: str | None = None


class SitemapEntry(BaseModel):
    loc: str
    lastmod: str | None = None
    source: str  # sitemap file the entry came from


class SitemapSource(BaseModel):
    url: str
    status_code: int | None
    kind: Literal["urlset", "index", "invalid", "unreachable"]
    entry_count: int = 0
    error: str | None = None


class SitemapInfo(BaseModel):
    from_robots: list[str] = Field(default_factory=list)  # Sitemap: lines in robots.txt
    sources: list[SitemapSource] = Field(default_factory=list)
    entries: list[SitemapEntry] = Field(default_factory=list)
    truncated: bool = False  # more sitemaps/entries existed than we fetched/kept


class SiteBasics(BaseModel):
    final_url: str
    origin: str  # final origin after redirects
    https: bool
    home: FetchedResource | None = None
    robots: FetchedResource | None = None
    sitemap: SitemapInfo = Field(default_factory=SitemapInfo)
    ucp: FetchedResource | None = None


class PlatformInfo(BaseModel):
    platform: Platform = "other"
    signals: list[Evidence] = Field(default_factory=list)


class PageSample(BaseModel):
    products: list[FetchedResource] = Field(default_factory=list)
    categories: list[FetchedResource] = Field(default_factory=list)
    policies: dict[str, FetchedResource] = Field(default_factory=dict)  # "shipping" -> page


class ScanContext(BaseModel):
    """Everything a check may read. Built once after sampling; checks never fetch."""

    origin: str
    options: ScanOptions
    basics: SiteBasics
    platform: PlatformInfo
    pages: PageSample


# --- Output ----------------------------------------------------------------------------


class ScanReport(BaseModel):
    scanner_version: str
    url: str
    origin: str
    started_at: datetime
    finished_at: datetime
    platform: PlatformInfo
    score: float | None  # None until scoring is implemented / nothing scorable
    grade: Grade | None
    excluded_checks: int
    results: list[CheckResult]
