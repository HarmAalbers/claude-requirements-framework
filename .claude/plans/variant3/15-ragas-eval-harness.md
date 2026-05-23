# Step 15 — Ragas eval harness + minimal golden set

> **Rewritten 2026-05-23** for the ADR-016 substrate. The original Step 15
> (direct `AnthropicChat` judge + 20 hand-curated cases + `ToolCallAccuracy`
> on a code-reviewer that has no tools) is non-viable under Max-only auth and
> over-scoped for a harness that has no users yet. This document replaces it.

## Goal

Score every `code_reviewer` worker run against a small golden set using two
complementary metrics — a deterministic structural `FindingMatch` (does the
report mention the expected file/line/category?) and a semantic
`AgentGoalAccuracyWithReference` judged by a persistent `ClaudeSDKClient`
session. Persist scores both as a per-branch JSONL ledger and as Langfuse
trace scores so the same data is available for diffing (git) and for human
inspection (Langfuse UI from Step 11).

## Why now

After Step 14, the V3 platform can write, retrieve, route, and produce
structured output — but every prompt change is still vibes. Step 20 (Sonnet
pinning on review agents) is meaningless without an eval baseline to compare
against. Step 15 is the gate.

## Scope decisions (locked 2026-05-23)

| Question | Decision |
| --- | --- |
| Judge model | **Haiku default** via persistent `ClaudeSDKClient`. `--judge sonnet` CLI flag escalates per-run. Per Step 17a budget data, 5-case Haiku cycle ≈ $0.05; Sonnet ≈ $0.50. |
| Golden-set scope | **5 hand-authored synthetic cases.** One per finding category: security/CRITICAL, perf/IMPORTANT, correctness/IMPORTANT, type-safety/SUGGESTION, simplification/SUGGESTION. Expand only after dogfooding surfaces patterns. |
| Metric mix | **`FindingMatch` (deterministic) + `AgentGoalAccuracyWithReference` (Ragas+LLM judge).** `ToolCallAccuracy` deferred — code-reviewer doesn't use tools. |
| Result destinations | **Both JSONL ledger AND Langfuse scores.** JSONL at `.git/requirements/eval/<YYYY-MM-DD_HHMMSS>_<branch>.jsonl` for replay/diff; Langfuse `score(trace_id, name, value)` for the UI built in Step 11. |
| Default flag | **Manual CLI only** (`python3 scripts/run_eval.py`). No pre-PR gate, no nightly cron yet — wire those when the harness has dogfooded long enough that the threshold isn't arbitrary. |
| SDK substrate | **Persistent `ClaudeSDKClient` session** for the judge, not per-call `query()`. Spike data: `query()` has ~6–12s subprocess overhead per call; 5 cases × 12s = 1 minute of pure startup. `ClaudeSDKClient` amortizes the subprocess across the run. |
| Adapter routing | **Import the SDK via `hooks.lib.llm.claude`**, not `claude_agent_sdk` directly. Inherits Step 11 observability spans + Step 17a budget recording for free. |
| Branching | **Stack on `refactor/step-08-llm-package-scaffold`** as stg patches. Continues the 13/14 pattern. |

## Files touched

| File | Action |
| --- | --- |
| `hooks/lib/llm/eval.py` | populated — `ClaudeSDKRagasLLM`, `FindingMatch`, `score_case`, optional Langfuse poster |
| `tests/test_eval.py` | **new** — pure-helper + mocked-judge tests using `TestRunner` |
| `golden_set/README.md` | **new** — case format + how-to-add docs |
| `golden_set/cases/00{1..5}-*.json` | **new** — 5 synthetic cases |
| `golden_set/diffs/00{1..5}.diff` | **new** — matching diffs |
| `scripts/run_eval.py` | **new** — async CLI driver |
| `hooks/lib/llm/_spikes/v3_ragas_eval_smoke.py` | **new** — loud-fail end-to-end smoke |
| `pyproject.toml` | **no change** — `ragas>=0.2` already declared in `[llm]` extras |
| `plugins/requirements-framework/.claude-plugin/plugin.json` | bump 4.2.0 → 4.3.0 |
| `CHANGELOG.md` | append v4.3.0 entry |

## Validated APIs

### Persistent `ClaudeSDKClient` for the judge

```python
from hooks.lib.llm.claude import ClaudeSDKClient, ClaudeAgentOptions

async def judge_session(model: str = "claude-haiku-4-5"):
    async with ClaudeSDKClient(options=ClaudeAgentOptions(model=model)) as client:
        # Send N prompts; subprocess opened once, reused across the session.
        await client.query("rate this answer 0-1: ...")
        async for msg in client.receive_response():
            ...
```

The session-per-eval-run pattern is the spike-validated trick — Ragas calls
the judge per case, so wrapping the whole eval cycle in one client open/close
amortizes the ~10s subprocess startup.

### Ragas custom LLM adapter

```python
from ragas.llms.base import BaseRagasLLM
from langchain_core.outputs import LLMResult, Generation

class ClaudeSDKRagasLLM(BaseRagasLLM):
    """Ragas-compatible wrapper over a long-lived ClaudeSDKClient."""

    def __init__(self, client: ClaudeSDKClient):
        self._client = client

    async def agenerate_text(self, prompt: str, *_, **__) -> LLMResult:
        await self._client.query(prompt)
        text = "".join(msg.content async for msg in self._client.receive_response()
                       if hasattr(msg, "content"))
        return LLMResult(generations=[[Generation(text=text)]])
```

(Exact signature pinned during Patch 2 against the Ragas 0.2.x BaseRagasLLM
contract — the docs above are illustrative.)

### Deterministic `FindingMatch` metric

```python
from pydantic import BaseModel

class FindingMatch(BaseModel):
    file_match: bool        # exact path
    line_match: bool        # within ±2 of expected
    category_match: bool    # exact (security|perf|correctness|...)

    @property
    def score(self) -> float:
        return sum([self.file_match, self.line_match, self.category_match]) / 3.0
```

Per-case score = arithmetic mean of file/line/category match flags. Lenient
enough that one-off prompt drift doesn't tank the run; strict enough that
wrong-file findings score zero.

## Acceptance

- [ ] `python3 tests/test_eval.py` passes (mocked SDK + Langfuse client)
- [ ] `python3 scripts/run_eval.py` runs to completion against the 5 cases
- [ ] JSONL ledger written to `.git/requirements/eval/` with one line per case
- [ ] Langfuse scores visible in UI when `LANGFUSE_PUBLIC_KEY` is set
- [ ] Smoke spike's median `FindingMatch.score` ≥ 0.66 on the 5 cases (proves
      code-reviewer actually finds the planted bugs at least 2-of-3 fields)
- [ ] Smoke's wall-clock for the 5-case Haiku run < 90s (vs ~120s theoretical
      floor if we'd used per-call `query()`)

## Rollback

`scripts/run_eval.py` is manual-only. Nothing in production runtime depends
on `eval.py`. Removing the patches leaves the rest of V3 untouched.

## Effort

Half a day — eval module + adapter is the bulk; 5 synthetic cases are
~2 hours of authoring; everything else (script, smoke, housekeeping) is
boilerplate.

## Depends on

- Step 09 (schemas for `ReviewReport`)
- Step 10 (`workers.code_reviewer.review`)
- Step 11 (Langfuse — soft dep, fail-open if unreachable)
- Step 13/14 not required, but eval cases stored in Qdrant would be a
  future feature (not in scope).

## Honest scope notes

- **5 cases is a baseline, not coverage.** Expand opportunistically when real
  bugs hit the code-reviewer that the harness misses. Don't commit to a
  weekly curation sprint — that's the path the original 20-case plan was
  going down.
- **`ToolCallAccuracy` deferred.** Until V3 has a worker that actually uses
  tools (the `appsec-auditor` once it's migrated, maybe), the metric is dead
  weight. The plan from Step 18 mentions Pydantic `HandoffResult` for the
  supervisor — that's an arguable tool call but not in the code-reviewer
  scope.
- **No pre-PR gate, no cron.** The harness exists; the wiring is a follow-up.
  Wiring it as a gate against an unknown threshold is "regression detection
  theatre" — wait for ≥3 cycles of human-confirmed baseline before
  automating the gate.
- **No real-bug corpus.** Synthetic cases test the harness, not the model's
  ability to find weird real bugs. A future Step 15b can mine `git log
  --grep=fix` for real bug commits and label them.
- **Judge variance is real but unmeasured.** Same case judged twice by Haiku
  produces slightly different scores. Plan to record 3 judge passes per case
  in a follow-up to quantify variance — out of scope today.
