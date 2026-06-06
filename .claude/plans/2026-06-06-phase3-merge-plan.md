# Phase-3 Merge Plan — `refactor/step-08-llm-package-scaffold` → `master`

> Produced by the `phase3-merge-planning` workflow (28 agents: cartography → 21 unit
> readiness + 4 crux-risk → synthesis → adversarial critic), then corrected by the
> primary session against the critic's findings. Date: 2026-06-06. Branch tip: `bc28b83`.

## 1. Bottom line

**Merge all 177 patches as the new `master` baseline (Option A) — after two must-fixes (a CI
dependency fix + a README rewrite) and an explicit behavior-change note.** The evidence is decisive:

- **V3 is structurally dormant on every live path.** All 17 lifecycle hooks load with
  `claude_agent_sdk` forcibly absent; `hooks/lib/llm/__init__.py` is PEP-562 lazy (importing the
  package does not import the SDK or pydantic); the only three live touch-points
  (`handle-session-start` retrieval read, `handle-session-end` qdrant write, the budget CLI) are
  config-gated **off by default** and fail-open. Landing V3 tested-but-unwired cannot destabilize a
  real session — and the project is source-only/undeployed anyway.
- **Nothing in the stack is half-built.** Steps 17b/19/20 exist only as **inert plan docs** under
  `.claude/plans/variant3/` — zero implementation code. No `NotImplementedError`/stub/FIXME in
  `hooks/lib/llm`. So Option B ("finish Task #4 first") buys zero safety while stranding the
  high-value re-enablement/workflow payload.
- **Extraction (Option C) is infeasible, not just costly.** Per the stack-dependency analysis the
  valuable era-2 workflow units sit *on top of* ~156 V3 patches; the CI suite hard-imports `llm`;
  the top patch edits `llm/supervisor.py`; the self-contained-plugin build-copies the whole `llm`
  tree. Extracting means rebasing `--onto master`, dropping 156 patches, and stripping test imports
  + plugin copies — throwing away green, tested work for **no live-safety gain**.

## 2. Merge units (21 units, stack order bottom → top)

6 clean **yes**, 15 **merge-with-caveat**, **0 "no"** — every caveat is "tested off-CI" or "dormant
surface area," not a correctness defect.

| # | Unit (scope) | Earned | Key note |
|---|---|---|---|
| 1 | `v3-scaffold-schemas` (08/09) | caveat | **Source of the CI break** — schemas.py eager-imports pydantic (§4) |
| 2 | `v3-workers-aggregator` (10) | caveat | deliberately-unwired pilot; 28 tests off-CI |
| 3 | `v3-observability` (11) | caveat | ships 5-service dev docker stack; 20 assertions off-CI |
| 4 | `v3-prompt-registry` (12) | caveat | Langfuse path CI-unguarded |
| 5 | `v3-retrieval-qdrant` (13) | caveat | first live-hook touch (SessionEnd), fail-open only |
| 6 | `v3-retrieval-read` (14) | caveat | SessionStart wiring, off-by-default + fail-open |
| 7 | `v3-eval-ragas` (15) | **yes** | 34 tests green (off-CI) |
| 8 | `v3-jinja2-engine` (16) | **yes** | 61 tests + render gate (off-CI) |
| 9 | `v3-jinja2-agents` (16b) | caveat | 29 byte-identical mechanical patches |
| 10 | `v3-jinja2-commands-skills` (16c) | **yes** | 32 mechanical; permanent invariant test |
| 11 | `v3-dogfood` | caveat | load-bearing `ReviewReport.summary` cap-removal has **no regression test** |
| 12 | `v3-budget-tracker` (17a) | caveat | `claude.py` re-export→live wrapper on V3 hot path |
| 13 | `v3-supervisor` (18) | caveat | orphaned red tests at HEAD (§5) |
| 14 | `v3-fanout` (18b) | caveat | ~200 tests CI-invisible |
| 15 | `v3-review-command` (18c) | caveat | **cost foot-gun $2–12/run, no per-call cap** (§7) |
| 16 | `re-enablement-hardening` (1a–1e) | caveat | live-path-core state-locking, **well CI-tested** |
| 17 | `re-enablement-ledger` (2-ledger) | **yes** | docs-only |
| 18 | `self-contained-plugin` (3) | caveat | build-copies `llm` tree into plugin (two-place tax) |
| 19 | `commit-plan-gate-and-ux` (2) | **yes** | **live-path behavior change** (§3.1); strong CI coverage |
| 20 | `workflow-order-engine` (2) | **yes** | live-path-core, **llm-free**, 77 assertions; **brainstorm-nudge default-ON** |
| 21 | `config-driven-supervisor` (3, `bc28b83`) | caveat | **introduces the CI-breaking test** (§4) |

## 3. Method & sequencing

**One PR for the whole branch, landed with a `--no-ff` merge commit.**
- **Not squash** — 177 atomic stg patches are deliberately one-logical-change-each; squashing
  destroys the bisectable history this assessment relied on.
- **Not bare fast-forward** — the stack *is* FF-able (zero divergence), but `--no-ff` preserves all
  177 commits *and* gives one named "V3 + re-enablement baseline" marker on master.
- A reviewable 2-PR cut is *possible* (PR1 = all V3 via `git merge 11da47e`; PR2 = the 21 era-2
  patches, which hard-import `llm` from PR1) but buys nothing for a single-user repo. Not recommended.

### 3.1 ⚠️ Behavior changes for plugin users (MUST land in CHANGELOG + release note)
This is the largest user-visible delta in the merge and was under-weighted in the draft. Era-2 changes
**default** live-path behavior for anyone who installs the plugin:
- **Brainstorm nudge is default-ON** (`hooks.prompt_submit.brainstorm_nudge`) — every substantive
  first prompt now gets a `/brainstorming` nudge (mode-independent, once per session).
- **`commit_plan` / design gates** fire on `Edit`/`Write` whenever enabled — the gate UX + deadlock
  fixes changed how/when edits are blocked.
- **`stop_only` verification gate** — `verification_evidence` enforced at `Stop`.
- These are off unless the requirement is enabled in config, **but the brainstorm nudge defaults on**.
  Call this out explicitly so existing users aren't surprised. Provide the opt-out keys.

## 4. MUST-FIX #1 — CI goes red on merge (CONFIRMED, hard blocker)

`.github/workflows/ci.yml` installs **only** `pip install pyyaml`, then runs
`python hooks/test_requirements.py`. The branch's `test_supervisor_config_driven`
(`hooks/test_requirements.py:12362`) hard-imports `hooks.lib.llm.schemas`, whose module top does
`from pydantic import …` with no skip-guard.

**Reproduced empirically in this session** (fresh `python -m venv`, `pip install pyyaml` only,
`__pycache__` pruned, hermetic `HOME`):
```
ModuleNotFoundError: No module named 'pydantic'   # hooks/lib/llm/schemas.py:14
  → test_supervisor_config_driven crashes the runner UNCAUGHT → exit code 1
```
This resolves the disagreement in the workflow's own evidence: crux-check #1's "1445/1445" run
isolated `HOME` but **not** the interpreter (the dev box has pydantic in site-packages), so it did
not reproduce CI. Crux-check #2 + this session's repro did. **Treat CI as will-break-until-fixed.**

**Chosen fix (a) — install the light deps so the tests actually run:**
```yaml
# .github/workflows/ci.yml — dependency step:
-     run: pip install pyyaml
+     run: pip install pyyaml pydantic jinja2   # NOT the full .[llm] extra (drags torch/ragas)
```
Optionally *also* add a `try/except ModuleNotFoundError → skip` guard around the `llm` imports in
`test_supervisor_config_driven` (defensive: matches `test_llm_package_scaffold`'s existing pattern,
keeps a deps-less dev box from crashing the suite). Belt-and-suspenders.

**Verification must be on REAL CI, not a local venv** (the draft's §8 repeated the "trust the dev
box" error): push the **branch** (already done — `bc28b83` is on origin) plus the CI-fix patch, and
**watch the actual GitHub Actions run on the PR go green before merging to master.** A local
`venv(pyyaml+pydantic+jinja2)` run is a pre-check, not proof.

## 5. MUST-FIX #2 (with merge) — README contradicts the branch's own install.sh

The branch removed hook-copying + `settings.json` registration from `install.sh` (the plugin's
`hooks.json` is now the single source of truth), but `README.md` still tells users the installer
"copies hooks to `~/.claude/hooks/`" (L34), "registers all hooks in settings" (L36), and documents
the two-location `sync.sh` deploy flow (~L189, 1018–1021, 1290–1426). A user following README after
merge builds a **stale/duplicate hook config**. `install.sh` + `CLAUDE.md` already describe the
plugin-owned model; README is the lone holdout. Rewrite those sections to: "install.sh sets up only
the `req` CLI + statusline + shell env; hooks activate via `/plugin install …` or
`claude --plugin-dir`."

## 6. Fix-after / housekeeping (non-blocking, fast-follow)

- **Orphaned RED tests**: `tests/test_supervisor.py` (era-2's lazy `query` broke a `mock.patch`) and
  `tests/test_schemas.py` (21/22 after `Literal[7]→str`) error at HEAD but are **not CI-gated** → they
  rot silently. Repair or delete.
- **CHANGELOG** stops at `[4.6.0]`; `plugin.json` is `4.15.0`. Add a consolidated
  "V3 LLM platform + workflow simplification (4.7.0→4.15.0)" entry — **including §3.1's behavior changes.**
- **CLAUDE.md counts**: "19 agents, 8 commands, 5 skills" → **25 / 12 / 21**; "950+ tests" → **1445**;
  add `handle-git-events.py` to the lifecycle list.
- **Stale `447` test-count** in README (L16/767/778/808) + DEVELOPMENT.md:389; README "four hooks" → 13.
- **`ruff_check.py` docs drift** (step-1d deleted the hook, refs remain in CLAUDE.md L192,
  DEVELOPMENT.md L135, 4 plugin skills, docs/installation-friction-points.md).
- **`git_hash` drift** (~46 components `fe1bf87→87dd023`): **auto-healed by `publish.yml`** post-merge
  (see §7 — verify that workflow actually succeeds against this tree). Optional `./update-plugin-versions.sh`
  pre-merge only if you want an honest merge diff.
- **CI hardening (follow-up)**: wire the orphaned `tests/` V3 suite (273+ tests) +
  `scripts/render_prompts.py --check` into CI (with `PYTHONDONTWRITEBYTECODE=1`); optional scoped ruff.
- **Local footgun (not a defect)**: a live `--plugin-dir` session seeds
  `plugins/.../hooks/lib/__pycache__`, giving a false 1444/1445 via the `build --check` test. Prune
  `__pycache__` / set `PYTHONDONTWRITEBYTECODE=1` before trusting a local run. Clean-checkout CI is unaffected.

## 7. Risk register

| Risk | Severity | Mitigation |
|---|---|---|
| CI red on merge (pyyaml-only vs pydantic-importing test) | **High / blocking** | §4: `pip install pyyaml pydantic jinja2`; **verify on real CI**, not local venv |
| README install flow contradicts branch (users build stale hook config) | High (user-facing) | §5 rewrite, with the merge |
| **era-2 default behavior changes (brainstorm-nudge ON, gates, stop-only) surprise users** | **Medium-High** | §3.1: document in CHANGELOG + release note + opt-out keys |
| `/v3-review` cost foot-gun ($2–12/run, no per-call cap; 17b unfinished) **and it can satisfy `pre_pr_review` via `auto-satisfy-skills.py`** | Medium (cost) | Confirm it only **auto-satisfies when the user runs it** (never auto-*invokes*); keep opt-in; document loudly; defer auto-wiring until 17b |
| 273+ V3 `tests/` + freshness gates CI-invisible → silent rot | Medium | Follow-up CI job; until then keep V3 dormant |
| `publish.yml` auto-runs `update-plugin-versions.sh` + commits to master on push | Medium | **Verify** publish.yml succeeds against the 177-patch tree (incl. uncommitted `v3-review.md.j2`) before relying on auto-heal; consider running it manually pre-merge |
| whole `llm` tree build-copied into plugin (maintenance tax) | Medium | Enforce inert-V3 invariants: `__init__.py` stays lazy; the 2 session-hook `llm` paths stay config-gated + fail-open; no live hook gains a top-level `llm` import |
| load-bearing `ReviewReport.summary` cap-removal has no regression test | Low | add a one-line assert in follow-up |

## 8. Deferred / dropped
- **Nothing dropped** — all 177 merge.
- **17b/19/20**: inert plan docs → merge-dormant as roadmap history.
- **Task #4** (V3 portability + eval-score + budget-gate): not in this stack; remains deferred.
- **Off-by-default live wiring** (`hooks.retrieval.enabled`, `hooks.qdrant.enabled` = `false`):
  merged but fenced; leave disabled.

## 9. Concrete next actions (in order)
1. **`stg new step-4-ci-llm-test-deps`** → edit `ci.yml` (`pip install pyyaml pydantic jinja2`),
   optional skip-guard on the test → `stg refresh`. Pre-check in an isolated `venv(pyyaml+pydantic+jinja2)`
   → expect `1445/1445`, exit 0.
2. **README rewrite** (§5) + **CHANGELOG entry** with the §3.1 behavior note → `stg new` patches.
3. **Verify `publish.yml`** won't misfire on the merge (dry-run `update-plugin-versions.sh`).
4. **Push branch + open ONE PR → watch real CI go green** (not a local venv).
5. **Merge to master with `--no-ff`** (requires explicit user sign-off — outward-facing + triggers
   publish.yml auto-push).
6. Fast-follow: §6 housekeeping.
