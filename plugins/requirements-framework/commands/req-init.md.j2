---
name: req-init
description: "Scaffold .claude/requirements.local.yaml for strict-mode compliance"
argument-hint: ""
allowed-tools: ["Bash", "Glob", "Grep", "Read", "Write", "Edit", "AskUserQuestion"]
git_hash: 7966aea
---

> **Workflow position**: escape-hatch command. Always allowed even when strict preflight is blocking the project. Run this to make a non-compliant project compliant.

# Initialize Requirements Config (strict mode)

Walk the user through creating `.claude/requirements.local.yaml` so this project passes the strict preflight gate. This command is one of the escape-hatch-allowed actions: it runs even when strict mode is otherwise blocking all edits.

You MUST follow these steps in order. Do not skip or improvise.

## Step 1: Choose a stage preset

Ask the user which adoption stage they want, using `AskUserQuestion`. Present these three presets:

- **instrument-only** — Observability only. No workflow gates fire; the project just becomes compliant so strict mode stops blocking. Lowest friction. Good for a first adoption.
- **front-gates** — Design/plan gates at the front of the workflow (e.g. `design_approved`, `commit_plan`) plus observability. Nudges design-first without gating every commit.
- **full-chain** — The full gated workflow (design → plan → review) end to end. Highest assurance, most friction.

Briefly describe each as above and let the user pick one (default to **instrument-only** if they are unsure).

## Step 2: Write the config

Write `.claude/requirements.local.yaml` with `strict_preflight: true` plus at least one enabled requirement (the preflight requires ≥1 enabled requirement). Use the chosen preset:

**instrument-only:**

```yaml
strict_preflight: true
requirements:
  observability:
    enabled: true
    type: dynamic
    scope: session
    description: "R5 Langfuse session tracing active"
```

**front-gates:** the instrument-only block PLUS:

```yaml
  commit_plan:
    enabled: true
    type: blocking
    scope: branch
    trigger_tools: [ExitPlanMode]
    satisfied_by_skill: 'arch-review'
```

**full-chain:** the front-gates block PLUS:

```yaml
  pre_pr_review:
    enabled: true
    type: blocking
    scope: branch
    satisfied_by_skill: 'deep-review'
```

If `.claude/requirements.local.yaml` already exists, read it first and merge rather than clobbering the user's existing requirements; ensure `strict_preflight: true` is present and at least one requirement is enabled.

## Step 3: Ensure it is gitignored

`.claude/requirements.local.yaml` is a local override and must NOT be committed. Check `.gitignore`:

```bash
grep -qF '**/.claude/requirements.local.yaml' .gitignore 2>/dev/null && echo present || echo missing
```

If missing, append `**/.claude/requirements.local.yaml` to `.gitignore` (create `.gitignore` if it does not exist).

## Step 4: Remind about the rest of compliance

Strict-mode compliance is more than the config. Tell the user that strict mode ALSO requires:

- **Valid Langfuse env** — run `python3 scripts/setup_langfuse_tracing.py --write` to write the 5 Layer-1 keys into `.claude/settings.local.json` (and prune any stale Layer-2 keys).
- **`uv` on PATH** — required by the bundled tracing hook. If `which uv` returns nothing, install it (`curl -LsSf https://astral.sh/uv/install.sh | sh`).

## Step 5: Tell them to restart

The new config and env block are loaded at session start. Tell the user to **restart the Claude Code session** so the configuration takes effect.

If they would rather make this project inert instead of compliant, point them at `/req-optout`.
