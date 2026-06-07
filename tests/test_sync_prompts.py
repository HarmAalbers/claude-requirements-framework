#!/usr/bin/env python3
"""Tests for scripts/sync_prompts_to_langfuse.py (idempotency + --check).

Empirical finding (2026-06-07): Langfuse does NOT dedup identical content
server-side — `create_prompt()` with unchanged text mints a new version.
The script therefore compares client-side against the registry's current
labeled version and skips identical files. `--check` reports drift and
exits 1 without writing (pre-commit / CI gate; drift fails loudly).

Sync/check logic is tested against a stub client (hermetic, no network),
following the test_eval.py stub pattern. The dry-run CLI path is exercised
as a subprocess (no creds required).

Run with: python3 tests/test_sync_prompts.py
"""

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "sync_prompts_to_langfuse.py"

try:
    import jinja2  # noqa: F401  (parity with sibling script tests)
except ImportError:
    print("SKIP: jinja2 not installed. `pip install -e '.[llm]'` to enable.")
    sys.exit(0)


def _load_module():
    spec = importlib.util.spec_from_file_location("sync_prompts", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _StubPrompt:
    def __init__(self, prompt: str, version: int = 1):
        self.prompt = prompt
        self.version = version


class _StubClient:
    """Records create_prompt calls; serves canned get_prompt responses."""

    def __init__(self, registry: dict[str, str]):
        self._registry = dict(registry)
        self.created: list[str] = []
        self._next_version = 2

    def get_prompt(self, name, label=None, **kwargs):
        if name not in self._registry:
            raise LookupError(f"prompt not found: {name}")
        return _StubPrompt(self._registry[name])

    def create_prompt(self, *, name, type, prompt, labels):
        self.created.append(name)
        self._registry[name] = prompt
        v = self._next_version
        self._next_version += 1
        return _StubPrompt(prompt, version=v)

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


def _make_prompt_dir(files: dict[str, str]) -> Path:
    d = Path(tempfile.mkdtemp())
    for name, content in files.items():
        (d / f"{name}.md.j2").write_text(content)
    return d


def main() -> int:
    r = TestRunner()
    mod = _load_module()

    # --- sync mode -------------------------------------------------------
    print("sync: identical content is skipped (client-side compare)")
    d = _make_prompt_dir({"alpha": "SAME\n", "beta": "NEW\n"})
    client = _StubClient({"alpha": "SAME\n", "beta": "OLD\n"})
    changed = mod.sync_prompts(
        sorted(d.glob("*.md.j2")), client, label="production", check=False
    )
    r.test("unchanged prompt not re-created", client.created == ["beta"],
           f"created={client.created}")
    r.test("sync returns only changed names", changed == ["beta"],
           f"changed={changed}")

    print("sync: missing-in-registry prompt is created")
    d = _make_prompt_dir({"gamma": "BRAND NEW\n"})
    client = _StubClient({})
    changed = mod.sync_prompts(
        sorted(d.glob("*.md.j2")), client, label="production", check=False
    )
    r.test("missing prompt created", client.created == ["gamma"],
           f"created={client.created}")

    # --- check mode ------------------------------------------------------
    print("check: drift detected, nothing written")
    d = _make_prompt_dir({"alpha": "SAME\n", "beta": "NEW\n"})
    client = _StubClient({"alpha": "SAME\n", "beta": "OLD\n"})
    drifted = mod.sync_prompts(
        sorted(d.glob("*.md.j2")), client, label="production", check=True
    )
    r.test("check reports drifted prompt", drifted == ["beta"],
           f"drifted={drifted}")
    r.test("check writes nothing", client.created == [],
           f"created={client.created}")

    print("check: clean registry reports no drift")
    d = _make_prompt_dir({"alpha": "SAME\n"})
    client = _StubClient({"alpha": "SAME\n"})
    drifted = mod.sync_prompts(
        sorted(d.glob("*.md.j2")), client, label="production", check=True
    )
    r.test("clean check is empty", drifted == [], f"drifted={drifted}")

    print("check: missing prompt counts as drift")
    d = _make_prompt_dir({"gamma": "X\n"})
    client = _StubClient({})
    drifted = mod.sync_prompts(
        sorted(d.glob("*.md.j2")), client, label="production", check=True
    )
    r.test("missing prompt is drift", drifted == ["gamma"],
           f"drifted={drifted}")

    # --- trailing newline is significant (keep_trailing_newline lore) ----
    print("compare: trailing-newline difference is drift")
    d = _make_prompt_dir({"alpha": "SAME\n"})
    client = _StubClient({"alpha": "SAME"})
    drifted = mod.sync_prompts(
        sorted(d.glob("*.md.j2")), client, label="production", check=True
    )
    r.test("newline-only diff detected", drifted == ["alpha"],
           f"drifted={drifted}")

    # --- flatten: playground-compatible rendering --------------------------
    import jinja2 as j2

    def _env(partials: dict[str, str]):
        e = j2.Environment(
            loader=j2.DictLoader(partials),
            autoescape=False,
            keep_trailing_newline=True,
            undefined=j2.StrictUndefined,
        )
        e.filters["repr"] = repr
        return e

    print("flatten: simple vars stay as mustache placeholders")
    env = _env({})
    out = mod.flatten_template("Review this:\n{{ diff }}\n", env)
    r.test("simple var preserved", out == "Review this:\n{{diff}}\n", repr(out))

    print("flatten: includes are resolved inline")
    env = _env({"partials/safety.j2": "SAFETY RULES"})
    out = mod.flatten_template(
        "{% include 'partials/safety.j2' %}\n{{ diff }}\n", env
    )
    r.test("include folded in", out == "SAFETY RULES\n{{diff}}\n", repr(out))

    print("flatten: repr filter pre-applied around placeholder")
    env = _env({})
    out = mod.flatten_template("scope={{ scope | repr }}\n", env)
    r.test("repr quoting survives", out == "scope='{{scope}}'\n", repr(out))

    print("flatten: if-defined section kept with placeholder")
    env = _env({})
    out = mod.flatten_template(
        "{% if project_conventions is defined and project_conventions %}"
        "CONV: {{ project_conventions }}{% endif %}\n",
        env,
    )
    r.test("conditional section kept",
           out == "CONV: {{project_conventions}}\n", repr(out))

    print("flatten: phases loop collapses to sentinel line")
    env = _env({})
    out = mod.flatten_template(
        "{% for p in phases %}  {{ p.name }} — "
        "{{ p.get('description') or p.get('skill') or '' }}\n{% endfor %}",
        env,
    )
    r.test("loop renders one placeholder row",
           "{{phases}}" in out and out.count("\n") == 1, repr(out))

    print("flatten: trailing newline preserved (keep_trailing_newline)")
    env = _env({})
    out = mod.flatten_template("X\n", env)
    r.test("trailing newline kept", out == "X\n", repr(out))

    # --- playground items: naming + label ---------------------------------
    print("playground: suffixed names, separate label")
    d = _make_prompt_dir({"alpha": "{{ diff }}\n"})
    client = _StubClient({})
    changed = mod.sync_playground(
        sorted(d.glob("*.md.j2")), client, env=_env({}), check=False
    )
    r.test("playground name suffixed", client.created == ["alpha-playground"],
           f"created={client.created}")
    r.test("playground content flattened",
           client._registry.get("alpha-playground") == "{{diff}}\n",
           repr(client._registry.get("alpha-playground")))

    # --- CLI: dry-run needs no creds --------------------------------------
    print("cli: --dry-run lists without creds")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--dry-run"],
        capture_output=True, text=True, check=False,
        env={"PATH": "/usr/bin:/bin"},
    )
    r.test("dry-run exits 0", proc.returncode == 0, proc.stderr[:200])
    r.test("dry-run lists prompts", "code-reviewer" in proc.stdout,
           proc.stdout[:200])

    return r.summary()


if __name__ == "__main__":
    sys.exit(main())
