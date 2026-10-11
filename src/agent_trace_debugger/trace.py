"""Read and validate a trace: one JSON span per line."""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Mapping, Sequence


class TraceError(ValueError):
    """The trace is unreadable or breaks a structural rule. ``kind`` is a stable machine-readable code."""

    def __init__(self, kind: str, message: str, line: int | None = None):
        super().__init__(message)
        self.kind = kind
        self.line = line


@dataclass(frozen=True)
class Span:
    id: str
    name: str
    start: float
    end: float
    status: str
    tokens: float
    parent: str | None = None


def _num(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def parse_trace(text: str) -> list[Span]:
    """Parse JSONL into spans. Blank lines are skipped. Raises TraceError with the line number."""
    spans: list[Span] = []
    for number, line in enumerate(re.split(r"\r?\n", text), 1):
        if not line.strip():
            continue
        try:
            s = json.loads(line)
        except ValueError as e:
            raise TraceError("invalid_json", f"line {number}: not valid JSON", number) from e
        ok = (
            isinstance(s, dict)
            and isinstance(s.get("id"), str) and s["id"] != ""
            and isinstance(s.get("name"), str)
            and (s.get("parent") is None or isinstance(s.get("parent"), str))
            and _num(s.get("start")) and _num(s.get("end")) and _num(s.get("tokens"))
            and s["end"] >= s["start"] and s["tokens"] >= 0
            and s.get("status") in ("ok", "error")
        )
        if not ok:
            raise TraceError(
                "invalid_span",
                f"line {number}: not a valid span (check id, name, start <= end, tokens >= 0, status ok or error)",
                number,
            )
        spans.append(Span(s["id"], s["name"], s["start"], s["end"], s["status"], s["tokens"], s.get("parent")))
    if not spans:
        raise TraceError("empty", "no spans found")
    return spans


def validate_tree(spans: Sequence[Span]) -> Mapping[str, Span]:
    """Check ids, parent links and nesting. Returns spans by id."""
    by_id = {s.id: s for s in spans}
    if len(by_id) != len(spans):
        raise TraceError("duplicate_id", "duplicate span id")
    for s in spans:
        seen = {s.id}
        p = s.parent
        while p is not None:
            if p in seen:
                raise TraceError("cycle", f'span "{s.id}" is part of a parent cycle')
            seen.add(p)
            parent = by_id.get(p)
            if parent is None:
                raise TraceError("missing_parent", f'span "{s.id}" names a missing parent "{p}"')
            p = parent.parent
        if s.parent is not None:
            parent = by_id[s.parent]
            if s.start < parent.start or s.end > parent.end:
                raise TraceError("outside_parent", f'span "{s.id}" runs outside its parent "{s.parent}"')
    return by_id

