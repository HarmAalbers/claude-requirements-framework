# Design: Refactor Orchestration Integration

**Date**: 2026-05-18
**Status**: Approved, ready for implementation planning
**Companion plan**: `2026-05-18-refactor-orchestration-integration-plan.md` (to be written via `requirements-framework:writing-plans`)
**Related ADR**: ADR-014 (to be written as part of this migration)

## Context

The user has placed a new skill and three supporting agents at `~/.claude/`:

- Skill: `~/.claude/skills/refactor-orchestration/` (SKILL.md + 4 templates + learnings.md)
- Agents: `~/.claude/agents/refactor-{executor,investigator,analyzer}.md`

The skill captures a workflow for **multi-layer top-down refactors**: design the outermost layer first, push unfit responsibilities downward with an "export manifest," then move layer by layer until the codebase is reshaped. It produces a frozen plan + an orchestrator-prompt that runs in a fresh `claude` session, dispatching mechanical chunks to a Haiku executor and escalating contradictions to a Sonnet investigator. A final Sonnet analyzer writes a retrospective and grows a learnings ledger via rule-of-three promotion.

The skill's own SKILL.md already declares a coexistence mapping with `requirements-framework`. This design captures the decision to **adopt it as a first-class part of the framework** rather than leave it as a global side-installation.

## Goals

1. Make refactor-orchestration discoverable and invocable through the framework's standard surfaces (commands, agents, skills).
2. Preserve the skill's tight self-contained design — no dilution of its model-tier fanout, no aggressive auto-detection, no premature merging with existing learning systems.
3. Keep a single source of truth in the plugin repo; eliminate drift from globally-installed duplicates.
4. Add minimal new surface area — one command, three namespaced agents, one bundled skill.

## Non-goals

- Auto-detection of "this refactor is large" via heuristics on branch_size or touched-file count. Routing is explicit only.
- Auto-satisfying the framework's blocking requirements (`design_approved`, `plan_written`, etc.) from this skill. The user is expected to run `/arch-review` first by convention.
- Merging refactor-orchestration's learning loop with the framework's `session-learning` system.
- Cross-pollination of the auto-grown `.claude/refactor-conventions.md` into other framework commands (`/arch-review`, `/writing-plans`, `/brainstorming`).
- Real end-to-end multi-layer refactor as a test gate. v1 ships with theoretical confidence and refines via real use.

## Brainstorm decisions (Q1–Q5 + follow-ups)

| Question | Decision |
|---|---|
| Q1: Primary intent | Adopt into plugin **and** route on detection (resolved in Q2 to: route via explicit command) |
| Q2: Routing trigger | Explicit `/requirements-framework:refactor-orchestrate` command (deterministic per ADR-007). No magic detection. |
| Q3: Learning loop relation | Keep separate from `session-learning`. Two distinct systems. |
| Q4: Requirements bridging | No auto-satisfy. User runs `/arch-review` first by convention. |
| Q5: Source of truth | Plugin only. Globals at `~/.claude/skills/` and `~/.claude/agents/` get **deleted** after bundling. |
| Approach | **B**: Migration + adaptation pass (move + namespace + rewrite stale cross-references + light docs touch). |
| Commit policy | `.claude/refactor-orchestration/learnings.md` and `.claude/refactor-conventions.md` both **gitignored** by default. |
| Convention sheet scope | Scoped to refactor-orchestration only. Other framework commands do not read it in v1. |
| ADR | ADR-014 written as part of this migration. |
| Version bump | Existing `update-plugin-versions.sh` + auto-bump automation handles it. |

## File layout (post-migration)

### Source tree

```
plugins/requirements-framework/
├── .claude-plugin/plugin.json              ← minor version bump
├── agents/
│   ├── refactor-executor.md                ← NEW (moved + namespaced)
│   ├── refactor-investigator.md            ← NEW (moved + namespaced)
│   └── refactor-analyzer.md                ← NEW (moved + namespaced)
├── commands/
│   └── refactor-orchestrate.md             ← NEW (thin command invoking the skill)
└── skills/
    └── refactor-orchestration/             ← NEW (moved + edited)
        ├── SKILL.md                        ← edited (cross-refs rewritten)
        ├── plan-template.md                ← moved as-is
        ├── orchestrator-prompt-template.md ← edited (Task() subagent_type updates)
        ├── retrospective-template.md       ← moved as-is
        └── learnings.md.template           ← seed template (was learnings.md)
```

### Deletions

```
~/.claude/skills/refactor-orchestration/    ← DELETED entirely
~/.claude/agents/refactor-executor.md       ← DELETED
~/.claude/agents/refactor-investigator.md   ← DELETED
~/.claude/agents/refactor-analyzer.md       ← DELETED
```

### Touched (existing files, lightly edited)

```
plugins/requirements-framework/skills/requirements-framework-status/SKILL.md  ← mention /requirements-framework:refactor-orchestrate
plugins/requirements-framework/skills/requirements-framework-usage/SKILL.md   ← mention /requirements-framework:refactor-orchestrate
CLAUDE.md                                                                      ← document command + agent fanout
docs/adr/ADR-014-refactor-orchestration-bundled-skill.md                       ← NEW (rationale ADR)
```

## Components

### 6.1 `commands/refactor-orchestrate.md` (NEW)

Thin command (~40 lines) with frontmatter (`description`, `allowed-tools`, `git_hash` placeholder) and body that invokes `Skill: requirements-framework:refactor-orchestration`. Includes usage hint ("Run `/arch-review` first") and documents the two outputs + the fresh-session paste pattern. Mirrors existing thin-command wrappers like `brainstorm.md`.

### 6.2 `agents/refactor-{executor,investigator,analyzer}.md` (NEW, moved)

Each agent moved verbatim except two frontmatter field changes:

| Field | Before | After |
|---|---|---|
| `name:` | `refactor-executor` | **unchanged** (`refactor-executor`) — plugin loader applies namespace externally |
| `description:` | (unchanged) | Append " — part of the requirements-framework refactor-orchestration skill." |

All hard rules, workflows, output templates, model assignments stay byte-identical.

### 6.3 `skills/refactor-orchestration/SKILL.md` (MOVED + edited)

Three edits:

- **Lines 59–61**: replace `~/.claude/agents/refactor-executor.md` etc. with namespaced subagent_type form.
- **Lines 71–83** ("If you use requirements-framework" table): rewrite framing from optional/coexistence to **bundled** ("This skill is part of requirements-framework. Recommended sequencing: `/requirements-framework:arch-review` → `/requirements-framework:refactor-orchestrate` → fresh session for execution").
- **Lines 104–118** (File map): point at `plugins/requirements-framework/` paths, not `~/.claude/`.

### 6.4 `skills/refactor-orchestration/orchestrator-prompt-template.md` (MOVED + edited)

Every `Task(subagent_type="refactor-{executor,investigator,analyzer}", ...)` invocation gets the `requirements-framework:` namespace prefix. Phase F's reference to the learnings.md path points at the writable per-user location `~/.claude/refactor-orchestration/learnings.md`, not the plugin install path.

A new **Prerequisites** block goes near the top of the BEGIN/END block:

```
PREREQUISITES (verify before continuing):
- Plugin installed: requirements-framework@requirements-framework
- Working tree clean: git status shows nothing to commit
- Baseline tests passing
```

### 6.5 `skills/refactor-orchestration/{plan,retrospective}-template.md` (MOVED, byte-identical)

Pure data templates. No content changes.

### 6.6 `skills/refactor-orchestration/learnings.md.template` (RENAMED from learnings.md)

The bundled file becomes a **seed template**. The analyzer's hard-rules section gains: *"If `~/.claude/refactor-orchestration/learnings.md` doesn't exist, copy from `plugins/requirements-framework/skills/refactor-orchestration/learnings.md.template` to the writable location, then proceed."*

This solves the persistence-state-inside-plugin-skill pattern cleanly.

### 6.7 Discovery skill touches

Single-line additions to `requirements-framework-status` and `requirements-framework-usage` SKILL.md bodies mentioning `/requirements-framework:refactor-orchestrate` in their command catalogs. No structural changes.

### 6.8 CLAUDE.md update

Small subsection under "Testing Plugin Components":

```
**New: refactor orchestration**
- `/requirements-framework:refactor-orchestrate` — multi-layer top-down refactor workflow
- Agents: `requirements-framework:refactor-{executor,investigator,analyzer}`
- Produces: `.claude/plans/<slug>.md` + `<slug>-orchestrator-prompt.md`
- Execution happens in a fresh `claude` session by pasting the prompt
- Recommended sequencing: /requirements-framework:arch-review → /requirements-framework:refactor-orchestrate → fresh session
```

## Data flow

### Session A — Planning (user's current session)

```
/requirements-framework:refactor-orchestrate
  → Command runs deterministic orchestrator steps (see Task 11 of the impl plan)
  → Invokes Skill: requirements-framework:refactor-orchestration
  → Stage 1: 2× parallel Explore agents (inventory + ADRs)
            + read .claude/refactor-conventions.md if exists
  → Stage 2: top-down design + export manifest
  → Stage 3: context7 library-claim validation (non-optional)
  → Stage 4: harmonization pass
  → Stage 5: write .claude/plans/<YYYY-MM-DD>-<slug>.md
  → Stage 6: chunk queue design
  → Stage 7: write .claude/plans/<slug>-orchestrator-prompt.md (BEGIN/END markers)
  → Terminate with paste-instructions
```

The framework's blocking gates are **not** auto-satisfied. User runs `/arch-review` first if those gates are required.

### Session B — Execution (fresh `claude` invocation)

```
Paste orchestrator block between BEGIN/END markers
  → Prerequisites check (plugin installed, tree clean, baseline tests pass)
  → Phase A: Baseline verification (ruff, tests, import smoke)
  → Phase B–D: Chunk queue dispatch loop
       for chunk in queue:
         Task(subagent_type="requirements-framework:refactor-executor",
              prompt="apply plan §X to files Y...")
         review executor's report
         if simple issue: retry (max 2x)
         if complex issue: Task(subagent_type="requirements-framework:refactor-investigator")
         if blocked: AskUserQuestion → user picks path
         commit atomically (one chunk = one commit)
  → Phase E: Final smoke (full ruff + collect + branch tests)
  → Phase F: Task(subagent_type="requirements-framework:refactor-analyzer")
       ├─ Read global ledger: ~/.claude/refactor-orchestration/learnings.md (seed if missing)
       ├─ Read project ledger: .claude/refactor-orchestration/learnings.md (create if missing)
       ├─ Classify each observation: global vs project (default project on ambiguity)
       ├─ Write retrospective: .claude/plans/<slug>-retrospective.md
       ├─ Append to BOTH ledgers per classification
       ├─ Promote count=3 observations:
       │    global → AskUserQuestion against 5 plugin buckets
       │    project → AskUserQuestion against .claude/refactor-conventions.md (gitignored)
       └─ On approval, apply diffs (plugin path or project path respectively)
```

## Two-tier learning architecture

| Tier | Ledger location | Observation type | Promotes against |
|---|---|---|---|
| **Global** | `~/.claude/refactor-orchestration/learnings.md` (seeded from plugin template) | About the **orchestration system itself**: template gaps, executor retry patterns, investigator behavior, model-tier mismatches | The 5 plugin buckets: `SKILL.md`, `plan-template.md`, `orchestrator-prompt-template.md`, `refactor-executor.md`, `refactor-investigator.md` |
| **Project** | `.claude/refactor-orchestration/learnings.md` (gitignored) | About **this codebase's quirks**: naming conventions, layer rules, repo-specific anti-patterns, files that always need touching together | `.claude/refactor-conventions.md` (gitignored, auto-grown by promotions) |

### Classifier logic (new step in `refactor-analyzer.md` workflow, between current steps 4 and 5)

```
4.5. Classify each extracted observation:
     - If the observation describes behavior of the orchestration system
       (template, agent, executor/investigator workflow), tag as global.
     - If the observation describes a repo-specific rule, convention,
       layer constraint, or recurring local pattern, tag as project.
     - If ambiguous, prefer project (less surprise: edits stay scoped).
```

Steps 5 onward (read prior ledger, increment counts, write retrospective, propose diffs) run **twice**: once per ledger.

### `.claude/refactor-conventions.md` auto-grown sections

```
# Refactor Conventions for <repo-name>

## Layer rules
- (auto-grown from rule-of-three promotions)

## Naming & API patterns
- (auto-grown)

## Cross-cutting checklists
- (auto-grown)

## Known anti-patterns
- (auto-grown)
```

Each promoted line gets a footnote: `<!-- promoted from learning <obs-slug> on YYYY-MM-DD, count=3 -->`. Easy to audit, revertable via git history (when the user opts to commit).

## Error handling (fail-open posture)

| Scenario | Behavior |
|---|---|
| Plugin missing in Session B | Orchestrator's prerequisites block detects, fails fast with clear install instruction. |
| First run — no global learnings.md | Analyzer seeds from `learnings.md.template`, then proceeds. |
| First run — no project learnings.md | Analyzer creates empty ledger at `.claude/refactor-orchestration/learnings.md`. |
| First run — no conventions.md | Stage 1 reads conditionally; missing = no project conventions to seed with. Sheet created only on first project-tier promotion (count=3). |
| context7 unavailable in Stage 3 | Skill stops with retry instruction. **No escape hatch** — the skill's own design declares Stage 3 non-optional. |
| Chunk dispatch failures (Phase B–D) | Existing retry + escalate logic in current SKILL.md applies unchanged. |
| Stale globals still exist | Migration deletes them as a hard step; post-delete verification step in migration plan. |
| Analyzer proposes diff against locally-modified file | Existing AskUserQuestion flow lets user reject or modify. No clobbering without approval. |

## Versioning, sync, distribution

- **Plugin version bump**: handled by existing `update-plugin-versions.sh` + auto-bump automation.
- **`git_hash` regeneration**: `./update-plugin-versions.sh` picks up all 9 new/moved files automatically (scan covers `plugins/requirements-framework/{commands,agents,skills}/**.md`).
- **`sync.sh`**: no changes needed (we don't touch `hooks/`). Run `./sync.sh status` before committing to confirm no drift.
- **Marketplace publish ritual** (post-merge): `/plugin uninstall` → `/plugin marketplace update` → `/plugin install`.
- **Dev install for iteration**: `claude --plugin-dir ~/Tools/claude-requirements-framework/plugin`.

## ADR-014

To be written as part of the migration at `docs/adr/ADR-014-refactor-orchestration-bundled-skill.md`. Captures the rationale for:

1. Bundled vs standalone/symlinked installation
2. Explicit command routing (no detection magic)
3. No auto-satisfy of framework requirements
4. Two-tier learning (global plugin templates + project conventions)
5. Three-model-tier fanout pattern (Haiku executor, Sonnet investigator, Sonnet analyzer) as a new framework pattern

ADR-014 ships **with** the migration, not as a follow-up. It locks in the brainstorm answers.

## Testing & verification

### Static verification (pre-commit, automated)

```bash
# 1. Plugin manifest is valid JSON
python3 -c "import json; json.load(open('plugins/requirements-framework/.claude-plugin/plugin.json'))"

# 2. All agent frontmatter parses + names are namespaced
for f in plugins/requirements-framework/agents/refactor-*.md; do
  python3 -c "
import yaml
content = open('$f').read()
header = content.split('---', 2)[1]
data = yaml.safe_load(header)
assert data['name'].startswith('requirements-framework:'), f\"agent {data['name']} not namespaced\"
print('$f', 'OK')
"
done

# 3. update-plugin-versions.sh --check shows expected files
./update-plugin-versions.sh --check

# 4. sync.sh status confirms no drift
./sync.sh status

# 5. No lingering ~/.claude/agents/refactor-* references
rg -n '~/\.claude/agents/refactor-' plugins/ docs/ CLAUDE.md
# Expected: zero hits

# 6. No un-namespaced agent refs in moved skill files
rg -n 'subagent_type[^"]+"refactor-(executor|investigator|analyzer)"' \
   plugins/requirements-framework/skills/refactor-orchestration/
# Expected: zero hits
```

### Live-reload smoke test (dev install)

```bash
claude --plugin-dir ~/Tools/claude-requirements-framework/plugin
```

1. `/help` shows `/requirements-framework:refactor-orchestrate` in command list
2. Subagent registration shows `requirements-framework:refactor-{executor,investigator,analyzer}`
3. Running `/requirements-framework:refactor-orchestrate` against a trivial target produces both output files at `.claude/plans/`

### Fresh-session execution smoke (one-time, before merging)

In a second `claude` session, paste the orchestrator-prompt block. Confirm:
- Phase A baseline checks run
- First chunk dispatches to `requirements-framework:refactor-executor` (or fails cleanly on a zero-chunk target)
- Phase F dispatches the analyzer
- Both ledger files materialize at expected paths

### Marketplace install smoke (post-merge)

```bash
/plugin uninstall requirements-framework@requirements-framework
/plugin marketplace update requirements-framework
/plugin install requirements-framework@requirements-framework
```

Repeat the live-reload checklist in a marketplace-backed session.

### Out of scope for v1

- Real multi-layer refactor end-to-end as a test gate.
- Cross-version stability tests.
- Performance benchmarks.

## Open questions / known unknowns

- **Will `update-plugin-versions.sh` scan loop find files in `skills/refactor-orchestration/`?** Likely yes given existing patterns, but verify with `--check` before committing.
- **Does the marketplace install path materialize `learnings.md.template` correctly?** Plugin install copies plugin tree as-is; the seed-on-first-run logic in the analyzer handles the writable copy. Should Just Work but worth confirming via the post-merge smoke.
- **Will rule-of-three observations promote frequently or rarely in real use?** Unknown until real refactors run. If frequent, the gitignored convention sheet may want a "stabilization" period before opt-in commit. Re-evaluate after 3+ real runs.

## Implementation plan reference

The companion implementation plan will be produced via `requirements-framework:writing-plans` at:

`docs/plans/2026-05-18-refactor-orchestration-integration-plan.md`

That plan will break this design into atomic commits with explicit ordering, file paths, and verification steps per chunk.
