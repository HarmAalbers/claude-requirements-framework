# ADR-013: Standardized Agent Output Format

## Status
Approved (2026-02-17) — Decision approved, implementation in progress (phases 1-5)

## Context

The requirements framework has 9 review agents that produce findings during code review. Each agent evolved independently and uses a different output format and severity system:

| Agent | Severity System |
|-------|----------------|
| code-reviewer | Confidence 0-100 (threshold >= 80) |
| silent-failure-hunter | CRITICAL / HIGH / MEDIUM |
| test-analyzer | Rating 1-10 (threshold >= 7) |
| backward-compatibility-checker | Emoji severity (red/yellow/green circle) |
| type-design-analyzer | Four 1-10 dimensional ratings |
| comment-analyzer | Critical / Improvement / Removal categories |
| codex-review-agent | High / Medium / Low with emoji |
| tool-validator | CRITICAL / MEDIUM / LOW with emoji |
| code-simplifier | Free-form suggestions |

This inconsistency creates two problems:

1. **Cross-validation is unreliable**. The `/deep-review` lead must parse free-form markdown from agents using different formats and somehow correlate findings. A code-reviewer "Confidence: 85/100" finding and a silent-failure-hunter "HIGH" finding about the same code location are hard to match programmatically.

2. **Aggregation requires normalization**. Commands like `/quality-check` must map different severity systems to common counts (e.g., treating "HIGH" and "confidence >= 80" as the same level). This normalization logic is fragile and undocumented.

## Decision

**All review agents must use a standardized markdown output template with three severity levels: CRITICAL, IMPORTANT, SUGGESTION.**

### Standard Finding Template

```markdown
# [Agent Title] Review

## Files Reviewed
- path/to/file1.py

## Findings

### CRITICAL: [Short title]
- **Location**: `path/to/file.py:42`
- **Description**: What is wrong and why it matters
- **Impact**: What breaks if not fixed
- **Fix**: Concrete suggestion

### IMPORTANT: [Short title]
- **Location**: `path/to/file.py:87`
- **Description**: What is wrong
- **Impact**: What could go wrong
- **Fix**: Concrete suggestion

### SUGGESTION: [Short title]
- **Location**: `path/to/file.py:123`
- **Description**: What could be improved
- **Fix**: Optional suggestion

## Summary
- **CRITICAL**: X
- **IMPORTANT**: Y
- **SUGGESTION**: Z
- **Verdict**: ISSUES FOUND | APPROVED
```

### Format Rules

1. **Severity is the H3 prefix**: `### CRITICAL:`, `### IMPORTANT:`, or `### SUGGESTION:`. This enables reliable regex parsing: `/^### (CRITICAL|IMPORTANT|SUGGESTION): (.+)$/`.
2. **Location is always `file:line`**: e.g., `path/to/file.py:42`. Ranges use start line: `path/to/file.py:42-56`.
3. **Summary section with counts**: Every agent MUST end with `## Summary` containing numeric counts and a verdict.
4. **No agent-specific severity systems**: Agent-specific metrics (confidence scores, dimensional ratings) are internal reasoning aids, not output format.

### Severity Mapping

| Agent | Maps to CRITICAL | Maps to IMPORTANT | Maps to SUGGESTION |
|-------|-----------------|-------------------|-------------------|
| code-reviewer | confidence >= 90 | confidence 80-89 | below threshold |
| silent-failure-hunter | CRITICAL | HIGH | MEDIUM |
| test-analyzer | rating 9-10 | rating 7-8 | rating 5-6 |
| backward-compat | CRITICAL (was red) | MEDIUM (was yellow) | LOW (was green) |
| type-design-analyzer | any single dimension <= 3 | any single dimension 4-6 | all dimensions >= 7 |
| comment-analyzer | Critical Issues | Improvements | Removals |
| codex-review-agent | High | Medium | Low |
| tool-validator | Error | Warning | Info |
| code-simplifier | (unused) | (unused) | All findings |

### Cross-Validation Rules

When the lead cross-validates findings from multiple agents, "same location" means the same file within 10-line proximity. Domain-specific rules determine how findings interact:

| Agents | Condition | Action |
|--------|-----------|--------|
| code-reviewer + silent-failure-hunter | Both flag same region | Escalate to CRITICAL |
| code-reviewer + comment-analyzer | Code change + comment issue same location | Corroborate |
| test-analyzer + code-reviewer | Bug + no tests for same function | Escalate both to CRITICAL |
| type-design-analyzer + backward-compat | Weak types + breaking change | Escalate to CRITICAL |
| type-design-analyzer + silent-failure-hunter | Unenforced invariants + error path | Escalate |
| silent-failure-hunter + backward-compat | Breaking change + silent suppression | Escalate to CRITICAL |
| codex-review-agent + any | Same location | Corroborate with "confirmed by external AI" |
| code-simplifier + code-reviewer | Simplifier targets code-reviewer flagged area | Corroborate: complexity contributes to bug |
| code-simplifier + silent-failure-hunter | Same region flagged | Note: simplifying may fix error handling |

## Allowed

- Agents retain internal reasoning frameworks (e.g., type-design-analyzer still evaluates 4 dimensions internally) but output uses standard format
- Agents can include additional context in the Description field beyond the minimum required fields
- The "No findings" case uses the standard Summary section with zero counts

## Prohibited

- Agent-specific severity labels in output (no "HIGH", "MEDIUM", "LOW", confidence scores, numeric ratings, or emoji severity markers)
- Output without the Summary section (required for automated aggregation)
- Findings without a Location field (required for cross-validation)

## Consequences

### Positive
- Cross-validation becomes reliable: findings from different agents can be matched by location and compared by severity
- Aggregation is trivial: count `### CRITICAL:`, `### IMPORTANT:`, `### SUGGESTION:` occurrences
- New agents automatically participate in cross-validation by following the template
- Users see consistent output regardless of which agents run

### Negative
- Agents lose nuanced output (e.g., type-design-analyzer's 4-dimensional ratings conveyed more information than a single severity level)
- Initial migration effort across 9 agent files
- Agent prompts become longer (template specification takes space)

### Neutral
- Output format applies to both teammate and subagent execution modes
- Template is markdown (human-readable) not JSON (machine-parseable) — a deliberate choice favoring readability over programmatic processing

## Implementation Notes

1. Cross-validation rules require agent output standardization (phases 1-4) before they can be implemented in `/deep-review` (phase 5). Rules are forward-looking design guidance.
2. Agent-internal reasoning frameworks (e.g., type-design-analyzer's 4-dimensional ratings) remain unchanged. Only the output format changes.
3. All agents follow the same template regardless of execution mode (teammate or subagent).

## Related ADRs

- **ADR-007**: Deterministic Command Orchestrators — cross-validation rules follow deterministic format
- **ADR-012**: Agent Teams Integration — standardized output enables reliable cross-validation in team mode
