#!/usr/bin/env python3
"""Tests for strict-preflight config accessor — RequirementsConfig + ConfigStateView.

`strict_preflight_enabled()` reads the top-level `strict_preflight` config key
(mirroring `is_enabled()` / the `enabled` key). It defaults to False (opt-in),
returns the configured boolean when set, and is exposed identically through the
ConfigStateView passthrough.

Run: python3 tests/test_preflight.py
"""

import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "hooks"))
sys.path.insert(0, str(REPO_ROOT / "hooks" / "lib"))

from config import ConfigStateView, RequirementsConfig
import preflight


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


def _config_with(strict_preflight=None) -> RequirementsConfig:
    """Build a RequirementsConfig over a temp project dir, then inject the
    top-level key directly so the test does not depend on YAML cascade plumbing."""
    tmpdir = tempfile.mkdtemp()
    config = RequirementsConfig(tmpdir)
    if strict_preflight is not None:
        config._config["strict_preflight"] = strict_preflight
    return config


# ---------------------------------------------------------------------------
# Task 2: pure compliance evaluator (hooks/lib/preflight.py)
# ---------------------------------------------------------------------------

def _compliant_env() -> dict:
    """All 5 Layer-1 keys non-empty, zero deprecated Layer-2 keys."""
    return {
        "TRACE_TO_LANGFUSE": "true",
        "LANGFUSE_PUBLIC_KEY": "pk-x",
        "LANGFUSE_SECRET_KEY": "sk-x",
        "LANGFUSE_HOST": "http://localhost:3000",
        "CC_LANGFUSE_MAX_CHARS": "5000",
    }


def _write_local_config(project_dir: str, body: str) -> None:
    claude_dir = Path(project_dir) / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    (claude_dir / "requirements.local.yaml").write_text(body)


def _baseline():
    """A fully compliant axis set: (project_dir, env, which_fn).

    Individual tests break exactly one axis. The project has a config with one
    enabled requirement; env is the compliant Layer-1 set; uv is on PATH.
    """
    project_dir = tempfile.mkdtemp()
    _write_local_config(
        project_dir,
        "requirements:\n  commit_plan:\n    enabled: true\n",
    )
    env = _compliant_env()
    which_fn = lambda name: "/usr/bin/uv"  # noqa: E731
    return project_dir, env, which_fn


def _codes(result) -> set:
    return {f[0] for f in result.failures}


def test_preflight(r: TestRunner) -> None:
    print("\npreflight.evaluate — short-circuits")

    # kill-switch wins even when every other axis is broken
    broken = tempfile.mkdtemp()  # no config
    ks = preflight.evaluate(
        broken,
        strict_enabled=True,
        env={"RF_STRICT_OFF": "TRUE"},
        which_fn=lambda n: None,
    )
    r.test(
        "killswitch short-circuits (inert + compliant)",
        ks.strict_active is False and ks.compliant is True and not ks.failures,
        f"got {ks!r}",
    )

    # opt-out sentinel makes the project inert
    optout_dir = tempfile.mkdtemp()
    (Path(optout_dir) / ".claude").mkdir(parents=True, exist_ok=True)
    (Path(optout_dir) / ".claude" / ".rf-optout").write_text("")
    oo = preflight.evaluate(
        optout_dir, strict_enabled=True, env={}, which_fn=lambda n: None
    )
    r.test(
        "optout short-circuits (inert)",
        oo.strict_active is False and oo.compliant is True,
        f"got {oo!r}",
    )

    # master switch off → inert
    proj, env, which = _baseline()
    inert = preflight.evaluate(proj, strict_enabled=False, env=env, which_fn=which)
    r.test(
        "strict disabled is inert",
        inert.strict_active is False and inert.compliant is True,
        f"got {inert!r}",
    )

    print("\npreflight.evaluate — compliant baseline")
    proj, env, which = _baseline()
    ok = preflight.evaluate(proj, strict_enabled=True, env=env, which_fn=which)
    r.test(
        "compliant when all checks pass",
        ok.strict_active is True and ok.compliant is True and not ok.failures,
        f"got {ok!r}",
    )

    print("\npreflight.evaluate — local-config failures")
    # missing config file
    no_cfg_dir = tempfile.mkdtemp()
    _, env, which = _baseline()
    missing = preflight.evaluate(
        no_cfg_dir, strict_enabled=True, env=env, which_fn=which
    )
    r.test(
        "missing config fails (no_config)",
        not missing.compliant and "no_config" in _codes(missing),
        f"got {_codes(missing)!r}",
    )

    # config with zero enabled requirements
    proj, env, which = _baseline()
    _write_local_config(proj, "requirements:\n  commit_plan:\n    enabled: false\n")
    empty = preflight.evaluate(proj, strict_enabled=True, env=env, which_fn=which)
    r.test(
        "empty config fails (empty_config)",
        not empty.compliant and "empty_config" in _codes(empty),
        f"got {_codes(empty)!r}",
    )

    proj, env, which = _baseline()
    _write_local_config(proj, "requirements: {}\n")
    empty2 = preflight.evaluate(proj, strict_enabled=True, env=env, which_fn=which)
    r.test(
        "empty requirements map fails (empty_config)",
        not empty2.compliant and "empty_config" in _codes(empty2),
        f"got {_codes(empty2)!r}",
    )

    # malformed YAML
    proj, env, which = _baseline()
    _write_local_config(proj, "requirements: [unterminated\n  : :\n")
    bad = preflight.evaluate(proj, strict_enabled=True, env=env, which_fn=which)
    r.test(
        "bad config fails (bad_config)",
        not bad.compliant and "bad_config" in _codes(bad),
        f"got {_codes(bad)!r}",
    )

    # non-dict top level → bad_config
    proj, env, which = _baseline()
    _write_local_config(proj, "- just\n- a\n- list\n")
    nondict = preflight.evaluate(proj, strict_enabled=True, env=env, which_fn=which)
    r.test(
        "non-dict top level fails (bad_config)",
        not nondict.compliant and "bad_config" in _codes(nondict),
        f"got {_codes(nondict)!r}",
    )

    print("\npreflight.evaluate — langfuse env failures")
    # deprecated Layer-2 key present
    proj, env, which = _baseline()
    stale_env = dict(env)
    stale_env["OTEL_EXPORTER_OTLP_ENDPOINT"] = "http://localhost:4318"
    stale = preflight.evaluate(proj, strict_enabled=True, env=stale_env, which_fn=which)
    r.test(
        "stale Layer-2 key fails (stale_layer2)",
        not stale.compliant and "stale_layer2" in _codes(stale),
        f"got {_codes(stale)!r}",
    )

    # missing Layer-1 keys
    proj, env, which = _baseline()
    partial = {"TRACE_TO_LANGFUSE": "true"}  # missing the other 4
    missing_keys = preflight.evaluate(
        proj, strict_enabled=True, env=partial, which_fn=which
    )
    r.test(
        "missing Layer-1 keys fail (langfuse_env)",
        not missing_keys.compliant and "langfuse_env" in _codes(missing_keys),
        f"got {_codes(missing_keys)!r}",
    )

    # empty-string Layer-1 key is treated as missing
    proj, env, which = _baseline()
    empty_val = dict(env)
    empty_val["LANGFUSE_SECRET_KEY"] = ""
    empty_key = preflight.evaluate(
        proj, strict_enabled=True, env=empty_val, which_fn=which
    )
    r.test(
        "empty-string Layer-1 key fails (langfuse_env)",
        not empty_key.compliant and "langfuse_env" in _codes(empty_key),
        f"got {_codes(empty_key)!r}",
    )

    print("\npreflight.evaluate — uv check")
    proj, env, which = _baseline()
    no_uv = preflight.evaluate(
        proj, strict_enabled=True, env=env, which_fn=lambda n: None
    )
    r.test(
        "missing uv fails (no_uv)",
        not no_uv.compliant and "no_uv" in _codes(no_uv),
        f"got {_codes(no_uv)!r}",
    )

    print("\npreflight — every failure carries a fix command")
    # union of all failures: break every axis at once
    all_broken_dir = tempfile.mkdtemp()  # no config
    all_broken = preflight.evaluate(
        all_broken_dir,
        strict_enabled=True,
        env={"OTEL_TRACES_EXPORTER": "otlp"},  # stale + missing L1
        which_fn=lambda n: None,  # no uv
    )
    r.test(
        "every failure tuple has a non-empty fix_cmd",
        all_broken.failures
        and all(
            isinstance(f[2], str) and f[2].strip() for f in all_broken.failures
        ),
        f"got {all_broken.failures!r}",
    )
    r.test(
        "every failure tuple has a non-empty human_msg",
        all(isinstance(f[1], str) and f[1].strip() for f in all_broken.failures),
        f"got {all_broken.failures!r}",
    )


# ---------------------------------------------------------------------------
# Task 3: escape allowlist (hooks/lib/preflight.py)
# ---------------------------------------------------------------------------

def test_escape_allowed(r: TestRunner) -> None:
    print("\npreflight.is_escape_allowed — edit/write to config + optout")
    tmp = tempfile.mkdtemp()

    cfg_input = {"file_path": f"{tmp}/.claude/requirements.local.yaml"}
    r.test(
        "Write to requirements.local.yaml allowed",
        preflight.is_escape_allowed("Write", cfg_input, tmp) is True,
        "expected True",
    )
    r.test(
        "Edit to requirements.local.yaml allowed",
        preflight.is_escape_allowed("Edit", cfg_input, tmp) is True,
        "expected True",
    )
    r.test(
        "MultiEdit to requirements.local.yaml allowed",
        preflight.is_escape_allowed("MultiEdit", cfg_input, tmp) is True,
        "expected True",
    )

    optout_input = {"file_path": f"{tmp}/.claude/.rf-optout"}
    r.test(
        "Write to .rf-optout allowed",
        preflight.is_escape_allowed("Write", optout_input, tmp) is True,
        "expected True",
    )

    print("\npreflight.is_escape_allowed — arbitrary / traversal NOT allowed")
    r.test(
        "Write to arbitrary source file NOT allowed",
        preflight.is_escape_allowed("Write", {"file_path": f"{tmp}/src/app.py"}, tmp)
        is False,
        "expected False",
    )
    r.test(
        "Write to /etc/passwd (outside project) NOT allowed",
        preflight.is_escape_allowed("Write", {"file_path": "/etc/passwd"}, tmp)
        is False,
        "expected False",
    )
    r.test(
        "Write via ../ traversal outside project NOT allowed",
        preflight.is_escape_allowed(
            "Write",
            {"file_path": f"{tmp}/../other/.claude/requirements.local.yaml"},
            tmp,
        )
        is False,
        "expected False",
    )

    print("\npreflight.is_escape_allowed — Bash req init/optout")
    for cmd, expect in (
        ("req init", True),
        ("req optout", True),
        ("python3 hooks/requirements-cli.py optout", True),
        ("python3 hooks/requirements-cli.py init", True),
        ("/req-init", True),
        ("/req-optout", True),
        ("rm -rf x", False),
        ("git commit -m x", False),
        ("requirements", False),
    ):
        r.test(
            f"Bash {cmd!r} -> {expect}",
            preflight.is_escape_allowed("Bash", {"command": cmd}, tmp) is expect,
            f"expected {expect}",
        )

    print("\npreflight.is_escape_allowed — defensive / unknown")
    r.test(
        "tool_input=None NOT allowed (no raise)",
        preflight.is_escape_allowed("Write", None, tmp) is False,
        "expected False",
    )
    r.test(
        "tool_input={} NOT allowed (no raise)",
        preflight.is_escape_allowed("Write", {}, tmp) is False,
        "expected False",
    )
    r.test(
        "Bash tool_input=None NOT allowed (no raise)",
        preflight.is_escape_allowed("Bash", None, tmp) is False,
        "expected False",
    )
    r.test(
        "unknown tool_name (Read) NOT allowed",
        preflight.is_escape_allowed("Read", cfg_input, tmp) is False,
        "expected False",
    )


def main() -> int:
    r = TestRunner()
    print("strict_preflight_enabled — RequirementsConfig")

    cfg_default = _config_with()
    r.test(
        "defaults to False when key absent",
        cfg_default.strict_preflight_enabled() is False,
        f"got {cfg_default.strict_preflight_enabled()!r}",
    )

    cfg_true = _config_with(True)
    r.test(
        "returns True when configured True",
        cfg_true.strict_preflight_enabled() is True,
        f"got {cfg_true.strict_preflight_enabled()!r}",
    )

    cfg_false = _config_with(False)
    r.test(
        "returns False when configured False",
        cfg_false.strict_preflight_enabled() is False,
        f"got {cfg_false.strict_preflight_enabled()!r}",
    )

    print("\nstrict_preflight_enabled — ConfigStateView passthrough")

    view_default = ConfigStateView(_config_with())
    r.test(
        "view defaults to False",
        view_default.strict_preflight_enabled() is False,
        f"got {view_default.strict_preflight_enabled()!r}",
    )

    view_true = ConfigStateView(_config_with(True))
    r.test(
        "view returns True when configured True",
        view_true.strict_preflight_enabled() is True,
        f"got {view_true.strict_preflight_enabled()!r}",
    )

    test_preflight(r)
    test_escape_allowed(r)

    return r.summary()


if __name__ == "__main__":
    sys.exit(main())
