"""Test-only helpers: generate merchant keys, sign checkouts, build fake merchants.

Signing code lives here on purpose: the ap2check package must never sign anything
(tests/test_safety.py)."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from ap2check.jose import b64url_encode, canonical_json
from tests.conftest import FakeShop

SHOP = "https://shop.example.nl"
PUBLIC_IP = "93.184.215.14"

_CURVES = {
    "ES256": (ec.SECP256R1(), 32, hashes.SHA256(), "P-256"),
    "ES384": (ec.SECP384R1(), 48, hashes.SHA384(), "P-384"),
}


async def public_resolver(host: str) -> list[str]:
    return [PUBLIC_IP]


class MerchantKey:
    def __init__(self, kid: str = "merchant-2026-11", alg: str = "ES256") -> None:
        curve, self.n, self.hash, self.crv = _CURVES[alg]
        self.kid, self.alg = kid, alg
        self.private = ec.generate_private_key(curve)

    def jwk(self, **extra: Any) -> dict[str, Any]:
        nums = self.private.public_key().public_numbers()
        return {
            "kid": self.kid,
            "kty": "EC",
            "crv": self.crv,
            "x": b64url_encode(nums.x.to_bytes(self.n, "big")),
            "y": b64url_encode(nums.y.to_bytes(self.n, "big")),
            "use": "sig",
            "alg": self.alg,
            **extra,
        }

    def private_jwk(self) -> dict[str, Any]:
        d = self.private.private_numbers().private_value
        return {**self.jwk(), "d": b64url_encode(d.to_bytes(self.n, "big"))}

    def _sig(self, data: bytes) -> str:
        r, s = decode_dss_signature(self.private.sign(data, ec.ECDSA(self.hash)))
        return b64url_encode(r.to_bytes(self.n, "big") + s.to_bytes(self.n, "big"))

    def sign_checkout(self, checkout: dict[str, Any], kid: str | None = None) -> dict[str, Any]:
        """UCP: detached JWS over JCS(checkout without ap2), in ap2.merchant_authorization."""
        body = {k: v for k, v in checkout.items() if k != "ap2"}
        header = b64url_encode(json.dumps({"alg": self.alg, "kid": kid or self.kid}).encode())
        payload = b64url_encode(canonical_json(body))
        sig = self._sig(f"{header}.{payload}".encode())
        out = copy.deepcopy(checkout)
        out.setdefault("ap2", {})["merchant_authorization"] = f"{header}..{sig}"
        return out

    def checkout_jwt(self, payload: dict[str, Any], alg: str | None = None) -> str:
        header = b64url_encode(
            json.dumps({"alg": alg or self.alg, "typ": "JWT", "kid": self.kid}).encode()
        )
        body = b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
        return f"{header}.{body}.{self._sig(f'{header}.{body}'.encode())}"


def checkout_hash(jwt: str) -> str:
    return b64url_encode(hashlib.sha256(jwt.encode()).digest())


def sample_checkout() -> dict[str, Any]:
    return {
        "id": "chk_test_1",
        "status": "ready_for_complete",
        "currency": "EUR",
        "line_items": [
            {"id": "li_1", "item": {"id": "sku-1", "title": "Mok", "price": 1299}, "quantity": 1}
        ],
        "totals": [{"type": "subtotal", "amount": 1299}, {"type": "total", "amount": 1299.5}],
        "ucp": {"version": "2026-08-25"},
    }


def a2a_checkout_payload(exp: int = 4_102_444_800) -> dict[str, Any]:
    return {
        "id": "cart_1",
        "merchant": {"id": "m-1", "name": "Test Shop", "website": SHOP},
        "line_items": [{"id": "li_1", "quantity": 1}],
        "currency": "EUR",
        "totals": [{"type": "total", "amount": 1299}],
        "iat": 1_700_000_000,
        "exp": exp,
    }


def profile(key: MerchantKey | None = None, **overrides: Any) -> dict[str, Any]:
    """A complete, valid UCP 2026-08-25 business profile with AP2 mandates."""
    key = key or MerchantKey()
    prof: dict[str, Any] = {
        "ucp": {
            "version": "2026-08-25",
            "services": {
                "dev.ucp.shopping": [
                    {"version": "2026-08-25", "transport": "rest", "endpoint": f"{SHOP}/ucp/v1"},
                ]
            },
            "capabilities": {
                "dev.ucp.shopping.checkout": [{"version": "2026-08-25"}],
                "dev.ucp.common.payment.ap2_mandate": [
                    {
                        "version": "2026-08-25",
                        "spec": "https://ucp.dev/2026-08-25/specification/payment/extensions/ap2-mandates",
                        "schema": "https://ucp.dev/2026-08-25/schemas/common/payment_ap2_mandate.json",
                        "extends": "dev.ucp.shopping.checkout",
                        "config": {"vp_formats_supported": {"dc+sd-jwt": {}}},
                    }
                ],
            },
            "payment_handlers": {"com.google.pay": [{"id": "gpay", "version": "2026-08-25"}]},
        },
        "keys": [key.jwk()],
    }
    prof.update(overrides)
    return prof


GOOD_HEADERS = {
    "content-type": "application/json",
    "cache-control": "public, max-age=300",
    "etag": '"v1"',
}


def agent_card_1_0(required: bool = True) -> dict[str, Any]:
    return {
        "name": "Test Shop merchant agent",
        "description": "Sells mugs.",
        "version": "1.0.0",
        "supportedInterfaces": [
            {"url": f"{SHOP}/a2a/v1", "protocolBinding": "JSONRPC", "protocolVersion": "1.0"}
        ],
        "capabilities": {
            "streaming": False,
            "extensions": [
                {
                    "uri": "https://github.com/google-agentic-commerce/ap2/v1",
                    "description": "Supports the Agent Payments Protocol.",
                    "required": required,
                }
            ],
        },
        "defaultInputModes": ["application/json"],
        "defaultOutputModes": ["application/json"],
        "skills": [
            {"id": "search_catalog", "name": "Search", "description": "Search", "tags": ["shop"]}
        ],
    }


def merchant(
    prof: dict[str, Any] | None = None,
    *,
    headers: dict[str, str] | None = None,
    card: dict[str, Any] | None = None,
    robots: str = "User-agent: *\nDisallow: /cart\n",
) -> FakeShop:
    routes: dict[str, Any] = {f"{SHOP}/robots.txt": (200, robots)}
    if prof is not None:
        routes[f"{SHOP}/.well-known/ucp"] = (200, json.dumps(prof), headers or GOOD_HEADERS)
    if card is not None:
        routes[f"{SHOP}/.well-known/agent-card.json"] = (
            200,
            json.dumps(card),
            {"content-type": "application/json"},
        )
    return FakeShop(routes)
