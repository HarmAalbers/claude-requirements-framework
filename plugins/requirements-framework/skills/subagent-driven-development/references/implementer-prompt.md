# Implementer Subagent Prompt Template

Use this template when dispatching an implementer subagent.

```
Task tool (general-purpose):
  description: "Implement Task N: [task name]"
  prompt: |
    You are implementing Task N: [task name]

    ## Task Description

    [FULL TEXT of task from plan - paste it here, don't make subagent read file]

    ## Context

    [Scene-setting: where this fits, dependencies, architectural context]

    ## Verified codebase facts

    [Exact API signatures, file:line anchors, and behavioral facts the orchestrator
    has verified (e.g. from a seams exploration). The implementer treats these as
    ground truth. For judgment-heavy tasks: spell out the decision logic literally,
    branch by branch — do not leave design decisions to the implementer.]

    If the codebase contradicts any fact above: STOP and ask. Do not guess.

    ## Hard Rules

    - NEVER run a formatter or auto-fixer (`ruff format`, `prettier`, `--fix`, ...)
      unless the task explicitly asks for it. Lint-CHECK commands are fine.
      Touch only the lines your task needs.
    - Stage files by explicit path: `git add <file> <file>`. NEVER `git add -A`,
      `git add .`, or glob-adds. Before committing, run `git status` and
      `git diff --stat`; if anything you did not expect shows up, leave it
      unstaged and mention it in your report.
    - Commit your work. A task without its commit is not done.
    - Your task is not finished until your report is DELIVERED (final message, or
      the channel the orchestrator named). Going idle without reporting is a failure.

    ## Before You Begin

    If you have questions about:
    - The requirements or acceptance criteria
    - The approach or implementation strategy
    - Dependencies or assumptions
    - Anything unclear in the task description

    **Ask them now.** Raise any concerns before starting work.

    ## Your Job

    Once you're clear on requirements:
    1. Implement exactly what the task specifies
    2. Write tests (following TDD - test first, then implement)
    3. Verify implementation works
    4. Commit your work
    5. Self-review (see below)
    6. Report back

    Work from: [directory]

    **While you work:** If you encounter something unexpected or unclear, **ask questions**.
    It's always OK to pause and clarify. Don't guess or make assumptions.

    ## Before Reporting Back: Self-Review

    Review your work with fresh eyes. Ask yourself:

    **Completeness:**
    - Did I fully implement everything in the spec?
    - Did I miss any requirements?
    - Are there edge cases I didn't handle?

    **Quality:**
    - Is this my best work?
    - Are names clear and accurate (match what things do, not how they work)?
    - Is the code clean and maintainable?

    **Discipline:**
    - Did I avoid overbuilding (YAGNI)?
    - Did I only build what was requested?
    - Did I follow existing patterns in the codebase?

    **Testing:**
    - Do tests actually verify behavior (not just mock behavior)?
    - Did I follow TDD (test first)?
    - Are tests comprehensive?

    If you find issues during self-review, fix them now before reporting.

    ## Report Format

    When done, report:
    - What you implemented
    - Test and lint results: PASTE the actual final output lines of the commands
      (e.g. `512 passed in 1.4s`, the linter's summary line). A claim like
      "all checks pass" without pasted output counts as unverified.
    - Files changed (and any unexpected files you saw in `git status`)
    - Commit hash(es)
    - Self-review findings (if any)
    - Any issues, concerns, or deviations from the spec
```
