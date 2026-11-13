"""Run a readiness check: normalise the URL, fetch the discovery documents, run every check,
compute the verdict. Data collection happens before any check runs; checks never fetch."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx

from ap2check import __version__
from ap2check.checks import ALL_CHECKS
from ap2check.checks.base import SPECS, UCP_VERSION, result
from ap2check.fetch import Fetcher, Resolver, private_host, system_resolver
from ap2check.models import (
    CheckInput,
    CheckResult,
    Evidence,
    FetchedResource,
    Report,
    Step,
    Verdict,
)

SPEC_VERSIONS = {
    "AP2": "v0.2.0 (2026-04-28)",
    "UCP": UCP_VERSION,
    "A2A": "1.0.0",
}

NOTES = [
    "AP2 v0.2 is a pre-release protocol; standardisation continues at the FIDO Alliance. "
    "Passing these checks means your public setup follows the published specs, not that any "
    "AI agent will send you orders. Ask your platform or payment provider whether agent "
    "checkout is available in your market.",
    "Not tested: whether your checkout verifies incoming Checkout and Payment Mandates "
    "(SD-JWT signature, key binding, expiry, constraints) and returns signed receipts. That "
    "needs a test transaction against your checkout, which this tool never sends.",
    "Your sample checkout is checked in memory and not stored. Use a test checkout without "
    "real customer data.",
]


class InvalidTarget(ValueError):
    """The submitted URL cannot be checked."""


def normalise_target(raw: str) -> str:
    """'Shop.nl', 'http://shop.nl/p/1' -> 'https://shop.nl'. UCP requires HTTPS."""
    text = raw.strip()
    if not text:
        raise InvalidTarget("enter your shop's domain, e.g. shop.example.com")
    if "://" not in text:
        text = "https://" + text
    parts = urlsplit(text)
    if parts.scheme not in ("http", "https"):
        raise InvalidTarget("only http(s) URLs can be checked")
    host = (parts.hostname or "").lower().rstrip(".")
    if not host or parts.username or parts.password:
        raise InvalidTarget("not a valid shop URL")
    if private_host(host):
        raise InvalidTarget("private or local addresses cannot be checked")
    port = f":{parts.port}" if parts.port and parts.port != 443 else ""
    return f"https://{host}{port}"


def _json(res: FetchedResource | None) -> Any:
    if res is None or res.status_code != 200 or not res.body or res.truncated:
        return None
    try:
        return json.loads(res.body)
    except json.JSONDecodeError:
        return None


async def collect(target: str, sample: str | None, fetcher: Fetcher) -> CheckInput:
    profile = await fetcher.get(f"{target}/.well-known/ucp")
    card = await fetcher.get(f"{target}/.well-known/agent-card.json")
    return CheckInput(
        target=target,
        profile=profile,
        profile_json=_json(profile),
        agent_card=card,
        agent_card_json=_json(card),
        sample=sample,
    )


def run_checks(inp: CheckInput) -> list[CheckResult]:
    out: list[CheckResult] = []
    for check in ALL_CHECKS:
        try:
            out.append(check(inp))
        except Exception as exc:  # a bug in one check never aborts the report
            prefix = check.__name__.split("_", 1)[0].upper() + "."  # u1_... -> "U1."
            cid = next(k for k in SPECS if k.startswith(prefix))
            out.append(result(cid, "error", [Evidence(detail=f"internal error: {exc!r}")]))
    return out


def verdict(results: list[CheckResult]) -> Verdict:
    by = {r.id.split(".")[0]: r.status for r in results}
    profile_ok = by["U1"] in ("pass", "warn")
    card_ap2 = by["G2"] in ("pass", "warn")
    if not profile_ok and not card_ap2:
        if by["U1"] == "error":
            return Verdict(
                level="unknown",
                title="We could not read your setup",
                summary="Your server blocked or did not answer our request for "
                "/.well-known/ucp. AI agents fetching it would likely hit the same wall. "
                "Check firewall / bot-protection rules for this path, then run the check "
                "again.",
            )
        return Verdict(
            level="not_discoverable",
            title="AI agents cannot find your AP2 setup",
            summary="There is no UCP business profile at /.well-known/ucp and no A2A agent "
            "card declaring AP2. Agents discover a merchant's checkout, payment handlers and "
            "signing keys there, so AP2 payment requests cannot reach you yet.",
        )
    if by["A1"] not in ("pass", "warn") and not card_ap2:
        return Verdict(
            level="no_ap2",
            title="Discoverable, but AP2 is not declared",
            summary="Agents can read your UCP profile, but it does not declare the AP2 "
            "mandates extension (dev.ucp.common.payment.ap2_mandate), so agents will not send "
            "AP2 Checkout or Payment Mandates.",
        )
    core = ["U2", "U3", "U4", "U5", "A1", "A2"] if profile_ok else []
    core += [g for g in ("G1", "G2") if by[g] != "not_applicable"]
    broken = [r.label for r in results if r.id.split(".")[0] in core and r.status == "fail"]
    if not profile_ok:
        broken.append("signing keys: AP2 does not define key publication outside a UCP profile")
    if broken:
        return Verdict(
            level="incomplete",
            title="AP2 declared, but the setup is incomplete",
            summary="Agents would reject or be unable to complete AP2 payments until these "
            "are fixed: " + "; ".join(broken) + ".",
        )
    m1 = by["M1"]
    if m1 in ("pass", "warn"):
        return Verdict(
            level="ready",
            title="Set up to accept AP2 payment requests",
            summary="Your profile declares AP2, publishes valid signing keys, and the sample "
            "checkout signature verifies with them. Remaining: your checkout must verify the "
            "mandates agents send (not testable from outside).",
        )
    if m1 in ("fail", "error"):
        return Verdict(
            level="signature_failed",
            title="AP2 declared, but your checkout signature does not verify",
            summary="Agents verify ap2.merchant_authorization before showing a checkout to "
            "the buyer; with this signature they would refuse it.",
        )
    return Verdict(
        level="untested",
        title="AP2 declared and well-formed; signature not tested yet",
        summary="Your public setup is in order. Paste one checkout response from your test "
        "checkout to verify that your merchant signature matches your published keys.",
    )


LADDER: list[tuple[str, tuple[str, ...]]] = [
    ("Agents can find your shop", ("U1", "U2", "U3")),
    ("Agents can start a checkout", ("U4", "U5")),
    ("AP2 is switched on", ("A1",)),
    ("Your signing key is published", ("A2",)),
    ("Your checkout signature verifies", ("M1",)),
]


def ladder(results: list[CheckResult]) -> tuple[list[Step], str]:
    """The readiness ladder and the single next action (guidance of the first open rung)."""
    by = {r.id.split(".")[0]: r for r in results}
    steps: list[Step] = []
    next_step = ""
    for title, ids in LADDER:
        rung = [by[i] for i in ids]
        statuses = {r.status for r in rung}
        state: Literal["done", "problem", "unknown", "todo"]
        if "fail" in statuses:
            state = "problem"
        elif "error" in statuses:
            state = "unknown"
        elif "not_applicable" in statuses:
            state = "todo"
        else:
            state = "done"
        current = state != "done" and not next_step
        if current:
            blocker = next((r for r in rung if r.status in ("fail", "error")), None)
            if blocker is not None and blocker.guidance:
                next_step = blocker.guidance
            elif ids == ("M1",):
                next_step = (
                    "Paste one checkout response from your test checkout to verify that your "
                    "signature matches your published key."
                )
            else:
                next_step = "Fix the step before this one first, then run the check again."
        steps.append(Step(title=title, state=state, current=current, checks=[r.id for r in rung]))
    if not next_step:
        next_step = (
            "Nothing to fix in your public setup. Make sure your checkout verifies the "
            "mandates agents send and returns signed receipts; that cannot be tested from "
            "outside."
        )
    return steps, next_step


async def check_merchant(
    url: str,
    sample: str | None = None,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    resolver: Resolver = system_resolver,
    min_interval_s: float = 1.0,
) -> Report:
    target = normalise_target(url)
    async with Fetcher(
        transport=transport, resolver=resolver, min_interval_s=min_interval_s
    ) as fetcher:
        inp = await collect(target, sample, fetcher)
        log = list(fetcher.log)
    results = run_checks(inp)
    steps, next_step = ladder(results)
    return Report(
        target=target,
        checked_at=datetime.now(UTC).isoformat(timespec="seconds"),
        tool_version=__version__,
        spec_versions=SPEC_VERSIONS,
        verdict=verdict(results),
        steps=steps,
        next_step=next_step,
        results=results,
        requests=log,
        notes=list(NOTES),
    )
