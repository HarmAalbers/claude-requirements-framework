#!/usr/bin/env python3
"""Step 15 smoke — end-to-end eval harness validation.

Hard-fails loudly per `[[feedback-loud-smoke-spikes]]`. Verifies:
    1. All required imports succeed (pydantic, claude-agent-sdk).
    2. The 5 golden cases parse and their diffs exist.
    3. The persistent ClaudeSDKClient opens cleanly (judge channel).
    4. The code_reviewer worker runs on each case without error.
    5. score_case computes both metrics and writes valid JSONL.
    6. Median FindingMatch ≥ 0.50 on the 5 cases (proves the harness
       produces real signal; if the model can't find any planted bug
       even partially, something is regressing).
    7. At least one judge call returned a non-None score (proves the
       judge pipeline isn't silently fail-open on every case).

Prereqs:
    pip install -e '.[llm]'
    # Optional: docker compose -f infra/docker-compose.yml up -d  (Langfuse)

Run:
    python3 hooks/lib/llm/_spikes/v3_ragas_eval_smoke.py

Wall-clock: typically 60-120s for the 5-case Haiku run. Persistent
ClaudeSDKClient amortizes subprocess startup (~6-12s) across all 5 cases
plus the judge calls — vs ~5 × 12s = 60s of pure startup if we used
per-call query().
"""

import asyncio
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))


def _refuse_if_extras_missing() -> None:
    missing: list[str] = []
    try:
        import pydantic  # noqa: F401
    except ImportError:
        missing.append("pydantic")
    try:
        import claude_agent_sdk  # noqa: F401
    except ImportError:
        missing.append("claude-agent-sdk")
    if missing:
        sys.stderr.write(
            "ERROR: missing python package(s): " + ", ".join(missing) + "\n"
            "Install with:\n    pip install -e '.[llm]'\n"
        )
        sys.exit(2)


def _refuse_if_golden_set_missing() -> None:
    cases_dir = REPO_ROOT / "golden_set" / "cases"
    if not cases_dir.is_dir():
        sys.stderr.write(f"ERROR: {cases_dir} missing — run from repo root\n")
        sys.exit(3)
    case_files = sorted(cases_dir.glob("*.json"))
    if len(case_files) < 5:
        sys.stderr.write(
            f"ERROR: expected ≥5 cases, found {len(case_files)} in {cases_dir}\n"
        )
        sys.exit(4)


_refuse_if_extras_missing()
_refuse_if_golden_set_missing()


# Imports must follow the guards so a missing extras failure short-circuits
# with a clean error instead of an ImportError stack.
from hooks.lib.llm.eval import (  # noqa: E402
    GoldenCase,
    score_case,
)
from hooks.lib.llm.workers.code_reviewer import review  # noqa: E402


async def _make_judge():
    """Open a persistent ClaudeSDKClient as the judge. Reuses scripts/run_eval.py's
    contract but inlines it here so the smoke is self-contained.
    """
    from scripts.run_eval import make_judge

    judge, close = await make_judge("claude-haiku-4-5")
    if judge is None:
        sys.stderr.write("ERROR: could not open ClaudeSDKClient for judge\n")
        sys.exit(5)
    return judge, close


async def main() -> int:
    cases_dir = REPO_ROOT / "golden_set" / "cases"
    cases = [
        GoldenCase.model_validate_json(p.read_text())
        for p in sorted(cases_dir.glob("*.json"))
    ]
    print(f"Loaded {len(cases)} golden case(s):")
    for c in cases:
        print(f"  - {c.id}  ({c.reference_findings[0].get('category', '?')})")

    print("\nOpening persistent ClaudeSDKClient (Haiku) as judge...")
    judge_start = time.monotonic()
    judge, close_judge = await _make_judge()
    print(f"  judge ready in {time.monotonic() - judge_start:.1f}s")

    out_dir = REPO_ROOT / ".git" / "requirements" / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    ledger = out_dir / "smoke_step_15.jsonl"

    print(f"\nRunning {len(cases)} cases through review() + judge...")
    print(f"Ledger: {ledger}\n")

    scores = []
    cycle_start = time.monotonic()
    try:
        with ledger.open("w") as fh:
            for i, case in enumerate(cases, 1):
                case_start = time.monotonic()
                print(f"[{i}/{len(cases)}] {case.id} ...", flush=True)
                diff = (REPO_ROOT / case.diff_path).read_text()
                report = await review(diff, scope=case.id)
                score = await score_case(
                    case, report, judge=judge, judge_model="claude-haiku-4-5"
                )
                fh.write(score.model_dump_json() + "\n")
                fh.flush()
                scores.append((case, report, score))

                fm = score.finding_match.score if score.finding_match else 0.0
                goal = score.agent_goal_accuracy
                goal_s = f"{goal:.2f}" if goal is not None else "  -"
                print(f"  finding_match={fm:.2f}  goal_accuracy={goal_s}  "
                      f"findings_emitted={len(report.findings)}  "
                      f"({time.monotonic() - case_start:.1f}s)")
    finally:
        assert close_judge is not None  # _make_judge sys.exit's otherwise
        await close_judge()

    cycle_elapsed = time.monotonic() - cycle_start
    print(f"\nCycle wall-clock: {cycle_elapsed:.1f}s")

    fms = [s.finding_match.score for _, _, s in scores if s.finding_match]
    goals = [s.agent_goal_accuracy for _, _, s in scores if s.agent_goal_accuracy is not None]

    median_fm = sorted(fms)[len(fms) // 2] if fms else 0.0
    print(f"FindingMatch median: {median_fm:.2f}  mean: "
          f"{sum(fms) / len(fms):.2f}" if fms else "0.00")
    if goals:
        median_g = sorted(goals)[len(goals) // 2]
        print(f"AgentGoalAccuracy median: {median_g:.2f}  mean: "
              f"{sum(goals) / len(goals):.2f}  ({len(goals)}/{len(cases)} judged)")
    else:
        print("AgentGoalAccuracy: NO judge scores returned — pipeline silently broken?")

    # Hard-fail assertions (loud smoke contract):

    if median_fm < 0.50:
        sys.stderr.write(
            f"\nERROR: median FindingMatch={median_fm:.2f} < 0.50.\n"
            "The code-reviewer worker isn't finding the planted bugs even partially. "
            "Either prompt drift / model regression / golden cases are too cryptic.\n"
        )
        return 6

    if not goals:
        sys.stderr.write(
            "\nERROR: every judge call returned None — the judge pipeline is "
            "silently failing on every case (probably an SDK contract change "
            "in receive_response message shape).\n"
        )
        return 7

    print("\n✓ Step 15 smoke complete.")
    print(f"  - {len(scores)}/{len(cases)} cases scored")
    print(f"  - median FindingMatch {median_fm:.2f} (≥0.50 acceptance threshold)")
    print(f"  - {len(goals)}/{len(cases)} judge scores returned")
    print(f"  - ledger: {ledger}")

    # Print one sample EvalScore as proof the JSONL is well-formed
    print("\nSample EvalScore (first case):")
    print(json.dumps(json.loads(ledger.read_text().splitlines()[0]), indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
