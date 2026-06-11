#!/usr/bin/env python3
"""Tests for the strict-preflight PreToolUse gate in hooks/check-requirements.py.

Task 4 wires a fail-closed, fail-SAFE strict gate into the PreToolUse hook. These
are DIRECT unit tests of the two extracted helpers:

  - ``strict_preflight_block(config, tool_name, tool_input, project_dir)`` returns a
    deny-payload dict when strict mode must block the call, else ``None`` (inert,
    compliant, escape-allowed, or — fail-SAFE — any internal exception).
  - ``_strict_denial_payload(verdict, project_dir)`` builds the PreToolUse deny
    payload listing each compliance failure + fix and the escape/kill-switch footer.

The hook file has a hyphen in its name, so it is loaded via importlib from its path
(its top-level body is import-safe: only defs + an ``if __name__ == "__main__"`` guard).

Run: python3 tests/test_check_requirements_strict.py
"""

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
# hooks/lib first so the hook module's bare imports (requirements, config, ...) resolve.
sys.path.insert(0, str(REPO_ROOT / "hooks" / "lib"))
sys.path.insert(0, str(REPO_ROOT / "hooks"))
sys.path.insert(0, str(REPO_ROOT))

import preflight  # noqa: E402


def _load_hook_module():
    """Load hooks/check-requirements.py (hyphenated → importlib by path)."""
    path = REPO_ROOT / "hooks" / "check-requirements.py"
    spec = importlib.util.spec_from_file_location("check_requirements", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CR = _load_hook_module()


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


class FakeConfig:
    """Minimal stand-in exposing only what the strict gate consults."""

    def __init__(self, strict: bool, raises: bool = False):
        self._strict = strict
        self._raises = raises

    def strict_preflight_enabled(self) -> bool:
        if self._raises:
            raise RuntimeError("boom: simulated config failure")
        return self._strict


def _noncompliant_project() -> str:
    """A temp project with NO .claude/requirements.local.yaml → fails `no_config`,
    deterministically non-compliant regardless of env/PATH."""
    return tempfile.mkdtemp()


def _compliant_env() -> dict:
    return {
        "TRACE_TO_LANGFUSE": "true",
        "LANGFUSE_PUBLIC_KEY": "pk-x",
        "LANGFUSE_SECRET_KEY": "sk-x",
        "LANGFUSE_HOST": "http://localhost:3000",
        "CC_LANGFUSE_MAX_CHARS": "5000",
    }


def _deny_reason(payload) -> str:
    return payload["hookSpecificOutput"]["permissionDecisionReason"]


def _is_deny(payload) -> bool:
    hso = payload.get("hookSpecificOutput", {})
    return (
        hso.get("hookEventName") == "PreToolUse"
        and hso.get("permissionDecision") == "deny"
    )


def main() -> int:
    r = TestRunner()

    print("strict_preflight_block — blocking / allow paths")

    # --- block arbitrary edit when strict + non-compliant ---
    tmp = _noncompliant_project()
    out = CR.strict_preflight_block(
        FakeConfig(strict=True), "Write", {"file_path": f"{tmp}/src/app.py"}, tmp
    )
    r.test(
        "block_when_strict_noncompliant_arbitrary_edit: returns deny dict",
        out is not None and _is_deny(out),
        f"got {out!r}",
    )
    r.test(
        "block_when_strict_noncompliant_arbitrary_edit: reason mentions a fix",
        out is not None and "`/req-init`" in _deny_reason(out),
        f"reason={_deny_reason(out) if out else None!r}",
    )

    # --- allow editing the config itself (escape hatch) ---
    out = CR.strict_preflight_block(
        FakeConfig(strict=True),
        "Write",
        {"file_path": f"{tmp}/.claude/requirements.local.yaml"},
        tmp,
    )
    r.test(
        "allow_config_edit_when_noncompliant: returns None",
        out is None,
        f"got {out!r}",
    )

    # --- allow `req init` bash (escape hatch) ---
    out = CR.strict_preflight_block(
        FakeConfig(strict=True), "Bash", {"command": "req init"}, tmp
    )
    r.test(
        "allow_req_init_bash: returns None",
        out is None,
        f"got {out!r}",
    )

    # --- inert when strict disabled ---
    out = CR.strict_preflight_block(
        FakeConfig(strict=False), "Write", {"file_path": f"{tmp}/src/app.py"}, tmp
    )
    r.test(
        "inert_when_strict_disabled: returns None",
        out is None,
        f"got {out!r}",
    )

    # --- compliant project → None ---
    compliant_dir = tempfile.mkdtemp()
    claude_dir = Path(compliant_dir) / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    (claude_dir / "requirements.local.yaml").write_text(
        "requirements:\n  commit_plan:\n    enabled: true\n"
    )
    # Provide a FAKE `uv` on PATH so the uv check resolves deterministically in
    # any environment (CI runners have no real uv) — shutil.which reads PATH at
    # call time, so prepending a dir holding an executable `uv` stub makes the
    # project fully compliant → the gate must stay inert (None).
    fake_bin = Path(compliant_dir) / "bin"
    fake_bin.mkdir(parents=True, exist_ok=True)
    fake_uv = fake_bin / "uv"
    fake_uv.write_text("#!/bin/sh\nexit 0\n")
    fake_uv.chmod(0o755)
    saved_environ = dict(os.environ)
    try:
        # Drop any deprecated Layer-2 keys + add the 5 Layer-1 keys, and prepend
        # the fake-uv dir to PATH so the uv check passes regardless of host.
        for k in preflight.DEPRECATED_L2_KEYS:
            os.environ.pop(k, None)
        os.environ.update(_compliant_env())
        os.environ["PATH"] = f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}"
        out = CR.strict_preflight_block(
            FakeConfig(strict=True), "Write", {"file_path": f"{compliant_dir}/src/x.py"},
            compliant_dir,
        )
        r.test(
            "compliant_returns_none: returns None",
            out is None,
            f"got {out!r}",
        )
    finally:
        os.environ.clear()
        os.environ.update(saved_environ)

    # --- fail-safe: evaluator/config exception must NOT raise and NOT block ---
    raised = False
    try:
        out = CR.strict_preflight_block(
            FakeConfig(strict=True, raises=True),
            "Write",
            {"file_path": f"{tmp}/src/app.py"},
            tmp,
        )
    except Exception as e:  # noqa: BLE001
        raised = True
        out = e
    r.test(
        "fail_safe_on_evaluator_error: does not raise",
        not raised,
        f"raised {out!r}",
    )
    r.test(
        "fail_safe_on_evaluator_error: returns None (does not block)",
        out is None,
        f"got {out!r}",
    )

    print("\n_strict_denial_payload — shape + content")

    verdict = preflight.ComplianceResult(
        strict_active=True,
        compliant=False,
        failures=[
            ("no_config", "no .claude/requirements.local.yaml", "/req-init"),
            ("no_uv", "uv not on PATH", "install uv"),
        ],
    )
    payload = CR._strict_denial_payload(verdict, tmp)
    r.test(
        "denial_payload_shape: deny shape",
        _is_deny(payload),
        f"got {payload!r}",
    )
    reason = _deny_reason(payload)
    r.test(
        "denial_payload_shape: first fix present",
        "`/req-init`" in reason,
        f"reason={reason!r}",
    )
    r.test(
        "denial_payload_shape: second fix present",
        "`install uv`" in reason,
        f"reason={reason!r}",
    )
    r.test(
        "denial_payload_shape: kill-switch footer present",
        "RF_STRICT_OFF" in reason,
        f"reason={reason!r}",
    )

    return r.summary()


if __name__ == "__main__":
    sys.exit(main())
