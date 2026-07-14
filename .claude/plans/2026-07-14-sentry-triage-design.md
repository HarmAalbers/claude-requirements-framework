# Design: Sentry Triage in the Workflow (validate teammate + design hint)

**Date**: 2026-07-14 · **Tier**: standard · **Branch**: feat/sentry-triage

## Problem

When designing a new feature or changing existing code, the workflow never looks at
production reality: Sentry may already hold unresolved errors/warnings in the exact
code about to be adjusted. Those issues should surface (a) as design input and (b) as
a rigorous file-level check once the plan names the files being touched.

## Decisions (from interview)

1. **Placement**: a `sentry-triage` teammate in `/arch-review` (validate phase) does the
   rigorous check against the plan's file list; the brainstorming skill's anchor-peek
   step gets a one-line design-time hint. Not added to `/deep-review` (can follow later
   if the validate-time check proves valuable).
2. **Configuration**: an explicit `sentry: {org, project}` block in the requirements.yaml
   cascade (project or local layer). No block → the teammate is skipped silently, same
   UX as the Codex conditional. No auto-discovery — the user runs Sentry MCP under two
   orgs (personal + work) and guessing is worse than skipping.

## Architecture

Prompts-only change — no Python, no new gates, no schema changes. Mirrors the existing
`codex-arch-reviewer` conditional-teammate pattern end to end.

### Components

1. **New agent `sentry-triage`** (`plugins/requirements-framework/agents/sentry-triage.md.j2`
   → rendered `.md`, modeled on `codex-arch-reviewer`):
   - Reads `.claude/requirements.yaml` / `.claude/requirements.local.yaml` itself to get
     `sentry.org` / `sentry.project` (local wins).
   - Derives the touched surface from the plan file it is handed (file paths, module
     names, endpoints); falls back to `git diff --name-only origin/master...HEAD`.
   - Loads Sentry MCP tools via ToolSearch (`mcp__plugin_sentry_sentry__*`) and searches
     **unresolved** issues whose stack frames / metadata reference the touched files
     (search by filename, then by module/function name for the fuzzier hits), bounded to
     a recent window (default: last 90 days) to keep noise down.
   - Reports findings via SendMessage with severity (frequency × recency × overlap with
     the planned change) and the Sentry issue IDs/links; marks its task complete.
   - **Fail-soft invariant**: MCP tools absent, auth failure, timeout, or zero matches →
     report "skipped (<reason>)" / "no known issues" — never invent findings, never block.

2. **`/arch-review` command edit** (`commands/arch-review.md.j2`):
   - Probe: `HAS_SENTRY` = a `sentry:` block exists in `.claude/requirements.yaml` or
     `.claude/requirements.local.yaml` (grep-level check; MCP availability is handled by
     the agent itself at runtime).
   - Conditional teammate task "Sentry issue triage" assigned to `sentry-triage`, ONLY if
     HAS_SENTRY — parallel to the HAS_CODEX pattern.
   - Cross-reference rules in the synthesis step, e.g.: sentry-triage finds an unresolved
     issue in a region another agent also flags → escalate ("production evidence confirms
     the concern"); issue in a touched file no agent flags → standalone finding "known
     production error in code being modified — plan should address or consciously defer".
   - Report gains a "Known Production Issues (Sentry)" section, with the same
     "skipped (not configured)" fallback wording as Codex.

3. **Brainstorming skill hint** (`skills/brainstorming/SKILL.md.j2`, anchor-peek line):
   one sentence appended — if the project declares a `sentry:` block, query Sentry for
   unresolved issues in the area being changed; known production errors are design input.

4. **Config surface**: document the `sentry:` block in the plugin README (and
   DEVELOPMENT.md config section). No loader change — unknown top-level keys already
   pass through the cascade untouched, and only the agent consumes the block.

### Data flow

```
/arch-review probe (grep sentry: in requirements yamls)
   └─ HAS_SENTRY → spawn sentry-triage(plan file)
        └─ agent: read yaml → touched files from plan/diff → Sentry MCP search
             └─ SendMessage findings → synthesis cross-reference → report section
```

## Error handling

Everything fail-soft, consistent with the framework's fail-open principle: any Sentry
failure degrades to a "skipped" line in the report. The main review is never blocked or
delayed beyond the teammate's timeout (raised to 240s for sentry-triage — remote MCP
queries; other teammates keep 120s).

## Testing

No Python changes → no `test_requirements.py` additions. Verification is:
`uv run python scripts/render_prompts.py --check` (j2 → md), `scripts/build_plugin_hooks.py`
bundle rebuild, plus a manual smoke: add a `sentry:` block to this repo's local config and
run `/arch-review` on a branch touching a file with a known Sentry issue.

## Versioning

Minor bump of `plugins/requirements-framework/.claude-plugin/plugin.json` (new feature),
README agent/command counts updated (24 → 25 agents).

## Rejected alternatives

- **Design-time only (prompt hint, no agent)** — no structured file-level check; touched
  files are fuzzy at design time.
- **Standalone `/sentry-check` conditional command** — conditionals don't auto-fire; it
  would rarely run in practice.
- **Auto-discovery of org/project via MCP find_organizations** — wrong-org risk across
  the user's personal/work contexts; explicit config + silent skip is safer.
- **Also wiring into /deep-review now** — deferred until the validate-time check proves
  its value (YAGNI).
