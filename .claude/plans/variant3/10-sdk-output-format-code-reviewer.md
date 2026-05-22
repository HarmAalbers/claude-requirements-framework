# Step 10 — SDK `output_format` worker + aggregator agent (`code-reviewer`)

> **Revised body, 2026-05-22.** Replaces the original "Instructor-wrap `code-reviewer`" plan, superseded by [ADR-016](../../../docs/adr/ADR-016-v3-claude-agent-sdk-substrate.md). The user has Max only (no API key), so `anthropic.Anthropic()` + `instructor.from_anthropic()` is not viable. Substrate is `claude_agent_sdk.query()` with native `output_format` — validated end-to-end by `hooks/lib/llm/_spikes/v3_spike.py`.

## Goal

Promote the spike pattern into the package. Land **one structured-output worker** (`code-reviewer`) plus the **aggregator agent**, both calling `query(output_format=…)` through the budget-recording wrapper at `hooks/lib/llm/claude.py`. Neither is wired into `/deep-review` yet — that consolidation happens in Step 18.

The aggregator is included even though we have only one worker, because:
1. Its contract (`list[ReviewReport] → ReviewReport`) is what Step 18 will consume — landing it now means Step 18 is purely "add more workers", no new packaging.
2. A degenerate length-1 input still validates prompt rendering, JSON contract round-trip, severity ranking, and narrative-summary generation.
3. The spike already proved the architecture; promoting it costs nothing extra and avoids deleting working code.

## Why `code-reviewer` first

It's the most-recruited agent (3 workflows). High-volume = highest signal on whether structured output is worth the conversion cost across the remaining ~24 agents.

## Files touched

New:
- `hooks/lib/llm/workers/code_reviewer.py` — async `review(diff, scope) → ReviewReport`
- `hooks/lib/llm/workers/aggregator.py` — async `aggregate(reports) → ReviewReport`
- `tests/test_code_reviewer_worker.py` — mocked-SDK unit tests
- `tests/test_aggregator.py` — mocked-SDK unit tests (incl. degenerate len-1)
- `hooks/lib/llm/_spikes/v3_code_reviewer_smoke.py` — runnable end-to-end against the deliberate-bug diff

Modified:
- `hooks/lib/llm/workers/__init__.py` — export `review` and `aggregate`
- `hooks/lib/llm/_spikes/README.md` — link the new smoke

## Validated API (from the spike, SDK v0.2.82)

```python
from hooks.lib.llm.claude import query, ClaudeAgentOptions, ResultMessage
from hooks.lib.llm.schemas import ReviewReport

async for msg in query(
    prompt=PROMPT,
    options=ClaudeAgentOptions(
        system_prompt="You are code-reviewer producing strict JSON output.",
        output_format={"type": "json_schema", "schema": ReviewReport.model_json_schema()},
        allowed_tools=[],   # workers MUST NOT read/write files; supervisor handles I/O
        max_turns=5,
    ),
):
    if isinstance(msg, ResultMessage):
        if msg.subtype == "success" and msg.structured_output:
            return ReviewReport.model_validate(msg.structured_output)
        raise RuntimeError(f"worker failed: subtype={msg.subtype!r}")
```

Key points:
- `output_format` is SDK-native; the SDK validates internally and retries on schema mismatch up to its built-in cap. The terminal `ResultMessage.subtype` is either `"success"` (then `structured_output` is the parsed dict) or `"error_max_structured_output_retries"`.
- We import `query` from `hooks.lib.llm.claude` (not `claude_agent_sdk` directly), so observability is pre-initialized (Step 11, R7) AND every call is auto-recorded into the budget ledger (Step 17a).
- `allowed_tools=[]` keeps workers in a pure transform role — diff in, ReviewReport out. No filesystem, no shell, no nested Task calls.

## Implementation sketch

```python
# hooks/lib/llm/workers/code_reviewer.py
from hooks.lib.llm.claude import ClaudeAgentOptions, ResultMessage, query
from hooks.lib.llm.schemas import ReviewReport


_SYSTEM = (
    "You are code-reviewer, producing strict JSON output conforming to ReviewReport. "
    "Filter aggressively — quality over quantity. Only report findings you are confident about."
)

_PROMPT = """\
Review the diff below. For each issue, produce a ReviewFinding with:
  severity:   CRITICAL | IMPORTANT | SUGGESTION
  file, line: location (line >= 1)
  category:   security | performance | logic | style | test | compatibility | complexity
  title:      10–120 chars
  body:       1–3 sentences explaining the issue
  suggested_fix: optional code or guidance
  confidence: 0.0–1.0

Wrap them in a ReviewReport with agent='code-reviewer', scope={scope!r}, and a 1–3 sentence summary.

```diff
{diff}
```
"""


async def review(diff: str, scope: str = "unstaged") -> ReviewReport:
    prompt = _PROMPT.format(diff=diff, scope=scope)
    options = ClaudeAgentOptions(
        system_prompt=_SYSTEM,
        output_format={"type": "json_schema", "schema": ReviewReport.model_json_schema()},
        allowed_tools=[],
        max_turns=5,
    )
    async for msg in query(prompt=prompt, options=options):
        if isinstance(msg, ResultMessage):
            if msg.subtype == "success" and msg.structured_output:
                return ReviewReport.model_validate(msg.structured_output)
            raise RuntimeError(f"code-reviewer failed: subtype={msg.subtype!r}")
    raise RuntimeError("code-reviewer: no ResultMessage")
```

The aggregator follows the same shape — its prompt encodes the merge rules from `v3_spike.py` lines 130–149 (±2-line semantic merge, attribution, severity-then-confidence ranking, narrative summary).

## Acceptance

- [ ] `from hooks.lib.llm.workers import review, aggregate` succeeds
- [ ] `python3 tests/test_code_reviewer_worker.py` passes (mocked SDK; covers success path, `error_max_structured_output_retries`, no-ResultMessage case, agent-label propagation to budget recorder)
- [ ] `python3 tests/test_aggregator.py` passes (mocked SDK; covers degenerate len-1 input, len-2 merge, error subtype handling)
- [ ] `python3 hooks/lib/llm/_spikes/v3_code_reviewer_smoke.py` produces a valid `ReviewReport` on the deliberate-bug diff under Max auth — captured in the spike output, not gated in CI
- [ ] All existing test suites still green (1370/1370 at start of Step 10)
- [ ] `req budget tail -n 5` shows a `code-reviewer`-labeled entry after running the smoke

## Non-goals (deferred)

- Wiring `/deep-review` to call `review()`/`aggregate()`. That's Step 18 (supervisor) — until then, `/deep-review` continues to recruit `code-reviewer` via Task tool the legacy way.
- Converting other review agents (`appsec-auditor`, `solid-reviewer`, etc.) — also Step 18.
- Per-call token caps / degradation ladder — Step 17b, deferred behind Step 16 (templates).
- Replacing the inline prompt with a Jinja2 template — Step 16.
- Retrieval-augmented prompts — Step 13/14.

## Rollback

```bash
stg pop step-10-* && stg delete step-10-*
```

Nothing outside `hooks/lib/llm/workers/` and `tests/` consumes the new code; rollback is safe.

## Effort

≤ 1 day (most of the work is already in `v3_spike.py`; promotion is mechanical).

## Depends on

- Step 08 (`hooks/lib/llm/` package scaffold) — done.
- Step 09 (`ReviewReport` schema) — done.
- Step 11 (observability + `claude.py` wrapper) — done.
- Step 17a (budget recorder hooked into `claude.py`) — done.

## Honest scope note

This step intentionally lands a small surface (~2 modules + tests + 1 spike). The hard architectural decisions were made in ADR-016 and validated by the V3 spike. Step 10's job is to make that pattern importable and tested, not to re-litigate it.

## Pattern for Step 18

Once Step 10 lands, the template for converting any additional review agent is:

```python
# hooks/lib/llm/workers/<agent>.py
_SYSTEM = "..."  # agent-specific
_PROMPT = "..."  # agent-specific; same output_format contract

async def <agent>(diff: str, scope: str = "unstaged") -> ReviewReport:
    # identical body to code_reviewer.review(), different prompt
    ...
```

Step 18 fans out N of these in parallel via `asyncio.gather(...)` and pipes the result list through `aggregate(...)`.
