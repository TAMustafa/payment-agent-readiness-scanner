"""Minimal JOSE helpers for verifying merchant signatures (verify only, never sign).

- JCS canonical JSON (RFC 8785, https://www.rfc-editor.org/rfc/rfc8785), which UCP's AP2
  extension uses for the signed checkout payload
  (https://ucp.dev/2026-08-25/specification/payment/extensions/ap2-mandates/#canonicalization).
- EC public JWKs (RFC 7517/7518) and ECDSA JWS signatures ES256/ES384/ES512 (RFC 7518 §3.4:
  the signature is the raw R||S concatenation, not DER).
- Compact JWS and detached-content JWS (RFC 7515 Appendix F: `<header>..<signature>`).

There is deliberately no signing code and no private-key handling here: the checker only
verifies what the merchant publishes or pastes.
"""

from __future__ import annotations

import base64
import binascii
import json
import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature


class JoseError(ValueError):
    """Malformed token, key or JSON value."""


# alg -> (curve name, coordinate/scalar byte length, hash)
ALGS: dict[str, tuple[str, int, hashes.HashAlgorithm]] = {
    "ES256": ("P-256", 32, hashes.SHA256()),
    "ES384": ("P-384", 48, hashes.SHA384()),
    "ES512": ("P-521", 66, hashes.SHA512()),
}
CURVES: dict[str, ec.EllipticCurve] = {
    "P-256": ec.SECP256R1(),
    "P-384": ec.SECP384R1(),
    "P-521": ec.SECP521R1(),
}
CURVE_ALG = {curve: alg for alg, (curve, _, _) in ALGS.items()}
COORD_LEN = {curve: n for _, (curve, n, _) in ALGS.items()}


def b64url_decode(data: str) -> bytes:
    if not isinstance(data, str) or any(c in data for c in "+/= \n"):
        raise JoseError("not base64url (RFC 4648 §5, unpadded)")
    try:
        return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
    except (binascii.Error, ValueError) as exc:
        raise JoseError(f"invalid base64url: {exc}") from exc


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


# --- JCS (RFC 8785) ------------------------------------------------------------------------


def _es6_number(value: float | int) -> str:
    """Number serialisation of ECMAScript Number.prototype.toString (RFC 8785 §3.2.2.3)."""
    if isinstance(value, bool):
        raise JoseError("bool is not a number")
    f = float(value)
    if math.isnan(f) or math.isinf(f):
        raise JoseError("NaN/Infinity cannot be canonicalised")
    if f == 0:
        return "0"
    sign = "-" if f < 0 else ""
    # repr() gives the shortest round-tripping digits, like ECMAScript.
    _, digits_t, exp = Decimal(repr(abs(f))).normalize().as_tuple()
    digits = "".join(str(d) for d in digits_t)
    k = len(digits)
    n = int(exp) + k  # position of the decimal point relative to the digits
    if k <= n <= 21:
        out = digits + "0" * (n - k)
    elif 0 < n <= 21:
        out = digits[:n] + "." + digits[n:]
    elif -6 < n <= 0:
        out = "0." + "0" * (-n) + digits
    else:
        e = n - 1
        mantissa = digits if k == 1 else digits[0] + "." + digits[1:]
        out = f"{mantissa}e{'+' if e >= 0 else '-'}{abs(e)}"
    return sign + out


def canonical_json(value: Any) -> bytes:
    """RFC 8785 JSON Canonicalization Scheme, UTF-8 encoded."""
    return _jcs(value).encode("utf-8")


def _jcs(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        # Integers beyond 2^53 are not exactly representable in I-JSON: serialise as doubles.
        return str(value) if abs(value) <= 2**53 else _es6_number(value)
    if isinstance(value, float):
        return _es6_number(value)
    if isinstance(value, str):
        # json.dumps(ensure_ascii=False) matches ECMAScript JSON.stringify for strings:
        # only " \ and control characters are escaped, lowercase \u00xx.
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ",".join(_jcs(v) for v in value) + "]"
    if isinstance(value, dict):
        for k in value:
            if not isinstance(k, str):
                raise JoseError("object keys must be strings")
        # Keys sorted by UTF-16 code units (RFC 8785 §3.2.3).
        keys = sorted(value, key=lambda k: k.encode("utf-16-be"))
        return "{" + ",".join(f"{_jcs(k)}:{_jcs(value[k])}" for k in keys) + "}"
    raise JoseError(f"unsupported JSON type {type(value).__name__}")


# --- Keys ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class EcKey:
    kid: str | None
    crv: str
    alg: str  # derived from the curve
    key: ec.EllipticCurvePublicKey


def ec_key_from_jwk(jwk: Any) -> EcKey:
    """Parse a public EC JWK; raises JoseError explaining what is wrong with it."""
    if not isinstance(jwk, dict):
        raise JoseError("key is not a JSON object")
    if jwk.get("kty") != "EC":
        raise JoseError(f"kty is {jwk.get('kty')!r}, not 'EC'")
    crv = jwk.get("crv")
    if crv not in CURVES:
        raise JoseError(f"crv {crv!r} is not P-256, P-384 or P-521")
    n = COORD_LEN[crv]
    coords: list[int] = []
    for name in ("x", "y"):
        raw = b64url_decode(jwk.get(name) or "")
        if len(raw) != n:
            raise JoseError(f"{name} is {len(raw)} bytes, {crv} needs {n}")
        coords.append(int.from_bytes(raw, "big"))
    try:
        key = ec.EllipticCurvePublicNumbers(coords[0], coords[1], CURVES[crv]).public_key()
    except ValueError as exc:
        raise JoseError(f"point is not on curve {crv}") from exc
    kid = jwk.get("kid")
    return EcKey(kid=kid if isinstance(kid, str) else None, crv=crv, alg=CURVE_ALG[crv], key=key)


def verify_es(alg: str, key: EcKey, signing_input: bytes, signature: bytes) -> bool:
    if alg not in ALGS:
        raise JoseError(f"alg {alg!r} is not ES256/ES384/ES512")
    curve, n, digest = ALGS[alg]
    if key.crv != curve:
        raise JoseError(f"{alg} needs a {curve} key, key {key.kid!r} is {key.crv}")
    if len(signature) != 2 * n:
        raise JoseError(f"{alg} signature must be {2 * n} bytes (R||S), got {len(signature)}")
    r = int.from_bytes(signature[:n], "big")
    s = int.from_bytes(signature[n:], "big")
    try:
        key.key.verify(encode_dss_signature(r, s), signing_input, ec.ECDSA(digest))
    except InvalidSignature:
        return False
    return True


# --- JWS -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Jws:
    header: dict[str, Any]
    header_b64: str
    payload_b64: str  # "" for detached content
    signature: bytes


def parse_jws(token: str) -> Jws:
    """Compact (`h.p.s`) or detached (`h..s`) JWS. Raises JoseError."""
    if not isinstance(token, str):
        raise JoseError("token is not a string")
    parts = token.strip().split(".")
    if len(parts) != 3:
        raise JoseError(f"expected 3 dot-separated parts, got {len(parts)}")
    h, p, s = parts
    try:
        header = json.loads(b64url_decode(h))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise JoseError("protected header is not JSON") from exc
    if not isinstance(header, dict):
        raise JoseError("protected header is not a JSON object")
    return Jws(header=header, header_b64=h, payload_b64=p, signature=b64url_decode(s))


def detached_signing_input(jws: Jws, payload: bytes) -> bytes:
    """Signing input for detached content; honours RFC 7797 `b64: false`."""
    if jws.header.get("b64") is False:
        return jws.header_b64.encode("ascii") + b"." + payload
    return f"{jws.header_b64}.{b64url_encode(payload)}".encode("ascii")
