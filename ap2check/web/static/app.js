// AP2 Readiness Check front-end. All report text is inserted with textContent (never
// innerHTML): profiles and agent cards come from third-party servers.
"use strict";

const STAGES = [
  ["discovery", "Step 1 · Agents can find your shop"],
  ["checkout", "Step 2 · Agents can start a checkout"],
  ["ap2", "Steps 3–4 · AP2 switched on, signing key published"],
  ["signature", "Step 5 · Your checkout signature"],
  ["a2a", "Optional · A2A merchant agent"],
];
const STATUS_LABEL = {
  pass: "OK", warn: "Improve", fail: "Problem", not_applicable: "Not checked",
  error: "Couldn't check",
};
const STEP_MARK = { done: "✓", problem: "!", unknown: "?", todo: "" };
const STEP_WORD = { done: "done", problem: "needs fixing", unknown: "could not be checked",
  todo: "not reached yet" };
const NEEDS_ATTENTION = new Set(["fail", "warn", "error"]);

const $ = (id) => document.getElementById(id);

function el(tag, attrs = {}, text) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text !== undefined) node.textContent = text;
  return node;
}

function safeHref(url) {
  try {
    const u = new URL(url);
    return u.protocol === "https:" ? u.href : null;
  } catch {
    return null;
  }
}

// Guidance templates say "https://<your-domain>"; show the shop's own address instead.
let origin = "";
const mine = (text) => text.replaceAll("https://<your-domain>", origin);

function renderCheck(r) {
  const node = el("details", { class: `check ${r.status}` });
  if (NEEDS_ATTENTION.has(r.status)) node.open = true;
  const head = el("summary", { class: "check-head" });
  const chip = el("span", { class: `chip ${r.status}` }, STATUS_LABEL[r.status] || r.status);
  head.append(chip, el("span", { class: "check-label" }, r.label));
  node.append(head);

  const body = el("div", { class: "check-body" });
  const list = el("ul", { class: "evidence" });
  for (const e of r.evidence) {
    const li = el("li", {}, e.detail);
    if (e.snippet) li.append(el("pre", {}, e.snippet));
    list.append(li);
  }
  body.append(list);
  if (r.guidance) {
    const g = el("div", { class: "guidance" });
    g.append(el("p", { class: "guidance-title" }, "How to fix"),
      el("p", { class: "guidance-text" }, mine(r.guidance)));
    body.append(g);
  }
  const meta = el("p", { class: "check-meta" });
  meta.append(el("code", {}, r.id));
  const href = safeHref(r.spec);
  if (href) {
    meta.append(document.createTextNode(" · "));
    meta.append(el("a", { href, target: "_blank", rel: "noopener noreferrer" }, "Read the spec"));
  }
  body.append(meta);
  node.append(body);
  return node;
}

function renderSteps(steps) {
  const ol = el("ol", { class: "steps" });
  steps.forEach((s, i) => {
    const li = el("li", { class: `step ${s.state}${s.current ? " current" : ""}` });
    li.append(el("span", { class: "step-mark", "aria-hidden": "true" },
      STEP_MARK[s.state] || String(i + 1)));
    const text = el("span", { class: "step-text" }, s.title);
    text.append(el("span", { class: "step-state" },
      s.current && s.state === "todo" ? " — your next step" : ` — ${STEP_WORD[s.state]}`));
    li.append(text);
    ol.append(li);
  });
  return ol;
}

function summaryText(report) {
  const lines = [
    `AP2 readiness check for ${report.target} (${report.checked_at})`,
    `Result: ${report.verdict.title}`,
    report.verdict.summary,
    "",
    "Progress:",
    ...report.steps.map((s, i) => `  ${i + 1}. ${s.title}: ${STEP_WORD[s.state]}`),
    "",
    `Next step: ${mine(report.next_step)}`,
  ];
  const open = report.results.filter((r) => NEEDS_ATTENTION.has(r.status));
  if (open.length) lines.push("", "Findings:");
  for (const r of open) {
    lines.push(`- ${r.label} [${r.id}] — ${STATUS_LABEL[r.status]}`);
    r.evidence.forEach((e) => lines.push(`    ${e.detail}`));
    if (r.guidance) lines.push(`    Fix: ${mine(r.guidance)}`);
    lines.push(`    Spec: ${r.spec}`);
  }
  const versions = Object.entries(report.spec_versions).map(([k, v]) => `${k} ${v}`).join(", ");
  lines.push("", `Checked against ${versions}.`);
  return lines.join("\n");
}

function renderReport(report) {
  const out = $("result");
  out.replaceChildren();
  origin = report.target;

  // 1. Verdict + where you stand
  const verdict = el("div", { class: `card verdict ${report.verdict.level}` });
  verdict.append(el("p", { class: "target" }, new URL(report.target).host));
  verdict.append(el("h2", {}, report.verdict.title), el("p", {}, report.verdict.summary));
  const done = report.steps.filter((s) => s.state === "done").length;
  verdict.append(el("p", { class: "steps-title" }, `${done} of ${report.steps.length} steps done`));
  verdict.append(renderSteps(report.steps));
  out.append(verdict);

  // 2. The one thing to do next
  const next = el("div", { class: "card next" });
  next.append(el("h2", {}, "Your next step"), el("p", {}, mine(report.next_step)));
  const actions = el("div", { class: "actions" });
  const current = report.steps.find((s) => s.current);
  if (current && current.checks.includes("M1.merchant_signature")) {
    const verify = el("button", { type: "button" }, "Paste a checkout response");
    verify.addEventListener("click", () => {
      $("sample-box").open = true;
      $("sample").focus();
      $("check-form").scrollIntoView({ behavior: "smooth", block: "start" });
    });
    actions.append(verify);
  }
  const copy = el("button", { type: "button", class: "secondary" }, "Copy summary for your developer");
  copy.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(summaryText(report));
      copy.textContent = "Copied";
    } catch {
      copy.textContent = "Copy failed — use Download";
    }
    setTimeout(() => { copy.textContent = "Copy summary for your developer"; }, 2000);
  });
  const dl = el("button", { type: "button", class: "secondary" }, "Download full report (JSON)");
  dl.addEventListener("click", () => {
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const a = el("a", { href: URL.createObjectURL(blob),
      download: `ap2-check-${new URL(report.target).host}.json` });
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  });
  actions.append(copy, dl);
  next.append(actions);
  out.append(next);

  // 3. Details per check: problems open, everything else folded
  const counts = {};
  report.results.forEach((r) => { counts[r.status] = (counts[r.status] || 0) + 1; });
  const tally = ["fail", "warn", "error", "pass", "not_applicable"]
    .filter((s) => counts[s])
    .map((s) => `${counts[s]} ${STATUS_LABEL[s].toLowerCase()}`)
    .join(" · ");
  const detailsHead = el("div", { class: "details-head" });
  detailsHead.append(el("h2", {}, "All checks"), el("p", { class: "tally" }, tally));
  out.append(detailsHead);
  for (const [stage, title] of STAGES) {
    const items = report.results.filter((r) => r.stage === stage);
    if (!items.length) continue;
    const section = el("section", { class: "stage" });
    section.append(el("h3", {}, title));
    items.forEach((r) => section.append(renderCheck(r)));
    out.append(section);
  }

  // 4. Caveats and transparency, folded
  const notes = el("details", { class: "card notes-box" });
  notes.append(el("summary", {}, "What this check does and does not tell you"));
  const ul = el("ul", { class: "notes" });
  report.notes.forEach((n) => ul.append(el("li", {}, n)));
  const reqs = report.requests.map((q) => `${q.url} → ${q.status ?? q.error}`).join("; ");
  ul.append(el("li", {}, `Requests we sent: ${reqs || "none"}.`));
  const versions = Object.entries(report.spec_versions).map(([k, v]) => `${k} ${v}`).join(" · ");
  ul.append(el("li", {}, `Checked ${report.checked_at} against ${versions}.`));
  notes.append(ul);
  out.append(notes);

  out.hidden = false;
  out.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function onSubmit(ev) {
  ev.preventDefault();
  const err = $("form-error");
  const progress = $("progress");
  const button = $("submit");
  err.hidden = true;
  const url = $("url").value.trim();
  if (!url) {
    err.textContent = "Enter your shop's domain, for example shop.example.com.";
    err.hidden = false;
    $("url").focus();
    return;
  }
  const sample = $("sample").value.trim() || null;
  button.disabled = true;
  button.textContent = "Checking…";
  progress.textContent = "Reading your shop's public files. This takes about 3 seconds…";
  progress.hidden = false;
  $("result").hidden = true;
  try {
    const resp = await fetch("/api/check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, sample }),
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      const detail = Array.isArray(data.detail) ? "Input too long or invalid." : data.detail;
      throw new Error(detail || `The check failed (HTTP ${resp.status}).`);
    }
    renderReport(data);
    // Shareable link to this shop's check (the sample is never put in the URL).
    history.replaceState(null, "", `?url=${encodeURIComponent(new URL(data.target).host)}`);
  } catch (e) {
    err.textContent = e.message || "The check failed.";
    err.hidden = false;
  } finally {
    progress.hidden = true;
    button.disabled = false;
    button.textContent = "Check my shop";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  $("check-form").addEventListener("submit", onSubmit);
  const q = new URLSearchParams(location.search).get("url");
  if (q) $("url").value = q;
});
