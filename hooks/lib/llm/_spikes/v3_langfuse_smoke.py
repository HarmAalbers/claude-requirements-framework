#!/usr/bin/env python3
"""Step 11 smoke — verifies Langfuse + Claude Agent SDK observability wiring.

Prereqs:
    cd infra && docker compose up -d
    # Bootstrap Langfuse via http://localhost:3000 (see README "Local
    # observability (V3)") and copy the keys.
    export LANGFUSE_PUBLIC_KEY=pk-...
    export LANGFUSE_SECRET_KEY=sk-...
    export LANGFUSE_HOST=http://localhost:3000

Run:
    python3 hooks/lib/llm/_spikes/v3_langfuse_smoke.py

Verify:
    Open http://localhost:3000 → Traces tab → look for a trace from the last
    minute. Expected attributes: model=claude-sonnet-4-6, input_tokens > 0,
    output_tokens > 0, output_format schema name = ReviewFinding.
"""

import asyncio
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))


def _refuse_if_observability_will_silently_disable() -> None:
    """Hard-fail when this spike cannot possibly produce traces.

    The observability module is fail-open by design — if env vars are
    missing or the OpenInference extra isn't installed, init_observability()
    logs at INFO and returns, and the SDK runs untraced. That makes a
    misconfigured spike look identical to a successful one ("✓ Got
    ReviewFinding" prints, Langfuse stays empty). The whole purpose of
    this spike is to verify traces appear, so we refuse to run when the
    environment guarantees they won't.
    """
    missing = [
        v
        for v in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST")
        if not os.getenv(v)
    ]
    if missing:
        sys.stderr.write(
            "ERROR: missing env var(s): " + ", ".join(missing) + "\n"
            "This smoke spike only makes sense with Langfuse credentials set.\n"
            "See the prereqs section in this file's module docstring.\n"
        )
        sys.exit(2)


_refuse_if_observability_will_silently_disable()

# R7: import from the V3 wrapper, not claude_agent_sdk directly.
# The wrapper initializes observability at its own import time, guaranteeing
# the monkey-patch is in place before query() resolves.
from hooks.lib.llm.claude import (  # noqa: E402  — must follow env-var guard above
    ClaudeAgentOptions,
    ResultMessage,
    query,
)
from hooks.lib.llm.schemas import ReviewFinding  # noqa: E402
from hooks.lib.llm import observability  # noqa: E402

if not observability._instrumented:
    # Env vars were set (the pre-flight passed) but instrumentation still
    # didn't run — almost always the OpenInference extra missing.
    sys.stderr.write(
        "ERROR: env vars are set but ClaudeAgentSDKInstrumentor did not "
        "initialize.\n"
        "Most likely cause: openinference-instrumentation-claude-agent-sdk "
        "is not installed.\n"
        "Fix: pip install -e '.[llm]' (from the repo root)\n"
        "Set LANGFUSE_DEBUG=1 and re-run for a traceback.\n"
    )
    sys.exit(3)


async def main() -> int:
    start = time.monotonic()
    prompt = (
        "Review this one-line diff for issues. Return a single ReviewFinding "
        "with severity SUGGESTION if all is well.\n\n"
        "@@ -1 +1 @@\n-print('hi')\n+print('hi')\n"
    )
    options = ClaudeAgentOptions(
        system_prompt="You are a code reviewer. Return one ReviewFinding.",
        model="claude-sonnet-4-6",
        allowed_tools=[],
        max_turns=5,
        output_format={
            "type": "json_schema",
            "schema": ReviewFinding.model_json_schema(),
        },
    )

    async for msg in query(prompt=prompt, options=options):
        if isinstance(msg, ResultMessage):
            if msg.subtype == "success":
                finding = ReviewFinding.model_validate(msg.structured_output)
                print(f"✓ Got ReviewFinding: severity={finding.severity}, "
                      f"category={finding.category}")
            else:
                print(f"✗ query failed: subtype={msg.subtype}")
                return 1

    elapsed = time.monotonic() - start
    print(f"\nElapsed: {elapsed:.1f}s")
    print("→ Now open http://localhost:3000 → Traces and look for the most "
          "recent claude_agent_sdk.query span.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
