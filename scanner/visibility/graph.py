"""V1 subgraph (SPEC §4 V): plan questions -> budget check -> Send(ask) per
assistant x question x run -> results. Only openrouter.ai is contacted; never a shop.

Budget (Tarek, 2026-11-09: max EUR 10/month -> USD 10 cap), checked in layers:
1. pre-run: live prices x max_uses searches; refuse if > per_scan_usd, or if
   month-to-date (max of local ledger and OpenRouter's usage_monthly) + estimate > monthly_usd;
2. per call: spent + worst case (worst_case_searches) re-checked against BOTH caps before
   every paid call, so they are hard limits even if a provider searches more than expected;
3. OpenRouter key limit (HTTP 402) stops all remaining calls.
Every call's cost is written to the ledger immediately.
"""

from __future__ import annotations

import asyncio
import json
import operator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, TypedDict

import httpx
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Send

from scanner.models import VisibilityCall, VisibilityResult
from scanner.visibility import ledger
from scanner.visibility.config import Assistant, VisibilityConfig
from scanner.visibility.openrouter import BudgetExhausted, OpenRouterClient, OpenRouterError
from scanner.visibility.parse import parse_response
from scanner.visibility.prompts import Question, ShopIdentity, build_questions

EST_PROMPT_TOKENS = 4_000  # question + search results fed to the model (planning estimate)
EST_COMPLETION_TOKENS = 800


@dataclass
class VisDeps:
    config: VisibilityConfig
    client: OpenRouterClient | None  # None = no API key
    ledger_path: Path
    raw_dir: Path | None
    host: str
    spent: float = 0.0
    reserved: float = 0.0  # worst case of in-flight calls, held until their cost is booked
    exhausted: str | None = None
    month_to_date: float = 0.0
    semaphore: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(4))


class VisState(TypedDict, total=False):
    shop: dict[str, Any]
    override: list[dict[str, str]] | None
    questions: list[dict[str, str]]
    prices: dict[str, dict[str, float]]
    estimate: float
    month_to_date: float
    skipped_reason: str | None
    calls: Annotated[list[VisibilityCall], operator.add]


class AskInput(TypedDict):
    assistant: dict[str, Any]
    question: dict[str, str]
    run: int
    index: int
    shop: dict[str, Any]
    prices: dict[str, dict[str, float]]


def per_question_worst(a: Assistant, prices: dict[str, dict[str, float]], searches: float) -> float:
    p = prices.get(a.model)
    if p is None:  # live price missing -> snapshot from config
        return (
            a.snapshot.web_search * searches
            + EST_PROMPT_TOKENS * a.snapshot.prompt_per_m / 1e6
            + EST_COMPLETION_TOKENS * a.snapshot.completion_per_m / 1e6
        )
    return (
        p["web_search"] * searches
        + EST_PROMPT_TOKENS * p["prompt"]
        + EST_COMPLETION_TOKENS * p["completion"]
        + p.get("request", 0.0)
    )


async def plan(state: VisState, runtime: Runtime[VisDeps]) -> dict[str, Any]:
    if state.get("override"):
        return {"questions": state["override"]}
    run = runtime.context.config.run
    shop = ShopIdentity(
        **{
            **state["shop"],
            "terms": tuple(state["shop"]["terms"]),
            "categories": tuple(state["shop"]["categories"]),
        }
    )
    qs = build_questions(shop, run.brand_questions, run.category_questions)
    return {"questions": [{"kind": q.kind, "text": q.text} for q in qs]}


async def budget_check(state: VisState, runtime: Runtime[VisDeps]) -> dict[str, Any]:
    deps = runtime.context
    cfg = deps.config
    if deps.client is None:
        return {"skipped_reason": "OPENROUTER_API_KEY not set (add it to .env)"}
    if not state.get("questions"):
        return {"skipped_reason": "no questions: no brand or category names found"}
    models = [a.model for a in cfg.assistants]
    try:
        prices = await deps.client.model_prices(models)
    except Exception:  # live prices unavailable -> snapshot prices
        prices = {}
    n = len(state["questions"]) * cfg.run.runs
    estimate = round(
        # expected cost: searches capped by max_uses; the per-call guard below uses the
        # worst case, so the caps hold even if a provider searches more often
        sum(
            per_question_worst(a, prices, a.expected_searches or cfg.run.max_searches_per_question)
            for a in cfg.assistants
        )
        * n,
        4,
    )
    local = ledger.month_to_date(deps.ledger_path)
    remote = await deps.client.month_usage()
    mtd = max(local, remote or 0.0)
    deps.month_to_date = mtd
    out: dict[str, Any] = {"prices": prices, "estimate": estimate, "month_to_date": mtd}
    if estimate > cfg.budget.per_scan_usd:
        out["skipped_reason"] = (
            f"estimated USD {estimate:.2f} exceeds the per-scan cap "
            f"USD {cfg.budget.per_scan_usd:.2f}"
        )
    elif mtd + estimate > cfg.budget.monthly_usd:
        out["skipped_reason"] = (
            f"month-to-date USD {mtd:.2f} + estimate USD {estimate:.2f} would exceed the "
            f"monthly cap USD {cfg.budget.monthly_usd:.2f}"
        )
    return out


def fan_out(state: VisState, runtime: Runtime[VisDeps]) -> list[Send] | str:
    if state.get("skipped_reason"):
        return END
    cfg = runtime.context.config
    sends: list[Send] = []
    for a in cfg.assistants:
        for run in range(1, cfg.run.runs + 1):
            for i, q in enumerate(state["questions"]):
                sends.append(
                    Send(
                        "ask",
                        AskInput(
                            assistant=a.model_dump(),
                            question=q,
                            run=run,
                            index=i,
                            shop=state["shop"],
                            prices=state.get("prices", {}),
                        ),
                    )
                )
    return sends


async def ask(state: AskInput, runtime: Runtime[VisDeps]) -> dict[str, Any]:
    deps = runtime.context
    cfg = deps.config
    a = Assistant.model_validate(state["assistant"])
    q = state["question"]
    call = VisibilityCall(
        assistant=a.name, model=a.model, run=state["run"], kind=q["kind"], prompt=q["text"]
    )
    worst = per_question_worst(a, state["prices"], cfg.run.worst_case_searches)
    async with deps.semaphore:
        if deps.exhausted:
            call.error = deps.exhausted
            return {"calls": [call]}
        # Check and reserve with no await in between: parallel calls cannot all pass on
        # the same remaining budget (live run 2026-11-09 overshot the cap without this).
        committed = deps.spent + deps.reserved + worst
        if deps.month_to_date + committed > cfg.budget.monthly_usd:
            call.error = "skipped: monthly budget guard"
            return {"calls": [call]}
        if committed > cfg.budget.per_scan_usd:
            call.error = "skipped: per-scan budget guard"
            return {"calls": [call]}
        deps.reserved += worst
        assert deps.client is not None
        try:
            raw = await asyncio.wait_for(
                deps.client.chat(
                    a.model,
                    q["text"],
                    engine=a.engine,
                    max_uses=cfg.run.max_searches_per_question,
                    data_collection=cfg.privacy.data_collection,
                ),
                timeout=cfg.run.timeout_s,  # whole call incl. 429 retries (max_duration_s)
            )
        except BudgetExhausted as exc:
            deps.reserved -= worst
            deps.exhausted = str(exc)
            call.error = str(exc)
            return {"calls": [call]}
        except (OpenRouterError, httpx.ConnectError, httpx.ConnectTimeout) as exc:
            deps.reserved -= worst  # refused by OpenRouter or never sent: not billed
            call.error = f"{type(exc).__name__}: {str(exc)[:160]}"
            return {"calls": [call]}
        except Exception as exc:
            # Sent, but no answer (timeout, dropped connection): OpenRouter may have run and
            # billed it. Book the worst case so the caps can only be over-, never under-counted.
            deps.reserved -= worst
            deps.spent += worst
            ledger.append(
                deps.ledger_path,
                [
                    {
                        "host": deps.host,
                        "assistant": a.name,
                        "model": a.model,
                        "run": state["run"],
                        "cost_usd": round(worst, 6),
                        "usage_cost": None,
                        "searches": None,
                        "generation_id": None,
                        "note": f"no answer ({type(exc).__name__}): worst case booked",
                    }
                ],
            )
            call.cost_usd = round(worst, 6)
            call.error = (
                f"{type(exc).__name__}: no answer, cost unknown; worst case booked "
                f"(USD {worst:.4f})"
            )
            return {"calls": [call]}

    shop = state["shop"]
    parsed = parse_response(raw, shop["domain"], tuple(shop["terms"]))
    price = state["prices"].get(a.model)
    ws_fee = price["web_search"] if price else a.snapshot.web_search
    if parsed.usage_cost is not None:
        cost = parsed.usage_cost + (
            parsed.searches * ws_fee if cfg.run.add_search_fee_to_cost else 0
        )
    elif price:
        cost = (
            parsed.prompt_tokens * price["prompt"]
            + parsed.completion_tokens * price["completion"]
            + parsed.searches * ws_fee
        )
    else:
        cost = worst  # unknown cost: book the worst case
    deps.spent += cost
    deps.reserved -= worst
    ledger.append(
        deps.ledger_path,
        [
            {
                "host": deps.host,
                "assistant": a.name,
                "model": a.model,
                "run": state["run"],
                "cost_usd": round(cost, 6),
                "usage_cost": parsed.usage_cost,
                "searches": parsed.searches,
                "generation_id": parsed.generation_id,
            }
        ],
    )
    if deps.raw_dir is not None:
        deps.raw_dir.mkdir(parents=True, exist_ok=True)
        path = deps.raw_dir / f"{a.name.lower()}_run{state['run']}_q{state['index']:02d}.json"
        path.write_text(json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")
        call.raw_path = str(path)
    call.mentioned = parsed.mentioned
    call.mentioned_in_text = parsed.mentioned_in_text
    call.cited = parsed.cited
    call.position = parsed.position
    call.cited_url = parsed.cited_url
    call.cited_domains = parsed.cited_domains[:10]
    call.searches = parsed.searches
    call.cost_usd = round(cost, 6)
    call.generation_id = parsed.generation_id
    return {"calls": [call]}


def build_subgraph() -> Any:
    g = StateGraph(VisState, context_schema=VisDeps)
    g.add_node("plan", plan)
    g.add_node("budget_check", budget_check)
    g.add_node("ask", ask, input_schema=AskInput)
    g.add_edge(START, "plan")
    g.add_edge("plan", "budget_check")
    g.add_conditional_edges("budget_check", fan_out, ["ask", END])
    g.add_edge("ask", END)
    return g.compile()


async def run_visibility(
    shop: ShopIdentity,
    deps: VisDeps,
    override: list[Question] | None = None,
) -> VisibilityResult:
    deps.semaphore = asyncio.Semaphore(deps.config.run.concurrency)
    state: VisState = {
        "shop": {
            "brand": shop.brand,
            "domain": shop.domain,
            "terms": list(shop.terms),
            "categories": list(shop.categories),
        },
        "override": [{"kind": q.kind, "text": q.text} for q in override] if override else None,
        "calls": [],
    }
    final = await build_subgraph().ainvoke(state, context=deps)
    calls: list[VisibilityCall] = final.get("calls", [])
    return VisibilityResult(
        ran=bool(calls),
        skipped_reason=final.get("skipped_reason"),
        brand_terms=list(shop.terms),
        calls=sorted(calls, key=lambda c: (c.assistant, c.run, c.kind, c.prompt)),
        estimate_usd=final.get("estimate", 0.0),
        total_cost_usd=round(sum(c.cost_usd for c in calls), 6),
        month_to_date_usd=round(deps.month_to_date + deps.spent, 6),
        monthly_cap_usd=deps.config.budget.monthly_usd,
    )
