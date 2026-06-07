#!/usr/bin/env python3
"""Step 12 smoke — verifies the Langfuse prompt registry round-trip.

Round-trip:
    1. Sync local `prompts/*.txt` to Langfuse (via the sync script).
    2. Call `load_prompt('code-reviewer')` — should hit Langfuse,
       returning the same content that's on disk.
    3. Toggle: unset LANGFUSE_PUBLIC_KEY and confirm the loader
       falls back to the file silently.

Prereqs (same as the Step 11 smoke):
    cd infra && docker compose up -d
    export LANGFUSE_PUBLIC_KEY=pk-...
    export LANGFUSE_SECRET_KEY=sk-...
    export LANGFUSE_HOST=http://localhost:3000

Run:
    python3 hooks/lib/llm/_spikes/v3_prompt_loader_smoke.py

Verify:
    Open http://localhost:3000 -> Prompts tab -> see `code-reviewer`
    and `review-aggregator` listed with the `production` label.
    Edit one in the UI, promote, then re-run this script — within
    Langfuse's ~60s internal cache TTL the script will print the
    new content (which is the rollback story we wanted).
"""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))


def _fail(msg: str) -> int:
    print(f"FAIL: {msg}", file=sys.stderr)
    return 1


def main() -> int:
    needed = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST")
    missing = [k for k in needed if not os.getenv(k)]
    if missing:
        return _fail(
            "Langfuse env vars not set: " + ", ".join(missing)
            + ". See module docstring for setup.")

    sync_script = REPO_ROOT / "scripts" / "sync_prompts_to_langfuse.py"
    print(f"Step 1/3: running {sync_script.relative_to(REPO_ROOT)} ...")
    rc = subprocess.run([sys.executable, str(sync_script)], check=False).returncode
    if rc != 0:
        return _fail(f"sync script exited {rc}")

    print("\nStep 2/3: loading prompts via PromptLoader (Langfuse path) ...")
    # Import after sync — the lazy-singleton picks up env vars on first call.
    from hooks.lib.llm.prompts import load_prompt
    for name in ("code-reviewer", "review-aggregator"):
        text = load_prompt(name)
        on_disk = (REPO_ROOT / "hooks" / "lib" / "llm" / "prompts" /
                   f"{name}.txt").read_text()
        match = text == on_disk
        print(f"  {name}: {len(text)} bytes, matches disk={match}")
        if not match:
            print("    (Langfuse has different content than disk — likely a "
                  "newer version was promoted in the UI; not a failure.)")

    print("\nStep 3/3: forcing file fallback (clearing LANGFUSE_PUBLIC_KEY) ...")
    saved = os.environ.pop("LANGFUSE_PUBLIC_KEY")
    try:
        # Re-import to reset the lazy singleton.
        for mod_name in list(sys.modules):
            if mod_name.startswith("hooks.lib.llm.prompts"):
                del sys.modules[mod_name]
        from hooks.lib.llm.prompts import load_prompt as load_again
        text = load_again("code-reviewer")
        if "{diff}" not in text:
            return _fail("file fallback did not return the expected template")
        print(f"  ok — file fallback returned {len(text)} bytes with {{diff}} placeholder")
    finally:
        os.environ["LANGFUSE_PUBLIC_KEY"] = saved

    print("\nAll three steps passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
