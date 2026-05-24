# Baseline — /deep-review output for Step 16c branch

**Date**: 2026-05-24
**Branch**: `refactor/step-08-llm-package-scaffold`
**Scope**: `7c090b4..HEAD` (Step 16c only, 102 files, ~7500 diff lines at review time)
**Review command**: `/requirements-framework:deep-review` invoked at conversation turn ~14:00
**Team size**: 11 agents (frontend-reviewer skipped — no .tsx/.jsx in scope; tool-validator ran as BLOCKING gate, not counted as team member)
**Source**: This document is a structured transcription of the team's findings from the live conversation. It is the baseline against which the V3 dogfood run will be compared.

---

## Tool Validator (BLOCKING gate — passed)

| Tool | Files | Errors | Warnings |
|------|-------|--------|----------|
| ruff 0.12.12 | 2 Python | 0 | 0 |
| pyright 1.1.408 | 2 Python | 0 | 0 |
| shellcheck 0.11.0 | 1 shell | 0 | 0 |

**Verdict**: 0 CRITICAL tool errors — team review unblocked.

---

## Per-agent findings

### code-reviewer
- **CRITICAL**: 0
- **IMPORTANT**: 1 — DEVELOPMENT.md `{% include %}` loader-root note opening sentence contradicts closing sentence and actual behavior (`{% include %}` against `hooks/lib/llm/prompts/partials/` works and is used by 13 agents)
- **SUGGESTION**: 2 — test docstring rename consistency, DEVELOPMENT.md prose clarity
- **Verdict**: ISSUES FOUND

### silent-failure-hunter (error-auditor)
- **CRITICAL**: 0
- **IMPORTANT**: 1 — `pre-commit-check.sh` missing-python3 fail-open intent not documented (the render_prompts.py absence guard had a comment; the python3 guard did not)
- **SUGGESTION**: 1 — test exclusion list is static name-based, slight fragility
- **Verdict**: PASS with one IMPORTANT note

### test-analyzer
- **CRITICAL**: 0
- **IMPORTANT**: 0
- **SUGGESTION**: 1 (dead exclusion names — 3 of 5 named exclusions never match the scan paths; defensive dead code but harmless)
- **Verdict**: PASS — test is sound, 6 of 6 checks confirmed

### backward-compatibility-checker (compat-checker)
- **CRITICAL**: 0
- **IMPORTANT**: 0 (confirmed byte-identical claim across all 32 files via MD5 + --check)
- **SUGGESTION**: 1 (DEVELOPMENT.md loader-root note imprecise — same finding as code-reviewer's IMPORTANT, lower severity from this angle)
- **Verdict**: PASS with one low-severity documentation note

### type-design-analyzer
- **CRITICAL**: 0
- **IMPORTANT**: 0
- **SUGGESTION**: 1 (optional: comment on `Path(str(md) + ".j2")` cross-version idiom)
- **Verdict**: PASS

### comment-analyzer
- **CRITICAL**: 0
- **IMPORTANT**: 0
- **SUGGESTION**: 2 (pre-commit-check.sh -u edge case for new files; DEVELOPMENT.md prose clarity)
- **Verdict**: PASS

### code-simplifier
- **CRITICAL**: 0
- **IMPORTANT**: 0
- **SUGGESTION**: 0 (explicitly: two-loop test structure justified, multi-echo block intentional UX, no actionable simplifications)
- **Verdict**: APPROVED

### codex-review-agent (codex-reviewer — internal codex pass)
- **CRITICAL**: 0
- **IMPORTANT**: 1 — DEVELOPMENT.md loader-root note opening sentence contradicts closing sentence (called MEDIUM by this agent; cross-validates code-reviewer's IMPORTANT)
- **LOW**: 1 — pre-commit-check.sh header comment still says "Step 16b" after scope expanded
- **Verdict**: ISSUES FOUND

### tenant-isolation-auditor
- **Verdict**: SKIPPED — no tenant boundary code in scope

### appsec-auditor
- **CRITICAL**: 0
- **IMPORTANT**: 0 (Step 16c introduces no new attack surface)
- **MEDIUM (pre-existing, not introduced by Step 16c)**: 1 — Jinja2 SSTI in build-time renderer (`hooks/lib/llm/templates.py` uses non-sandboxed Environment). Accepted risk for self-hosted single-developer deployment model.
- **Verdict**: 0 new issues; 4 confirmed non-exploitable threat vectors

### compliance-auditor
- **Verdict**: SKIPPED — no PII or compliance surface in scope

---

## Cross-validated findings (per ADR-013 rules applied during synthesis)

### ~~IMPORTANT~~ → RESOLVED: DEVELOPMENT.md `{% include %}` loader-root note inaccuracy
- **Corroboration**: TRIPLE — code-reviewer + compat-checker + codex-reviewer all independently flagged the same factual inaccuracy
- **Cross-validation rule**: "Documentation drift" + "AI corroboration" + "Type+breaking changes" → strongest synthesis signal
- **Status at end of /deep-review**: Folded into housekeeping patch via `stg refresh --index` (rewrote section to accurately describe that `{% include %}` works in both build-time and runtime paths)

### ~~IMPORTANT~~ → RESOLVED: pre-commit-check.sh missing-python3 fail-open intent undocumented
- **Single-agent**: error-auditor
- **Status at end of /deep-review**: Folded — added explanatory comment

### ~~LOW~~ → RESOLVED: pre-commit-check.sh header comment "Step 16b" stale
- **Single-agent**: codex-reviewer
- **Status at end of /deep-review**: Folded — updated header to "Steps 16b–16c"

---

## Final synthesis verdict

- **CRITICAL**: 0 (0 corroborated)
- **IMPORTANT**: 0 (2 cross-validated findings RESOLVED in-patch during synthesis)
- **LOW**: 0 (1 resolved)
- **SUGGESTION**: 5 (all non-blocking, documentation/code-clarity polish)
- **Verdict**: **READY**

`pre_pr_review` requirement satisfied per skill protocol after this synthesis.

---

## Aggregate severity tally (used for V3 comparison)

```
{
  "CRITICAL":   0,
  "IMPORTANT":  2,  // both resolved in-patch
  "LOW":        1,  // resolved
  "SUGGESTION": 5,
  "verdict":    "READY",
  "agent_count": 11,
  "skipped_agents": 2,  // tenant-isolation-auditor, compliance-auditor
  "files_in_scope": 102,
  "diff_lines": 7515
}
```

---

## Notable findings the V3 chain will be measured against

These are the items where structural cross-validation produced the highest-value signal. The V3 dogfood comparison should specifically check whether the single code-reviewer worker catches any of them.

1. **DEVELOPMENT.md `{% include %}` doc inaccuracy** — required THREE-agent agreement to escalate to actionable IMPORTANT. V3's single worker cannot replicate this triple-corroboration structurally.
2. **pre-commit-check.sh fail-open intent comment** — error-auditor's specialist finding. V3's code-reviewer worker is not specifically tuned for silent-failure auditing.
3. **pre-commit-check.sh header "Step 16b" stale** — codex-reviewer's prose-accuracy finding. V3's code-reviewer reads code first, prose second; this may or may not surface.
4. **Jinja2 SSTI (pre-existing MEDIUM)** — appsec-auditor specialist finding outside Step 16c's diff. V3's code-reviewer worker is unlikely to flag pre-existing risks.
5. **Stale exclusion names in test** — test-analyzer specialist finding. V3's worker is general-purpose; specialist patterns may not surface.

**Out of /deep-review baseline scope** (kept here for context but not used in V3 comparison): the `/codex-review` run AFTER /deep-review caught a CRITICAL the team missed (keep_trailing_newline rationale wrong in CHANGELOG). That finding is a separate V3-vs-/codex-review comparison, not part of this baseline.
