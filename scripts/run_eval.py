#!/usr/bin/env python3
"""Step 15 eval CLI driver.

Loads golden cases from `golden_set/cases/*.json`, replays each through
the `code_reviewer` worker, scores both `FindingMatch` (deterministic) and
`AgentGoalAccuracyWithReference`-style (LLM-judged) metrics, writes a
JSONL ledger to `.git/requirements/eval/`, and optionally posts scores to
Langfuse.

Usage:
    python3 scripts/run_eval.py                          # all cases, Haiku judge
    python3 scripts/run_eval.py --judge sonnet           # escalate judge
    python3 scripts/run_eval.py --cases '001-*.json'     # subset
    python3 scripts/run_eval.py --no-langfuse            # skip Langfuse posting

Exit codes:
    0  — all cases scored (regardless of score values)
    1  — invalid args or unrecoverable load error
    2  — required extras missing (pydantic / claude-agent-sdk)

Note on the "Ragas judge":
    v1 uses a direct prompt-and-parse via persistent ClaudeSDKClient — the
    same idea as Ragas's AgentGoalAccuracyWithReference, but without the
    Ragas BaseRagasLLM adapter. We satisfy the JudgeFn protocol defined in
    hooks/lib/llm/eval.py; the smoke spike validates the contract end-to-end.
    Upgrading to a real Ragas LLM adapter is a deliberate future patch
    (gated on whether the simpler judge produces sufficiently variant
    scores in practice).
"""

import argparse
import asyncio
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _branch() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def _load_cases(pattern: str) -> list[Any]:
    """Load cases matching glob (relative to golden_set/cases/)."""
    from hooks.lib.llm.eval import GoldenCase

    cases_dir = REPO_ROOT / "golden_set" / "cases"
    paths = sorted(cases_dir.glob(pattern))
    if not paths:
        sys.stderr.write(f"ERROR: no cases matched {pattern!r} in {cases_dir}\n")
        sys.exit(1)
    out = []
    for p in paths:
        try:
            out.append(GoldenCase.model_validate_json(p.read_text()))
        except Exception as exc:
            sys.stderr.write(f"ERROR: failed to parse {p}: {exc}\n")
            sys.exit(1)
    return out


JUDGE_PROMPT_TEMPLATE = """You are evaluating whether an automated code-review agent met a specific goal.

GOAL: {goal}

AGENT REPORT (JSON):
{report_json}

Did the agent meet the goal? Score from 0.0 (did not meet at all) to 1.0 (fully met).

Respond with EXACTLY one line:
    SCORE: <number between 0.0 and 1.0>
"""


SCORE_RE = re.compile(r"SCORE:\s*([0-9]*\.?[0-9]+)")


async def make_judge(judge_model: str):
    """Open a persistent ClaudeSDKClient and return (judge_fn, close_fn).

    The closure captures the client so calls to judge_fn reuse the same
    subprocess. close_fn is called once at the end of the eval cycle.
    Returns (None, None) if the SDK or claude wrapper can't be imported.
    """
    try:
        from hooks.lib.llm.claude import ClaudeAgentOptions, ClaudeSDKClient
    except Exception as exc:
        sys.stderr.write(f"WARN: cannot import claude-agent-sdk: {exc}\n")
        return None, None

    client = ClaudeSDKClient(
        options=ClaudeAgentOptions(model=judge_model)
    )
    await client.__aenter__()

    async def judge(report, reference: str) -> float:
        prompt = JUDGE_PROMPT_TEMPLATE.format(
            goal=reference,
            report_json=report.model_dump_json(indent=2),
        )
        await client.query(prompt)
        text_parts: list[str] = []
        async for msg in client.receive_response():
            # Concatenate any content the SDK surfaces; different SDK versions
            # use slightly different message shapes, so we duck-type.
            content = getattr(msg, "content", None) or getattr(msg, "text", None)
            if isinstance(content, str):
                text_parts.append(content)
            elif isinstance(content, list):
                for block in content:
                    block_text = getattr(block, "text", None)
                    if isinstance(block_text, str):
                        text_parts.append(block_text)
        text = "".join(text_parts)
        m = SCORE_RE.search(text)
        if not m:
            raise ValueError(f"judge produced no parseable SCORE line: {text[:200]!r}")
        return max(0.0, min(1.0, float(m.group(1))))

    async def close():
        await client.__aexit__(None, None, None)

    return judge, close


def _ledger_path() -> Path:
    out_dir = REPO_ROOT / ".git" / "requirements" / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
    branch = _branch().replace("/", "-")
    return out_dir / f"{stamp}_{branch}.jsonl"


async def run(args: argparse.Namespace) -> int:
    try:
        from hooks.lib.llm.eval import post_to_langfuse, score_case
        from hooks.lib.llm.workers.code_reviewer import review
    except Exception as exc:
        sys.stderr.write(f"ERROR: required extras missing: {exc}\n"
                         "Install with: pip install -e '.[llm]'\n")
        return 2

    cases = _load_cases(args.cases)
    print(f"Loaded {len(cases)} case(s) from golden_set/cases/")

    # Resolve the judge_model label unconditionally so EvalScore.judge_model
    # always has the right value, even when --no-judge is set ("none" in that case).
    judge_model = "claude-sonnet-4-6" if args.judge == "sonnet" else "claude-haiku-4-5"
    judge, close_judge = (None, None)
    if not args.no_judge:
        print(f"Opening persistent ClaudeSDKClient for judge ({judge_model})...")
        judge, close_judge = await make_judge(judge_model)
        if judge is None:
            print("  (judge unavailable — proceeding with FindingMatch only)")

    ledger = _ledger_path()
    print(f"Ledger: {ledger}\n")

    start = time.monotonic()
    scores: list[Any] = []
    try:
        with ledger.open("w") as fh:
            for i, case in enumerate(cases, 1):
                case_start = time.monotonic()
                print(f"[{i}/{len(cases)}] {case.id} ...", flush=True)
                diff_path = REPO_ROOT / case.diff_path
                diff = diff_path.read_text()
                try:
                    report = await review(diff, scope=case.id)
                except Exception as exc:
                    sys.stderr.write(f"  ERROR: review failed for {case.id}: {exc}\n")
                    continue

                score = await score_case(
                    case, report,
                    judge=judge,
                    judge_model=judge_model if judge else "none",
                )
                fh.write(score.model_dump_json() + "\n")
                fh.flush()
                scores.append(score)

                fm = score.finding_match.score if score.finding_match else 0.0
                goal = score.agent_goal_accuracy
                goal_s = f"{goal:.2f}" if goal is not None else "  -"
                print(f"  finding_match={fm:.2f}  goal_accuracy={goal_s}  "
                      f"({time.monotonic() - case_start:.1f}s)")

                if not args.no_langfuse:
                    # Trace IDs aren't currently surfaced from review() — once
                    # observability spans expose them on the ResultMessage we'll
                    # wire them through; for now, post against the case id so
                    # scores at least cluster correctly in the Langfuse UI.
                    post_to_langfuse(case.id, "finding_match", fm)
                    if goal is not None:
                        post_to_langfuse(case.id, "agent_goal_accuracy", goal)
    finally:
        if close_judge:
            await close_judge()

    elapsed = time.monotonic() - start
    if not scores:
        sys.stderr.write("ERROR: no cases scored — review() failed on all of them\n")
        return 1

    fms = [s.finding_match.score for s in scores if s.finding_match]
    goals = [s.agent_goal_accuracy for s in scores if s.agent_goal_accuracy is not None]
    print()
    print(f"Wall-clock: {elapsed:.1f}s for {len(scores)}/{len(cases)} case(s)")
    if fms:
        print(f"FindingMatch — median {sorted(fms)[len(fms)//2]:.2f}, "
              f"mean {sum(fms)/len(fms):.2f}")
    if goals:
        print(f"AgentGoalAccuracy — median {sorted(goals)[len(goals)//2]:.2f}, "
              f"mean {sum(goals)/len(goals):.2f}")
    print(f"Ledger: {ledger}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Run Step 15 eval harness")
    ap.add_argument("--judge", choices=["haiku", "sonnet"], default="haiku",
                    help="Judge model (default: haiku)")
    ap.add_argument("--cases", default="*.json",
                    help="Glob pattern for cases under golden_set/cases/ (default: *.json)")
    ap.add_argument("--no-langfuse", action="store_true",
                    help="Skip Langfuse score posting even if LANGFUSE_PUBLIC_KEY is set")
    ap.add_argument("--no-judge", action="store_true",
                    help="Skip the LLM judge — compute FindingMatch only (free, fast)")
    args = ap.parse_args()
    if not os.getenv("LANGFUSE_PUBLIC_KEY"):
        args.no_langfuse = True
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
