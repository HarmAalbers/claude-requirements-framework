# Step 10 — Instructor-wrap `code-reviewer`

## Goal

Convert ONE agent (`code-reviewer`) to use Instructor + Pydantic structured output. Pilot. Once proven, Step 18 templates this pattern across the others.

## Why this one

`code-reviewer` is the most-recruited agent (3 workflows). High-volume = highest signal on whether structured output helps.

## Files touched

- `hooks/lib/llm/workers/code_reviewer.py` (new — Python wrapper)
- `plugins/requirements-framework/agents/code-reviewer.md` — add a "structured output" section to body
- `tests/test_code_reviewer_wrapper.py` (new)

## Validated APIs

From the [Instructor docs](https://github.com/567-labs/instructor/blob/main/docs/blog/posts/structured-output-anthropic.md):

```python
import anthropic
import instructor
from pydantic import BaseModel

client = instructor.from_anthropic(anthropic.Anthropic())

class UserDetail(BaseModel):
    name: str
    age: int

user: UserDetail = client.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    response_model=UserDetail,
    max_retries=2,
    messages=[{"role": "user", "content": "..."}],
)
```

Two patterns are valid (both validated this round):
- `instructor.from_anthropic(anthropic.Anthropic())` then `client.create(response_model=...)`
- `instructor.from_provider("openai/gpt-4.1-mini")` — provider string form

We use the explicit Anthropic patch form because it's the documented Claude path.

## Implementation

```python
# hooks/lib/llm/workers/code_reviewer.py
"""Structured-output wrapper around the code-reviewer agent prompt."""
from pathlib import Path
import anthropic
import instructor
from hooks.lib.llm.schemas import ReviewReport

_client = instructor.from_anthropic(anthropic.Anthropic())

_PROMPT_TEMPLATE = (Path(__file__).parent.parent / "prompts" / "code-reviewer.txt").read_text()


def review(diff: str, scope: str = "unstaged changes") -> ReviewReport:
    """Run the code-reviewer agent over the given diff. Returns a typed report.

    On Instructor validation failure the agent re-prompts up to 2 times.
    """
    prompt = _PROMPT_TEMPLATE.format(scope=scope, diff=diff)
    return _client.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        response_model=ReviewReport,
        max_retries=2,
        messages=[{"role": "user", "content": prompt}],
    )
```

The accompanying `prompts/code-reviewer.txt` is the existing agent body, lightly edited to instruct: "Respond ONLY with the JSON schema for ReviewReport. Do not include prose outside the schema." Instructor handles the rest.

## Example call

```python
from hooks.lib.llm.workers.code_reviewer import review
import subprocess

diff = subprocess.check_output(["git", "diff", "HEAD"]).decode()
report = review(diff, scope="HEAD")

for f in report.findings:
    if f.severity == "CRITICAL":
        print(f"❌ {f.file}:{f.line} — {f.title}")
```

## Acceptance

- [ ] Wrapper produces a valid `ReviewReport` for a deliberate-bug diff
- [ ] Validation failure (e.g., Claude returns malformed JSON) triggers retry; succeeds within 2 attempts on the test fixture
- [ ] Test `tests/test_code_reviewer_wrapper.py` mocks Anthropic and asserts the schema is enforced
- [ ] The original `/deep-review` command still runs `code-reviewer` the legacy way — no breaking change yet. Step 18 will switch consumers.

## Rollback

Delete the wrapper. Nothing else consumes it yet.

## Effort

1 day

## Depends on

Steps 08, 09.

## Honest scope note

This step does NOT yet route the existing `/deep-review` through the wrapper. That switch happens in Step 18 (supervisor consolidation), where multiple wrapped agents are aggregated programmatically. This step just proves the pattern works end-to-end on one agent.
