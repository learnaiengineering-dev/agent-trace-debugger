"""Debug agent runs and fail CI when they get worse."""
from .analysis import Analysis, Diff, Limits, Row, analyze, compare, diff
from .trace import Span, TraceError, parse_trace, validate_tree

__version__ = "0.1.0"
__all__ = [
    "analyze", "compare", "diff", "parse_trace", "validate_tree",
    "Analysis", "Diff", "Limits", "Row", "Span", "TraceError", "__version__",
]

