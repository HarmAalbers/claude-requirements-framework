#!/usr/bin/env python3
"""Tests for hooks.lib.llm.summarizer (Step 13).

Mocks `query` and `ResultMessage` inside the summarizer module so no real
SDK calls happen and the budget ledger stays untouched. Mirrors the pattern
from tests/test_code_reviewer_worker.py.

Critical invariant: summarizer is FAIL-OPEN. Every error path must return ""
without raising. The SessionEnd hook depends on this — surfacing an exception
would risk breaking session teardown.

Run: python3 tests/test_summarizer.py
"""

from __future__ import annotations

import asyncio
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


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


def _import_summarizer():
    import hooks.lib.llm.summarizer as mod
    return importlib.reload(mod)


# ---------- success path ----------


def test_returns_text_on_success(runner: TestRunner) -> None:
    print("\n[success path]")
    mod = _import_summarizer()
    result_msg = SimpleNamespace(
        subtype="success",
        structured_output={"text": "Refactored auth middleware to address legal compliance."},
    )

    async def fake_query(*args, prompt=None, options=None, **kw):
        yield result_msg

    async def run():
        with patch.object(mod, "query", fake_query):
            with patch.object(mod, "ResultMessage", SimpleNamespace):
                return await mod.summarize_session("some transcript content here")

    out = asyncio.run(run())
    runner.test(
        "returns the structured_output text",
        out == "Refactored auth middleware to address legal compliance.",
        f"got={out!r}",
    )


def test_prompt_includes_transcript(runner: TestRunner) -> None:
    print("\n[prompt shape]")
    mod = _import_summarizer()
    captured: dict = {}

    async def fake_query(*args, prompt=None, options=None, **kw):
        captured["prompt"] = prompt
        captured["options"] = options
        yield SimpleNamespace(
            subtype="success", structured_output={"text": "ok"}
        )

    async def run():
        with patch.object(mod, "query", fake_query):
            with patch.object(mod, "ResultMessage", SimpleNamespace):
                return await mod.summarize_session("UNIQUE_TRANSCRIPT_MARKER")

    asyncio.run(run())
    runner.test(
        "transcript text appears in the prompt",
        "UNIQUE_TRANSCRIPT_MARKER" in (captured["prompt"] or ""),
    )
    runner.test(
        "prompt mentions 300-char limit",
        "300" in (captured["prompt"] or ""),
    )


def test_options_use_haiku_and_no_tools(runner: TestRunner) -> None:
    print("\n[options shape]")
    mod = _import_summarizer()
    captured: dict = {}

    async def fake_query(*args, prompt=None, options=None, **kw):
        captured["options"] = options
        yield SimpleNamespace(
            subtype="success", structured_output={"text": "ok"}
        )

    async def run():
        with patch.object(mod, "query", fake_query):
            with patch.object(mod, "ResultMessage", SimpleNamespace):
                return await mod.summarize_session("x")

    asyncio.run(run())
    opts = captured["options"]
    runner.test(
        "model is claude-haiku-4-5",
        getattr(opts, "model", None) == "claude-haiku-4-5",
        f"model={getattr(opts, 'model', None)!r}",
    )
    runner.test(
        "allowed_tools is empty list",
        getattr(opts, "allowed_tools", None) == [],
    )
    runner.test(
        "agent label set for budget tracker",
        getattr(opts, "agent", None) == "session-summarizer",
    )
    runner.test(
        "output_format is json_schema",
        getattr(opts, "output_format", {}).get("type") == "json_schema",
    )


# ---------- fail-open paths ----------


def test_empty_transcript_returns_empty_string(runner: TestRunner) -> None:
    print("\n[fail-open: empty input]")
    mod = _import_summarizer()

    async def fake_query(*args, **kw):  # should NOT be called
        runner.test("query NOT called for empty input", False,
                    "summarize_session called the SDK with empty transcript")
        yield None

    async def run():
        with patch.object(mod, "query", fake_query):
            return await mod.summarize_session("")

    out = asyncio.run(run())
    runner.test("empty transcript returns ''", out == "")


def test_error_subtype_returns_empty(runner: TestRunner) -> None:
    print("\n[fail-open: SDK error subtype]")
    mod = _import_summarizer()

    async def fake_query(*args, **kw):
        yield SimpleNamespace(
            subtype="error_max_structured_output_retries",
            structured_output=None,
        )

    async def run():
        with patch.object(mod, "query", fake_query):
            with patch.object(mod, "ResultMessage", SimpleNamespace):
                return await mod.summarize_session("anything")

    out = asyncio.run(run())
    runner.test("error subtype returns ''", out == "")


def test_no_result_message_returns_empty(runner: TestRunner) -> None:
    print("\n[fail-open: no ResultMessage observed]")
    mod = _import_summarizer()

    async def fake_query(*args, **kw):
        # Stream of non-ResultMessage items only (something the SDK might
        # yield as intermediate progress).
        for _ in range(3):
            yield object()

    async def run():
        with patch.object(mod, "query", fake_query):
            with patch.object(mod, "ResultMessage", SimpleNamespace):
                return await mod.summarize_session("anything")

    out = asyncio.run(run())
    runner.test("no ResultMessage returns ''", out == "")


def test_query_raises_returns_empty(runner: TestRunner) -> None:
    print("\n[fail-open: query raises]")
    mod = _import_summarizer()

    async def fake_query(*args, **kw):
        raise RuntimeError("simulated SDK transport failure")
        yield  # unreachable, makes this an async generator

    async def run():
        with patch.object(mod, "query", fake_query):
            with patch.object(mod, "ResultMessage", SimpleNamespace):
                return await mod.summarize_session("anything")

    out = asyncio.run(run())
    runner.test("query exception returns '' (no raise)", out == "")


def test_validation_failure_returns_empty(runner: TestRunner) -> None:
    print("\n[fail-open: schema validation fails]")
    mod = _import_summarizer()

    async def fake_query(*args, **kw):
        # Wrong shape: 'text' missing.
        yield SimpleNamespace(
            subtype="success", structured_output={"wrong_key": "no"}
        )

    async def run():
        with patch.object(mod, "query", fake_query):
            with patch.object(mod, "ResultMessage", SimpleNamespace):
                return await mod.summarize_session("anything")

    out = asyncio.run(run())
    runner.test("validation failure returns ''", out == "")


def main() -> int:
    print("Running summarizer tests...")
    r = TestRunner()
    test_returns_text_on_success(r)
    test_prompt_includes_transcript(r)
    test_options_use_haiku_and_no_tools(r)
    test_empty_transcript_returns_empty_string(r)
    test_error_subtype_returns_empty(r)
    test_no_result_message_returns_empty(r)
    test_query_raises_returns_empty(r)
    test_validation_failure_returns_empty(r)
    return r.summary()


if __name__ == "__main__":
    sys.exit(main())
