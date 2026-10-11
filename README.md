# agent-trace-debugger

A dependency-free **trace debugger and CI gate for AI agent runs**. Feed it a trace (one JSON span per line) and it shows where time and tokens went. Feed it a baseline too, and it tells you what changed, even when the wall time did not.

> A run can finish in the same 100 ms and still be worse: one more error, hundreds more tokens burned in failed calls. This tool makes that visible and can fail the build on it.

## Install

```bash
pip install agent-trace-debugger
```

Python 3.10+, no runtime dependencies, no network access.

## Quickstart

```bash
git clone https://github.com/learnaiengineering-dev/agent-trace-debugger
cd agent-trace-debugger
pip install -e ".[dev]"
trace-debug examples/trace.jsonl --baseline examples/baseline.jsonl --html report.html
```

<<OUTPUT>>

Open `report.html` for a self-contained timeline (no scripts, no external assets), or send `--markdown` output to a pull request.

The exit code is the contract:

| Exit code | Meaning |
|---|---|
| 0 | Passed |
| 1 | A limit was exceeded (see "The gate" below) |
| 2 | Bad input (unreadable file, invalid span, broken parent links) |

## Trace format

One JSON object per line:

```json
{"id": "run", "name": "Support agent run", "start": 0, "end": 100, "status": "ok", "tokens": 0}
{"id": "draft", "parent": "run", "name": "Draft reply", "start": 80, "end": 95, "status": "error", "tokens": 500}
```

| Field | Rules |
|---|---|
| `id` | Non-empty string, unique in the trace |
| `parent` | Optional. The `id` of the parent span. Omit or use `null` for a root |
| `name` | String |
| `start`, `end` | Numbers (milliseconds), `end >= start` |
| `status` | `"ok"` or `"error"` |
| `tokens` | Number >= 0: this span's **own** usage, not including its children |

Rules checked on load: unique ids, parents exist, no cycles, and every child lies inside its parent's interval. Clocks from different machines must be normalised before import. OTLP JSON is not read directly; convert it to this format.

## What it measures

- **Total time** of a span is `end - start`.
- **Own time** is total time minus the *union* of its children's intervals, so parallel children are not double-counted. Two overlapping 50 ms tools inside a 100 ms parent leave 20 ms of parent own time, not zero.
- **Wall time** is the union of the root spans.
- **Tokens in failed spans** is the sum of `tokens` over spans with `status: "error"`.
- **Most own time** names the span doing the most work itself, rather than a root that is mostly waiting.

## The gate

With `--baseline`, the run is compared span by span. The gate fails (exit 1) when:

| Limit | Default | Meaning |
|---|---|---|
| `--max-new-errors N` | 0 | More than N additional errors than the baseline |
| `--max-wall-increase MS` | off | Wall time grew by more than MS |
| `--max-token-increase N` | off | Total tokens grew by more than N |
| `--max-failed-token-increase N` | off | Tokens in failed spans grew by more than N |
| `--max-errors N` | off | Absolute error count above N (works without a baseline) |

## Options

```text
trace-debug TRACE [--baseline BASELINE]
  --json PATH          full report (schema_version 1)
  --markdown PATH      pull-request-friendly summary
  --html PATH          self-contained timeline report
  --github-summary     append the Markdown to $GITHUB_STEP_SUMMARY
  --quiet              print only the result line
```

## Use it in GitHub Actions

```yaml
- uses: actions/checkout@v4
- uses: learnaiengineering-dev/agent-trace-debugger@v0.1.0
  with:
    trace: traces/current.jsonl
    baseline: traces/baseline.jsonl
    max-wall-increase: "50"
    html: trace-report.html
```

See [`examples/github-action.yml`](examples/github-action.yml) for a version that also uploads the HTML report.

## Use it from Python

```python
from agent_trace_debugger import analyze, compare, parse_trace

current = analyze(parse_trace(open("current.jsonl").read()))
baseline = analyze(parse_trace(open("baseline.jsonl").read()))
result = compare(current, baseline, max_wall_increase=50)
if not result.passed:
    print("\n".join(result.failures))
report = result.to_dict()   # JSON-serialisable, schema_version 1
```

## Embed it on a web page

`docs/agent-trace-widget.js` is a single-file web component with no dependencies and no network access:

```html
<script type="module" src="/assets/agent-trace-widget.js"></script>
<agent-trace heading="Last agent run">
  <script type="application/x-ndjson" data-role="current">
{"id":"run","name":"Agent run","start":0,"end":100,"status":"ok","tokens":0}
  </script>
</agent-trace>
```

It is themeable with CSS custom properties, works under a strict content policy, and emits a `trace-result` event carrying the same report the Python package writes. See the [docs page](docs/index.html) for attributes, a live demo and the iframe option. The widget's numbers are checked against the Python package with a shared golden file.

## Use it in your organisation

- **No network, no telemetry, no dependencies.** It reads files and writes reports. It runs offline and behind a firewall.
- **Traces stay local.** Nothing is uploaded. Treat trace files as you would logs: they can contain prompts and customer text, so redact before sharing a report.
- **Deterministic.** The same inputs always produce the same numbers and the same report.
- **Stable outputs.** The JSON report carries `schema_version` and the exit codes are documented. Pin a version in your pipeline.
- **MIT licensed.** Use, modify and redistribute it, including in commercial products. Keep the licence and [NOTICE](NOTICE).

## Limits

- Span names and other text come from your trace. The HTML and Markdown reports escape them, but if you paste report text into another tool, treat it as untrusted data.
- Token counts must be per-span. Cumulative counts would be double-counted in the totals.
- The timeline shows timing as recorded. It does not explain why a span was slow or why a call failed.

## Credit

The span format and timing rules follow the Agent Trace Debugger project in [AI Engineering from Scratch](https://github.com/rohitg00/ai-engineering-from-scratch) by rohitg00 (MIT). This is an independent implementation. See [NOTICE](NOTICE).

---

## Part of Learn AI Engineering

This repo is a free resource from [Learn AI Engineering](https://learnaiengineering.dev/?utm_source=github&utm_medium=repo&utm_campaign=agent-trace-debugger) — *Build production AI systems.*

- Structured learning paths, labs and portfolio projects: [https://learnaiengineering.dev](https://learnaiengineering.dev/?utm_source=github&utm_medium=repo&utm_campaign=agent-trace-debugger)
- Want the production-ready version (enterprise templates, deployment, evals, runbooks)? See the **FDE Toolkit** on the portal.
- More free repos: [github.com/learnaiengineering-dev](https://github.com/learnaiengineering-dev)

Licensed under MIT.
