"""V3-safe re-export of the Claude Agent SDK with observability pre-initialized.

V3 code SHOULD import from this module rather than from `claude_agent_sdk`
directly. Rationale (R7 / arch-review M2): the OpenInference instrumentor
monkey-patches `claude_agent_sdk.query` and `ClaudeSDKClient` at instrument
time. Any module that imported those symbols BEFORE instrumentation will
hold references to the un-traced originals. Routing all V3 imports through
this wrapper guarantees the right import order without relying on developer
discipline.

Usage:
    from hooks.lib.llm.claude import query, ClaudeSDKClient, ClaudeAgentOptions

The module body calls init_observability() once at import time. If env vars
or extras are missing, observability silently no-ops (per R1) and these
symbols still work — they just don't produce traces.
"""

from __future__ import annotations

# Step 1 — initialize observability BEFORE importing claude_agent_sdk.
from hooks.lib.llm.observability import init_observability

init_observability()

# Step 2 — now import (or re-import) the SDK. The instrumentor's monkey-patch
# is already in place if observability was successfully enabled.
from claude_agent_sdk import (  # noqa: E402 — order is the point
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    query,
)

__all__ = [
    "ClaudeAgentOptions",
    "ClaudeSDKClient",
    "ResultMessage",
    "query",
]
