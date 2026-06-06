# Golden Set — Step 15 eval harness corpus

Hand-authored synthetic diffs labeled with the bug the code-reviewer worker
*should* find. `scripts/run_eval.py` replays each diff through the
`hooks.lib.llm.workers.code_reviewer.review()` worker and scores the result
against the reference using two metrics defined in `hooks/lib/llm/eval.py`:

- **`FindingMatch`** (deterministic) — did the report mention the expected
  `file`, `line` (±2), and `category`? Score = mean of the three flags.
- **`AgentGoalAccuracyWithReference`** (Ragas, judged by Claude Haiku) — did
  the agent meet the natural-language goal? Score ∈ [0, 1].

## Adding a new case

1. **Write the diff.** Create `diffs/NNN-slug.diff` in unified-diff format
   (the format `git diff` produces). Keep it minimal — the smallest diff
   that surfaces the bug, so the eval signal isn't drowned in noise.
2. **Write the case manifest.** Create `cases/NNN-slug.json`:

   ```json
   {
     "id": "NNN-slug",
     "agent": "code-reviewer",
     "diff_path": "golden_set/diffs/NNN-slug.diff",
     "reference_findings": [
       {
         "file": "path/relative/to/diff/root.py",
         "line": 42,
         "category": "security",
         "severity": "CRITICAL"
       }
     ],
     "reference_goal": "Detect <bug type> in <file> around line <line> with <severity> severity"
   }
   ```

   - `file` must be the exact path the diff touches. The match is exact (not
     fuzzy) — see `FindingMatch.file_match`.
   - `line` is the expected line number. Match tolerance is ±2 lines.
   - `category` must be one of the `FindingCategory` enum values in
     `hooks/lib/llm/schemas.py`: `security`, `performance`, `logic`,
     `style`, `test`, `compatibility`, `complexity`.
   - `severity` is informational for the human reading the manifest; it's
     not currently part of `FindingMatch` (could be added in a future patch).
   - `reference_goal` is the prompt the Ragas judge sees. Be specific:
     mention file, line, and bug type — vague goals score poorly.

3. **Run it.** `python3 scripts/run_eval.py --cases cases/NNN-slug.json`
   to verify the case parses and the harness produces a sensible score.

## Why synthetic, not real bugs?

The initial 5 cases are hand-crafted to cover one bug category each —
control over the signal matters more than realism at this stage. Future
expansion (Step 15b) will mine `git log --grep=fix` for real bug commits and
label them, which catches weirder failure modes that synthetic cases miss.
That's a known follow-up, not an oversight.

## Coverage matrix (as of Step 15 v1)

| ID  | File              | Category    | Severity   | Bug type                       |
|-----|-------------------|-------------|------------|--------------------------------|
| 001 | api/users.py      | security    | CRITICAL   | f-string SQL injection         |
| 002 | services/feed.py  | performance | IMPORTANT  | N+1 ORM query in loop          |
| 003 | lib/window.py     | logic       | IMPORTANT  | Off-by-one array index         |
| 004 | api/handlers.py   | style       | SUGGESTION | Overly permissive `Any` return |
| 005 | services/router.py| complexity  | SUGGESTION | Deeply nested conditional      |

`test` and `compatibility` categories are not yet exercised — they'll come
when real bugs from dogfooding surface those patterns.
