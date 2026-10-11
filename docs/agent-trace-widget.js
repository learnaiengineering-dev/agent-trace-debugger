/*
 * <agent-trace>: embeddable agent trace debugger.
 * Copyright (c) 2026 Learn AI Engineering. MIT License.
 * Span format and timing rules follow the Agent Trace Debugger project in
 * https://github.com/rohitg00/ai-engineering-from-scratch (MIT). See NOTICE.
 *
 * One file, no dependencies, no network access, no inline scripts or style attributes.
 * Usage:
 *   <script type="module" src="agent-trace-widget.js"></script>
 *   <agent-trace heading="Last agent run">
 *     <script type="application/x-ndjson" data-role="current">
 *       {"id":"run","name":"Agent run","start":0,"end":100,"status":"ok","tokens":0}
 *     </script>
 *   </agent-trace>
 * Add a second script with data-role="baseline" to compare with a previous run.
 */

export const SCHEMA_VERSION = 1;

export class TraceError extends Error {
  constructor(kind, message, line = null) {
    super(message);
    this.kind = kind;
    this.line = line;
  }
}

const isObject = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
const isNum = (v) => typeof v === "number" && Number.isFinite(v);
const cmp = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
// Shortest readable number, like Python's {:g}.
const g = (v) => String(Number(v.toPrecision(6)));

/** Parse JSONL into spans. Blank lines are skipped. Throws TraceError with the line number. */
export function parseTrace(text) {
  const spans = [];
  String(text).split(/\r?\n/).forEach((line, i) => {
    const number = i + 1;
    if (!line.trim()) return;
    let s;
    try { s = JSON.parse(line); } catch { throw new TraceError("invalid_json", `line ${number}: not valid JSON`, number); }
    const ok = isObject(s) && typeof s.id === "string" && s.id !== "" && typeof s.name === "string" &&
      (s.parent == null || typeof s.parent === "string") &&
      isNum(s.start) && isNum(s.end) && isNum(s.tokens) && s.end >= s.start && s.tokens >= 0 &&
      (s.status === "ok" || s.status === "error");
    if (!ok) throw new TraceError("invalid_span", `line ${number}: not a valid span (check id, name, start <= end, tokens >= 0, status ok or error)`, number);
    spans.push({ id: s.id, name: s.name, start: s.start, end: s.end, status: s.status, tokens: s.tokens, parent: s.parent ?? null });
  });
  if (!spans.length) throw new TraceError("empty", "no spans found");
  return spans;
}

/** Check ids, parent links and nesting. Returns spans by id. */
export function validateTree(spans) {
  const byId = new Map(spans.map((s) => [s.id, s]));
  if (byId.size !== spans.length) throw new TraceError("duplicate_id", "duplicate span id");
  for (const s of spans) {
    const seen = new Set([s.id]);
    let p = s.parent;
    while (p !== null) {
      if (seen.has(p)) throw new TraceError("cycle", `span "${s.id}" is part of a parent cycle`);
      seen.add(p);
      const parent = byId.get(p);
      if (!parent) throw new TraceError("missing_parent", `span "${s.id}" names a missing parent "${p}"`);
      p = parent.parent;
    }
    if (s.parent !== null) {
      const parent = byId.get(s.parent);
      if (s.start < parent.start || s.end > parent.end) throw new TraceError("outside_parent", `span "${s.id}" runs outside its parent "${s.parent}"`);
    }
  }
  return byId;
}

function merge(intervals) {
  const out = [];
  for (const [s, e] of intervals.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1])) {
    const last = out[out.length - 1];
    if (last && s <= last[1]) last[1] = Math.max(last[1], e);
    else out.push([s, e]);
  }
  return out;
}
const union = (intervals) => merge(intervals).reduce((n, [a, b]) => n + (b - a), 0);
const order = (a, b) => a.start - b.start || cmp(a.id, b.id);

/** Validate the trace and compute total time, own time, wall time and token totals. */
export function analyze(spans) {
  validateTree(spans);
  const kids = new Map(spans.map((s) => [s.id, []]));
  for (const s of spans) if (s.parent !== null) kids.get(s.parent).push(s);
  const rows = [];
  const stack = spans.filter((s) => s.parent === null).sort(order).reverse().map((s) => [s, 0]);
  while (stack.length) {
    const [s, depth] = stack.pop();
    const own = [];
    let cursor = s.start;
    for (const [a, b] of merge(kids.get(s.id).map((c) => [c.start, c.end]))) {
      if (a > cursor) own.push([cursor, a]);
      cursor = Math.max(cursor, b);
    }
    if (cursor < s.end) own.push([cursor, s.end]);
    rows.push({ span: s, id: s.id, depth, inclusive: s.end - s.start, exclusive: own.reduce((n, [a, b]) => n + (b - a), 0), own_segments: own, children: kids.get(s.id).map((c) => c.id) });
    for (const c of kids.get(s.id).slice().sort(order).reverse()) stack.push([c, depth + 1]);
  }
  const slowest = rows.slice().sort((a, b) => b.exclusive - a.exclusive || cmp(a.id, b.id))[0];
  return {
    rows,
    wall_time: union(spans.filter((s) => s.parent === null).map((s) => [s.start, s.end])),
    total_tokens: spans.reduce((n, s) => n + s.tokens, 0),
    errors: spans.filter((s) => s.status === "error").length,
    failed_span_tokens: spans.filter((s) => s.status === "error").reduce((n, s) => n + s.tokens, 0),
    slowest,
  };
}

const summary = (a) => ({ wall_time: a.wall_time, total_tokens: a.total_tokens, errors: a.errors, failed_span_tokens: a.failed_span_tokens, slowest_own_time: a.slowest.id });

/** Current minus baseline. Spans are matched by id. */
export function diff(current, baseline) {
  const cur = new Map(current.rows.map((r) => [r.id, r]));
  const base = new Map(baseline.rows.map((r) => [r.id, r]));
  const spans = {};
  for (const id of [...cur.keys()].filter((i) => base.has(i)).sort(cmp)) {
    spans[id] = {
      inclusive: cur.get(id).inclusive - base.get(id).inclusive,
      exclusive: cur.get(id).exclusive - base.get(id).exclusive,
      tokens: cur.get(id).span.tokens - base.get(id).span.tokens,
      status_before: base.get(id).span.status,
      status_after: cur.get(id).span.status,
    };
  }
  return {
    wall_time: current.wall_time - baseline.wall_time,
    total_tokens: current.total_tokens - baseline.total_tokens,
    errors: current.errors - baseline.errors,
    failed_span_tokens: current.failed_span_tokens - baseline.failed_span_tokens,
    spans,
    added: [...cur.keys()].filter((i) => !base.has(i)).sort(cmp),
    removed: [...base.keys()].filter((i) => !cur.has(i)).sort(cmp),
  };
}

const LIMIT_KEYS = ["maxNewErrors", "maxWallIncrease", "maxTokenIncrease", "maxFailedTokenIncrease", "maxErrors"];

/** Compare a run with an optional baseline and apply the gate limits. Returns the report. */
export function compare(current, baseline = null, limits = {}) {
  const L = { maxNewErrors: 0, maxWallIncrease: null, maxTokenIncrease: null, maxFailedTokenIncrease: null, maxErrors: null, ...limits };
  for (const k of LIMIT_KEYS) {
    const v = L[k];
    if (v !== null && (typeof v !== "number" || Number.isNaN(v) || v < 0)) throw new TraceError("bad_limit", `${k} must be a number >= 0`);
  }
  if (!baseline && (L.maxWallIncrease !== null || L.maxTokenIncrease !== null || L.maxFailedTokenIncrease !== null)) {
    throw new TraceError("needs_baseline", "the increase limits need a baseline trace");
  }
  const d = baseline ? diff(current, baseline) : null;
  const failures = [];
  const over = (delta, limit, label, now, before, unit = "") => {
    if (limit !== null && delta > limit) failures.push(`${label} rose by ${g(delta)}${unit} (${g(before)} -> ${g(now)}), limit ${g(limit)}${unit}`);
  };
  if (d) {
    over(d.errors, L.maxNewErrors, "errors", current.errors, baseline.errors);
    over(d.wall_time, L.maxWallIncrease, "wall time", current.wall_time, baseline.wall_time, " ms");
    over(d.total_tokens, L.maxTokenIncrease, "total tokens", current.total_tokens, baseline.total_tokens);
    over(d.failed_span_tokens, L.maxFailedTokenIncrease, "tokens in failed spans", current.failed_span_tokens, baseline.failed_span_tokens);
  }
  if (L.maxErrors !== null && current.errors > L.maxErrors) failures.push(`${current.errors} errors, limit ${g(L.maxErrors)}`);
  return {
    schema_version: SCHEMA_VERSION,
    summary: summary(current),
    spans: current.rows.map((r) => ({ id: r.id, parent: r.span.parent, name: r.span.name, start: r.span.start, end: r.span.end, status: r.span.status, tokens: r.span.tokens, depth: r.depth, inclusive: r.inclusive, exclusive: r.exclusive })),
    baseline: baseline ? { summary: summary(baseline) } : null,
    diff: d,
    gate: {
      passed: failures.length === 0,
      failures,
      limits: { max_new_errors: L.maxNewErrors, max_wall_increase: L.maxWallIncrease, max_token_increase: L.maxTokenIncrease, max_failed_token_increase: L.maxFailedTokenIncrease, max_errors: L.maxErrors },
    },
  };
}

/** One sentence describing what changed underneath, or null without a baseline. */
export function headline(report) {
  const d = report.diff;
  if (!d) return null;
  const parts = [];
  if (d.errors) parts.push(`${d.errors > 0 ? "+" : ""}${g(d.errors)} ${Math.abs(d.errors) === 1 ? "error" : "errors"}`);
  if (d.failed_span_tokens) parts.push(`${d.failed_span_tokens > 0 ? "+" : ""}${g(d.failed_span_tokens)} tokens spent in failed spans`);
  if (d.total_tokens && d.total_tokens !== d.failed_span_tokens) parts.push(`${d.total_tokens > 0 ? "+" : ""}${g(d.total_tokens)} total tokens`);
  if (d.wall_time === 0 && !parts.length) return "No visible change: wall time, tokens and errors match the baseline.";
  const lead = d.wall_time === 0 ? `Wall time is unchanged at ${g(report.summary.wall_time)} ms, but the run changed underneath` : `Wall time moved ${d.wall_time > 0 ? "+" : ""}${g(d.wall_time)} ms`;
  return parts.length ? `${lead}: ${parts.join(" · ")}.` : `${lead}.`;
}

/* ------------------------------------------------------------------ widget */

const CSS = `
:host{
  --_bg:var(--at-bg,#ffffff); --_ink:var(--at-ink,#1a1a1a); --_muted:var(--at-muted,#6b6b66);
  --_line:var(--at-line,#e4e4dc); --_accent:var(--at-accent,#3553ff); --_tint:var(--at-tint,#eef0ff);
  --_good:var(--at-good,#2f9e44); --_bad:var(--at-bad,#d9480f);
  --_ok:var(--at-ok,#2b8a8a); --_okwait:var(--at-ok-wait,#cfe8e8); --_err:var(--at-error,#d9480f); --_errwait:var(--at-error-wait,#f8d5c8);
  display:block; color:var(--_ink); background:var(--_bg); border:1px solid var(--_line);
  border-radius:var(--at-radius,12px); padding:14px; font:15px/1.5 var(--at-font,system-ui,-apple-system,"Segoe UI",sans-serif);
  box-sizing:border-box;
}
@media (prefers-color-scheme:dark){
  :host(:not([theme="light"])){
    --_bg:var(--at-bg,#1a1a1f); --_ink:var(--at-ink,#ececf0); --_muted:var(--at-muted,#9a9aa5);
    --_line:var(--at-line,#2c2c34); --_accent:var(--at-accent,#8097ff); --_tint:var(--at-tint,#22243a);
    --_good:var(--at-good,#5fd47a); --_bad:var(--at-bad,#ff8a5c);
    --_ok:var(--at-ok,#59b7b2); --_okwait:var(--at-ok-wait,#27403f); --_err:var(--at-error,#ff8a5c); --_errwait:var(--at-error-wait,#4a2a20);
  }
}
:host([theme="dark"]){
  --_bg:var(--at-bg,#1a1a1f); --_ink:var(--at-ink,#ececf0); --_muted:var(--at-muted,#9a9aa5);
  --_line:var(--at-line,#2c2c34); --_accent:var(--at-accent,#8097ff); --_tint:var(--at-tint,#22243a);
  --_good:var(--at-good,#5fd47a); --_bad:var(--at-bad,#ff8a5c);
  --_ok:var(--at-ok,#59b7b2); --_okwait:var(--at-ok-wait,#27403f); --_err:var(--at-error,#ff8a5c); --_errwait:var(--at-error-wait,#4a2a20);
}
*{box-sizing:border-box}
h2{margin:0 0 8px;font-size:1rem}
.banner{border:1px solid var(--_line);border-radius:10px;padding:10px 12px;margin-bottom:10px}
.banner.fail{border-color:var(--_bad)} .banner.pass{border-color:var(--_good)}
.banner b{display:block} .banner small{display:block;color:var(--_muted)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;margin-bottom:10px}
.card{border:1px solid var(--_line);border-radius:10px;padding:6px 10px}
.card small{display:block;color:var(--_muted);font-size:.7em;text-transform:uppercase;letter-spacing:.05em}
.card b{font-size:1.15em;display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.card span{display:block;font-size:.8em}
.up{color:var(--_bad)} .down{color:var(--_good)} .flat{color:var(--_muted)}
.axis,.row{display:grid;grid-template-columns:minmax(100px,190px) 1fr;gap:0 10px;align-items:center}
.axis{font-size:.72em;color:var(--_muted);margin-bottom:4px}
.ticks{display:flex;justify-content:space-between;font-variant-numeric:tabular-nums}
.row{cursor:pointer;border-top:1px solid var(--_line)}
.lbl{padding:6px 4px;font-size:.88em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-height:34px;display:flex;align-items:center;gap:6px}
.lbl small{color:var(--_muted);font-size:.78em}
.track{position:relative;height:34px}
.span{position:absolute;top:7px;height:16px;border-radius:3px;background:var(--_okwait);outline:1px solid var(--_ok)}
.span.error{background:var(--_errwait);outline-color:var(--_err)}
.own{position:absolute;top:0;bottom:0;background:var(--_ok);border-radius:2px}
.span.error .own{background:var(--_err)}
.ghost{position:absolute;top:27px;height:3px;background:var(--_muted);opacity:.7;border-radius:2px}
.row:hover,.row.sel{background:var(--_tint)}
.row:focus-visible{outline:2px solid var(--_accent);outline-offset:-2px}
.legend{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:.78em;color:var(--_muted);margin-top:8px}
.legend i{display:inline-block;width:12px;height:9px;border-radius:2px;margin-right:5px}
.detail{margin-top:10px;border-top:1px solid var(--_line);padding-top:8px;font-size:.88em}
.detail dl{display:grid;grid-template-columns:auto 1fr;gap:2px 12px;margin:0}
.detail dt{color:var(--_muted)} .detail dd{margin:0;font-variant-numeric:tabular-nums}
.scroll{overflow-x:auto;margin-top:10px}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums;font-size:.88em}
th,td{padding:5px 8px;text-align:right;border-bottom:1px solid var(--_line);white-space:nowrap}
th:first-child,td:first-child{text-align:left;white-space:normal}
th{font-size:.72em;text-transform:uppercase;letter-spacing:.05em;color:var(--_muted);font-weight:600}
.note{color:var(--_muted);font-size:.85em;margin:8px 0 0}
details{margin-top:10px} summary{cursor:pointer;color:var(--_muted);font-size:.85em}
label{display:block;font-size:.8em;font-weight:600;margin:8px 0 2px}
textarea{width:100%;height:120px;font:12px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--_ink);background:var(--_bg);border:1px solid var(--_line);border-radius:8px;padding:6px;resize:vertical;white-space:pre;overflow:auto}
textarea:focus-visible{outline:2px solid var(--_accent);outline-offset:1px}
.error-text{color:var(--_bad);font-size:.85em;margin:6px 0 0}
`;

let sheet = null;
function applyStyles(root) {
  // Constructed stylesheets are not blocked by a strict style-src Content-Security-Policy.
  if (typeof CSSStyleSheet !== "undefined" && "adoptedStyleSheets" in root) {
    if (!sheet) { sheet = new CSSStyleSheet(); sheet.replaceSync(CSS); }
    root.adoptedStyleSheets = [sheet];
  } else {
    const style = document.createElement("style");
    style.textContent = CSS;
    root.appendChild(style);
  }
}

const el = (tag, cls, text) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
};
const toText = (v) => (Array.isArray(v) ? v.map((x) => JSON.stringify(x)).join("\n") : String(v ?? ""));
const signed = (v, unit = "") => (v === 0 ? "no change" : `${v > 0 ? "+" : ""}${g(v)}${unit}`);
const deltaSpan = (v, unit = "", suffix = "") => el("span", v === 0 ? "flat" : v > 0 ? "up" : "down", signed(v, unit) + (v === 0 ? "" : suffix));

if (typeof HTMLElement !== "undefined" && typeof customElements !== "undefined") {
  class AgentTrace extends HTMLElement {
    static observedAttributes = ["heading", "theme", "editable", "max-new-errors", "max-wall-increase", "max-token-increase", "max-failed-token-increase", "max-errors"];

    #data = null;
    #report = null;
    #selected = null;
    #root;
    #host = null;

    constructor() {
      super();
      this.#root = this.attachShadow({ mode: "open" });
      applyStyles(this.#root);
    }

    connectedCallback() {
      if (!this.#data) {
        const scripts = [...this.querySelectorAll('script[type="application/x-ndjson"]')];
        if (scripts.length) {
          const pick = (role) => scripts.find((s) => (s.dataset.role || "current") === role);
          this.#data = { current: pick("current")?.textContent ?? "", baseline: pick("baseline")?.textContent ?? "" };
        }
      }
      this.#build();
    }

    attributeChangedCallback() { if (this.isConnected) this.#build(); }

    /** Set {current, baseline}. Each is JSONL text or an array of span objects. */
    set data(value) { this.#data = value; this.#selected = null; if (this.isConnected) this.#build(); }
    get data() { return this.#data; }
    /** The last report, in the same shape as the Python JSON report. */
    get result() { return this.#report; }

    #limits() {
      const num = (name) => (this.hasAttribute(name) ? Number(this.getAttribute(name)) : null);
      return {
        maxNewErrors: this.hasAttribute("max-new-errors") ? Number(this.getAttribute("max-new-errors")) : 0,
        maxWallIncrease: num("max-wall-increase"),
        maxTokenIncrease: num("max-token-increase"),
        maxFailedTokenIncrease: num("max-failed-token-increase"),
        maxErrors: num("max-errors"),
      };
    }

    #build() {
      for (const n of [...this.#root.childNodes]) if (n.nodeType === 1 && n.tagName !== "STYLE") n.remove();
      const wrap = el("div");
      const heading = this.getAttribute("heading");
      if (heading) wrap.appendChild(el("h2", "", heading));
      this.#host = el("div");
      wrap.appendChild(this.#host);
      if (this.hasAttribute("editable")) wrap.appendChild(this.#buildEditor());
      this.#root.appendChild(wrap);
      this.#update();
    }

    // Re-renders only the result area, so editor textareas keep focus while typing.
    #update() {
      this.#host.replaceChildren();
      this.#report = null;
      let error = null, cur = null, base = null, baseNote = null;
      const text = this.#data ? toText(this.#data.current) : "";
      if (!text.trim()) error = 'No trace. Add a <script type="application/x-ndjson"> child or set the .data property.';
      else {
        try {
          cur = analyze(parseTrace(text));
          const bt = this.#data.baseline == null ? "" : toText(this.#data.baseline);
          if (bt.trim()) {
            try { base = analyze(parseTrace(bt)); } catch (e) { if (e instanceof TraceError) baseNote = `Baseline ignored: ${e.message}`; else throw e; }
          }
          this.#report = compare(cur, base, this.#limits());
        } catch (e) {
          if (e instanceof TraceError) error = e.message; else throw e;
        }
      }
      if (error) {
        const p = el("p", "error-text", error);
        p.setAttribute("role", "alert");
        this.#host.appendChild(p);
      } else {
        this.#renderResult(this.#host, cur, base, this.#report, baseNote);
      }
      this.dispatchEvent(new CustomEvent("trace-result", { detail: this.#report, bubbles: true, composed: true }));
    }

    #renderResult(wrap, cur, base, report, baseNote) {
      const d = report.diff;
      const banner = el("div", `banner ${report.gate.passed ? "pass" : "fail"}`);
      banner.setAttribute("role", "status");
      banner.appendChild(el("b", "", report.gate.passed ? "Gate: PASS" : "Gate: FAIL"));
      banner.appendChild(el("small", "", headline(report) || "No baseline supplied, so nothing to compare."));
      for (const f of report.gate.failures) banner.appendChild(el("small", "", f));
      wrap.appendChild(banner);

      const cards = el("div", "cards");
      const card = (label, value, delta, unit) => {
        const c = el("div", "card");
        c.append(el("small", "", label), el("b", "", value));
        if (delta !== null && delta !== undefined) c.appendChild(deltaSpan(delta, unit, " vs baseline"));
        cards.appendChild(c);
      };
      card("Wall time", `${g(cur.wall_time)} ms`, d && d.wall_time, " ms");
      card("Total tokens", g(cur.total_tokens), d && d.total_tokens, "");
      card("Errors", String(cur.errors), d && d.errors, "");
      card("Tokens in failed spans", g(cur.failed_span_tokens), d && d.failed_span_tokens, "");
      card("Most own time", cur.slowest.span.name, null);
      wrap.appendChild(cards);

      const all = cur.rows.concat(base ? base.rows : []);
      const lo = Math.min(0, ...all.map((r) => r.span.start)), hi = Math.max(1, ...all.map((r) => r.span.end)), span = hi - lo;
      const pct = (v) => `${(((v - lo) / span) * 100).toFixed(4)}%`;
      const baseRows = base ? new Map(base.rows.map((r) => [r.id, r])) : null;

      const axis = el("div", "axis");
      const ticks = el("div", "ticks");
      for (let i = 0; i <= 5; i++) ticks.appendChild(el("span", "", g(Math.round((lo + (span * i) / 5) * 10) / 10)));
      axis.append(el("div"), ticks);
      wrap.appendChild(axis);

      const tl = el("div", "tl");
      for (const r of cur.rows) {
        const row = el("div", `row${r.id === this.#selected ? " sel" : ""}`);
        row.tabIndex = 0;
        row.setAttribute("role", "button");
        row.setAttribute("aria-label", `${r.span.name}, ${g(r.inclusive)} ms total, ${g(r.exclusive)} ms own, ${g(r.span.tokens)} tokens, ${r.span.status}`);
        row.dataset.id = r.id;
        const lbl = el("div", "lbl", r.span.name);
        lbl.style.paddingLeft = `${4 + r.depth * 16}px`;
        lbl.appendChild(el("small", "", `${g(r.span.tokens)} tok${r.span.status === "error" ? " · error" : ""}`));
        const track = el("div", "track");
        const bar = el("div", r.span.status === "error" ? "span error" : "span");
        bar.style.left = pct(r.span.start);
        bar.style.width = `${Math.max((r.inclusive / span) * 100, 0.4).toFixed(4)}%`;
        const w = r.span.end - r.span.start || 1;
        for (const [a, b] of r.own_segments) {
          const o = el("div", "own");
          o.style.left = `${(((a - r.span.start) / w) * 100).toFixed(4)}%`;
          o.style.width = `${(((b - a) / w) * 100).toFixed(4)}%`;
          bar.appendChild(o);
        }
        track.appendChild(bar);
        const b = baseRows && baseRows.get(r.id);
        if (b) {
          const ghost = el("div", "ghost");
          ghost.title = `Baseline ${g(b.span.start)} to ${g(b.span.end)}`;
          ghost.style.left = pct(b.span.start);
          ghost.style.width = `${Math.max(((b.span.end - b.span.start) / span) * 100, 0.4).toFixed(4)}%`;
          track.appendChild(ghost);
        }
        row.append(lbl, track);
        const select = () => { this.#selected = r.id; this.#update(); this.#focusRow(r.id); };
        row.addEventListener("click", select);
        row.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); select(); } });
        tl.appendChild(row);
      }
      wrap.appendChild(tl);

      const legend = el("div", "legend");
      const key = (color, text) => { const s = el("span"); const i = el("i"); i.style.background = color; s.append(i, text); legend.appendChild(s); };
      key("var(--_ok)", "own time");
      key("var(--_okwait)", "waiting on child spans");
      key("var(--_err)", "error");
      if (base) key("var(--_muted)", "baseline position");
      wrap.appendChild(legend);

      wrap.appendChild(this.#detail(cur, base));
      if (d) wrap.appendChild(this.#diffTable(cur, d));
      if (baseNote) wrap.appendChild(el("p", "note", baseNote));
    }

    #focusRow(id) {
      for (const n of this.#root.querySelectorAll(".row")) if (n.dataset.id === id) { n.focus(); return; }
    }

    #detail(cur, base) {
      const box = el("div", "detail");
      const r = cur.rows.find((x) => x.id === (this.#selected ?? cur.slowest.id));
      if (!r) return box;
      const b = base && base.rows.find((x) => x.id === r.id);
      const dl = el("dl");
      const add = (k, v, was) => {
        const dd = el("dd", "", v);
        if (was) dd.appendChild(el("span", "flat", ` (baseline ${was})`));
        dl.append(el("dt", "", k), dd);
      };
      add("Span", `${r.span.name} (${r.id})`);
      add("Parent", r.span.parent ?? "none (root)");
      add("Interval", `${g(r.span.start)} to ${g(r.span.end)} ms`, b && `${g(b.span.start)} to ${g(b.span.end)}`);
      add("Total time", `${g(r.inclusive)} ms`, b && `${g(b.inclusive)} ms`);
      add("Own time", `${g(r.exclusive)} ms`, b && `${g(b.exclusive)} ms`);
      add("Tokens", g(r.span.tokens), b && g(b.span.tokens));
      add("Status", r.span.status, b && b.span.status !== r.span.status ? `was ${b.span.status}` : null);
      box.appendChild(dl);
      return box;
    }

    #diffTable(cur, d) {
      const scroll = el("div", "scroll");
      const table = el("table");
      const head = el("tr");
      for (const h of ["Span", "Total ms", "Own ms", "Tokens", "Status"]) head.appendChild(el("th", "", h));
      table.appendChild(head);
      const names = new Map(cur.rows.map((r) => [r.id, r.span.name]));
      const cell = (v) => { const td = el("td"); td.appendChild(deltaSpan(v)); return td; };
      for (const [id, c] of Object.entries(d.spans)) {
        const same = c.status_before === c.status_after;
        const status = el("td", same ? "" : c.status_after === "error" ? "up" : "down", same ? c.status_after : `${c.status_before} → ${c.status_after}`);
        const tr = el("tr");
        tr.append(el("td", "", names.get(id) ?? id), cell(c.inclusive), cell(c.exclusive), cell(c.tokens), status);
        table.appendChild(tr);
      }
      for (const [ids, cls, text] of [[d.added, "up", "new span"], [d.removed, "down", "removed span"]]) {
        for (const id of ids) {
          const tr = el("tr");
          const td = el("td", cls, text);
          td.colSpan = 4;
          tr.append(el("td", "", names.get(id) ?? id), td);
          table.appendChild(tr);
        }
      }
      scroll.appendChild(table);
      return scroll;
    }

    #buildEditor() {
      const details = el("details");
      details.appendChild(el("summary", "", "Edit the trace"));
      const areas = {};
      for (const key of ["current", "baseline"]) {
        const id = `at-${key}`;
        const label = el("label", "", key === "current" ? "Current trace (JSONL)" : "Baseline trace (JSONL, optional)");
        label.htmlFor = id;
        const ta = el("textarea");
        ta.id = id;
        ta.spellcheck = false;
        ta.value = this.#data && this.#data[key] != null ? toText(this.#data[key]).trim() : "";
        areas[key] = ta;
        details.append(label, ta);
      }
      const onInput = () => {
        this.#data = { current: areas.current.value, baseline: areas.baseline.value };
        this.#selected = null;
        this.#update();
      };
      for (const ta of Object.values(areas)) ta.addEventListener("input", onInput);
      return details;
    }
  }

  if (!customElements.get("agent-trace")) customElements.define("agent-trace", AgentTrace);
}
