"""V1 AI visibility against a fake OpenRouter (httpx.MockTransport). No paid calls, ever."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from scanner.graph import run_scan
from scanner.models import FetchedResource, PageSample, ScanOptions
from scanner.visibility import ledger
from scanner.visibility.config import DEFAULT_PATH, load_config
from scanner.visibility.parse import parse_response, term_in_text
from scanner.visibility.prompts import build_questions, identify, load_override
from tests.conftest import FakeShop

ORIGIN = "https://www.dille-kamille.nl"
HOME = """<html><head><title>Dille &amp; Kamille - Koken, wonen en tuin</title>
<script type="application/ld+json">{"@type":"Organization","name":"Dille & Kamille",
"url":"https://www.dille-kamille.nl"}</script></head><body><nav>
<a href="/koken/">Koken</a><a href="/wonen/">Wonen</a><a href="/tuin/">Tuin</a>
<a href="/servies/">Servies</a><a href="/klantenservice/">Klantenservice</a>
<a href="/sale/">Sale</a></nav></body></html>"""
MODELS = {
    "data": [
        {
            "id": "openai/gpt-6-luna",
            "pricing": {"prompt": "0.0000001", "completion": "0.0000005", "web_search": "0.01"},
        },
        {
            "id": "google/gemini-3.1-flash-lite",
            "pricing": {"prompt": "0.00000025", "completion": "0.0000015", "web_search": "0.014"},
        },
    ]
}


def answer(mention: bool, cost: float = 0.012) -> dict[str, Any]:
    text = "Probeer Dille & Kamille of Xenos." if mention else "Probeer Xenos of HEMA."
    anns = [
        {
            "type": "url_citation",
            "url_citation": {"url": "https://www.xenos.nl/x", "start_index": 1, "end_index": 5},
        }
    ]
    if mention:
        anns.append(
            {
                "type": "url_citation",
                "url_citation": {
                    "url": "https://www.dille-kamille.nl/koken/",
                    "start_index": 9,
                    "end_index": 20,
                },
            }
        )
    return {
        "id": "gen-1",
        "choices": [{"message": {"content": text, "annotations": anns}}],
        "usage": {
            "prompt_tokens": 3000,
            "completion_tokens": 400,
            "cost": cost,
            "server_tool_use_details": {"web_search_requests": 1},
        },
    }


class FakeOpenRouter:
    def __init__(
        self, usage_monthly: float = 0.0, fail_402_after: int | None = None, cost: float = 0.012
    ) -> None:
        self.usage_monthly = usage_monthly
        self.cost = cost
        self.fail_402_after = fail_402_after
        self.posts: list[dict[str, Any]] = []
        self.gets: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.url.host == "openrouter.ai"  # never anything else
        path = request.url.path
        if request.method == "GET":
            self.gets.append(path)
            if path.endswith("/models"):
                return httpx.Response(200, json=MODELS)
            if path.endswith("/key"):
                return httpx.Response(200, json={"data": {"usage_monthly": self.usage_monthly}})
        if request.method == "POST" and path.endswith("/chat/completions"):
            body = json.loads(request.content)
            self.posts.append(body)
            if self.fail_402_after is not None and len(self.posts) > self.fail_402_after:
                return httpx.Response(
                    402, json={"error": {"metadata": {"limit_source": "openrouter_key_limit"}}}
                )
            prompt = body["messages"][0]["content"]
            return httpx.Response(
                200, json=answer(mention="Kamille" in prompt or "koken" in prompt.lower())
            )
        return httpx.Response(404)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


def config_file(tmp_path: Path, **replace: str) -> str:
    text = DEFAULT_PATH.read_text(encoding="utf-8")
    for old, new in replace.items():
        text = text.replace(old, new)
    path = tmp_path / "visibility.toml"
    path.write_text(text, encoding="utf-8")
    return str(path)


async def vscan(
    tmp_path: Path,
    fake: FakeOpenRouter,
    monkeypatch: pytest.MonkeyPatch,
    key: str | None = "test-key",
    cfg: str | None = None,
    options: ScanOptions | None = None,
) -> Any:
    if key:
        monkeypatch.setenv("OPENROUTER_API_KEY", key)
    else:
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    shop = FakeShop({f"{ORIGIN}/": (200, HOME)})
    return await run_scan(
        ORIGIN,
        options or ScanOptions(checks=["D1"], visibility=True),
        transport=shop.transport,
        min_interval_s=0,
        openrouter_transport=fake.transport,
        visibility_config_path=cfg or config_file(tmp_path),
        visibility_ledger_path=str(tmp_path / "ledger.jsonl"),
    )


def v1(report: Any) -> Any:
    return next(r for r in report.results if r.id == "V1.prompt_visibility")


# --- units -----------------------------------------------------------------------------


def test_config_matches_tarek_decisions() -> None:
    cfg = load_config()
    assert cfg.budget.monthly_usd <= 10.0
    assert [a.name for a in cfg.assistants] == ["ChatGPT", "Gemini"]
    assert all(a.engine == "native" for a in cfg.assistants)
    assert cfg.run.runs == 2 and cfg.privacy.data_collection == "deny"


def test_identity_and_questions_are_deterministic() -> None:
    home = FetchedResource(url=f"{ORIGIN}/", status_code=200, body=HOME)
    shop = identify(ORIGIN, home, PageSample(), 8)
    assert shop.brand == "Dille & Kamille" and shop.domain == "dille-kamille.nl"
    assert {"dille & kamille", "dille-kamille.nl", "dille kamille"} <= set(shop.terms)
    assert shop.categories == ("koken", "wonen", "tuin", "servies")  # no service/sale links
    qs = build_questions(shop, 2, 8)
    assert len(qs) == 10 and [q.kind for q in qs].count("brand") == 2
    assert all("in Nederland" in q.text for q in qs)
    assert qs == build_questions(shop, 2, 8)


def test_whole_word_mentions_and_citation_position() -> None:
    assert term_in_text("hema", "Kijk bij HEMA.") and not term_in_text("hema", "schema")
    p = parse_response(answer(True), "dille-kamille.nl", ("dille & kamille",))
    assert p.mentioned and p.cited and p.position == 2 and p.searches == 1
    assert p.cited_domains == ["xenos.nl", "dille-kamille.nl"]
    miss = parse_response(answer(False), "dille-kamille.nl", ("dille & kamille",))
    assert not miss.mentioned and miss.position is None


def test_ledger_month_rollover(tmp_path: Path) -> None:
    path = tmp_path / "l.jsonl"
    ledger.append(path, [{"cost_usd": 4.0}], now=datetime(2026, 10, 31, 23, tzinfo=UTC))
    ledger.append(path, [{"cost_usd": 1.5}], now=datetime(2026, 11, 1, 0, 30, tzinfo=UTC))
    assert ledger.month_to_date(path, datetime(2026, 11, 9, tzinfo=UTC)) == 1.5


def test_prompts_override(tmp_path: Path) -> None:
    f = tmp_path / "q.txt"
    f.write_text("# eigen vragen\nBeste theepot kopen in Nederland?\n\n", encoding="utf-8")
    assert [q.text for q in load_override(f)] == ["Beste theepot kopen in Nederland?"]


# --- full scan -------------------------------------------------------------------------


async def test_full_run_two_assistants_two_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeOpenRouter()
    cfg = config_file(tmp_path, **{"per_scan_usd = 1.40": "per_scan_usd = 2.00"})
    report = await vscan(tmp_path, fake, monkeypatch, cfg=cfg)
    r = v1(report)
    assert len(fake.posts) == 10 * 2 * 2  # questions x runs x assistants
    body = fake.posts[0]
    assert body["tools"][0]["type"] == "openrouter:web_search"
    assert body["tools"][0]["parameters"] == {"engine": "native", "max_uses": 1}
    assert body["provider"] == {"data_collection": "deny"}
    vis = report.visibility
    assert vis is not None and len(vis.calls) == 40 and all(c.error is None for c in vis.calls)
    assert r.status in ("pass", "warn", "fail") and 0 < r.score_fraction < 1
    assert "Snapshot" in r.evidence[0].detail
    # cost = usage.cost (verified live 2026-11-09: it already includes the search fee)
    assert vis.total_cost_usd == pytest.approx(40 * 0.012)
    rows = (tmp_path / "ledger.jsonl").read_text().splitlines()
    assert len(rows) == 40 and "test-key" not in "".join(rows)


async def test_per_scan_cap_refuses_before_any_paid_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeOpenRouter()
    cfg = config_file(tmp_path, **{"per_scan_usd = 1.40": "per_scan_usd = 0.05"})
    r = v1(await vscan(tmp_path, fake, monkeypatch, cfg=cfg))
    assert r.status == "error" and "per-scan cap" in r.evidence[0].detail
    assert fake.posts == []


async def test_monthly_cap_uses_higher_of_ledger_and_openrouter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeOpenRouter(usage_monthly=9.80)  # OpenRouter says 9.80 spent, ledger says 0
    cfg = config_file(tmp_path, **{"per_scan_usd = 1.40": "per_scan_usd = 2.00"})
    r = v1(await vscan(tmp_path, fake, monkeypatch, cfg=cfg))
    assert r.status == "error" and "monthly cap" in r.evidence[0].detail
    assert fake.posts == []


async def test_per_scan_cap_is_hard_during_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even if actual costs are higher than estimated, spending stops at the per-scan cap."""
    fake = FakeOpenRouter(cost=0.03)  # each call costs more than estimated, < worst case
    cfg = config_file(
        tmp_path,
        **{
            "per_scan_usd = 1.40": "per_scan_usd = 0.30",
            "expected_searches = 1.7": "expected_searches = 0.1",
            "expected_searches = 2.7": "expected_searches = 0.1",
        },
    )
    report = await vscan(tmp_path, fake, monkeypatch, cfg=cfg)
    vis = report.visibility
    assert vis is not None and 0 < len(fake.posts) < 40
    # reservation before each call: 4 parallel calls cannot overshoot the cap together
    assert vis.total_cost_usd <= 0.30
    assert any(c.error == "skipped: per-scan budget guard" for c in vis.calls)


def test_gemini_redirect_citations_use_title_domain() -> None:
    raw = {
        "choices": [
            {
                "message": {
                    "content": "Kijk bij Thuisbezorgd.nl.",
                    "annotations": [
                        {
                            "type": "url_citation",
                            "url_citation": {
                                "url": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZ1",
                                "title": "dutchreview.com",
                                "start_index": "0",
                                "end_index": "10",
                            },
                        },
                        {
                            "type": "url_citation",
                            "url_citation": {
                                "url": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZ2",
                                "title": "thuisbezorgd.nl",
                                "start_index": "20",
                                "end_index": "30",
                            },
                        },
                    ],
                }
            }
        ]
    }
    p = parse_response(raw, "thuisbezorgd.nl", ("thuisbezorgd",))
    assert p.cited_domains == ["dutchreview.com", "thuisbezorgd.nl"]
    assert p.cited and p.position == 2


def test_estimate_uses_measured_searches() -> None:
    from scanner.visibility.graph import per_question_worst

    a = next(x for x in load_config().assistants if x.name == "Gemini")
    prices = {a.model: {"prompt": 0.0, "completion": 0.0, "web_search": 0.014, "request": 0.0}}
    assert per_question_worst(a, prices, a.expected_searches or 1) == pytest.approx(0.0378)


async def test_openrouter_402_stops_remaining_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeOpenRouter(fail_402_after=5)
    cfg = config_file(tmp_path, **{"per_scan_usd = 1.40": "per_scan_usd = 2.00"})
    report = await vscan(tmp_path, fake, monkeypatch, cfg=cfg)
    vis = report.visibility
    assert vis is not None
    assert len(fake.posts) <= 5 + 4  # at most the in-flight calls (concurrency 4) after a 402
    assert sum(1 for c in vis.calls if c.error and "budget exhausted" in c.error) >= 30
    assert v1(report).status in ("pass", "warn", "fail", "error")


async def test_no_key_means_no_requests(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeOpenRouter()
    r = v1(await vscan(tmp_path, fake, monkeypatch, key=None))
    assert r.status == "error" and "OPENROUTER_API_KEY not set" in r.evidence[0].detail
    assert fake.posts == [] and fake.gets == []


async def test_visibility_off_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeOpenRouter()
    report = await vscan(tmp_path, fake, monkeypatch, options=ScanOptions(checks=["D1"]))
    assert report.visibility is None and fake.posts == [] and fake.gets == []
    assert all(r.id != "V1.prompt_visibility" for r in report.results)


class TimeoutOnce(FakeOpenRouter):
    """The first chat call times out after it was sent: OpenRouter may have billed it."""

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and not self.posts:
            self.posts.append(json.loads(request.content))
            raise httpx.ReadTimeout("timed out", request=request)
        return super().handler(request)


async def test_call_that_times_out_is_booked_at_worst_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = TimeoutOnce()
    cfg = config_file(tmp_path, **{"per_scan_usd = 1.40": "per_scan_usd = 2.00"})
    report = await vscan(tmp_path, fake, monkeypatch, cfg=cfg)
    vis = report.visibility
    assert vis is not None
    lost = [c for c in vis.calls if c.error]
    assert len(lost) == 1 and "worst case booked" in (lost[0].error or "")
    assert lost[0].cost_usd > 0.012  # more than a normal call: never under-counted
    assert vis.total_cost_usd == pytest.approx(39 * 0.012 + lost[0].cost_usd)
    rows = [json.loads(x) for x in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    assert len(rows) == 40
    assert sum(r["cost_usd"] for r in rows) == pytest.approx(vis.total_cost_usd)
