"""The Python package and the browser widget must agree. Both are checked against this golden file."""
import json
from pathlib import Path

import pytest

from agent_trace_debugger import TraceError, analyze, compare, parse_trace

GOLDEN = json.loads((Path(__file__).resolve().parent / "golden" / "cases.json").read_text())


def close(a, b, path=""):
    if isinstance(a, dict):
        assert isinstance(b, dict) and a.keys() == b.keys(), path
        for key in a:
            close(a[key], b[key], f"{path}.{key}")
    elif isinstance(a, list):
        assert a == b, path
    elif isinstance(a, float) or isinstance(b, float):
        assert a == pytest.approx(b, abs=1e-9), path
    else:
        assert a == b, path


@pytest.mark.parametrize("case", GOLDEN["reports"], ids=[c["name"] for c in GOLDEN["reports"]])
def test_report_matches_golden(case):
    current = analyze(parse_trace(case["current"]))
    baseline = analyze(parse_trace(case["baseline"])) if case["baseline"] else None
    close(compare(current, baseline, **case["limits"]).to_dict(), case["expected"])


@pytest.mark.parametrize("case", GOLDEN["invalid"], ids=[c["name"] for c in GOLDEN["invalid"]])
def test_invalid_input_matches_golden(case):
    with pytest.raises(TraceError) as e:
        analyze(parse_trace(case["text"]))
    assert {"kind": e.value.kind, "line": e.value.line} == case["expected"]


@pytest.mark.parametrize("case", GOLDEN["limit_errors"], ids=[c["name"] for c in GOLDEN["limit_errors"]])
def test_limit_errors_match_golden(case):
    one = analyze(parse_trace('{"id": "a", "name": "A", "start": 0, "end": 10, "status": "ok", "tokens": 0}'))
    with pytest.raises(TraceError) as e:
        compare(one, **case["limits"])
    assert e.value.kind == case["kind"]
