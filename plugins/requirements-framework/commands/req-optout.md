---
name: req-optout
description: "Mark the project inert under strict mode via the .rf-optout sentinel"
argument-hint: ""
allowed-tools: ["Bash", "Glob", "Grep", "Read", "Write", "Edit"]
git_hash: ee3eedd
---

> **Workflow position**: escape-hatch command. Always allowed even when strict preflight is blocking the project. Run this to make a project fully inert so the framework stops gating it.

# Opt Out of the Requirements Framework

Create the `.claude/.rf-optout` sentinel so this project is fully exempt from strict preflight and every other framework gate. This command is one of the escape-hatch-allowed actions: it runs even when strict mode is otherwise blocking all edits.

You MUST follow these steps in order.

## Step 1: Create the sentinel

Create the file `.claude/.rf-optout` in the project root (create the `.claude/` directory first if it does not exist). The file's contents do not matter — its mere existence makes the project inert. A short note explaining why is helpful:

```
This project opts out of the requirements framework (strict preflight + all gates).
```

## Step 2: Decide whether to commit or gitignore it

Explain the two choices to the user and let them decide:

- **Gitignore it (personal opt-out)** — add `**/.claude/.rf-optout` to `.gitignore` so only YOU skip the framework in this repo. Use this when the team still wants the framework but you personally don't, here and now.
- **Commit it (team-wide opt-out)** — `git add .claude/.rf-optout` so everyone treats this repo as "not a framework project". Use this when the repo genuinely shouldn't be gated for anyone.

Do not do both. If the user is unsure, default to gitignoring it (least surprising for others).

## Step 3: Confirm

Confirm to the user that the project is now inert: strict preflight will not block, no workflow gates will fire, and SessionStart will not print the strict briefing. To re-enable the framework later, delete `.claude/.rf-optout` and restart the session.
