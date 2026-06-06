#!/usr/bin/env python3
"""Tests for hooks.lib.llm.supervisor — Step 18.

Mocks `query` and `ResultMessage` at the `hooks.lib.llm.claude` wrapper so no
real SDK calls happen and no real budget ledger is touched. The supervisor
imports those symbols lazily inside `route()` (deferred so the module stays
import-safe without the optional SDK), so the patch targets the wrapper's
import site rather than the supervisor module — the lazy-import analogue of
the `patch.object(worker, ...)` pattern in tests/test_code_reviewer_worker.py.

Run: python3 tests/test_supervisor.py
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Optional heavy dep: the supervisor patches the claude-wrapper (hooks.lib.llm.claude),
# which eager-imports the Claude Agent SDK. CI installs only the light llm extras
# (pyyaml/pydantic/jinja2), so skip cleanly instead of crashing when the SDK is
# absent — mirrors the optional-dep skip pattern in hooks/test_requirements.py.
try:
    import claude_agent_sdk  # noqa: F401
except ModuleNotFoundError as e:
    print(f"   ⊘ skipped: optional dep absent ({e.name})")
    sys.exit(0)


class TestRunner:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.failed_tests: list[tuple[str, str]] = []

    def test(self, name: str, condition: bool, msg: str = ""):
        if condition:
            self.passed += 1
            print(f"  ✓ {name}")
        else:
            self.failed += 1
            self.failed_tests.append((name, msg))
            print(f"  ✗ {name}: {msg}")

    def summary(self) -> int:
        total = self.passed + self.failed
        print(f"\n{self.passed}/{total} passed")
        if self.failed:
            print("\nFailures:")
            for name, m in self.failed_tests:
                print(f"  {name}: {m}")
            return 1
        return 0


def _import_supervisor_module():
    import importlib
    import hooks.lib.llm.supervisor as mod
    return importlib.reload(mod)


VALID_HANDOFF = {
    "target": "deep-review",
    "rationale": "Implementation complete; pre_pr_review unsatisfied.",
}

# Explicit routing vocabulary. The target is now a config-driven phase NAME, and
# route() clamps any out-of-vocabulary target back to the input phase. Passing
# `phases` explicitly keeps the parsed target ("deep-review") in the active
# vocabulary so it survives un-clamped, and makes the test deterministic
# regardless of whether `config` is importable in the bare-script context (its
# fail-open default is an empty phase set, which would clamp everything).
PHASES = [
    {"name": "review", "description": "cross-validated team review"},
    {"name": "deep-review", "description": "deep multi-agent review"},
    {"name": "ship", "description": "branch is shippable"},
]


def test_route_returns_handoff_result(runner):
    print("\n[success path]")
    sup = _import_supervisor_module()
    result_msg = SimpleNamespace(
        subtype="success", structured_output=VALID_HANDOFF)
    captured = {}

    async def fake_query(*args, prompt=None, options=None, **kw):
        captured["prompt"] = prompt
        captured["options"] = options
        yield result_msg

    async def run():
        with patch("hooks.lib.llm.claude.query", fake_query):
            with patch("hooks.lib.llm.claude.ResultMessage", SimpleNamespace):
                return await sup.route(
                    phase="review",
                    unsatisfied=["pre_pr_review", "codex_reviewer"],
                    phases=PHASES,
                )

    result = asyncio.run(run())
    runner.test(
        "returns HandoffResult with the parsed target",
        result.target == "deep-review",
        f"target={result.target!r}",
    )
    runner.test(
        "rationale round-trips",
        "pre_pr_review" in result.rationale,
        f"rationale={result.rationale!r}",
    )
    prompt = captured["prompt"] or ""
    runner.test(
        "phase renders into prompt",
        "review" in prompt,
        "prompt missing phase",
    )
    runner.test(
        "unsatisfied items render into prompt",
        "pre_pr_review" in prompt and "codex_reviewer" in prompt,
        "prompt missing unsatisfied items",
    )


def test_empty_unsatisfied_renders_as_none(runner):
    print("\n[empty unsatisfied -> '(none)']")
    sup = _import_supervisor_module()
    result_msg = SimpleNamespace(
        subtype="success",
        structured_output={"target": "ship", "rationale": "All clear."},
    )
    captured = {}

    async def fake_query(*args, prompt=None, options=None, **kw):
        captured["prompt"] = prompt
        yield result_msg

    async def run():
        with patch("hooks.lib.llm.claude.query", fake_query):
            with patch("hooks.lib.llm.claude.ResultMessage", SimpleNamespace):
                return await sup.route(phase="ship", unsatisfied=[])

    asyncio.run(run())
    runner.test(
        "empty list renders as '(none)' marker",
        "(none)" in (captured["prompt"] or ""),
        "expected '(none)' literal in rendered prompt",
    )


def test_route_passes_output_format_and_no_tools(runner):
    print("\n[options: output_format + no tools]")
    sup = _import_supervisor_module()
    result_msg = SimpleNamespace(
        subtype="success", structured_output=VALID_HANDOFF)
    captured = {}

    async def fake_query(*args, prompt=None, options=None, **kw):
        captured["options"] = options
        yield result_msg

    async def run():
        with patch("hooks.lib.llm.claude.query", fake_query):
            with patch("hooks.lib.llm.claude.ResultMessage", SimpleNamespace):
                return await sup.route(phase="review", unsatisfied=[])

    asyncio.run(run())
    opts = captured["options"]
    runner.test(
        "allowed_tools is empty list",
        getattr(opts, "allowed_tools", None) == [],
        f"got {getattr(opts, 'allowed_tools', '<missing>')!r}",
    )
    of = getattr(opts, "output_format", None)
    runner.test(
        "output_format is json_schema for HandoffResult",
        isinstance(of, dict)
        and of.get("type") == "json_schema"
        and "target" in of["schema"].get("properties", {}),
        f"got {of!r}",
    )


def test_route_labels_options_with_agent_name(runner):
    print("\n[agent label for budget]")
    sup = _import_supervisor_module()
    result_msg = SimpleNamespace(
        subtype="success", structured_output=VALID_HANDOFF)
    captured = {}

    async def fake_query(*args, prompt=None, options=None, **kw):
        captured["options"] = options
        yield result_msg

    async def run():
        with patch("hooks.lib.llm.claude.query", fake_query):
            with patch("hooks.lib.llm.claude.ResultMessage", SimpleNamespace):
                return await sup.route(phase="review", unsatisfied=[])

    asyncio.run(run())
    runner.test(
        "options.agent == 'req-supervisor' for budget label",
        getattr(captured["options"], "agent", None) == "req-supervisor",
        f"got {getattr(captured['options'], 'agent', '<missing>')!r}",
    )


def test_route_raises_on_error_subtype(runner):
    print("\n[error_max_structured_output_retries]")
    sup = _import_supervisor_module()
    err_msg = SimpleNamespace(
        subtype="error_max_structured_output_retries",
        structured_output=None,
    )

    async def fake_query(*args, prompt=None, options=None, **kw):
        yield err_msg

    async def run():
        with patch("hooks.lib.llm.claude.query", fake_query):
            with patch("hooks.lib.llm.claude.ResultMessage", SimpleNamespace):
                return await sup.route(phase="review", unsatisfied=[])

    raised = False
    try:
        asyncio.run(run())
    except RuntimeError as exc:
        raised = "subtype" in str(exc)
    runner.test(
        "RuntimeError mentions the SDK subtype",
        raised,
        "expected RuntimeError with subtype info",
    )


def test_route_raises_when_no_result_message(runner):
    print("\n[no terminal ResultMessage]")
    sup = _import_supervisor_module()

    class OtherMsg:
        pass

    async def fake_query(*args, prompt=None, options=None, **kw):
        yield OtherMsg()
        # No ResultMessage ever yielded

    async def run():
        with patch("hooks.lib.llm.claude.query", fake_query):
            with patch("hooks.lib.llm.claude.ResultMessage", SimpleNamespace):
                return await sup.route(phase="review", unsatisfied=[])

    raised = False
    try:
        asyncio.run(run())
    except RuntimeError as exc:
        raised = "no ResultMessage" in str(exc)
    runner.test(
        "RuntimeError when stream ends without ResultMessage",
        raised,
        "expected 'no ResultMessage' RuntimeError",
    )


def test_route_consumes_pre_result_messages(runner):
    print("\n[non-result messages ignored before result]")
    sup = _import_supervisor_module()
    result_msg = SimpleNamespace(
        subtype="success", structured_output=VALID_HANDOFF)

    class StreamMsg:
        pass

    async def fake_query(*args, prompt=None, options=None, **kw):
        for m in [StreamMsg(), StreamMsg(), result_msg]:
            yield m

    async def run():
        with patch("hooks.lib.llm.claude.query", fake_query):
            with patch("hooks.lib.llm.claude.ResultMessage", SimpleNamespace):
                return await sup.route(
                    phase="review", unsatisfied=[], phases=PHASES)

    result = asyncio.run(run())
    runner.test(
        "route consumes pre-result messages and still returns",
        result.target == "deep-review",
        f"target={result.target!r}",
    )


def main() -> int:
    runner = TestRunner()
    test_route_returns_handoff_result(runner)
    test_empty_unsatisfied_renders_as_none(runner)
    test_route_passes_output_format_and_no_tools(runner)
    test_route_labels_options_with_agent_name(runner)
    test_route_raises_on_error_subtype(runner)
    test_route_raises_when_no_result_message(runner)
    test_route_consumes_pre_result_messages(runner)
    return runner.summary()


if __name__ == "__main__":
    sys.exit(main())
