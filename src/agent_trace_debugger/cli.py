"""Command line entry point. Exit codes: 0 pass, 1 a limit was exceeded, 2 bad input."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .analysis import analyze, compare
from .report import summary_line, to_html, to_json, to_markdown, to_text
from .trace import TraceError, parse_trace


def _load(path: str):
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as e:
        raise TraceError("unreadable", f"{path}: {e.strerror or e}") from e
    try:
        return analyze(parse_trace(text))
    except TraceError as e:
        raise TraceError(e.kind, f"{path}: {e}", e.line) from e


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="trace-debug",
        description="Debug an agent trace and gate regressions. Exit 0 pass, 1 limit exceeded, 2 bad input.",
    )
    p.add_argument("trace", help="JSONL trace: one span per line")
    p.add_argument("--baseline", help="JSONL trace of the previous run to compare against")
    p.add_argument("--max-new-errors", type=float, default=0, help="allowed extra errors vs baseline (default 0)")
    p.add_argument("--max-wall-increase", type=float, help="allowed wall-time increase in ms")
    p.add_argument("--max-token-increase", type=float, help="allowed total-token increase")
    p.add_argument("--max-failed-token-increase", type=float, help="allowed increase in tokens spent in failed spans")
    p.add_argument("--max-errors", type=float, help="absolute error limit (works without a baseline)")
    p.add_argument("--json", metavar="PATH", help="write the full JSON report")
    p.add_argument("--markdown", metavar="PATH", help="write a Markdown summary")
    p.add_argument("--html", metavar="PATH", help="write a self-contained HTML timeline")
    p.add_argument("--github-summary", action="store_true", help="append the Markdown to $GITHUB_STEP_SUMMARY")
    p.add_argument("--quiet", action="store_true", help="print only the result line")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        current = _load(args.trace)
        baseline = _load(args.baseline) if args.baseline else None
        res = compare(
            current, baseline,
            max_new_errors=args.max_new_errors,
            max_wall_increase=args.max_wall_increase,
            max_token_increase=args.max_token_increase,
            max_failed_token_increase=args.max_failed_token_increase,
            max_errors=args.max_errors,
        )
        for path, render in ((args.json, to_json), (args.markdown, to_markdown), (args.html, to_html)):
            if path:
                Path(path).write_text(render(res), encoding="utf-8")
        if args.github_summary and os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
                fh.write(to_markdown(res))
    except TraceError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"error: could not write report: {e.strerror or e}", file=sys.stderr)
        return 2
    print(summary_line(res) if args.quiet else to_text(res))
    return 0 if res.passed else 1

