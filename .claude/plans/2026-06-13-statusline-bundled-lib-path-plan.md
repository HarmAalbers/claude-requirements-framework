# Statusline bundled-lib path fix + regression guard — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use requirements-framework:executing-plans to implement this plan task-by-task.

**Goal:** Repoint `statusline.sh` at the plugin's bundled `hooks/lib` so the phase + req-count fields stop silently degrading to placeholders, and add a regression guard that invokes the script end-to-end.

**Architecture:** One-line path fix in a bash script (delete two dead fallbacks), plus two new Python tests in the existing `hooks/test_requirements.py` suite — one asserting the bundled libs exist, one running `statusline.sh` via `subprocess` against a throwaway git repo + fixture state file and asserting the output is not the fail-open placeholder.

**Tech Stack:** Bash, Python stdlib (`subprocess`, `tempfile`, `json`), the repo's hand-rolled `TestRunner`.

**Design doc:** `.claude/plans/2026-06-13-statusline-bundled-lib-path-design.md`

---

### Task 1: Regression guard tests (RED first)

**Files:**
- Modify: `hooks/test_requirements.py` (add two test functions next to `test_count_unsatisfied`, ~line 12397; register both in the run list at ~line 12983)

**Step 1: Write the two failing tests**

Add after `test_count_unsatisfied`:

```python
def test_statusline_bundled_libs_present(runner: TestRunner):
    """The self-contained plugin must bundle the libs statusline.sh reads."""
    print("\n📦 Testing statusline bundled libs present...")
    repo_root = Path(__file__).resolve().parent.parent
    bundled = repo_root / "plugins" / "requirements-framework" / "hooks" / "lib"
    for name in ("statusline_data.py", "derive_phase.py", "count_unsatisfied.py"):
        runner.test(f"bundled {name} exists",
                    (bundled / name).is_file(),
                    f"missing: {bundled / name}")


def test_statusline_script_end_to_end(runner: TestRunner):
    """statusline.sh must render real phase/count, not the fail-open placeholder.

    Runs both lib-resolution paths: CLAUDE_PLUGIN_ROOT set (plugin-loader
    invocation) AND unset (the install.sh / settings-runner production path,
    which relies on the $(dirname "$0") fallback). HOME is pinned to the
    throwaway dir so the RED state can't be masked by a real ~/.claude/hooks/lib
    on a machine where the framework was deployed (codex + tdd-validator).
    """
    print("\n📦 Testing statusline.sh end-to-end...")
    repo_root = Path(__file__).resolve().parent.parent
    plugin_root = repo_root / "plugins" / "requirements-framework"
    script = plugin_root / "statusline.sh"
    if not script.is_file():
        runner.test("statusline.sh exists", False, f"missing: {script}")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)
        # A throwaway git repo with a born branch so `git rev-parse --abbrev-ref
        # HEAD` resolves the way statusline.sh expects.
        subprocess.run(["git", "init", "-b", "wip", str(repo)],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t",
                        "-c", "user.name=t", "commit", "--allow-empty",
                        "-m", "init"], check=True, capture_output=True)

        state_dir = repo / ".git" / "requirements"
        state_dir.mkdir(parents=True, exist_ok=True)
        # design_approved satisfied → phase advances past "design" to
        # "plan-write"; one triggered-unsatisfied req → count == 1. Both differ
        # from the placeholder ([design] / [? req]).
        (state_dir / "wip.json").write_text(json.dumps({"requirements": {
            "design_approved": {"satisfied": True},
            "plan_written": {"triggered": True},
        }}))

        payload = json.dumps({
            "workspace": {"current_dir": str(repo)},
            "context_window": {"used_percentage": 7},
            "session": {"cost_usd": 0.5},
        })

        def _render(plugin_root_env) -> str:
            # HOME pinned to tmpdir: kills any real ~/.claude/hooks/lib so the
            # only way to resolve the libs is the path under test.
            env = {**os.environ, "HOME": str(repo)}
            if plugin_root_env is None:
                env.pop("CLAUDE_PLUGIN_ROOT", None)
            else:
                env["CLAUDE_PLUGIN_ROOT"] = plugin_root_env
            return subprocess.run(["bash", str(script)], input=payload,
                                  capture_output=True, text=True, env=env).stdout

        # Path A: plugin-loader invocation (CLAUDE_PLUGIN_ROOT set).
        out_a = _render(str(plugin_root))
        # Path B: settings-runner / install.sh invocation — CLAUDE_PLUGIN_ROOT
        # unset, so the $(dirname "$0") fallback must resolve $PLUGIN_ROOT/hooks/lib.
        out_b = _render(None)

        for label, out in (("plugin-root", out_a), ("dirname-fallback", out_b)):
            runner.test(f"{label}: phase is real, not [design]",
                        "[plan-write]" in out, f"Got: {out!r}")
            runner.test(f"{label}: req count numeric, not '?'",
                        "[? req" not in out and "[1 req" in out, f"Got: {out!r}")
```

Confirm `import os` is present at the top of the file (it is — `os`, `json`, `subprocess`, `tempfile`, `pathlib.Path` are all already imported; the "add if missing" note is moot).

**Step 2: Register both tests in the run list**

Next to `test_count_unsatisfied(runner)`:

```python
    test_count_unsatisfied(runner)
    test_statusline_bundled_libs_present(runner)
    test_statusline_script_end_to_end(runner)
```

**Step 3: Run to verify the end-to-end test FAILS (path bug still present)**

Run: `python3 hooks/test_requirements.py 2>&1 | grep -iE "statusline|FAIL"`
Expected: `test_statusline_script_end_to_end` assertions FAIL for **both** the `plugin-root` and `dirname-fallback` variants — output contains `[design]` and `[? req⬜]` because `statusline.sh` can't find the libs (old `../../../hooks/lib` is absent and HOME-pinning kills the dead `~/.claude/hooks/lib` fallback). (`test_statusline_bundled_libs_present` may already PASS — the libs exist; only the bash path is wrong.)

**Step 4: Commit the red tests**

```bash
stg new statusline-guard-tests -m "test(statusline): end-to-end guard against fail-open placeholder"
git add hooks/test_requirements.py
stg refresh --index
```

---

### Task 2: Fix the path (GREEN)

**Files:**
- Modify: `plugins/requirements-framework/statusline.sh:14-22`

**Step 1: Replace the lib-resolution block**

Replace lines 14–22 (the `PLUGIN_ROOT=` line through the `fi` that closes the `~/.claude/hooks/lib` fallback) with:

```bash
# Locate the plugin's bundled hook libs. The plugin is self-contained
# (commit 652141b): libs live under $PLUGIN_ROOT/hooks/lib in both the
# --plugin-dir dev layout and the global cached install.
# $CLAUDE_PLUGIN_ROOT is set when invoked through Claude Code's plugin loader.
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")" && pwd)}"
HOOK_LIB="${PLUGIN_ROOT}/hooks/lib"
```

**Step 2: Run the suite to verify GREEN**

Run: `python3 hooks/test_requirements.py 2>&1 | tail -5`
Expected: all tests pass, including the two new statusline tests.

**Step 3: Manual sanity check**

Run:
```bash
echo '{"workspace":{"current_dir":"'"$PWD"'"},"context_window":{"used_percentage":12},"session":{"cost_usd":0.87}}' \
  | CLAUDE_PLUGIN_ROOT="$PWD/plugins/requirements-framework" bash plugins/requirements-framework/statusline.sh
```
Expected: a **real** phase and a **numeric** count — i.e. `[ctx 12%] [$0.87]` with the phase field NOT `[design]` *(unless design is genuinely the current phase on this branch)* and the req field NOT `[? req⬜]`. The exact phase/count depend on this branch's state file, so don't assert a hard-coded `[ship]`; the point is that both computed fields resolve instead of degrading to placeholders.

**Step 4: Commit the fix**

```bash
stg new statusline-path-fix -m "fix(statusline): read bundled \$PLUGIN_ROOT/hooks/lib (self-contained plugin)"
git add plugins/requirements-framework/statusline.sh
stg refresh --index
```

---

### Task 3: Plugin version bump

**Files:**
- Modify: `plugins/requirements-framework/.claude-plugin/plugin.json` (`"version": "4.19.1"` → `"4.19.2"`)

**Step 1: Bump the patch version**

Change `"version": "4.19.1"` to `"version": "4.19.2"`.

**Step 2: Fold into the fix patch (same logical change)**

```bash
git add plugins/requirements-framework/.claude-plugin/plugin.json
stg refresh --index   # folds the bump into statusline-path-fix
```

**Step 3: Verify the stack**

Run: `stg series`
Expected: `design-doc`, `statusline-guard-tests`, `statusline-path-fix` (3 patches).

---

## Done criteria

- `python3 hooks/test_requirements.py` fully green, including the two new statusline tests (both the `plugin-root` and `dirname-fallback` variants).
- Manual render shows real phase/count (no placeholder degradation).
- Plugin version bumped to 4.19.2 in the fix patch.
- Deferred items left untouched (still accurate in `docs/STATUSLINE.md`).

## Follow-ups discovered in arch-review (OUT OF SCOPE for this fix)

These are real but distinct from the path bug; tracking them here so they aren't lost. Do NOT fold into this fix:

1. **Worktree state-path bug (codex, IMPORTANT).** `statusline.sh` computes `$CWD/.git/requirements/$BRANCH.json` in shell, duplicating Python's `branch_to_filename` + state-dir resolution. In a git worktree `.git` is a *file*, not a dir, so the state file is never found → the statusline silently shows `[design] [? req⬜]` (same failure class this fix addresses, different codepath). Proper fix: teach `statusline_data.py` to accept `--cwd` and resolve the state dir via the existing Python logic (`git rev-parse --git-common-dir`), collapsing the shell's git/state-path logic. Separate change — needs its own design/plan.
2. **ADR for the self-contained plugin (adr-guardian, IMPORTANT-systemic).** Commit `652141b` ("self-contained hooks via build-copy") is load-bearing but has no ADR, and CLAUDE.md's "Two-Location System" section still describes `~/.claude/hooks` as the runtime — the stale mental model that produced this very bug. Recommend a follow-up `ADR-021: self-contained plugin via build-copy` documenting source-of-truth `hooks/`, the build-copy step, `statusline.sh` as the hand-maintained exception, and `${CLAUDE_PLUGIN_ROOT}/hooks/lib` as canonical. Separate commit.

---

## Commit Plan

> Stacked Git. Base patch `design-doc` (design + this plan) already committed. Two new patches complete the work.
> The version bump is metadata for the fix and folds into the fix patch — not an independent logical change.

| Order | Patch (stg) | Type | Files | Independently green |
|-------|-------------|------|-------|---------------------|
| 1 | `statusline-guard-tests` | test (RED) | `hooks/test_requirements.py` | No — RED by design until patch 2 |
| 2 | `statusline-path-fix` | fix + chore | `plugins/requirements-framework/statusline.sh`, `plugins/requirements-framework/.claude-plugin/plugin.json` | Yes — turns the suite green |

### Patch 1: `statusline-guard-tests`
**Title:** `test(statusline): end-to-end guard against fail-open placeholder`
**Files:** `hooks/test_requirements.py` — add `test_statusline_bundled_libs_present` + `test_statusline_script_end_to_end` (both env variants) next to `test_count_unsatisfied`; register both in the run list.
**Test:** `python3 hooks/test_requirements.py 2>&1 | grep -iE "statusline|FAIL"` → e2e test FAILS (intentional RED; flag in PR so a bisect doesn't misread it).

### Patch 2: `statusline-path-fix`
**Title:** `fix(statusline): read bundled $PLUGIN_ROOT/hooks/lib (self-contained plugin)`
**Files:** `statusline.sh:14-22` (two-line bundled resolution, fallbacks deleted) + `plugin.json` 4.19.1 → 4.19.2 (same patch).
**Test:** full suite GREEN (both new tests); manual render shows real phase/count; `stg show statusline-path-fix` includes the `plugin.json` hunk.

### Stack verification
`stg series` → `design-doc`, `statusline-guard-tests`, `statusline-path-fix`. Only the tip is expected green (stack ships as a unit). No `sync.sh` step — change lives under the plugin, loaded via `--plugin-dir`.

---

## Verdict

APPROVED
Reviewed: fix/statusline-bundled-lib-path @ 2026-06-13T07:12:00Z

7-agent team (incl. codex). Six APPROVED; codex's 2 IMPORTANT findings triaged: the test-coverage gap (dirname fallback) is folded into Task 1; the worktree state-path bug is a distinct pre-existing latent bug tracked as Follow-up #1, not a blocker for this path fix. No CRITICAL findings.
