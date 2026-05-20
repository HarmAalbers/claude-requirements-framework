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
    summary: str = Field(max_length=500)


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
    """Supervisor routing decision — which command to invoke next.

    Targets match the handoff tools exposed by `hooks/lib/llm/supervisor.py`
    (Step 18). When that supervisor lands, this literal becomes its
    `output_type` contract.
    """

    target: Literal[
        "brainstorm",
        "arch-review",
        "execute-plan",
        "deep-review",
        "refactor-orchestrate",
        "ship",
    ]
    rationale: str
