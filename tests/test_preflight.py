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

    return r.summary()


if __name__ == "__main__":
    sys.exit(main())
