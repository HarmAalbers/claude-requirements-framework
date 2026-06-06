#!/usr/bin/env python3
"""Test the budget-recording wrapper around `claude.query` — Step 17a.

We monkey-patch `_sdk_query` and `_budget_record` inside hooks.lib.llm.claude
so the test never imports the real SDK and never writes to a real ledger.

Run with: python3 tests/test_claude_wrapper.py
"""

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Optional heavy dep: the V3 worker / claude-wrapper modules this suite exercises
# eager-import the Claude Agent SDK. CI installs only the light llm extras
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
            for name, msg in self.failed_tests:
                print(f"  {name}: {msg}")
            return 1
        return 0


def _import_claude_module():
    """Import the wrapper module fresh so monkey-patches apply cleanly."""
    import importlib
    import hooks.lib.llm.claude as mod
    return importlib.reload(mod)


def _make_async_iter(items):
    async def _gen(*_args, **_kwargs):
        for item in items:
            yield item
    return _gen


def test_wrapper_yields_all_messages(runner):
    print("\n[wrapper passthrough]")
    claude = _import_claude_module()
    # Build fake messages — only the ResultMessage subclass triggers record()
    fake_result = SimpleNamespace(
        total_cost_usd=0.01, usage={"input_tokens": 100, "output_tokens": 50},
        duration_ms=1000, session_id="s1", is_error=False, model_usage=None,
    )
    # Make the ResultMessage isinstance check pass by patching the type guard
    fake_messages = ["msg-1", "msg-2", fake_result]

    async def runit():
        recorded = []
        with patch.object(claude, "_sdk_query",
                          _make_async_iter(fake_messages)):
            with patch.object(claude, "ResultMessage", SimpleNamespace):
                with patch.object(claude, "_budget_record",
                                  lambda *a, **kw: recorded.append((a, kw))):
                    collected = []
                    async for m in claude.query(prompt="test", options=None):
                        collected.append(m)
        return collected, recorded

    collected, recorded = asyncio.run(runit())
    runner.test("yields 3 messages", len(collected) == 3,
                f"got {len(collected)}")
    runner.test("recorded only ResultMessage", len(recorded) == 1,
                f"got {len(recorded)} recordings")
    runner.test("recording passes the result through",
                recorded[0][0][0] is fake_result if recorded else False)


def test_wrapper_swallows_record_errors(runner):
    print("\n[fail-open]")
    claude = _import_claude_module()
    fake_result = SimpleNamespace(
        total_cost_usd=0.05, usage={"input_tokens": 10, "output_tokens": 5},
        duration_ms=2, session_id="s2", is_error=False, model_usage=None,
    )
    fake_messages = [fake_result]

    def boom(*_a, **_kw):
        raise RuntimeError("simulated budget failure")

    async def runit():
        with patch.object(claude, "_sdk_query",
                          _make_async_iter(fake_messages)):
            with patch.object(claude, "ResultMessage", SimpleNamespace):
                with patch.object(claude, "_budget_record", boom):
                    collected = []
                    async for m in claude.query(prompt="x", options=None):
                        collected.append(m)
        return collected

    try:
        collected = asyncio.run(runit())
        runner.test("iteration continues despite recorder exception",
                    len(collected) == 1)
    except RuntimeError as e:
        runner.test("iteration continues despite recorder exception",
                    False, f"raised: {e}")


def test_agent_label_from_options(runner):
    print("\n[agent label extraction]")
    claude = _import_claude_module()
    # Forward-compat: an explicit `agent` attribute wins
    runner.test("explicit agent attr",
                claude._agent_label(SimpleNamespace(agent="reviewer")) ==
                "reviewer")
    runner.test("model fallback",
                claude._agent_label(SimpleNamespace(model="sonnet")) ==
                "sonnet")
    runner.test("none when neither", claude._agent_label(
                SimpleNamespace()) is None)
    runner.test("none for None options", claude._agent_label(None) is None)


def test_agent_label_passed_to_record(runner):
    print("\n[agent label end-to-end]")
    claude = _import_claude_module()
    fake_result = SimpleNamespace(
        total_cost_usd=0.05, usage={}, duration_ms=1, session_id="s",
        is_error=False, model_usage=None,
    )
    options = SimpleNamespace(agent="code-reviewer")

    async def runit():
        captured = {}
        with patch.object(claude, "_sdk_query",
                          _make_async_iter([fake_result])):
            with patch.object(claude, "ResultMessage", SimpleNamespace):
                def fake_record(result, *, agent=None):
                    captured["agent"] = agent
                with patch.object(claude, "_budget_record", fake_record):
                    async for _ in claude.query(prompt="x", options=options):
                        pass
        return captured

    captured = asyncio.run(runit())
    runner.test("agent label propagates to record",
                captured.get("agent") == "code-reviewer",
                f"got {captured}")


if __name__ == "__main__":
    runner = TestRunner()
    test_wrapper_yields_all_messages(runner)
    test_wrapper_swallows_record_errors(runner)
    test_agent_label_from_options(runner)
    test_agent_label_passed_to_record(runner)
    sys.exit(runner.summary())
