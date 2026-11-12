"""P1.ucp_profile — /.well-known/ucp returns a valid UCP business profile.

Validated against the UCP specification version 2026-08-25
(https://ucp.dev/2026-08-25/specification/overview/), which states:
- businesses publish their profile at /.well-known/ucp, over HTTPS, without redirects;
- the profile is a JSON object with a required `ucp` member; `ucp.version`,
  `ucp.services` and `ucp.payment_handlers` are required (registries present even empty);
- services: reverse-domain keys -> entries with `transport` in rest|mcp|a2a|embedded;
- artifacts carry Cache-Control with `public` and max-age >= 60.
No JSON Schema URL for the profile is published, so these rules are checked directly.
Order readiness (added 2026-11-12): a spec-valid profile that declares no payment handler, or
a capabilities registry without `dev.ucp.shopping.checkout`, lets agents read the shop but
not pay through UCP -> warn (-0.3), not a full pass.
Agent checkout via UCP is not live for Dutch merchants yet: this measures readiness.
"""

from __future__ import annotations

import json
import re
from typing import Any

from scanner.checks.base import result
from scanner.models import CheckResult, CheckStatus, Evidence, ScanContext

CHECK_ID = "P1.ucp_profile"
SPEC_VERSION = "2026-08-25"
TRANSPORTS = frozenset({"rest", "mcp", "a2a", "embedded"})
NEEDS_ENDPOINT = frozenset({"rest", "mcp", "a2a"})


def order_gaps(profile: Any) -> list[str]:
    """Why agents could not order and pay through this (spec-valid) profile."""
    ucp = profile.get("ucp") if isinstance(profile, dict) else None
    if not isinstance(ucp, dict):
        return []
    gaps: list[str] = []
    handlers = ucp.get("payment_handlers")
    if isinstance(handlers, dict) and not handlers:
        gaps.append("no payment handler declared: agents cannot pay through UCP yet")
    caps = ucp.get("capabilities")
    if isinstance(caps, dict) and "dev.ucp.shopping.checkout" not in caps:
        gaps.append("no checkout capability declared: agents cannot place orders through UCP")
    return gaps


def validate(profile: Any) -> tuple[list[str], list[str]]:
    """(errors, notes). Errors break the spec; notes are informational."""
    errors: list[str] = []
    notes: list[str] = []
    if not isinstance(profile, dict) or not isinstance(profile.get("ucp"), dict):
        return ["no top-level `ucp` object"], notes
    ucp = profile["ucp"]
    version = ucp.get("version")
    if not isinstance(version, str) or not version:
        errors.append("`ucp.version` missing")
    elif version < SPEC_VERSION:
        notes.append(f"profile version {version} is older than {SPEC_VERSION}")
    for key in ("services", "payment_handlers"):
        if not isinstance(ucp.get(key), dict):
            errors.append(f"`ucp.{key}` missing (required, even when empty)")
    for name, entries in (ucp.get("services") or {}).items():
        for e in entries if isinstance(entries, list) else [entries]:
            t = e.get("transport") if isinstance(e, dict) else None
            if t not in TRANSPORTS:
                errors.append(f"service {name}: invalid transport {t!r}")
            elif t in NEEDS_ENDPOINT and not e.get("endpoint"):
                errors.append(f"service {name}: {t} transport without endpoint")
    handlers = ucp.get("payment_handlers")
    if isinstance(handlers, dict) and handlers:
        notes.append(f"payment handlers: {', '.join(sorted(handlers))}")
    caps = ucp.get("capabilities") or {}
    if isinstance(caps, dict) and caps:
        checkout = "yes" if "dev.ucp.shopping.checkout" in caps else "no"
        notes.append(f"{len(caps)} capabilities declared (checkout: {checkout})")
    return errors, notes


async def check(ctx: ScanContext) -> CheckResult:
    res = ctx.endpoints.ucp
    url = ctx.origin + "/.well-known/ucp"
    if res is None or res.status_code is None:
        detail = res.error if res and res.error else "not fetched"
        return result(CHECK_ID, ctx, "error", 0.0, [Evidence(url=url, detail=detail)])
    if res.status_code in (401, 403, 429):
        return result(
            CHECK_ID,
            ctx,
            "error",
            0.0,
            [
                Evidence(
                    url=url, detail=f"HTTP {res.status_code}: refused to our scanner, cannot verify"
                )
            ],
        )
    if res.status_code >= 500:
        # A server error says nothing about whether a profile exists: not a guessed fail.
        return result(
            CHECK_ID,
            ctx,
            "error",
            0.0,
            [Evidence(url=url, detail=f"HTTP {res.status_code}: server error, cannot verify")],
        )
    if res.status_code != 200:
        return result(
            CHECK_ID,
            ctx,
            "fail",
            0.0,
            [Evidence(url=url, detail=f"No UCP profile (HTTP {res.status_code})")],
        )
    if (res.body or "").lstrip()[:15].lower().startswith(("<!doctype", "<html")):
        return result(
            CHECK_ID,
            ctx,
            "fail",
            0.0,
            [
                Evidence(
                    url=url,
                    detail="No UCP profile: the URL returns an HTML page with HTTP 200 (soft 404)",
                    snippet=(res.body or "")[:120],
                )
            ],
        )
    try:
        profile = json.loads(res.body or "")
    except json.JSONDecodeError as exc:
        return result(
            CHECK_ID,
            ctx,
            "fail",
            0.0,
            [
                Evidence(
                    url=url, detail=f"Not valid JSON: {exc.msg}", snippet=(res.body or "")[:200]
                )
            ],
        )

    errors, notes = validate(profile)
    hosting: list[str] = []
    if not url.startswith("https://"):
        hosting.append("not served over HTTPS")
    if res.final_url and res.final_url.rstrip("/") != url.rstrip("/"):
        hosting.append(f"served via redirect to {res.final_url} (spec: MUST NOT redirect)")
    cache = res.headers.get("cache-control", "").lower()
    m = re.search(r"max-age=(\d+)", cache)
    if "public" not in cache or not m or int(m.group(1)) < 60:
        hosting.append(f"Cache-Control should be public with max-age >= 60 (got {cache!r})")

    version = (profile.get("ucp") or {}).get("version") if isinstance(profile, dict) else None
    evidence = [
        Evidence(
            url=url,
            detail=f"UCP profile found (version {version}); checked "
            f"against UCP spec {SPEC_VERSION}",
        )
    ]
    evidence += [Evidence(url=url, detail=f"Spec error: {e}") for e in errors]
    gaps = order_gaps(profile) if not errors else []
    evidence += [Evidence(url=url, detail=f"Orders: {g}") for g in gaps]
    evidence += [Evidence(url=url, detail=f"Hosting: {h}") for h in hosting]
    evidence += [Evidence(url=url, detail=f"Note: {n}") for n in notes]

    status: CheckStatus
    if errors:
        status, fraction = "fail", 0.5
    elif hosting or gaps:
        status = "warn"
        fraction = round(1.0 - (0.2 if hosting else 0.0) - (0.3 if gaps else 0.0), 2)
    else:
        status, fraction = "pass", 1.0
    return result(CHECK_ID, ctx, status, fraction, evidence)
