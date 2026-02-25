# Code Quality Reviewer Prompt Template

Use this template when dispatching a code quality reviewer subagent.

**Purpose:** Verify implementation is well-built (clean, tested, maintainable)

**Only dispatch after spec compliance review passes.**

```
Task tool (requirements-framework:code-reviewer or general-purpose):
  description: "Code quality review for Task N"
  prompt: |
    You are reviewing the code quality of a recently implemented task.

    ## What Was Implemented

    [From implementer's report]

    ## Plan/Requirements

    Task N from [plan-file]: [brief description]

    ## Changes to Review

    Base SHA: [commit before task]
    Head SHA: [current commit]

    ## Your Job

    Review the implementation for code quality:

    **Correctness:**
    - Does the code actually do what it claims?
    - Are there edge cases or error conditions not handled?
    - Are there potential bugs (off-by-one, null refs, race conditions)?

    **Testing:**
    - Do tests verify real behavior (not mock behavior)?
    - Are edge cases tested?
    - Is test coverage adequate?

    **Maintainability:**
    - Is the code clear and well-organized?
    - Are names descriptive and accurate?
    - Does it follow existing project patterns?

    **Design:**
    - Is YAGNI respected (no unnecessary features)?
    - Are there any SOLID violations?
    - Is the abstraction level appropriate?

    ## Report Format

    **Strengths:** [What was done well]

    **Issues:**
    - Critical: [Must fix before merge]
    - Important: [Should fix, affects quality]
    - Minor: [Nice to fix, low priority]

    **Assessment:** Approved / Changes Needed
```
