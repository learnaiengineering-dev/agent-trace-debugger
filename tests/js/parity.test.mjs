// Run with: node --test tests/js/parity.test.mjs
// The widget's logic must match the Python implementation, via the shared golden file.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { analyze, compare, parseTrace, headline, TraceError } from "../../docs/agent-trace-widget.js";

const golden = JSON.parse(readFileSync(new URL("../golden/cases.json", import.meta.url), "utf8"));

const toLimits = (l) => ({
  ...(l.max_new_errors !== undefined && { maxNewErrors: l.max_new_errors }),
  ...(l.max_wall_increase !== undefined && { maxWallIncrease: l.max_wall_increase }),
  ...(l.max_token_increase !== undefined && { maxTokenIncrease: l.max_token_increase }),
  ...(l.max_failed_token_increase !== undefined && { maxFailedTokenIncrease: l.max_failed_token_increase }),
  ...(l.max_errors !== undefined && { maxErrors: l.max_errors }),
});

function close(actual, expected, path = "") {
  if (expected !== null && typeof expected === "object" && !Array.isArray(expected)) {
    assert.ok(actual !== null && typeof actual === "object", `object at ${path}`);
    assert.deepEqual(Object.keys(actual).sort(), Object.keys(expected).sort(), `keys at ${path}`);
    for (const key of Object.keys(expected)) close(actual[key], expected[key], `${path}.${key}`);
  } else if (typeof expected === "number") {
    assert.ok(Math.abs(actual - expected) < 1e-9, `${path}: ${actual} vs ${expected}`);
  } else if (Array.isArray(expected) && path.endsWith(".failures")) {
    // Wording of failure messages can differ slightly between languages; the count must match.
    assert.equal(actual.length, expected.length, `length at ${path}`);
  } else {
    assert.deepEqual(actual, expected, path);
  }
}

for (const c of golden.reports) {
  test(`report matches Python: ${c.name}`, () => {
    const current = analyze(parseTrace(c.current));
    const baseline = c.baseline ? analyze(parseTrace(c.baseline)) : null;
    close(compare(current, baseline, toLimits(c.limits)), c.expected);
  });
}

for (const c of golden.invalid) {
  test(`invalid input matches Python: ${c.name}`, () => {
    assert.throws(
      () => analyze(parseTrace(c.text)),
      (e) => e instanceof TraceError && e.kind === c.expected.kind && e.line === c.expected.line,
    );
  });
}

for (const c of golden.limit_errors) {
  test(`limit error matches Python: ${c.name}`, () => {
    const one = analyze(parseTrace('{"id": "a", "name": "A", "start": 0, "end": 10, "status": "ok", "tokens": 0}'));
    assert.throws(() => compare(one, null, toLimits(c.limits)), (e) => e instanceof TraceError && e.kind === c.kind);
  });
}

test("parallel children are not double-counted", () => {
  const c = golden.reports.find((r) => r.name === "parallel tools alone");
  const a = analyze(parseTrace(c.current));
  assert.equal(a.rows.find((r) => r.id === "run").exclusive, 20);
});

test("the headline names the change that wall time hides", () => {
  const c = golden.reports.find((r) => r.name === "example vs baseline");
  const report = compare(analyze(parseTrace(c.current)), analyze(parseTrace(c.baseline)));
  assert.match(headline(report), /Wall time is unchanged at 100 ms/);
  assert.match(headline(report), /\+500 tokens spent in failed spans/);
});

test("a very deep trace does not overflow the stack", () => {
  const lines = Array.from({ length: 5000 }, (_, i) => JSON.stringify({ id: `s${i}`, ...(i ? { parent: `s${i - 1}` } : {}), name: "n", start: 0, end: 100, status: "ok", tokens: 0 }));
  assert.equal(analyze(parseTrace(lines.join("\n"))).rows.length, 5000);
});
