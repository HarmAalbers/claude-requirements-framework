# Design — Diff Scope Refactor

**Date**: 2026-04-21
**Branch**: `feat/diff-scope-refactor`
**Target version**: `3.0.0` (breaking agent contract)
**Author**: Harm + Claude (brainstorming session `0b283774`)

## Motivation

Borrowed from solarmonkey's `tino/agent-guidance-via-docs` review. Two patterns we want in our framework:

1. **Pre-compute the diff once** — today, each of 13 review agents runs its own `git diff` in Step 1, meaning a `/deep-review` with 10 parallel agents does 10 redundant diffs. Solarmonkey computes it once in the command and passes paths to every agent.
2. **Multi-input scope resolution** — today, reviews only work on staged-then-unstaged. Solarmonkey's `/deep-review` also accepts a branch name, a git range, or a PR number. We adopt Git + PR number (JJ dropped — no real users).

Two solarmonkey patterns **rejected** for our framework (see brainstorming transcript):
- "Agents read project docs instead of embedding rules" — our `adr-guardian` already reads ADRs from disk; `solid-reviewer`'s embedded knowledge is universal (SOLID), not project-specific. Low applicability.
- "Rules backlog file" — our `/session-reflect` + learning system already fills this niche better.

## Scope

### In scope
- New module `hooks/lib/diff_scope.py` — one source of truth for "what are we reviewing?"
- Bash wrapper `scripts/prepare-diff-scope` — invoked by commands and (as fallback) by agents
- Config key `hooks.diff_scope.base` — overrides default `origin/master`
- Command migration: `/deep-review`, `/quality-check`
- Agent migration: 13 diff-based review agents (see list below)
- `/arch-review` minor update: accepts plan file path as argument
- Plugin version bump `2.8.2 → 3.0.0` (breaking agent contract)
- `hooks/test_diff_scope.py` — ~26 tests

### Out of scope / Follow-ups
- **`comment-cleaner` + `import-organizer`** — these agents auto-edit files (not reviewers) and want staged-only semantics. Intentionally excluded; they deserve their own review pass. Tracked as task #7 in the brainstorming session.
- JJ (Jujutsu) support — dropped until real users need it
- Plan-based agents untouched: `adr-guardian`, `solid-reviewer`, `tdd-validator`, `refactor-advisor`, `commit-planner`, `session-analyzer`, `codex-arch-reviewer`

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Commands (/deep-review, /quality-check)                    │
│  1. Parse argument (branch | a..b | PR# | empty)            │
│  2. Call scripts/prepare-diff-scope "$ARGUMENTS"            │
│  3. Pass SCOPE_FILE, DIFF_FILE paths to each agent          │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
        ┌────────────────────────────────┐
        │  scripts/prepare-diff-scope    │
        │  (bash wrapper)                │
        └────────────────────┬───────────┘
                             │
                             ▼
        ┌────────────────────────────────┐
        │  hooks/lib/diff_scope.py       │
        │  • prepare_diff_scope(arg)     │
        │  • read_scope()                │
        │  • ensure_scope()              │
        │  • Scope dataclass             │
        │  • DiffScopeError              │
        └────────────────────┬───────────┘
                             ▲
                             │
┌────────────────────────────┴────────────────────────────────┐
│  Review Agents (13)                                         │
│  Step 1: scripts/prepare-diff-scope --ensure                │
│  Then read /tmp/review_scope.txt + /tmp/review.diff         │
└─────────────────────────────────────────────────────────────┘
```

### Key properties
- **Single source of truth** — one function, one pair of temp files
- **Deterministic and idempotent** — same input = same output files
- **Testable** — `diff_scope.py` has a pure-Python API with no global state
- **Graceful on missing tools** — PR-number path raises `DiffScopeError` on `gh` missing; other paths keep working

## Public API

```python
# hooks/lib/diff_scope.py

@dataclass(frozen=True)
class Scope:
    files: list[str]         # changed file paths
    diff_text: str           # unified diff
    scope_file: Path
    diff_file: Path
    source: str              # "empty", "branch:foo", "range:a..b", "pr:123"
    base_ref: str | None     # the base diffed against


class DiffScopeError(Exception):
    """Scope could not be resolved (missing gh, bad PR, etc.)."""


def prepare_diff_scope(
    arg: str | None = None,
    scope_file: Path = Path("/tmp/review_scope.txt"),
    diff_file: Path = Path("/tmp/review.diff"),
    base: str = "origin/master",
) -> Scope:
    """Resolve arg to a Scope and write both files."""


def read_scope(
    scope_file: Path = Path("/tmp/review_scope.txt"),
    diff_file: Path = Path("/tmp/review.diff"),
) -> Scope:
    """Read pre-computed scope without re-resolving."""


def ensure_scope(
    scope_file: Path = Path("/tmp/review_scope.txt"),
    diff_file: Path = Path("/tmp/review.diff"),
) -> Scope:
    """Agent-side entry: read pre-computed scope if present, else compute."""
```

### Argument parsing (`arg`)
| Shape | Treatment |
|---|---|
| `None` / `""` | staged → unstaged → current branch vs `base` (precedence order) |
| `"a..b"` / `"a...b"` | git range (two-dot or three-dot merge-base) |
| all digits or `#digits` | PR number → `gh pr diff N --patch` |
| anything else | branch name → `git diff base...arg` |

### Config
```yaml
# requirements.yaml
hooks:
  diff_scope:
    base: "origin/master"   # default; override to "origin/main" etc.
```

## Command-Side Integration

### `/deep-review` — Step 1 rewrite
Before: inline `git diff --cached` + `git diff` fallback.
After: `scripts/prepare-diff-scope "$ARGUMENTS"` + scope-summary line.

### `/quality-check` — same shape
### `/arch-review` — accepts plan file path as argument (sibling change, commit 16)
Not wired into `diff_scope` — plan review is a different substrate.

### Output convention
Commands print a scope summary after helper returns:
```
Scope: pr:1234 (8 files, base=origin/master)
```

### Argument-hint updates
```yaml
argument-hint: "[branch | a..b | PR#]"
```

## Agent-Side Integration

**13 agents migrated** (identical Step 1 replacement):
`code-reviewer`, `tool-validator`, `silent-failure-hunter`, `test-analyzer`, `type-design-analyzer`, `comment-analyzer`, `code-simplifier`, `backward-compatibility-checker`, `frontend-reviewer`, `codex-review-agent`, `tenant-isolation-auditor`, `appsec-auditor`, `compliance-auditor`.

### Unified new Step 1
```markdown
## Step 1: Load Review Scope

Execute: `scripts/prepare-diff-scope --ensure`

Read `/tmp/review_scope.txt` (list of changed files, one per line) and
`/tmp/review.diff` (unified diff). If the scope file is empty, output
"No review scope provided" and EXIT.

Focus your review on the files in the scope; do not expand beyond them.
```

### Frontmatter
All 13 agents gain (if missing): `allowed-tools: ["Bash", "Read", "Glob", "Grep", "SendMessage", "TaskUpdate"]`.

### Codex agent special case
`codex-review-agent` reads `/tmp/review.diff` and passes it to `codex exec` as context instead of shelling `git diff` itself.

## Error Handling

| Scenario | Behavior |
|---|---|
| `gh` missing + PR# arg | `DiffScopeError("gh CLI required…")` → command prints install hint, exits |
| Invalid PR# | `DiffScopeError("PR #N not found or access denied")` |
| Invalid branch | `DiffScopeError("branch '…' not found")` |
| Invalid range | `DiffScopeError("invalid range '…'")` |
| Empty scope (no changes) | Returns `Scope(files=[], …)`; caller decides (commands print `No changes to review`) |
| Large diff >1 MB | Warning logged via `hooks.lib.logger`; scope returned intact |
| Non-Git repo | `DiffScopeError("not a git repository")` |
| Detached HEAD | `git rev-parse HEAD` used as "current ref" |
| Parallel invocations | Accept explicit `scope_file`/`diff_file` overrides; commands can pass session-scoped paths |

### Wrapper semantics (`scripts/prepare-diff-scope`)
- `--ensure` mode: if both files exist non-empty → silent no-op; else → run helper, print single line
- No-arg mode (command invocation): always runs helper, prints scope summary

## Testing Strategy

TDD. New file `hooks/test_diff_scope.py`. ~26 tests in 10 groups using fixture Git repos (`tempfile.TemporaryDirectory` + subprocess — no `git` mocking, consistent with `test_branch_size_calculator.py`).

### Groups
1. **Empty-arg precedence** (5) — staged → unstaged → branch → detached → non-git
2. **Branch arg** (3) — valid / not-found / identical-to-base
3. **Range arg** (3) — two-dot / three-dot / malformed
4. **PR# arg** (4) — gh missing / gh succeeds / PR not-found / not-authed
5. **File outputs** (3) — default paths / custom paths / idempotent overwrite
6. **Scope dataclass contract** (2) — source field / base_ref field
7. **Config override** (2) — override applied / default used
8. **ensure_scope() fallback** (2) — pre-computed / compute-on-demand
9. **Large diff warning** (1)
10. **Plugin version guard** (1) — if `diff_scope.py` exists, `plugin.json` version ≥ 3.0.0

Plus one integration smoke test at shell level: `scripts/prepare-diff-scope --ensure` in a fixture repo writes both files.

PR# tests use a fake `gh` binary injected via `PATH` (pragmatic exception to "no mocking" — CI can't auth real PRs).

## Commit Plan (atomic, within one PR)

### Phase 1 — Foundation
1. `feat(diff-scope): add diff_scope module skeleton + dataclass`
2. `test(diff-scope): add fixture repo helpers and empty-arg tests` (RED)
3. `feat(diff-scope): implement empty-arg resolution` (GREEN)

### Phase 2 — Input types
4. `test(diff-scope): add branch and range arg tests` (RED)
5. `feat(diff-scope): implement branch and range arg resolution` (GREEN)
6. `test(diff-scope): add PR# tests with gh shim` (RED)
7. `feat(diff-scope): implement PR# arg via gh CLI` (GREEN)

### Phase 3 — Config + fallback
8. `feat(config): support hooks.diff_scope.base override`
9. `test(diff-scope): add ensure_scope() fallback tests`
10. `feat(diff-scope): implement ensure_scope() helper`

### Phase 4 — Wrapper + wiring
11. `feat(scripts): add prepare-diff-scope bash wrapper`
12. `feat(commands): migrate /deep-review to diff_scope helper`
13. `feat(commands): migrate /quality-check to diff_scope helper`

### Phase 5 — Agent sweep + release
14. `refactor(agents): unify Step 1 on diff_scope helper (13 agents)`
15. `chore: bump plugin to 3.0.0 + CHANGELOG + plugin-version test`

### Phase 6 — Sibling
16. `feat(commands): /arch-review accepts plan file path argument`

## Rollback Strategy

- Each commit independently revertable
- Commit 14 is riskiest (13-file mechanical refactor) — if a specific agent regresses, fix in follow-up commit without reverting the sweep
- Commits 11–13 enable the helper with zero breakage; 14 is the contract-break boundary
- Plugin consumers can pin to 2.8.2 until ready for 3.0.0

## Open Items (non-blocking)

- **Framework gates were bypassed for design-doc write**: session requirements (`commit_plan`, `adr_reviewed`, `tdd_planned`, `solid_reviewed`, etc.) were satisfied via `req satisfy` rather than the intended `/arch-review` flow. Before the implementation PR, run `/arch-review` against this design doc for real gate coverage.
- Follow-up: review `comment-cleaner` and `import-organizer` for inclusion in a future staged-scope helper (task #7 in brainstorming session)
- ADR for the `diff_scope` contract? — the 3.0.0 agent-contract break probably deserves an ADR. To be decided during `/writing-plans`.

## References

- Solarmonkey branch: `tino/agent-guidance-via-docs` at `~/Work/solarmonkey-app-10311`
- Framework review of that branch: earlier in this session
- Our existing test patterns: `hooks/test_branch_size_calculator.py`
- Existing ADRs relevant: ADR-012 (agent teams), ADR-013 (standardized agent output format)
