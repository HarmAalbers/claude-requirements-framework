# Refactor Orchestration Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use requirements-framework:executing-plans to implement this plan task-by-task.

**Goal:** Bundle the refactor-orchestration skill and its three supporting agents into the requirements-framework plugin, add an explicit `/requirements-framework:refactor-orchestrate` command, implement two-tier learning (global plugin templates + project conventions), and delete the existing global copies at `~/.claude/`.

**Architecture:** Mechanical migration with adaptation pass (Approach B from the design doc). Source of truth becomes the plugin. Per existing plugin convention, agent frontmatter `name:` stays bare (e.g., `name: refactor-executor`) — the plugin loader applies the `requirements-framework:` namespace externally for `subagent_type` dispatch and command invocation (`/requirements-framework:refactor-orchestrate`). The analyzer agent gains a classifier step and seed-on-first-run logic for the global ledger. No auto-detection routing, no auto-satisfy of framework requirements — user invokes the command explicitly after running `/arch-review` by convention.

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
2. **Discoverability** — bundling makes `/requirements-framework:refactor-orchestrate` discoverable through standard plugin channels.
3. **Learning loop ownership** — the analyzer's rule-of-three promotion is a novel self-evolving pattern; merging it with the framework's existing `session-learning` system would dilute both.
4. **Routing surface** — auto-detecting "this refactor is large" via heuristics adds magic that's hard to predict and easy to abuse.

## Decision

**Bundle the skill, register its three agents via the plugin manifest (frontmatter `name:` stays bare, namespace applied externally), add a deterministic `/requirements-framework:refactor-orchestrate` command per ADR-007. Keep the skill's tight self-contained design intact.**

### Brainstorm decisions captured

| Question | Decision |
|---|---|
| End-state | Bundled into `plugins/requirements-framework/`. Globals at `~/.claude/` deleted. |
| Routing | Explicit `/requirements-framework:refactor-orchestrate` command (deterministic per ADR-007). No auto-detection from branch_size or touched-file heuristics. |
| Why not Agent Teams | The orchestrator is a sequential pipeline (executor → optional investigator → analyzer). ADR-012's carve-out for sequential pipelines applies — `Task` dispatch is the right primitive, not Agent Teams. |
| Requirements bridging | None. User runs `/arch-review` first by convention. The skill itself satisfies no framework requirements. |
| Learning loop relation | Separate from `session-learning`. Two distinct systems with non-overlapping targets. |
| Source of truth | Plugin only. Agents become available as `requirements-framework:refactor-*` via plugin registration; frontmatter `name:` stays bare per plugin convention. |

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
- `/requirements-framework:refactor-orchestrate` becomes discoverable via standard plugin channels.
- ADRs, brainstorm decisions, and the skill artifacts now version together.
- Two-tier learning splits global plugin-template evolution from project-specific convention growth, keeping blast radius proportional to observation scope.

### Negative

- Plugin install becomes a prerequisite for using the skill (previously could run standalone).
- The auto-grown `.claude/refactor-conventions.md` (gitignored) is per-developer state in v1; team adoption requires opt-in commit policy.
- Model-tier pinning creates a precedent that other agents may or may not adopt. ADR-014 explicitly does not prescribe it for other components.
- Two-tier learning tier paths are hardcoded in the analyzer agent's prose (v1 limitation). Adding a third tier (e.g., team-level) would require editing the agent body. A future ADR may model tiers as data (`{scope, ledger_path, promotion_target, approval_policy}`) if the need arises.

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
- Create: `plugins/requirements-framework/agents/refactor-executor.md` (copied from `~/.claude/agents/refactor-executor.md` with description field change + ADR-013 output format alignment)

**Important — convention correction (from arch-review)**: agent frontmatter `name:` stays **bare** (`name: refactor-executor`). The plugin loader applies the `requirements-framework:` namespace externally. Verified by inspecting `plugins/requirements-framework/agents/code-reviewer.md` and other existing agents.

**Step 1: Copy the file**

```bash
cp ~/.claude/agents/refactor-executor.md plugins/requirements-framework/agents/refactor-executor.md
```

**Step 2: Update the `description:` field**

Use Edit to append " — part of the requirements-framework refactor-orchestration skill." to the description string (preserving the existing description). The `name:` field stays unchanged.

**Step 3: Align output format with ADR-013**

The existing executor report format uses bullets ("Files touched:", "Verification:", "Deviations from plan:", "Noticed-but-not-changed:"). ADR-013 standardizes review-agent output with `### CRITICAL:` / `### IMPORTANT:` / `### SUGGESTION:` markers and a `## Summary` section with verdict.

The executor is a code-applying agent, not a review agent. Apply ADR-013 minimally:
- Keep the existing "Files touched" / "Verification" / "Deviations" / "Noticed" sections (they are factual reporting, not findings).
- Add a final `## Summary` section per ADR-013 with: `verdict: SUCCESS | PARTIAL | FAILED | SKIPPED` (one of the ADR-013 defined verdicts). `SKIPPED` applies if the chunk was a no-op.
- The "Deviations from plan" bullets become `### IMPORTANT:` items when present.

Use Edit to update the `## Report format` section in the agent file accordingly.

**Step 4: Verify**

```bash
python3 -c "
import yaml
content = open('plugins/requirements-framework/agents/refactor-executor.md').read()
header = content.split('---', 2)[1]
data = yaml.safe_load(header)
assert data['name'] == 'refactor-executor', f'name should be bare, got {data[\"name\"]}'
assert 'requirements-framework refactor-orchestration' in data['description']
print('OK')
"
# Expected: OK

# Confirm ADR-013 alignment present
rg -n '^## Summary$' plugins/requirements-framework/agents/refactor-executor.md
# Expected: 1 hit
rg -n 'verdict:' plugins/requirements-framework/agents/refactor-executor.md
# Expected: 1+ hits
```

**Step 5: Commit**

```bash
git add plugins/requirements-framework/agents/refactor-executor.md
git commit -m "feat(agents): bundle refactor-executor (Haiku chunk executor)

Description field appended with framework attribution; name kept bare
per plugin convention (loader applies namespace externally).
Output format aligned with ADR-013 (Summary section + verdict)."
```

---

### Task 5: Migrate refactor-investigator agent

**Files:**
- Create: `plugins/requirements-framework/agents/refactor-investigator.md`

**Step 1: Copy the file**

```bash
cp ~/.claude/agents/refactor-investigator.md plugins/requirements-framework/agents/refactor-investigator.md
```

**Step 2: Update `description:` field**

Append " — part of the requirements-framework refactor-orchestration skill." to the description. The `name:` field stays bare (`name: refactor-investigator`) per plugin convention.

**Step 3: Align output format with ADR-013**

The existing investigator output template uses `Root cause:` / `Why the plan got this wrong:` / `Solution paths:` / `Recommended:`. Align with ADR-013:
- Keep `Root cause` and `Why the plan got this wrong` as factual sections.
- The `Solution paths` numbered list maps onto `### IMPORTANT:` items (each is a recommended path with trade-offs).
- The `Recommended:` line maps onto a `## Summary` section with `verdict: APPROVED` (recommendation is the verdict) plus `recommended_path: <number>`.

Use Edit to update the `## Output template` section.

**Step 4: Verify**

```bash
python3 -c "
import yaml
content = open('plugins/requirements-framework/agents/refactor-investigator.md').read()
header = content.split('---', 2)[1]
data = yaml.safe_load(header)
assert data['name'] == 'refactor-investigator', f'name should be bare, got {data[\"name\"]}'
assert 'requirements-framework refactor-orchestration' in data['description']
print('OK')
"
# Expected: OK

rg -n '^## Summary$' plugins/requirements-framework/agents/refactor-investigator.md
# Expected: 1 hit
```

**Step 5: Commit**

```bash
git add plugins/requirements-framework/agents/refactor-investigator.md
git commit -m "feat(agents): bundle refactor-investigator (Sonnet diagnostician)

Description field appended with framework attribution; name kept bare
per plugin convention. Output format aligned with ADR-013."
```

---

### Task 6: Migrate refactor-analyzer agent (base move only)

**Files:**
- Create: `plugins/requirements-framework/agents/refactor-analyzer.md`

**Step 1: Copy the file**

```bash
cp ~/.claude/agents/refactor-analyzer.md plugins/requirements-framework/agents/refactor-analyzer.md
```

**Step 2: Update `description:` field**

Append " — part of the requirements-framework refactor-orchestration skill." The `name:` field stays bare (`name: refactor-analyzer`) per plugin convention.

**Step 3: Align output format with ADR-013**

The analyzer produces a retrospective report (a `.md` file) plus proposed diffs surfaced via `AskUserQuestion`. ADR-013 alignment:
- The retrospective report is a separate artifact (`.claude/plans/<slug>-retrospective.md`); ADR-013 does not constrain its internal format.
- The analyzer's *report back to the orchestrator* (after a run completes) should follow ADR-013: `### IMPORTANT:` per promoted observation, `## Summary` with `verdict: SUCCESS | NO_PROMOTIONS | DEFERRED` and counts.

Use Edit to add a new `## Report format` section to the agent file specifying the post-run summary structure.

**Step 4: Verify**

```bash
python3 -c "
import yaml
content = open('plugins/requirements-framework/agents/refactor-analyzer.md').read()
header = content.split('---', 2)[1]
data = yaml.safe_load(header)
assert data['name'] == 'refactor-analyzer', f'name should be bare, got {data[\"name\"]}'
assert 'requirements-framework refactor-orchestration' in data['description']
print('OK')
"
# Expected: OK

rg -n '^## Report format$' plugins/requirements-framework/agents/refactor-analyzer.md
# Expected: 1 hit
```

**Step 5: Commit**

```bash
git add plugins/requirements-framework/agents/refactor-analyzer.md
git commit -m "feat(agents): bundle refactor-analyzer (Sonnet retrospective writer)

Description field appended with framework attribution; name kept bare
per plugin convention. Output format aligned with ADR-013 (Report
format section for post-run summary back to orchestrator)."
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
| 2 | `/requirements-framework:refactor-orchestrate` | Stages 1–7 of this skill: inventory, top-down design, library-claim validation, harmonization, plan write, chunk queue, orchestrator-prompt write. |
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

**Step 5: Update the Don'ts section to allow the new write target**

Find the bullet in `## Don'ts` that reads `"Don't propose edits to anything outside the 5 buckets"`. Replace with:

```
- Don't propose edits to anything outside the 5 plugin buckets OR `.claude/refactor-conventions.md`. The convention sheet is the only approved project-tier write target.
```

Same section already has a bullet "Don't auto-apply diffs. Always AskUserQuestion first." — that bullet applies to BOTH tiers and stays unchanged.

**Step 6: Add the convention-sheet auto-creation logic to the Workflow appendix**

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

**Step 7: Verify**

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

# Confirm Don'ts updated to allow conventions sheet
rg -n '\.claude/refactor-conventions\.md' \
   plugins/requirements-framework/agents/refactor-analyzer.md
# Expected: multiple hits (Hard Rules + Don'ts + Workflow appendix)
```

**Note — this is the SINGLE commit containing all two-tier behavior**: Task 10 isolates the entire two-tier learning enhancement to one commit. Rollback is `git revert <task-10-sha>`, after which the analyzer reverts to its pre-enhancement behavior (single ledger, no classifier, no convention sheet auto-creation). This addresses the codex finding that two-tier learning should be isolated as standalone commits.

**Step 8: Commit**

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

### Task 11: Create /requirements-framework:refactor-orchestrate command (deterministic per ADR-007)

**Files:**
- Create: `plugins/requirements-framework/commands/refactor-orchestrate.md`

**Important — ADR-007 compliance (from arch-review)**: thin-wrapper commands are explicitly prohibited. The command must follow the deterministic-orchestrator pattern modeled by `/deep-review`, `/arch-review`, `/quality-check`: numbered steps, scope acquisition via bash, defined conditionals, explicit `Task` dispatch, threshold-based verdict logic.

**Step 1: Write the deterministic command file**

```markdown
---
name: refactor-orchestrate
description: "Multi-layer top-down refactor workflow. Produces a validated plan and an orchestrator-prompt that runs in a fresh claude session, dispatching Haiku executor chunks and escalating contradictions to a Sonnet investigator."
argument-hint: "[<refactor-slug>]"
allowed-tools: ["Bash", "Glob", "Grep", "Read", "Write", "Edit", "Task", "AskUserQuestion", "WebFetch"]
git_hash: uncommitted
---

# Refactor Orchestration — Deterministic Orchestrator

Multi-layer top-down refactor workflow. Satisfies no framework requirements (run `/requirements-framework:arch-review` first if your project enforces planning gates).

**See ADR-014 for design rationale.**

## Deterministic Execution Workflow

You MUST follow these steps in exact order. Do not skip steps or interpret — execute as written.

### Step 0: Resolve refactor slug

If `` is provided, use as the refactor slug. Otherwise prompt the user once via AskUserQuestion for a short kebab-case slug. The slug becomes part of the output filenames.

```bash
SLUG=""
if [[ -z "$SLUG" ]]; then
  # Will be set after AskUserQuestion
  SLUG=""
fi
DATE="$(date +%Y-%m-%d)"
PLAN_PATH=".claude/plans/${DATE}-${SLUG}.md"
ORCH_PATH=".claude/plans/${DATE}-${SLUG}-orchestrator-prompt.md"
```

If either output file already exists, ask the user via AskUserQuestion: overwrite, append-date-suffix, or abort.

### Step 1: Pre-flight checks

```bash
# Working tree must be clean
git diff --quiet || { echo "Working tree dirty — commit or stash first." >&2; exit 2; }

# .claude/plans/ must exist or be creatable
mkdir -p .claude/plans

# Project conventions sheet (if present) is readable
if [ -f .claude/refactor-conventions.md ]; then
  echo "Found .claude/refactor-conventions.md — will be included in Stage 1 inventory"
fi
```

Stop with explicit error if any pre-flight fails.

### Step 2: Invoke skill stage 1 (Inventory)

Dispatch two parallel Explore agents:

```
Task(subagent_type="Explore", prompt="...catalogue current layer state of target area...")
Task(subagent_type="Explore", prompt="...extract rules from relevant ADRs/design docs/conventions sheet...")
```

Collect "what is" + "what should be" reports.

### Step 3: Invoke skill stages 2–4 (Top-down design, context7 validation, harmonization)

Per the `requirements-framework:refactor-orchestration` skill workflow. Each stage produces a section of the in-progress plan content held in memory.

Context7 validation (Stage 3) is non-optional. Stop if context7 is unreachable; instruct user to retry.

### Step 4: Persist plan

Write the validated plan to `$PLAN_PATH` using the skill's `plan-template.md` structure (§0–§13).

### Step 5: Generate chunk queue

Decompose the plan into atomic chunks (one chunk = one commit). Group into phases (typically: shared primitives → protocols/contracts → per-feature rewrites → structural tests → smoke validation).

### Step 6: Persist orchestrator-prompt

Write the copy-paste orchestrator to `$ORCH_PATH` using the skill's `orchestrator-prompt-template.md`. The block must include:
- `=== BEGIN ORCHESTRATOR PROMPT ===` / `=== END ORCHESTRATOR PROMPT ===` markers
- Prerequisites block (plugin installed, working tree clean, baseline tests pass)
- Chunk queue
- Phase A–F dispatch logic
- Subagent_type strings using `requirements-framework:refactor-{executor,investigator,analyzer}` namespaced form

### Step 7: Verify outputs

```bash
[ -f "$PLAN_PATH" ] && [ -f "$ORCH_PATH" ] || { echo "Output files missing." >&2; exit 2; }

# Confirm BEGIN/END markers in orchestrator-prompt
grep -q '=== BEGIN ORCHESTRATOR PROMPT ===' "$ORCH_PATH" || exit 2
grep -q '=== END ORCHESTRATOR PROMPT ===' "$ORCH_PATH" || exit 2

# Confirm subagent_type uses namespaced form
grep -E 'subagent_type[^"]*"refactor-(executor|investigator|analyzer)"' "$ORCH_PATH" && {
  echo "Found un-namespaced subagent_type references" >&2; exit 2;
}
```

### Step 8: Final report to user

Print:
```
Plan written to: $PLAN_PATH
Orchestrator-prompt written to: $ORCH_PATH

NEXT STEPS:
1. Review the plan at $PLAN_PATH
2. Open a FRESH claude session (not this one)
3. Paste the block between === BEGIN ORCHESTRATOR PROMPT === and === END ORCHESTRATOR PROMPT === markers in $ORCH_PATH
4. The orchestrator runs Phases A–F; commits atomically per chunk; finishes with refactor-analyzer retrospective
```

This command does NOT auto-satisfy framework requirements. Run `/requirements-framework:arch-review` first if planning gates are required.

### Verdict

- **SUCCESS**: both output files exist, all verifications pass.
- **FAILED**: any pre-flight or verification step failed; report exit code with reason.
- **ABORTED**: user chose to abort during file-collision handling.
```

**Step 2: Verify**

```bash
# YAML frontmatter parses
python3 -c "
import yaml
content = open('plugins/requirements-framework/commands/refactor-orchestrate.md').read()
header = content.split('---', 2)[1]
data = yaml.safe_load(header)
assert data['name'] == 'refactor-orchestrate', f'name should be bare, got {data[\"name\"]}'
assert 'Task' in data['allowed-tools']
print('OK')
"
# Expected: OK

# Confirm numbered Step structure (ADR-007 compliance)
rg -n '^### Step [0-9]+:' plugins/requirements-framework/commands/refactor-orchestrate.md
# Expected: 8+ hits (Steps 0–8)

# Confirm explicit Task dispatch
rg -n 'Task\(subagent_type=' plugins/requirements-framework/commands/refactor-orchestrate.md
# Expected: 2+ hits

# Confirm Verdict section
rg -n '^### Verdict' plugins/requirements-framework/commands/refactor-orchestrate.md
# Expected: 1 hit
```

**Step 3: Commit**

```bash
git add plugins/requirements-framework/commands/refactor-orchestrate.md
git commit -m "feat(commands): add /requirements-framework:refactor-orchestrate

Deterministic orchestrator per ADR-007: numbered steps (0-8) with
scope acquisition, pre-flight checks, explicit Task dispatch for
Stage 1 Explore agents, output verification, and verdict logic.
Models the pattern established by /deep-review and /arch-review.

Name field kept bare per plugin convention; invocation path is
/requirements-framework:refactor-orchestrate."
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
new_agents = ['./agents/refactor-executor.md', './agents/refactor-investigator.md', './agents/refactor-analyzer.md']
for a in new_agents:
    assert a in agents, f'missing {a}'
# Dynamic count check (avoids hardcoding 25): every new agent must be present
# without removing any existing agents
assert len(agents) >= len(new_agents) + 22, f'agents shrank? len={len(agents)}'
print('OK; total agents:', len(agents))
"
# Expected: OK; total agents: 25 (or more, if other agents were added in parallel work)
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
rg -n '/arch-review|/deep-review|/refactor-orchestrate|/requirements-framework:' \
   plugins/requirements-framework/skills/requirements-framework-status/SKILL.md \
   plugins/requirements-framework/skills/requirements-framework-usage/SKILL.md
```

**Step 2: Add /requirements-framework:refactor-orchestrate one-liner to each**

Use Edit to add an entry alongside existing commands in each file. Suggested wording:

```
- `/requirements-framework:refactor-orchestrate` — multi-layer top-down refactor workflow (produces plan + orchestrator-prompt for fresh-session execution)
```

**Step 3: Verify**

```bash
rg -n '/requirements-framework:refactor-orchestrate' \
   plugins/requirements-framework/skills/requirements-framework-status/SKILL.md \
   plugins/requirements-framework/skills/requirements-framework-usage/SKILL.md
# Expected: at least 1 hit in each file
```

**Step 4: Commit**

```bash
git add plugins/requirements-framework/skills/requirements-framework-status/SKILL.md \
        plugins/requirements-framework/skills/requirements-framework-usage/SKILL.md
git commit -m "docs(skills): mention /requirements-framework:refactor-orchestrate in discovery skills"
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

**Command**: `/requirements-framework:refactor-orchestrate`

**Agents (Haiku/Sonnet/Sonnet fanout)**:
- `requirements-framework:refactor-executor` (Haiku) — mechanical chunk execution
- `requirements-framework:refactor-investigator` (Sonnet) — read-only diagnosis
- `requirements-framework:refactor-analyzer` (Sonnet) — retrospective + rule-of-three promotion

**Outputs**:
- `.claude/plans/<YYYY-MM-DD>-<slug>.md` — validated design plan
- `.claude/plans/<YYYY-MM-DD>-<slug>-orchestrator-prompt.md` — copy-paste orchestrator

**Execution model**: A planning session produces both files. The orchestrator block runs in a **fresh `claude` session** by paste — chunks dispatch atomically, one commit per chunk.

**Recommended sequencing**: `/requirements-framework:arch-review` → `/requirements-framework:refactor-orchestrate` → fresh session for execution.

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

rg -n '/requirements-framework:refactor-orchestrate' CLAUDE.md
# Expected: 1+ hits
```

**Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document /requirements-framework:refactor-orchestrate workflow in CLAUDE.md"
```

---

### Task 15: Migrate accumulated state + delete globals

This is the **point of no return** for source-of-truth migration. Run only after all previous tasks pass static verification.

**Critical safety note (from arch-review)**: the existing global `~/.claude/skills/refactor-orchestration/learnings.md` contains accumulated observations from any prior orchestration runs (134 lines at time of arch-review). It MUST be migrated to the new writable location BEFORE deletion.

**Step 1: Migrate accumulated learnings to writable per-user location**

```bash
mkdir -p ~/.claude/refactor-orchestration

if [ -f ~/.claude/skills/refactor-orchestration/learnings.md ]; then
  cp ~/.claude/skills/refactor-orchestration/learnings.md \
     ~/.claude/refactor-orchestration/learnings.md
  echo "Migrated learnings.md to ~/.claude/refactor-orchestration/"
else
  echo "No existing learnings.md to migrate"
fi

# Sanity check: confirm migration succeeded (if applicable)
if [ -f ~/.claude/skills/refactor-orchestration/learnings.md ]; then
  diff -q ~/.claude/skills/refactor-orchestration/learnings.md \
          ~/.claude/refactor-orchestration/learnings.md \
    || { echo "Migration failed!" >&2; exit 2; }
fi
```

**Step 2: Verify ALL 8 plugin copies are byte-equivalent to globals (expanded gate)**

```bash
# Compare body content (excluding frontmatter) of all 3 agents
for agent in refactor-executor refactor-investigator refactor-analyzer; do
  diff <(awk 'BEGIN{p=0} /^---$/{c++; if(c==2)p=1; next} p' ~/.claude/agents/$agent.md) \
       <(awk 'BEGIN{p=0} /^---$/{c++; if(c==2)p=1; next} p' plugins/requirements-framework/agents/$agent.md) \
    || { echo "Body diff failed for $agent" >&2; exit 2; }
done

# Compare 5 skill files byte-identically (these had no frontmatter edits except SKILL.md and orchestrator-prompt-template.md which ARE edited)
# For the unedited 3 (plan-template, retrospective-template, learnings.md→template), do full byte compare:
for f in plan-template.md retrospective-template.md; do
  diff -q ~/.claude/skills/refactor-orchestration/$f \
          plugins/requirements-framework/skills/refactor-orchestration/$f \
    || { echo "File differs: $f" >&2; exit 2; }
done

# learnings.md → learnings.md.template byte-compare
diff -q ~/.claude/skills/refactor-orchestration/learnings.md \
        plugins/requirements-framework/skills/refactor-orchestration/learnings.md.template \
  || { echo "learnings.md.template does not match source learnings.md" >&2; exit 2; }

# SKILL.md and orchestrator-prompt-template.md were EDITED in Tasks 8, 9 — full byte compare would fail.
# Sanity check those by confirming key content is preserved:
grep -q '## Stages' plugins/requirements-framework/skills/refactor-orchestration/SKILL.md \
  || { echo "SKILL.md missing core content" >&2; exit 2; }
grep -q '=== BEGIN ORCHESTRATOR PROMPT ===' plugins/requirements-framework/skills/refactor-orchestration/orchestrator-prompt-template.md \
  || { echo "orchestrator-prompt-template missing BEGIN marker" >&2; exit 2; }

echo "All 8 plugin copies verified."
```

**Step 3: Delete the global agent files**

```bash
rm ~/.claude/agents/refactor-executor.md
rm ~/.claude/agents/refactor-investigator.md
rm ~/.claude/agents/refactor-analyzer.md
```

**Step 4: Delete the global skill folder**

```bash
rm -rf ~/.claude/skills/refactor-orchestration
```

**Step 5: Verify deletion + post-state**

```bash
ls ~/.claude/skills/refactor-orchestration/ 2>/dev/null
# Expected: no output (folder gone)

ls ~/.claude/agents/refactor-*.md 2>/dev/null
# Expected: no output (files gone)

# Confirm migrated learnings.md still exists at new path
ls ~/.claude/refactor-orchestration/learnings.md 2>/dev/null \
  && echo "Migrated ledger preserved at writable location" \
  || echo "(No prior ledger to preserve — fresh install)"
```

**Step 6: No commit needed** — these are outside the repo. The deletion + migration are runtime-state operations.

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

### Task 17: Static verification (7 checks)

No new commits — just assertions. If ANY check fails, stop and investigate.

**Step 1: Plugin manifest valid JSON**

```bash
python3 -c "import json; json.load(open('plugins/requirements-framework/.claude-plugin/plugin.json'))"
# Expected: no output (no exception)
```

**Step 2: All 3 agent frontmatter parses + names are BARE (not namespaced)**

```bash
for f in plugins/requirements-framework/agents/refactor-*.md; do
  python3 -c "
import yaml
content = open('$f').read()
header = content.split('---', 2)[1]
data = yaml.safe_load(header)
# Per plugin convention, name: stays bare. Namespace is applied by the plugin loader.
assert ':' not in data['name'], f\"agent name {data['name']} must NOT be namespaced (loader adds prefix)\"
assert data['name'].startswith('refactor-'), f\"unexpected agent name {data['name']}\"
print('$f', 'OK (name=' + data['name'] + ')')
"
done
# Expected: 3 OK lines with bare names
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

**Step 6: No un-namespaced subagent_type refs in moved skill files**

```bash
rg -n 'subagent_type[^"]*"refactor-(executor|investigator|analyzer)"' \
   plugins/requirements-framework/skills/refactor-orchestration/
# Expected: zero hits
```

**Step 7: Cross-file namespace completeness sweep (NEW, from arch-review)**

A single sweep across all migrated files to catch any stray bare-name references in `subagent_type` strings or markdown body — the per-file checks above might miss locations not individually verified.

```bash
rg -rn '"refactor-(executor|investigator|analyzer)"' \
   plugins/requirements-framework/ \
   --glob '!agents/refactor-*.md'
# Expected: zero hits. The agent files themselves DO have bare name: refactor-* in
# frontmatter (correct per plugin convention), so they're excluded from this sweep.
# Anywhere else, references must use the requirements-framework:refactor-* namespaced form.
```

If ANY of these checks fail, **stop and investigate** before proceeding. Do not attempt to push.

---

### Task 18: Live-reload smoke test — covers Stages 1–9 (manual)

**Important — depth (from arch-review)**: the smoke test MUST exercise the full pipeline, not just Stages 1–7 (planning). Stages 8–9 (execution + retrospective) include the new analyzer logic (classifier, two-tier ledgers, seed-on-first-run, convention sheet auto-creation), and without paste-and-run coverage that logic ships untested.

**Step 1: Launch dev-install session**

In a separate terminal:

```bash
claude --plugin-dir ~/Tools/claude-requirements-framework/plugin
```

**Step 2: Verify command discoverability**

In that session, type `/help` and confirm `/requirements-framework:refactor-orchestrate` appears in the command list.

**Step 3: Verify agent registration**

Invoke `Task` with `subagent_type="requirements-framework:refactor-executor"` on a no-op prompt (e.g., "Reply 'ack' and exit"). Repeat for `refactor-investigator` and `refactor-analyzer`. Confirm all 3 namespaced agents are reachable and respond.

**Step 4: Run /requirements-framework:refactor-orchestrate on a trivial target (Stages 1–7)**

Pick a small known-good area of the framework codebase (e.g., a small docs file or a single small skill). Run `/requirements-framework:refactor-orchestrate` and confirm:
- Both output files appear at `.claude/plans/`
- Plan file follows the §0–§13 structure
- Orchestrator-prompt has `=== BEGIN ORCHESTRATOR PROMPT ===` / `=== END ===` markers
- Subagent_type strings inside the orchestrator-prompt use namespaced form (`requirements-framework:refactor-*`)

**Step 5: Open a fresh `claude` session and paste the orchestrator block (Stages 8–9)**

This is the new depth requirement. Open a second `claude` session (NOT the dev-install one — use the normal session, post-marketplace install OR a separate dev-install). Paste the block between the BEGIN/END markers from Step 4's output.

Verify:
- **Phase A**: prerequisites check runs (working tree, baseline tests). Should pass for the trivial target.
- **Phases B–D**: each chunk dispatches to `requirements-framework:refactor-executor` and commits atomically. The trivial target may produce a very short chunk queue (1–2 chunks).
- **Phase E**: final smoke check (lint + tests) runs.
- **Phase F (analyzer)**: confirm:
  - `~/.claude/refactor-orchestration/learnings.md` exists (created from `.template` if first run, or preserved migration from Task 15).
  - `.claude/refactor-orchestration/learnings.md` exists (created empty on first run).
  - If the test session produces an observation, confirm classifier tags it (global vs project) and the entry is added to the correct ledger with `count=1`.
  - The retrospective file is written to `.claude/plans/<slug>-retrospective.md`.

**Step 6: Synthetic count=3 promotion test (optional but recommended)**

To exercise the count=3 promotion path, manually edit `.claude/refactor-orchestration/learnings.md` to bump a synthetic observation's `count` to 2 BEFORE running the orchestrator. Then run a second orchestration that would naturally re-record the same observation. The analyzer should:
- Detect the observation, bump count to 3.
- Trigger AskUserQuestion against `.claude/refactor-conventions.md`.
- On approval, create `.claude/refactor-conventions.md` with the seed structure and append the promoted line with the footnote.

This is the only path that exercises convention-sheet auto-creation. Skipping it means that code path remains untested.

**Step 7: Cleanup**

Discard the test plan files (`.claude/plans/`), retrospective, and any test-generated ledger entries. Restore the migrated learnings.md from a backup or accept that the smoke ran on a fresh ledger.

Stop both `claude` sessions.

This task has no commits — it is a manual verification gate.

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
- Add explicit `/requirements-framework:refactor-orchestrate` deterministic command (no auto-detection; ADR-007 compliant)
- Implement two-tier learning: global plugin templates + project conventions
- Delete global copies at `~/.claude/skills/refactor-orchestration/` and `~/.claude/agents/refactor-*.md` (with migration of accumulated `learnings.md` to `~/.claude/refactor-orchestration/` first)

Design + decisions: `docs/plans/2026-05-18-refactor-orchestration-integration-design.md`
ADR: `docs/adr/ADR-014-refactor-orchestration-bundled-skill.md`

## Test plan

- [x] All 7 static verification checks pass (Task 17 in the implementation plan)
- [x] Live-reload smoke test confirms `/requirements-framework:refactor-orchestrate` discoverability and agent registration; smoke covers Stages 1–9 including analyzer ledger creation (Task 18)
- [x] `/requirements-framework:refactor-orchestrate` produces both output files on a trivial target
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
3. Optionally pilot `/requirements-framework:refactor-orchestrate` on a real multi-layer refactor in another repo to start populating the learnings ledgers with real-world observations.

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

---

## Atomic Commit Strategy (validated)

Existing 21-commit sequence validated. All dependency orderings are correct and commits are atomic by construction.

### Dependency order checks

| Constraint | Status |
|---|---|
| Task 7 (skill folder copy) before Task 8 (SKILL.md edit) | Correct — Task 8 modifies a file created in Task 7 |
| Task 6 (analyzer base move) before Task 10 (analyzer enhancement) | Correct — Task 10 edits the file created in Task 6; the note at end of Task 6 explicitly documents this split |
| Tasks 3–13 (all source moves) before Task 15 (delete globals) | Correct — Task 15 is explicitly marked "point of no return" and depends on all plugin copies being in place |
| Task 15 (deletion) before Task 16 (`update-plugin-versions.sh` regen) | Correct — Task 16 re-hashes committed files; runtime cleanup (Task 15) is a prerequisite for the final consistent state |

### Atomicity assessment

Each commit encapsulates exactly one logical change:
- Tasks 2–3: docs corrections (ADR ref fix, new ADR)
- Tasks 4–6: one agent per commit (copy + namespace)
- Task 7: skill folder copy as a batch (5 files, all byte-identical copies — correct to batch)
- Task 8: SKILL.md cross-ref rewrite (separate from copy, cleanly split)
- Task 9: orchestrator-prompt namespace + Prerequisites (two related edits to one file — acceptable)
- Task 10: analyzer enhancement (the largest change, but scoped to one agent file)
- Tasks 11–13: command + manifest + discovery skills (each a separate logical concern)
- Task 14: CLAUDE.md documentation
- Task 16: version hash regen (chore, correctly separated from content commits)
- Tasks 17–21: verification, review gates, PR (no commits except Task 16)

### Commit message style

All proposed messages match the project's conventional-commit style (`type(scope): description`, lowercase, imperative mood). No issues found. Multi-line bodies use blank-line separation correctly (Tasks 7, 9, 10).

### One minor note

Task 15 produces no git commit (deletes files outside the repo). This is correct — the note says "No commit needed." The version-hash regen in Task 16 will still work because it targets committed plugin files, not the deleted globals.

---

## Preparatory Refactoring

Analysis of the codebase against this migration revealed the following opportunities, severity-labeled:

### [LOW] Model-tier frontmatter field is already established — no prep needed

Two agents (`comment-cleaner`, `import-organizer`) already use `model: haiku` in their frontmatter. The incoming `refactor-executor` will be the third. No centralization is warranted at this scale; three instances does not justify an abstraction.

### [LOW] `update-plugin-versions.sh` has no namespace-aware check — low risk for this migration

The script discovers files by path pattern (`find plugins/.../agents/*.md`) rather than by inspecting the `name:` field. Adding namespaced agents (e.g., `requirements-framework:refactor-executor`) will not break hash updates — the script updates the `git_hash` field regardless of the `name:` value. No preparatory change needed. **However**: if the project later adds a lint gate that verifies `name:` matches the filename stem, namespaced agents will fail. Worth noting as a future consideration but not actionable now.

### [LOW] Thin command frontmatter is consistent across all 11 existing commands — no template needed

All commands share the same five frontmatter fields (`name`, `description`, `argument-hint`, `allowed-tools`, `git_hash`) with no structural variation. Task 11's new `refactor-orchestrate.md` can follow the same pattern directly. No shared template abstraction is needed.

### [LOW] Skill SKILL.md files have no shared frontmatter — no centralization needed

Skills use only `name`, `description`, and `git_hash` in YAML frontmatter; their content is unconstrained prose. No repeated structure to extract.

### [NONE] No significant preparatory refactoring required

All migration tasks (4–11) are self-contained copy-and-edit operations. The codebase's existing conventions are sufficiently consistent that the executor can proceed directly with Task 1 without any prior refactoring.
