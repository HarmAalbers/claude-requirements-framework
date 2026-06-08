#!/usr/bin/env python3
"""Test suite for scripts/setup_langfuse_tracing.py — R5 opt-in env-block generator.

Follows the framework's TestRunner convention (see tests/test_observability.py).
Run with: python3 tests/test_setup_langfuse_tracing.py

Dependency-free: invokes the script as a subprocess with a controlled env
(inherited LANGFUSE_* vars stripped), temp cwd dirs, and a fake `uv` on PATH
for --write cache-warming tests. Never touches the network or a real Langfuse.
"""

import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "setup_langfuse_tracing.py"
HOOK_PATH = REPO_ROOT / "hooks" / "_langfuse_hook.py"

PK = "pk-lf-x"
SK = "sk-lf-y"
HOST = "http://localhost:3000"

CRED_ENV = {
    "LANGFUSE_PUBLIC_KEY": PK,
    "LANGFUSE_SECRET_KEY": SK,
    "LANGFUSE_HOST": HOST,
}


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


def expected_env_block(pk=PK, sk=SK, host=HOST):
    """The 5-key Layer-1 env block the script must produce (host normalized).

    The 6 former Layer-2 OTEL keys are no longer emitted (ADR-019).
    """
    host = host.rstrip("/")
    return {
        "TRACE_TO_LANGFUSE": "true",
        "LANGFUSE_PUBLIC_KEY": pk,
        "LANGFUSE_SECRET_KEY": sk,
        "LANGFUSE_HOST": host,
        "CC_LANGFUSE_MAX_CHARS": "100000",
    }


# The 6 deprecated Layer-2 OTEL keys the script must drop + prune.
DEPRECATED_OTEL_KEYS = (
    "CLAUDE_CODE_ENABLE_TELEMETRY",
    "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA",
    "OTEL_TRACES_EXPORTER",
    "OTEL_EXPORTER_OTLP_PROTOCOL",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_HEADERS",
)


def make_fake_uv(dir_path: Path, exit_code=0, record_to=None, stderr_line=None):
    """Create an executable fake `uv` that records argv and exits as told.

    If stderr_line is given, the fake uv writes that line to its own stderr
    before exiting — used to verify the warm-failure hint path.
    """
    record = (
        f'printf \'%s\\n\' "$@" > "{record_to}/args.txt"' if record_to else ":"
    )
    stderr_write = (
        f'printf \'%s\\n\' "{stderr_line}" >&2' if stderr_line else ":"
    )
    body = f"#!/bin/sh\n{record}\n{stderr_write}\nexit {exit_code}\n"
    uv = dir_path / "uv"
    uv.write_text(body)
    uv.chmod(uv.stat().st_mode | stat.S_IEXEC)
    return uv


def parse_env_block(runner, result, label):
    """json-parse stdout and return its 'env' block, or None (recorded fail)."""
    try:
        return json.loads(result.stdout)["env"]
    except (json.JSONDecodeError, KeyError) as exc:
        runner.test(label, False, f"{exc}: stdout={result.stdout!r}")
        return None


def run_script(args=None, env_overrides=None, cwd=None, path_dirs=None):
    """Run the setup script as a subprocess with a controlled environment.

    Inherited LANGFUSE_* and CC_LANGFUSE_* vars are stripped so the host
    machine's real credentials can never leak into (or satisfy) a test.
    """
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("LANGFUSE_") and not k.startswith("CC_LANGFUSE_")
    }
    components = [str(d) for d in (path_dirs or [])] + ["/usr/bin", "/bin"]
    env["PATH"] = ":".join(components)
    env.update(env_overrides or {})
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + (args or []),
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        timeout=60,
    )


def test_loud_failure_names_all_missing(runner):
    print("\ntest_loud_failure_names_all_missing")
    with tempfile.TemporaryDirectory() as tmp:
        result = run_script(args=["--skip-ping"], cwd=tmp)
        runner.test(
            "exits nonzero with no creds anywhere",
            result.returncode != 0,
            f"rc={result.returncode} stderr={result.stderr!r}",
        )
        for var in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST"):
            runner.test(
                f"stderr names {var}",
                var in result.stderr,
                f"stderr={result.stderr!r}",
            )


def test_happy_path_print_mode(runner):
    print("\ntest_happy_path_print_mode")
    with tempfile.TemporaryDirectory() as tmp:
        result = run_script(
            args=["--skip-ping"], env_overrides=CRED_ENV, cwd=tmp
        )
        runner.test(
            "exits 0", result.returncode == 0, f"stderr={result.stderr!r}"
        )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            runner.test("stdout is valid JSON", False, f"{exc}: {result.stdout!r}")
            return
        runner.test("stdout is valid JSON", True)
        runner.test(
            "top-level shape is {'env': ...}",
            set(payload.keys()) == {"env"},
            f"keys={set(payload.keys())}",
        )
        expected = expected_env_block()
        block = payload.get("env", {})
        runner.test(
            "env block has exactly the 5 expected keys",
            set(block.keys()) == set(expected.keys()),
            f"got={sorted(block.keys())}",
        )
        runner.test(
            "no deprecated Layer-2 OTEL keys present",
            all(k not in block for k in DEPRECATED_OTEL_KEYS),
            f"got={sorted(block.keys())}",
        )
        for key, value in expected.items():
            runner.test(
                f"{key} correct",
                block.get(key) == value,
                f"got={block.get(key)!r} want={value!r}",
            )


def test_host_normalization(runner):
    print("\ntest_host_normalization")
    with tempfile.TemporaryDirectory() as tmp:
        # Host WITH trailing slash must be normalized (no trailing slash).
        env = dict(CRED_ENV, LANGFUSE_HOST="http://localhost:3000/")
        result = run_script(args=["--skip-ping"], env_overrides=env, cwd=tmp)
        runner.test(
            "exits 0 with trailing-slash host",
            result.returncode == 0,
            f"stderr={result.stderr!r}",
        )
        block = parse_env_block(runner, result, "stdout parses (trailing slash)")
        if block is None:
            return
        runner.test(
            "LANGFUSE_HOST normalized (no trailing slash)",
            block["LANGFUSE_HOST"] == "http://localhost:3000",
            f"got={block['LANGFUSE_HOST']!r}",
        )


def test_infra_env_sourcing(runner):
    print("\ntest_infra_env_sourcing")
    with tempfile.TemporaryDirectory() as tmp:
        infra = Path(tmp) / "infra"
        infra.mkdir()
        (infra / ".env").write_text(
            "# Langfuse credentials\n"
            "\n"
            f'LANGFUSE_PUBLIC_KEY="{PK}"\n'
            f"LANGFUSE_SECRET_KEY='{SK}'\n"
            f"export LANGFUSE_HOST={HOST}\n"
        )
        result = run_script(args=["--skip-ping"], cwd=tmp)
        runner.test(
            "exits 0 with creds only in infra/.env",
            result.returncode == 0,
            f"stderr={result.stderr!r}",
        )
        block = parse_env_block(runner, result, "stdout parses (infra/.env)")
        if block is None:
            return
        expected = expected_env_block()
        runner.test(
            "env block from infra/.env matches (quotes stripped)",
            block == expected,
            f"got={block}",
        )
        runner.test(
            "'export KEY=VALUE' lines are honored",
            block["LANGFUSE_HOST"] == HOST,
            f"got={block['LANGFUSE_HOST']!r}",
        )

        # Process env must take precedence over infra/.env per-key.
        env_pk = "pk-lf-from-env"
        result = run_script(
            args=["--skip-ping"],
            env_overrides={"LANGFUSE_PUBLIC_KEY": env_pk},
            cwd=tmp,
        )
        runner.test(
            "exits 0 with mixed env + file creds",
            result.returncode == 0,
            f"stderr={result.stderr!r}",
        )
        block = parse_env_block(runner, result, "stdout parses (precedence)")
        if block is None:
            return
        runner.test(
            "process env wins over infra/.env",
            block["LANGFUSE_PUBLIC_KEY"] == env_pk,
            f"got={block['LANGFUSE_PUBLIC_KEY']!r}",
        )
        runner.test(
            "non-overridden keys still come from infra/.env",
            block["LANGFUSE_SECRET_KEY"] == SK,
            f"got={block['LANGFUSE_SECRET_KEY']!r}",
        )


def test_write_merges_existing_settings(runner):
    print("\ntest_write_merges_existing_settings")
    with tempfile.TemporaryDirectory() as tmp, \
            tempfile.TemporaryDirectory() as uv_dir:
        make_fake_uv(Path(uv_dir))
        claude_dir = Path(tmp) / ".claude"
        claude_dir.mkdir()
        settings_path = claude_dir / "settings.local.json"
        settings_path.write_text(
            json.dumps(
                {"permissions": {"allow": ["X"]}, "env": {"EXISTING": "x"}},
                indent=2,
            )
            + "\n"
        )
        result = run_script(
            args=["--write", "--skip-ping", "--skip-model-sync"],
            env_overrides=CRED_ENV,
            cwd=tmp,
            path_dirs=[uv_dir],
        )
        runner.test(
            "exits 0", result.returncode == 0, f"stderr={result.stderr!r}"
        )
        raw = settings_path.read_text()
        runner.test(
            "file ends with trailing newline", raw.endswith("\n"), f"tail={raw[-5:]!r}"
        )
        try:
            settings = json.loads(raw)
        except json.JSONDecodeError as exc:
            runner.test("settings file is valid JSON", False, str(exc))
            return
        runner.test("settings file is valid JSON", True)
        runner.test(
            "permissions preserved",
            settings.get("permissions") == {"allow": ["X"]},
            f"got={settings.get('permissions')}",
        )
        env_block = settings.get("env", {})
        runner.test(
            "existing env key preserved",
            env_block.get("EXISTING") == "x",
            f"got={env_block.get('EXISTING')!r}",
        )
        expected = expected_env_block()
        for key, value in expected.items():
            runner.test(
                f"merged env has {key}",
                env_block.get(key) == value,
                f"got={env_block.get(key)!r} want={value!r}",
            )


def test_write_rejects_corrupt_settings(runner):
    print("\ntest_write_rejects_corrupt_settings")
    cases = [
        ("corrupt JSON", "{not json\n"),
        ("non-dict top level", "[]\n"),
    ]
    for label, content in cases:
        with tempfile.TemporaryDirectory() as tmp, \
                tempfile.TemporaryDirectory() as uv_dir:
            make_fake_uv(Path(uv_dir))
            claude_dir = Path(tmp) / ".claude"
            claude_dir.mkdir()
            settings_path = claude_dir / "settings.local.json"
            settings_path.write_text(content)
            result = run_script(
                args=["--write", "--skip-ping", "--skip-model-sync"],
                env_overrides=CRED_ENV,
                cwd=tmp,
                path_dirs=[uv_dir],
            )
            runner.test(
                f"exits nonzero on {label}",
                result.returncode != 0,
                f"rc={result.returncode} stderr={result.stderr!r}",
            )
            runner.test(
                f"stderr names the settings path ({label})",
                str(settings_path.resolve()) in result.stderr,
                f"stderr={result.stderr!r}",
            )
            runner.test(
                f"original file untouched ({label})",
                settings_path.read_text() == content,
                f"content={settings_path.read_text()!r}",
            )


def test_write_creates_settings(runner):
    print("\ntest_write_creates_settings")
    with tempfile.TemporaryDirectory() as tmp, \
            tempfile.TemporaryDirectory() as uv_dir:
        make_fake_uv(Path(uv_dir))
        result = run_script(
            args=["--write", "--skip-ping", "--skip-model-sync"],
            env_overrides=CRED_ENV,
            cwd=tmp,
            path_dirs=[uv_dir],
        )
        runner.test(
            "exits 0", result.returncode == 0, f"stderr={result.stderr!r}"
        )
        settings_path = Path(tmp) / ".claude" / "settings.local.json"
        runner.test(
            ".claude/settings.local.json created",
            settings_path.exists(),
            f"missing: {settings_path}",
        )
        if not settings_path.exists():
            return
        settings = json.loads(settings_path.read_text())
        runner.test(
            "file contains just the env block",
            settings == {"env": expected_env_block()},
            f"got={settings}",
        )


def test_write_no_secrets_on_stdout(runner):
    print("\ntest_write_no_secrets_on_stdout")
    with tempfile.TemporaryDirectory() as tmp, \
            tempfile.TemporaryDirectory() as uv_dir:
        make_fake_uv(Path(uv_dir))
        result = run_script(
            args=["--write", "--skip-ping", "--skip-model-sync"],
            env_overrides=CRED_ENV,
            cwd=tmp,
            path_dirs=[uv_dir],
        )
        runner.test(
            "exits 0", result.returncode == 0, f"stderr={result.stderr!r}"
        )
        runner.test(
            "secret key value NOT on stdout",
            SK not in result.stdout,
            f"stdout={result.stdout!r}",
        )
        runner.test(
            "confirmation mentions settings file path",
            ".claude/settings.local.json" in result.stdout,
            f"stdout={result.stdout!r}",
        )
        runner.test(
            "confirmation mentions var count (5)",
            "5" in result.stdout,
            f"stdout={result.stdout!r}",
        )


def test_write_warms_uv_cache(runner):
    print("\ntest_write_warms_uv_cache")
    with tempfile.TemporaryDirectory() as tmp, \
            tempfile.TemporaryDirectory() as uv_dir, \
            tempfile.TemporaryDirectory() as record_dir:
        make_fake_uv(Path(uv_dir), exit_code=0, record_to=record_dir)
        result = run_script(
            args=["--write", "--skip-ping", "--skip-model-sync"],
            env_overrides=CRED_ENV,
            cwd=tmp,
            path_dirs=[uv_dir],
        )
        runner.test(
            "exits 0", result.returncode == 0, f"stderr={result.stderr!r}"
        )
        args_file = Path(record_dir) / "args.txt"
        runner.test(
            "fake uv was invoked", args_file.exists(), "args.txt missing"
        )
        argv = args_file.read_text().splitlines() if args_file.exists() else []
        runner.test(
            "uv invoked with run --script",
            argv[:2] == ["run", "--script"],
            f"argv={argv}",
        )
        runner.test(
            "uv given the _langfuse_hook.py path",
            str(HOOK_PATH) in argv,
            f"argv={argv}",
        )
        runner.test(
            "stdout mentions cache warming",
            "warm" in result.stdout.lower(),
            f"stdout={result.stdout!r}",
        )


def test_write_warm_failure_not_fatal(runner):
    print("\ntest_write_warm_failure_not_fatal")
    with tempfile.TemporaryDirectory() as tmp, \
            tempfile.TemporaryDirectory() as uv_dir:
        make_fake_uv(Path(uv_dir), exit_code=1, stderr_line="uv stderr: mock resolution error")
        result = run_script(
            args=["--write", "--skip-ping", "--skip-model-sync"],
            env_overrides=CRED_ENV,
            cwd=tmp,
            path_dirs=[uv_dir],
        )
        runner.test(
            "script still exits 0 when uv warm fails",
            result.returncode == 0,
            f"rc={result.returncode} stderr={result.stderr!r}",
        )
        runner.test(
            "stderr carries a warning",
            "warn" in result.stderr.lower(),
            f"stderr={result.stderr!r}",
        )
        runner.test(
            "uv stderr hint included in warning",
            "uv stderr" in result.stderr,
            f"stderr={result.stderr!r}",
        )
        settings_path = Path(tmp) / ".claude" / "settings.local.json"
        runner.test(
            "settings file was still written",
            settings_path.exists(),
            f"missing: {settings_path}",
        )


def test_env_block_is_five_keys(runner):
    print("\ntest_env_block_is_five_keys")
    with tempfile.TemporaryDirectory() as tmp:
        result = run_script(
            args=["--skip-ping"], env_overrides=CRED_ENV, cwd=tmp
        )
        block = parse_env_block(runner, result, "stdout parses")
        if block is None:
            return
        runner.test(
            "exactly 5 keys",
            len(block) == 5 and set(block) == set(expected_env_block()),
            f"got={sorted(block)}",
        )
        for k in DEPRECATED_OTEL_KEYS:
            runner.test(f"{k} absent", k not in block, f"present in {sorted(block)}")


def test_write_prunes_deprecated_otel_keys(runner):
    print("\ntest_write_prunes_deprecated_otel_keys")
    with tempfile.TemporaryDirectory() as tmp, \
            tempfile.TemporaryDirectory() as uv_dir:
        make_fake_uv(Path(uv_dir))
        claude_dir = Path(tmp) / ".claude"
        claude_dir.mkdir()
        settings_path = claude_dir / "settings.local.json"
        # Pre-seed the 6 deprecated keys + an unrelated key (simulates a project
        # onboarded with the old 11-key block).
        seeded_env = {k: "stale" for k in DEPRECATED_OTEL_KEYS}
        seeded_env["UNRELATED_KEY"] = "keep-me"
        settings_path.write_text(
            json.dumps({"env": seeded_env}, indent=2) + "\n"
        )
        result = run_script(
            args=["--write", "--skip-ping", "--skip-model-sync"],
            env_overrides=CRED_ENV,
            cwd=tmp,
            path_dirs=[uv_dir],
        )
        runner.test("exits 0", result.returncode == 0, f"stderr={result.stderr!r}")
        env_block = json.loads(settings_path.read_text()).get("env", {})
        for k in DEPRECATED_OTEL_KEYS:
            runner.test(f"{k} pruned", k not in env_block, "still present")
        runner.test(
            "unrelated key preserved",
            env_block.get("UNRELATED_KEY") == "keep-me",
            f"got={env_block.get('UNRELATED_KEY')!r}",
        )
        for k in expected_env_block():
            runner.test(f"new key {k} present", k in env_block, "missing")


def test_prune_preserves_v3_traces_keys(runner):
    """The prune is exact-match: the V3 stack's OTEL_EXPORTER_OTLP_TRACES_* keys
    (a DIFFERENT namespace) must SURVIVE — a prefix match would wrongly strip them."""
    print("\ntest_prune_preserves_v3_traces_keys")
    with tempfile.TemporaryDirectory() as tmp, \
            tempfile.TemporaryDirectory() as uv_dir:
        make_fake_uv(Path(uv_dir))
        claude_dir = Path(tmp) / ".claude"
        claude_dir.mkdir()
        settings_path = claude_dir / "settings.local.json"
        v3_keys = {
            "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": "http://localhost:3000/otel/v1/traces",
            "OTEL_EXPORTER_OTLP_TRACES_HEADERS": "Authorization=Basic zzz",
            "OTEL_EXPORTER_OTLP_TRACES_PROTOCOL": "http/protobuf",
        }
        seeded = {**{k: "stale" for k in DEPRECATED_OTEL_KEYS}, **v3_keys}
        settings_path.write_text(json.dumps({"env": seeded}, indent=2) + "\n")
        result = run_script(
            args=["--write", "--skip-ping", "--skip-model-sync"],
            env_overrides=CRED_ENV,
            cwd=tmp,
            path_dirs=[uv_dir],
        )
        runner.test("exits 0", result.returncode == 0, f"stderr={result.stderr!r}")
        env_block = json.loads(settings_path.read_text()).get("env", {})
        for k, v in v3_keys.items():
            runner.test(
                f"V3 key {k} survives prune",
                env_block.get(k) == v,
                f"got={env_block.get(k)!r}",
            )
        for k in DEPRECATED_OTEL_KEYS:
            runner.test(f"{k} still pruned", k not in env_block, "present")


def test_write_warns_but_continues_on_model_sync_failure(runner):
    """--write with an unreachable host: model sync fails but setup still exits 0
    with settings written (warn-but-continue contract)."""
    print("\ntest_write_warns_but_continues_on_model_sync_failure")
    with tempfile.TemporaryDirectory() as tmp, \
            tempfile.TemporaryDirectory() as uv_dir:
        make_fake_uv(Path(uv_dir))
        # localhost:1 → connection refused (no real Langfuse touched). --skip-ping
        # so the unreachable host doesn't fail at the ping stage instead.
        env = dict(CRED_ENV, LANGFUSE_HOST="http://localhost:1")
        result = run_script(
            args=["--write", "--skip-ping"],  # NB: model sync NOT skipped
            env_overrides=env,
            cwd=tmp,
            path_dirs=[uv_dir],
        )
        runner.test(
            "exits 0 despite model-sync failure",
            result.returncode == 0,
            f"rc={result.returncode} stderr={result.stderr!r}",
        )
        runner.test(
            "stderr warns about model-sync failure",
            "model-price sync failed" in result.stderr,
            f"stderr={result.stderr!r}",
        )
        settings_path = Path(tmp) / ".claude" / "settings.local.json"
        runner.test(
            "settings still written",
            settings_path.exists(),
            f"missing: {settings_path}",
        )


def test_print_mode_notes_model_sync_skipped(runner):
    print("\ntest_print_mode_notes_model_sync_skipped")
    with tempfile.TemporaryDirectory() as tmp:
        result = run_script(
            args=["--skip-ping"], env_overrides=CRED_ENV, cwd=tmp
        )
        runner.test("exits 0", result.returncode == 0, f"stderr={result.stderr!r}")
        runner.test(
            "stderr notes model defs were NOT registered in print mode",
            "model-price definitions were NOT registered" in result.stderr,
            f"stderr={result.stderr!r}",
        )
        runner.test(
            "stderr points to --write follow-up",
            "--write" in result.stderr,
            f"stderr={result.stderr!r}",
        )


def main():
    runner = TestRunner()
    print("Testing scripts/setup_langfuse_tracing.py")
    test_loud_failure_names_all_missing(runner)
    test_happy_path_print_mode(runner)
    test_env_block_is_five_keys(runner)
    test_host_normalization(runner)
    test_infra_env_sourcing(runner)
    test_write_merges_existing_settings(runner)
    test_write_rejects_corrupt_settings(runner)
    test_write_creates_settings(runner)
    test_write_no_secrets_on_stdout(runner)
    test_write_warms_uv_cache(runner)
    test_write_warm_failure_not_fatal(runner)
    test_write_prunes_deprecated_otel_keys(runner)
    test_prune_preserves_v3_traces_keys(runner)
    test_write_warns_but_continues_on_model_sync_failure(runner)
    test_print_mode_notes_model_sync_skipped(runner)
    return runner.summary()


if __name__ == "__main__":
    sys.exit(main())
