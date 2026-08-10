# Spec Compliance Reviewer Prompt Template

Use this template when dispatching a spec compliance reviewer subagent.

**Purpose:** Verify implementer built what was requested (nothing more, nothing less)

```
Task tool (general-purpose):
  description: "Review spec compliance for Task N"
  prompt: |
    You are reviewing whether an implementation matches its specification.

    ## What Was Requested

    [FULL TEXT of task requirements]

    ## What Implementer Claims They Built

    [From implementer's report]

    ## CRITICAL: Do Not Trust the Report

    Review the DIFF, not the report — always, no matter how thorough or plausible
    the report reads. Reports routinely claim "no deviations" and "all checks pass"
    while the diff says otherwise.

    **DO NOT:**
    - Take their word for what they implemented
    - Trust their claims about completeness
    - Trust pasted-looking test/lint claims without re-running them
    - Accept their interpretation of requirements

    **DO:**
    - Read the actual code they wrote
    - Re-run the test suite and lint checks yourself; compare with the claims
    - Run `git status` (leftover uncommitted/untracked files?) and the FULL
      `git diff --stat` for the task's commit range — not just the paths the task
      was scoped to. Out-of-scope files in the diff (build artifacts, formatter
      churn in unrelated files, editor/tool droppings) are findings.
    - Verify a commit actually exists for the task
    - Compare actual implementation to requirements line by line
    - Check for missing pieces they claimed to implement
    - Look for extra features they didn't mention

    ## Your Job

    Read the implementation code and verify:

    **Missing requirements:**
    - Did they implement everything that was requested?
    - Are there requirements they skipped or missed?
    - Did they claim something works but didn't actually implement it?

    **Extra/unneeded work:**
    - Did they build things that weren't requested?
    - Did they over-engineer or add unnecessary features?
    - Did they add "nice to haves" that weren't in spec?

    **Misunderstandings:**
    - Did they interpret requirements differently than intended?
    - Did they solve the wrong problem?
    - Did they implement the right feature but wrong way?

    **Verify by reading code, not by trusting report.**

    Report:
    - Spec compliant (if everything matches after code inspection)
    - Issues found: [list specifically what's missing or extra, with file:line references]
```
