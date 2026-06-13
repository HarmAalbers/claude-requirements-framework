---
name: req
description: "Workflow conductor — derives the current requirements-framework phase and dispatches to the matching skill/command. Run with no arguments to be guided, or pass an explicit phase. The default phases are design, plan-write, plan-validate, implement, review, refactor, ship (these are the default phases; a project may configure others — run `req-phase` to see the active set). Also accepts `plan` as a friendly alias that auto-picks the active plan sub-phase."
argument-hint: "[phase]"
allowed-tools: ["Bash", "Read", "Skill"]
git_hash: 95d0dbf
---

# `/req` — Workflow Conductor

You are the requirements-framework workflow conductor. Your job is to (1) resolve the **current phase**, (2) tell the user *which* command/skill matches that phase and *why*, and (3) invoke it. Do not perform the phase's work yourself — delegate.

The phase order and the skill each phase dispatches to are **configured per project** (the `workflow:` config section). Resolve both at runtime from the helper script below — never hardcode the mapping. The script reads the active project's configuration, so a custom workflow (reordered, added, or renamed phases) just works.

## Step 1 — Resolve the phase and its skill

**No argument (auto-detect).** Run:

```
${CLAUDE_PLUGIN_ROOT}/scripts/req-phase --with-skill
```

It prints one line: `<phase>\t<skill>` (tab-separated). The left field is the current phase; the right field is the skill to dispatch (empty when the phase has no skill, e.g. `ship`). Capture both.

**Explicit phase.** If `$ARGUMENTS` names a phase, resolve *that* phase's skill instead:

```
${CLAUDE_PLUGIN_ROOT}/scripts/req-phase --with-skill --phase "$ARGUMENTS"
```

This prints `<phase>\t<skill>` for the named phase — including a **gateless dispatch-only** phase (a phase with a skill but no gate, e.g. a `cleanup` or `refactor` phase) that auto-detection never surfaces on its own. If the skill comes back empty, fall back to the default mapping in the note below.

**`plan` alias.** If `$ARGUMENTS` is `plan`, run `${CLAUDE_PLUGIN_ROOT}/scripts/req-phase --with-skill` (no `--phase`): auto-detection already routes to the active plan sub-phase (`plan-write` while `plan_written` is unsatisfied, otherwise `plan-validate`). Dispatch whatever skill it prints.

The accepted phase arguments are the configured workflow's phase names. To list them when unsure, run `${CLAUDE_PLUGIN_ROOT}/scripts/req-phase` with no flags to see the current phase.

## Step 2 — Dispatch

Act on the `<phase>\t<skill>` line from Step 1:

- **Skill is non-empty** → send the user a single line announcing the decision, then invoke that skill via the `Skill` tool. For example:

  > Phase is **plan-validate** — invoking `requirements-framework:arch-review`.

- **Skill is empty** (e.g. the `ship` phase, or the script was unavailable) → do not invoke anything. Report the current phase/status. For `ship`, suggest the user finalize commits and open a PR (e.g. `/requirements-framework:codex-review`, then a PR) — shipping is a decision the user makes.

> **Default fallback mapping** — use this *only* if `${CLAUDE_PLUGIN_ROOT}/scripts/req-phase` is unavailable and you must route by hand. It mirrors the default (zero-config) workflow; the script is always authoritative when it runs.
>
> | Phase         | Skill                                            |
> |---------------|--------------------------------------------------|
> | design        | `requirements-framework:brainstorming`           |
> | plan-write    | `requirements-framework:writing-plans`           |
> | plan-validate | `requirements-framework:arch-review`             |
> | implement     | `requirements-framework:executing-plans`         |
> | review        | `requirements-framework:deep-review`             |
> | ship          | *(none — report status)*                         |
>
> `refactor` is a gateless dispatch-only phase that maps to `requirements-framework:refactor-orchestration`.

## Step 3 — After dispatch

The target skill takes over from here. Do not continue the workflow yourself in this turn — your job is over once the dispatch happens. The skill (and the framework hooks that listen for its completion) will flip the next requirement, which moves the project to the next phase. The user can rerun `/req` to advance.

## Notes

- This is a **deterministic dispatcher**, not an agent. It does not negotiate, summarize, or improvise — it routes attention to the right next step.
- The phase order and skills are read live from the project's `workflow:` config via `req-phase`. The `workflow-index` skill is the human-readable companion; if the two ever drift, the config (surfaced by the script) is the executable source of truth.
- For the `ship` phase, there is no single canonical skill — the user typically wraps up with `/requirements-framework:codex-review` and a PR. Surface those as suggestions but do not invoke them automatically; shipping is a decision the user makes.
