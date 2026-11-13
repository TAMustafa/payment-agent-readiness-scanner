"""M1: verify the merchant's signature on a sample checkout the merchant pastes in.

We never call the merchant's checkout (read-only rule); the merchant supplies one response
from their own test checkout. Two formats are accepted:

1. UCP checkout response (JSON) with `ap2.merchant_authorization`: a detached JWS
   (`<header>..<signature>`, RFC 7515 App. F) with `alg` ES256/ES384/ES512 and `kid`, over the
   JCS (RFC 8785) canonical checkout without its `ap2` member, verified with the key of that
   `kid` from the profile's top-level `keys`
   (https://ucp.dev/2026-08-25/specification/payment/extensions/ap2-mandates/
   #business-authorization).
2. AP2 A2A flow: a merchant-signed compact `checkout_jwt` (alone, or inside JSON such as the
   `ap2.checkout` DataPart of the AP2 v0.2 samples). AP2 v0.2: "The Merchant MUST provide a
   merchant-signed JWT containing the Checkout", signed with "a digital signature scheme
   (e.g., ECDSA) and not a deterministic signature (e.g., Ed25519)"
   (https://ap2-protocol.org/ap2/specification/). AP2 does not say where merchant keys are
   published, so we look the `kid` up in the UCP profile `keys`.

Privacy: the sample may contain buyer data. It is processed in memory only; evidence shows
headers, key ids, hashes and field names, never field values.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any

from ap2check.checks.base import result
from ap2check.jose import (
    ALGS,
    EcKey,
    JoseError,
    b64url_decode,
    b64url_encode,
    canonical_json,
    detached_signing_input,
    ec_key_from_jwk,
    parse_jws,
    verify_es,
)
from ap2check.models import CheckInput, CheckResult, Evidence

CID = "M1.merchant_signature"
DETACHED = re.compile(r"^[A-Za-z0-9_-]+\.\.[A-Za-z0-9_-]+$")
MAX_SAMPLE_CHARS = 256_000


def published_keys(profile: Any) -> dict[str, EcKey]:
    keys = profile.get("keys") if isinstance(profile, dict) else None
    out: dict[str, EcKey] = {}
    for jwk in keys if isinstance(keys, list) else []:
        if isinstance(jwk, dict) and "d" not in jwk:
            try:
                k = ec_key_from_jwk(jwk)
            except JoseError:
                continue
            if k.kid:
                out[k.kid] = k
    return out


def _find_checkout_jwt(obj: Any, depth: int = 0) -> tuple[str, str | None] | None:
    """(checkout_jwt, checkout_hash or None) anywhere in a JSON sample."""
    if depth > 6:
        return None
    if isinstance(obj, dict):
        jwt = obj.get("checkout_jwt")
        if isinstance(jwt, str):
            h = obj.get("checkout_hash")
            return jwt, h if isinstance(h, str) else None
        for v in obj.values():
            found = _find_checkout_jwt(v, depth + 1)
            if found:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _find_checkout_jwt(v, depth + 1)
            if found:
                return found
    return None


def m1_merchant_signature(inp: CheckInput) -> CheckResult:
    sample = (inp.sample or "").strip()
    if not sample:
        return result(
            CID,
            "not_applicable",
            [
                Evidence(
                    detail="no sample checkout supplied; paste one checkout response from "
                    "your test checkout to verify your signature"
                )
            ],
        )
    if len(sample) > MAX_SAMPLE_CHARS:
        return result(CID, "fail", [Evidence(detail="sample larger than 256 kB")])
    keys = published_keys(inp.profile_json)
    if sample.startswith("{"):
        try:
            obj = json.loads(sample)
        except json.JSONDecodeError as exc:
            return result(CID, "fail", [Evidence(detail=f"sample is not valid JSON: {exc}")])
        if not isinstance(obj, dict):
            return result(CID, "fail", [Evidence(detail="sample JSON is not an object")])
        ap2 = obj.get("ap2")
        if isinstance(ap2, dict) and "merchant_authorization" in ap2:
            return _verify_ucp(obj, ap2["merchant_authorization"], keys)
        found = _find_checkout_jwt(obj)
        if found:
            return _verify_checkout_jwt(found[0], found[1], keys)
        if isinstance(ap2, dict) or "line_items" in obj:
            return result(
                CID,
                "fail",
                [
                    Evidence(
                        detail="checkout response has no `ap2.merchant_authorization`: agents "
                        "reject it with `merchant_authorization_missing`"
                    )
                ],
            )
        return result(
            CID,
            "fail",
            [
                Evidence(
                    detail="no `ap2.merchant_authorization` or `checkout_jwt` found in the sample"
                )
            ],
        )
    if sample.count(".") == 2:
        return _verify_checkout_jwt(sample, None, keys)
    return result(
        CID,
        "fail",
        [Evidence(detail="sample is neither a JSON checkout response nor a compact JWT")],
    )


def _lookup(kid: Any, keys: dict[str, EcKey]) -> tuple[EcKey | None, str | None]:
    if not keys:
        return None, (
            "no usable EC key in your profile's `keys`, so nobody can verify this "
            "signature (see A2)"
        )
    if not isinstance(kid, str) or not kid:
        return None, "JWS header has no `kid`"
    key = keys.get(kid)
    if key is None:
        return None, (f"kid {kid!r} is not in your profile's keys ({', '.join(sorted(keys))})")
    return key, None


def _verify_ucp(checkout: dict[str, Any], auth: Any, keys: dict[str, EcKey]) -> CheckResult:
    ev = [Evidence(detail="format: UCP checkout response with `ap2.merchant_authorization`")]
    if not isinstance(auth, str) or not DETACHED.match(auth):
        ev.append(
            Evidence(
                detail="`ap2.merchant_authorization` is not a detached JWS `<header>..<signature>`",
                snippet=str(auth)[:80],
            )
        )
        return result(CID, "fail", ev)
    try:
        jws = parse_jws(auth)
    except JoseError as exc:
        ev.append(Evidence(detail=f"malformed JWS: {exc}"))
        return result(CID, "fail", ev)
    header = jws.header
    ev.append(Evidence(detail="protected header", snippet=json.dumps(header)[:200]))
    alg = header.get("alg")
    if alg not in ALGS:
        ev.append(Evidence(detail=f"alg {alg!r} not allowed: AP2 v0.2 requires ES256/384/512"))
        return result(CID, "fail", ev)
    key, problem = _lookup(header.get("kid"), keys)
    if key is None:
        ev.append(Evidence(detail=problem or "key not found"))
        return result(CID, "error" if not keys else "fail", ev)
    payload_obj = {k: v for k, v in checkout.items() if k != "ap2"}
    try:
        payload = canonical_json(payload_obj)
        ok = verify_es(alg, key, detached_signing_input(jws, payload), jws.signature)
    except JoseError as exc:
        ev.append(Evidence(detail=str(exc)))
        return result(CID, "fail", ev)
    digest = b64url_encode(hashlib.sha256(payload).digest())
    ev.append(
        Evidence(
            detail=f"signed content: JCS of the checkout without `ap2`, "
            f"{len(payload)} bytes, sha-256 {digest}"
        )
    )
    if ok:
        ev.append(Evidence(detail=f"signature verifies with key {key.kid!r} ({alg})"))
        return result(CID, "pass", ev)
    ev.append(
        Evidence(
            detail=f"signature does NOT verify with key {key.kid!r}. Common causes: "
            "signing before the checkout was final, not using RFC 8785 (JCS), "
            "or including the `ap2` member in the signed content"
        )
    )
    return result(CID, "fail", ev)


def _verify_checkout_jwt(
    token: str, claimed_hash: str | None, keys: dict[str, EcKey]
) -> CheckResult:
    ev = [Evidence(detail="format: AP2 merchant-signed `checkout_jwt` (compact JWS)")]
    try:
        jws = parse_jws(token)
        payload_raw = b64url_decode(jws.payload_b64)
    except JoseError as exc:
        ev.append(Evidence(detail=f"malformed JWT: {exc}"))
        return result(CID, "fail", ev)
    header = jws.header
    ev.append(Evidence(detail="protected header", snippet=json.dumps(header)[:200]))
    alg = header.get("alg")
    if alg == "EdDSA":
        ev.append(
            Evidence(
                detail="EdDSA is a deterministic signature; AP2 v0.2 requires a "
                "non-deterministic scheme such as ECDSA for the Checkout JWT "
                "(open upstream question: AP2 issue #268)"
            )
        )
        return result(CID, "fail", ev)
    if alg not in ALGS:
        ev.append(Evidence(detail=f"alg {alg!r} not allowed: use ES256/ES384/ES512"))
        return result(CID, "fail", ev)
    computed = b64url_encode(hashlib.sha256(token.strip().encode("ascii")).digest())
    ev.append(Evidence(detail=f"checkout_hash (sha-256 of checkout_jwt): {computed}"))
    if claimed_hash is not None and claimed_hash != computed:
        ev.append(
            Evidence(
                detail=f"`checkout_hash` in the sample ({claimed_hash}) does not "
                "match the checkout_jwt"
            )
        )
        return result(CID, "fail", ev)
    warnings, notes = _payload_findings(payload_raw)
    key, problem = _lookup(header.get("kid"), keys)
    if key is None:
        ev.append(Evidence(detail=problem or "key not found"))
        return result(CID, "error" if not keys else "fail", ev)
    signing_input = f"{jws.header_b64}.{jws.payload_b64}".encode("ascii")
    try:
        ok = verify_es(alg, key, signing_input, jws.signature)
    except JoseError as exc:
        ev.append(Evidence(detail=str(exc)))
        return result(CID, "fail", ev)
    if not ok:
        ev.append(Evidence(detail=f"signature does NOT verify with key {key.kid!r}"))
        return result(CID, "fail", ev)
    ev.append(Evidence(detail=f"signature verifies with key {key.kid!r} ({alg})"))
    ev += [Evidence(detail=w) for w in warnings] + [Evidence(detail=n) for n in notes]
    return result(CID, "warn" if warnings else "pass", ev)


# Required members of the AP2 v0.2 Checkout type
# (code/sdk/schemas/ucp/types/checkout.json in github.com/google-agentic-commerce/AP2).
CHECKOUT_REQUIRED = ("id", "line_items", "status", "currency", "totals", "links")


def _payload_findings(raw: bytes) -> tuple[list[str], list[str]]:
    """(warnings, notes) about the signed checkout payload; values are never echoed."""
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return ["checkout_jwt payload is not JSON"], []
    if not isinstance(payload, dict):
        return ["checkout_jwt payload is not a JSON object"], []
    out: list[str] = []
    notes: list[str] = []
    missing = [f for f in CHECKOUT_REQUIRED if f not in payload]
    if missing:
        out.append("payload lacks required checkout field(s): " + ", ".join(missing))
    merchant = payload.get("merchant")  # optional; when present it needs id and name
    if merchant is not None and not (
        isinstance(merchant, dict) and merchant.get("id") and merchant.get("name")
    ):
        out.append("`merchant` is present but lacks `id` or `name` (AP2 Merchant type)")
    exp = payload.get("exp")
    if isinstance(exp, int) and exp < time.time():
        notes.append(
            "note: this sample has expired (fine for a test; live checkouts must be fresh)"
        )
    return out, notes


CHECKS = [m1_merchant_signature]
