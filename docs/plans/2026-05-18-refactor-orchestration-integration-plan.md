# Refactor Orchestration Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use requirements-framework:executing-plans to implement this plan task-by-task.

**Goal:** Bundle the refactor-orchestration skill and its three supporting agents into the requirements-framework plugin, add an explicit `/refactor-orchestrate` command, implement two-tier learning (global plugin templates + project conventions), and delete the existing global copies at `~/.claude/`.

**Architecture:** Mechanical migration with adaptation pass (Approach B from the design doc). Source of truth becomes the plugin; agents get namespaced as `requirements-framework:refactor-*`; the analyzer agent gains a classifier step and seed-on-first-run logic for the global ledger. No auto-detection routing, no auto-satisfy of framework requirements — user invokes the command explicitly after running `/arch-review` by convention.

**Tech Stack:** Markdown (skill/agent definitions), YAML frontmatter, JSON (plugin manifest), Bash for verification, ripgrep for static checks.

**Design reference:** `docs/plans/2026-05-18-refactor-orchestration-integration-design.md`

**ADR reference:** This plan creates **ADR-014** (the design doc mistakenly references ADR-013, which already exists — `ADR-013-standardized-agent-output-format.md`).

---

## Pre-flight

Verify clean state before starting:

```bash
git status              # Expected: clean working tree
git branch --show-current   # Expected: master
```

If working tree is dirty, stash or commit first.

---

### Task 1: Create feature branch

**Files:** none (git operation only)

**Step 1: Create and switch to feature branch**

```bash
git checkout -b feat/refactor-orchestration-bundle
```

**Step 2: Verify**

```bash
git branch --show-current
# Expected: feat/refactor-orchestration-bundle
```

**Step 3: Mark requirement satisfied**

The `protected_branch` requirement auto-satisfies on non-main branches; no manual req call needed.

---

### Task 2: Fix the ADR reference in the design doc

The design doc references "ADR-013" but that number is taken. Update to ADR-014.

**Files:**
- Modify: `docs/plans/2026-05-18-refactor-orchestration-integration-design.md`

**Step 1: Replace all ADR-013 references with ADR-014**

```bash
sed -i.bak 's/ADR-013/ADR-014/g' docs/plans/2026-05-18-refactor-orchestration-integration-design.md
rm docs/plans/2026-05-18-refactor-orchestration-integration-design.md.bak
```

**Step 2: Replace the filename reference too**

```bash
sed -i.bak 's|013-refactor-orchestration-bundled-skill|ADR-014-refactor-orchestration-bundled-skill|g' \
  docs/plans/2026-05-18-refactor-orchestration-integration-design.md
rm docs/plans/2026-05-18-refactor-orchestration-integration-design.md.bak
```

**Step 3: Verify**

```bash
rg -n 'ADR-013' docs/plans/2026-05-18-refactor-orchestration-integration-design.md
# Expected: zero hits
rg -n 'ADR-014' docs/plans/2026-05-18-refactor-orchestration-integration-design.md
# Expected: 2 hits (one in the body, one in the implementation plan reference)
```

**Step 4: Commit**

```bash
git add docs/plans/2026-05-18-refactor-orchestration-integration-design.md
git commit -m "docs: correct ADR number in refactor-orchestration design (013 → 014)"
```

---

### Task 3: Write ADR-014

**Files:**
- Create: `docs/adr/ADR-014-refactor-orchestration-bundled-skill.md`

**Step 1: Write the ADR**

```markdown
# ADR-014: Refactor Orchestration via Bundled Skill + Three-Agent Fanout

## Status
Approved (2026-05-18)

## Context

The framework gained access to a new skill, `refactor-orchestration`, that captures a workflow for multi-layer top-down refactors too large for a single session. The skill produces a frozen plan plus an orchestrator-prompt that runs in a fresh `claude` session, dispatching mechanical chunks to a Haiku executor and escalating contradictions to a Sonnet investigator. A final Sonnet analyzer writes a retrospective and grows a learnings ledger via rule-of-three promotion to its own templates.

The skill was initially installed globally at `~/.claude/skills/refactor-orchestration/` with its three agents at `~/.claude/agents/refactor-{executor,investigator,analyzer}.md`. Its own SKILL.md declares a coexistence mapping with `requirements-framework`, framing the plugin as optional.

This ADR records the decision to **adopt the skill as a first-class part of the framework** rather than leave it as a global side-installation.

Key considerations:
1. **Source of truth** — two installation locations risk drift.
2. **Discoverability** — bundling makes `/refactor-orchestrate` discoverable through standard plugin channels.
3. **Learning loop ownership** — the analyzer's rule-of-three promotion is a novel self-evolving pattern; merging it with the framework's existing `session-learning` system would dilute both.
4. **Routing surface** — auto-detecting "this refactor is large" via heuristics adds magic that's hard to predict and easy to abuse.

## Decision

**Bundle the skill, namespace its three agents, add a thin `/refactor-orchestrate` command. Keep the skill's tight self-contained design intact.**

### Brainstorm decisions captured

| Question | Decision |
|---|---|
| End-state | Bundled into `plugins/requirements-framework/`. Globals at `~/.claude/` deleted. |
| Routing | Explicit `/refactor-orchestrate` command. No auto-detection from branch_size or touched-file heuristics. |
| Requirements bridging | None. User runs `/arch-review` first by convention. The skill itself satisfies no framework requirements. |
| Learning loop relation | Separate from `session-learning`. Two distinct systems with non-overlapping targets. |
| Source of truth | Plugin only. Agents namespaced as `requirements-framework:refactor-*`. |

### Two-tier learning architecture

The skill's existing single-ledger design extends to two tiers:

- **Global ledger** at `~/.claude/refactor-orchestration/learnings.md` (seeded from a plugin template on first run). Promotes against the 5 plugin buckets: `SKILL.md`, `plan-template.md`, `orchestrator-prompt-template.md`, `refactor-executor.md`, `refactor-investigator.md`.
- **Project ledger** at `.claude/refactor-orchestration/learnings.md` (gitignored by default). Promotes against `.claude/refactor-conventions.md` (gitignored, auto-grown by promotions).

The analyzer's workflow gains a classifier step (between current steps 4 and 5) that tags each observation as global or project, defaulting to project on ambiguity.

The convention sheet is **scoped to refactor-orchestration only** in v1; other framework commands (`/arch-review`, `/writing-plans`, `/brainstorming`) do not read it. Cross-command reuse may be considered in a follow-up after real-use data.

### Three-model-tier fanout (a new framework pattern)

This is the first framework component to formally specify model tiers for its agent fanout:

- `refactor-executor` (Haiku) — mechanical chunk execution
- `refactor-investigator` (Sonnet) — read-only diagnosis of plan-vs-reality contradictions
- `refactor-analyzer` (Sonnet) — retrospective + rule-of-three promotion

Existing framework agents do not pin model tiers; the convention is "use what's available." This skill's reliance on the Haiku/Sonnet split for cost-and-latency tuning is acknowledged as a new pattern. It does NOT propagate to other agents in v1 — only refactor-orchestration uses model pinning.

## Consequences

### Positive

- Single source of truth eliminates drift.
- `/refactor-orchestrate` becomes discoverable via standard plugin channels.
- ADRs, brainstorm decisions, and the skill artifacts now version together.
- Two-tier learning splits global plugin-template evolution from project-specific convention growth, keeping blast radius proportional to observation scope.

### Negative

- Plugin install becomes a prerequisite for using the skill (previously could run standalone).
- The auto-grown `.claude/refactor-conventions.md` (gitignored) is per-developer state in v1; team adoption requires opt-in commit policy.
- Model-tier pinning creates a precedent that other agents may or may not adopt. ADR-014 explicitly does not prescribe it for other components.

### Neutral

- The orchestrator prompt still runs in a fresh `claude` session by paste. This is intrinsic to the skill's design (separation of planning context from execution context) and not affected by bundling.
- No auto-satisfy of framework requirements means the user must explicitly run `/arch-review` if those gates are required for the work. Documented in the command's body and in CLAUDE.md.

## Implementation reference

See `docs/plans/2026-05-18-refactor-orchestration-integration-plan.md`.
```

**Step 2: Verify**

```bash
ls docs/adr/ADR-014-refactor-orchestration-bundled-skill.md
# Expected: file listed (no "No such file")
```

**Step 3: Commit**

```bash
git add docs/adr/ADR-014-refactor-orchestration-bundled-skill.md
git commit -m "docs(adr): ADR-014 refactor orchestration via bundled skill"
```

---

### Task 4: Migrate refactor-executor agent

**Files:**
- Create: `plugins/requirements-framework/agents/refactor-executor.md` (copied from `~/.claude/agents/refactor-executor.md` with two frontmatter changes)

**Step 1: Copy the file**

```bash
cp ~/.claude/agents/refactor-executor.md plugins/requirements-framework/agents/refactor-executor.md
```

**Step 2: Update the `name:` field**

Use Edit to change:
- Old: `name: refactor-executor`
- New: `name: requirements-framework:refactor-executor`

**Step 3: Update the `description:` field**

Use Edit to append " — part of the requirements-framework refactor-orchestration skill." to the description string (preserving the existing description).

**Step 4: Verify**

```bash
python3 -c "
import yaml
content = open('plugins/requirements-framework/agents/refactor-executor.md').read()
header = content.split('---', 2)[1]
data = yaml.safe_load(header)
assert data['name'] == 'requirements-framework:refactor-executor', f'name={data[\"name\"]}'
assert 'requirements-framework refactor-orchestration' in data['description']
print('OK')
"
# Expected: OK
```

**Step 5: Commit**

```bash
git add plugins/requirements-framework/agents/refactor-executor.md
git commit -m "feat(agents): bundle refactor-executor (Haiku chunk executor)"
```

---

### Task 5: Migrate refactor-investigator agent

**Files:**
- Create: `plugins/requirements-framework/agents/refactor-investigator.md`

**Step 1: Copy the file**

```bash
cp ~/.claude/agents/refactor-investigator.md plugins/requirements-framework/agents/refactor-investigator.md
```

**Step 2: Update `name:` field**

- Old: `name: refactor-investigator`
- New: `name: requirements-framework:refactor-investigator`

**Step 3: Update `description:` field**

Append " — part of the requirements-framework refactor-orchestration skill."

**Step 4: Verify**

```bash
python3 -c "
import yaml
content = open('plugins/requirements-framework/agents/refactor-investigator.md').read()
header = content.split('---', 2)[1]
data = yaml.safe_load(header)
assert data['name'] == 'requirements-framework:refactor-investigator'
assert 'requirements-framework refactor-orchestration' in data['description']
print('OK')
"
# Expected: OK
```

**Step 5: Commit**

```bash
git add plugins/requirements-framework/agents/refactor-investigator.md
git commit -m "feat(agents): bundle refactor-investigator (Sonnet diagnostician)"
```

---

### Task 6: Migrate refactor-analyzer agent (base move only)

**Files:**
- Create: `plugins/requirements-framework/agents/refactor-analyzer.md`

**Step 1: Copy the file**

```bash
cp ~/.claude/agents/refactor-analyzer.md plugins/requirements-framework/agents/refactor-analyzer.md
```

**Step 2: Update `name:` field**

- Old: `name: refactor-analyzer`
- New: `name: requirements-framework:refactor-analyzer`

**Step 3: Update `description:` field**

Append " — part of the requirements-framework refactor-orchestration skill."

**Step 4: Verify**

```bash
python3 -c "
import yaml
content = open('plugins/requirements-framework/agents/refactor-analyzer.md').read()
header = content.split('---', 2)[1]
data = yaml.safe_load(header)
assert data['name'] == 'requirements-framework:refactor-analyzer'
assert 'requirements-framework refactor-orchestration' in data['description']
print('OK')
"
# Expected: OK
```

**Step 5: Commit**

```bash
git add plugins/requirements-framework/agents/refactor-analyzer.md
git commit -m "feat(agents): bundle refactor-analyzer (Sonnet retrospective writer)"
```

(Task 10 will enhance this agent with the two-tier classifier and seed-on-first-run logic — keeping the base move atomic and separate.)

---

### Task 7: Migrate skill folder + rename learnings.md to seed template

**Files:**
- Create: `plugins/requirements-framework/skills/refactor-orchestration/SKILL.md`
- Create: `plugins/requirements-framework/skills/refactor-orchestration/plan-template.md`
- Create: `plugins/requirements-framework/skills/refactor-orchestration/orchestrator-prompt-template.md`
- Create: `plugins/requirements-framework/skills/refactor-orchestration/retrospective-template.md`
- Create: `plugins/requirements-framework/skills/refactor-orchestration/learnings.md.template`

**Step 1: Create the skill directory**

```bash
mkdir -p plugins/requirements-framework/skills/refactor-orchestration
```

**Step 2: Copy the four template files byte-identically**

```bash
cp ~/.claude/skills/refactor-orchestration/SKILL.md \
   plugins/requirements-framework/skills/refactor-orchestration/SKILL.md

cp ~/.claude/skills/refactor-orchestration/plan-template.md \
   plugins/requirements-framework/skills/refactor-orchestration/plan-template.md

cp ~/.claude/skills/refactor-orchestration/orchestrator-prompt-template.md \
   plugins/requirements-framework/skills/refactor-orchestration/orchestrator-prompt-template.md

cp ~/.claude/skills/refactor-orchestration/retrospective-template.md \
   plugins/requirements-framework/skills/refactor-orchestration/retrospective-template.md
```

**Step 3: Copy learnings.md as a seed template**

```bash
cp ~/.claude/skills/refactor-orchestration/learnings.md \
   plugins/requirements-framework/skills/refactor-orchestration/learnings.md.template
```

**Step 4: Verify all 5 files exist**

```bash
ls plugins/requirements-framework/skills/refactor-orchestration/
# Expected: SKILL.md  learnings.md.template  orchestrator-prompt-template.md  plan-template.md  retrospective-template.md
```

**Step 5: Commit**

```bash
git add plugins/requirements-framework/skills/refactor-orchestration/
git commit -m "feat(skills): bundle refactor-orchestration skill folder

Includes SKILL.md, plan-template.md, orchestrator-prompt-template.md,
retrospective-template.md, and learnings.md.template (seed for global
ledger, copied to ~/.claude/refactor-orchestration/learnings.md on
first run by the refactor-analyzer agent).

Files are copied byte-identically from ~/.claude/skills/refactor-orchestration/.
Cross-reference edits happen in subsequent commits (Tasks 8 + 9)."
```

---

### Task 8: Edit SKILL.md — rewrite cross-references for bundled context

**Files:**
- Modify: `plugins/requirements-framework/skills/refactor-orchestration/SKILL.md`

**Step 1: Update agent path references (lines 59–61)**

Use Edit to replace:

```
- **`refactor-executor`** — Haiku subagent at `~/.claude/agents/refactor-executor.md`. Mechanical chunk execution. Reads only the referenced plan section, edits only the named files, verifies with ruff + import smoke. Does not redesign.
- **`refactor-investigator`** — Sonnet subagent at `~/.claude/agents/refactor-investigator.md`. Read-only. Diagnoses plan-vs-reality contradictions and proposes 2-3 solution paths.
- **`refactor-analyzer`** — Sonnet subagent at `~/.claude/agents/refactor-analyzer.md`. Read-mostly. Writes the retrospective report + learnings.md; proposes template/agent diffs via AskUserQuestion. NEVER edits past plans/orchestrator prompts.
```

with:

```
- **`requirements-framework:refactor-executor`** — Haiku subagent. Mechanical chunk execution. Reads only the referenced plan section, edits only the named files, verifies with ruff + import smoke. Does not redesign.
- **`requirements-framework:refactor-investigator`** — Sonnet subagent. Read-only. Diagnoses plan-vs-reality contradictions and proposes 2-3 solution paths.
- **`requirements-framework:refactor-analyzer`** — Sonnet subagent. Read-mostly. Writes the retrospective report + learnings.md; proposes template/agent diffs via AskUserQuestion. NEVER edits past plans/orchestrator prompts.
```

**Step 2: Rewrite the "If you use requirements-framework" section (lines 71–83)**

Replace the entire `## If you use requirements-framework` section with:

```markdown
## Part of requirements-framework

This skill is bundled with the `requirements-framework` plugin. Recommended sequencing:

| Step | Command | What it covers |
|---|---|---|
| 1 | `/arch-review` | Satisfies the framework's planning gates (commit_plan, adr_reviewed, tdd_planned, solid_reviewed) for the upcoming work. |
| 2 | `/refactor-orchestrate` | Stages 1–7 of this skill: inventory, top-down design, library-claim validation, harmonization, plan write, chunk queue, orchestrator-prompt write. |
| 3 | Fresh `claude` session | Paste the orchestrator block. Stages 8–9 (execution + retrospective) run there. |

This skill does **not** auto-satisfy any framework requirements. Run `/arch-review` first if the project enforces them.

`req:session-reflect` is complementary to Stage 9 — does general session reflection. The analyzer mentions it in the retrospective's "Further reading" footer but does not invoke it.
```

**Step 3: Update the File map (lines 104–118)**

Replace:

```
~/.claude/
├── skills/refactor-orchestration/
│   ├── SKILL.md                            ← you are here
│   ├── plan-template.md                    ← §0–§13 structure for plans
│   ├── orchestrator-prompt-template.md     ← BEGIN/END block for orchestrators
│   ├── retrospective-template.md           ← §1–§7 structure for retrospectives
│   └── learnings.md                        ← cross-run observation ledger
└── agents/
    ├── refactor-executor.md                ← Haiku mechanical execution
    ├── refactor-investigator.md            ← Sonnet read-only diagnosis
    └── refactor-analyzer.md                ← Sonnet retrospective + rule-of-three promotion
```

with:

```
plugins/requirements-framework/
├── skills/refactor-orchestration/
│   ├── SKILL.md                            ← you are here
│   ├── plan-template.md                    ← §0–§13 structure for plans
│   ├── orchestrator-prompt-template.md     ← BEGIN/END block for orchestrators
│   ├── retrospective-template.md           ← §1–§7 structure for retrospectives
│   └── learnings.md.template               ← seed for the global ledger (first run only)
└── agents/
    ├── refactor-executor.md                ← Haiku mechanical execution
    ├── refactor-investigator.md            ← Sonnet read-only diagnosis
    └── refactor-analyzer.md                ← Sonnet retrospective + rule-of-three promotion

# Writable per-user state (created on first run):
~/.claude/refactor-orchestration/learnings.md   ← global ledger (seeded from .template)

# Per-project state (gitignored by default):
.claude/refactor-orchestration/learnings.md     ← project ledger
.claude/refactor-conventions.md                 ← auto-grown convention sheet
```

**Step 4: Verify**

```bash
# Confirm no remaining ~/.claude/agents/ references
rg -n '~/\.claude/agents/refactor-' \
   plugins/requirements-framework/skills/refactor-orchestration/SKILL.md
# Expected: zero hits

# Confirm "Part of requirements-framework" replaces the old section header
rg -n '^## Part of requirements-framework$' \
   plugins/requirements-framework/skills/refactor-orchestration/SKILL.md
# Expected: 1 hit

# Confirm old "If you use requirements-framework" header is gone
rg -n '^## If you use requirements-framework$' \
   plugins/requirements-framework/skills/refactor-orchestration/SKILL.md
# Expected: zero hits
```

**Step 5: Commit**

```bash
git add plugins/requirements-framework/skills/refactor-orchestration/SKILL.md
git commit -m "feat(skills): rewrite SKILL.md cross-refs for bundled context

- Agent refs use namespaced subagent_type form (requirements-framework:refactor-*)
- 'If you use requirements-framework' section becomes 'Part of requirements-framework'
- File map reflects plugin install paths + writable per-user/per-project state"
```

---

### Task 9: Edit orchestrator-prompt-template.md — namespace Task() calls + Prerequisites block

**Files:**
- Modify: `plugins/requirements-framework/skills/refactor-orchestration/orchestrator-prompt-template.md`

**Step 1: Read the file first**

```bash
# Read it to understand the BEGIN/END structure and current Task() call shape
cat plugins/requirements-framework/skills/refactor-orchestration/orchestrator-prompt-template.md
```

**Step 2: Namespace every Task() subagent_type reference**

Find every occurrence of:
- `subagent_type="refactor-executor"` → `subagent_type="requirements-framework:refactor-executor"`
- `subagent_type="refactor-investigator"` → `subagent_type="requirements-framework:refactor-investigator"`
- `subagent_type="refactor-analyzer"` → `subagent_type="requirements-framework:refactor-analyzer"`

Use Edit with `replace_all: true` for each pattern. The plain agent names should appear ONLY inside the namespaced strings after this step.

**Step 3: Add Prerequisites block near the top of the BEGIN/END section**

Locate the `=== BEGIN ORCHESTRATOR PROMPT ===` marker. Insert immediately after that line:

```markdown
## Prerequisites (verify before continuing)

Stop with a clear error message if ANY check fails:
- `requirements-framework@requirements-framework` plugin is installed
- Working tree is clean: `git status` shows nothing to commit
- Baseline tests passing (run the project's standard test command)

If the plugin is missing, instruct the user: "Install via `/plugin install requirements-framework@requirements-framework` then restart this session."
```

**Step 4: Update Phase F's learnings.md path reference**

Find the Phase F dispatch block. Update the analyzer prompt to reference both ledger paths:
- Global: `~/.claude/refactor-orchestration/learnings.md` (created from `learnings.md.template` if missing)
- Project: `.claude/refactor-orchestration/learnings.md` (created empty if missing)

**Step 5: Verify**

```bash
# Confirm no un-namespaced subagent_type references
rg -n 'subagent_type[^"]*"refactor-(executor|investigator|analyzer)"' \
   plugins/requirements-framework/skills/refactor-orchestration/orchestrator-prompt-template.md
# Expected: zero hits

# Confirm namespaced references exist
rg -n 'subagent_type[^"]*"requirements-framework:refactor-' \
   plugins/requirements-framework/skills/refactor-orchestration/orchestrator-prompt-template.md
# Expected: multiple hits

# Confirm Prerequisites block exists
rg -n '## Prerequisites \(verify before continuing\)' \
   plugins/requirements-framework/skills/refactor-orchestration/orchestrator-prompt-template.md
# Expected: 1 hit
```

**Step 6: Commit**

```bash
git add plugins/requirements-framework/skills/refactor-orchestration/orchestrator-prompt-template.md
git commit -m "feat(skills): namespace Task() calls + add Prerequisites block

Every refactor-{executor,investigator,analyzer} subagent_type now uses
the requirements-framework: namespace. New Prerequisites block at the
top of the BEGIN/END section catches plugin-missing failures fast in
the fresh-session execution path."
```

---

### Task 10: Enhance refactor-analyzer.md with two-tier classifier + seed-on-first-run logic

**Files:**
- Modify: `plugins/requirements-framework/agents/refactor-analyzer.md`

This is the most substantive content change in the migration.

**Step 1: Update the Hard Rules section**

Find the bullet that reads:

```
- Mostly READ-ONLY. You may Write ONLY the retrospective report (`.claude/plans/<plan-slug>-retrospective.md`) and append to `~/.claude/skills/refactor-orchestration/learnings.md`. Everything else via AskUserQuestion + Edit (only after approval).
```

Replace with:

```
- Mostly READ-ONLY. You may Write ONLY:
    - The retrospective report at `.claude/plans/<plan-slug>-retrospective.md`
    - The global ledger at `~/.claude/refactor-orchestration/learnings.md`
    - The project ledger at `.claude/refactor-orchestration/learnings.md`
    - The project convention sheet at `.claude/refactor-conventions.md` (only on count=3 promotions)
  Everything else (plugin templates, agent files) goes through AskUserQuestion + Edit (only after approval).
```

**Step 2: Add seed-on-first-run logic to Hard Rules**

Append a new bullet to the Hard Rules section:

```
- **Seed-on-first-run**: If `~/.claude/refactor-orchestration/learnings.md` does not exist, create the parent directory and copy from `plugins/requirements-framework/skills/refactor-orchestration/learnings.md.template`. If the plugin path is unreachable (e.g., dev install), initialize an empty ledger with the YAML header. Same logic for the project ledger at `.claude/refactor-orchestration/learnings.md` — create empty if missing.
```

**Step 3: Add Step 4.5 (classifier) to the Workflow section**

After the current step 4 (Check plan-vs-reality gaps) and before step 5 (Read learnings.md), insert:

```markdown
4.5. **Classify each extracted observation.** For each observation:
    - **Global tier** — describes behavior of the orchestration system itself: template gaps, executor retry patterns, investigator output deviations, model-tier mismatches, plan-template field omissions. Targets the 5 plugin buckets.
    - **Project tier** — describes a repo-specific rule, convention, layer constraint, or recurring local pattern: naming conventions, ADR-derived constraints, files that always need touching together, repo-specific anti-patterns. Targets `.claude/refactor-conventions.md`.
    - **Ambiguity rule**: default to project tier. Less surprise — edits stay scoped to one repo. If the same observation recurs across multiple repos, the classifier in those repos will tag it global next time.
```

**Step 4: Update steps 5–9 to iterate per ledger**

Find the existing step 5 (Read learnings.md). Replace with:

```markdown
5. **Read both ledgers.** Read `~/.claude/refactor-orchestration/learnings.md` (global) and `.claude/refactor-orchestration/learnings.md` (project). For each observation extracted in step 4, look up its `obs-slug` in the correctly-classified ledger only (per step 4.5). If found, bump `count` and `last_seen`. If not, create a new entry with `count=1`.
```

Find step 8 (Propose diffs). Replace with:

```markdown
8. **Propose diffs for promoted observations.** For each observation that hit `count=3` this run:
    - **Global-tier promotions**: AskUserQuestion against one of the 5 plugin buckets (`SKILL.md`, `plan-template.md`, `orchestrator-prompt-template.md`, `refactor-executor.md`, `refactor-investigator.md`). One question per diff. Max 3 diffs per retrospective.
    - **Project-tier promotions**: AskUserQuestion against `.claude/refactor-conventions.md`. If the file does not exist, create it with the standard 4-section structure (Layer rules / Naming & API patterns / Cross-cutting checklists / Known anti-patterns) before proposing the first promotion. Each promoted line gets a footnote: `<!-- promoted from learning <obs-slug> on YYYY-MM-DD, count=3 -->`.
    - If more than 3 promotions hit count=3 in a single run, list the top 3 by severity (impact × frequency) and note the rest in §5 of the retrospective as "deferred — re-evaluate next run".
```

**Step 5: Add the convention-sheet auto-creation logic to the Don'ts or Workflow appendix**

Add to the agent file (after step 10 of the workflow), a new appendix section:

```markdown
## Convention sheet template

When the project ledger triggers its first count=3 promotion and `.claude/refactor-conventions.md` does not exist, create it with this seed structure:

```
# Refactor Conventions for <repo-name>

> Auto-grown by refactor-analyzer rule-of-three promotions. Gitignored by default.
> Read by refactor-orchestration Stage 1 (inventory).

## Layer rules

## Naming & API patterns

## Cross-cutting checklists

## Known anti-patterns
```

Append promoted observations under the appropriate section based on the observation content. If no section fits cleanly, prefer "Known anti-patterns".
```

**Step 6: Verify**

```bash
# Confirm classifier step present
rg -n '^4\.5\. \*\*Classify each extracted observation' \
   plugins/requirements-framework/agents/refactor-analyzer.md
# Expected: 1 hit

# Confirm seed-on-first-run bullet present
rg -n 'Seed-on-first-run' \
   plugins/requirements-framework/agents/refactor-analyzer.md
# Expected: 1 hit

# Confirm both ledger paths referenced
rg -n '~/\.claude/refactor-orchestration/learnings\.md' \
   plugins/requirements-framework/agents/refactor-analyzer.md
# Expected: multiple hits

rg -n '\.claude/refactor-orchestration/learnings\.md' \
   plugins/requirements-framework/agents/refactor-analyzer.md
# Expected: multiple hits (including the global path matches)
```

**Step 7: Commit**

```bash
git add plugins/requirements-framework/agents/refactor-analyzer.md
git commit -m "feat(agents): two-tier learning + seed-on-first-run in refactor-analyzer

- Classifier step 4.5: tag observations as global or project; default
  project on ambiguity
- Seed-on-first-run logic for both ledger paths
- Steps 5 and 8 updated to iterate per tier (global → plugin buckets,
  project → .claude/refactor-conventions.md)
- Convention sheet template + auto-creation on first project-tier
  promotion

Implements ADR-014 two-tier learning architecture."
```

---

### Task 11: Create /refactor-orchestrate command

**Files:**
- Create: `plugins/requirements-framework/commands/refactor-orchestrate.md`

**Step 1: Write the thin command file**

```markdown
---
name: refactor-orchestrate
description: "Multi-layer top-down refactor workflow. Produces a frozen plan and a copy-paste orchestrator-prompt that runs in a fresh claude session, dispatching Haiku executor chunks and escalating contradictions to a Sonnet investigator. Run /arch-review first if your project enforces planning gates."
argument-hint: ""
allowed-tools: ["Bash", "Glob", "Grep", "Read", "Write", "Edit", "Task", "AskUserQuestion", "WebFetch"]
git_hash: uncommitted
---

Invoke the `requirements-framework:refactor-orchestration` skill and follow it exactly as presented to you.

**Recommended sequencing**: `/arch-review` → `/refactor-orchestrate` → fresh `claude` session (paste the orchestrator-prompt block).

This command produces two files at `.claude/plans/`:
- `<YYYY-MM-DD>-<slug>.md` — the validated design plan
- `<YYYY-MM-DD>-<slug>-orchestrator-prompt.md` — the copy-paste orchestrator block

Execution happens in a **fresh `claude` session** by pasting the prompt between the BEGIN/END markers. This command does NOT auto-satisfy framework requirements; run `/arch-review` first if the project enforces planning gates.
```

**Step 2: Verify**

```bash
# YAML frontmatter parses
python3 -c "
import yaml
content = open('plugins/requirements-framework/commands/refactor-orchestrate.md').read()
header = content.split('---', 2)[1]
data = yaml.safe_load(header)
assert data['name'] == 'refactor-orchestrate'
assert 'Task' in data['allowed-tools']
print('OK')
"
# Expected: OK
```

**Step 3: Commit**

```bash
git add plugins/requirements-framework/commands/refactor-orchestrate.md
git commit -m "feat(commands): add /refactor-orchestrate (thin skill invocation)"
```

---

### Task 12: Update plugin.json agents array

**Files:**
- Modify: `plugins/requirements-framework/.claude-plugin/plugin.json`

**Step 1: Add the 3 new agent paths**

Use Edit to append the following entries to the `agents` array (preserving existing entries):

```json
    "./agents/refactor-executor.md",
    "./agents/refactor-investigator.md",
    "./agents/refactor-analyzer.md"
```

**Step 2: Verify the JSON parses + new entries present**

```bash
python3 -c "
import json
data = json.load(open('plugins/requirements-framework/.claude-plugin/plugin.json'))
agents = data['agents']
for a in ['./agents/refactor-executor.md', './agents/refactor-investigator.md', './agents/refactor-analyzer.md']:
    assert a in agents, f'missing {a}'
print('OK; total agents:', len(agents))
"
# Expected: OK; total agents: 25
```

**Step 3: Commit**

```bash
git add plugins/requirements-framework/.claude-plugin/plugin.json
git commit -m "chore(plugin): register 3 refactor-orchestration agents in manifest"
```

---

### Task 13: Touch discovery skills (status + usage)

**Files:**
- Modify: `plugins/requirements-framework/skills/requirements-framework-status/SKILL.md`
- Modify: `plugins/requirements-framework/skills/requirements-framework-usage/SKILL.md`

**Step 1: Find the command catalog in each file**

```bash
rg -n '/arch-review|/deep-review|/refactor-orchestrate' \
   plugins/requirements-framework/skills/requirements-framework-status/SKILL.md \
   plugins/requirements-framework/skills/requirements-framework-usage/SKILL.md
```

**Step 2: Add /refactor-orchestrate one-liner to each**

Use Edit to add an entry alongside existing commands in each file. Suggested wording:

```
- `/refactor-orchestrate` — multi-layer top-down refactor workflow (produces plan + orchestrator-prompt for fresh-session execution)
```

**Step 3: Verify**

```bash
rg -n '/refactor-orchestrate' \
   plugins/requirements-framework/skills/requirements-framework-status/SKILL.md \
   plugins/requirements-framework/skills/requirements-framework-usage/SKILL.md
# Expected: at least 1 hit in each file
```

**Step 4: Commit**

```bash
git add plugins/requirements-framework/skills/requirements-framework-status/SKILL.md \
        plugins/requirements-framework/skills/requirements-framework-usage/SKILL.md
git commit -m "docs(skills): mention /refactor-orchestrate in discovery skills"
```

---

### Task 14: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Add a "Refactor Orchestration" subsection**

Locate the section "## Testing Plugin Components" or "## Plugin Component Versioning". Insert a new subsection:

```markdown
### Refactor Orchestration

The framework includes a bundled refactor-orchestration skill for multi-layer top-down refactors.

**Command**: `/refactor-orchestrate`

**Agents (Haiku/Sonnet/Sonnet fanout)**:
- `requirements-framework:refactor-executor` (Haiku) — mechanical chunk execution
- `requirements-framework:refactor-investigator` (Sonnet) — read-only diagnosis
- `requirements-framework:refactor-analyzer` (Sonnet) — retrospective + rule-of-three promotion

**Outputs**:
- `.claude/plans/<YYYY-MM-DD>-<slug>.md` — validated design plan
- `.claude/plans/<YYYY-MM-DD>-<slug>-orchestrator-prompt.md` — copy-paste orchestrator

**Execution model**: A planning session produces both files. The orchestrator block runs in a **fresh `claude` session** by paste — chunks dispatch atomically, one commit per chunk.

**Recommended sequencing**: `/arch-review` → `/refactor-orchestrate` → fresh session for execution.

**Two-tier learning** (refactor-analyzer):
- Global ledger: `~/.claude/refactor-orchestration/learnings.md` (seeded from plugin template)
- Project ledger: `.claude/refactor-orchestration/learnings.md` (gitignored)
- Project conventions: `.claude/refactor-conventions.md` (gitignored, auto-grown)

See `docs/adr/ADR-014-refactor-orchestration-bundled-skill.md` for design rationale.
```

**Step 2: Verify**

```bash
rg -n '^### Refactor Orchestration$' CLAUDE.md
# Expected: 1 hit

rg -n '/refactor-orchestrate' CLAUDE.md
# Expected: 1+ hits
```

**Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document /refactor-orchestrate workflow in CLAUDE.md"
```

---

### Task 15: Delete globals from ~/.claude/

This is the **point of no return** for source-of-truth migration. Run only after all previous tasks pass static verification.

**Step 1: Verify the plugin copies are byte-equivalent (excluding the frontmatter edits we made)**

```bash
# Quick sanity check: compare body content (excluding frontmatter) of one agent
diff <(awk 'BEGIN{p=0} /^---$/{c++; if(c==2)p=1; next} p' ~/.claude/agents/refactor-executor.md) \
     <(awk 'BEGIN{p=0} /^---$/{c++; if(c==2)p=1; next} p' plugins/requirements-framework/agents/refactor-executor.md)
# Expected: no diff (bodies identical)
```

**Step 2: Delete the global agent files**

```bash
rm ~/.claude/agents/refactor-executor.md
rm ~/.claude/agents/refactor-investigator.md
rm ~/.claude/agents/refactor-analyzer.md
```

**Step 3: Delete the global skill folder**

```bash
rm -rf ~/.claude/skills/refactor-orchestration
```

**Step 4: Verify deletion**

```bash
ls ~/.claude/skills/refactor-orchestration/ 2>/dev/null
# Expected: "No such file or directory" (zero output to stdout)

ls ~/.claude/agents/refactor-*.md 2>/dev/null
# Expected: "No such file or directory"
```

**Step 5: No commit needed** — these are outside the repo. The deletion is just runtime-state cleanup.

---

### Task 16: Run update-plugin-versions.sh

**Files:**
- Modify: every new/moved file in `plugins/requirements-framework/{agents,commands,skills}/` will have its `git_hash` frontmatter field updated.

**Step 1: Dry-run to preview affected files**

```bash
./update-plugin-versions.sh --check
```

Expected: lists 9 affected files (3 agents + 1 command + 5 skill files).

**Step 2: Apply hash updates**

```bash
./update-plugin-versions.sh
```

**Step 3: Verify hashes are no longer "uncommitted" for files we just committed**

```bash
rg -n '^git_hash: uncommitted' plugins/requirements-framework/agents/refactor-*.md
# Expected: zero hits

rg -n '^git_hash: uncommitted' plugins/requirements-framework/commands/refactor-orchestrate.md
# Expected: zero hits (or 1 hit if the command commit doesn't exist yet — re-run sequence if so)
```

**Step 4: Commit**

```bash
git add plugins/requirements-framework/
git commit -m "chore: update git_hash fields for refactor-orchestration components"
```

---

### Task 17: Static verification (the 6 design-doc checks)

No new commits — just assertions.

**Step 1: Plugin manifest valid JSON**

```bash
python3 -c "import json; json.load(open('plugins/requirements-framework/.claude-plugin/plugin.json'))"
# Expected: no output (no exception)
```

**Step 2: All 3 agent frontmatter parses + names are namespaced**

```bash
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
# Expected: 3 OK lines
```

**Step 3: update-plugin-versions.sh --verify confirms hashes current**

```bash
./update-plugin-versions.sh --verify
# Expected: exit 0; no drift reported
```

**Step 4: sync.sh status — confirm no hook drift**

```bash
./sync.sh status
# Expected: "In sync" or equivalent clean status
```

**Step 5: No lingering ~/.claude/agents/refactor-* references in plugin sources**

```bash
rg -n '~/\.claude/agents/refactor-' plugins/ docs/ CLAUDE.md
# Expected: zero hits
```

**Step 6: No un-namespaced agent refs in moved skill files**

```bash
rg -n 'subagent_type[^"]*"refactor-(executor|investigator|analyzer)"' \
   plugins/requirements-framework/skills/refactor-orchestration/
# Expected: zero hits
```

If ANY of these checks fail, **stop and investigate** before proceeding. Do not attempt to push.

---

### Task 18: Live-reload smoke test (manual)

**Step 1: Launch dev-install session**

In a separate terminal:

```bash
claude --plugin-dir ~/Tools/claude-requirements-framework/plugin
```

**Step 2: Verify command discoverability**

In that session, type `/help` and confirm `/refactor-orchestrate` appears in the command list.

**Step 3: Verify agent registration**

Ask the agent to list registered subagent types (or invoke `Task` with `subagent_type="requirements-framework:refactor-executor"` on a no-op prompt). Confirm all 3 namespaced agents are reachable.

**Step 4: Run /refactor-orchestrate on a trivial target**

Pick a small known-good area of the framework codebase (e.g., a single small skill or a small docs file). Run `/refactor-orchestrate` and confirm Stages 1–7 produce both output files at `.claude/plans/`.

**Step 5: No-op cleanup**

Discard the test plan files (they're per-project, gitignored under `.claude/plans/` per existing convention) or `git restore` them if accidentally tracked.

Stop the dev-install session.

This task has no commits — it's a manual verification gate.

---

### Task 19: Run /deep-review

Satisfies the `pre_pr_review` requirement.

```bash
# In your main claude session
/deep-review
```

Wait for the team-based review to complete. Address any blocking findings before proceeding to Task 20.

---

### Task 20: Run /codex-review

Satisfies the `codex_reviewer` requirement.

```bash
/codex-review
```

If Codex CLI is unavailable, the requirement may be skipped via the documented teammate-mode fallback. Otherwise wait for completion and address blocking findings.

---

### Task 21: Open the pull request

**Step 1: Push the feature branch**

```bash
git push -u origin feat/refactor-orchestration-bundle
```

**Step 2: Create the PR**

```bash
gh pr create --title "feat: bundle refactor-orchestration skill + 3 agents into plugin" --body "$(cat <<'EOF'
## Summary

- Bundle the refactor-orchestration skill and its three Haiku/Sonnet agents into `plugins/requirements-framework/`
- Add explicit `/refactor-orchestrate` command (no auto-detection)
- Implement two-tier learning: global plugin templates + project conventions
- Delete global copies at `~/.claude/skills/refactor-orchestration/` and `~/.claude/agents/refactor-*.md`

Design + decisions: `docs/plans/2026-05-18-refactor-orchestration-integration-design.md`
ADR: `docs/adr/ADR-014-refactor-orchestration-bundled-skill.md`

## Test plan

- [x] All 6 static verification checks pass (Task 17 in the implementation plan)
- [x] Live-reload smoke test confirms `/refactor-orchestrate` discoverability and agent registration (Task 18)
- [x] `/refactor-orchestrate` produces both output files on a trivial target
- [ ] Marketplace install smoke test (post-merge): `/plugin uninstall` → `marketplace update` → `install` → repeat live-reload checks
EOF
)"
```

---

## Post-merge follow-up (not part of this PR)

After merge:

1. Run the marketplace install ritual to confirm production publish path:
   ```bash
   /plugin uninstall requirements-framework@requirements-framework
   /plugin marketplace update requirements-framework
   /plugin install requirements-framework@requirements-framework
   ```
2. In a fresh session backed by the marketplace install, repeat the live-reload checklist (Task 18) to confirm production parity.
3. Optionally pilot `/refactor-orchestrate` on a real multi-layer refactor in another repo to start populating the learnings ledgers with real-world observations.

---

## References

- Design doc: `docs/plans/2026-05-18-refactor-orchestration-integration-design.md`
- ADR: `docs/adr/ADR-014-refactor-orchestration-bundled-skill.md` (created in Task 3)
- Existing related ADRs: ADR-012 (Agent Teams), ADR-013 (standardized agent output format)
- Plugin manifest: `plugins/requirements-framework/.claude-plugin/plugin.json`

## Sub-skills referenced

- `requirements-framework:executing-plans` — recommended for parallel-session execution of this plan
- `requirements-framework:subagent-driven-development` — recommended for in-session execution
- `requirements-framework:systematic-debugging` — if a verification step fails unexpectedly
- `requirements-framework:verification-before-completion` — before marking the migration done
- `requirements-framework:receiving-code-review` — when integrating `/deep-review` and `/codex-review` findings
