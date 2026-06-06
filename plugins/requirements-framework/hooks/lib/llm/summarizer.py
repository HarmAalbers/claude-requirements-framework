"""Session-transcript summarizer for Step 13 (Qdrant write side).

Public surface:
    summarize_session(transcript_tail: str) -> str
        Async function. Returns a <=300-char summary suitable for embedding,
        or "" on ANY failure (missing extras, SDK error, validation error,
        timeout, …). The SessionEnd hook checks truthiness before calling
        upsert_session, so an empty return is the signal "skip this session".

Why fail-open here (vs. workers/code_reviewer.py which raises):

    code_reviewer is called from /deep-review where a hard failure surfaces
    to a developer who can act on it. summarize_session is called from a
    PostToolUse SessionEnd hook where there is no developer to act —
    surfacing the exception would just risk breaking session teardown.
    Empty string is the explicit "no embed for this session" signal.

Cost note (Step 17a hook):

    Goes through hooks.lib.llm.claude.query, so the Haiku call is auto-
    recorded in the monthly $-tracker ledger. Per-session cost ≈ $0.001
    (300 chars in, 100 chars out). The wrapper labels the agent as
    "session-summarizer" so budget breakdowns show this distinctly from
    review-agent spend.

Why a Pydantic schema for a single-field summary:

    Using output_format with a strict schema makes the SDK do the JSON
    validation + retries for us. Without it, we'd need to teach the
    model "respond with only the summary text" and risk it returning
    "Here is the summary: ...". The 30 extra tokens for JSON wrapping
    are cheaper than the parsing fragility.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from hooks.lib.llm.claude import ClaudeAgentOptions, ResultMessage, query


class Summary(BaseModel):
    """Output schema for the summarizer Haiku call."""

    text: str = Field(
        ...,
        max_length=400,  # 300 char ceiling + slack for retries before SDK truncates
        description="Concise summary of the session in <=300 chars, focused on what was changed and why.",
    )


_PROMPT_TEMPLATE = (
    "Summarize the following Claude Code session in <= 300 characters. "
    "Focus on: what was changed (files/features), why (motivation/decisions), "
    "and any unresolved questions. Output JSON conforming to the Summary "
    "schema.\n\n"
    "Session transcript (most recent first):\n"
    "{transcript}"
)


def _build_options() -> ClaudeAgentOptions:
    options = ClaudeAgentOptions(
        system_prompt="You are session-summarizer. Output strict JSON only.",
        allowed_tools=[],
        max_turns=2,
        model="claude-haiku-4-5",
    )
    # Same forward-compat pattern as workers/code_reviewer.py: setattr keeps
    # Pyright happy and survives ClaudeAgentOptions dataclass shape changes.
    setattr(options, "output_format", {
        "type": "json_schema",
        "schema": Summary.model_json_schema(),
    })
    try:
        setattr(options, "agent", "session-summarizer")
    except (AttributeError, TypeError):
        pass
    return options


async def summarize_session(transcript_tail: str) -> str:
    """Return a <=300-char summary of `transcript_tail`, or "" on any failure.

    Args:
        transcript_tail: Recent transcript text (caller typically passes the
            last 10-15KB to bound prompt size and cost).

    Returns:
        Summary text, or "" if the SDK errored / extras missing / no
        terminal ResultMessage / validation failed. Callers MUST check
        truthiness before using the result.
    """
    if not transcript_tail:
        return ""

    prompt = _PROMPT_TEMPLATE.format(transcript=transcript_tail)
    options = _build_options()

    try:
        async for msg in query(prompt=prompt, options=options):
            if isinstance(msg, ResultMessage):
                if msg.subtype == "success" and getattr(msg, "structured_output", None):
                    try:
                        return Summary.model_validate(msg.structured_output).text
                    except Exception:
                        return ""  # validation failed — fail-open
                return ""  # any other terminal subtype (error_max_*) → fail-open
        return ""  # no ResultMessage observed — fail-open
    except Exception:
        return ""  # SDK/transport error → fail-open


__all__ = ["Summary", "summarize_session"]
