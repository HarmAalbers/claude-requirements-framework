"""LLM platform package for the requirements-framework V3 layer.

Submodules are populated by later V3 steps (see `.claude/plans/variant3/`):
    schemas        — Pydantic output schemas (Step 09)
    observability  — Langfuse + OpenInference instrumentation (Step 11)
    retrieval      — Qdrant-backed session embedding/query (Step 13)
    memory         — LlamaIndex memory blocks (Step 14)
    eval           — Ragas eval harness (Step 15)
    templates      — Jinja2 prompt templates (Step 16)
    claude         — Thin Agent SDK wrapper that initializes observability (Step 11, R7)
    workers        — Claude Agent SDK subagent workers (Step 10+)

Submodules do not eagerly import their third-party dependencies at package-import
time. Install the optional extras with `pip install -e .[llm]` before importing
the submodules that need them.
"""
