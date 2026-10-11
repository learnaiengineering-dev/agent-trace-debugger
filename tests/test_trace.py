import json

import pytest

from agent_trace_debugger import TraceError, parse_trace, validate_tree


def line(**kw):
    base = {"id": "a", "name": "A", "start": 0, "end": 10, "status": "ok", "tokens": 0}
    base.update(kw)
    return json.dumps(base)


def kind(text):
    with pytest.raises(TraceError) as e:
        validate_tree(parse_trace(text))
    return e.value.kind


def test_parses_and_skips_blank_lines():
    spans = parse_trace(line() + "\n\n" + line(id="b", parent="a", start=1, end=2))
    assert [s.id for s in spans] == ["a", "b"] and spans[1].parent == "a"


def test_null_parent_means_root():
    assert parse_trace(line(parent=None))[0].parent is None


def test_error_names_the_line():
    with pytest.raises(TraceError) as e:
        parse_trace(line() + "\nnot json")
    assert e.value.kind == "invalid_json" and e.value.line == 2


@pytest.mark.parametrize(
    "bad",
    [
        dict(id=""), dict(id=5), dict(name=None), dict(status="done"), dict(tokens=-1),
        dict(start=5, end=1), dict(start="0"), dict(tokens=True), dict(parent=7),
    ],
)
def test_invalid_spans_rejected(bad):
    with pytest.raises(TraceError) as e:
        parse_trace(line(**bad))
    assert e.value.kind == "invalid_span"


def test_empty_trace_rejected():
    with pytest.raises(TraceError) as e:
        parse_trace("\n  \n")
    assert e.value.kind == "empty"


def test_structure_rules():
    assert kind(line() + "\n" + line()) == "duplicate_id"
    assert kind(line(parent="zz")) == "missing_parent"
    assert kind(line(id="a", parent="b") + "\n" + line(id="b", parent="a")) == "cycle"
    assert kind(line() + "\n" + line(id="c", parent="a", start=5, end=20)) == "outside_parent"

