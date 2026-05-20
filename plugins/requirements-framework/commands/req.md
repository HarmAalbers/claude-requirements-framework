---
name: req
description: "Workflow conductor — derives the current requirements-framework phase and dispatches to the matching skill/command. Run with no arguments to be guided, or pass an explicit phase: design, plan-write, plan-validate, implement, review, refactor, ship. Also accepts `plan` as a friendly alias that auto-picks the active plan sub-phase."
argument-hint: "[phase]"
allowed-tools: ["Bash", "Read", "Skill"]
git_hash: 9d913aa
---

# `/req` — Workflow Conductor

You are the requirements-framework workflow conductor. Your job is to (1) resolve the **current phase**, (2) tell the user *which* command/skill matches that phase and *why*, and (3) invoke it. Do not perform the phase's work yourself — delegate.

## Step 1 — Resolve the phase

If `$ARGUMENTS` is one of `design`, `plan-write`, `plan-validate`, `implement`, `review`, `refactor`, or `ship`, use that value as the phase. Skip to Step 2.

If `$ARGUMENTS` is the friendly alias `plan`, resolve it: derive the current phase (next step) and treat it as `plan-write` if `plan_written` is unsatisfied, otherwise `plan-validate`.

Otherwise, derive the phase by running:

```
${CLAUDE_PLUGIN_ROOT}/scripts/req-phase
```

That script prints a single word — the phase — to stdout. Capture it.

## Step 2 — Dispatch

Look up the resolved phase in this table and act:

| Phase         | Underlying skill                                | What to do                                                  |
|---------------|-------------------------------------------------|-------------------------------------------------------------|
| design        | `requirements-framework:brainstorming`          | Invoke the skill with the Skill tool                        |
| plan-write    | `requirements-framework:writing-plans`          | Invoke the skill with the Skill tool                        |
| plan-validate | `requirements-framework:arch-review`            | Invoke the skill with the Skill tool                        |
| implement     | `requirements-framework:executing-plans`        | Invoke the skill with the Skill tool                        |
| review        | `requirements-framework:deep-review`            | Invoke the skill with the Skill tool                        |
| refactor      | `requirements-framework:refactor-orchestration` | Invoke the skill with the Skill tool                        |
| ship          | *(none)*                                        | Report status and suggest the user finalize commits + open a PR |

Before invoking, send the user a single line announcing the dispatch decision, like:

> Phase is **plan-validate** — invoking `requirements-framework:arch-review`.

Then invoke the skill via the `Skill` tool.

## Step 3 — After dispatch

The target skill takes over from here. Do not continue the workflow yourself in this turn — your job is over once the dispatch happens. The skill (and the framework hooks that listen for its completion) will flip the next requirement, which moves the project to the next phase. The user can rerun `/req` to advance.

## Notes

- This is a **deterministic dispatcher**, not an agent. It does not negotiate, summarize, or improvise — it routes attention to the right next step.
- The phase mapping mirrors the `workflow-index` skill exactly. If the two ever drift, the index is the human-readable source of truth; this command is the executable one.
- For the `ship` phase, there is no single canonical skill — the user typically wraps up with `/requirements-framework:codex-review` and a PR. Surface those as suggestions but do not invoke them automatically; shipping is a decision the user makes.
