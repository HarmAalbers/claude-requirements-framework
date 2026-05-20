# Changelog

All notable changes to the requirements-framework plugin are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [4.0.0] — 2026-05-20

### Removed

- **Command `/plan-review`** — superseded by `/arch-review` (team-based, cross-validated) and `/req plan` (conductor). Marked deprecated in `3ca0bde`; removed here.
- **Command `/quality-check`** — superseded by `/deep-review` (cross-validated team review) and `/req review` (conductor). Marked deprecated in `3ca0bde`; removed here.
- **Config value `hooks.session_start.briefing_format: rich`** — `compact` has been the default since Step 01; the `rich` code path is removed from the dispatcher, `messages.py`/`message_validator.py`/`config.py`. Setting `briefing_format: rich` post-4.0 emits a deprecation warning and falls back to `compact`.

### Deprecated (carried into 4.0, scheduled for removal in 4.1+)

- **Agent `code-simplifier`** — marked DEPRECATED in `3ca0bde`. Retained in 4.0 because `/deep-review` and `/pre-commit` still actively spawn it; removal requires restructuring those commands first. Scheduled for removal in a future minor release after 4.0.

### Changed

- Plugin major version bumped to 4.0.0. The deprecated paths were introduced in `bdd0dc1` (workflow-position notes) and flagged in `3ca0bde` (deprecation marking); both commits are on master. The 2-week soak originally gating this removal was skipped per user decision on 2026-05-20 (clean break preferred over incremental accumulation of accidental dependencies).

### Migration

Update muscle memory and any local scripts:

| Old | New |
|---|---|
| `/plan-review` | `/arch-review` |
| `/quality-check` | `/deep-review` |
| `briefing_format: rich` | Remove the key entirely — `compact` is the default |

There is no compatibility shim. The 4.0.0 boundary is intentional.

---

## [3.0.0] — 2026-04-22

### Breaking
- **All 13 diff-based review agents now read pre-computed scope files** instead of running their own `git diff` in Step 1. They expect `/tmp/review_scope.txt` (changed files) and `/tmp/review.diff` (unified diff), either pre-computed by the invoking command (`/deep-review`, `/quality-check`) or auto-populated via `${CLAUDE_PLUGIN_ROOT}/scripts/prepare-diff-scope --ensure`. Consumers invoking review agents directly via the Task tool with a custom pre-populated `/tmp/code_review.diff` must migrate to the new paths.
- Affected agents: `code-reviewer`, `tool-validator`, `silent-failure-hunter`, `test-analyzer`, `type-design-analyzer`, `comment-analyzer`, `code-simplifier`, `backward-compatibility-checker`, `frontend-reviewer`, `codex-review-agent`, `tenant-isolation-auditor`, `appsec-auditor`, `compliance-auditor`.

### Added
- `hooks/lib/diff_scope.py` — unified review-scope resolution supporting empty/branch/range/PR# arguments, with 28 unit tests.
- `plugins/requirements-framework/scripts/prepare-diff-scope` — bash wrapper invoked by commands and agents.
- `hooks.diff_scope.base` config key (default `origin/master`) — override base ref for branch-vs-base resolution.
- `/deep-review` and `/quality-check` accept branch name, git range (`a..b` / `a...b`), or PR number (`1234` / `#1234`) as arguments.

### Fixed
- `--diff-filter` now includes `D` (deletions), so staged `git rm` is no longer silently skipped.
- Base ref is validated before diffing — missing `origin/master` no longer produces an empty scope silently.

### Developer
- New test file `hooks/test_diff_scope.py` with 30 tests using fixture git repos plus a fake-gh shim for PR-path tests.
- Plugin-version guard test ensures that when `diff_scope.py` is present the plugin version is ≥ 3.0.0.

### Known limitations
- `/quality-check` no longer reaches the `parallel` dispatch shortcut (the first positional arg is now consumed as the scope). Will be resolved in a follow-up by moving parallel-mode to a flag or env var.

### Internal
- Plugin wrapper script lives inside the plugin at `scripts/prepare-diff-scope` so commands can reference it via `${CLAUDE_PLUGIN_ROOT}/scripts/prepare-diff-scope`.
