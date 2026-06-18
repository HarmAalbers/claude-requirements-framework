---
name: writing-plans
description: Use when there is a spec or requirements for a multi-step task, before touching code
git_hash: a165daf
---

# Writing Plans

## Overview

Write comprehensive implementation plans assuming the engineer has zero context for the codebase. Document everything they need to know: which files to touch for each task, code, testing, docs they might need to check, how to test it. Give them the whole plan as bite-sized tasks. DRY. YAGNI. TDD. Frequent commits.

Assume they are a skilled developer, but know almost nothing about the toolset or problem domain. Assume they don't know good test design very well.

**Announce at start:** "I'm using the writing-plans skill to create the implementation plan."

**Save plans to:** `docs/plans/YYYY-MM-DD-<feature-name>.md` or `.claude/plans/`

The plan should bias toward the least code that works — apply this ladder to every task:

# Lazy-Dev Ladder

You are a lazy senior developer — lazy means efficient, not careless. The best code is the code never written.

Before writing code, stop at the first rung that holds:
1. Does this need to exist at all? Speculative need → skip it, say so in one line. (YAGNI)
2. Does the standard library already do this? Use it.
3. Does a native platform feature cover it? Use it (`<input type="date">` over a picker lib, a DB constraint over app code, CSS over JS).
4. Does an already-installed dependency solve it? Use it — never add a new dependency for what a few lines can do.
5. Can it be one line? Make it one line.
6. Only then: write the minimum code that works.

Never lazy about: input validation at trust boundaries, error handling that prevents data loss, security, accessibility, and anything explicitly requested. Between two same-size options, pick the edge-case-correct one — lazy means less code, not the flimsier algorithm.

Output: code first, then at most a couple of lines naming what you skipped and when to add it. Don't defend simplifications with prose.

<!-- Adapted from ponytail (https://github.com/DietrichGebert/ponytail), MIT-licensed. -->


## Bite-Sized Task Granularity

**Each step is one action (2-5 minutes):**
- "Write the failing test" — step
- "Run it to make sure it fails" — step
- "Implement the minimal code to make the test pass" — step
- "Run the tests and make sure they pass" — step
- "Commit" — step

## Plan Document Header

**Every plan MUST start with this header:**

```markdown
# [Feature Name] Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use requirements-framework:executing-plans to implement this plan task-by-task.

**Goal:** [One sentence describing what this builds]

**Architecture:** [2-3 sentences about approach]

**Tech Stack:** [Key technologies/libraries]

---
```

## Task Structure

````markdown
### Task N: [Component Name]

**Files:**
- Create: `exact/path/to/file.py`
- Modify: `exact/path/to/existing.py:123-145`
- Test: `tests/exact/path/to/test.py`

**Step 1: Write the failing test**

```python
def test_specific_behavior():
    result = function(input)
    assert result == expected
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/path/test.py::test_name -v`
Expected: FAIL with "function not defined"

**Step 3: Write minimal implementation**

```python
def function(input):
    return expected
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/path/test.py::test_name -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/path/test.py src/path/file.py
git commit -m "feat: add specific feature"
```
````

## Remember
- Exact file paths always
- Complete code in plan (not "add validation")
- Exact commands with expected output
- DRY, YAGNI, TDD, frequent commits
- Reference relevant skills where applicable

## Execution Handoff

After saving the plan, offer execution choice:

**"Plan complete and saved to `docs/plans/<filename>.md`. Two execution options:**

**1. Subagent-Driven (this session)** — I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** — Open new session with executing-plans, batch execution with checkpoints

**Which approach?"**

**If Subagent-Driven chosen:**
- **REQUIRED SUB-SKILL:** Use `requirements-framework:subagent-driven-development`
- Stay in this session
- Fresh subagent per task + code review

**If Parallel Session chosen:**
- Guide them to open new session in worktree
- **REQUIRED SUB-SKILL:** New session uses `requirements-framework:executing-plans`

## Requirements Integration

When this skill completes, it auto-satisfies both `plan_written` and `commit_plan` requirements. This means Edit/Write tools will no longer be blocked by the planning gate (if your project has these requirements enabled).

For architecture validation, consider running `/arch-review` on the plan to also satisfy `adr_reviewed`, `tdd_planned`, and `solid_reviewed`.
