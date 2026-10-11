import json
from pathlib import Path

from agent_trace_debugger import Span, analyze, compare, parse_trace
from agent_trace_debugger.report import to_html, to_json, to_markdown, to_text

EX = Path(__file__).resolve().parent.parent / "examples"


def result(**kw):
    cur = analyze(parse_trace((EX / "trace.jsonl").read_text()))
    base = analyze(parse_trace((EX / "baseline.jsonl").read_text()))
    return compare(cur, base, **kw)


def test_text_report_names_the_hidden_change():
    t = to_text(result())
    assert "Wall time is unchanged at 100 ms" in t and "+500 tokens spent in failed spans" in t
    assert "Result: FAIL (1 limit exceeded)" in t


def test_json_report_is_versioned():
    d = json.loads(to_json(result()))
    assert d["schema_version"] == 1 and d["gate"]["passed"] is False
    assert d["diff"]["spans"]["draft"]["status_after"] == "error"


def test_markdown_has_table_and_failures():
    m = to_markdown(result())
    assert "| Wall time | 100 ms (no change) |" in m and "**Failures**" in m


def test_html_is_self_contained_and_escapes_trace_text():
    evil = '<script>alert("x")</script><img src=x onerror=alert(1)>'
    spans = [Span("a", evil, 0, 10, "ok", 1), Span("b", "child", 2, 4, "error", 3, "a")]
    html = to_html(compare(analyze(spans)))
    assert "<script>" not in html and "<img" not in html
    assert "&lt;script&gt;" in html
    assert "http://" not in html and "https://" not in html


def test_report_without_baseline():
    t = to_text(compare(analyze(parse_trace((EX / "trace.jsonl").read_text()))))
    assert "Result: PASS" in t and "vs baseline" not in t

