"""JCS canonicalisation and ECDSA verification."""

from __future__ import annotations

import json

import pytest

from ap2check.jose import (
    JoseError,
    b64url_decode,
    canonical_json,
    ec_key_from_jwk,
    parse_jws,
    verify_es,
)
from tests.helpers import MerchantKey


def test_jcs_rfc8785_example() -> None:
    # RFC 8785 §3.2.4 sample input / output.
    data = json.loads(
        '{"numbers": [333333333.33333329, 1E30, 4.50, 2e-3, 0.000000000000000000000000001],'
        '"string": "\\u20ac$\\u000F\\u000aA\'\\u0042\\u0022\\u005c\\\\\\"\\/",'
        '"literals": [null, true, false]}'
    )
    expected = (
        '{"literals":[null,true,false],"numbers":[333333333.3333333,1e+30,4.5,0.002,1e-27],'
        '"string":"€$\\u000f\\nA\'B\\"\\\\\\\\\\"/"}'
    )
    assert canonical_json(data).decode() == expected


@pytest.mark.parametrize(
    ("value", "out"),
    [
        (0.0, "0"),
        (-0.0, "0"),
        (100.0, "100"),
        (1e21, "1e+21"),
        (1e20, "100000000000000000000"),
        (0.000001, "0.000001"),
        (1e-7, "1e-7"),
        (-1.5, "-1.5"),
        (2**60, "1152921504606847000"),
    ],
)
def test_jcs_numbers(value: float, out: str) -> None:
    assert canonical_json(value).decode() == out


def test_jcs_sorts_keys_by_utf16() -> None:
    # RFC 8785 §3.2.3: UTF-16 code units, not code points. U+1F600 (surrogate 0xD83D) sorts
    # before U+FB33, although its code point is higher.
    data = {"דּ": 1, "\U0001f600": 2, "a": 3}
    assert canonical_json(data).decode() == '{"a":3,"\U0001f600":2,"דּ":1}'


def test_key_and_signature_roundtrip() -> None:
    k = MerchantKey()
    key = ec_key_from_jwk(k.jwk())
    jwt = k.checkout_jwt({"a": 1})
    h, p, _ = jwt.split(".")
    jws = parse_jws(jwt)
    assert verify_es("ES256", key, f"{h}.{p}".encode(), jws.signature)
    assert not verify_es("ES256", key, f"{h}.{p}x".encode(), jws.signature)


def test_point_not_on_curve_is_rejected() -> None:
    jwk = MerchantKey().jwk()
    y = bytearray(b64url_decode(jwk["y"]))
    y[-1] ^= 1
    from ap2check.jose import b64url_encode

    jwk["y"] = b64url_encode(bytes(y))
    with pytest.raises(JoseError, match="not on curve"):
        ec_key_from_jwk(jwk)


def test_wrong_curve_for_alg() -> None:
    key = ec_key_from_jwk(MerchantKey(alg="ES384").jwk())
    with pytest.raises(JoseError, match="needs a P-256 key"):
        verify_es("ES256", key, b"x", b"\0" * 64)


def test_padded_base64_rejected() -> None:
    with pytest.raises(JoseError):
        b64url_decode("YQ==")
