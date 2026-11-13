"""Regenerate the demo merchant fixture in ap2check/demo_data/.

Run: uv run python scripts/make_demo_fixture.py

This script is deliberately OUTSIDE the ap2check package: the package must never sign or
hold private keys (tests/test_safety.py). It creates a throw-away P-256 key, writes the
public JWK into a demo UCP profile, signs one demo checkout response the way UCP's AP2
extension prescribes (detached JWS over the RFC 8785 canonical checkout without `ap2`,
https://ucp.dev/2026-08-25/specification/payment/extensions/ap2-mandates/), and then
forgets the private key. Only public data is written to disk.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from ap2check.jose import b64url_encode, canonical_json

OUT = Path(__file__).resolve().parents[1] / "ap2check" / "demo_data"
SHOP = "https://demo-shop.example"
KID = "demo-2026-11"
V = "2026-08-25"


def main() -> None:
    private = ec.generate_private_key(ec.SECP256R1())  # never written anywhere
    nums = private.public_key().public_numbers()
    jwk = {
        "kid": KID,
        "kty": "EC",
        "crv": "P-256",
        "x": b64url_encode(nums.x.to_bytes(32, "big")),
        "y": b64url_encode(nums.y.to_bytes(32, "big")),
        "use": "sig",
        "alg": "ES256",
    }
    profile: dict[str, Any] = {
        "ucp": {
            "version": V,
            "services": {
                "dev.ucp.shopping": [
                    {
                        "version": V,
                        "spec": f"https://ucp.dev/{V}/specification/overview/",
                        "transport": "rest",
                        "endpoint": f"{SHOP}/ucp/v1",
                    }
                ]
            },
            "capabilities": {
                "dev.ucp.shopping.checkout": [
                    {
                        "version": V,
                        "spec": f"https://ucp.dev/{V}/specification/shopping/checkout/",
                        "schema": f"https://ucp.dev/{V}/schemas/shopping/checkout.json",
                    }
                ],
                "dev.ucp.common.payment.ap2_mandate": [
                    {
                        "version": V,
                        "spec": f"https://ucp.dev/{V}/specification/payment/extensions/ap2-mandates",
                        "schema": f"https://ucp.dev/{V}/schemas/common/payment_ap2_mandate.json",
                        "extends": "dev.ucp.shopping.checkout",
                        "config": {"vp_formats_supported": {"dc+sd-jwt": {}}},
                    }
                ],
            },
            "payment_handlers": {"com.google.pay": [{"id": "google_pay", "version": V}]},
        },
        "keys": [jwk],
    }
    checkout: dict[str, Any] = {
        "ucp": {"version": V},
        "id": "chk_demo_0001",
        "status": "ready_for_complete",
        "currency": "EUR",
        "line_items": [
            {
                "id": "li_1",
                "item": {"id": "mug-blue", "title": "Demo mug, blue", "price": 1295},
                "quantity": 2,
                "totals": [{"type": "subtotal", "amount": 2590}],
            }
        ],
        "totals": [
            {"type": "subtotal", "amount": 2590},
            {"type": "fulfillment", "amount": 495},
            {"type": "total", "amount": 3085},
        ],
        "links": [{"type": "privacy_policy", "url": f"{SHOP}/privacy"}],
    }
    header = b64url_encode(json.dumps({"alg": "ES256", "kid": KID}).encode())
    payload = b64url_encode(canonical_json(checkout))
    der = private.sign(f"{header}.{payload}".encode("ascii"), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    signature = b64url_encode(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
    checkout["ap2"] = {"merchant_authorization": f"{header}..{signature}"}

    OUT.mkdir(exist_ok=True)
    (OUT / "profile.json").write_text(json.dumps(profile, indent=2) + "\n")
    (OUT / "checkout.json").write_text(json.dumps(checkout, indent=2) + "\n")
    print(f"wrote {OUT}/profile.json and checkout.json (key {KID}; private key discarded)")


if __name__ == "__main__":
    main()
