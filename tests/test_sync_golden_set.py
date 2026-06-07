#!/usr/bin/env python3
"""Tests for scripts/sync_golden_set_to_langfuse.py.

Mirrors golden_set/cases/*.json into a Langfuse dataset so in-UI
experiments and judge calibration can run against it. Item ids are the
case ids — Langfuse upserts dataset items by id, so re-runs are
idempotent server-side (unlike prompts; verified in the v3 SDK docs).

Stub-client tests (hermetic). Loud-failure contract: this is a script,
not library code — missing diff files must hard-fail, not skip.

Run with: python3 tests/test_sync_golden_set.py
"""

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "sync_golden_set_to_langfuse.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("sync_golden", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _StubClient:
    def __init__(self, existing_datasets: set[str] | None = None):
        self.datasets_created: list[str] = []
        self.items: list[dict] = []
        self._existing = existing_datasets or set()

    def get_dataset(self, name):
        if name not in self._existing:
            raise LookupError(f"dataset not found: {name}")
        return {"name": name}

    def create_dataset(self, *, name, description=None, metadata=None):
        self.datasets_created.append(name)
        self._existing.add(name)

    def create_dataset_item(self, *, dataset_name, id, input,
                            expected_output, metadata):
        self.items.append({
            "dataset_name": dataset_name, "id": id, "input": input,
            "expected_output": expected_output, "metadata": metadata,
        })

    def flush(self):
        pass


class TestRunner:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.failed_tests: list[tuple[str, str]] = []

    def test(self, name: str, condition: bool, msg: str = "") -> None:
        if condition:
            self.passed += 1
            print(f"  PASS  {name}")
        else:
            self.failed += 1
            self.failed_tests.append((name, msg))
            print(f"  FAIL  {name}  {msg}")

    def summary(self) -> int:
        total = self.passed + self.failed
        print(f"\n{self.passed}/{total} passed")
        for name, msg in self.failed_tests:
            print(f"  FAILED: {name}  {msg}")
        return 1 if self.failed else 0


def _make_golden_dir(cases: list[dict], diffs: dict[str, str]) -> Path:
    root = Path(tempfile.mkdtemp())
    (root / "cases").mkdir()
    (root / "diffs").mkdir()
    for rel, content in diffs.items():
        (root / rel).write_text(content)
    for c in cases:
        (root / "cases" / f"{c['id']}.json").write_text(json.dumps(c))
    return root


def main() -> int:
    r = TestRunner()
    mod = _load_module()

    case = {
        "id": "001-sql-injection",
        "agent": "code-reviewer",
        "diff_path": "diffs/001.diff",
        "reference_findings": [{"file": "api/users.py", "line": 12,
                                "category": "security",
                                "severity": "CRITICAL"}],
        "reference_goal": "Detect SQL injection.",
    }

    print("sync: case maps to dataset item with inlined diff")
    root = _make_golden_dir([case], {"diffs/001.diff": "--- a/api/users.py\n"})
    client = _StubClient()
    n = mod.sync_golden_set(root, client, dataset_name="golden-set")
    r.test("dataset created", client.datasets_created == ["golden-set"],
           f"{client.datasets_created}")
    r.test("one item synced", n == 1 and len(client.items) == 1,
           f"n={n}, items={len(client.items)}")
    item = client.items[0]
    r.test("item id is case id", item["id"] == "001-sql-injection", item["id"])
    r.test("diff content inlined",
           item["input"]["diff"] == "--- a/api/users.py\n",
           repr(item["input"].get("diff")))
    r.test("agent in input", item["input"]["agent"] == "code-reviewer",
           repr(item["input"]))
    r.test("expected_output carries findings + goal",
           item["expected_output"]["reference_findings"] == case["reference_findings"]
           and item["expected_output"]["reference_goal"] == case["reference_goal"],
           repr(item["expected_output"]))
    r.test("metadata keeps diff_path",
           item["metadata"]["diff_path"] == "diffs/001.diff",
           repr(item["metadata"]))

    print("sync: existing dataset is not re-created")
    root = _make_golden_dir([case], {"diffs/001.diff": "X\n"})
    client = _StubClient(existing_datasets={"golden-set"})
    mod.sync_golden_set(root, client, dataset_name="golden-set")
    r.test("no duplicate dataset", client.datasets_created == [],
           f"{client.datasets_created}")

    print("sync: missing diff file hard-fails (loud, not fail-open)")
    bad = dict(case, diff_path="diffs/missing.diff")
    root = _make_golden_dir([bad], {})
    client = _StubClient()
    try:
        mod.sync_golden_set(root, client, dataset_name="golden-set")
        r.test("missing diff raises", False, "no exception raised")
    except (SystemExit, FileNotFoundError):
        r.test("missing diff raises", True)
    r.test("nothing synced on failure", client.items == [],
           f"items={client.items}")

    print("cli: --dry-run lists cases without creds")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--dry-run"],
        capture_output=True, text=True, check=False,
        env={"PATH": "/usr/bin:/bin"},
    )
    r.test("dry-run exits 0", proc.returncode == 0, proc.stderr[:200])
    r.test("dry-run lists golden cases", "001-sql-injection" in proc.stdout,
           proc.stdout[:200])

    return r.summary()


if __name__ == "__main__":
    sys.exit(main())
