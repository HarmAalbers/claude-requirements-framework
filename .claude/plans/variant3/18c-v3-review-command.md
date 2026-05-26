# Step 18c — `/v3-review` command (fan-out exposed at `/deep-review` parity)

> **Status: planned 2026-05-26.** Net-new step. Exposes the Step 18b fan-out
> coordinator as a user-facing command, the payoff 18b deferred ("CLI smoke only").
> Additive — the team-based `/deep-review` (ADR-012) is untouched. See ADR-018.

## Arch-Review Outcome (2026-05-26) — VERDICT: APPROVED

7-agent team review. No CRITICAL blockers; the architecture is sound and additive. Three
HIGH items are *additions*, not redesigns. Binding refinements (fold into the named patch):

**HIGH (cross-validated):**

1. **Extract a testable `run_review(...)` core from `review_cli.py`** (tdd-validator + solid-reviewer
   + codex). The `scope→gate→fanout→render` pipeline must not live inline in a script that
   uses `subprocess`/`sys.exit`/`asyncio.run`, or the key acceptance criterion ("tool-gate
   aborts before LLM spend") has no RED test. Extract `run_review(diff, scope, files, workers)
   -> str` so it's unit-testable with mock workers; `review_cli.py` is the thin shell that
   resolves scope, calls it, prints.
2. **Aggregation resilience at N=11** (compat-checker + codex). 11 reports is ~3.7× the input
   that 18b's smoke choked on. `run_review` must: (a) if `aggregate()` fails, fall back to
   rendering the surviving per-worker reports with a warning (don't die); (b) if ALL workers
   fail, catch `RuntimeError` and print a human-readable "diff too large / all workers failed"
   message. Add an acceptance criterion + test. Tree-reduce aggregation is deferred.
3. **`FanoutResult.worker_errors: dict[str, str]`** (codex). `survivor_count` alone can't tell
   the renderer *which* workers failed/why. Add the field (populated in fanout's exception
   loop), and render a "Workers that did not complete" section. Small additive change to 18b's
   frozen dataclass; backwards-compatible.
4. **`aclose()` race at N=11** (codex; already observed in ADR-017). Wrap the entry's
   `asyncio.run` in `try/finally` that cancels remaining tasks; document as a known limitation.
   Do **NOT** switch to `ClaudeSDKClient` — it bypasses budget recording (`claude.py:25`).

**MEDIUM / design (consensus):**

5. **`tool_gate.py` is its own module** — unanimous (solid HIGH, codex, tdd). Drop the plan's
   "or a function in the entry script" wording; the TDD plan's `test_tool_gate.py` requires it
   importable. Interface: `run_tool_gate(files: list[str]) -> list[str]`, fail-LOUD on missing linter.
6. **No worker factory — keep one-module-per-worker** (solid + refactor + codex + commit-planner,
   unanimous). The ADR-017 mock-patching constraint (`patch.object(worker_module, "query")`) is
   load-bearing; a factory closure would silently bypass it. Stamp the 8 modules from a template
   if desired, but each keeps its own `query`/`ResultMessage` import.
7. **Roster in `workers/rosters.py`, built incrementally** (refactor + commit-planner + solid).
   Seed with 3 in a prep patch, grow per worker-batch so it's never a bolt-on. `WorkerFn` stays
   in `fanout.py`; `rosters.py` imports it one-way; **`fanout.py` must NOT import `rosters.py`**
   (avoids the cycle codex flagged).
8. **`render.py` exposes `compute_verdict(report)` separately** from `render_review_markdown`
   (solid + tdd) so the 3-branch verdict is unit-testable without parsing rendered markdown.
9. **Author 8 `_SYSTEM` strings** (codex) — plan gap; model on the existing workers + each
   plugin agent's intent.
10. **Test additions** (tdd): add the 2 missing cases to the shared worker contract
    (`empty_success`, `skips_non_result` — the shared file has 7, canonical has 9); render
    boundary tests `IMPORTANT==5`→READY vs `==6`→REVIEW + header ordering; tool-gate
    missing-linter loud-fail RED test; roster laziness (modules absent from `sys.modules`
    before first call).
11. **Revised 9-patch plan**: prepend `step-18c-rosters-scaffold` (3 entries), grow the roster
    across batches (see the appended Atomic Commit Strategy + Preparatory Refactoring sections).

**ADR-018 edits (adr-guardian):** see the ADR — (a) note dual-gate-sharing is intentional and
doesn't demote ADR-012; (b) record the corroboration-rule divergence as a **known limitation**
(v3-review may show IMPORTANT where /deep-review escalates to CRITICAL), not just a "refinement";
(c) add a Related ADRs section.

## Goal

Add a `/v3-review` plugin command that runs the SDK fan-out over a diff at **parity-or-better**
with `/deep-review`'s reviewer roster (the 10 always-on reviewers **plus** `solid-reviewer` =
11), renders the unified `ReviewReport` into the ADR-013 markdown format users already expect,
and satisfies the `pre_pr_review` gate — a genuine drop-in alternative to the team path, not a
spike. (Known limitation: it does not replicate `/deep-review`'s cross-validation corroboration
*escalation* rules — see ADR-018.)

## Locked scope decisions (2026-05-26 interview)

| # | Decision | Choice |
|---|---|---|
| 1 | Integration shape | **New `/v3-review` command** — additive; `/deep-review` unchanged; no ADR-012 breakage; no default-spend risk before Step 17b |
| 2 | Worker roster | **Full `/deep-review` parity** — 11 query-workers |
| 3 | Output + gate | **Render ADR-013 markdown + satisfy `pre_pr_review`** |
| 4 | Tool gate | **Replicate** the deterministic ruff/pyright pre-flight gate; abort before LLM spend on CRITICAL tool errors |
| 5 | Special agents | **Defer** `codex-review-agent` (Codex CLI substrate) and `frontend-reviewer` (conditional) to a follow-up |
| 6 | `solid-reviewer` | **Include** (bonus SOLID perspective beyond `/deep-review`'s roster) |

## Worker roster (11)

Already exist (Steps 10/18b): `code-reviewer`, `appsec-auditor`, `solid-reviewer`.

**8 new** thin `_base.run_worker` delegates + `prompts/<name>.md.j2` (modeled on the
plugin agents under `plugins/.../agents/<name>.md.j2`):
`silent-failure-hunter`, `test-analyzer`, `backward-compatibility-checker`,
`type-design-analyzer`, `comment-analyzer`, `code-simplifier`,
`tenant-isolation-auditor`, `compliance-auditor`.

Deferred: `codex-review-agent` (shells to Codex CLI — different substrate, not
`output_format`), `frontend-reviewer` (conditional on `.tsx/.css` in scope).

## What already exists (do not rebuild)

- `workers/_base.run_worker(*, prompt, system, schema, agent_label, query, result_cls, max_turns)` — the shared loop every new worker delegates to (Step 18b)
- `workers/fanout.fanout_review(diff, scope, workers) -> FanoutResult` — the coordinator; takes an injected worker dict, so the 11-worker roster is just a different `workers=` argument (Step 18b)
- `workers/aggregator.aggregate(reports)` — semantic merge (Step 10)
- `tracing.review_session` — session/tag binding (Step 18b)
- `prompts.load_prompt` + `partials/{safety,project_conventions}.j2` (Steps 12/16)
- `scripts/prepare-diff-scope` — scope resolver `/deep-review` uses (writes `/tmp/review.diff`, `/tmp/review_scope.txt`)
- auto-satisfy hook `hooks/auto-satisfy-skills.py` `DEFAULT_SKILL_MAPPINGS` — add `'requirements-framework:v3-review': 'pre_pr_review'`

## Gap analysis

1. **8 workers + prompts missing** — mechanical given `_base`; the variety is per-agent prompt focus.
2. **No review roster** — `fanout._default_workers()` is the 3-worker 18b pilot. Need a `REVIEW_WORKERS` roster (the 11) for this command. Define it where the entry script can pass it as `workers=`.
3. **No `ReviewReport`→markdown renderer** — the command must emit the ADR-013 format (`### CRITICAL/IMPORTANT/SUGGESTION` + `## Summary` + verdict), not raw JSON.
4. **No deterministic tool-gate** — a subprocess step (ruff + pyright on changed Python files) that aborts before fan-out on CRITICAL.
5. **No entry point** — a Python script wiring scope→gate→fanout→render, plus the `/v3-review` Markdown command that shells to it.
6. **No gate satisfaction** — `pre_pr_review` mapping for `v3-review`.

## Design detail

### Review roster (`workers/fanout.py` or a small `workers/rosters.py`)
A `review_workers()` lazy factory returning the 11-name → review-fn dict (same lazy-import
pattern as `_default_workers`). The entry script calls
`fanout_review(diff, scope, workers=review_workers())`.

### Renderer (`hooks/lib/llm/render.py`, new) — TWO functions (arch-review #8)
- `compute_verdict(report: ReviewReport) -> str` — pure, unit-testable, the SAME rule as `/deep-review`:
  - `CRITICAL > 0` → **FIX ISSUES FIRST**
  - else `IMPORTANT > 5` → **REVIEW RECOMMENDED**
  - else → **READY**
- `render_review_markdown(report: ReviewReport, *, worker_errors: dict[str,str] = {}) -> str` —
  calls `compute_verdict`, groups findings by severity (CRITICAL→IMPORTANT→SUGGESTION) with
  Location/Description/Fix, adds a `## Summary` with counts + verdict, and a "Workers that did
  not complete" section when `worker_errors` is non-empty (arch-review #3).

**Known limitation (ADR-018):** the fan-out aggregator does semantic merge + attribution, but
does NOT replicate `/deep-review`'s corroboration *escalation* rules (which bump severity when
specific agent-pairs flag the same region). So `/v3-review` may surface as IMPORTANT a finding
`/deep-review` would escalate to CRITICAL. Recorded as a limitation, not a mere refinement.

### Tool gate (`hooks/lib/llm/tool_gate.py`, new — OWN MODULE, not inline; arch-review #5)
`run_tool_gate(files: list[str]) -> list[str]` runs `ruff check` and `pyright` on the changed
Python files in scope; returns CRITICAL error lines. **Fail-LOUD**: a missing linter binary is
an error (raise), not a silent skip (loud-smoke-spikes rule). The entry layer aborts (prints
errors, non-zero, no fan-out) if any. Mirrors `/deep-review` Step 3's blocking behavior. ESLint
is N/A (Python repo); frontend deferred with `frontend-reviewer`.

### Entry: testable core + thin shell (arch-review #1)
- `run_review(diff: str, scope: str, files: list[str], workers) -> str` (in `review_cli.py` or a
  `review.py`): tool-gate → (abort string if CRITICAL) → `fanout_review(...)` → on aggregator
  failure, render survivors with a warning; on all-workers-fail `RuntimeError`, return a
  human-readable "all workers failed / diff too large" message (arch-review #2) → else
  `render_review_markdown(result.report, worker_errors=result.worker_errors)`. Unit-testable
  with mock workers + mocked gate.
- `review_cli.py main()` — thin shell: read `/tmp/review.diff` (→ diff) and `/tmp/review_scope.txt`
  (→ Python `files`) explicitly (arch-review: avoid hidden `/tmp` coupling in `tool_gate`),
  resolve scope via `prepare-diff-scope` (loud-fail), call `run_review`, print result + session_id
  + cost footer. Wrap `asyncio.run` in `try/finally` cancelling remaining tasks (aclose race, #4).
  Exit 0 on success; the verdict lives in the text (matches `/deep-review`).

### `/v3-review` command (`plugins/requirements-framework/commands/v3-review.md` + `.md.j2`)
Markdown command, `allowed-tools: ["Bash"]`, shells to `${CLAUDE_PLUGIN_ROOT}/scripts/v3-review "$ARGUMENTS"` and relays output — same pattern as `req.md`. **Plugin file → bump `plugin.json`.**

### auto-satisfy (`hooks/auto-satisfy-skills.py`)
Add `'requirements-framework:v3-review': 'pre_pr_review'` to `DEFAULT_SKILL_MAPPINGS`.

## TDD plan

- Extend `tests/test_review_workers.py` to drive all 10 query-workers (the existing 2 + 8 new) through the 7-test contract (incl. system-prompt identity).
- `tests/test_render.py` — verdict logic (3 branches), severity grouping/ordering, empty-findings → READY, ADR-013 section headers present.
- `tests/test_tool_gate.py` — clean files → no errors (mock subprocess); ruff/pyright error → returned as CRITICAL; gate is fail-LOUD (a missing linter is an error, not a skip — per the loud-smoke-spikes rule for gates).
- `tests/test_review_roster.py` — `review_workers()` returns the 11 expected names, lazily.
- Live smoke: reuse `v3_fanout_smoke.py` shape OR run `/v3-review` against the narrow 18b range. Expect ~$8-12 / longer wall-time (11 workers). NOT in the unit suite.
- Framework suite stays green; new `v3-review` command must not break command-loading tests.

## Acceptance

- [ ] `/v3-review <scope>` resolves scope, runs the tool-gate, fans out 11 workers, renders ADR-013 markdown with a correct verdict, prints `session_id` + cost
- [ ] Tool-gate aborts before any LLM spend when ruff/pyright report CRITICAL
- [ ] All 10 query-workers pass the 7-test contract; roster returns 11 lazily
- [ ] Renderer verdict matches `/deep-review`'s rule (FIX/REVIEW/READY)
- [ ] Completing `/v3-review` satisfies `pre_pr_review`
- [ ] `plugin.json` bumped; `./sync.sh status` accounted for; framework suite green
- [ ] Live `/v3-review` on a real narrow diff produces a usable report (one Langfuse session)

## Patch plan (stacked stg on `refactor/step-08-llm-package-scaffold`)

1. `step-18c-plan-docs` — this doc + overview slot + ADR-018
2. `step-18c-workers-batch1` — 4 new workers + prompts + tests (silent-failure-hunter, test-analyzer, backward-compatibility-checker, type-design-analyzer)
3. `step-18c-workers-batch2` — 4 new workers + prompts + tests (comment-analyzer, code-simplifier, tenant-isolation-auditor, compliance-auditor)
4. `step-18c-roster` — `review_workers()` roster (11) + test
5. `step-18c-renderer` — `render.py` + `test_render.py`
6. `step-18c-tool-gate` — `tool_gate.py` + `test_tool_gate.py`
7. `step-18c-entry-and-command` — `review_cli.py` + `scripts/v3-review` + `commands/v3-review.md(.j2)` + auto-satisfy mapping + `plugin.json` bump
8. `step-18c-housekeeping` — exports, `update-plugin-versions.sh`, `sync.sh status`, status-memory update

## Deferred (carry forward)

- **`codex-review-agent`** worker (Codex CLI substrate, not `output_format`) — needs a separate integration
- **`frontend-reviewer`** worker (conditional on `.tsx/.css`) — add when frontend scope detection is wired
- **Cross-validation corroboration rules** — `/deep-review`'s lead applies a rule table; the fan-out aggregator does semantic merge but not the explicit rule-based escalation. Port later if parity demands it.
- **Step 17b budget caps** — at ~$8-12/run, `/v3-review` should ideally run under per-call caps; 17b is still pending. Until then, `/v3-review` is opt-in (its own command), which bounds the exposure.
- **Replacing `/deep-review`** — out of scope; would be a breaking ADR-012 change needing its own ADR.

## Depends on

Steps 10 (worker/aggregator), 16 (templates), 17a (budget), 18 (supervisor pattern), 18b (fan-out coordinator + `_base` + tracing).

---

## Preparatory Refactoring

> Analysis conducted 2026-05-26 before implementing the 8 new workers.

### Observation: workers are structurally identical

The three existing workers (`code_reviewer.py`, `solid_reviewer.py`, `appsec_auditor.py`)
are ~41–52 line modules that differ in exactly two values: the `_SYSTEM` string and the
`load_prompt` name. Every other line is identical boilerplate. At N=11 workers, hand-writing
8 more identical files amplifies that boilerplate 8×.

### Why a "replace modules with a factory" refactor is the wrong move

The tempting fix — replace N modules with a declarative `{name: (system, prompt)}` dict +
a single factory function — breaks the mock-patching contract. Tests use
`patch.object(worker_module, "query", fake_query)` to intercept SDK calls without the
worker needing to accept `query` as a parameter. That pattern requires each worker to own
the `query` and `ResultMessage` names in its *own module namespace*. A factory that
produces closures sharing `_base`'s imports would bypass those patches silently, making all
8 new workers untestable under the existing 7-test contract without rewriting the test
harness. ADR-017 explicitly calls this out; the arch-review cemented it.

Conclusion: **one module per worker is not ceremonial — it is load-bearing for the test
isolation model.** Do not eliminate the modules.

### What IS worth doing: two targeted prep patches

#### Prep A — Extend `tests/test_review_workers.py`'s `WORKERS` table now (before batch 1)

The test table at line 76 already drives all test functions data-dependently:
```python
WORKERS = [
    ("hooks.lib.llm.workers.solid_reviewer", "solid-reviewer", "solid-reviewer"),
    ("hooks.lib.llm.workers.appsec_auditor", "appsec-auditor", "appsec-auditor"),
]
```
Adding a new worker to this table is one line and zero new test functions. Confirm this
works for the 3 pilot workers first (no code change needed — just verify), then during
batch 1 and batch 2 each new worker is one `WORKERS` entry. **No test-harness refactoring
needed; the table pattern already scales.**

#### Prep B — Add `review_workers()` roster to `workers/rosters.py` before writing any worker

The plan already calls for a `REVIEW_WORKERS` roster. Write `workers/rosters.py` with a
`review_workers()` lazy factory *before* batch 1 so each new module is registered as it
lands rather than bolted on at patch 4 (`step-18c-roster`). This also lets `fanout.py`'s
`_default_workers()` be retired in favor of `review_workers()[:3]` or left as the 3-pilot
convenience — either way the roster becomes the single source of truth.

Shape:
```python
# workers/rosters.py
def review_workers() -> dict[str, WorkerFn]:
    """Full 11-worker review roster for /v3-review. Lazily imported."""
    from hooks.lib.llm.workers import (
        appsec_auditor, backward_compatibility_checker, code_reviewer,
        code_simplifier, comment_analyzer, compliance_auditor,
        silent_failure_hunter, solid_reviewer, tenant_isolation_auditor,
        test_analyzer, type_design_analyzer,
    )
    return {
        "code-reviewer":                    code_reviewer.review,
        "solid-reviewer":                   solid_reviewer.review,
        "appsec-auditor":                   appsec_auditor.review,
        "silent-failure-hunter":            silent_failure_hunter.review,
        "test-analyzer":                    test_analyzer.review,
        "backward-compatibility-checker":   backward_compatibility_checker.review,
        "type-design-analyzer":             type_design_analyzer.review,
        "comment-analyzer":                 comment_analyzer.review,
        "code-simplifier":                  code_simplifier.review,
        "tenant-isolation-auditor":         tenant_isolation_auditor.review,
        "compliance-auditor":               compliance_auditor.review,
    }
```

This keeps each worker module independent and mockable while making the roster the single
authoritative list the entry script calls.

#### Prep C — `workers/__init__.py` lazy `__getattr__`: no change needed

At N=11, the current `if name == ...` chain in `__init__.py`'s `__getattr__` is verbose but
correct. The workers are accessed by module (`workers.code_reviewer.review`) not via
`__getattr__`, so the lazy-import table in `__init__.py` only matters for the public names
`review`, `aggregate`, `fanout_review`, `FanoutResult`. Those 4 are not growing. **Leave
`__init__.py` alone.** The new modules are imported directly by `rosters.py` and by tests.

### Revised patch plan

Insert one new patch before `step-18c-workers-batch1`:

```
0. step-18c-rosters-scaffold   — workers/rosters.py with review_workers() stub (3 entries
                                  for now); test_review_roster.py skeleton; no __init__ change
1. step-18c-workers-batch1     — 4 workers + extend WORKERS table (4 entries)
2. step-18c-workers-batch2     — 4 workers + extend WORKERS table (4 more entries)
3. step-18c-roster-complete    — fill all 11 entries in review_workers(); test passes
   (replaces the original step-18c-roster patch)
4–7. unchanged
```

### Summary

| Question | Answer |
|---|---|
| Replace modules with a factory? | No — mock-patching contract is load-bearing |
| Test harness refactor needed? | No — `WORKERS` table already scales to N=11 |
| Unify `_default_workers` + `review_workers`? | Partial: add `rosters.py` first; `_default_workers` can delegate to it or remain the 3-pilot shortcut |
| `__init__.py` `__getattr__` refactor? | Not needed — workers accessed by module, not via `__getattr__` |
| **Net prep work** | One new module (`rosters.py`) + skeleton test = ~1 patch |

---

## Atomic Commit Strategy

Branch: `refactor/step-08-llm-package-scaffold` (already `stg init`-ed, top patch: `step-18c-plan-docs`).

### Dependency graph

```
plan-docs  (already done — top patch)
    ↓
rosters-scaffold   ← new (from Prep B above); write rosters.py + skeleton test FIRST
    ↓
workers-batch1   ← 4 workers + prompts; extend WORKERS table + roster
    ↓
workers-batch2   ← 4 more workers + prompts; extend WORKERS table + fill roster to 11
    ↓
renderer         ← only imports schemas.ReviewReport; no dependency on workers
    ↓
tool-gate        ← shells to ruff/pyright; no dependency on workers or renderer
    ↓
entry-and-command ← imports roster+renderer+tool-gate+fanout_review; ALSO contains
                    commands/v3-review.md(.j2), plugin.json bump, auto-satisfy mapping.
                    Must come last of "code" patches.
    ↓
housekeeping     ← update-plugin-versions.sh, sync.sh status, memory update
```

**Key ordering constraint**: `entry-and-command` depends on roster (complete 11-entry version), renderer, tool-gate, and both worker batches. The plugin rule says `plugin.json` bumps ride in the same patch as the new command file — so the command file, entry script, auto-satisfy mapping, and plugin.json bump are all atomic in P7.

**renderer and tool-gate** have no worker dependencies — they could float earlier. Keeping them after the worker batches groups all "library" patches before the "wiring" patch.

**Declarative registry note**: The `## Preparatory Refactoring` section above explains why a declarative factory replacing worker modules is the wrong move. With the `WORKERS` table pattern in `test_review_workers.py` and the separate `rosters.py`, the two worker batches remain the right granularity. They do NOT collapse regardless of how the roster is wired.

---

### Patch-by-patch specification

#### P1 — `step-18c-plan-docs` (ALREADY DONE — current top patch)
**Files**: `.claude/plans/variant3/18c-v3-review-command.md`, ADR-018, overview slot update.
**Test before `stg refresh`**: `python3 hooks/test_requirements.py` (framework suite green).
**Status**: Already applied.

---

#### P2 — `step-18c-rosters-scaffold`
**Files** (2 files):
- `hooks/lib/llm/workers/rosters.py` — `review_workers()` lazy factory with 3-entry stub (code-reviewer, solid-reviewer, appsec-auditor); `WorkerFn` type alias; docstring noting it will grow to 11
- `tests/test_review_roster.py` — skeleton test: roster returns 3 keys currently, all callable

**Rationale**: Writing the roster file first makes each subsequent worker batch a one-line registration in `review_workers()` rather than a bolt-on at P5. The test stays RED for the 11-worker assertion until the batches land.

**Test before `stg refresh`**:
```bash
python3 tests/test_review_roster.py     # GREEN: 3-entry checks pass
python3 hooks/test_requirements.py      # framework suite green
```

---

#### P3 — `step-18c-workers-batch1`
**Files** (10 files):
- `hooks/lib/llm/workers/silent_failure_hunter.py` (new)
- `hooks/lib/llm/workers/test_analyzer.py` (new)
- `hooks/lib/llm/workers/backward_compatibility_checker.py` (new)
- `hooks/lib/llm/workers/type_design_analyzer.py` (new)
- `hooks/lib/llm/prompts/silent-failure-hunter.md.j2` (new)
- `hooks/lib/llm/prompts/test-analyzer.md.j2` (new)
- `hooks/lib/llm/prompts/backward-compatibility-checker.md.j2` (new)
- `hooks/lib/llm/prompts/type-design-analyzer.md.j2` (new)
- `tests/test_review_workers.py` (extend `WORKERS` list: +4 entries)
- `hooks/lib/llm/workers/rosters.py` (edit: add 4 new entries to `review_workers()`)

**Pattern**: Each worker mirrors `solid_reviewer.py` — module docstring, `_SYSTEM` string naming the agent (must contain the agent's own name for the 7th contract test), `review(diff, scope)` async function delegating to `run_worker`. Prompt templates mirror the structure of `appsec-auditor.md.j2`.

**Test before `stg refresh`**:
```bash
python3 tests/test_review_workers.py    # RED first; GREEN after files added (7 tests × 4 = 28 new assertions)
python3 tests/test_review_roster.py     # roster now has 7 entries; update skeleton test expectation
python3 hooks/test_requirements.py      # framework suite green
```

---

#### P4 — `step-18c-workers-batch2`
**Files** (10 files):
- `hooks/lib/llm/workers/comment_analyzer.py` (new)
- `hooks/lib/llm/workers/code_simplifier.py` (new)
- `hooks/lib/llm/workers/tenant_isolation_auditor.py` (new)
- `hooks/lib/llm/workers/compliance_auditor.py` (new)
- `hooks/lib/llm/prompts/comment-analyzer.md.j2` (new)
- `hooks/lib/llm/prompts/code-simplifier.md.j2` (new)
- `hooks/lib/llm/prompts/tenant-isolation-auditor.md.j2` (new)
- `hooks/lib/llm/prompts/compliance-auditor.md.j2` (new)
- `tests/test_review_workers.py` (extend `WORKERS` list: +4 more entries; total 10)
- `hooks/lib/llm/workers/rosters.py` (edit: add final 4 entries; roster now returns full 11)

**Test before `stg refresh`**:
```bash
python3 tests/test_review_workers.py    # GREEN: 10 workers × 7 tests = 70 assertions
python3 tests/test_review_roster.py     # GREEN: roster returns exactly 11; update assertion to 11
python3 hooks/test_requirements.py      # framework suite green
```

---

#### P5 — `step-18c-renderer`
**Files** (2 files):
- `hooks/lib/llm/render.py` (new)
- `tests/test_render.py` (new)

**`render_review_markdown(report: ReviewReport) -> str`** produces ADR-013 format:
- Findings grouped `CRITICAL → IMPORTANT → SUGGESTION`; each severity section only emitted when that severity has findings.
- Each finding: file+line location, description, fix.
- `## Summary` with counts per severity and verdict.
- Verdict rule (exact parity with `/deep-review`): `CRITICAL > 0` → `FIX ISSUES FIRST`; else `IMPORTANT > 5` → `REVIEW RECOMMENDED`; else → `READY`.

**Minimum `test_render.py` assertions**:
1. `CRITICAL > 0` → verdict string contains `FIX ISSUES FIRST`.
2. `CRITICAL = 0, IMPORTANT > 5` → `REVIEW RECOMMENDED`.
3. `CRITICAL = 0, IMPORTANT ≤ 5` → `READY`.
4. Empty findings → `READY` (edge case guard).
5. Severity ordering: CRITICAL section appears before IMPORTANT before SUGGESTION.
6. ADR-013 section headers present (`## Summary`; severity headers only when findings exist).

**Test before `stg refresh`**: `python3 tests/test_render.py` RED → GREEN; framework suite green.

---

#### P6 — `step-18c-tool-gate`
**Files** (2 files):
- `hooks/lib/llm/tool_gate.py` (new)
- `tests/test_tool_gate.py` (new)

**`run_tool_gate(files: list[str]) -> list[str]`**: runs `ruff check` and `pyright` on `.py` files only; returns CRITICAL error strings. A missing linter is a hard error, not a silent skip (loud-smoke-spikes rule). Non-Python files and empty file list → return `[]` immediately.

**Minimum `test_tool_gate.py` assertions (all mock subprocess)**:
1. Clean files → `[]`.
2. `ruff` error → error string in result.
3. `pyright` error → error string in result.
4. No `.py` files → `[]` (no subprocess called).
5. Missing linter (`FileNotFoundError`) → error string returned (fail-loud).
6. Empty list → `[]`.

**Test before `stg refresh`**: `python3 tests/test_tool_gate.py` RED → GREEN; framework suite green.

---

#### P7 — `step-18c-entry-and-command`
**Files** (6 files — all in one patch per project rule on plugin.json):
- `hooks/lib/llm/review_cli.py` (new) — entry: read `/tmp/review.diff` + `/tmp/review_scope.txt` → `run_tool_gate` → `fanout_review(diff, scope, workers=review_workers())` → `render_review_markdown` → print + session footer; exit 0 on success (verdict in text, not exit code)
- `plugins/requirements-framework/scripts/v3-review` (new) — `set -euo pipefail`; locates `review_cli.py` via deployed (`$HOME/.claude/hooks/lib/llm/review_cli.py`) or repo path; hard-fails (`exit 3`) if not found; passes `$@` to `python3`
- `plugins/requirements-framework/commands/v3-review.md` (new) — static: `allowed-tools: ["Bash"]`; shells to `${CLAUDE_PLUGIN_ROOT}/scripts/v3-review "$ARGUMENTS"`
- `plugins/requirements-framework/commands/v3-review.md.j2` (new) — same content as `.md`
- `hooks/auto-satisfy-skills.py` (edit) — add `'requirements-framework:v3-review': 'pre_pr_review'` to `DEFAULT_SKILL_MAPPINGS`
- `plugins/requirements-framework/.claude-plugin/plugin.json` (edit) — bump `4.6.0 → 4.7.0` (minor: new user-facing command); add `v3-review` to `commands` list

**Ordering hazard**: must follow P2 (rosters), P3 (batch1), P4 (batch2), P5 (renderer), P6 (tool-gate). All `review_cli.py` imports must resolve.

**Test before `stg refresh`**:
```bash
python3 hooks/test_requirements.py      # framework suite; covers auto-satisfy mapping
# The command-loading test (if it exists) must not error on the new v3-review command.
# Smoke (manual, NOT in unit suite):
#   /v3-review <narrow-range>   →  expect ADR-013 output + session_id line
```

---

#### P8 — `step-18c-housekeeping`
**Files** (1–3 files depending on what `update-plugin-versions.sh` touches):
- Any `git_hash` changes emitted by `./update-plugin-versions.sh`
- Memory file `refactor-current-status.md` updated to mark Step 18c complete

**Test before `stg refresh`**:
```bash
./update-plugin-versions.sh --verify    # must exit 0
python3 hooks/test_requirements.py      # framework suite green
./sync.sh status                        # note result in commit message; deploy if needed
```

---

### Full 9-patch stack (including P1 already applied)

| # | stg patch name | Files (approx) | Key test |
|---|---|---|---|
| P1 | `step-18c-plan-docs` | plan + ADR | framework suite |
| P2 | `step-18c-rosters-scaffold` | `rosters.py` + skeleton test | `test_review_roster.py` (3-entry) |
| P3 | `step-18c-workers-batch1` | 4 workers + 4 prompts + test edits + roster edit | `test_review_workers.py` (28 new) |
| P4 | `step-18c-workers-batch2` | 4 workers + 4 prompts + test edits + roster edit | `test_review_workers.py` (70 total) |
| P5 | `step-18c-renderer` | `render.py` + `test_render.py` | `test_render.py` (6+ assertions) |
| P6 | `step-18c-tool-gate` | `tool_gate.py` + `test_tool_gate.py` | `test_tool_gate.py` (6+ assertions) |
| P7 | `step-18c-entry-and-command` | `review_cli.py` + script + command × 2 + auto-satisfy + `plugin.json` | framework suite + smoke |
| P8 | `step-18c-housekeeping` | version hashes + memory | `--verify` + framework suite |
