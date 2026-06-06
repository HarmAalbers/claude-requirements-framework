#!/usr/bin/env python3
"""Tests for hooks/lib/llm/prompts.py — Step 12.

Verifies the two-tier loader: Langfuse first when configured, file
fallback otherwise. No real Langfuse calls — the client is mocked.

Run: python3 tests/test_prompts.py
"""

import os
import sys
from contextlib import contextmanager
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
            for name, msg in self.failed_tests:
                print(f"  {name}: {msg}")
            return 1
        return 0


@contextmanager
def fresh_prompts_module():
    """Reload prompts module so the lazy-singleton client state is clean."""
    import hooks.lib.llm as _parent
    sys.modules.pop("hooks.lib.llm.prompts", None)
    if hasattr(_parent, "prompts"):
        delattr(_parent, "prompts")
    from hooks.lib.llm import prompts  # noqa: F401  reload-on-purpose
    try:
        yield prompts
    finally:
        sys.modules.pop("hooks.lib.llm.prompts", None)
        if hasattr(_parent, "prompts"):
            delattr(_parent, "prompts")


def test_file_fallback_when_no_langfuse_env(runner: TestRunner):
    print("\ntest_file_fallback_when_no_langfuse_env")
    env_without = {k: v for k, v in os.environ.items()
                   if not k.startswith("LANGFUSE_")}
    with patch.dict(os.environ, env_without, clear=True):
        with fresh_prompts_module() as prompts:
            text = prompts.load_prompt(
                "code-reviewer",
                diff="--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new",
                scope="unstaged",
            )
            runner.test(
                "returns non-empty string",
                isinstance(text, str) and len(text) > 0,
                f"got: {type(text).__name__} len={len(text) if isinstance(text, str) else 0}",
            )
            runner.test(
                "rendered output contains the diff text",
                "+new" in text,
                "code-reviewer prompt must render the diff variable",
            )
            runner.test(
                "rendered output contains scope repr",
                "'unstaged'" in text,
                "scope should be repr'd with single quotes",
            )


def test_file_fallback_for_aggregator(runner: TestRunner):
    print("\ntest_file_fallback_for_aggregator")
    env_without = {k: v for k, v in os.environ.items()
                   if not k.startswith("LANGFUSE_")}
    with patch.dict(os.environ, env_without, clear=True):
        with fresh_prompts_module() as prompts:
            text = prompts.load_prompt(
                "review-aggregator",
                reports_json='[{"agent": "code-reviewer", "findings": []}]',
            )
            runner.test(
                "rendered output contains the reports_json content",
                '"agent": "code-reviewer"' in text,
                "aggregator prompt must render the reports_json variable",
            )


def test_missing_prompt_file_raises(runner: TestRunner):
    print("\ntest_missing_prompt_file_raises")
    env_without = {k: v for k, v in os.environ.items()
                   if not k.startswith("LANGFUSE_")}
    with patch.dict(os.environ, env_without, clear=True):
        with fresh_prompts_module() as prompts:
            raised = False
            try:
                prompts.load_prompt("does-not-exist-xyz")
            except FileNotFoundError:
                raised = True
            runner.test(
                "raises FileNotFoundError for unknown name",
                raised,
                "expected FileNotFoundError when no Langfuse and no file",
            )


def test_langfuse_path_when_client_available(runner: TestRunner):
    print("\ntest_langfuse_path_when_client_available")
    env = {
        "LANGFUSE_PUBLIC_KEY": "pk-test",
        "LANGFUSE_SECRET_KEY": "sk-test",
        "LANGFUSE_HOST": "http://localhost:3000",
    }
    with patch.dict(os.environ, env, clear=False):
        with fresh_prompts_module() as prompts:
            mock_client = SimpleNamespace(
                get_prompt=lambda name, label="production": SimpleNamespace(
                    prompt=f"<langfuse:{name}:{label}>"
                )
            )
            with patch.object(prompts, "_get_langfuse_client",
                              return_value=mock_client):
                text = prompts.load_prompt("code-reviewer")
                runner.test(
                    "returns Langfuse prompt content",
                    text == "<langfuse:code-reviewer:production>",
                    f"got: {text!r}",
                )


def test_langfuse_exception_falls_back_to_file(runner: TestRunner):
    print("\ntest_langfuse_exception_falls_back_to_file")
    env = {
        "LANGFUSE_PUBLIC_KEY": "pk-test",
        "LANGFUSE_SECRET_KEY": "sk-test",
        "LANGFUSE_HOST": "http://localhost:3000",
    }

    def boom(*_a, **_kw):
        raise RuntimeError("langfuse unreachable")

    with patch.dict(os.environ, env, clear=False):
        with fresh_prompts_module() as prompts:
            mock_client = SimpleNamespace(get_prompt=boom)
            with patch.object(prompts, "_get_langfuse_client",
                              return_value=mock_client):
                text = prompts.load_prompt(
                    "code-reviewer",
                    diff="dummy diff text",
                    scope="unstaged",
                )
                runner.test(
                    "falls back to file on Langfuse exception",
                    "dummy diff text" in text,
                    "expected file content rendered with the diff var",
                )


def test_label_is_forwarded_to_langfuse(runner: TestRunner):
    print("\ntest_label_is_forwarded_to_langfuse")
    env = {
        "LANGFUSE_PUBLIC_KEY": "pk-test",
        "LANGFUSE_SECRET_KEY": "sk-test",
        "LANGFUSE_HOST": "http://localhost:3000",
    }
    with patch.dict(os.environ, env, clear=False):
        with fresh_prompts_module() as prompts:
            captured: dict[str, object] = {}

            def fake_get_prompt(name, label="production"):
                captured["name"] = name
                captured["label"] = label
                return SimpleNamespace(prompt="ok")

            mock_client = SimpleNamespace(get_prompt=fake_get_prompt)
            with patch.object(prompts, "_get_langfuse_client",
                              return_value=mock_client):
                prompts.load_prompt("code-reviewer", label="staging")
            runner.test(
                "name forwarded",
                captured.get("name") == "code-reviewer",
                f"name={captured.get('name')!r}",
            )
            runner.test(
                "label forwarded",
                captured.get("label") == "staging",
                f"label={captured.get('label')!r}",
            )


def test_langfuse_disabled_when_keys_missing(runner: TestRunner):
    print("\ntest_langfuse_disabled_when_keys_missing")
    env_without = {k: v for k, v in os.environ.items()
                   if not k.startswith("LANGFUSE_")}
    with patch.dict(os.environ, env_without, clear=True):
        with fresh_prompts_module() as prompts:
            client = prompts._get_langfuse_client()
            runner.test(
                "client is None when env vars unset",
                client is None,
                f"expected None, got {client!r}",
            )


def test_langfuse_disabled_when_import_fails(runner: TestRunner):
    print("\ntest_langfuse_disabled_when_import_fails")
    env = {
        "LANGFUSE_PUBLIC_KEY": "pk-test",
        "LANGFUSE_SECRET_KEY": "sk-test",
    }
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) \
        else __builtins__.__import__

    def fail_langfuse(name, *args, **kwargs):
        if name == "langfuse" or name.startswith("langfuse."):
            raise ImportError(f"mocked: no module named {name!r}")
        return real_import(name, *args, **kwargs)

    with patch.dict(os.environ, env, clear=False):
        with fresh_prompts_module() as prompts:
            # Force a fresh attempt by clearing the cached client state.
            prompts._client = None
            prompts._client_attempted = False
            with patch("builtins.__import__", side_effect=fail_langfuse):
                client = prompts._get_langfuse_client()
            runner.test(
                "client is None when langfuse import fails",
                client is None,
                f"expected None, got {client!r}",
            )


def test_known_prompt_files_present(runner: TestRunner):
    print("\ntest_known_prompt_files_present")
    root = REPO_ROOT / "hooks" / "lib" / "llm" / "prompts"
    for name in ("code-reviewer", "review-aggregator", "req-supervisor"):
        path = root / f"{name}.md.j2"
        runner.test(
            f"{name}.md.j2 exists",
            path.exists() and path.stat().st_size > 0,
            f"missing or empty: {path}",
        )


def main() -> int:
    runner = TestRunner()
    test_known_prompt_files_present(runner)
    test_file_fallback_when_no_langfuse_env(runner)
    test_file_fallback_for_aggregator(runner)
    test_missing_prompt_file_raises(runner)
    test_langfuse_path_when_client_available(runner)
    test_langfuse_exception_falls_back_to_file(runner)
    test_label_is_forwarded_to_langfuse(runner)
    test_langfuse_disabled_when_keys_missing(runner)
    test_langfuse_disabled_when_import_fails(runner)
    return runner.summary()


if __name__ == "__main__":
    sys.exit(main())
