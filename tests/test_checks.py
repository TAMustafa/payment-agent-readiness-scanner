"""Profile (U*, A*), agent card (G*) and signature (M1) checks on in-memory inputs."""

from __future__ import annotations

import json
from typing import Any

import pytest

from ap2check.checks import agent_card, profile, signature
from ap2check.models import CheckInput, FetchedResource
from tests.helpers import (
    GOOD_HEADERS,
    SHOP,
    MerchantKey,
    a2a_checkout_payload,
    agent_card_1_0,
    checkout_hash,
    sample_checkout,
)
from tests.helpers import profile as make_profile


def inp(
    prof: Any = None,
    *,
    status: int = 200,
    headers: dict[str, str] | None = None,
    card: Any = None,
    card_status: int = 404,
    sample: str | None = None,
) -> CheckInput:
    body = json.dumps(prof) if prof is not None else None
    return CheckInput(
        target=SHOP,
        profile=FetchedResource(
            url=f"{SHOP}/.well-known/ucp",
            status_code=status,
            headers=headers if headers is not None else GOOD_HEADERS,
            body=body,
        ),
        profile_json=prof if status == 200 else None,
        agent_card=FetchedResource(
            url=f"{SHOP}/.well-known/agent-card.json",
            status_code=200 if card is not None else card_status,
            body=json.dumps(card) if card is not None else None,
        ),
        agent_card_json=card,
        sample=sample,
    )


def details(res: Any) -> str:
    return " | ".join(e.detail for e in res.evidence)


# --- profile -------------------------------------------------------------------------------


def test_valid_profile_passes_everything() -> None:
    i = inp(make_profile())
    for check in profile.CHECKS:
        assert check(i).status == "pass", (check.__name__, details(check(i)))


def test_redirect_fails_u1() -> None:
    i = inp(None, status=301, headers={"location": "https://www.shop.example.nl/.well-known/ucp"})
    r = profile.u1_profile_reachable(i)
    assert r.status == "fail" and "MUST NOT redirect" in details(r)
    assert profile.a1_ap2_capability(i).status == "not_applicable"


@pytest.mark.parametrize("code", [403, 429, 503])
def test_blocked_profile_is_error_not_fail(code: int) -> None:
    assert profile.u1_profile_reachable(inp(None, status=code)).status == "error"


def test_404_is_fail() -> None:
    assert profile.u1_profile_reachable(inp(None, status=404)).status == "fail"


def test_missing_registries_fail_u2() -> None:
    p = make_profile()
    del p["ucp"]["payment_handlers"]
    r = profile.u2_profile_structure(inp(p))
    assert r.status == "fail" and "payment_handlers" in details(r)


def test_http_endpoint_fails_u2() -> None:
    p = make_profile()
    p["ucp"]["services"]["dev.ucp.shopping"][0]["endpoint"] = "http://shop.example.nl/ucp"
    assert profile.u2_profile_structure(inp(p)).status == "fail"


@pytest.mark.parametrize(
    ("cc", "status"),
    [
        ("public, max-age=300", "pass"),
        ("max-age=300", "fail"),
        ("public, max-age=30", "fail"),
        ("public, max-age=300, no-cache", "fail"),
        ("", "fail"),
    ],
)
def test_cache_control(cc: str, status: str) -> None:
    headers = {"cache-control": cc, "etag": '"1"'} if cc else {"etag": '"1"'}
    assert profile.u3_profile_caching(inp(make_profile(), headers=headers)).status == status


def test_missing_validator_warns() -> None:
    r = profile.u3_profile_caching(
        inp(make_profile(), headers={"cache-control": "public, max-age=60"})
    )
    assert r.status == "warn"


def test_no_payment_handler_fails_u5() -> None:
    p = make_profile()
    p["ucp"]["payment_handlers"] = {}
    assert profile.u5_payment_handlers(inp(p)).status == "fail"


def test_ap2_not_declared() -> None:
    p = make_profile()
    del p["ucp"]["capabilities"]["dev.ucp.common.payment.ap2_mandate"]
    assert profile.a1_ap2_capability(inp(p)).status == "fail"


def test_ap2_without_checkout_capability_fails() -> None:
    p = make_profile()
    del p["ucp"]["capabilities"]["dev.ucp.shopping.checkout"]
    r = profile.a1_ap2_capability(inp(p))
    assert r.status == "fail" and "does not declare" in details(r)
    assert profile.u4_checkout_capability(inp(p)).status == "fail"


def test_ap2_without_sd_jwt_format_warns() -> None:
    p = make_profile()
    p["ucp"]["capabilities"]["dev.ucp.common.payment.ap2_mandate"][0].pop("config")
    assert profile.a1_ap2_capability(inp(p)).status == "warn"


def test_leaked_private_key_fails_loudly() -> None:
    k = MerchantKey()
    r = profile.a2_signing_keys(inp(make_profile(k, keys=[k.private_jwk()])))
    assert r.status == "fail" and "private key material" in details(r)


def test_keys_inside_ucp_object_fail() -> None:
    p = make_profile()
    p["ucp"]["keys"] = p.pop("keys")
    r = profile.a2_signing_keys(inp(p))
    assert r.status == "fail" and "top-level" in details(r)


def test_only_ed25519_key_fails() -> None:
    okp = {
        "kid": "http-1",
        "kty": "OKP",
        "crv": "Ed25519",
        "x": "11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo",
    }
    r = profile.a2_signing_keys(inp(make_profile(keys=[okp])))
    assert r.status == "fail" and "ECDSA" in details(r)


def test_p384_only_warns() -> None:
    k = MerchantKey(alg="ES384")
    assert profile.a2_signing_keys(inp(make_profile(k))).status == "warn"


def test_duplicate_kid_and_bad_use() -> None:
    k = MerchantKey()
    r = profile.a2_signing_keys(inp(make_profile(k, keys=[k.jwk(), k.jwk()])))
    assert r.status == "fail" and "duplicate" in details(r)
    r = profile.a2_signing_keys(inp(make_profile(k, keys=[k.jwk(use="enc")])))
    assert r.status == "fail"


# --- agent card ----------------------------------------------------------------------------


def test_agent_card_1_0_passes() -> None:
    i = inp(make_profile(), card=agent_card_1_0())
    assert agent_card.g1_agent_card(i).status == "pass"
    assert agent_card.g2_ap2_extension(i).status == "pass"


def test_no_agent_card_is_not_applicable() -> None:
    i = inp(make_profile())
    assert agent_card.g1_agent_card(i).status == "not_applicable"
    assert agent_card.g2_ap2_extension(i).status == "not_applicable"


def test_ap2_sample_style_0_3_card_warns() -> None:
    card = {
        "name": "MerchantAgent",
        "description": "x",
        "url": f"{SHOP}/a2a/merchant_agent",
        "protocolVersion": "0.3.0",
        "version": "1.0.0",
        "defaultInputModes": ["json"],
        "defaultOutputModes": ["json"],
        "skills": [],
        "capabilities": {
            "extensions": [
                {"uri": "https://github.com/google-agentic-commerce/ap2/v1", "required": True}
            ]
        },
    }
    i = inp(make_profile(), card=card)
    assert agent_card.g1_agent_card(i).status == "warn"
    assert agent_card.g2_ap2_extension(i).status == "pass"


def test_extension_not_required_warns_and_missing_fails() -> None:
    assert agent_card.g2_ap2_extension(inp(card=agent_card_1_0(required=False))).status == "warn"
    card = agent_card_1_0()
    card["capabilities"]["extensions"] = []
    assert agent_card.g2_ap2_extension(inp(card=card)).status == "fail"


def test_http_interface_fails() -> None:
    card = agent_card_1_0()
    card["supportedInterfaces"][0]["url"] = "http://shop.example.nl/a2a"
    assert agent_card.g1_agent_card(inp(card=card)).status == "fail"


# --- merchant signature --------------------------------------------------------------------


def test_ucp_signature_verifies() -> None:
    k = MerchantKey()
    sample = json.dumps(k.sign_checkout(sample_checkout()))
    r = signature.m1_merchant_signature(inp(make_profile(k), sample=sample))
    assert r.status == "pass", details(r)


def test_ucp_signature_survives_reformatting_and_key_order() -> None:
    k = MerchantKey()
    signed = k.sign_checkout(sample_checkout())
    reordered = dict(reversed(list(signed.items())))
    sample = json.dumps(reordered, indent=4)
    assert signature.m1_merchant_signature(inp(make_profile(k), sample=sample)).status == "pass"


def test_tampered_checkout_fails() -> None:
    k = MerchantKey()
    signed = k.sign_checkout(sample_checkout())
    signed["totals"][1]["amount"] = 1
    r = signature.m1_merchant_signature(inp(make_profile(k), sample=json.dumps(signed)))
    assert r.status == "fail" and "does NOT verify" in details(r)


def test_signature_by_other_key_fails() -> None:
    published, other = MerchantKey(), MerchantKey()
    sample = json.dumps(other.sign_checkout(sample_checkout()))
    assert (
        signature.m1_merchant_signature(inp(make_profile(published), sample=sample)).status
        == "fail"
    )


def test_unknown_kid_fails() -> None:
    k = MerchantKey()
    sample = json.dumps(k.sign_checkout(sample_checkout(), kid="old-key"))
    r = signature.m1_merchant_signature(inp(make_profile(k), sample=sample))
    assert r.status == "fail" and "old-key" in details(r)


def test_missing_merchant_authorization_fails() -> None:
    r = signature.m1_merchant_signature(inp(make_profile(), sample=json.dumps(sample_checkout())))
    assert r.status == "fail" and "merchant_authorization_missing" in details(r)


def test_compact_jws_in_merchant_authorization_fails() -> None:
    k = MerchantKey()
    c = sample_checkout()
    c["ap2"] = {"merchant_authorization": k.checkout_jwt({"x": 1})}
    r = signature.m1_merchant_signature(inp(make_profile(k), sample=json.dumps(c)))
    assert r.status == "fail" and "detached" in details(r)


def test_no_published_keys_is_error() -> None:
    k = MerchantKey()
    sample = json.dumps(k.sign_checkout(sample_checkout()))
    assert (
        signature.m1_merchant_signature(inp(make_profile(k, keys=[]), sample=sample)).status
        == "error"
    )


def test_a2a_checkout_jwt_verifies_alone_and_in_datapart() -> None:
    k = MerchantKey()
    jwt = k.checkout_jwt(a2a_checkout_payload())
    assert signature.m1_merchant_signature(inp(make_profile(k), sample=jwt)).status == "pass"
    part = {"ap2.checkout": {"checkout_jwt": jwt, "checkout_hash": checkout_hash(jwt)}}
    r = signature.m1_merchant_signature(inp(make_profile(k), sample=json.dumps(part)))
    assert r.status == "pass", details(r)


def test_a2a_hash_mismatch_fails() -> None:
    k = MerchantKey()
    jwt = k.checkout_jwt(a2a_checkout_payload())
    part = {"checkout_jwt": jwt, "checkout_hash": "AAAA"}
    assert (
        signature.m1_merchant_signature(inp(make_profile(k), sample=json.dumps(part))).status
        == "fail"
    )


def test_a2a_eddsa_fails() -> None:
    k = MerchantKey()
    jwt = k.checkout_jwt(a2a_checkout_payload(), alg="EdDSA")
    r = signature.m1_merchant_signature(inp(make_profile(k), sample=jwt))
    assert r.status == "fail" and "deterministic" in details(r)


def test_a2a_expired_sample_is_only_a_note_and_missing_merchant_warns() -> None:
    k = MerchantKey()
    expired = k.checkout_jwt(a2a_checkout_payload(exp=1_700_000_100))
    r = signature.m1_merchant_signature(inp(make_profile(k), sample=expired))
    assert r.status == "pass" and "expired" in details(r)
    payload = a2a_checkout_payload()
    del payload["merchant"]
    assert (
        signature.m1_merchant_signature(inp(make_profile(k), sample=k.checkout_jwt(payload))).status
        == "warn"
    )


def test_evidence_never_echoes_sample_values() -> None:
    k = MerchantKey()
    c = sample_checkout()
    c["buyer"] = {"email": "jan@example.nl", "name": "Jan Jansen"}
    r = signature.m1_merchant_signature(inp(make_profile(k), sample=json.dumps(k.sign_checkout(c))))
    dumped = r.model_dump_json()
    assert "jan@example.nl" not in dumped and "Jansen" not in dumped


def test_no_sample_is_not_applicable() -> None:
    assert signature.m1_merchant_signature(inp(make_profile())).status == "not_applicable"
