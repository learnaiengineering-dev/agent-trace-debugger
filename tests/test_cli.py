import json
from pathlib import Path

from agent_trace_debugger.cli import main

EX = Path(__file__).resolve().parent.parent / "examples"
T, B = str(EX / "trace.jsonl"), str(EX / "baseline.jsonl")


def test_new_error_fails_with_exit_1(capsys):
    assert main([T, "--baseline", B]) == 1
    assert "Result: FAIL" in capsys.readouterr().out


def test_allowing_one_error_passes(capsys):
    assert main([T, "--baseline", B, "--max-new-errors", "1"]) == 0


def test_single_trace_reports_and_passes(capsys):
    assert main([T]) == 0
    assert "tokens in failed" in capsys.readouterr().out


def test_quiet_prints_one_line(capsys):
    main([T, "--baseline", B, "--quiet"])
    assert capsys.readouterr().out.strip().startswith("Result: FAIL")


def test_reports_are_written(tmp_path):
    j, m, h = tmp_path / "r.json", tmp_path / "r.md", tmp_path / "r.html"
    main([T, "--baseline", B, "--json", str(j), "--markdown", str(m), "--html", str(h)])
    assert json.loads(j.read_text())["schema_version"] == 1
    assert "Agent Trace Debugger" in m.read_text() and h.read_text().startswith("<!doctype html>")


def test_github_summary_appends(tmp_path, monkeypatch):
    s = tmp_path / "s.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(s))
    main([T, "--baseline", B, "--github-summary"])
    assert "Agent Trace Debugger" in s.read_text()


def test_missing_file_exits_2(capsys):
    assert main(["nope.jsonl"]) == 2
    assert "error:" in capsys.readouterr().err


def test_bad_span_names_file_and_line(tmp_path, capsys):
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"id": "a"}\n')
    assert main([str(bad)]) == 2
    err = capsys.readouterr().err
    assert "bad.jsonl" in err and "line 1" in err


def test_increase_limit_without_baseline_exits_2(capsys):
    assert main([T, "--max-wall-increase", "5"]) == 2


def test_unwritable_report_exits_2(tmp_path, capsys):
    assert main([T, "--html", str(tmp_path / "no" / "r.html")]) == 2
    assert "could not write report" in capsys.readouterr().err

