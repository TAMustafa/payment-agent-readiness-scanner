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
    visibility_prompts_file: str | None = None  # operator override: one question per line
    timeout_s: float = 120.0
    max_pages: int = 40
    # Small samples so rate-limiting shops (Shopify 429 + Retry-After 60) still yield data
    # within the time budget; decided 2026-11-08 over longer scans.
    max_products: int = 8
    max_categories: int = 2
    lang: Literal["nl", "en"] = "en"  # English default (Tarek, 2026-11-10)
    # D5 manual input (never guessed): Merchant Center feed active + disapproval percentage
    merchant_center_active: bool | None = None
    merchant_center_disapproved_pct: float | None = Field(default=None, ge=0, le=100)
    # Checkout probe (step 2) is opt-in because it adds an item to an anonymous cart:
    # `checkout` = operator has permission to test this shop (robots.txt still respected);
    # `checkout_consent` = the merchant asked for this scan: implies `checkout` and may enter
    # cart/checkout paths that robots.txt disallows (decided 2026-11-08).
    checkout: bool = False
    checkout_consent: bool = False
    artifacts_dir: str | None = None  # screenshots go here (only when --out is given)


# --- Fetched data (lives in state so checks never refetch) -----------------------------


class FetchedResource(BaseModel):
    url: str

    @property
    def ok(self) -> bool:
        """2xx with a body: usable as page content (a 429/403/challenge page is not)."""
        return self.status_code is not None and 200 <= self.status_code < 300 and bool(self.body)

    def unavailable_reason(self) -> str:
        return self.error or f"HTTP {self.status_code}"

    final_url: str | None = None  # after redirects
    status_code: int | None = None  # None = network error / not fetched
    headers: dict[str, str] = Field(default_factory=dict)  # Set-Cookie removed
    cookie_names: list[str] = Field(default_factory=list)  # names only, never values
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


class PlatformInfo(BaseModel):
    platform: Platform = "other"
    signals: list[Evidence] = Field(default_factory=list)


class PageSample(BaseModel):
    products: list[FetchedResource] = Field(default_factory=list)
    categories: list[FetchedResource] = Field(default_factory=list)
    policies: dict[str, FetchedResource] = Field(default_factory=dict)  # "shipping" -> page
    notes: list[Evidence] = Field(default_factory=list)  # how pages were chosen


class AgentEndpoints(BaseModel):
    """Agent-protocol discovery files, fetched after sampling (P1, P3)."""

    ucp: FetchedResource | None = None  # /.well-known/ucp (UCP business profile)
    ai_catalog: FetchedResource | None = None  # /.well-known/ai-catalog.json (MCP SEP-2127)
    llms_txt: FetchedResource | None = None  # /llms.txt


class UaProbe(BaseModel):
    """One D2 re-fetch of the probe page with an AI bot's published User-Agent."""

    token: str
    kind: str  # "search" | "user_agent"
    url: str
    tested: bool
    outcome: Literal["ok", "blocked", "rate_limited", "inconclusive", "skipped"]
    reason: str


class AgentProbes(BaseModel):
    url: str | None = None  # page re-fetched (the home page)
    baseline_outcome: Literal["ok", "blocked", "rate_limited", "inconclusive"] = "inconclusive"
    baseline_reason: str = "not probed"
    cdn: str | None = None  # "Cloudflare" / "Akamai" when the site is fronted by one
    probes: list[UaProbe] = Field(default_factory=list)


class ProbeStep(BaseModel):
    name: str  # "product" | "cookie_banner" | "popup" | "add_to_cart" | "cart" | "checkout"
    url: str | None = None
    outcome: Literal["ok", "blocked", "skipped", "failed"]
    detail: str
    screenshot: str | None = None  # file name inside the scan's artifacts dir


class RenderedPage(BaseModel):
    """What a JS-rendering browser sees on a product page (for D4)."""

    url: str
    price_visible: bool
    stock_visible: bool


class CheckoutProbe(BaseModel):
    """Data collected by the Playwright checkout probe (C1-C4, part of C3, D4 render).

    Read-only by design: stops on the checkout page, never types, never pays.
    """

    ran: bool = False
    skipped_reason: str | None = None  # robots / no products / browser missing / disabled
    skipped_kind: Literal["robots", "technical", "disabled"] | None = None
    product_url: str | None = None
    steps: list[ProbeStep] = Field(default_factory=list)
    interstitials: list[str] = Field(default_factory=list)  # cookie banner counted once
    challenge: str | None = None  # bot challenge / captcha met before checkout
    added_to_cart: bool | None = None
    checkout_url: str | None = None
    checkout_reached: bool = False
    login_wall: bool | None = None
    guest_option: bool | None = None
    captcha_markers: list[str] = Field(default_factory=list)  # on checkout entry
    payment_methods: dict[str, str] = Field(default_factory=dict)  # method -> URL seen
    rendered: list[RenderedPage] = Field(default_factory=list)


class ScanContext(BaseModel):
    """Everything a check may read. Built once after sampling; checks never fetch."""

    origin: str
    options: ScanOptions
    basics: SiteBasics
    platform: PlatformInfo
    pages: PageSample
    agent_probes: AgentProbes = Field(default_factory=AgentProbes)
    endpoints: AgentEndpoints = Field(default_factory=AgentEndpoints)
    checkout: CheckoutProbe = Field(default_factory=CheckoutProbe)


# --- Output ----------------------------------------------------------------------------


class VisibilityCall(BaseModel):
    """One question to one assistant in one run (V1). No shop data is sent anywhere."""

    assistant: str
    model: str
    run: int
    kind: Literal["brand", "category", "custom"]
    prompt: str
    mentioned: bool = False
    mentioned_in_text: bool = False
    cited: bool = False
    position: int | None = None  # 1-based rank of the shop among distinct cited domains
    cited_url: str | None = None  # first citation pointing at the shop
    cited_domains: list[str] = Field(default_factory=list)
    searches: int = 0
    cost_usd: float = 0.0
    generation_id: str | None = None
    raw_path: str | None = None  # raw response JSON (only with --out)
    error: str | None = None


class VisibilityResult(BaseModel):
    ran: bool = False
    skipped_reason: str | None = None
    brand_terms: list[str] = Field(default_factory=list)
    calls: list[VisibilityCall] = Field(default_factory=list)
    estimate_usd: float = 0.0
    total_cost_usd: float = 0.0
    month_to_date_usd: float = 0.0
    monthly_cap_usd: float = 0.0


class StageScore(BaseModel):
    """Score per stage of an agent order (scanner.report.scoring.STAGES), re-normalised over
    the stage's scorable checks."""

    stage: str  # "access" | "product_data" | "checkout" | "protocols"
    score: float | None  # 0..100; None = nothing scorable in this stage
    earned: float  # sum of weight x score_fraction
    scorable_weight: int  # weight of checks not excluded
    total_weight: int  # catalogue weight of the stage
    check_ids: list[str] = Field(default_factory=list)
    excluded: list[str] = Field(default_factory=list)  # ids not_applicable / error / not run


class Fix(BaseModel):
    """One of the top fixes: (weight x (1 - score_fraction)) / effort factor (SPEC §5)."""

    rank: int
    check_id: str
    label: str
    status: CheckStatus
    priority: float
    points_available: float  # weight x (1 - score_fraction)
    score_gain: float  # points the 0..100 score rises when fixed fully (re-normalised)
    effort: Effort
    guidance: str


class ScanReport(BaseModel):
    scanner_version: str
    url: str
    origin: str
    started_at: datetime
    finished_at: datetime
    platform: PlatformInfo
    sampled: dict[str, list[str]] = Field(default_factory=dict)  # kind -> page URLs
    sampling_notes: list[Evidence] = Field(default_factory=list)
    requests_made: int = 0
    score: float | None  # 0..100, None when nothing was scorable
    grade: Grade | None  # None: nothing scorable, or coverage below the minimum
    coverage: float = 0.0  # measured share of in-scope weight (0..1)
    excluded_checks: int  # in-scope results not_applicable / error (not in the score)
    not_run: list[str] = Field(default_factory=list)  # in-scope ids with no result at all
    stages: list[StageScore] = Field(default_factory=list)
    # Checks that ran but are outside the report's scope (only V1, the paid AI-visibility
    # snapshot): kept here in `results`, not scored, not in the HTML (decided 2026-11-10).
    out_of_scope: list[str] = Field(default_factory=list)
    top_fixes: list[Fix] = Field(default_factory=list)
    lang: Literal["nl", "en"] = "en"  # English default (Tarek, 2026-11-10)
    checkout_tested: bool = False  # the opt-in Playwright probe ran (methodology note)
    results: list[CheckResult]
    visibility: VisibilityResult | None = None
