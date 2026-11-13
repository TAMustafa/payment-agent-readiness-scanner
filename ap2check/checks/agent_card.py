"""G1, G2: the A2A agent card (/.well-known/agent-card.json) and its AP2 extension.

A2A 1.0 (https://a2a-protocol.org/latest/specification/ §8.2, §8.4.1): REQUIRED fields
name, description, supportedInterfaces, version, capabilities, defaultInputModes,
defaultOutputModes, skills; `url`/`protocolVersion` live inside each supportedInterfaces
entry. The AP2 v0.2 samples still ship A2A 0.3 cards (top-level `url`, `protocolVersion`
"0.3.0"), which we accept with a warning.
A2A is optional for AP2 merchants who use UCP over REST/MCP, so a missing card is
`not_applicable` when a UCP profile exists.
"""

from __future__ import annotations

from typing import Any

from ap2check.checks.base import AP2_A2A_EXTENSION, result
from ap2check.models import CheckInput, CheckResult, Evidence

REQUIRED_1_0 = (
    "name",
    "description",
    "version",
    "capabilities",
    "defaultInputModes",
    "defaultOutputModes",
    "skills",
)


def _url(inp: CheckInput) -> str:
    return f"{inp.target}/.well-known/agent-card.json"


def card_usable(inp: CheckInput) -> bool:
    return isinstance(inp.agent_card_json, dict)


def g1_agent_card(inp: CheckInput) -> CheckResult:
    cid = "G1.agent_card"
    res, url = inp.agent_card, _url(inp)
    if res is None or res.status_code is None:
        return result(
            cid,
            "error",
            [Evidence(url=url, detail=f"could not fetch: {res.error if res else 'not fetched'}")],
        )
    if res.status_code in (401, 403, 429) or res.status_code >= 500:
        return result(cid, "error", [Evidence(url=url, detail=f"HTTP {res.status_code}")])
    if res.status_code != 200:
        detail = f"HTTP {res.status_code}: no agent card"
        if 300 <= res.status_code < 400:
            detail = f"HTTP {res.status_code} redirect to {res.headers.get('location', '?')}"
        # Optional channel: only a problem when there is no UCP profile either (verdict).
        return result(cid, "not_applicable", [Evidence(url=url, detail=detail)])
    card = inp.agent_card_json
    if not isinstance(card, dict):
        return result(cid, "fail", [Evidence(url=url, detail="HTTP 200 but not a JSON object")])
    missing = [f for f in REQUIRED_1_0 if f not in card]
    ifaces = card.get("supportedInterfaces")
    ev = [
        Evidence(
            url=url, detail=f"agent card {card.get('name')!r}, version {card.get('version')!r}"
        )
    ]
    warnings: list[str] = []
    urls: list[str] = []
    if isinstance(ifaces, list) and ifaces:
        for i in ifaces:
            if isinstance(i, dict):
                urls.append(str(i.get("url", "")))
                if not i.get("protocolBinding") or not i.get("protocolVersion"):
                    warnings.append(
                        "a supportedInterfaces entry lacks protocolBinding or protocolVersion"
                    )
    elif isinstance(card.get("url"), str):
        urls.append(card["url"])
        warnings.append(
            f"pre-1.0 agent card (protocolVersion {card.get('protocolVersion')!r},"
            " top-level url); A2A 1.0 uses supportedInterfaces"
        )
    else:
        missing.append("supportedInterfaces")
    insecure = [u for u in urls if not u.startswith("https://")]
    if missing:
        ev.append(Evidence(detail="missing required field(s): " + ", ".join(missing)))
    if insecure:
        ev.append(Evidence(detail="interface URL is not https: " + ", ".join(insecure)))
    ev += [Evidence(detail=w) for w in warnings]
    if missing or insecure:
        return result(cid, "fail", ev)
    return result(cid, "warn" if warnings else "pass", ev)


def _extensions(card: Any) -> list[dict[str, Any]]:
    caps = card.get("capabilities") if isinstance(card, dict) else None
    exts = caps.get("extensions") if isinstance(caps, dict) else None
    return [e for e in exts if isinstance(e, dict)] if isinstance(exts, list) else []


def g2_ap2_extension(inp: CheckInput) -> CheckResult:
    cid = "G2.ap2_extension"
    url = _url(inp)
    if not card_usable(inp):
        return result(cid, "not_applicable", [Evidence(url=url, detail="no agent card (see G1)")])
    exts = _extensions(inp.agent_card_json)
    exact = [e for e in exts if e.get("uri") == AP2_A2A_EXTENSION]
    similar = [e for e in exts if "google-agentic-commerce/ap2" in str(e.get("uri", "")).lower()]
    if exact:
        e = exact[0]
        ev = [Evidence(url=url, detail=f"AP2 extension declared: {AP2_A2A_EXTENSION}")]
        if e.get("required") is not True:
            ev.append(Evidence(detail="`required` is not true; merchant agents SHOULD set it"))
            return result(cid, "warn", ev)
        return result(cid, "pass", ev)
    if similar:
        return result(
            cid,
            "warn",
            [
                Evidence(
                    url=url,
                    detail=f"AP2-like extension URI {similar[0].get('uri')!r}; "
                    f"the AP2 v0.2 samples use {AP2_A2A_EXTENSION}",
                )
            ],
        )
    uris = ", ".join(str(e.get("uri")) for e in exts) or "none"
    return result(cid, "fail", [Evidence(url=url, detail=f"no AP2 extension (extensions: {uris})")])


CHECKS = [g1_agent_card, g2_ap2_extension]
