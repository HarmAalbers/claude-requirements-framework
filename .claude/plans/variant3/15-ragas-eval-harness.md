# Step 15 — Ragas eval harness + golden set

## Goal

Score every traced agent run with Ragas metrics: `ToolCallAccuracy` (where applicable) and `AgentGoalAccuracy`. Build a small golden-set of 20 known-bug commits with expected findings. Post scores to Langfuse traces.

## Why now

We have traces (Step 11) and structured outputs (Step 10). Now we measure quality. Without measurement, every prompt change is gambling.

## Files touched

- `hooks/lib/llm/eval.py` (populated)
- `golden_set/README.md` (new — how to add a golden case)
- `golden_set/cases/*.json` (initial 20 cases)
- `scripts/run_eval.py` (new — nightly cron)
- `hooks/handle-stop.py` — add per-session roll-up (guarded)

## Validated APIs (from [Ragas agent metrics docs](https://github.com/vibrantlabsai/ragas/blob/main/docs/concepts/metrics/available_metrics/agents.md))

### ToolCallAccuracy
```python
from ragas.metrics.collections import ToolCallAccuracy
from ragas.messages import HumanMessage, AIMessage, ToolCall

result = await ToolCallAccuracy().ascore(
    user_input=[HumanMessage(content="..."), AIMessage(content="...",
                tool_calls=[ToolCall(name="weather_check", args={"location": "NY"})])],
    reference_tool_calls=[ToolCall(name="weather_check", args={"location": "NY"})],
)
print(result.value)   # float in [0,1]
```

### AgentGoalAccuracyWithReference
```python
from ragas.dataset_schema import MultiTurnSample
from ragas.metrics import AgentGoalAccuracyWithReference
from ragas.llms import LangchainLLMWrapper

sample = MultiTurnSample(user_input=ragas_trace, reference="Find the SQL injection on auth.py:42")
scorer = AgentGoalAccuracyWithReference()
scorer.llm = LangchainLLMWrapper(ChatOpenAI(model="gpt-4o-mini"))
score = await scorer.multi_turn_ascore(sample)
```

## Implementation

### Eval module
```python
# hooks/lib/llm/eval.py
"""Ragas eval wrappers. Score is posted back to Langfuse trace."""
import os
from langfuse import Langfuse
from ragas.metrics.collections import ToolCallAccuracy
from ragas.metrics import AgentGoalAccuracyWithReference
from ragas.dataset_schema import MultiTurnSample
from ragas.messages import HumanMessage, AIMessage, ToolCall

_lf = Langfuse() if os.getenv("LANGFUSE_PUBLIC_KEY") else None

async def score_tool_calls(trace_id: str, actual: list, reference: list) -> float:
    result = await ToolCallAccuracy().ascore(user_input=actual, reference_tool_calls=reference)
    if _lf:
        _lf.score(trace_id=trace_id, name="tool_call_accuracy", value=result.value)
    return result.value

async def score_goal_accuracy(trace_id: str, conv: list, reference: str, evaluator_llm) -> float:
    sample = MultiTurnSample(user_input=conv, reference=reference)
    scorer = AgentGoalAccuracyWithReference()
    scorer.llm = evaluator_llm
    score = await scorer.multi_turn_ascore(sample)
    if _lf:
        _lf.score(trace_id=trace_id, name="agent_goal_accuracy", value=score)
    return score
```

### Golden case format
```jsonc
// golden_set/cases/001-sql-injection-auth.json
{
  "id": "001-sql-injection-auth",
  "agent": "appsec-auditor",
  "diff_path": "golden_set/diffs/001.diff",
  "reference_findings": [
    { "file": "auth.py", "line": 42, "category": "security",
      "title_substring": "SQL injection" }
  ],
  "reference_goal": "Detect SQL injection in auth.py line 42 with CRITICAL severity"
}
```

### Run-eval script
```python
# scripts/run_eval.py
"""Nightly: replay each golden case through the agent; record score."""
import json, asyncio
from pathlib import Path
from hooks.lib.llm.workers.code_reviewer import review
from hooks.lib.llm.eval import score_goal_accuracy

async def main():
    for case_path in Path("golden_set/cases").glob("*.json"):
        case = json.loads(case_path.read_text())
        diff = Path(case["diff_path"]).read_text()
        report = review(diff, scope=case["id"])
        # Convert report into a Ragas-compatible conversation trace
        conv = [...]  # adapter; see eval.py
        score = await score_goal_accuracy(
            trace_id=case["id"], conv=conv, reference=case["reference_goal"],
            evaluator_llm=...)
        print(f"{case['id']}: {score:.2f}")

asyncio.run(main())
```

## Acceptance

- [ ] 20 golden cases authored (mix of severities, categories)
- [ ] `python scripts/run_eval.py` runs to completion and prints scores
- [ ] Scores appear on Langfuse trace records (verify in UI)
- [ ] Production target met initially: `agent_goal_accuracy ≥ 0.85` median across 20 cases
- [ ] CI job runs the script weekly and fails build if median drops by > 0.1

## Rollback

Disable the CI job. `eval.py` is opt-in.

## Effort

2 days (mostly the golden set curation).

## Depends on

Steps 09, 10, 11.

## Honest scope notes

- Authoring golden cases is one-time human effort. ~1 hour per case for 20 cases.
- Initial reference language can be loose; tighten after first eval cycle reveals which signals matter.
- For ToolCallAccuracy specifically: applies only to agents that *use tools*. The code-review agents mostly don't — they read + emit findings. For those, `AgentGoalAccuracyWithReference` is the right metric.
