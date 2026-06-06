"""Pydantic output schemas for V3 agent responses.

These models define the structured-output contracts that downstream layers
(aggregation, deduplication, cross-validation) depend on. They are consumed
by Step 10's Instructor wrapper (code-reviewer) and Step 18's PydanticAI
supervisor.

Importing this module requires `pydantic` (ships transitively with the
optional `[llm]` extras: `pip install -e .[llm]`).
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

Severity = Literal["CRITICAL", "IMPORTANT", "SUGGESTION"]

FindingCategory = Literal[
    "security",
    "performance",
    "logic",
    "style",
    "test",
    "compatibility",
    "complexity",
]


class ReviewFinding(BaseModel):
    """One finding from any code-review agent."""

    severity: Severity
    file: str
    line: int = Field(ge=1)
    category: FindingCategory
    title: str = Field(min_length=10, max_length=120)
    body: str
    suggested_fix: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)


class ReviewReport(BaseModel):
    """Aggregate output from a code-review agent."""

    agent: str
    scope: str
    findings: list[ReviewFinding]
    # No max_length bound on summary: the prompt-level guidance ("1-3 sentence
    # summary") is the authoritative constraint. Pydantic max_length=500 was
    # dropped 2026-05-24 (V4.6.0) after the V3 dogfood empirically showed it
    # caused Anthropic's structured-output validator to reject every worker
    # response on large real diffs, surfacing as cryptic
    # "/summary: must NOT have more than 500 characters" errors and burning
    # max_turns retries. Downstream consumers (aggregator, ledger, dogfood
    # artifact) must tolerate variable-length summaries.
    summary: str


class PlanIssue(BaseModel):
    """One issue raised by a planning-gate agent (adr-guardian, tdd-validator, etc.)."""

    severity: Severity
    category: Literal["adr", "tdd", "solid", "refactor", "commit"]
    title: str
    body: str
    suggested_plan_edit: Optional[str] = None


class PlanReport(BaseModel):
    """Aggregate output from /arch-review's planning-gate agents."""

    agent: str
    issues: list[PlanIssue]
    plan_acceptable: bool
    summary: str


class RefactorVerdict(BaseModel):
    """Output from refactor-executor on a single chunk."""

    verdict: Literal["DONE", "NEEDS_CLARIFICATION", "BLOCKED"]
    chunk_id: str
    files_touched: list[str]
    notes: str
    next_steps: Optional[str] = None


class HandoffResult(BaseModel):
    """Supervisor routing decision — which workflow phase to hand off to next.

    `target` is one of the CONFIGURED workflow phase names — the per-project
    `workflow:` phase vocabulary surfaced by `config.get_workflow_phases()`
    and matched 1:1 to `derive_phase`'s output (design, plan-write,
    plan-validate, implement, review, refactor, ship by default; a project may
    reorder/rename/add phases). It is an open `str` rather than a `Literal`
    precisely because that vocabulary is no longer fixed.

    The membership check happens at runtime in `supervisor.route()`, which
    validates `target` against the active phase-name set and clamps a
    hallucinated value back to the input phase. Keeping the schema field a bare
    `str` lets the structured-output validator accept any custom phase name; the
    router owns the semantic guard.
    """

    target: str
    rationale: str
