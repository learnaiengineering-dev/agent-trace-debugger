"""Render a Result as text, Markdown, JSON or a self-contained HTML timeline."""
from __future__ import annotations

import html
import json

from .analysis import Result


def _n(v: float) -> str:
    return f"{v:g}"


def _d(v: float, unit: str = "") -> str:
    return "no change" if v == 0 else f"{v:+g}{unit}"


def summary_line(res: Result) -> str:
    if res.passed:
        return "Result: PASS"
    n = len(res.failures)
    return f"Result: FAIL ({n} limit{'s' if n != 1 else ''} exceeded)"


def headline(res: Result) -> str | None:
    d = res.diff
    if d is None:
        return None
    parts = []
    if d.errors:
        parts.append(f"{d.errors:+g} {'error' if abs(d.errors) == 1 else 'errors'}")
    if d.failed_span_tokens:
        parts.append(f"{d.failed_span_tokens:+g} tokens spent in failed spans")
    if d.total_tokens and d.total_tokens != d.failed_span_tokens:
        parts.append(f"{d.total_tokens:+g} total tokens")
    if d.wall_time == 0 and not parts:
        return "No visible change: wall time, tokens and errors match the baseline."
    lead = (
        f"Wall time is unchanged at {_n(res.current.wall_time)} ms, but the run changed underneath"
        if d.wall_time == 0
        else f"Wall time moved {d.wall_time:+g} ms"
    )
    return f"{lead}: {' · '.join(parts)}." if parts else f"{lead}."


def to_text(res: Result) -> str:
    cur, d = res.current, res.diff
    delta = (lambda v, u="": f"  ({_d(v, u)})") if d else (lambda v, u="": "")
    lines = ["Agent Trace Debugger"]
    h = headline(res)
    if h:
        lines.append(h)
    lines += [
        f"wall time            {_n(cur.wall_time)} ms{delta(d.wall_time, ' ms') if d else ''}",
        f"total tokens         {_n(cur.total_tokens)}{delta(d.total_tokens) if d else ''}",
        f"errors               {cur.errors}{delta(d.errors) if d else ''}",
        f"tokens in failed     {_n(cur.failed_span_tokens)}{delta(d.failed_span_tokens) if d else ''}",
        f"most own time        {cur.slowest.span.name} ({_n(cur.slowest.exclusive)} ms)",
        "",
    ]
    names = [("  " * r.depth) + r.span.name for r in cur.rows]
    w = max([len("span")] + [len(n) for n in names])
    lines.append(f"{'span':<{w}}  {'start':>7}  {'end':>7}  {'total':>7}  {'own':>7}  {'tokens':>7}  status")
    for r, n in zip(cur.rows, names):
        lines.append(
            f"{n:<{w}}  {_n(r.span.start):>7}  {_n(r.span.end):>7}  {_n(r.inclusive):>7}  "
            f"{_n(r.exclusive):>7}  {_n(r.span.tokens):>7}  {r.span.status}"
        )
    if d and (d.added or d.removed):
        lines.append("")
        lines += [f"new span: {i}" for i in d.added] + [f"removed span: {i}" for i in d.removed]
    lines.append("")
    lines.append(summary_line(res))
    lines += [f"  - {f}" for f in res.failures]
    return "\n".join(lines)


def to_markdown(res: Result) -> str:
    cur, d = res.current, res.diff

    def cell(v: float, delta: float | None, unit: str = "") -> str:
        return f"{_n(v)}{unit}" + (f" ({_d(delta, unit)})" if delta is not None else "")

    out = [f"### Agent Trace Debugger: {'PASS' if res.passed else 'FAIL'}", ""]
    h = headline(res)
    if h:
        out += [h, ""]
    out += [
        "| Metric | Value |", "|---|---|",
        f"| Wall time | {cell(cur.wall_time, d.wall_time if d else None, ' ms')} |",
        f"| Total tokens | {cell(cur.total_tokens, d.total_tokens if d else None)} |",
        f"| Errors | {cell(cur.errors, d.errors if d else None)} |",
        f"| Tokens in failed spans | {cell(cur.failed_span_tokens, d.failed_span_tokens if d else None)} |",
        f"| Most own time | {cur.slowest.span.name.replace('|', chr(92) + '|')} ({_n(cur.slowest.exclusive)} ms) |",
        "", "| Span | Total ms | Own ms | Tokens | Status |", "|---|---:|---:|---:|---|",
    ]
    for r in cur.rows:
        name = ("&nbsp;&nbsp;" * r.depth) + r.span.name.replace("|", "\\|")
        out.append(f"| {name} | {_n(r.inclusive)} | {_n(r.exclusive)} | {_n(r.span.tokens)} | {r.span.status} |")
    if res.failures:
        out += ["", "**Failures**", ""] + [f"- {f}" for f in res.failures]
    return "\n".join(out) + "\n"


def to_json(res: Result) -> str:
    return json.dumps(res.to_dict(), indent=2, sort_keys=True) + "\n"


_CSS = """
:root{--bg:#fafaf5;--panel:#fff;--ink:#1a1a1a;--muted:#6b6b66;--line:#e4e4dc;--ok:#2b8a8a;--okwait:#cfe8e8;--err:#d9480f;--errwait:#f8d5c8;--tint:#eef0ff;--good:#2f9e44;--bad:#d9480f}
@media (prefers-color-scheme:dark){:root{--bg:#111114;--panel:#1a1a1f;--ink:#ececf0;--muted:#9a9aa5;--line:#2c2c34;--ok:#59b7b2;--okwait:#27403f;--err:#ff8a5c;--errwait:#4a2a20;--tint:#22243a;--good:#5fd47a;--bad:#ff8a5c}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:980px;margin:0 auto;padding:24px 16px 40px}h1{font-size:1.4rem;margin:0 0 12px}
.banner{border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin-bottom:12px;background:var(--panel)}
.banner.fail{border-color:var(--bad)}.banner.pass{border-color:var(--good)}.banner b{display:block}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:14px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:8px 12px}
.card small{display:block;color:var(--muted);font-size:.7rem;text-transform:uppercase;letter-spacing:.05em}.card b{font-size:1.2rem}
.card span{display:block;font-size:.8rem;color:var(--muted)}.up{color:var(--bad)}.down{color:var(--good)}
.tl{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px}
.row{display:grid;grid-template-columns:minmax(120px,220px) 1fr;gap:10px;align-items:center;border-top:1px solid var(--line)}
.row:first-child{border-top:0}.lbl{padding:6px 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.lbl small{color:var(--muted)}
.track{position:relative;height:30px}.span{position:absolute;top:6px;height:16px;border-radius:3px;background:var(--okwait);outline:1px solid var(--ok)}
.span.error{background:var(--errwait);outline-color:var(--err)}.own{position:absolute;top:0;bottom:0;background:var(--ok);border-radius:2px}
.span.error .own{background:var(--err)}.axis{display:grid;grid-template-columns:minmax(120px,220px) 1fr;gap:10px;color:var(--muted);font-size:.75rem}
.ticks{display:flex;justify-content:space-between}.legend{color:var(--muted);font-size:.8rem;margin-top:8px}
footer{color:var(--muted);font-size:.8rem;margin-top:20px}
"""


def to_html(res: Result) -> str:
    """A single file with inline CSS and no scripts. Every value taken from the trace is escaped."""
    e = lambda s: html.escape(str(s), quote=True)  # noqa: E731
    cur, d = res.current, res.diff
    lo = min([0] + [r.span.start for r in cur.rows])
    hi = max([1] + [r.span.end for r in cur.rows])
    span = hi - lo
    cards = []

    def card(label: str, value: str, delta: float | None, unit: str = "") -> None:
        extra = ""
        if delta is not None:
            cls = "" if delta == 0 else ("up" if delta > 0 else "down")
            extra = f'<span class="{cls}">{e(_d(delta, unit))} vs baseline</span>'
        cards.append(f'<div class="card"><small>{e(label)}</small><b>{e(value)}</b>{extra}</div>')

    card("Wall time", f"{_n(cur.wall_time)} ms", d.wall_time if d else None, " ms")
    card("Total tokens", _n(cur.total_tokens), d.total_tokens if d else None)
    card("Errors", str(cur.errors), d.errors if d else None)
    card("Tokens in failed spans", _n(cur.failed_span_tokens), d.failed_span_tokens if d else None)
    card("Most own time", cur.slowest.span.name, None)
    rows = []
    for r in cur.rows:
        w = (r.span.end - r.span.start) or 1
        own = "".join(
            f'<div class="own" style="left:{(a - r.span.start) / w * 100:.4f}%;width:{(b - a) / w * 100:.4f}%"></div>'
            for a, b in r.own_segments
        )
        cls = "span error" if r.span.status == "error" else "span"
        label = f'{e(r.span.name)} <small>{e(_n(r.span.tokens))} tok{" · error" if r.span.status == "error" else ""}</small>'
        rows.append(
            f'<div class="row"><div class="lbl" style="padding-left:{r.depth * 16}px" title="{e(r.id)}: total {e(_n(r.inclusive))} ms, own {e(_n(r.exclusive))} ms">{label}</div>'
            f'<div class="track"><div class="{cls}" style="left:{(r.span.start - lo) / span * 100:.4f}%;width:{max(r.inclusive / span * 100, 0.4):.4f}%">{own}</div></div></div>'
        )
    ticks = "".join(f"<span>{e(_n(round(lo + span * i / 5, 1)))}</span>" for i in range(6))
    h = headline(res)
    status = "pass" if res.passed else "fail"
    failures = "".join(f"<div>{e(f)}</div>" for f in res.failures)
    banner = (
        f'<div class="banner {status}"><b>Gate: {"PASS" if res.passed else "FAIL"}</b>'
        f'{e(h) if h else "No baseline supplied."}{failures}</div>'
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>Agent trace report</title><style>{_CSS}</style></head><body><main>"
        f'<h1>Agent trace report</h1>{banner}<div class="cards">{"".join(cards)}</div>'
        f'<div class="tl"><div class="axis"><div></div><div class="ticks">{ticks}</div></div>{"".join(rows)}'
        '<div class="legend">Solid = own time. Pale = waiting on child spans. Red = error. Times in ms.</div></div>'
        "<footer>Generated by agent-trace-debugger. Span names come from your trace.</footer></main></body></html>\n"
    )

