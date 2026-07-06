# Design: Live-deriving requirements-framework-status skill

**Date**: 2026-07-06
**Branch**: `docs/status-skill-live-derive`
**Status**: Approved

## Problem

The `requirements-framework-status` skill is a hand-maintained mirror of facts the
repo already knows. Every volatile number has drifted:

| In skill | Reality (2026-07-06) |
|----------|----------------------|
| v2.5.0 | v4.24.1 |
| 1079 tests | 1529 tests |
| 15 hooks | ~18 hooks |
| ADRs …ADR-014 | ADR-019, ADR-020 exist |
| Skills "(20)" / header "21" | drifted |

`references/component-inventory.md` is worse — it hard-codes per-file **line counts**
(`config.py … 865`), which change on every edit. Refreshing the numbers re-rots on
the next change; that is exactly how it reached this state.

## Solution

Split content by volatility.

### Volatile → derive at runtime (inline read-only commands in SKILL.md)

The skill body lists the commands and instructs Claude to run them and report output.
No helper script (YAGNI) — the commands are self-verifying every invocation.

- Version ← `grep '"version"' plugins/requirements-framework/.claude-plugin/plugin.json`
- Test pass line ← `python3 hooks/test_requirements.py | tail -1`
- Hook count ← `ls hooks/handle-*.py hooks/check-requirements.py … | wc -l`
- Agent / command / skill counts ← `ls plugins/requirements-framework/<dir>/*.md | wc -l`
- ADR list ← `ls docs/adr/ADR-*.md`
- Live gating ← `req status`

### Durable → stays static

Config cascade, 3-strategy table, session lifecycle, requirement scopes, usage guide,
and `references/architecture-overview.md` (design patterns).

### Delete

- `references/component-inventory.md` (file lists + line counts — pure derivable rot)
  and every link to it.
- The frozen "Implementation Timeline / Phase 1-3" section.
- The hard-coded ADR table (replaced by the `ls docs/adr/` derivation).

## Files touched

- `skills/requirements-framework-status/SKILL.md.j2` (source) → re-render to `SKILL.md`
  via `scripts/render_prompts.py`. (`.j2` currently has no template vars — byte-identical
  to `.md`; the rewrite stays plain content.)
- `rm skills/requirements-framework-status/references/component-inventory.md`
- `plugin.json` patch bump.
- `update-plugin-versions.sh` for the `git_hash` frontmatter.
- `./sync.sh status` check.

## Verification

Run the full derivation command block end-to-end and confirm it prints today's real
numbers (v4.24.1 / 1529 tests / correct counts). This is the evidence for
`verification_evidence`.

## Skipped (YAGNI)

No helper script, no caching, no CI drift-check — the inline derivation is the
anti-rot mechanism by construction.
