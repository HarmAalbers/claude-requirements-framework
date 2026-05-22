#!/usr/bin/env python3
"""Mirror bundled prompt .txt files into Langfuse Prompt Management.

Step 12. One-shot publisher: reads `hooks/lib/llm/prompts/*.txt` and
upserts each one as a text-typed Langfuse prompt with the
`production` label. After this runs, the PromptLoader at
`hooks.lib.llm.prompts.load_prompt` will fetch from Langfuse on
its next cache-miss instead of falling back to the file.

Why "upsert": `langfuse.create_prompt` is idempotent on content —
if the prompt text is identical to the latest version it's a no-op
on Langfuse's side; if different, a new version is created and the
`production` label is moved to it. That gives a clean
"edit file → run sync → next workers see new version" loop.

Usage:
    # Prereqs (same as the Step 11 smoke):
    cd infra && docker compose up -d
    export LANGFUSE_PUBLIC_KEY=pk-...
    export LANGFUSE_SECRET_KEY=sk-...
    export LANGFUSE_HOST=http://localhost:3000

    python3 scripts/sync_prompts_to_langfuse.py            # publish
    python3 scripts/sync_prompts_to_langfuse.py --dry-run  # list, don't push
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = REPO_ROOT / "hooks" / "lib" / "llm" / "prompts"


def _require_env() -> None:
    missing = [
        k for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST")
        if not os.getenv(k)
    ]
    if missing:
        sys.stderr.write(
            "ERROR: Langfuse env vars not set: "
            + ", ".join(missing)
            + "\nSee scripts/sync_prompts_to_langfuse.py docstring for setup.\n"
        )
        sys.exit(2)


def _discover_prompts() -> list[Path]:
    if not PROMPTS_DIR.is_dir():
        sys.stderr.write(f"ERROR: prompts dir not found: {PROMPTS_DIR}\n")
        sys.exit(2)
    files = sorted(PROMPTS_DIR.glob("*.txt"))
    if not files:
        sys.stderr.write(f"ERROR: no .txt files in {PROMPTS_DIR}\n")
        sys.exit(2)
    return files


def main() -> int:
    description = (__doc__ or "Mirror prompts to Langfuse.").split("\n\n")[0]
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="list what would be synced; don't talk to Langfuse",
    )
    parser.add_argument(
        "--label", default="production",
        help="label to attach (default: production)",
    )
    args = parser.parse_args()

    files = _discover_prompts()

    if args.dry_run:
        print(f"Would sync {len(files)} prompt(s) to Langfuse with label={args.label!r}:")
        for p in files:
            print(f"  {p.stem}  ({p.stat().st_size} bytes)")
        return 0

    _require_env()
    from langfuse import Langfuse
    lf = Langfuse()

    for p in files:
        content = p.read_text()
        result = lf.create_prompt(
            name=p.stem,
            type="text",
            prompt=content,
            labels=[args.label],
        )
        version = getattr(result, "version", "?")
        print(f"synced: {p.stem}  -> version {version}, label {args.label!r}")

    lf.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
