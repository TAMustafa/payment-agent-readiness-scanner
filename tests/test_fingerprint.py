"""Platform fingerprinting on hand-written home page fixtures."""

from __future__ import annotations

import pytest

from scanner.models import FetchedResource
from scanner.platform.fingerprint import fingerprint
from tests.conftest import fixture


def home(name: str, **kw: object) -> FetchedResource:
    return FetchedResource(
        url="https://shop.example.nl/", status_code=200, body=fixture(f"home/{name}.html"), **kw
    )  # type: ignore[arg-type]


@pytest.mark.parametrize("name", ["shopify", "woocommerce", "shopware6", "lightspeed", "magento"])
def test_detects_each_platform(name: str) -> None:
    info = fingerprint(home(name))
    assert info.platform == name
    assert info.signals and all(e.snippet for e in info.signals)
    assert info.signals[0].detail.startswith(name)


def test_shopware6_production_build_without_bundles_storefront() -> None:
    info = fingerprint(home("shopware6_prod"))
    assert info.platform == "shopware6"
    assert {"window.salesChannelId", "window.themeJsPublicPath"} <= {
        e.detail.split(": ", 1)[1].split(" (+")[0] for e in info.signals
    }


def test_weak_signal_alone_is_other() -> None:
    info = fingerprint(home("wordpress_only"))
    assert info.platform == "other"
    assert any("wp-content" in e.detail for e in info.signals)  # still shown as evidence


def test_headers_and_cookie_names_count() -> None:
    res = FetchedResource(
        url="https://x.nl/",
        status_code=200,
        body="<html></html>",
        headers={"x-shopid": "123"},
        cookie_names=["_shopify_y"],
    )
    info = fingerprint(res)
    assert info.platform == "shopify" and len(info.signals) == 2


def test_missing_home_is_other() -> None:
    assert fingerprint(None).platform == "other"


def test_rate_limited_home_is_not_fingerprinted() -> None:
    res = FetchedResource(url="https://x.nl/", status_code=429, body="Too many requests")
    info = fingerprint(res)
    assert info.platform == "other" and "HTTP 429" in info.signals[0].detail
