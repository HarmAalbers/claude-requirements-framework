#!/usr/bin/env python3
"""Mirror golden_set/cases/*.json into a Langfuse dataset.

The golden set is the local ground truth for the eval harness
(`scripts/run_eval.py`, `hooks/lib/llm/eval.py`). Uploading it as a
Langfuse dataset enables what local JSON can't:

  - in-UI prompt experiments against the cases (paired with the
    `--playground` prompt variants from sync_prompts_to_langfuse.py)
  - dataset runs comparable in the Experiments UI
  - judge calibration for `agent_goal_accuracy` as a Langfuse
    experiment (see the langfuse skill's judge-calibration reference)

Mapping (one dataset item per case JSON):
  id              <- case "id" (stable; Langfuse upserts dataset items
                     by id, so re-runs are idempotent server-side —
                     unlike prompts, which need our client-side compare)
  input           <- {"agent": ..., "diff": <contents of diff_path>}
                     (diff text inlined so the dataset is self-contained)
  expected_output <- {"reference_findings": ..., "reference_goal": ...}
  metadata        <- {"diff_path": ..., "source": "golden_set"}

The files stay the source of truth — same convention as prompts: edit
cases locally, re-run this script. Don't edit items in the UI.

Loud-failure contract: this is tooling, not library code. A case that
references a missing diff file aborts the run before anything syncs
(fail-open belongs in the runtime loader, not in publish scripts).

Usage:
    python3 scripts/sync_golden_set_to_langfuse.py             # publish
    python3 scripts/sync_golden_set_to_langfuse.py --dry-run   # list only
    python3 scripts/sync_golden_set_to_langfuse.py --dataset NAME
"""

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_ROOT = REPO_ROOT / "golden_set"
DEFAULT_DATASET = "golden-set"


def _load_dotenv() -> None:
    """Same cred source as the other Langfuse scripts: `infra/.env` first,
    then repo `.env`; shell env wins. Soft-dep on python-dotenv."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for candidate in (REPO_ROOT / "infra" / ".env", REPO_ROOT / ".env"):
        if candidate.is_file():
            load_dotenv(candidate, override=False)


def _require_env() -> None:
    missing = [
        k for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST")
        if not os.getenv(k)
    ]
    if missing:
        sys.stderr.write(
            "ERROR: Langfuse env vars not set: "
            + ", ".join(missing)
            + "\nSee scripts/sync_golden_set_to_langfuse.py docstring for setup.\n"
        )
        sys.exit(2)


def _discover_cases(root: Path) -> list[Path]:
    cases_dir = root / "cases"
    if not cases_dir.is_dir():
        sys.stderr.write(f"ERROR: cases dir not found: {cases_dir}\n")
        sys.exit(2)
    files = sorted(cases_dir.glob("*.json"))
    if not files:
        sys.stderr.write(f"ERROR: no case JSON files in {cases_dir}\n")
        sys.exit(2)
    return files


def _load_case(path: Path, root: Path) -> dict:
    """Parse one case and inline its diff. Hard-fails on schema gaps or a
    missing diff file — a half-synced dataset is worse than no sync."""
    case = json.loads(path.read_text())
    for key in ("id", "agent", "diff_path", "reference_findings", "reference_goal"):
        if key not in case:
            sys.stderr.write(f"ERROR: {path.name} missing required key {key!r}\n")
            sys.exit(2)
    # diff_path is repo-root-relative in the shipped cases ("golden_set/diffs/...")
    # but root-relative paths are accepted too (test fixtures, future layouts).
    diff_file = REPO_ROOT / case["diff_path"]
    if not diff_file.is_file():
        diff_file = root / case["diff_path"]
    if not diff_file.is_file():
        sys.stderr.write(
            f"ERROR: {path.name}: diff file not found: {case['diff_path']}\n"
        )
        raise SystemExit(2)
    case["_diff"] = diff_file.read_text()
    return case


def sync_golden_set(root: Path, lf, *, dataset_name: str) -> int:
    """Upsert all cases under `root` into `dataset_name`. Returns item count.

    All cases are loaded (and validated, diffs inlined) BEFORE any network
    write — a broken case aborts the whole run with nothing synced.
    """
    cases = [_load_case(p, root) for p in _discover_cases(root)]

    try:
        lf.get_dataset(dataset_name)
    except Exception:
        lf.create_dataset(
            name=dataset_name,
            description="Golden review cases mirrored from golden_set/cases/ "
                        "(file-first; edit locally and re-sync).",
            metadata={"source": "golden_set"},
        )
        print(f"created dataset: {dataset_name}")

    for case in cases:
        lf.create_dataset_item(
            dataset_name=dataset_name,
            id=case["id"],
            input={"agent": case["agent"], "diff": case["_diff"]},
            expected_output={
                "reference_findings": case["reference_findings"],
                "reference_goal": case["reference_goal"],
            },
            metadata={"diff_path": case["diff_path"], "source": "golden_set"},
        )
        print(f"upserted: {case['id']}")
    return len(cases)


def main() -> int:
    description = (__doc__ or "Mirror the golden set to Langfuse.").split("\n\n")[0]
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="list what would be synced; don't talk to Langfuse",
    )
    parser.add_argument(
        "--dataset", default=DEFAULT_DATASET,
        help=f"target dataset name (default: {DEFAULT_DATASET})",
    )
    args = parser.parse_args()

    if args.dry_run:
        files = _discover_cases(GOLDEN_ROOT)
        print(f"Would sync {len(files)} case(s) to dataset {args.dataset!r}:")
        for p in files:
            print(f"  {p.stem}  ({p.stat().st_size} bytes)")
        return 0

    _load_dotenv()
    _require_env()
    from langfuse import Langfuse
    lf = Langfuse()

    n = sync_golden_set(GOLDEN_ROOT, lf, dataset_name=args.dataset)
    lf.flush()
    print(f"done: {n} item(s) in dataset {args.dataset!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
