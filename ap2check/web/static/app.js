// AP2 Readiness Check front-end. All report text is inserted with textContent (never
// innerHTML): profiles and agent cards come from third-party servers.
"use strict";

const STAGES = [
  ["discovery", "1 · Discovery — UCP profile"],
  ["checkout", "2 · Checkout and payment handlers"],
  ["ap2", "3 · AP2 mandates and signing keys"],
  ["a2a", "4 · A2A merchant agent (optional)"],
  ["signature", "5 · Merchant signature"],
];
const STATUS_LABEL = {
  pass: "Pass", warn: "Warning", fail: "Fail", not_applicable: "n/a", error: "Not tested",
};

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

function renderCheck(r) {
  const node = $("tpl-check").content.firstElementChild.cloneNode(true);
  const chip = node.querySelector(".chip");
  chip.textContent = STATUS_LABEL[r.status] || r.status;
  chip.classList.add(r.status);
  node.querySelector(".check-label").textContent = r.label;
  node.querySelector(".check-id").textContent = r.id;
  const list = node.querySelector(".evidence");
  for (const e of r.evidence) {
    const li = el("li");
    li.append(document.createTextNode(e.detail));
    if (e.url) li.append(document.createTextNode(` — ${e.url}`));
    if (e.snippet) li.append(el("pre", {}, e.snippet));
    list.append(li);
  }
  if (r.guidance) {
    node.querySelector(".guidance").hidden = false;
    node.querySelector(".guidance-text").textContent = r.guidance;
  }
  const spec = node.querySelector(".spec");
  const href = safeHref(r.spec);
  if (href) {
    spec.href = href;
    spec.textContent = "Spec: " + new URL(href).host + new URL(href).pathname;
  } else {
    spec.remove();
  }
  return node;
}

function renderReport(report) {
  const out = $("result");
  out.replaceChildren();

  const verdict = el("div", { class: `card verdict ${report.verdict.level}` });
  verdict.append(el("h2", {}, report.verdict.title), el("p", {}, report.verdict.summary));
  const versions = Object.entries(report.spec_versions).map(([k, v]) => `${k} ${v}`).join(" · ");
  verdict.append(el("p", { class: "meta" },
    `${report.target} · checked ${report.checked_at} · ${versions}`));
  out.append(verdict);

  for (const [stage, title] of STAGES) {
    const items = report.results.filter((r) => r.stage === stage);
    if (!items.length) continue;
    const section = el("section", { class: "stage" });
    section.append(el("h2", {}, title));
    items.forEach((r) => section.append(renderCheck(r)));
    out.append(section);
  }

  const notes = el("section", { class: "stage" });
  notes.append(el("h2", {}, "Good to know"));
  const ul = el("ul", { class: "notes" });
  report.notes.forEach((n) => ul.append(el("li", {}, n)));
  const reqs = report.requests.map((q) => `${q.url} → ${q.status ?? q.error}`).join("; ");
  ul.append(el("li", {}, `Requests we sent: ${reqs || "none"}.`));
  notes.append(ul);

  const actions = el("div", { class: "actions" });
  const dl = el("button", { type: "button", class: "secondary" }, "Download JSON report");
  dl.addEventListener("click", () => {
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const a = el("a", { href: URL.createObjectURL(blob),
      download: `ap2-check-${new URL(report.target).host}.json` });
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  });
  actions.append(dl);
  notes.append(actions);
  out.append(notes);
  out.hidden = false;
  out.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function onSubmit(ev) {
  ev.preventDefault();
  const err = $("form-error");
  const button = $("submit");
  err.hidden = true;
  const url = $("url").value.trim();
  if (!url) {
    err.textContent = "Enter your shop's domain.";
    err.hidden = false;
    return;
  }
  const sample = $("sample").value.trim() || null;
  button.disabled = true;
  button.textContent = "Checking…";
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
  } catch (e) {
    err.textContent = e.message || "The check failed.";
    err.hidden = false;
  } finally {
    button.disabled = false;
    button.textContent = "Check";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  $("check-form").addEventListener("submit", onSubmit);
  const q = new URLSearchParams(location.search).get("url");
  if (q) $("url").value = q;
});
