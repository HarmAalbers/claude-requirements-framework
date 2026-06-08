#!/usr/bin/env python3
"""Tests for the R5 trace enrichment in hooks/_langfuse_hook.py (VENDOR-PATCH (e)).

Follows the framework's TestRunner convention. Run with:
    python3 tests/test_langfuse_hook_enrichment.py

The vendored hook imports langfuse v4 (and opentelemetry) at module top and
``sys.exit``s if that import fails — which it would under the repo's global
langfuse v3 / SDK-absent environment. So we stub ``langfuse`` and
``opentelemetry`` in ``sys.modules`` BEFORE loading the module, then exercise
the PURE enrichment helpers (``_enrichment``/``_trace_attrs``). These are the
SDK-free wiring contract: emit_turn calls ``propagate_attributes(**_trace_attrs(...))``
verbatim, so asserting _trace_attrs's output asserts what reaches the trace.
No network, no real langfuse, no skip-on-absent.
"""

import importlib.util
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK_PATH = REPO_ROOT / "hooks" / "_langfuse_hook.py"


class TestRunner:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.failed_tests = []

    def test(self, name, condition, msg=""):
        if condition:
            self.passed += 1
            print(f"  ✓ {name}")
        else:
            self.failed += 1
            self.failed_tests.append((name, msg))
            print(f"  ✗ {name}: {msg}")

    def summary(self):
        print(f"\n{self.passed} passed, {self.failed} failed")
        return 1 if self.failed else 0


def _load_hook_module():
    """Load _langfuse_hook.py with langfuse/opentelemetry stubbed in sys.modules."""
    captured_propagate_kwargs = []

    fake_langfuse = types.ModuleType("langfuse")

    class _FakeLangfuse:  # only needed as a type-hint target
        pass

    def _fake_propagate_attributes(**kwargs):
        captured_propagate_kwargs.append(kwargs)
        # The hook uses it as a context manager; return a trivial one.
        from contextlib import nullcontext
        return nullcontext()

    fake_langfuse.Langfuse = _FakeLangfuse
    fake_langfuse.propagate_attributes = _fake_propagate_attributes

    fake_otel = types.ModuleType("opentelemetry")
    fake_otel_trace = types.ModuleType("opentelemetry.trace")
    fake_otel.trace = fake_otel_trace

    sys.modules["langfuse"] = fake_langfuse
    sys.modules["opentelemetry"] = fake_otel
    sys.modules["opentelemetry.trace"] = fake_otel_trace

    spec = importlib.util.spec_from_file_location("_langfuse_hook_under_test", HOOK_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._captured_propagate_kwargs = captured_propagate_kwargs
    return mod


MOD = _load_hook_module()


def _user_row(**over):
    row = {
        "type": "user",
        "version": "2.1.168",
        "cwd": "/Users/harm/Tools/claude-requirements-framework",
        "gitBranch": "feat/r5-observability-hardening",
        "message": {"role": "user", "content": "hi"},
    }
    row.update(over)
    return row


def test_enrichment_extracts_version_and_tags(runner):
    print("\ntest_enrichment_extracts_version_and_tags")
    enr = MOD._enrichment(_user_row(), os_user="harm")
    runner.test("version is the CC version", enr.get("version") == "2.1.168", f"got={enr.get('version')!r}")
    runner.test(
        "project tag from cwd basename",
        "project:claude-requirements-framework" in enr.get("tags", []),
        f"got={enr.get('tags')}",
    )
    runner.test(
        "branch tag from gitBranch",
        "branch:feat/r5-observability-hardening" in enr.get("tags", []),
        f"got={enr.get('tags')}",
    )
    runner.test("user_id is the os_user proxy", enr.get("user_id") == "harm", f"got={enr.get('user_id')!r}")


def test_enrichment_omits_user_id_without_os_user(runner):
    print("\ntest_enrichment_omits_user_id_without_os_user")
    enr = MOD._enrichment(_user_row(), os_user=None)
    runner.test("no user_id key when os_user falsy", "user_id" not in enr, f"got={enr}")
    enr2 = MOD._enrichment(_user_row(), os_user="")
    runner.test("no user_id key when os_user empty", "user_id" not in enr2, f"got={enr2}")


def test_enrichment_graceful_on_missing_fields(runner):
    print("\ntest_enrichment_graceful_on_missing_fields")
    enr = MOD._enrichment({}, os_user="harm")
    runner.test("no version key when absent", "version" not in enr, f"got={enr}")
    runner.test("no tags key when no cwd/branch", "tags" not in enr, f"got={enr}")
    runner.test("user_id still set", enr.get("user_id") == "harm", f"got={enr}")
    # non-dict input must not crash
    enr_none = MOD._enrichment(None, os_user="harm")
    runner.test("non-dict user_msg tolerated", enr_none.get("user_id") == "harm", f"got={enr_none}")
    # partial: cwd but no branch
    enr_p = MOD._enrichment({"cwd": "/tmp/foo"}, os_user=None)
    runner.test("project tag only when branch absent", enr_p.get("tags") == ["project:foo"], f"got={enr_p}")


def test_trace_attrs_is_the_propagate_contract(runner):
    print("\ntest_trace_attrs_is_the_propagate_contract")
    attrs = MOD._trace_attrs("sess-1", 7, _user_row(), os_user="harm")
    runner.test("session_id passed through", attrs.get("session_id") == "sess-1", f"got={attrs.get('session_id')!r}")
    runner.test(
        "trace_name carries turn number",
        attrs.get("trace_name") == "Claude Code - Turn 7",
        f"got={attrs.get('trace_name')!r}",
    )
    tags = attrs.get("tags", [])
    runner.test("base claude-code tag preserved first", tags[:1] == ["claude-code"], f"got={tags}")
    runner.test("project tag appended", "project:claude-requirements-framework" in tags, f"got={tags}")
    runner.test("branch tag appended", "branch:feat/r5-observability-hardening" in tags, f"got={tags}")
    runner.test("user_id reaches propagate kwargs", attrs.get("user_id") == "harm", f"got={attrs.get('user_id')!r}")
    runner.test("version reaches propagate kwargs", attrs.get("version") == "2.1.168", f"got={attrs.get('version')!r}")


def test_trace_attrs_keys_are_supported_propagate_kwargs(runner):
    print("\ntest_trace_attrs_keys_are_supported_propagate_kwargs")
    # Guard against the fail-hard crash: every key must be a real
    # propagate_attributes parameter (confirmed against langfuse v4 signature).
    supported = {"user_id", "session_id", "metadata", "version", "tags", "trace_name", "as_baggage"}
    attrs = MOD._trace_attrs("s", 1, _user_row(), os_user="harm")
    unknown = set(attrs) - supported
    runner.test("only supported propagate_attributes kwargs used", not unknown, f"unknown keys: {unknown}")
    # minimal row (no enrichment) still yields only base keys
    attrs_min = MOD._trace_attrs("s", 1, {}, os_user=None)
    runner.test(
        "minimal attrs are session_id/trace_name/tags",
        set(attrs_min) == {"session_id", "trace_name", "tags"},
        f"got={set(attrs_min)}",
    )
    runner.test("minimal tags is just claude-code", attrs_min.get("tags") == ["claude-code"], f"got={attrs_min.get('tags')}")


def main():
    runner = TestRunner()
    print("Testing hooks/_langfuse_hook.py R5 enrichment (VENDOR-PATCH (e))")
    test_enrichment_extracts_version_and_tags(runner)
    test_enrichment_omits_user_id_without_os_user(runner)
    test_enrichment_graceful_on_missing_fields(runner)
    test_trace_attrs_is_the_propagate_contract(runner)
    test_trace_attrs_keys_are_supported_propagate_kwargs(runner)
    return runner.summary()


if __name__ == "__main__":
    sys.exit(main())
