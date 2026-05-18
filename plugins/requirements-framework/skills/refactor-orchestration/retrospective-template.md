# Retrospective — <Refactor Title>

**Plan:** `.claude/plans/<YYYY-MM-DD>-<slug>.md`
**Orchestrator prompt:** `.claude/plans/<YYYY-MM-DD>-<slug>-orchestrator-prompt.md`
**Branch:** `<branch>`
**Baseline commit:** `<sha>`
**Head commit:** `<sha>`
**Run date:** `<YYYY-MM-DD>`

## 1. Run Summary

| Metric | Value |
|---|---|
| Chunks total | <N> |
| Chunks first-pass-pass | <N> |
| Chunks retried | <N> (avg <X> retries / max <Y>) |
| Chunks escalated to investigator | <N> |
| Chunks escalated to user (AskUserQuestion) | <N> |
| Commits total | <N> |
| Commits per chunk (median) | <ideal: 1.0> |
| Plan sections edited mid-run | <N> (§<list>) |
| Time elapsed | <HH:MM> |

## 2. Per-chunk Signals

| Chunk | Files touched | Retries | Escalation? | Executor "noticed-but-not-changed" |
|---|---|---|---|---|
| A1 | <paths> | 0 | no | <bullets or "none"> |
| A2 | <paths> | <N> (<cause>) | <no / investigator / user> | <bullets> |
| ... | | | | |

## 3. Cross-chunk Patterns

<Group recurring "noticed-but-not-changed" items, recurring retry causes, recurring escalation root causes. One paragraph per pattern; cite the chunks. If a pattern matches an existing learnings.md entry, link the slug.>

### Pattern: <short name>

<Observation. Cite chunks. Link to learnings entry if recurring.>

## 4. Plan-vs-Reality Gaps

<For each plan section that was edited mid-run: what changed, why, what that signals about Stages 1-4 (inventory / design / validation / harmonization). If no mid-run plan edits occurred, write "None — the plan held through execution.">

## 5. Recommendations

<Each recommendation has: target bucket (one of the 5 files), severity (low / medium / high), proposed change (one sentence), rationale (one sentence with chunk citations). Ordered by severity, then by recurrence count.>

### High severity (promoted — proposed via AskUserQuestion this run)

1. **`<target-bucket>`**: <one-sentence change>. Rationale: <one-sentence with chunk citations>.
   - Status: `proposed` / `applied` / `rejected` / `deferred`
   - learnings.md slug: `<obs-slug>` (count: <N>)

### Medium severity (ledger only — not yet at rule-of-three)

1. **`<target-bucket>`**: <observation>. Rationale: <one-sentence>.
   - learnings.md slug: `<obs-slug>` (count: <N>)

### Low severity / one-off observations

1. <observation>. Cited from <chunk>. Not added to ledger.

### Out of scope (outside the 5 buckets)

<Anything that would be useful but isn't an SKILL/template/agent change. E.g. "consider adding a new ADR for X.">

## 6. Learnings Ledger Entries This Run

<Newly created or count-bumped entries this run. Slugs link to anchors in the appropriate ledger: global `~/.claude/refactor-orchestration/learnings.md` (cross-project) or project `.claude/refactor-orchestration/learnings.md` (this repo only).>

| Slug | Status | Count | Affected artifact | One-line observation |
|---|---|---|---|---|
| `<obs-slug>` | open | 1 | SKILL.md | <observation> |
| `<obs-slug>` | open | 2 | refactor-executor.md | <observation> |
| `<obs-slug>` | promoted | 3 | plan-template.md | <observation> |

## 7. Further reading

- `~/.claude/refactor-orchestration/learnings.md` — global ledger (cross-project observations)
- `.claude/refactor-orchestration/learnings.md` — project ledger (this-repo observations, gitignored)
- `.claude/refactor-conventions.md` — auto-grown repo convention sheet (gitignored)
- Bundled `SKILL.md` in this skill's plugin install directory — workflow definition
- `/requirements-framework:session-reflect` (if installed) — general session reflection on the parent session
