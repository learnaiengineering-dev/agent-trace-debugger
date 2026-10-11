from pathlib import Path

import pytest

from agent_trace_debugger import Span, TraceError, analyze, compare, parse_trace

EX = Path(__file__).resolve().parent.parent / "examples"


def load(name):
    return analyze(parse_trace((EX / name).read_text()))


def test_overlapping_children_are_not_double_counted():
    a = load("parallel.jsonl")
    assert a.row("run").exclusive == 20  # 100 minus the union 10..90, not minus 50 + 50
    assert a.wall_time == 100


def test_known_numbers_for_the_example_trace():
    a = load("trace.jsonl")
    assert (a.wall_time, a.total_tokens, a.errors, a.failed_span_tokens) == (100, 710, 1, 500)
    assert a.row("run").exclusive == 9
    assert a.slowest.id == "orders" and a.slowest.exclusive == 40


def test_rows_are_depth_first_by_start():
    a = load("trace.jsonl")
    assert [r.id for r in a.rows] == ["run", "plan", "search", "orders", "draft"]
    assert [r.depth for r in a.rows] == [0, 1, 1, 1, 1]


def test_deep_trace_does_not_hit_recursion_limit():
    spans = [Span(f"s{i}", "n", 0, 100, "ok", 0, f"s{i - 1}" if i else None) for i in range(3000)]
    assert len(analyze(spans).rows) == 3000


def test_diff_shows_what_changed_while_wall_time_did_not():
    r = compare(load("trace.jsonl"), load("baseline.jsonl"))
    d = r.diff
    assert d.wall_time == 0 and d.errors == 1 and d.total_tokens == 200 and d.failed_span_tokens == 500
    assert d.changes["draft"].status_before == "ok" and d.changes["draft"].status_after == "error"


def test_default_gate_fails_on_a_new_error():
    r = compare(load("trace.jsonl"), load("baseline.jsonl"))
    assert not r.passed and "errors rose by 1" in r.failures[0]


def test_limits_can_allow_or_add_failures():
    cur, base = load("trace.jsonl"), load("baseline.jsonl")
    assert compare(cur, base, max_new_errors=1).passed
    r = compare(cur, base, max_new_errors=1, max_token_increase=100, max_failed_token_increase=10)
    assert len(r.failures) == 2


def test_identical_runs_pass():
    a = load("baseline.jsonl")
    assert compare(a, a).passed


def test_absolute_error_limit_works_without_baseline():
    a = load("trace.jsonl")
    assert not compare(a, max_errors=0).passed
    assert compare(a, max_errors=1).passed


def test_increase_limits_need_a_baseline():
    with pytest.raises(TraceError) as e:
        compare(load("trace.jsonl"), max_wall_increase=5)
    assert e.value.kind == "needs_baseline"


def test_negative_limits_rejected():
    with pytest.raises(TraceError):
        compare(load("trace.jsonl"), load("baseline.jsonl"), max_new_errors=-1)

