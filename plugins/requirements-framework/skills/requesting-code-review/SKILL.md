---
name: requesting-code-review
description: Use when completing tasks, implementing major features, or before merging to verify work meets requirements
git_hash: uncommitted
---

# Requesting Code Review

Dispatch code review to catch issues before they cascade. Uses our specialized review agents or `/pre-commit` command.

**Core principle:** Review early, review often.

## When to Request Review

**Mandatory:**
- After each task in subagent-driven development
- After completing major feature
- Before merge to main

**Optional but valuable:**
- When stuck (fresh perspective)
- Before refactoring (baseline check)
- After fixing complex bug

## How to Request

### Option 1: Use `/pre-commit` (Recommended)

Our framework provides specialized review agents. Simply run:
```
/pre-commit
```

This dispatches code-reviewer, silent-failure-hunter, and tool-validator agents with cross-validation.

### Option 2: Manual Review via Subagent

**1. Get git SHAs:**
```bash
BASE_SHA=$(git rev-parse HEAD~1)  # or origin/main
HEAD_SHA=$(git rev-parse HEAD)
```

**2. Dispatch code-reviewer subagent:**

Use Task tool with `requirements-framework:code-reviewer` type, fill template at `references/code-reviewer-template.md`

**Placeholders:**
- `{WHAT_WAS_IMPLEMENTED}` — What you just built
- `{PLAN_OR_REQUIREMENTS}` — What it should do
- `{BASE_SHA}` — Starting commit
- `{HEAD_SHA}` — Ending commit
- `{DESCRIPTION}` — Brief summary

**3. Act on feedback:**
- Fix Critical issues immediately
- Fix Important issues before proceeding
- Note Minor issues for later
- Push back if reviewer is wrong (with reasoning)

## Integration with Workflows

**Subagent-Driven Development:**
- Review after EACH task
- Catch issues before they compound
- Fix before moving to next task

**Executing Plans:**
- Review after each batch (3 tasks)
- Get feedback, apply, continue

**Ad-Hoc Development:**
- Review before merge
- Review when stuck

## Requirements Integration

When this skill completes, it auto-satisfies the `pre_commit_review` requirement. This means git commit will no longer be blocked.

## Red Flags

**Never:**
- Skip review because "it's simple"
- Ignore Critical issues
- Proceed with unfixed Important issues
- Argue with valid technical feedback

**If reviewer wrong:**
- Push back with technical reasoning
- Show code/tests that prove it works
- Request clarification
