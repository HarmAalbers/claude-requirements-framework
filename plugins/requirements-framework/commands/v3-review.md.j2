---
name: v3-review
description: "SDK fan-out code review (V3) — structured-output review workers + aggregator, rendered as an ADR-013 report. Additive opt-in alternative to /deep-review (see ADR-018)."
argument-hint: "[branch | a..b | PR#]"
allowed-tools: ["Bash"]
git_hash: e53947f
---

> **Workflow position**: an opt-in SDK alternative to the team-based `/deep-review` (ADR-012). Both satisfy `pre_pr_review`; choose the substrate you want.

# `/v3-review` — SDK Fan-out Code Review

Runs the V3 review workers in parallel over the diff via the Claude Agent SDK, aggregates their findings into one report, and prints it in the ADR-013 markdown format. A deterministic `ruff` gate runs first and aborts **before any LLM spend** if the changed Python files don't lint.

**Cost**: roughly $2–12 per run depending on diff size — there is no per-call budget cap yet (Step 17b). Prefer a narrow scope (e.g. a commit range).

## Run

```bash
${CLAUDE_PLUGIN_ROOT}/scripts/v3-review "$ARGUMENTS"
```

Relay the script's output verbatim — the rendered review plus the trailing `session_id` / cost footer is the deliverable. Do not re-review or summarize it yourself.

## Notes

- **Run interactively in a terminal.** The fan-out spawns N Claude-Agent-SDK subprocesses (the bundled Max CLI) whose control handshake needs an interactive stdio context. Launching it as a detached/background process with redirected stdio can fail with `Control request timeout: initialize`. A foreground run works (incl. the `!` prefix inside a Claude Code session).
- **Additive** to `/deep-review`; see ADR-018 for when to use which.
- **Known limitation**: this path does not apply `/deep-review`'s cross-validation corroboration *escalation* rules, so a finding may be reported as IMPORTANT where the team path would escalate it to CRITICAL.
