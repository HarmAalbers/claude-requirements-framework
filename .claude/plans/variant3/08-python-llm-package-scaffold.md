# Step 08 — Python LLM package scaffold

## Goal

Create the `hooks/lib/llm/` package and install dependencies. No behavior change — purely structural. After this step, subsequent steps can import from `hooks.lib.llm.*`.

## Why first

Every subsequent step needs imports from this package. Doing the setup up front avoids relitigating module structure mid-stream.

## Files touched

- `hooks/lib/llm/__init__.py` (new)
- `hooks/lib/llm/schemas.py` (placeholder; populated in Step 09)
- `hooks/lib/llm/workers/__init__.py` (new)
- `hooks/lib/llm/observability.py` (placeholder; populated in Step 11)
- `hooks/lib/llm/retrieval.py` (placeholder; populated in Step 13)
- `hooks/lib/llm/memory.py` (placeholder; populated in Step 14)
- `hooks/lib/llm/eval.py` (placeholder; populated in Step 15)
- `hooks/lib/llm/templates.py` (placeholder; populated in Step 16)
- `pyproject.toml` or `requirements.txt` — add deps

## Dependencies to add

```text
# Core LLM platform
pydantic-ai>=1.0
instructor>=2.0
anthropic>=0.40
jinja2>=3.1

# Observability
langfuse>=3.0
openinference-instrumentation-claude-agent-sdk>=0.1
opentelemetry-sdk>=1.27
opentelemetry-exporter-otlp-proto-http>=1.27

# Retrieval / memory
qdrant-client>=1.12
llama-index-core>=0.12
llama-index-embeddings-openai>=0.3   # OR llama-index-embeddings-huggingface for local
llama-index-vector-stores-qdrant>=0.4

# Evaluation
ragas>=0.2

# Token counting
tiktoken>=0.8
```

> Pin only major versions; let lockfile pin patch versions.

## Validation source

- [PydanticAI install docs](https://pydantic.dev/docs/ai/getting-started/) — `pip install pydantic-ai`
- [Instructor PyPI](https://pypi.org/project/instructor/) — `pip install instructor`
- [Langfuse + Claude Agent SDK](https://langfuse.com/integrations/frameworks/claude-agent-sdk) — exact command: `pip install langfuse claude-agent-sdk openinference-instrumentation-claude-agent-sdk`

## Implementation

1. Create the directories above with empty `__init__.py` files.
2. Add the dependency block to `pyproject.toml` (or `requirements.txt` if that's the convention here — check `hooks/`).
3. Run `pip install -e .[llm]` locally (use an optional dependency group so users who don't want V3 don't pay the install cost).
4. Add `from hooks.lib.llm import *` smoke test in `hooks/test_requirements.py` to verify the package imports.

## Example (verifying the install)

```python
# tests/test_llm_imports.py
def test_v3_stack_imports():
    import pydantic_ai
    import instructor
    import anthropic
    from langfuse.decorators import observe
    from openinference.instrumentation.claude_agent_sdk import ClaudeAgentSDKInstrumentor
    from qdrant_client import QdrantClient
    from llama_index.core.memory import Memory, VectorMemoryBlock
    import ragas
    import jinja2
    import tiktoken
```

## Acceptance

- [ ] `python -c "from hooks.lib.llm import *"` runs without error
- [ ] All listed packages are importable
- [ ] Existing tests still pass: `python3 hooks/test_requirements.py`
- [ ] No runtime behavior change in any session

## Rollback

```bash
git revert <commit>; pip uninstall -y pydantic-ai instructor langfuse \
  openinference-instrumentation-claude-agent-sdk qdrant-client \
  llama-index-core ragas tiktoken
```

## Effort

0.5 day

## Depends on

Steps 01–07 (simplification baseline).
