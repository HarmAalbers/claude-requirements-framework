# Step 16b — Jinja2 plugin agents (25 files, build-time render)

> **For Claude:** REQUIRED SUB-SKILL: Use `requirements-framework:executing-plans`
> to implement this plan task-by-task.

**Goal:** Convert all 25 `plugins/requirements-framework/agents/*.md` files to
`.md.j2` source + rendered `.md` siblings, using build-time Jinja2 partials
authored in Step 16 plus 5 new partials to eliminate duplicated review safety
/ severity / output-format / CLAUDE.md-loading / critical-rules vocabulary.

**Architecture:** Plugin agents are static text (no runtime variables). They
go through `scripts/render_prompts.py` (build-time renderer landed in Step
16), which uses the shared `hooks/lib/llm/templates.py` engine. Partials live
under `hooks/lib/llm/prompts/partials/` (Jinja2 `FileSystemLoader` root) and
are `{% include %}`'d. `StrictUndefined` becomes a guardrail: any leftover
`{{ runtime_var }}` blows up at render, signalling the file doesn't belong in
the plugin tree.

**Tech Stack:** Jinja2 3.x (already in `[llm]` extras), Python 3.10+, Stacked
Git for atomic patches, existing `update-plugin-versions.sh` (taught about
`.md.j2`), existing `sync.sh deploy` (already invokes `render_prompts.py`).

---

## Why now

Step 16 phase 1 landed the engine, the renderer, the partials library, and
the sync.sh hook with **zero plugin `.md.j2` files** — it was deliberate
plumbing-without-content so Step 16b is pure migration. Without 16b the
render-script invocation in `sync.sh` is dead-code-eligible. The 25 plugin
agents are the highest-leverage target: heavy duplication across the 13
diff-scope review agents (boilerplate `prepare-diff-scope` boot, severity
vocabulary, output-format template, CLAUDE.md loading).

Step 16c (11 commands + 21 skills) will follow on the same engine. Step 20
(Sonnet pinning eval iteration) and any future per-prompt experimentation
become tractable once the duplicated vocabulary is centralized.

## Scope decisions (locked 2026-05-24)

| Question | Decision |
| --- | --- |
| Partial extraction depth | **Aggressive.** Up to 5 new partials on top of Step 16's two: `diff_scope_load`, `severity_vocabulary`, `review_output_format`, `claude_md_loading`, `critical_rules_tail`. Authored from the largest common denominator across qualifying agents — agents whose text deviates keep that block inline. |
| Partial location | `hooks/lib/llm/prompts/partials/` (same dir as Step 16's `safety.j2` + `project_conventions.j2`). The `FileSystemLoader` in `templates.py` is anchored there, so `{% include 'partials/X.j2' %}` resolves identically for V3 worker prompts and plugin agents. |
| `git_hash` source-of-truth | **`.md.j2` source files own `git_hash`.** `update-plugin-versions.sh` is taught to scan `.md.j2`, skip `.md` files that have a `.md.j2` sibling (derived artifact), and re-invoke `scripts/render_prompts.py` at the end so rendered `.md` siblings track the updated source. |
| Migration cadence | **One atomic `stg` patch per agent** — 25 conversion patches. Easy to bisect and revert any one regression; verifiable byte-identical render per patch. Adds review fatigue but mechanical refactors stay readable patch-by-patch. |
| Acceptance signal | **Byte-identical rendered `.md` vs. pre-conversion `.md`** (whitespace-only diff at include boundaries tolerated and documented). Treat conversion as a strict refactor: zero semantic change. Verified per-agent before its commit lands. |
| Marketplace distribution | Unchanged from Step 16 — both `.md.j2` AND rendered `.md` committed. `marketplace.json:source` → `./plugins/requirements-framework` reads `.md` directly. |
| Branching | Stack on `refactor/step-08-llm-package-scaffold` (continues Step 13–18 pattern). |
| Plugin version bump | 4.4.0 → 4.5.0 (minor — additive: rendered output identical, but source format changes are user-visible to anyone reading the plugin tree). |

## Partial design (the 5 new partials)

Each partial extracts the **largest text kernel that appears byte-identically
across N qualifying agents**. If an agent's wording deviates even by one
word, that agent keeps the block inline — we never edit an agent's
substantive text to fit a partial. The acceptance gate is byte-identical
rendered output, so the partial must match exactly.

### 1. `diff_scope_load.j2`

Extracts the **identical opening boilerplate** that 13 diff-scope review
agents use to load review scope (verified via grep — block is ~7 lines of
prose between a `## Step 1: Load Review Scope` header and the agent's first
custom paragraph).

**Qualifying agents** (confirmed via grep of `prepare-diff-scope`): appsec-auditor,
backward-compatibility-checker, code-reviewer, code-simplifier,
codex-review-agent, comment-analyzer, compliance-auditor, frontend-reviewer,
silent-failure-hunter, tenant-isolation-auditor, test-analyzer,
tool-validator, type-design-analyzer.

**Excluded** (any agent whose Step 1 deviates — verified case-by-case during
conversion): plan validators (read a plan file, not a diff), refactor
agents, specialty agents.

### 2. `severity_vocabulary.j2`

The smallest kernel of severity wording shared verbatim. Likely just a
one-line reminder + the three-bullet definition block. Verified
case-by-case during conversion. If full classification blocks differ
agent-to-agent (likely), this partial drops to a short shared kernel and
the per-agent definitions stay inline.

### 3. `review_output_format.j2`

The `# Code Review / ## Files Reviewed / ## Findings / ## Summary` markdown
template at the tail of diff-scope review agents. Author from the kernel that
appears in code-reviewer; mark per-agent variations during conversion. If
agents diverge meaningfully (different field names, extra sections), the
partial is downsized to just the `## Summary` block.

### 4. `claude_md_loading.j2`

The `## Step 2: Load Project Guidelines` block ("Check CLAUDE.md, then
.claude/CLAUDE.md, then README..."). 5 agents grep-match — verify byte-
identical match per agent during conversion.

### 5. `critical_rules_tail.j2`

The `## Critical Rules` section at the bottom of review agents — "Be
precise / specific / actionable / thorough / filter aggressively". Author
from the most-common kernel; conservatively skip agents that deviate.

### Partial discoverability rule

If a partial's kernel doesn't byte-match for an agent, that agent **keeps
the block inline** rather than being force-fit. The acceptance gate
(byte-identical rendered output) prevents drift. We expect **between 3 and
5 partials to land** — final count discovered empirically during
conversion. Documented in Step 16b's housekeeping patch.

## Files touched

| File | Action | Note |
| --- | --- | --- |
| `.claude/plans/variant3/16b-jinja2-plugin-agents.md` | **new** | This document — Patch 1 |
| `hooks/lib/llm/prompts/partials/diff_scope_load.j2` | **new** | Patch 2 |
| `hooks/lib/llm/prompts/partials/severity_vocabulary.j2` | **new** (if kernel exists) | Patch 2 |
| `hooks/lib/llm/prompts/partials/review_output_format.j2` | **new** (if kernel exists) | Patch 2 |
| `hooks/lib/llm/prompts/partials/claude_md_loading.j2` | **new** (if kernel exists) | Patch 2 |
| `hooks/lib/llm/prompts/partials/critical_rules_tail.j2` | **new** (if kernel exists) | Patch 2 |
| `tests/test_partials.py` (or extend `tests/test_partials.py` from Step 16 if it exists) | **new/edit** | Patch 2 — verify each partial renders cleanly + matches its kernel + boundary newline tests + nonexistent-partial negative test + ADR-013 structural conformance test for one qualifying agent (synthesis additions) |
| `tests/test_render_prompts.py` | **new** | Patch 2 — codex Q3/Q5 — covers `render_prompts.py` CLI modes (render, dry-run, check-fresh, check-stale) + error paths (missing include, undefined variable) + zero-variable build-time contract for plugin templates |
| `update-plugin-versions.sh` | **edit** | Patch 3 — scan `.md.j2`, skip derived `.md`, re-invoke `render_prompts.py` |
| `plugins/requirements-framework/agents/<name>.md.j2` | **new** × 25 | Patches 4..28 — one per agent |
| `plugins/requirements-framework/agents/<name>.md` | **rewritten** × 25 | Patches 4..28 — rendered from `.md.j2`, byte-identical to pre-conversion |
| `plugins/requirements-framework/.claude-plugin/plugin.json` | **edit** | Patch 29 — bump 4.4.0 → 4.5.0 |
| `CHANGELOG.md` | **edit** | Patch 29 — append v4.5.0 entry |
| Memory `refactor-current-status.md` | **edit** | Patch 29 — mark Step 16b done, bump date |

## Patch breakdown (29 atomic patches)

| # | Patch name | Files |
| --- | --- | --- |
| 1 | `step-16b-plan-rewrite` | This plan document |
| 2 | `step-16b-partials` | 1-5 new `partials/*.j2` + test extensions |
| 3 | `step-16b-update-plugin-versions` | `update-plugin-versions.sh` + smoke run |
| 4 | `step-16b-convert-code-reviewer` | **Pilot** — `agents/code-reviewer.md.j2` + rendered `.md` |
| 5..15 | `step-16b-convert-<diff-scope-agent>` × 11 | Remaining 11 diff-scope reviewers (alphabetical): appsec-auditor, backward-compatibility-checker, code-simplifier, codex-review-agent, comment-analyzer, compliance-auditor, frontend-reviewer, silent-failure-hunter, tenant-isolation-auditor, test-analyzer, tool-validator |
| 16..19 | `step-16b-convert-<plan-validator>` × 4 | solid-reviewer, tdd-validator, adr-guardian, refactor-advisor |
| 20..22 | `step-16b-convert-<refactor-agent>` × 3 | refactor-executor, refactor-investigator, refactor-analyzer |
| 23..27 | `step-16b-convert-<specialty-agent>` × 5 | commit-planner, comment-cleaner, import-organizer, session-analyzer, codex-arch-reviewer |
| 28 | `step-16b-convert-type-design-analyzer` | type-design-analyzer — 13th diff-scope agent; fills the slot that was erroneously labelled `codex-review-agent` (already in 5..15). Total: 13 diff-scope (code-reviewer patch 4 + 11 in 5..15 + type-design-analyzer here). |
| 29 | `step-16b-housekeeping` | plugin bump, CHANGELOG, memory update, plugin-versions re-run, sync.sh deploy, test suite, **pre-commit hook wiring** (`render_prompts.py --check`), **DEVELOPMENT.md note** on `.md.j2` source-of-truth, **README inline note** on plugin template contract, deferred-items list (ADR amendments — see Synthesis Outcomes) |

## Per-agent migration procedure (Patches 4..28)

Apply this **identical** 7-step recipe per agent. Each step is one action.

**Files involved per agent:**
- Read: `plugins/requirements-framework/agents/<name>.md`
- Create: `plugins/requirements-framework/agents/<name>.md.j2`
- Verify-rewrite: `plugins/requirements-framework/agents/<name>.md`

### Step 1: Snapshot the original

```bash
cp plugins/requirements-framework/agents/<name>.md /tmp/<name>.md.snapshot
```

### Step 2: Author the `.md.j2` source

Author `agents/<name>.md.j2` from the snapshot:

- **Copy YAML frontmatter verbatim**, including current `git_hash`.
- For each candidate partial (`diff_scope_load`, `severity_vocabulary`,
  `review_output_format`, `claude_md_loading`, `critical_rules_tail`):
  diff the agent's corresponding block against the partial kernel. If
  byte-identical match, replace with `{% include 'partials/<name>.j2' %}`.
  If not, leave the block inline.
- All other content copied verbatim (no rewording, no normalization).

### Step 3: Render and capture rendered output

```bash
python3 scripts/render_prompts.py
```

Expected: single line `✓ agents/<name>.md.j2 → <name>.md` with no errors.
Other agents (not yet converted) are unaffected; the script only re-renders
files whose source exists.

### Step 4: Byte-identical render check

**4a — Render-side check** (uses the same comparison path as the
pre-commit hook landing in Patch 29):

```bash
python3 scripts/render_prompts.py --check
```

Expected: `OK: all N rendered file(s) are fresh.` Exit 0.

**4b — Snapshot-vs-rendered check** (catches first-render whitespace
wrongness that `--check` cannot detect — `--check` only compares the
file against itself):

```bash
diff /tmp/<name>.md.snapshot plugins/requirements-framework/agents/<name>.md
```

Expected: empty output, or whitespace-only diff at `{% include %}` boundaries.

**4c — Frontmatter key completeness** (closes the silent-default risk
flagged by tdd-validator Gap 4 — agents with non-standard `tools:` /
`model:` overrides are the highest-risk subset):

```bash
python3 -c "
import re
a = set(re.findall(r'^(\w[\w_-]*):', open('/tmp/<name>.md.snapshot').read(), re.M))
b = set(re.findall(r'^(\w[\w_-]*):', open('plugins/requirements-framework/agents/<name>.md').read(), re.M))
assert a == b, f'frontmatter key mismatch: {a.symmetric_difference(b)}'
print('frontmatter keys match')
"
```

**If 4a/4b/4c fail:**
- Identify the diverging block.
- Either: shrink the partial's kernel to a smaller byte-identical core, or:
  drop the partial for this agent and keep the block inline.
- Re-render and re-check. Iterate until clean.

### Step 5: Live smoke (pilot only — Patch 4) + targeted spot-checks

For the **pilot agent (code-reviewer)** only, run the agent end-to-end:

```bash
claude --plugin-dir ~/Tools/claude-requirements-framework/plugin
# In session: invoke code-reviewer against a small staged diff
# Expected: output structurally identical to baseline (manually compared)
```

**Additional targeted checks** (adr-guardian Finding 5 — ADR-014):
when converting the three refactor agents (`refactor-executor`,
`refactor-investigator`, `refactor-analyzer`), confirm that any
model-tier pinning prose lives in the agent **body** and not in YAML
frontmatter. The byte-identical render gate covers the body; if model
tiers were declared in frontmatter, Step 4c (key completeness) would
catch a drop. Quick check at conversion time: grep the snapshot for
`Haiku|Sonnet` and confirm hits appear below the closing `---` of the
frontmatter block.

This is a one-time smoke for the pilot; agents 5..28 rely on the byte-
identical render gate (Step 4 sub-steps a/b/c) since rendered `.md` is
what Claude Code dispatches.

### Step 6: Stg-commit

```bash
stg new step-16b-convert-<name>
git add plugins/requirements-framework/agents/<name>.md.j2 \
        plugins/requirements-framework/agents/<name>.md
stg refresh
```

Patch description (single-line, follows commit convention):
```
feat(step-16b): convert <name> agent .md → .md.j2 with partials
```

**Note on `git_hash: uncommitted`** (commit-planner IMPORTANT): each
`.md.j2` source lands with `git_hash: <copied-from-original-md>` (not
its own hash — it's a brand-new file). Patches 4..28 will therefore
ship with a stamping mismatch: the rendered `.md` carries the source
agent's last-commit hash, but the new `.md.j2` source has not yet been
seen by `update-plugin-versions.sh`. This is **intentional and fixed
in Patch 29** via `./update-plugin-versions.sh` (which Patch 3 teaches
about `.md.j2`). Do **not** run `update-plugin-versions.sh
--only-changed` per agent — it would inflate every patch with a hash
update and obscure the conversion diff.

### Step 7: Cleanup

```bash
rm /tmp/<name>.md.snapshot
```

Update memory `refactor-current-status.md` only at the housekeeping patch
(29), not per-agent.

## Acceptance

- [ ] All 25 `.md.j2` sources created; `scripts/render_prompts.py` exits 0.
- [ ] All 25 rendered `.md` files byte-identical (or whitespace-only diff)
      against pre-conversion snapshots. Whitespace-only diffs documented
      in the housekeeping patch's commit body.
- [ ] `python3 scripts/render_prompts.py --check` exits 0 (no drift).
- [ ] `./update-plugin-versions.sh --verify` exits 0 (all `.md.j2`
      git_hash fields current).
- [ ] `./sync.sh deploy` runs cleanly and copies all rendered `.md` files.
- [ ] `python3 hooks/test_requirements.py` passes (1290+ tests, unchanged).
- [ ] `python3 tests/test_partials.py` passes (covers new partials +
      boundary tests + no-vars contract + nonexistent-partial negative +
      ADR-013 structural conformance for one qualifying agent).
- [ ] `python3 tests/test_render_prompts.py` passes (4 CLI modes + error
      paths + zero-var plugin contract).
- [ ] Pilot smoke: `code-reviewer` invocation via `claude --plugin-dir`
      produces output structurally indistinguishable from pre-conversion.
- [ ] Plugin version bumped 4.4.0 → 4.5.0; CHANGELOG v4.5.0 entry written
      with explicit "source format change only; rendered output is
      byte-identical" wording (adr-guardian Finding 4).
- [ ] DEVELOPMENT.md (or equivalent) gains a "Plugin agent authoring"
      section noting `.md.j2` is source of truth; rendered `.md` must
      not be hand-edited (compat-checker Finding 3).
- [ ] `plugins/requirements-framework/README.md` gains an inline note
      on the `.md.j2` → `.md` contract (codex Finding Q3).
- [ ] Pre-commit hook wired in Patch 29: `render_prompts.py --check`
      runs against `*.md.j2` and `*.j2` files (tdd-validator Gap 3 +
      refactor-advisor Finding 5 — agreed at synthesis).
- [ ] Memory `refactor-current-status.md` updated.

## Rollback

Per-patch atomic via `stg pop`. The most-reversible single change: keep
all `.md.j2` source files but flip the partial includes back to inlined
content (lose the dedup benefit; rendered `.md` stays byte-identical).

If an entire partial design proves wrong (e.g., `review_output_format`
breaks down across agents), `stg delete step-16b-convert-<name>` for
affected patches and re-author from the snapshot.

If the build pipeline itself regresses (`render_prompts.py` or sync.sh
bug surfaced during a conversion), `stg pop` back to Patch 3 and fix the
pipeline before resuming conversions.

## Effort

Realistic estimate: **2-3 days** across multiple sessions.

- Patch 1 (plan): 30 min — this document.
- Patch 2 (partials): 1.5h — authoring + tests + verifying kernels.
- Patch 3 (update-plugin-versions.sh): 45 min — edit + smoke.
- Patches 4..28 (25 conversions): ~25 min per agent average = 10h
  total. Pilot (code-reviewer) takes longer (~1h) including smoke.
  Subsequent agents reuse the procedure verbatim and run faster.
- Patch 29 (housekeeping): 30 min.

## Depends on

- **Step 16** (engine + `render_prompts.py` + sync.sh hook + initial
  partials) — landed as 8 stacked patches.
- **No other dependencies.** Plugin agents have zero runtime variables;
  no Step 17/18/etc. requirements bind.

## Honest scope notes

- **Partial-count uncertainty is real.** The plan commits to "up to 5
  partials" but the byte-identical gate may force us down to 3 or 4 if
  agents' text deviates more than greps suggest. We discover this during
  Patches 4-10 and document the final count in housekeeping.

- **Whitespace handling at `{% include %}` boundaries is fiddly.** Jinja2
  preserves all whitespace by default (no `trim_blocks` / `lstrip_blocks`),
  but the partial file's leading/trailing newlines combine with the
  include-statement-line newline. Authors must end partials without
  trailing newlines (or with one specific count) to match the inline
  original. Empirical iteration during Patch 2 will pin this down.

- **YAML frontmatter ordering matters for `git_hash` placement.** The
  `update_file_hash` Python in `update-plugin-versions.sh` appends
  `git_hash` after the last field if not present. New `.md.j2` sources
  must preserve the same field order as the original `.md` to avoid
  whitespace-only diffs that could mask real ones.

- **Pre-commit hook lands in Patch 29 (housekeeping)** — reversed during
  /arch-review synthesis after tdd-validator (HIGH) and refactor-advisor
  (LOW) independently converged on the same recommendation: do **not**
  split it into a separate `step-16b-precommit-hook` patch. The hook is
  ~15 lines; conversion patches 4..28 are protected per-agent by Step
  4a (`render_prompts.py --check`); landing the hook in Patch 29
  catches future partial-edit drift across all 25 agents in one shot.

- **Cross-tree partial dependency is intentional, documented here, and
  not (yet) covered by an ADR** — plugin agents under
  `plugins/requirements-framework/agents/` `{% include %}` partials
  living under `hooks/lib/llm/prompts/partials/`. The
  `FileSystemLoader` anchor in `templates.py` makes this transparent.
  The coupling is build-time only (partials are pure text data, no
  Python imports), so it is safe — but it is also load-bearing if
  anyone refactors `hooks/lib/llm/` later. The Synthesis Outcomes
  section below tracks the ADR amendment as a Patch 29 deferred item.

- **Langfuse mirror not extended in this step.** Step 16 already taught
  `scripts/sync_prompts_to_langfuse.py` about `.md.j2`. That sync was for
  V3 worker prompts loaded via `load_prompt()`. Plugin agents are NOT
  loaded via `load_prompt()` — they're dispatched by Claude Code from
  the rendered `.md`. So no Langfuse work needed.

- **Plugin marketplace caching of `.md` is unaffected.** Users on
  `/plugin install requirements-framework` continue to receive the
  rendered `.md` files committed alongside `.md.j2` sources, identical
  to what they had pre-conversion (byte-identical gate).

- **No new requirements config changes.** Step 16b touches plugin agent
  source format only — no new `requirements.yaml` keys, no new hooks,
  no behavior changes that need configuration.

- **Tests for the conversion itself**: the byte-identical render gate
  is the **primary** test (we don't duplicate rendered `.md` content as
  fixtures). The /arch-review team added five supporting tests in
  Patch 2 to make the gate reliable across the 25-patch lifecycle: (1)
  boundary-newline tests per partial, (2) no-vars contract per partial,
  (3) nonexistent-partial negative test, (4) one ADR-013 structural
  conformance test (verifies a qualifying agent still emits `###
  CRITICAL:` H3 prefixes + `## Summary` verdict line — guards against
  partial-edit drift breaking ADR-013 regex parsing for all sharing
  agents at once), (5) `tests/test_render_prompts.py` covering all 4
  CLI modes + error paths + zero-var build-time contract. These are
  guards on the gate, not replacements.

## Testing Strategy

### Summary verdict

The byte-identical render gate is **necessary but not sufficient**. Three gaps
exist; two are low-cost to close in 16b itself.

---

### Gap 1 — Whitespace at `{% include %}` boundaries (MEDIUM severity)

**Risk:** `render_prompts.py --check` compares rendered output against the
`.md` file that's already on disk. If the first render produces a
whitespace-wrong output (extra or missing `\n` at include boundary) and that
output is committed as the `.md` sibling, `--check` always passes — it's
comparing the file against itself.

**Recommendation (Patch 2):** Add negative tests to `tests/test_partials.py`
that assert include boundaries produce *exactly* the expected newline count.
For each new partial, add one test with the include at the start of a line and
one at the end of a body paragraph. Pin the expected character-level output,
not just substring presence.

```python
def test_diff_scope_load_boundary_newlines(r):
    out = templates.render("BEFORE\n{% include 'partials/diff_scope_load.j2' %}\nAFTER")
    # Exactly one blank line between BEFORE and partial content
    assert out.startswith("BEFORE\n"), repr(out[:20])
```

**Patch to add this:** Patch 2 (`step-16b-partials`).

---

### Gap 2 — Static-partial contract (no runtime vars) (LOW severity, easy to close)

**Risk:** A partial that accidentally introduces `{{ some_var }}` will blow up
at render time for every agent that includes it — but only discovered when
`render_prompts.py` is run, not at partial-authoring time.

**Recommendation (Patch 2):** For each new partial, add an explicit test:

```python
def test_diff_scope_load_needs_no_caller_vars(r):
    try:
        templates.render("{% include 'partials/diff_scope_load.j2' %}")
        r.test("diff_scope_load needs no caller vars", True)
    except Exception as exc:
        r.test("diff_scope_load needs no caller vars", False, str(exc))
```

This mirrors the existing pattern for `safety.j2`. Covers `StrictUndefined`
blowing up on accidentally-included template vars.

---

### Gap 3 — Pre-commit hook deferral (HIGH severity)

**Risk:** The plan defers wiring `render_prompts.py --check` as a pre-commit
hook to a follow-up patch. This means the entire 25-patch migration runs
without CI enforcement of the render gate. Any agent whose `.md` drifts from
its `.md.j2` after an edit (e.g., fixing a typo in the partial later) will
silently pass all checks until someone manually runs `--check`.

**Recommendation:** Land the pre-commit hook in **Patch 29 (housekeeping)**,
not a follow-up. The `--check` flag already exists in `render_prompts.py`. The
hook wiring is a one-liner in `.pre-commit-config.yaml` or
`.claude/settings.json`. This is ~15 min of work, not the 30 min originally
estimated for a standalone patch.

```yaml
# .pre-commit-config.yaml (or equivalent hook config)
- id: render-prompts-check
  name: Check rendered prompts are fresh
  entry: python3 scripts/render_prompts.py --check
  language: python
  pass_filenames: false
  files: \.(md\.j2|j2)$
```

If the pre-commit wiring is genuinely deferred, document it as a **known
follow-up** in the housekeeping patch body and create a tracking issue or
task, so it doesn't silently disappear.

---

### Gap 4 — YAML frontmatter key completeness (LOW severity)

**Risk:** Patches 5–28 skip live smoke. If a copy-paste error in `.md.j2`
drops a frontmatter field that Claude Code silently defaults (e.g., `model:`,
`tools:`), the byte-identical gate catches it — but only if the snapshot was
taken correctly before conversion. Agents with `tools:` or `model:` overrides
are the highest-risk subset.

**Recommendation (per-agent procedure, Step 4 augmentation):** After the
byte-diff, add a one-liner frontmatter key check:

```bash
python3 -c "
import re, sys
a = set(re.findall(r'^(\w[\w_-]*):', open('/tmp/<name>.md.snapshot').read(), re.M))
b = set(re.findall(r'^(\w[\w_-]*):', open('plugins/requirements-framework/agents/<name>.md').read(), re.M))
assert a == b, f'frontmatter key mismatch: {a.symmetric_difference(b)}'
print('frontmatter keys match')
"
```

This is a 30-second addition to the per-agent procedure and closes the
silent-default risk for agents with non-standard frontmatter.

---

### Gap 5 — `tests/test_partials.py` missing "nonexistent partial" negative test (LOW severity)

**Risk:** There is no test confirming that including a nonexistent partial
raises `TemplateNotFound` (rather than silently returning empty). This matters
because a typo in a `{% include 'partials/typo.j2' %}` in a `.md.j2` would
produce a render failure that's caught at `render_prompts.py` run time — but
having an explicit test ensures the engine contract is validated independently
of agent content.

**Recommendation (Patch 2):** Add one negative test:

```python
def test_missing_partial_raises(r):
    from jinja2 import TemplateNotFound
    try:
        templates.render("{% include 'partials/does_not_exist.j2' %}")
        r.test("missing partial raises TemplateNotFound", False, "no exception raised")
    except TemplateNotFound:
        r.test("missing partial raises TemplateNotFound", True)
    except Exception as exc:
        r.test("missing partial raises TemplateNotFound", False, f"wrong exception: {exc}")
```

---

### What the byte-identical gate DOES cover (well)

- Semantic content drift (any word change in the rendered output).
- Accidental partial substitution of non-matching text.
- Render failures from `StrictUndefined` (template references a runtime var).
- Stale renders after source edit (when `--check` is run).

The gate is the right primary mechanism. The gaps above are about making it
reliable across the 25-patch lifecycle, not replacing it.

---

## SOLID Considerations

### SRP — CONCERN (IMPORTANT)

`critical_rules_tail.j2` as named mixes two distinct conceptual chunks:

1. **Verdict policy** — "Filter aggressively", "Be thorough", "quality over quantity" — meta-guidance about how to weigh findings and form a verdict.
2. **Output style** — "Be precise", "Be specific", "Be actionable" — prose style rules about how to phrase findings.

Grounding: `code-reviewer.md` lines 207–212 show all five bullet points in one `## Critical Rules` block. Meanwhile `tenant-isolation-auditor.md` and `appsec-auditor.md` each have **domain-specific** `## Critical Rules` that replace the generic precision/specificity bullets ("Zero tolerance for data leakage", "Think like an attacker"). The byte-identical gate already forces those agents to keep their block inline — but for the ~8 generic-rules agents, a shared partial that bundles verdict policy with style guidance creates a block an agent can't partially override later without dropping the whole include.

**Action**: In Patch 2, rename to `review_critical_rules_generic.j2` and confirm its kernel covers only the 5-bullet generic set; document which agents qualify.

---

### OCP — CONCERN (SUGGESTION)

`review_output_format.j2` is authored from `code-reviewer`'s `# Code Review / ## Files Reviewed / ## Findings / ## Summary` structure. `backward-compatibility-checker.md` already uses `# Backward Compatibility Analysis` as its top-level header — a different format — and will keep its output block inline. As the plugin grows, agents with non-standard output headers accumulate inline output-format boilerplate outside the partial set.

**Action**: During Patch 2 authoring, consider narrowing the kernel to just the `## Findings / ## Summary` skeleton (omitting the `# <Title>` line), so future agents with custom titles still reuse the structural tail.

---

### DIP — ACCEPTABLE (no action required)

The `plugin/ → hooks/lib/llm/prompts/partials/` dependency is intentional and build-time only: partials are pure text data with no Python imports; Claude Code dispatches rendered `.md` files that have zero dependency on `hooks/`. Acceptable. Consider documenting this assumption in `render_prompts.py` for future contributors who might move partials.

---

### ISP — CONCERN (SUGGESTION)

Each partial is independently includable — correct. One risk: `safety.j2` line 7 already contains `Severity vocabulary: CRITICAL / IMPORTANT / SUGGESTION...`. If `severity_vocabulary.j2` covers similar ground, agents including both partials get duplicated severity guidance.

**Action**: During Patch 2, compare `severity_vocabulary.j2` kernel against `safety.j2:7`. Either (a) remove the severity line from `safety.j2` for V3 worker prompts, or (b) drop `severity_vocabulary.j2` and note that `safety.j2` already covers it.

---

### Summary table

| Principle | Verdict | Severity | Blocking? |
|-----------|---------|----------|-----------|
| SRP | `critical_rules_tail.j2` mixes verdict policy + style guidance; domain-specific agents already deviate | IMPORTANT | No — byte-identical gate prevents misapplication; rename + scope-doc in Patch 2 |
| OCP | `review_output_format.j2` top-level title coupling limits reuse by future agents | SUGGESTION | No — narrow kernel to `## Findings/Summary` skeleton during Patch 2 |
| DIP | `plugin/ → hooks/lib/` dependency is intentional, build-time only | Acceptable | No |
| ISP | `severity_vocabulary.j2` may duplicate `safety.j2:7` for agents using both | SUGGESTION | No — verify during Patch 2; deduplicate |

---

## Related artifacts

- `.claude/plans/variant3/16-jinja2-prompt-templates.md` — Step 16 phase 1
  (engine + V3 prompts + plumbing). Author of partials precedent.
- `hooks/lib/llm/templates.py` — Jinja2 engine (`StrictUndefined`,
  `FileSystemLoader` anchored at `prompts/`).
- `scripts/render_prompts.py` — build-time renderer used by sync.sh and
  (future) pre-commit.
- `update-plugin-versions.sh` — plugin git_hash management.
- `sync.sh` — already invokes `render_prompts.py` before copying plugin
  files; no edit needed in 16b.
- Memory `[[refactor-current-status]]` — gets the "Step 16b done" mark
  in housekeeping.
- Memory `[[refactor-vision-and-roadmap]]` — unchanged.

---

## Preparatory Refactoring

Analysis performed 2026-05-24 against the current `refactor/step-08-llm-package-scaffold`
branch (all 25 `.md` files, `update-plugin-versions.sh`, `scripts/render_prompts.py`,
`tests/test_partials.py`, `hooks/lib/llm/templates.py`).

---

### Finding 1 — `update-plugin-versions.sh`: three hardcoded `find -name "*.md"` loops will stamp `git_hash` on derived artifacts [CRITICAL]

**Lines affected:** 234–246 (`find plugins/requirements-framework/agents/ ... -name "*.md"`,
`find .../commands/ ... -name "*.md"`, `find .../skills/ ... -name "skill.md"`).

**Problem:** Once Patch 3 converts the first agent, `agents/` contains both
`code-reviewer.md.j2` (source) and `code-reviewer.md` (derived, committed). The
current `find -name "*.md"` loop picks up the derived `.md` file, stamps it with
the hash of *that file's* last git commit, and leaves the `.md.j2` source without
a `git_hash` altogether. This defeats the plan's scope decision ("`.md.j2` source
files own `git_hash`") and produces misleading version tracking for the entire
25-agent set.

**Required fix (Patch 3):** Three changes to the discovery loops:

1. **Add a parallel `.md.j2` loop** for agents, commands, and skills — these are the
   source files to stamp.
2. **Skip derived `.md` siblings** — in the existing `*.md` loop, skip any file `foo.md`
   if `foo.md.j2` exists in the same directory.
3. **Re-invoke `render_prompts.py` after stamping** — `update_file_hash` rewrites the
   `.md.j2` frontmatter, which makes the previously-rendered `.md` stale. A final
   `python3 scripts/render_prompts.py` call at the end of `main()` refreshes rendered
   siblings. (This already happens in `sync.sh deploy`; the version script needs
   it too so `--verify` mode sees fresh hashes.)

This is the only change in Patch 3 that is genuinely blocking. Without it, Patches
4–28 (the 25 conversions) will silently mis-stamp every converted agent.

Concrete shell change for the agents discovery block:

```bash
# Source files (.md.j2) — own the git_hash
while IFS= read -r file; do
    [ -f "$file" ] && files+=("$file")
done < <(find plugins/requirements-framework/agents/ github-issues-plugin/agents/ \
             -name "*.md.j2" -type f 2>/dev/null)

# Plain .md files — skip any that have a .md.j2 sibling (derived artifacts)
while IFS= read -r file; do
    [ -f "$file" ] || continue
    [ -f "${file%.md}.md.j2" ] && continue   # skip derived sibling
    files+=("$file")
done < <(find plugins/requirements-framework/agents/ github-issues-plugin/agents/ \
             -name "*.md" -type f 2>/dev/null)
```

Apply the same pattern for the commands and skills loops.

---

### Finding 2 — Python byte-comparison helper vs. shell `diff` for the acceptance check [MEDIUM]

**Question addressed:** Should we extract a Python `compare_byte_identical(snapshot, rendered) -> diff`
helper instead of relying on shell `diff`?

**Conclusion: No new helper needed — but the per-agent procedure should call
`render_prompts.py --check` instead of raw `diff`.**

The plan's Step 4 per-agent procedure calls:
```bash
diff /tmp/<name>.md.snapshot plugins/requirements-framework/agents/<name>.md
```

This works but has two weaknesses:
1. On macOS, `diff` outputs a human-readable unified diff; an implementer might
   misread whitespace-only diffs as non-empty. `render_prompts.py --check` already
   normalises this comparison and exits 1 on any drift.
2. After Patch 3 fixes `update-plugin-versions.sh` to re-render after hash
   stamping, the snapshot-vs-rendered check and the `--check` mode converge on
   the same comparison.

**Recommended change to the per-agent procedure (Step 4):** Replace the shell `diff`
with:
```bash
python3 scripts/render_prompts.py --check
```
This gives a canonical "STALE" / "OK" verdict across all 25 conversions and uses
the same comparison path that the (future) pre-commit hook will use, so behaviour
is consistent.

A dedicated Python `compare_byte_identical()` helper would be overkill — it would
add a function to test only in unit tests, whereas `render_prompts.py --check` is
already the right integration-level tool.

---

### Finding 3 — `diff_scope_load.j2` kernel is provably byte-identical across all 13 agents [MEDIUM — confirms plan assumption]

**Verification:** The 5-line block from `Execute: \`${CLAUDE_PLUGIN_ROOT}/scripts/prepare-diff-scope --ensure\``
through `"No review scope provided" and EXIT.` was extracted from all 13 diff-scope
agents and checksummed:

```
MD5: 09f3eb3c657bc4397091348edbc95e58  (all 13 agents, identical)
```

Agents confirmed: appsec-auditor, backward-compatibility-checker, code-reviewer,
code-simplifier, codex-review-agent, comment-analyzer, compliance-auditor,
frontend-reviewer, silent-failure-hunter, tenant-isolation-auditor, test-analyzer,
tool-validator, type-design-analyzer.

**Implication for Patch 2:** `diff_scope_load.j2` can be authored immediately from
any one agent without per-agent diff verification — the kernel is already proven.
The only whitespace risk is the surrounding `\n` at the include boundary (see
Testing Strategy Gap 1 above).

Note: silent-failure-hunter is confirmed in the list even though its `## Step 1`
header appears at document line 162 (vs. lines 38–44 in most agents) — the block
content itself is byte-identical.

---

### Finding 4 — `test_partials.py` has no boilerplate problem; new partials are 3-line additions [LOW — no action needed]

**Question addressed:** Should we extract a shared loader test fixture to avoid
boilerplate duplication as more partials are added?

**Conclusion: No fixture extraction needed.** The existing `TestRunner` class
in `tests/test_partials.py` (lines 28–51) already provides the shared `r.test()`
pattern. Adding a new partial requires:
1. One `def test_<name>_no_vars_needed(r)` function (~5 lines, mirrors
   `test_safety_partial_no_vars_needed`).
2. One `def test_<name>_content(r)` function (~4 lines, mirrors
   `test_safety_partial_includes`).
3. Two calls in `main()`.

That's ~11 lines of non-repeated code per partial. A fixture abstraction would
save ~3 lines per partial at the cost of indirection — not worth it until the
file grows beyond 6–7 partials.

**What does need a note in Patch 2:** The `test_partials.py` `main()` function
calls each test explicitly (lines 127–133). Patch 2 authors must remember to
register each new test function there — there is no auto-discovery. Add one
comment to `main()` marking the registration block.

---

### Finding 5 — Pre-commit hook: Patch 29 (housekeeping) is the right landing spot [LOW]

**Question addressed:** Is this the right moment to land the `render_prompts.py --check`
pre-commit hook?

**Conclusion: Land it in Patch 29, not a separate follow-up.** The plan already
defers to Patch 29; the analysis confirms this is correct because:

1. There is no `.pre-commit-config.yaml` in the repo today — the pre-commit
   framework is not yet wired at all. The wiring involves either creating
   `.pre-commit-config.yaml` (if using `pre-commit` tool) or adding to
   `sync.sh`'s pre-push/pre-commit path. This is a design decision, not just
   a one-liner.
2. Landing the hook in Patch 3 (before any `.md.j2` files exist in agents/) would
   pass vacuously with "No sources found" — giving false confidence. It's more
   meaningful when Patch 4 (first conversion) is already on the stack.
3. The per-agent procedure already recommends `render_prompts.py --check` as
   the Step 4 acceptance check (see Finding 2). That provides equivalent
   coverage per-patch without a global hook.

**Risk accepted:** Patches 4–28 run without automated drift detection across
the full tree. The per-agent `--check` call in Step 4 mitigates this locally.
Document in Patch 29 that the hook is intentionally deferred, and create a
tracking note so it isn't silently dropped after 16b ships.

---

### Finding 6 — Frontmatter field ordering: two agents deviate; no normalisation needed [LOW]

**Question addressed:** Should `.md` files be normalised for consistent YAML field
ordering before conversion?

**Conclusion: No pre-normalisation needed.** 23 of 25 agents use the ordering
`color → allowed-tools → git_hash` at the bottom of frontmatter.
Two agents (`comment-cleaner.md`, `import-organizer.md`) use
`model → color → git_hash → allowed-tools`. This is an existing inconsistency in
the source files, not something introduced by conversion.

The `update_file_hash` Python embedded in `update-plugin-versions.sh` (lines
138–148) does a regex replace in-place, preserving existing field order. So
`.md.j2` sources that copy frontmatter verbatim from their `.md` originals will
have their existing ordering preserved — no drift risk.

**Only risk:** If a Patch 4–28 author normalises field order while authoring the
`.md.j2`, the rendered `.md` would show a frontmatter-order diff vs. the
pre-conversion snapshot. The byte-identical gate (Step 4) catches this. Explicitly
note in the per-agent procedure: "Copy YAML frontmatter verbatim, including field
ordering — do not reorder fields."

---

### Summary table

| # | Finding | Severity | Patch | Action |
|---|---------|----------|-------|--------|
| 1 | `update-plugin-versions.sh` stamps derived `.md` not `.md.j2` source | **CRITICAL** | Patch 3 | Fix three find loops + add re-render call |
| 2 | Per-agent Step 4 uses shell `diff` instead of `render_prompts.py --check` | MEDIUM | Per-agent procedure | Replace `diff` call in procedure |
| 3 | `diff_scope_load.j2` kernel verified byte-identical across all 13 agents | MEDIUM | Patch 2 | Author directly, no per-agent diff needed |
| 4 | `test_partials.py` needs explicit registration in `main()`; no fixture needed | LOW | Patch 2 | Add one comment to `main()` registration block |
| 5 | Pre-commit hook: Patch 29 is correct deferral point | LOW | Patch 29 | Document intentional deferral, create follow-up note |
| 6 | Frontmatter field ordering: 2 agents deviate; no normalisation needed | LOW | Per-agent procedure | Add "copy verbatim, do not reorder" note |

---

## Synthesis Outcomes (from /arch-review, 2026-05-24)

### Team composition
- **adr-guardian** — ADR compliance review
- **compat-checker** — Breaking change analysis
- **tdd-validator** — Testability assessment (added Testing Strategy section)
- **solid-reviewer** — SOLID principles review (added SOLID Considerations section)
- **refactor-advisor** — Preparatory refactoring (added Preparatory Refactoring section)
- **commit-planner** — Commit strategy validation (fixed Patch 28 ordering bug)
- **codex-arch-reviewer** — External AI architecture analysis (gpt-5.5)

### Cross-validated findings (multi-agent corroboration)

| Region | Agents | Severity (synthesized) | Resolution |
|---|---|---|---|
| `update-plugin-versions.sh` post-conversion behavior | refactor-advisor (CRITICAL) + codex Q2 (IMPORTANT) + adr-guardian #3 (IMPORTANT) | **CRITICAL — triple-corroborated** | Patch 3 must: (a) add `.md.j2` discovery, (b) skip `.md` with `.md.j2` sibling, (c) re-invoke `render_prompts.py` at end of `main()`, (d) apply to all three modes (update / check / verify). Concrete shell snippets in Preparatory Refactoring Finding 1. |
| Pre-commit hook timing | tdd-validator (HIGH) + refactor-advisor (LOW) | **Land in Patch 29** | Both agents converged: do NOT split into separate `step-16b-precommit-hook` follow-up. Per-agent `--check` (Step 4a) mitigates the migration window; Patch 29 hook protects future partial edits. |
| Output-format drift after partials shared | adr-guardian #2 (IMPORTANT) + codex Q5 (IMPORTANT) + tdd-validator Gap 1 (MEDIUM) | **Add 3 tests in Patch 2** | (1) Boundary-newline tests per partial, (2) ADR-013 structural conformance test for one qualifying agent, (3) zero-var plugin contract test in `tests/test_render_prompts.py`. |
| `severity_vocabulary.j2` overlaps `safety.j2:7` | solid-reviewer (ISP) | SUGGESTION | Verify during Patch 2 authoring; either drop `severity_vocabulary.j2` and reference `safety.j2`, or remove the severity line from `safety.j2`. Decision deferred to Patch 2 author based on byte-identical kernel analysis. |
| `critical_rules_tail.j2` mixes verdict policy + style | solid-reviewer (SRP) | IMPORTANT | Rename to `review_critical_rules_generic.j2` during Patch 2; document qualifying agents (the 8 generic-rules agents — appsec/tenant-isolation use domain-specific blocks). |
| `review_output_format.j2` kernel too coupled to `# <Title>` | solid-reviewer (OCP) | SUGGESTION | Patch 2 authoring: narrow kernel to `## Findings / ## Summary` skeleton; drop the `# <Title>` line so future agents with custom titles still reuse the structural tail. |

### Verdict: **APPROVED with mandatory plan amendments**

All 7 review teammates completed. No CRITICAL violations of project ADRs.
The CRITICAL cross-validated finding (Patch 3 scope) is addressed in-plan via
the Preparatory Refactoring section (Finding 1, concrete shell snippet) and
the expanded Patch 3 row in the Files Touched table. The plan is executable
as written; Patch 2 and Patch 29 expanded scope is reflected in the Files
Touched table, Acceptance checklist, and per-agent procedure.

### Deferred to Patch 29 housekeeping or beyond

These are tracked explicitly so they aren't dropped:

1. **DEVELOPMENT.md "Plugin agent authoring" section** — note `.md.j2` is
   source of truth; `.md` is derived and must not be hand-edited
   (compat-checker Finding 3). Patch 29 scope.
2. **`plugins/requirements-framework/README.md` inline contract note** —
   author-facing note about `.md.j2` → `.md` build-time render contract
   (codex Q3). Patch 29 scope.
3. **CHANGELOG v4.5.0 wording** — explicit "source format change only;
   rendered output is byte-identical" to preempt user confusion
   (adr-guardian Finding 4). Patch 29 scope.
4. **Pre-commit hook wiring** — `render_prompts.py --check` on
   `*.md.j2` and `*.j2` files (tdd-validator Gap 3 + refactor-advisor
   Finding 5 — agreed). Patch 29 scope.
5. **No tooling reads `.md.j2` directly** — quick verification grep in
   Patch 29 confirming nothing in `hooks/`, `scripts/`, `plugins/` opens
   `*.md.j2` for substantive parsing (adr-guardian Finding 7). One-line
   grep check; failure mode is "future tooling assumed `.md` was canonical".
6. **ADR amendments — deferred to post-16b follow-up** (not blocking 16b ship):
   - ADR-006 (plugin architecture): document the "rendered `.md` is a derived
     artifact" pattern and the `git_hash` source-of-truth invariant
     (adr-guardian Findings 1 + 3).
   - ADR-016 (V3 substrate): operational note on the
     `hooks/lib/llm/prompts/partials/` shared API serving both runtime
     (V3 worker prompts via `load_prompt()`) and build-time (plugin agents
     via `render_prompts.py`) consumers. (adr-guardian Finding 1 + codex Q1.)

   These can land as a single "ADR amendments after Step 16b" follow-up
   patch if Step 16c isn't waiting on them.

### Requirements satisfied

This /arch-review run satisfies the four planning requirements:
- `commit_plan` — Patch breakdown table (29 patches, validated by
  commit-planner; type-design-analyzer ordering bug fixed in-plan)
- `adr_reviewed` — adr-guardian review complete; no blocking ADR
  violations; ADR amendments tracked as deferred items above
- `tdd_planned` — Testing Strategy section authored by tdd-validator;
  5 specific test additions captured in Patch 2 scope
- `solid_reviewed` — SOLID Considerations section authored by
  solid-reviewer; 4 actions captured (SRP rename, OCP kernel narrowing,
  DIP accepted, ISP deduplication check)

`pre_pr_review` (deep-review) and `codex_reviewer` (codex-review) still
to be satisfied before final ship. `verification_evidence` lands at
Patch 29 housekeeping.
