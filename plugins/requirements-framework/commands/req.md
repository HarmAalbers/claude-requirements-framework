---
name: req
description: "Workflow conductor — derives the current requirements-framework phase and dispatches to the matching skill/command. Run with no arguments to be guided, or pass an explicit phase. The default phases are design, plan, validate, build, review, ship (these are the default phases; a project may configure others — run `req-phase` to see the current phase)."
argument-hint: "[phase]"
allowed-tools: ["Bash", "Read", "Skill"]
git_hash: 4acd4ca
---

# `/req` — Workflow Conductor

You are the requirements-framework workflow conductor. Your job is to (1) resolve the **current phase**, (2) tell the user *which* command/skill matches that phase and *why*, and (3) invoke it. Do not perform the phase's work yourself — delegate.

The phase order and the skill each phase dispatches to are **configured per project** (the `workflow:` config section). Resolve both at runtime from the helper script below — never hardcode the mapping. The script reads the active project's configuration, so a custom workflow (reordered, added, or renamed phases) just works.

## Step 1 — Resolve the phase and its skill

**No argument (auto-detect).** Run:

```
${CLAUDE_PLUGIN_ROOT}/scripts/req-phase --with-skill
```

It prints one line: `<phase>\t<skill>` (tab-separated). The left field is the current phase; the right field is the skill to dispatch (empty when the phase has no skill). Capture both.

**Explicit phase.** If `$ARGUMENTS` names a phase, resolve *that* phase's skill instead:

```
${CLAUDE_PLUGIN_ROOT}/scripts/req-phase --with-skill --phase "$ARGUMENTS"
```

This prints `<phase>\t<skill>` for the named phase — including a **non-terminal gateless dispatch-only** phase (a phase with a skill but no gate, e.g. a `cleanup` or `refactor` phase) that auto-detection never surfaces on its own. If the skill comes back empty, fall back to the default mapping in the note below.

The accepted phase arguments are the configured workflow's phase names. When unsure, run `${CLAUDE_PLUGIN_ROOT}/scripts/req-phase` with no flags to see the current phase.

## Step 2 — Dispatch

Act on the `<phase>\t<skill>` line from Step 1:

- **Skill is non-empty** → send the user a single line announcing the decision, then invoke that skill via the `Skill` tool. For example:

  > Phase is **validate** — invoking `requirements-framework:arch-review`.

- **Skill is empty** (the phase declares no configured skill) → do not invoke anything; report the current phase/status.

- **Script unavailable** → route by hand via the default fallback mapping below.

> **Default fallback mapping** — use this *only* if `${CLAUDE_PLUGIN_ROOT}/scripts/req-phase` is unavailable and you must route by hand. It mirrors the default (zero-config) workflow; the script is always authoritative when it runs.
>
> | Phase    | Skill                                                    |
> |----------|----------------------------------------------------------|
> | design   | `requirements-framework:brainstorming`                   |
> | plan     | `requirements-framework:writing-plans`                   |
> | validate | `requirements-framework:arch-review`                     |
> | build    | `requirements-framework:executing-plans`                 |
> | review   | `requirements-framework:deep-review`                     |
> | ship     | `requirements-framework:finishing-a-development-branch`  |
>
> Verify is not a phase — it is a per-push loop on **build** (`/verification-before-completion`, satisfies `verified` on each `git push`).

## Step 3 — After dispatch

The target skill takes over from here. Do not continue the workflow yourself in this turn — your job is over once the dispatch happens. The skill (and the framework hooks that listen for its completion) will flip the next requirement, which moves the project to the next phase. The user can rerun `/req` to advance.

## Notes

- This is a **deterministic dispatcher**, not an agent. It does not negotiate, summarize, or improvise — it routes attention to the right next step.
- The phase order and skills are read live from the project's `workflow:` config via `req-phase`. The `workflow-index` skill is the human-readable companion; if the two ever drift, the config (surfaced by the script) is the executable source of truth.
- For the `ship` phase, the default workflow dispatches `requirements-framework:finishing-a-development-branch`, which walks the user through the integration options — shipping stays a decision the user makes.
