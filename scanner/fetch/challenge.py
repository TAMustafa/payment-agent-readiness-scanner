"""Detect CDN/WAF bot challenges and blocks in a fetched response.

Markers are vendor-documented headers or the stock challenge page text. Body markers are
only checked on short-ish pages or with a non-2xx status, to avoid matching a normal page
that merely mentions a vendor name.
- Cloudflare: `cf-mitigated: challenge` header
  (https://developers.cloudflare.com/cloudflare-challenges/challenge-types/challenge-pages/detect-response/),
  stock interstitial title "Just a moment..."; observed on Lightspeed eCom shops 2026-11-08.
- Akamai: "Access Denied" page with "Reference #" / errors.edgesuite.net.
- DataDome: `x-datadome` header with a 403, captcha-delivery.com.
- PerimeterX / HUMAN: "px-captcha" / "_pxCaptcha".
- Imperva / Incapsula: "Incapsula incident ID".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from scanner.models import FetchedResource

BLOCK_STATUSES = frozenset({401, 403})
_SMALL_PAGE = 60_000  # bytes; challenge pages are small

_BODY_MARKERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Cloudflare challenge", re.compile(r"<title>\s*Just a moment\.\.\.\s*</title>", re.I)),
    ("Cloudflare challenge", re.compile(r"challenges\.cloudflare\.com/turnstile|cf-chl-", re.I)),
    (
        "Akamai block",
        re.compile(r"errors\.edgesuite\.net|<title>\s*Access Denied\s*</title>", re.I),
    ),
    ("DataDome", re.compile(r"captcha-delivery\.com", re.I)),
    ("PerimeterX/HUMAN", re.compile(r"px-captcha|_pxCaptcha", re.I)),
    ("Imperva/Incapsula", re.compile(r"Incapsula incident ID|_Incapsula_Resource", re.I)),
)


@dataclass(frozen=True)
class Verdict:
    outcome: Literal["ok", "blocked", "rate_limited", "inconclusive"]
    reason: str


def classify(res: FetchedResource) -> Verdict:
    if res.status_code is None:
        return Verdict("inconclusive", res.error or "no response")
    if res.headers.get("cf-mitigated", "").lower() == "challenge":
        return Verdict("blocked", f"HTTP {res.status_code}, Cloudflare challenge (cf-mitigated)")
    body = res.body or ""
    if res.status_code >= 400 or len(body) < _SMALL_PAGE:
        for vendor, rx in _BODY_MARKERS:
            if rx.search(body):
                return Verdict("blocked", f"HTTP {res.status_code}, {vendor} page")
    if res.status_code == 429:
        # Observed 2026-11-08: Shopify returns 429 (Retry-After: 60) to our own scanner UA at
        # 1 req/s too, so a 429 says nothing about bot targeting on its own.
        retry = res.headers.get("retry-after")
        extra = f", Retry-After {retry}s" if retry else ""
        return Verdict("rate_limited", f"HTTP 429 rate limited{extra}")
    if res.status_code in BLOCK_STATUSES:
        return Verdict("blocked", f"HTTP {res.status_code}")
    if "x-datadome" in res.headers and res.status_code >= 400:
        return Verdict("blocked", f"HTTP {res.status_code}, DataDome")
    if 200 <= res.status_code < 400:
        return Verdict("ok", f"HTTP {res.status_code}")
    return Verdict("inconclusive", f"HTTP {res.status_code}")
