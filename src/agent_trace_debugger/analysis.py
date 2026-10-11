"""Timing, token and regression analysis."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from .trace import Span, TraceError, validate_tree

SCHEMA_VERSION = 1


def merge(intervals: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    """Merge overlapping or touching intervals so parallel work is counted once."""
    out: list[list[float]] = []
    for s, e in sorted(intervals):
        if out and s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return [(a, b) for a, b in out]


def union(intervals: Sequence[tuple[float, float]]) -> float:
    return sum(b - a for a, b in merge(intervals))


@dataclass(frozen=True)
class Row:
    span: Span
    depth: int
    inclusive: float
    exclusive: float
    own_segments: tuple[tuple[float, float], ...]
    children: tuple[str, ...]

    @property
    def id(self) -> str:
        return self.span.id


@dataclass(frozen=True)
class Analysis:
    rows: list[Row]
    wall_time: float
    total_tokens: float
    errors: int
    failed_span_tokens: float
    slowest: Row

    def row(self, span_id: str) -> Row | None:
        return next((r for r in self.rows if r.id == span_id), None)

    def summary(self) -> dict[str, Any]:
        return {
            "wall_time": self.wall_time,
            "total_tokens": self.total_tokens,
            "errors": self.errors,
            "failed_span_tokens": self.failed_span_tokens,
            "slowest_own_time": self.slowest.id,
        }


def _order(s: Span) -> tuple[float, str]:
    return (s.start, s.id)


def analyze(spans: Sequence[Span]) -> Analysis:
    """Validate the trace and compute total time, own time, wall time and token totals."""
    validate_tree(spans)
    kids: dict[str, list[Span]] = {s.id: [] for s in spans}
    for s in spans:
        if s.parent is not None:
            kids[s.parent].append(s)
    rows: list[Row] = []
    stack = [(r, 0) for r in sorted((s for s in spans if s.parent is None), key=_order, reverse=True)]
    while stack:  # depth-first, siblings by start time, no recursion limit
        s, depth = stack.pop()
        own: list[tuple[float, float]] = []
        cursor = s.start
        for a, b in merge([(c.start, c.end) for c in kids[s.id]]):
            if a > cursor:
                own.append((cursor, a))
            cursor = max(cursor, b)
        if cursor < s.end:
            own.append((cursor, s.end))
        rows.append(Row(s, depth, s.end - s.start, sum(b - a for a, b in own), tuple(own), tuple(c.id for c in kids[s.id])))
        stack.extend((c, depth + 1) for c in sorted(kids[s.id], key=_order, reverse=True))
    slowest = sorted(rows, key=lambda r: (-r.exclusive, r.id))[0]
    return Analysis(
        rows=rows,
        wall_time=union([(s.start, s.end) for s in spans if s.parent is None]),
        total_tokens=sum(s.tokens for s in spans),
        errors=sum(1 for s in spans if s.status == "error"),
        failed_span_tokens=sum(s.tokens for s in spans if s.status == "error"),
        slowest=slowest,
    )


@dataclass(frozen=True)
class SpanChange:
    id: str
    name: str
    inclusive: float
    exclusive: float
    tokens: float
    status_before: str
    status_after: str


@dataclass(frozen=True)
class Diff:
    wall_time: float
    total_tokens: float
    errors: float
    failed_span_tokens: float
    changes: dict[str, SpanChange]
    added: list[str]
    removed: list[str]


def diff(current: Analysis, baseline: Analysis) -> Diff:
    """Current minus baseline. Spans are matched by id."""
    cur = {r.id: r for r in current.rows}
    base = {r.id: r for r in baseline.rows}
    changes = {
        i: SpanChange(
            i, cur[i].span.name,
            cur[i].inclusive - base[i].inclusive, cur[i].exclusive - base[i].exclusive,
            cur[i].span.tokens - base[i].span.tokens,
            base[i].span.status, cur[i].span.status,
        )
        for i in sorted(cur.keys() & base.keys())
    }
    return Diff(
        wall_time=current.wall_time - baseline.wall_time,
        total_tokens=current.total_tokens - baseline.total_tokens,
        errors=current.errors - baseline.errors,
        failed_span_tokens=current.failed_span_tokens - baseline.failed_span_tokens,
        changes=changes,
        added=sorted(cur.keys() - base.keys()),
        removed=sorted(base.keys() - cur.keys()),
    )


@dataclass(frozen=True)
class Limits:
    """Gate limits. ``None`` turns a limit off. Increases are current minus baseline."""

    max_new_errors: float | None = 0
    max_wall_increase: float | None = None
    max_token_increase: float | None = None
    max_failed_token_increase: float | None = None
    max_errors: float | None = None

    def to_dict(self) -> dict[str, float | None]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


@dataclass(frozen=True)
class Result:
    current: Analysis
    baseline: Analysis | None
    diff: Diff | None
    limits: Limits
    failures: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures

    def to_dict(self) -> dict[str, Any]:
        d = self.diff
        return {
            "schema_version": SCHEMA_VERSION,
            "summary": self.current.summary(),
            "spans": [
                {
                    "id": r.id, "parent": r.span.parent, "name": r.span.name, "start": r.span.start,
                    "end": r.span.end, "status": r.span.status, "tokens": r.span.tokens,
                    "depth": r.depth, "inclusive": r.inclusive, "exclusive": r.exclusive,
                }
                for r in self.current.rows
            ],
            "baseline": {"summary": self.baseline.summary()} if self.baseline else None,
            "diff": None if d is None else {
                "wall_time": d.wall_time, "total_tokens": d.total_tokens, "errors": d.errors,
                "failed_span_tokens": d.failed_span_tokens,
                "spans": {
                    i: {"inclusive": c.inclusive, "exclusive": c.exclusive, "tokens": c.tokens,
                        "status_before": c.status_before, "status_after": c.status_after}
                    for i, c in d.changes.items()
                },
                "added": list(d.added), "removed": list(d.removed),
            },
            "gate": {"passed": self.passed, "failures": list(self.failures), "limits": self.limits.to_dict()},
        }


def _check(value: object, name: str) -> None:
    if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0):
        raise TraceError("bad_limit", f"{name} must be a number >= 0")


def compare(
    current: Analysis,
    baseline: Analysis | None = None,
    max_new_errors: float | None = 0,
    max_wall_increase: float | None = None,
    max_token_increase: float | None = None,
    max_failed_token_increase: float | None = None,
    max_errors: float | None = None,
) -> Result:
    """Compare a run with an optional baseline and apply the gate limits."""
    limits = Limits(max_new_errors, max_wall_increase, max_token_increase, max_failed_token_increase, max_errors)
    for name, value in limits.to_dict().items():
        _check(value, name)
    if baseline is None and any(
        v is not None for v in (max_wall_increase, max_token_increase, max_failed_token_increase)
    ):
        raise TraceError("needs_baseline", "the increase limits need a baseline trace")
    d = diff(current, baseline) if baseline else None
    failures: list[str] = []

    def over(delta: float, limit: float | None, label: str, now: float, before: float, unit: str = "") -> None:
        if limit is not None and delta > limit:
            failures.append(f"{label} rose by {delta:g}{unit} ({before:g} -> {now:g}), limit {limit:g}{unit}")

    if d and baseline:
        over(d.errors, max_new_errors, "errors", current.errors, baseline.errors)
        over(d.wall_time, max_wall_increase, "wall time", current.wall_time, baseline.wall_time, " ms")
        over(d.total_tokens, max_token_increase, "total tokens", current.total_tokens, baseline.total_tokens)
        over(d.failed_span_tokens, max_failed_token_increase, "tokens in failed spans",
             current.failed_span_tokens, baseline.failed_span_tokens)
    if max_errors is not None and current.errors > max_errors:
        failures.append(f"{current.errors} errors, limit {max_errors:g}")
    return Result(current, baseline, d, limits, failures)

