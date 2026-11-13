"""Built-in demo merchant: shows what a report looks like at each stage, without any network.

No real shop declares AP2 yet (live round 2026-11-13, docs/VERIFY.md), so the website needs
its own example of a passing setup. The demo shop is a set of static public documents in
`demo_data/` (a UCP profile with a public key, and one checkout response signed with that
key), served to the normal checker through an in-memory transport. Nothing leaves the
process. The fixture is produced by `scripts/make_demo_fixture.py`, outside this package,
which discards the private key: the package itself never signs (tests/test_safety.py).
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from ap2check.checks.base import AP2_CAPABILITY
from ap2check.models import Report
from ap2check.runner import check_merchant

DATA = Path(__file__).parent / "demo_data"
DEMO_HOST = "demo-shop.example"  # .example is reserved (RFC 2606): can never be a real shop
DEMO_NOTE = (
    "This is a built-in demo shop, not a real merchant. Its documents are served from "
    "memory; no request left this server."
)
HEADERS = {
    "content-type": "application/json",
    "cache-control": "public, max-age=300",
    "etag": '"demo"',
}


@dataclass(frozen=True)
class Scenario:
    title: str
    description: str


SCENARIOS: dict[str, Scenario] = {
    "ready": Scenario(
        "A shop that passes",
        "AP2 declared, signing key published, and a checkout response whose signature verifies.",
    ),
    "no_ap2": Scenario(
        "A typical shop today",
        "A UCP profile with checkout and payment handlers but no AP2, like the Shopify "
        "default we see on live shops.",
    ),
    "signature_failed": Scenario(
        "A broken signature",
        "Everything is published, but the checkout was changed after it was signed.",
    ),
}


def _load(name: str) -> Any:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def _documents(scenario: str) -> tuple[dict[str, Any], str | None]:
    """(profile, sample checkout text or None) for a scenario."""
    profile = _load("profile.json")
    checkout = _load("checkout.json")
    if scenario == "no_ap2":
        del profile["ucp"]["capabilities"][AP2_CAPABILITY]
        del profile["keys"]
        return profile, None
    if scenario == "signature_failed":
        tampered = copy.deepcopy(checkout)
        tampered["totals"][-1]["amount"] += 500  # total changed after signing
        return profile, json.dumps(tampered, indent=2)
    return profile, json.dumps(checkout, indent=2)


async def _resolver(host: str) -> list[str]:
    return ["192.0.2.1"] if host != DEMO_HOST else ["93.184.215.14"]


async def run_demo(scenario: str) -> tuple[Report, str | None]:
    """Run the normal checks against the demo shop. Returns the report and the sample used."""
    if scenario not in SCENARIOS:
        raise KeyError(scenario)
    profile, sample = _documents(scenario)
    origin = f"https://{DEMO_HOST}"
    routes = {
        f"{origin}/robots.txt": httpx.Response(200, text="User-agent: *\nAllow: /\n"),
        f"{origin}/.well-known/ucp": httpx.Response(200, json=profile, headers=HEADERS),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return routes.get(str(request.url), httpx.Response(404, text="not found"))

    report = await check_merchant(
        origin,
        sample,
        transport=httpx.MockTransport(handler),
        resolver=_resolver,
        min_interval_s=0,
    )
    return report.model_copy(update={"notes": [DEMO_NOTE, *report.notes]}), sample
