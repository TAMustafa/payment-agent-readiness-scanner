"""Check registry helpers, spec URLs and merchant-facing guidance (English).

Guidance is templated here, from the specs cited in each entry (CLAUDE.md rule 5: no
fabricated facts). Re-read the cited section before changing a text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ap2check.models import CheckResult, CheckStatus, Evidence, Stage

UCP_VERSION = "2026-08-25"
UCP_OVERVIEW = f"https://ucp.dev/{UCP_VERSION}/specification/overview/"
UCP_AP2 = f"https://ucp.dev/{UCP_VERSION}/specification/payment/extensions/ap2-mandates/"
UCP_SIGNATURES = f"https://ucp.dev/{UCP_VERSION}/specification/signatures/"
A2A_SPEC = "https://a2a-protocol.org/latest/specification/"
AP2_SPEC = "https://ap2-protocol.org/ap2/specification/"
AP2_CHECKOUT = "https://ap2-protocol.org/ap2/checkout_mandate/"

AP2_CAPABILITY = "dev.ucp.common.payment.ap2_mandate"
CHECKOUT_CAPABILITY = "dev.ucp.shopping.checkout"
# Extension URI used by every merchant agent card in the AP2 v0.2 samples
# (code/samples/*/roles/merchant_agent/agent.json in github.com/google-agentic-commerce/AP2).
# The v0.2 spec text itself does not define an A2A extension URI.
AP2_A2A_EXTENSION = "https://github.com/google-agentic-commerce/ap2/v1"


@dataclass(frozen=True)
class Spec:
    id: str
    stage: Stage
    label: str
    spec: str
    guidance: str


SPECS: dict[str, Spec] = {
    s.id: s
    for s in [
        Spec(
            "U1.profile_reachable",
            "discovery",
            "UCP business profile at /.well-known/ucp",
            UCP_OVERVIEW,
            "Publish your UCP business profile as JSON at https://<your-domain>/.well-known/ucp. "
            "Serve it over HTTPS with status 200 and no redirect (agents must not follow "
            "redirects), and keep it under 128 KiB. Shopify, commercetools and Salesforce "
            "publish this file for you once UCP is enabled; on other platforms your developer "
            "or payment provider adds it.",
        ),
        Spec(
            "U2.profile_structure",
            "discovery",
            "Profile has the required UCP fields",
            UCP_OVERVIEW,
            "The profile needs a top-level `ucp` object with `version`, `services` and "
            "`payment_handlers` (the two registries must be present even when empty). Each "
            "service entry needs a `transport` of rest, mcp, a2a or embedded, and rest/mcp/a2a "
            "entries need an https `endpoint`.",
        ),
        Spec(
            "U3.profile_caching",
            "discovery",
            "Profile is served with the required cache headers",
            UCP_OVERVIEW,
            "Send `Cache-Control: public, max-age=300` (any max-age of at least 60) on "
            "/.well-known/ucp, without `private`, `no-store` or `no-cache`, and add an ETag or "
            "Last-Modified header. Agents cache your profile, including your signing keys.",
        ),
        Spec(
            "U4.checkout_capability",
            "checkout",
            "Checkout capability and a callable endpoint",
            UCP_AP2,
            "Declare `dev.ucp.shopping.checkout` under `ucp.capabilities` and expose at least "
            "one service with a rest, mcp or a2a endpoint. AP2 mandates extend the checkout "
            "capability; without it an agent has no checkout to attach a mandate to.",
        ),
        Spec(
            "U5.payment_handlers",
            "checkout",
            "At least one payment handler",
            UCP_OVERVIEW,
            "List at least one payment handler under `ucp.payment_handlers` (for example the "
            "Google Pay handler or your payment provider's card tokenizer). The AP2 Payment "
            "Mandate travels inside the payment instrument, so without a handler an agent "
            "cannot pay.",
        ),
        Spec(
            "A1.ap2_capability",
            "ap2",
            "AP2 mandates extension declared",
            UCP_AP2,
            f"Add `{AP2_CAPABILITY}` to `ucp.capabilities` with `version` {UCP_VERSION}, "
            f'`extends: "{CHECKOUT_CAPABILITY}"` and `config.vp_formats_supported` containing '
            '`"dc+sd-jwt"`. Once declared you must sign every checkout response '
            "(`ap2.merchant_authorization`) and refuse `complete_checkout` without "
            "`ap2.checkout_mandate`; only declare it when your checkout does both.",
        ),
        Spec(
            "A2.signing_keys",
            "ap2",
            "Public signing keys for AP2 in the profile",
            UCP_SIGNATURES,
            "Publish your checkout signing key in the top-level `keys` array of the profile as "
            "a public EC JWK with `kid`, `kty: EC`, `crv: P-256`, `x`, `y` (and optionally "
            '`use: "sig"`, `alg: "ES256"`). AP2 v0.2 requires ECDSA (ES256/ES384/ES512); every '
            "agent must support ES256, so prefer P-256. Never publish the private part "
            "(`d`). Rotate every 90 days and keep an old key for at least 7 days after.",
        ),
        Spec(
            "G1.agent_card",
            "a2a",
            "A2A agent card at /.well-known/agent-card.json",
            A2A_SPEC,
            "Only needed if your merchant agent talks A2A. Publish an agent card at "
            "/.well-known/agent-card.json with name, description, version, capabilities, "
            "defaultInputModes, defaultOutputModes, skills and supportedInterfaces (each with an "
            "https url, protocolBinding and protocolVersion).",
        ),
        Spec(
            "G2.ap2_extension",
            "a2a",
            "Agent card declares the AP2 extension",
            AP2_SPEC,
            f'Add `{{"uri": "{AP2_A2A_EXTENSION}", "required": true}}` to '
            "`capabilities.extensions` in your agent card, so shopping agents know they must "
            "speak AP2 with your merchant agent.",
        ),
        Spec(
            "M1.merchant_signature",
            "signature",
            "Merchant signature on a sample checkout verifies",
            UCP_AP2,
            "Sign each checkout response: put a detached JWS (`<header>..<signature>`) in "
            "`ap2.merchant_authorization`, with `alg` ES256/ES384/ES512 and a `kid` that is in "
            "your profile's `keys`, over the RFC 8785 (JCS) canonical JSON of the checkout "
            "without its `ap2` member. For A2A merchants: sign the `checkout_jwt` with ECDSA "
            "(not Ed25519) and a `kid` from your published keys.",
        ),
    ]
}


def result(
    check_id: str,
    status: CheckStatus,
    evidence: list[Evidence],
) -> CheckResult:
    s = SPECS[check_id]
    return CheckResult(
        id=s.id,
        stage=s.stage,
        label=s.label,
        status=status,
        evidence=evidence,
        # n/a checks depend on an earlier one (or are optional); that one carries the fix.
        guidance="" if status in ("pass", "not_applicable") else s.guidance,
        spec=s.spec,
    )


def entries(value: Any) -> list[dict[str, Any]]:
    """UCP registries map a name to one entry or a list of entries."""
    items = value if isinstance(value, list) else [value]
    return [e for e in items if isinstance(e, dict)]


def ucp_obj(profile: Any) -> dict[str, Any] | None:
    if isinstance(profile, dict) and isinstance(profile.get("ucp"), dict):
        ucp: dict[str, Any] = profile["ucp"]
        return ucp
    return None


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
