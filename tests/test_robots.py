"""RFC 9309 behaviour of the robots.txt parser."""

from __future__ import annotations

import pytest

from scanner.fetch.robots import RobotsTxt, robots_from_resource
from scanner.models import FetchedResource
from tests.conftest import fixture


def test_longest_match_wins() -> None:
    r = RobotsTxt.parse("User-agent: *\nDisallow: /shop\nAllow: /shop/products\n")
    assert not r.is_allowed("x", "/shop/cart")
    assert r.is_allowed("x", "/shop/products/fiets")


def test_allow_wins_equal_length_tie() -> None:
    r = RobotsTxt.parse("User-agent: *\nDisallow: /page\nAllow: /page\n")
    assert r.is_allowed("x", "/page")


@pytest.mark.parametrize(
    ("path", "allowed"),
    [
        ("/collections/fietsen?sort_by=price", False),
        ("/collections/fietsen", True),
        ("/file.pdf", False),
        ("/file.pdf?x=1", True),
    ],
)
def test_wildcards_and_end_anchor(path: str, allowed: bool) -> None:
    r = RobotsTxt.parse("User-agent: *\nDisallow: /collections/*sort_by*\nDisallow: /*.pdf$\n")
    assert r.is_allowed("x", path) is allowed


def test_specific_group_replaces_star_group_case_insensitive() -> None:
    r = RobotsTxt.parse(fixture("robots/search_blocked.txt"))
    assert not r.is_allowed("oai-searchbot", "/")
    assert not r.is_allowed("ChatGPT-User", "/")  # shares the group with OAI-SearchBot
    d = r.decide("Claude-SearchBot", "/product/accu/")
    assert not d.allowed and d.group == "token" and d.rule is not None
    assert r.is_allowed("Claude-SearchBot", "/")  # its own group only blocks /product/
    assert r.decide("Googlebot", "/product/accu/").group == "*"


def test_empty_disallow_means_allow_and_robots_txt_always_allowed() -> None:
    r = RobotsTxt.parse("User-agent: *\nDisallow:\n\nUser-agent: badbot\nDisallow: /\n")
    assert r.is_allowed("x", "/anything")
    assert r.is_allowed("badbot", "/robots.txt")
    assert not r.is_allowed("badbot", "/")


def test_sitemaps_and_comments_parsed() -> None:
    r = RobotsTxt.parse(fixture("robots/shopify_default.txt"))
    assert r.sitemaps == ["https://shop.example.nl/sitemap.xml"]
    assert not r.is_allowed("GPTBot", "/checkout")
    assert r.is_allowed("GPTBot", "/products/accu")


def test_status_handling_rfc_9309() -> None:
    def res(code: int | None) -> FetchedResource:
        return FetchedResource(url="https://x.nl/robots.txt", status_code=code, body="")

    assert robots_from_resource(res(404)) is not None
    assert robots_from_resource(res(404)).policy == "allow_all"  # type: ignore[union-attr]
    assert robots_from_resource(res(503)).policy == "disallow_all"  # type: ignore[union-attr]
    assert robots_from_resource(res(None)) is None
