"""LLM platform package for the requirements-framework V3 layer.

Submodules are populated by later V3 steps (see `.claude/plans/variant3/`):
    schemas        — Pydantic output schemas (Step 09)
    observability  — Langfuse + OpenInference instrumentation (Step 11)
    embedder       — Local sentence-transformers embedding (Step 13)
    retrieval      — Qdrant-backed session embedding/query (Step 13)
    summarizer     — Session-transcript summarizer via SDK Haiku (Step 13)
    memory         — LlamaIndex memory blocks (Step 14)
    eval           — Ragas eval harness (Step 15)
    templates      — Jinja2 prompt templates (Step 16)
    claude         — Thin Agent SDK wrapper that initializes observability (Step 11, R7)
    workers        — Claude Agent SDK subagent workers + fan-out coordinator (Step 10+, 18b)
    tracing        — Usage-time OTel session/tag binding for fan-out (Step 18b)

Submodules do not eagerly import their third-party dependencies at package-import
time. Install the optional extras with `pip install -e .[llm]` before importing
the submodules that need them.

`fanout_review` / `FanoutResult` are re-exported here lazily (PEP 562) for
convenience — accessing them triggers the underlying import, so the
no-eager-import contract above still holds.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = ["FanoutResult", "fanout_review"]


if TYPE_CHECKING:
    from hooks.lib.llm.workers.fanout import FanoutResult, fanout_review


def __getattr__(name: str) -> Any:
    if name in ("fanout_review", "FanoutResult"):
        from hooks.lib.llm.workers import fanout
        return getattr(fanout, name)
    raise AttributeError(
        f"module 'hooks.lib.llm' has no attribute {name!r}")
