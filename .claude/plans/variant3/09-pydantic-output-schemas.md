# Step 09 — Pydantic output schemas

## Goal

Define Pydantic models for the structured output every agent will return going forward. Establishes the contract that downstream aggregation, deduplication, and cross-validation depend on.

## Why now

Before we wrap any agent with Instructor (Step 10), we need the target shape. Defining schemas first lets us design contracts before behavior.

## Files touched

- `hooks/lib/llm/schemas.py` (populated; was placeholder in Step 08)
- `tests/test_schemas.py` (new)

## Validated APIs

Pydantic v2 — standard. `BaseModel`, `Field`, `Literal`, model_dump_json. No new validation needed.

## Implementation

```python
# hooks/lib/llm/schemas.py
from pydantic import BaseModel, Field
from typing import Literal, Optional

Severity = Literal["CRITICAL", "IMPORTANT", "NICE_TO_HAVE"]
FindingCategory = Literal["security", "performance", "logic", "style", "test",
                          "compatibility", "complexity"]


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
    """Output from /arch-review."""
    agent: str
    issues: list[PlanIssue]
    plan_acceptable: bool
    summary: str


class RefactorVerdict(BaseModel):
    """Output from refactor-executor."""
    verdict: Literal["DONE", "NEEDS_CLARIFICATION", "BLOCKED"]
    chunk_id: str
    files_touched: list[str]
    notes: str
    next_steps: Optional[str] = None


class HandoffResult(BaseModel):
    """Output from the supervisor — which command to invoke next."""
    target: Literal["brainstorm", "arch-review", "execute-plan",
                    "deep-review", "refactor-orchestrate",
                    "finishing-a-development-branch"]
    rationale: str
```

## Example use

```python
from hooks.lib.llm.schemas import ReviewFinding, ReviewReport

finding = ReviewFinding(
    severity="CRITICAL", file="auth.py", line=42, category="security",
    title="SQL injection in user lookup",
    body="String-built SQL query allows injection of arbitrary clauses.",
    suggested_fix="Use parameterized query: cursor.execute(sql, (user_id,))",
    confidence=0.95,
)
print(finding.model_dump_json(indent=2))
```

## Acceptance

- [ ] `python -c "from hooks.lib.llm.schemas import ReviewReport"` works
- [ ] `tests/test_schemas.py` covers: valid construction, validation error on missing fields, JSON round-trip
- [ ] Schemas use Pydantic v2 `Field(...)` validators consistently
- [ ] No existing behavior changes

## Rollback

Delete `schemas.py`. No other code references it yet (Step 10 will).

## Effort

0.5 day

## Depends on

Step 08.
