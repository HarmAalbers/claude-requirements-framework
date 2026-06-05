"""Ragas eval harness for V3 review workers (Step 15).

Public surface:
    GoldenCase           — Pydantic model for a single labeled eval case
    FindingMatch         — Pydantic structural-match metric (file/line/category)
    EvalScore            — Pydantic typed eval result (per case)
    compute_finding_match(report, reference, line_tolerance=2)
        -> FindingMatch (best-of-N across report.findings)
    score_case(case, report, *, judge=None, judge_model="claude-haiku-4-5")
        -> EvalScore (async; judge is an optional async callable)
    post_to_langfuse(trace_id, name, value) -> bool
        — env-gated, fail-open

Design notes:

1. **Two metrics, two reasons.** `FindingMatch` is deterministic, fast, and
   variance-free — it answers "did the report mention the right file/line/
   category?". `AgentGoalAccuracyWithReference` (via the injected `judge`)
   is semantic — it answers "did the agent meet the natural-language goal?".
   Both are written to the same `EvalScore` so downstream consumers can use
   either signal.

2. **Injected judge, not imported Ragas.** `score_case` accepts a `judge:
   Callable[[ReviewReport, str], Awaitable[float]] | None`. The smoke spike
   wires a real Ragas-backed judge; tests pass `async def
   fake_judge(...)`. This keeps the test suite Ragas-free and lets us swap
   judge implementations without touching scoring code.

3. **Fail-open on judge errors.** A broken judge (network blip, malformed
   Ragas response, expired auth) sets `agent_goal_accuracy = None` and
   leaves `finding_match` intact. Eval cycles must not crash mid-run because
   one case's judge call hiccupped.

4. **Best-of-N finding match.** A `ReviewReport` typically contains many
   findings; only one is "the planted bug". We compute `FindingMatch` for
   every candidate finding and return the one with the highest score. This
   means a noisy report with one perfect match still scores 1.0 — which is
   the right contract for "did the reviewer find the bug?" (vs. "was every
   finding correct?", which would be a separate precision metric).

5. **Langfuse posting is env-gated.** `post_to_langfuse` returns False when
   `LANGFUSE_PUBLIC_KEY` is unset or `trace_id` is None, never raising.
   Callers don't need to check the env themselves.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from hooks.lib.llm.schemas import ReviewReport

# Type alias for an async judge: takes a report + reference goal string,
# returns a [0, 1] semantic score (or raises, which is caught upstream).
JudgeFn = Callable[[ReviewReport, str], Awaitable[float]]


class GoldenCase(BaseModel):
    """One labeled eval case loaded from `golden_set/cases/*.json`."""

    id: str
    agent: str
    diff_path: str
    reference_findings: list[dict[str, Any]]
    reference_goal: str


class FindingMatch(BaseModel):
    """Deterministic structural match between one expected reference and one
    actual finding. Score is the arithmetic mean of the three flags."""

    file_match: bool
    line_match: bool
    category_match: bool

    @property
    def score(self) -> float:
        return (
            int(self.file_match)
            + int(self.line_match)
            + int(self.category_match)
        ) / 3.0


class EvalScore(BaseModel):
    """Per-case eval result. Persisted as one line of the JSONL ledger."""

    case_id: str
    finding_match: Optional[FindingMatch] = None
    agent_goal_accuracy: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    judge_model: str
    ran_at: str


def _match_one(
    finding_file: str,
    finding_line: int,
    finding_category: str,
    reference: dict[str, Any],
    line_tolerance: int,
) -> FindingMatch:
    return FindingMatch(
        file_match=(finding_file == reference.get("file")),
        line_match=(
            abs(int(finding_line) - int(reference.get("line", 0))) <= line_tolerance
        ),
        category_match=(finding_category == reference.get("category")),
    )


def compute_finding_match(
    report: ReviewReport,
    reference: dict[str, Any],
    line_tolerance: int = 2,
) -> FindingMatch:
    """Best-of-N: score every finding in report against `reference`, return max.

    Empty report → all flags False (score 0.0). Reference dict must contain
    `file`, `line`, `category` keys (additional keys ignored).
    """
    if not report.findings:
        return FindingMatch(file_match=False, line_match=False, category_match=False)

    best: FindingMatch | None = None
    for f in report.findings:
        m = _match_one(f.file, f.line, f.category, reference, line_tolerance)
        if best is None or m.score > best.score:
            best = m
    # mypy: best is not None here because report.findings is non-empty
    assert best is not None
    return best


async def score_case(
    case: GoldenCase,
    report: ReviewReport,
    *,
    judge: Optional[JudgeFn] = None,
    judge_model: str = "claude-haiku-4-5",
) -> EvalScore:
    """Compute both metrics for one case+report pair.

    `judge` is an async callable; if None, agent_goal_accuracy is skipped.
    Judge exceptions are caught and treated as "no score" — they never
    cancel a multi-case eval run.

    Uses the first entry in `case.reference_findings` for FindingMatch.
    Multi-reference cases are out of scope for v1; the harness contract is
    "the planted bug" (singular).
    """
    fm: FindingMatch | None = None
    if case.reference_findings:
        fm = compute_finding_match(report, case.reference_findings[0])

    goal_acc: float | None = None
    if judge is not None:
        try:
            goal_acc = float(await judge(report, case.reference_goal))
        except Exception:
            goal_acc = None  # fail-open

    return EvalScore(
        case_id=case.id,
        finding_match=fm,
        agent_goal_accuracy=goal_acc,
        judge_model=judge_model,
        ran_at=datetime.now(UTC).isoformat(),
    )


def post_to_langfuse(
    trace_id: str | None, name: str, value: float
) -> bool:
    """Send one score to Langfuse, env-gated. Returns True on successful send.

    Skips silently (returns False) when:
        - LANGFUSE_PUBLIC_KEY is unset
        - trace_id is None (caller has no trace to attach the score to)
        - the `langfuse` package is missing
        - the Langfuse client raises
    """
    if not os.getenv("LANGFUSE_PUBLIC_KEY"):
        return False
    if trace_id is None:
        return False
    try:
        from langfuse import Langfuse

        client = Langfuse()
        # langfuse v3 renamed Langfuse.score() -> create_score(); the old name
        # raises AttributeError (swallowed below), so scores silently never posted.
        client.create_score(trace_id=trace_id, name=name, value=value)
        client.flush()
        return True
    except Exception:
        return False
