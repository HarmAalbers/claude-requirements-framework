---
name: v3-review
description: "SDK fan-out code review (V3) — structured-output review workers + aggregator, rendered as an ADR-013 report. Additive opt-in alternative to /deep-review (see ADR-018)."
argument-hint: "[branch | a..b | PR#]"
allowed-tools: ["Bash"]
git_hash: 307b927
---

> **Workflow position**: an opt-in SDK alternative to the team-based `/deep-review` (ADR-012). Both satisfy `pr_reviewed`; choose the substrate you want.

# `/v3-review` — SDK Fan-out Code Review

Runs the V3 review workers in parallel over the diff via the Claude Agent SDK, aggregates their findings into one report, and prints it in the ADR-013 markdown format. A deterministic `ruff` gate runs first and aborts **before any LLM spend** if the changed Python files don't lint.

**Cost**: roughly $2–12 per run depending on diff size — there is no per-call budget cap yet (Step 17b). Prefer a narrow scope (e.g. a commit range).

## Where the report goes

## Where the reports go

Before dispatching any agent, resolve one review directory, `REVIEW_DIR`:

1. If the project describes its docs layout, follow it, including its naming. That can be a `docs/README.md`
   that says where reviews go, or a CLAUDE.md that names the docs location. The location may be outside the
   code repo, for example per ticket `tickets/<KEY>/reviews/<name>/`. Take the ticket key from the
   command's argument or from the branch name (such as `ATE-123`). Work that has its own folder in that
   layout without a key, such as an internal ticket folder, goes in that folder's `reviews/<name>/`. If the
   layout needs a key and none can be found, ask the user rather than guess.
2. Otherwise use `docs/reviews/<YYYY-MM-DD>-<branch>/` in the code repo.

`<name>` is `pr-<n>` when a pull request is reviewed, otherwise the command's name (such as `deep-review`).

Inside `REVIEW_DIR`:

- `RAPPORT.md` is the synthesis this command writes at the end, after the final verdict.
- `agents/<agent-name>.md` is each agent's own report, written by the agent. Give every agent you dispatch
  the line `REPORT FILE: <REVIEW_DIR>/agents/<agent-name>.md` in its prompt, and read its report from that
  file instead of from its message.

If `RAPPORT.md` already exists, this is a re-review. Add a dated section at the top of `RAPPORT.md` instead
of a new folder. The agent files are overwritten, so if the layout's repo is versioned, commit the previous
round first. When the layout says its docs are committed, commit the review there once it is complete.

Here `<name>` is `v3-review`. The workers run inside the script, not as prompted agents, so there are no
`agents/` files: the script's output is the whole report.

## Run

```bash
mkdir -p "<REVIEW_DIR>"
${CLAUDE_PLUGIN_ROOT}/scripts/v3-review "$ARGUMENTS" | tee "<REVIEW_DIR>/RAPPORT.md"
```

For a re-review, first move the existing `RAPPORT.md` content below the new output instead of overwriting it.
Relay the script's output verbatim — the rendered review plus the trailing `session_id` / cost footer is the deliverable. Do not re-review or summarize it yourself.

## Notes

- **Run interactively in a terminal.** The fan-out spawns N Claude-Agent-SDK subprocesses (the bundled Max CLI) whose control handshake needs an interactive stdio context. Launching it as a detached/background process with redirected stdio can fail with `Control request timeout: initialize`. A foreground run works (incl. the `!` prefix inside a Claude Code session).
- **Additive** to `/deep-review`; see ADR-018 for when to use which.
- **Known limitation**: this path does not apply `/deep-review`'s cross-validation corroboration *escalation* rules, so a finding may be reported as IMPORTANT where the team path would escalate it to CRITICAL.
