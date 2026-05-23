#!/usr/bin/env python3
"""Step 16 smoke — Jinja2 prompt engine end-to-end (no LLM calls).

Hard-fails loudly per `[[feedback-loud-smoke-spikes]]`. Verifies:
    1. jinja2 importable (extras installed).
    2. All 3 V3 prompt .md.j2 files exist with non-zero size.
    3. Both partials (safety + project_conventions) exist.
    4. Each prompt renders with realistic vars; rendered output contains
       the expected substituted text + partial content.
    5. StrictUndefined raises UndefinedError when a required var is missing
       (proves the contract isn't silently degraded).
    6. Optional Langfuse round-trip: if LANGFUSE_PUBLIC_KEY is set, push
       each .md.j2 source via sync_prompts_to_langfuse, re-fetch, re-render
       with the same vars, assert byte-equivalence with the local render.

What this does NOT do:
    - Call the SDK (no Haiku/Sonnet). The engine doesn't talk to LLMs;
      that's the worker's job. Worker tests cover SDK integration.
    - Test prompt *quality* (whether the rendered prompt produces good LLM
      output). That's the Step 15 eval harness.

Run:
    python3 hooks/lib/llm/_spikes/v3_jinja2_smoke.py

Exit codes:
    0  — engine works end-to-end
    2  — jinja2 missing
    3  — prompt or partial file missing
    4  — render produced unexpected output
    5  — StrictUndefined contract violated
    6  — Langfuse round-trip mismatch (only when env present)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))


def _refuse_if_extras_missing() -> None:
    try:
        import jinja2  # noqa: F401
    except ImportError:
        sys.stderr.write(
            "ERROR: jinja2 not installed.\n"
            "Install with:\n    pip install -e '.[llm]'\n"
        )
        sys.exit(2)


def _refuse_if_files_missing() -> None:
    prompts_dir = REPO_ROOT / "hooks" / "lib" / "llm" / "prompts"
    expected = [
        prompts_dir / "code-reviewer.md.j2",
        prompts_dir / "review-aggregator.md.j2",
        prompts_dir / "req-supervisor.md.j2",
        prompts_dir / "partials" / "safety.j2",
        prompts_dir / "partials" / "project_conventions.j2",
    ]
    missing = [p for p in expected if not p.is_file() or p.stat().st_size == 0]
    if missing:
        sys.stderr.write("ERROR: required prompt/partial files missing:\n")
        for p in missing:
            sys.stderr.write(f"  {p}\n")
        sys.exit(3)


_refuse_if_extras_missing()
_refuse_if_files_missing()


from jinja2 import UndefinedError  # noqa: E402

from hooks.lib.llm.prompts import load_prompt  # noqa: E402


FIXTURES = {
    "code-reviewer": {
        "vars": {
            "diff": "--- a/api/auth.py\n+++ b/api/auth.py\n@@ -1 +1 @@\n-old\n+new SQL injection here",
            "scope": "unstaged",
            "project_conventions": "Use snake_case. No bare excepts.",
        },
        "expectations": [
            "test fixtures",          # from partials/safety.j2
            "Project conventions",    # from partials/project_conventions.j2 (when var passed)
            "snake_case",             # the project_conventions content
            "SQL injection here",     # the diff content
            "'unstaged'",             # scope with single quotes (repr filter)
        ],
    },
    "review-aggregator": {
        "vars": {
            "reports_json": '[{"agent":"code-reviewer","findings":[{"file":"a.py","line":1}]}]',
        },
        "expectations": [
            "review-aggregator",      # the prompt mentions the agent name
            '"agent":"code-reviewer"',  # rendered reports_json content
        ],
    },
    "req-supervisor": {
        "vars": {
            "phase": "implement",
            "unsatisfied": "pre_pr_review, codex_reviewer",
        },
        "expectations": [
            "implement",
            "pre_pr_review, codex_reviewer",
            "HandoffResult",
        ],
    },
}


def _render_each() -> dict[str, str]:
    """Render all 3 prompts. Fail the smoke if any expected substring is absent."""
    rendered: dict[str, str] = {}
    for name, fixture in FIXTURES.items():
        print(f"  rendering {name} ...", end=" ", flush=True)
        out = load_prompt(name, **fixture["vars"])  # type: ignore[arg-type]
        for needle in fixture["expectations"]:
            if needle not in out:
                sys.stderr.write(
                    f"\nERROR: rendering {name!r} produced output missing {needle!r}\n"
                    f"--- rendered output ({len(out)} chars) ---\n{out[:500]}\n"
                )
                sys.exit(4)
        print(f"OK ({len(out)} chars)")
        rendered[name] = out
    return rendered


def _verify_strict_undefined() -> None:
    """Acceptance test: code-reviewer.md.j2 needs `diff` — omitting it must raise."""
    print("  verifying StrictUndefined raises on missing var ...", end=" ", flush=True)
    try:
        load_prompt("code-reviewer", scope="unstaged")  # `diff` missing on purpose
        sys.stderr.write(
            "\nERROR: load_prompt('code-reviewer', scope=...) succeeded without `diff` var.\n"
            "Expected UndefinedError under StrictUndefined contract.\n"
        )
        sys.exit(5)
    except UndefinedError:
        print("OK (raised UndefinedError as expected)")


def _maybe_langfuse_round_trip(local_rendered: dict[str, str]) -> None:
    """If Langfuse env present, push → fetch → render → assert byte-equivalence."""
    if not os.getenv("LANGFUSE_PUBLIC_KEY"):
        print("  langfuse round-trip skipped (LANGFUSE_PUBLIC_KEY unset)")
        return

    print("  langfuse round-trip: push → fetch → re-render ...")
    try:
        from langfuse import Langfuse
        lf = Langfuse()
    except Exception as exc:
        sys.stderr.write(f"WARN: langfuse client init failed ({exc}); skipping round-trip\n")
        return

    # Push current sources via the sync script's logic (reuse to avoid duplication).
    from scripts.sync_prompts_to_langfuse import (
        _discover_prompts,
        _prompt_name,
    )
    sources = _discover_prompts()
    for p in sources:
        lf.create_prompt(
            name=_prompt_name(p),
            type="text",
            prompt=p.read_text(),
            labels=["smoke-step-16"],
        )
    lf.flush()
    print(f"    pushed {len(sources)} prompts under label 'smoke-step-16'")

    # Re-fetch + render with the smoke fixtures + label override.
    from hooks.lib.llm.templates import render as _render_text
    for name, fixture in FIXTURES.items():
        fetched = lf.get_prompt(name, label="smoke-step-16").prompt
        re_rendered = _render_text(fetched, **fixture["vars"])  # type: ignore[arg-type]
        if re_rendered != local_rendered[name]:
            sys.stderr.write(
                f"\nERROR: langfuse round-trip mismatch for {name!r}\n"
                f"  local len={len(local_rendered[name])} fetched-rendered len={len(re_rendered)}\n"
            )
            sys.exit(6)
        print(f"    ✓ {name}: byte-equivalent ({len(re_rendered)} chars)")


def main() -> int:
    print("Step 16 Jinja2 engine smoke")
    print(f"Repo root: {REPO_ROOT}")
    print()

    print("[1/3] rendering all 3 prompts with realistic vars:")
    rendered = _render_each()
    print()

    print("[2/3] verifying StrictUndefined contract:")
    _verify_strict_undefined()
    print()

    print("[3/3] optional Langfuse round-trip:")
    _maybe_langfuse_round_trip(rendered)
    print()

    print("─" * 60)
    print("Sample rendered output (code-reviewer, first 600 chars):")
    print("─" * 60)
    print(rendered["code-reviewer"][:600])
    print("─" * 60)
    print()

    print("✓ Step 16 smoke complete. Engine works end-to-end (no LLM calls).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
