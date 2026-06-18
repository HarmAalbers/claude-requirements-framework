---
name: refactor-orchestration
description: "Use when starting a multi-layer top-down refactor that's too large for one session. Produces a validated plan and a copy-paste orchestrator prompt that dispatches small chunks to the refactor-executor agent (Haiku) and escalates contradictions to the refactor-investigator agent (Sonnet) plus the user. Triggers on phrases like 'orchestrate refactor', 'top-down refactor', 'design ideal shape', 'layer-by-layer refactor', 'plan and orchestrate', 'execute big refactor in chunks', 'ideal endpoint design', 'redesign this layer'."
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Grep
  - Glob
  - WebFetch
  - mcp__plugin_context7-plugin_context7__query-docs
  - mcp__plugin_context7-plugin_context7__resolve-library-id
git_hash: c9a318c
---

# Refactor Orchestration

This skill captures a workflow for **multi-layer top-down refactors**: the kind of work where you design the outermost layer first, push unfit responsibilities downward with an "export manifest," then move layer by layer until the codebase is reshaped.

## When to use

- A refactor that touches many files across multiple architectural layers.
- A refactor too large to design AND execute in one session.
- A refactor where you want to FREEZE the design before executing, then dispatch mechanical work in parallel-ish chunks.

If the work fits in one session and one mental model, skip this skill and just do it directly.

## Two outputs of this skill

1. `.claude/plans/<YYYY-MM-DD>-<slug>.md` — the validated design plan
2. `.claude/plans/<YYYY-MM-DD>-<slug>-orchestrator-prompt.md` — the copy-paste orchestrator prompt

The first is the WHAT; the second is the HOW. Both are produced in this skill's workflow.

## Stages

1. **Inventory.** Two parallel `Explore` agents: one catalogues the layer's current state (every file, every function, every leaked responsibility), one extracts rules from the relevant ADRs / design docs / framework conventions. If `.claude/refactor-conventions.md` exists, read it and include its **Layer rules** and **Known anti-patterns** sections in the "what should be" report — these are project-tier constraints promoted by prior `refactor-analyzer` runs and must be respected in the plan's §1 (Forbidden). Produces a "what is" and a "what should be" report.

2. **Top-down design.** Draft the IDEAL shape of the layer. For each item that doesn't fit cleanly, push it into the NEXT layer with a placeholder home — even if no clean home exists yet. Capture these in an Export Manifest. The principle: name the responsibility and its target Protocol/method now, defer the destination's implementation shape to the next pass.

3. **Library-claim validation (context7).** For every third-party API the plan names (FastAPI, Pydantic, SDK clients, streaming libraries), confirm the claim via context7 docs. Capture deltas in a validation table. **This step is non-optional** — in past refactors it caught 5/5 library claims, two of which were silent-failure blockers.

4. **Harmonization.** Force the design toward maximal symmetry. Define a canonical template; reduce N templates to 1 or 2; fix parameter order; make every endpoint/function/file look as similar as possible to every other. Asymmetric designs grow asymmetric code.

5. **Persist plan.** Write the plan to `.claude/plans/<YYYY-MM-DD>-<slug>.md` using `plan-template.md` (§0–§13 structure). Keep the section headers stable — anyone reading multiple plans should recognize the shape. When a conventions file was read in Stage 1, its Layer rules and Known anti-patterns must appear verbatim in plan §1 (Forbidden). New projects with no conventions file leave §1 populated only from ADR analysis — that is correct and expected.

6. **Orchestrator design.** Decompose the plan into a chunk queue. Each chunk = one atomic commit. Group chunks into phases (typically: shared primitives → protocols/contracts → per-feature rewrites → structural tests → smoke validation).

7. **Persist orchestrator.** Write the copy-paste orchestrator to `.claude/plans/<YYYY-MM-DD>-<slug>-orchestrator-prompt.md` using `orchestrator-prompt-template.md`. Wrap the executable block with `=== BEGIN ORCHESTRATOR PROMPT ===` and `=== END ORCHESTRATOR PROMPT ===` markers so the reader knows what to copy.

8. **Execute.** Open a fresh `claude` session, paste the orchestrator block between the markers, let it run. The orchestrator dispatches `refactor-executor` (Haiku) per chunk, reviews each itself, and escalates contradictions to `refactor-investigator` (Sonnet) then to the user via `AskUserQuestion`.

9. **Retrospective.** As its final phase (Phase F), the orchestrator dispatches `refactor-analyzer` (Sonnet, read-mostly). The analyzer reads the full session transcript, the git log, and the learnings ledger; writes a retrospective report at `.claude/plans/<plan-slug>-retrospective.md`; appends new observations to `learnings.md`; and proposes template/agent edits via `AskUserQuestion` for any observation that hit `count=3` this run (rule-of-three promotion). NEVER edits the just-finished plan or orchestrator-prompt — those are history. The 5 buckets the analyzer is allowed to propose against: `SKILL.md`, `plan-template.md`, `orchestrator-prompt-template.md`, `refactor-executor.md`, `refactor-investigator.md`. This is what closes the loop and makes the whole system learn over time.

## Templates and subagents

- **`plan-template.md`** — fully opinionated §0–§13 structure. Fill in placeholders; keep the section headers stable.
- **`orchestrator-prompt-template.md`** — `=== BEGIN/END ===` block with placeholders for plan path, branch, chunk queue, dispatch template instance. Ends with Phase F dispatching the analyzer.
- **`retrospective-template.md`** — §1–§7 structure for the retrospective report the analyzer produces.
- **`learnings.md`** — ledger that accumulates observations across runs. Rule-of-three promotion controls when an observation becomes a proposed diff.
- **`requirements-framework:refactor-executor`** — Haiku subagent. Mechanical chunk execution. Reads only the referenced plan section, edits only the named files, verifies with ruff + import smoke. Does not redesign.
- **`requirements-framework:refactor-investigator`** — Sonnet subagent. Read-only. Diagnoses plan-vs-reality contradictions and proposes 2-3 solution paths.
- **`requirements-framework:refactor-analyzer`** — Sonnet subagent. Read-mostly. Writes the retrospective report + learnings.md; proposes template/agent diffs via AskUserQuestion. NEVER edits past plans/orchestrator prompts.

## Conventions

- **Filenames:** `.claude/plans/YYYY-MM-DD-<slug>.md` for the plan and `<slug>-orchestrator-prompt.md` for the orchestrator companion. Same date prefix; same slug; explicit pairing.
- **One chunk = one commit.** The orchestrator commits atomically per chunk with an imperative subject mentioning the plan section (e.g. "Add execute()/stream() transport helpers per plan §4").
- **Pre-commit hooks are mandatory.** Never use `--no-verify` without explicit user approval. If hooks auto-format and leave files in `MM` state, re-stage and retry.
- **Two retries on simple issues** before escalating to investigation. If Haiku can't fix it in 3 total tries, the problem is probably a misunderstanding, not a typo.
- **Investigation outputs do not change code** — they produce options for the user to pick. The orchestrator updates the plan only after the user picks an option.

## Part of requirements-framework

This skill is bundled with the `requirements-framework` plugin. Recommended sequencing:

| Step | Command | What it covers |
|---|---|---|
| 1 | `/requirements-framework:arch-review` | Satisfies the framework's planning gates (commit_plan, adr_reviewed, tdd_planned, solid_reviewed) for the upcoming work. |
| 2 | `/requirements-framework:refactor-orchestrate` | Stages 1–7 of this skill: inventory, top-down design, library-claim validation, harmonization, plan write, chunk queue, orchestrator-prompt write. |
| 3 | Fresh `claude` session | Paste the orchestrator block. Stages 8–9 (execution + retrospective) run there. |

This skill does **not** auto-satisfy any framework requirements. Run `/requirements-framework:arch-review` first if the project enforces them.

`req:session-reflect` is complementary to Stage 9 — does general session reflection. The analyzer mentions it in the retrospective's "Further reading" footer but does not invoke it.

## Stop conditions for the orchestrator

Stop and bring problems to the user IF:
- Baseline tests fail before any chunk runs.
- A chunk hits a complex issue after one investigation dispatch.
- 2 simple-issue retries fail in a row.
- A circular import or layer-guard violation appears that the plan doesn't anticipate.
- The plan references a file/symbol that doesn't exist in the codebase.
- The chunk queue is empty (success path — give a final-state report).

## Anti-patterns

- **Skipping context7 validation.** Library APIs drift; the plan will be wrong.
- **Skipping harmonization.** Asymmetric designs grow asymmetric code.
- **Letting the executor make design decisions.** If the plan is ambiguous, fix the plan, not the chunk.
- **Running the orchestrator on a dirty working tree.** Atomic commits become non-atomic.
- **Bundling many chunks into one commit.** Loses the resume-on-escalation property.
- **Re-reading ADRs during execution.** They were inputs to design, not to execution. Trust the plan.

## File map

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
