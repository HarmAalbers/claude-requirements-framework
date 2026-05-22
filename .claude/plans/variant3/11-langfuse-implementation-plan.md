# Step 11 — Langfuse + Claude Agent SDK Observability — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use requirements-framework:executing-plans to implement this plan task-by-task.

**Goal:** Self-host Langfuse v3 locally and wire OpenInference's Claude Agent SDK instrumentor so every V3 `claude_agent_sdk.query()` call produces a trace visible in Langfuse — without breaking any code path when Langfuse isn't running.

**Architecture:** Three atomic stg patches on top of `refactor/step-08-llm-package-scaffold`. Patch 1 cleans up dead `[llm]` extras. Patch 2 brings up the local Langfuse stack + populates `hooks/lib/llm/observability.py` with a lazy-init instrumentor + ships dep-free unit tests. Patch 3 adds the runnable smoke spike + README walkthrough. Fail-open everywhere: no env vars → no traces → no errors.

**Tech Stack:** `claude-agent-sdk`, `openinference-instrumentation-claude-agent-sdk`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http`, `langfuse/langfuse:3` (Docker), Postgres 16, ClickHouse, Redis, MinIO.

**Source design:** `.claude/plans/variant3/11-langfuse-self-host-otel.md` (commit `8894603`).

**Branch:** `refactor/step-08-llm-package-scaffold` — continue stacking stg patches.

---

## Revisions log (post `/arch-review` 2026-05-22)

The team-based architecture review surfaced 8 findings worth applying before Patch 2 implementation. Required revisions:

- **R1 (HIGH)** — Split single `_initialized` flag into `_disabled_logged` (one-shot log guard) and `_instrumented` (only flips True when monkey-patch actually ran). Fixes the dotenv-after-import lifecycle bug where late env-var loading would silently no-op.
- **R2 (HIGH)** — Document the module-name split in `observability.py`'s docstring: `hooks.lib.llm.observability` vs `llm.observability` are distinct `sys.modules` entries.
- **R3 (CRITICAL converged)** — Decompose `init_observability` into `_read_langfuse_config` / `_build_tracer_provider` / `_install_claude_sdk_instrumentor`, with each helper owning its own imports. Eliminates the leaky-abstraction probe import.
- **R4 (MEDIUM)** — Pass `tracer_provider=provider` explicitly to `instrument()` per OpenInference upstream recommendation; don't rely on the OTel global.
- **R5 (LOW corroborated)** — Fix stale "Instructor-wrapped subagent workers" docstring in `hooks/lib/llm/__init__.py:10`. Added as a Patch 2 task (since Patch 1 is already landed and the user opted not to pop).
- **R6 (IMPORTANT)** — Pin the Langfuse compose-file source to a specific commit SHA (and record it in the patch commit message). No more floating `main` fetch.

Optional revisions also folded in:

- **R7 (MEDIUM, M2)** — Add `hooks/lib/llm/claude.py` thin wrapper that initializes observability before re-exporting `query` / `ClaudeSDKClient`. Future V3 code imports from this wrapper instead of `claude_agent_sdk` directly, making the ordering constraint structural rather than convention-based.
- **R8 (IMPORTANT, I3)** — Append an "Operational notes" section to ADR-016 covering: (a) `infra/` is the V3 dev-infra location, intentionally committed; (b) compose-file pinning policy; (c) acknowledgment of the dual-import path between `hooks/test_requirements.py` and `tests/`.

---

## Patch boundaries (stg series after Step 11)

```
+ step-08-llm-package
+ step-08-pyproject-llm-extras
+ step-09-pydantic-output-schemas
+ v3-substrate-pivot-docs
+ v3-supersede-step-plans
+ v3-preserve-spike-artifacts
+ step-11-revised-design-doc           ← already landed (8894603)
> step-11-pyproject-cleanup            ← Patch 1 (Tasks 1-2)
> step-11-observability-module         ← Patch 2 (Tasks 3-13)
> step-11-smoke-and-docs               ← Patch 3 (Tasks 14-17)
```

---

## Patch 1 — `step-11-pyproject-cleanup`

### Task 1: Drop dead extras from `pyproject.toml`

**Files:**
- Modify: `pyproject.toml:17-33`

**Why:** ADR-016 removed `pydantic-ai`, `instructor`, and `anthropic` from the V3 substrate; Step 13 will use local `sentence-transformers` instead of `llama-index-embeddings-openai`. Leaving them in the extras would mislead future readers about what V3 depends on.

**Step 1: Create the stg patch**

Run:
```bash
stg new step-11-pyproject-cleanup -m "chore(step-11): drop dead [llm] extras per ADR-016"
```

Expected: editor opens with the commit message pre-filled (or the message is set non-interactively). `stg series` shows the new patch as top.

**Step 2: Edit `pyproject.toml`**

Open `pyproject.toml`. The `[project.optional-dependencies]` block currently reads:

```toml
[project.optional-dependencies]
llm = [
    "pydantic-ai>=1.0",
    "instructor>=2.0",
    "anthropic>=0.40",
    "jinja2>=3.1",
    "langfuse>=3.0",
    "openinference-instrumentation-claude-agent-sdk>=0.1",
    "opentelemetry-sdk>=1.27",
    "opentelemetry-exporter-otlp-proto-http>=1.27",
    "qdrant-client>=1.12",
    "llama-index-core>=0.12",
    "llama-index-embeddings-openai>=0.3",
    "llama-index-vector-stores-qdrant>=0.4",
    "ragas>=0.2",
    "tiktoken>=0.8",
]
```

Replace with:

```toml
[project.optional-dependencies]
# V3 LLM platform deps. Substrate is `claude-agent-sdk` (inherits Claude Max auth
# from the bundled CLI subprocess); no direct Anthropic SDK use. See ADR-016.
llm = [
    "claude-agent-sdk>=0.2.82",
    "jinja2>=3.1",
    "langfuse>=3.0",
    "openinference-instrumentation-claude-agent-sdk>=0.1",
    "opentelemetry-sdk>=1.27",
    "opentelemetry-exporter-otlp-proto-http>=1.27",
    "qdrant-client>=1.12",
    "sentence-transformers>=3.0",
    "llama-index-core>=0.12",
    "llama-index-vector-stores-qdrant>=0.4",
    "ragas>=0.2",
    "tiktoken>=0.8",
]
```

Removed: `pydantic-ai`, `instructor`, `anthropic`, `llama-index-embeddings-openai`.
Added: `claude-agent-sdk` (was implicit), `sentence-transformers` (Step 13).

**Step 3: Verify `pip install -e '.[llm]' --dry-run` resolves**

Run:
```bash
pip install -e '.[llm]' --dry-run
```

Expected: dependency resolution prints a list of would-be-installed packages including `claude-agent-sdk`, `sentence-transformers`, `langfuse`, `openinference-instrumentation-claude-agent-sdk`. No `pydantic-ai`, `instructor`, `anthropic`. No errors.

If resolution errors out (e.g., `claude-agent-sdk>=0.2.82` not on PyPI yet), drop the lower bound to whatever the latest published version is.

**Step 4: Refresh the patch**

Run:
```bash
stg refresh && stg show
```

Expected: `stg show` displays a diff of `pyproject.toml` with the four removals + the `claude-agent-sdk` + `sentence-transformers` additions + the new comment line.

### Task 2: Verify framework tests still pass

**Step 1: Run the regression suite**

Run:
```bash
python3 hooks/test_requirements.py
```

Expected: `1290/1290 passed` (no regression from the pyproject change — these tests don't import the `[llm]` extras).

If it fails, investigate before continuing.

---

## Patch 2 — `step-11-observability-module`

This patch ships the Docker compose for local Langfuse, the populated `observability.py`, and the six dep-free unit tests — all together because TDD (write failing test, then minimal pass) needs both files in the same commit.

### Task 3: Create the stg patch and the `infra/` directory

**Files:**
- Create: `infra/` (new directory)

**Step 1: Create the patch**

Run:
```bash
stg new step-11-observability-module -m "feat(step-11): add local Langfuse stack and observability module"
```

Expected: new empty patch at the top of the stack.

**Step 2: Create the directory**

Run:
```bash
mkdir -p infra
```

Expected: `infra/` exists, empty.

### Task 4: Add the upstream Langfuse v3 self-hosting `docker-compose.yml`

**Files:**
- Create: `infra/docker-compose.yml`

**Why:** Langfuse v3 self-hosting requires 5 containers — `langfuse-web` + `langfuse-worker` + `postgres` + `clickhouse` + `redis` + `minio`. A simplified 2-container compose will not start a working Langfuse. The official upstream compose is the source of truth.

**Step 1: Resolve a pinned upstream SHA**

Per arch-review revision R6, we do NOT fetch `main` — that's a floating dependency. Pick a specific Langfuse commit SHA that produces a working compose file:

```bash
# Get the current SHA of langfuse/langfuse main HEAD
LANGFUSE_SHA="$(curl -sSL https://api.github.com/repos/langfuse/langfuse/commits/main | jq -r .sha)"
echo "Pinning to: $LANGFUSE_SHA"
```

Expected: a 40-char SHA. Record it; you'll embed it in the patch commit message and in a comment at the top of `infra/docker-compose.yml`.

**Step 2: Fetch the compose at that SHA**

```bash
curl -sSL "https://raw.githubusercontent.com/langfuse/langfuse/${LANGFUSE_SHA}/docker-compose.yml" -o infra/docker-compose.yml
```

Expected: ~5KB file written.

**Step 3: Annotate the file with its source SHA**

Prepend a comment to `infra/docker-compose.yml`:

```yaml
# Source: langfuse/langfuse@<LANGFUSE_SHA>
# Fetched: <ISO date>
# Update procedure: re-fetch from a specific SHA, update this header, refresh stg patch.
# Do NOT edit by hand — keep this file diff-clean against the upstream pin.
```

This makes the pinning explicit and discoverable. Future upgrades require a deliberate re-fetch.

**Step 2: Adjust the host-port mapping if needed**

Open `infra/docker-compose.yml`. Find the `langfuse-web` service's `ports` block. Confirm it maps host `3000:3000` (Langfuse default). If the port conflicts with something on your machine, change the host side only — e.g., `"3030:3000"` — and document the override in the README task later.

**Step 3: Smoke-start the stack**

Run:
```bash
cd infra && docker compose up -d && cd ..
```

Expected: Docker pulls 5 images on first run, brings up containers in dependency order. `docker compose -f infra/docker-compose.yml ps` shows all 5 containers in `running` (or `healthy`) state within ~60s.

If a container is `unhealthy`, run `docker compose -f infra/docker-compose.yml logs <service>` to diagnose. Common issues:
- Postgres init failure → blow away the volume: `docker compose down -v && docker compose up -d`
- ClickHouse permission errors on macOS → upstream issue; check the langfuse repo for a `LANGFUSE_CLICKHOUSE_*` workaround

**Step 4: Confirm Langfuse UI is reachable**

Run:
```bash
curl -sI http://localhost:3000 | head -1
```

Expected: `HTTP/1.1 200 OK` (or `302` redirect to `/auth/sign-in`).

### Task 5: Add `infra/.env.example`

**Files:**
- Create: `infra/.env.example`

**Step 1: Write the file**

Create `infra/.env.example` with:

```bash
# Copy to infra/.env (gitignored) and fill in real values after bootstrapping
# Langfuse via the web UI at http://localhost:3000.
#
# Bootstrap walkthrough: see README "Local observability" section.

LANGFUSE_PUBLIC_KEY=pk-lf-xxxxxxxxxxxxxxxxxxxx
LANGFUSE_SECRET_KEY=sk-lf-xxxxxxxxxxxxxxxxxxxx
LANGFUSE_HOST=http://localhost:3000

# Optional: turn on full tracebacks for init failures
# LANGFUSE_DEBUG=1
```

**Step 2: Verify the file exists**

Run:
```bash
ls -la infra/.env.example
```

Expected: file exists, ~400 bytes.

### Task 6: Update `.gitignore` to exclude `infra/.env`

**Files:**
- Modify: `.gitignore` (append section)

**Step 1: Append `infra/.env` to `.gitignore`**

Append to `.gitignore`:

```
# Local Langfuse credentials (created by user after Langfuse bootstrap)
infra/.env
```

**Step 2: Verify**

Run:
```bash
grep -A1 '^infra' .gitignore
```

Expected: shows the two lines above.

### Task 7: Write the first failing test — `test_disabled_when_no_public_key`

**Files:**
- Create: `tests/test_observability.py`

**Why:** We start with the test that exercises the fail-open path (env vars unset). This is the path users hit by default, and proving it works first protects every other path.

**Step 1: Create the test file with the harness scaffold**

Create `tests/test_observability.py`:

```python
#!/usr/bin/env python3
"""Test suite for hooks/lib/llm/observability.py — Step 11.

Follows the framework's TestRunner convention (see tests/test_schemas.py).
Run with: python3 tests/test_observability.py

Dependency-free: these tests never connect to a real Langfuse instance.
They verify env-var handling, ImportError swallowing, idempotency, and
log-once behavior.
"""

import io
import logging
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
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
def fresh_observability_module():
    """Reload observability with the current env, isolated from other tests."""
    sys.modules.pop("hooks.lib.llm.observability", None)
    from hooks.lib.llm import observability  # noqa: F401  reload-on-purpose
    try:
        yield observability
    finally:
        sys.modules.pop("hooks.lib.llm.observability", None)


def test_disabled_when_no_public_key(runner: TestRunner):
    print("\ntest_disabled_when_no_public_key")
    env_without_keys = {k: v for k, v in os.environ.items()
                         if not k.startswith("LANGFUSE_")}
    with patch.dict(os.environ, env_without_keys, clear=True):
        with fresh_observability_module() as obs:
            result = obs.init_observability()
            runner.test(
                "returns None when no env vars",
                result is None,
                f"expected None, got {result!r}",
            )
            # R1: _disabled_logged flips True to suppress log spam on repeat calls
            runner.test(
                "_disabled_logged = True after env-vars-unset path",
                obs._disabled_logged is True,
                f"expected True, got {obs._disabled_logged!r}",
            )
            # R1: _instrumented stays False so a later explicit init (after
            # dotenv loading) can still complete instrumentation.
            runner.test(
                "_instrumented stays False (allows late init after env loads)",
                obs._instrumented is False,
                f"expected False, got {obs._instrumented!r}",
            )


if __name__ == "__main__":
    runner = TestRunner()
    test_disabled_when_no_public_key(runner)
    sys.exit(runner.summary())
```

**Step 2: Run the test — expect failure**

Run:
```bash
python3 tests/test_observability.py
```

Expected: ImportError or `ModuleNotFoundError` referencing `hooks.lib.llm.observability` because the module is still a docstring stub with no `init_observability` symbol. (Confirms the test reaches the real code path.)

### Task 8: Implement minimal `observability.py` to pass Test 1

**Files:**
- Modify: `hooks/lib/llm/observability.py`

**Step 1: Replace the stub with the minimal implementation**

Open `hooks/lib/llm/observability.py`. Currently:

```python
"""Langfuse + OpenInference instrumentation (populated in Step 11)."""
```

Replace with:

```python
"""Langfuse + OpenInference instrumentation for Claude Agent SDK calls.

Public surface:
    init_observability() -> None  — idempotent on the success path. Reads
        LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST from env.
        If any are unset OR the required extras aren't installed, logs
        once at INFO level and returns WITHOUT permanently disabling — a
        later explicit call (e.g. after dotenv-loading at runtime) can
        still complete instrumentation.

State flags (R1 — arch-review revision):
    _disabled_logged — flips True once we've logged the "disabled" message.
        Prevents log spam on repeat calls when env vars stay unset.
    _instrumented — flips True only AFTER `instrument()` actually ran.
        Drives idempotence for the success path. Stays False after the
        "no env vars" or ImportError paths, allowing late init.

Module-name caveat (R2 — arch-review revision):
    `hooks.lib.llm.observability` and `llm.observability` resolve to the
    same physical file but appear in `sys.modules` as DIFFERENT entries
    when both import paths are exercised in one process — e.g.,
    hooks/test_requirements.py via `sys.path += ['hooks/lib']` vs
    tests/test_observability.py via repo-root sys.path. Each module copy
    has its own _instrumented / _disabled_logged flags. OpenInference's
    own BaseInstrumentor guard prevents double-monkey-patching, so this
    is safe — but the in-Python idempotence guarantee holds only
    per-module-name. Document and accept; do not try to reconcile in
    code.

Auto-init:
    The module body calls init_observability() once at the bottom, so
    `from hooks.lib.llm import observability` is enough to enable tracing
    when env vars are set. Callers may also call init_observability()
    explicitly after loading env from a .env file — both paths are valid.

Design: .claude/plans/variant3/11-langfuse-self-host-otel.md
"""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger(__name__)

_disabled_logged = False
_instrumented = False


def init_observability() -> None:
    """Idempotent on the success path. See module docstring."""
    global _disabled_logged, _instrumented
    if _instrumented:
        return

    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    host = os.getenv("LANGFUSE_HOST")

    if not (public_key and secret_key and host):
        if not _disabled_logged:
            logger.info(
                "Langfuse observability disabled "
                "(LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST unset)"
            )
            _disabled_logged = True
        return


init_observability()
```

**Step 2: Run the test — expect pass**

Run:
```bash
python3 tests/test_observability.py
```

Expected: `3/3 passed` (return-None + _disabled_logged + _instrumented assertions in `test_disabled_when_no_public_key`).

### Task 9: Add `test_disabled_on_import_error` and the ImportError-swallowing logic

**Files:**
- Modify: `tests/test_observability.py`
- Modify: `hooks/lib/llm/observability.py`

**Step 1: Append the test**

Append to `tests/test_observability.py` (above the `if __name__ == "__main__":` line):

```python
def test_disabled_on_import_error(runner: TestRunner):
    print("\ntest_disabled_on_import_error")
    fake_env = {
        "LANGFUSE_PUBLIC_KEY": "pk-test",
        "LANGFUSE_SECRET_KEY": "sk-test",
        "LANGFUSE_HOST": "http://localhost:3000",
    }
    # Force the openinference import to fail by aliasing it to a missing module
    with patch.dict(os.environ, fake_env, clear=True), \
         patch.dict(sys.modules,
                    {"openinference.instrumentation.claude_agent_sdk": None}):
        with fresh_observability_module() as obs:
            result = obs.init_observability()
            runner.test(
                "returns None when openinference unavailable",
                result is None,
                f"expected None, got {result!r}",
            )
            # R1: ImportError path also uses _disabled_logged guard,
            # NOT a permanent _instrumented flip — allows recovery
            # if user installs the extras later in the same process.
            runner.test(
                "_disabled_logged = True after ImportError",
                obs._disabled_logged is True,
                f"expected True, got {obs._disabled_logged!r}",
            )
            runner.test(
                "_instrumented stays False on ImportError",
                obs._instrumented is False,
                f"expected False, got {obs._instrumented!r}",
            )
```

And update the `__main__` block:

```python
if __name__ == "__main__":
    runner = TestRunner()
    test_disabled_when_no_public_key(runner)
    test_disabled_on_import_error(runner)
    sys.exit(runner.summary())
```

**Step 2: Run the tests — expect 3/5 fail**

Run:
```bash
python3 tests/test_observability.py
```

Expected: 3/5 pass (the keys-unset assertions still pass; the ImportError assertions fail because the implementation does not yet attempt the OpenInference import).

**Step 3: Implement the ImportError-swallowing path (interim form — final decomposition lands in Task 13)**

In `hooks/lib/llm/observability.py`, replace the function with:

```python
def init_observability() -> None:
    """Idempotent on the success path. See module docstring."""
    global _disabled_logged, _instrumented
    if _instrumented:
        return

    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    host = os.getenv("LANGFUSE_HOST")

    if not (public_key and secret_key and host):
        if not _disabled_logged:
            logger.info(
                "Langfuse observability disabled "
                "(LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST unset)"
            )
            _disabled_logged = True
        return

    try:
        # R3: imports stay inside their own scope until Task 13 decomposes
        # into _build_tracer_provider / _install_claude_sdk_instrumentor.
        # No standalone probe — let ImportError surface here directly.
        from openinference.instrumentation.claude_agent_sdk import (
            ClaudeAgentSDKInstrumentor,
        )
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as exc:
        if not _disabled_logged:
            logger.info(
                "Langfuse observability disabled (install with: "
                "pip install -e '.[llm]'). Missing: %s",
                exc.name or exc,
            )
            _disabled_logged = True
        return

    # Instrumentation wiring lands in Task 13's decomposed helpers.
    # For now, mark this task complete; the success path is filled in later.
    _instrumented = True  # placeholder; Task 13 moves this AFTER instrument() call
```

**Step 4: Run the tests — expect 5/5 pass**

Run:
```bash
python3 tests/test_observability.py
```

Expected: `5/5 passed`.

### Task 10: Add `test_init_idempotent` + verify the existing guard handles it

**Files:**
- Modify: `tests/test_observability.py`

**Step 1: Append the test**

```python
def test_init_idempotent(runner: TestRunner):
    print("\ntest_init_idempotent")
    with patch.dict(os.environ, {}, clear=True):
        with fresh_observability_module() as obs:
            obs.init_observability()
            # second call should be a no-op for logging but still NOT
            # set _instrumented (env vars are missing — late init must
            # remain possible).
            obs.init_observability()
            runner.test(
                "_disabled_logged stays True across repeated calls",
                obs._disabled_logged is True,
                f"got {obs._disabled_logged!r}",
            )
            # R1: idempotence MUST NOT extend to instrumented=True on the
            # env-vars-missing path. If a dotenv loader populates env later,
            # a third call should succeed.
            runner.test(
                "_instrumented stays False (late init still allowed)",
                obs._instrumented is False,
                f"got {obs._instrumented!r}",
            )
```

Add `test_init_idempotent(runner)` to the `__main__` block.

**Step 2: Run — expect pass without further implementation changes**

Run:
```bash
python3 tests/test_observability.py
```

Expected: `7/7 passed`. The `_disabled_logged` guard already prevents log spam; `_instrumented` stays False by design when env vars are missing. If this test fails, R1's flag semantics are wrong.

### Task 11: Add `test_logs_disabled_message_once`

**Files:**
- Modify: `tests/test_observability.py`

**Step 1: Append the test (still no implementation change needed)**

```python
def test_logs_disabled_message_once(runner: TestRunner):
    print("\ntest_logs_disabled_message_once")
    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.INFO)

    obs_logger = logging.getLogger("hooks.lib.llm.observability")
    obs_logger.addHandler(handler)
    obs_logger.setLevel(logging.INFO)

    try:
        with patch.dict(os.environ, {}, clear=True):
            with fresh_observability_module() as obs:
                obs.init_observability()
                obs.init_observability()
        log_output = log_stream.getvalue()
        disabled_count = log_output.count("Langfuse observability disabled")
        runner.test(
            "logs the disabled message exactly once",
            disabled_count == 1,
            f"expected 1, got {disabled_count} (output: {log_output!r})",
        )
    finally:
        obs_logger.removeHandler(handler)
```

Note: the bottom-of-module `init_observability()` call runs during module import, which produces one log AND sets `_disabled_logged=True`. The two subsequent explicit calls in the test hit the `if not _disabled_logged: …` guard and skip the log without setting `_instrumented`. So total log count is exactly 1 (from module import), and `_instrumented` stays False throughout — both invariants of R1.

Add `test_logs_disabled_message_once(runner)` to the `__main__` block.

**Step 2: Run — expect pass**

Run:
```bash
python3 tests/test_observability.py
```

Expected: `8/8 passed`.

### Task 12: Add `test_module_import_triggers_init`

**Files:**
- Modify: `tests/test_observability.py`

**Why:** Catch the regression where a future refactor removes the bottom-of-module `init_observability()` call. We assert in a *subprocess* (isolated from any module-cache pollution) that bare import doesn't raise.

**Step 1: Append the test**

```python
def test_module_import_triggers_init(runner: TestRunner):
    print("\ntest_module_import_triggers_init")
    # R1: subprocess isolates from main test process module cache.
    # With no LANGFUSE_* env: import must succeed, _disabled_logged must
    # be True (log emitted once), _instrumented must STAY FALSE (so any
    # caller that loads env later can still init successfully).
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from hooks.lib.llm import observability; "
            "assert observability._disabled_logged is True, "
            "    f'_disabled_logged={observability._disabled_logged}'; "
            "assert observability._instrumented is False, "
            "    f'_instrumented={observability._instrumented}'",
        ],
        cwd=REPO_ROOT,
        env={k: v for k, v in os.environ.items()
             if not k.startswith("LANGFUSE_")},
        capture_output=True,
        text=True,
    )
    runner.test(
        "subprocess imports cleanly without LANGFUSE env vars (R1 flags correct)",
        result.returncode == 0,
        f"stdout={result.stdout!r} stderr={result.stderr!r}",
    )
```

Add the test to the `__main__` block.

**Step 2: Run — expect pass**

Run:
```bash
python3 tests/test_observability.py
```

Expected: `7/7 passed`.

### Task 13: Add `test_logs_init_failure_with_traceback_only_when_debug_set` + wire the `LANGFUSE_DEBUG` branch

**Files:**
- Modify: `tests/test_observability.py`
- Modify: `hooks/lib/llm/observability.py`

**Step 1: Append the test**

```python
def test_logs_init_failure_with_traceback_only_when_debug_set(runner: TestRunner):
    print("\ntest_logs_init_failure_with_traceback_only_when_debug_set")
    fake_env = {
        "LANGFUSE_PUBLIC_KEY": "pk-test",
        "LANGFUSE_SECRET_KEY": "sk-test",
        "LANGFUSE_HOST": "http://localhost:3000",
    }

    def force_raise_during_init(*_a, **_kw):
        raise RuntimeError("simulated init failure")

    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    obs_logger = logging.getLogger("hooks.lib.llm.observability")
    obs_logger.addHandler(handler)
    obs_logger.setLevel(logging.INFO)

    try:
        # First: no debug flag → no traceback
        with patch.dict(os.environ, fake_env, clear=True), \
             patch("hooks.lib.llm.observability._install_claude_sdk_instrumentor",
                   force_raise_during_init):
            with fresh_observability_module() as obs:
                # R1: reset BOTH flags so this test isolates from the
                # module-import auto-init that ran when env was unset.
                obs._disabled_logged = False
                obs._instrumented = False
                obs.init_observability()
        no_debug_output = log_stream.getvalue()
        runner.test(
            "without LANGFUSE_DEBUG: no 'Traceback' in log",
            "Traceback" not in no_debug_output,
            f"got: {no_debug_output!r}",
        )

        # Second: LANGFUSE_DEBUG=1 → traceback included
        log_stream.truncate(0)
        log_stream.seek(0)
        with patch.dict(os.environ, {**fake_env, "LANGFUSE_DEBUG": "1"}, clear=True), \
             patch("hooks.lib.llm.observability._install_claude_sdk_instrumentor",
                   force_raise_during_init):
            with fresh_observability_module() as obs:
                obs._disabled_logged = False
                obs._instrumented = False
                obs.init_observability()
        debug_output = log_stream.getvalue()
        runner.test(
            "with LANGFUSE_DEBUG=1: 'Traceback' present in log",
            "Traceback" in debug_output,
            f"got: {debug_output!r}",
        )
    finally:
        obs_logger.removeHandler(handler)
```

**Note (R3)**: this test patches `_install_claude_sdk_instrumentor` (the renamed and decomposed helper, defined in Step 3 below). The `create=True` argument is intentionally absent — the helper MUST exist in the module before the patch; `create=True` would silently mask a typo or rename. Per tdd-validator's finding, this hardens the test against future refactors.

Add the test to the `__main__` block.

**Step 2: Run the test — expect failure**

Run:
```bash
python3 tests/test_observability.py
```

Expected: 8/10 pass; the two new assertions fail because `_install_claude_sdk_instrumentor` does not yet exist (the test's `patch(…)` call without `create=True` will raise `AttributeError`).

**Step 3: Decompose `init_observability()` into three single-responsibility helpers (R3 + R4)**

Per the arch-review's CRITICAL converged finding, `init_observability()` was doing too many things in one function. Replace its body and add three helpers, each owning its own imports. The final module shape is:

```python
"""Langfuse + OpenInference instrumentation for Claude Agent SDK calls.

… (docstring from Task 8 unchanged; see module docstring for R1 + R2 notes)
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

logger = logging.getLogger(__name__)

_disabled_logged = False
_instrumented = False


def _read_langfuse_config() -> tuple[str, str, str] | None:
    """Read the three LANGFUSE_* env vars.

    Returns (public_key, secret_key, host) if all are set, else None.
    Single responsibility: env-reading only. No logging side effects.
    """
    pk = os.getenv("LANGFUSE_PUBLIC_KEY")
    sk = os.getenv("LANGFUSE_SECRET_KEY")
    host = os.getenv("LANGFUSE_HOST")
    if pk and sk and host:
        return pk, sk, host
    return None


def _build_tracer_provider(public_key: str, secret_key: str, host: str) -> Any:
    """Construct an OTel TracerProvider wired to the Langfuse OTLP endpoint.

    Owns the OTel imports. Returns the provider — the caller passes it
    explicitly to instrument() (R4), avoiding reliance on the OTel global.
    """
    from base64 import b64encode

    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter,
    )
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    auth = b64encode(f"{public_key}:{secret_key}".encode()).decode()
    exporter = OTLPSpanExporter(
        endpoint=f"{host.rstrip('/')}/api/public/otel/v1/traces",
        headers={"Authorization": f"Basic {auth}"},
    )
    provider = TracerProvider()
    provider.add_span_processor(BatchSpanProcessor(exporter))
    return provider


def _install_claude_sdk_instrumentor(provider: Any) -> None:
    """Install the Claude Agent SDK instrumentor against the given provider.

    R4: passes `tracer_provider=provider` explicitly rather than relying on
    `trace.set_tracer_provider()` having been called. More robust per
    OpenInference upstream usage.
    """
    from openinference.instrumentation.claude_agent_sdk import (
        ClaudeAgentSDKInstrumentor,
    )
    ClaudeAgentSDKInstrumentor().instrument(tracer_provider=provider)


def init_observability() -> None:
    """Idempotent on the success path. See module docstring."""
    global _disabled_logged, _instrumented
    if _instrumented:
        return

    config = _read_langfuse_config()
    if config is None:
        if not _disabled_logged:
            logger.info(
                "Langfuse observability disabled "
                "(LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST unset)"
            )
            _disabled_logged = True
        return

    try:
        provider = _build_tracer_provider(*config)
        _install_claude_sdk_instrumentor(provider)
    except ImportError as exc:
        # R3: no separate probe — let helpers' imports surface here.
        if not _disabled_logged:
            logger.info(
                "Langfuse observability disabled (install with: "
                "pip install -e '.[llm]'). Missing: %s",
                exc.name or exc,
            )
            _disabled_logged = True
        return
    except Exception as exc:  # noqa: BLE001 — intentional: fail-open
        if os.getenv("LANGFUSE_DEBUG") == "1":
            logger.exception("Langfuse observability failed to initialize")
        else:
            logger.info(
                "Langfuse observability failed to initialize: %s "
                "(set LANGFUSE_DEBUG=1 for traceback)",
                exc,
            )
        # Per R1, instrumentation didn't run — _disabled_logged guards the
        # log; _instrumented stays False so the next call can retry once
        # the underlying problem is fixed (e.g. Langfuse becomes reachable).
        _disabled_logged = True
        return

    # ONLY now — after instrument() has actually run — set the success flag.
    _instrumented = True


init_observability()
```

Why the decomposition matters:

| Helper | Responsibility | Imports it owns |
|---|---|---|
| `_read_langfuse_config` | Env reading | stdlib only |
| `_build_tracer_provider` | OTel exporter + provider construction | `base64`, `opentelemetry.*` |
| `_install_claude_sdk_instrumentor` | OpenInference instrumentor install | `openinference.*` |
| `init_observability` | Policy / idempotence / error handling | None of the above (delegates) |

Each helper has one reason to change. The leaky-abstraction probe is gone. The success flag (`_instrumented = True`) only flips AFTER `instrument()` actually ran.

**Step 4: Run the tests — expect 10/10 pass**

Run:
```bash
python3 tests/test_observability.py
```

Expected: `10/10 passed`.

If any test fails, do not refresh the patch yet — debug first. Particular failure to watch for: the `patch("…_install_claude_sdk_instrumentor", …)` line in the new test will raise `AttributeError` if you missed renaming or omitted the helper. That's a fast-fail by design (R3 hardening per tdd-validator).

### Task 14: Refresh the observability patch and verify regression

**Step 1: Refresh**

Run:
```bash
stg refresh && stg show --stat
```

Expected: `stg show --stat` lists 7 files (R5 + R7 added `__init__.py` + `claude.py` versus the original 5):

```
.gitignore
docs/adr/ADR-016-v3-claude-agent-sdk-substrate.md  (R8 — amendment appended)
hooks/lib/llm/__init__.py                          (R5 — docstring fix)
hooks/lib/llm/claude.py                            (R7 — new wrapper)
hooks/lib/llm/observability.py                     (Tasks 8 + 13)
infra/.env.example
infra/docker-compose.yml
tests/test_observability.py
```

**Step 2: Run framework tests**

Run:
```bash
python3 hooks/test_requirements.py
```

Expected: `1290/1290 passed`.

**Step 3: Verify clean import path**

Run:
```bash
python3 -c "from hooks.lib.llm import observability; print('ok')"
```

Expected: prints `ok`. If LANGFUSE_PUBLIC_KEY is unset, the INFO log line appears first.

### Task 14a: Fix stale `Instructor` docstring in `hooks/lib/llm/__init__.py` (R5)

**Files:**
- Modify: `hooks/lib/llm/__init__.py:10`

**Why:** refactor-advisor and codex-arch-reviewer independently flagged a stale string. Line 10 reads `"workers — Instructor-wrapped subagent workers (Step 10+)"` — `Instructor` is no longer load-bearing per ADR-016. Patch 1 (already landed) was the natural home for this fix; since the user opted not to pop, fold the change into Patch 2.

**Step 1: Edit the docstring**

Open `hooks/lib/llm/__init__.py`. The relevant line:

```python
    workers        — Instructor-wrapped subagent workers (Step 10+)
```

Replace with:

```python
    claude         — Thin Agent SDK wrapper that initializes observability (Step 11, R7)
    workers        — Claude Agent SDK worker primitives (Step 10+)
```

(The `claude` line documents the new wrapper module added in Task 14b — keeps the module-level docstring in sync with reality.)

**Step 2: Verify the file still imports**

Run:
```bash
python3 -c "from hooks.lib.llm import __doc__; print(__doc__[:200])"
```

Expected: prints the first 200 chars of the docstring without raising.

### Task 14b: Add `hooks/lib/llm/claude.py` thin wrapper (R7 / M2)

**Files:**
- Create: `hooks/lib/llm/claude.py`

**Why:** the import-order convention ("import observability before claude_agent_sdk") is fragile — anyone writing new V3 code can accidentally skip it. R7 (codex's MEDIUM finding M2) makes the ordering structural: this wrapper module initializes observability at its own import time, then re-exports the Agent SDK symbols V3 code actually needs. Future V3 modules import from `hooks.lib.llm.claude` instead of `claude_agent_sdk`, and tracing is guaranteed.

**Step 1: Create the wrapper module**

Create `hooks/lib/llm/claude.py`:

```python
"""V3-safe re-export of the Claude Agent SDK with observability pre-initialized.

V3 code SHOULD import from this module rather than from `claude_agent_sdk`
directly. Rationale (R7 / arch-review M2): the OpenInference instrumentor
monkey-patches `claude_agent_sdk.query` and `ClaudeSDKClient` at instrument
time. Any module that imported those symbols BEFORE instrumentation will
hold references to the un-traced originals. Routing all V3 imports through
this wrapper guarantees the right import order without relying on developer
discipline.

Usage:
    from hooks.lib.llm.claude import query, ClaudeSDKClient, ClaudeAgentOptions

The module body calls init_observability() once at import time. If env vars
or extras are missing, observability silently no-ops (per R1) and these
symbols still work — they just don't produce traces.
"""

from __future__ import annotations

# Step 1 — initialize observability BEFORE importing claude_agent_sdk.
from hooks.lib.llm.observability import init_observability
init_observability()

# Step 2 — now import (or re-import) the SDK. The instrumentor's monkey-patch
# is already in place if observability was successfully enabled.
from claude_agent_sdk import (  # noqa: E402 — order is the point
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    query,
)

__all__ = [
    "ClaudeAgentOptions",
    "ClaudeSDKClient",
    "ResultMessage",
    "query",
]
```

**Step 2: Smoke-test the import**

Run:
```bash
python3 -c "from hooks.lib.llm.claude import query, ClaudeSDKClient; print('ok')"
```

Expected: prints `ok`. The "observability disabled" INFO log appears first if env vars are unset (that's correct — it proves init_observability ran).

**Step 3: Update the smoke spike to use the wrapper (forward reference)**

Note: Task 15's smoke spike currently imports `from claude_agent_sdk import …`. When that task lands, it MUST be updated to `from hooks.lib.llm.claude import …` instead. This is captured in Task 15's revision below.

### Task 14c: Append "Operational notes" section to ADR-016 (R8 / I3)

**Files:**
- Modify: `docs/adr/ADR-016-v3-claude-agent-sdk-substrate.md` (append section)

**Why:** arch-review I1 + I3 flagged that `infra/` location, compose pinning policy, and the dual-import-path caveat are undocumented architectural decisions. ADR-016 already governs the V3 substrate; the cleanest place to record these operational details is as an amendment to ADR-016 rather than a new ADR-017.

**Step 1: Append the section**

At the bottom of `docs/adr/ADR-016-v3-claude-agent-sdk-substrate.md`, append:

```markdown
## Operational notes (added 2026-05-22, Step 11)

### Local infra location

V3 dev infrastructure (Docker compose for self-hosted Langfuse, future Qdrant in Step 13, etc.) lives under `infra/` at the repo root. This directory is intentionally committed, not gitignored — the compose file is part of the project's operational contract. Per-user credentials go in `infra/.env` (which IS gitignored); `infra/.env.example` is committed as a template.

### Pinning third-party compose files

When this project vendors an upstream Docker compose file (Step 11 imports Langfuse's), we pin to a specific commit SHA, not a branch. The fetched file MUST carry a header comment naming the source repo and SHA. Updates require a deliberate re-fetch with a new pin. Floating `main`-tracked dependencies are out of scope per the spirit of ADR-016 (predictable substrate).

### Dual-import-path caveat for V3 modules

Two import styles for V3 code coexist in this repo:

1. `hooks/test_requirements.py` puts `hooks/lib/` on `sys.path` and imports as `llm.observability`.
2. V3 tests and spikes under `tests/` and `hooks/lib/llm/_spikes/` put repo root on `sys.path` and import as `hooks.lib.llm.observability`.

Both paths resolve to the same physical files but appear as DIFFERENT `sys.modules` entries when exercised in the same process. V3 modules that hold module-global state (e.g., `observability.py`'s `_disabled_logged` / `_instrumented` flags) must tolerate this by ensuring underlying side effects are themselves idempotent at the library level (OpenInference's `BaseInstrumentor` guard suffices). Do not attempt to reconcile this in Python — it would require canonicalizing `sys.path` across all entry points, which is out of scope.

### Why no separate ADR-017

These three items are operational refinements of ADR-016, not new decisions. Recording them inline keeps the substrate's decision boundary in one document.
```

**Step 2: Verify the file is valid markdown**

Run:
```bash
grep -c '^## ' docs/adr/ADR-016-v3-claude-agent-sdk-substrate.md
```

Expected: at least 5 (the existing headers + new "Operational notes"). No syntax errors at the markdown level.

### Task 14d: Re-refresh the observability patch with the R5/R7/R8 additions

**Step 1: Refresh again**

Run:
```bash
stg refresh && stg show --stat
```

Expected: now shows the full file list documented in Task 14 Step 1 (8 files changed in this single patch).

**Step 2: Re-run all tests**

Run:
```bash
python3 hooks/test_requirements.py && python3 tests/test_observability.py
```

Expected: `1290/1290 passed` AND `10/10 passed`.

---

## Patch 3 — `step-11-smoke-and-docs`

### Task 15: Create the patch and add the smoke spike

**Files:**
- Create: `hooks/lib/llm/_spikes/v3_langfuse_smoke.py`

**Step 1: Create the patch**

Run:
```bash
stg new step-11-smoke-and-docs -m "feat(step-11): add Langfuse smoke spike + README walkthrough"
```

**Step 2: Write the smoke spike**

Create `hooks/lib/llm/_spikes/v3_langfuse_smoke.py`:

```python
#!/usr/bin/env python3
"""Step 11 smoke — verifies Langfuse + Claude Agent SDK observability wiring.

Prereqs:
    cd infra && docker compose up -d
    # Bootstrap Langfuse via http://localhost:3000 (see README "Local
    # observability") and copy the keys.
    export LANGFUSE_PUBLIC_KEY=pk-...
    export LANGFUSE_SECRET_KEY=sk-...
    export LANGFUSE_HOST=http://localhost:3000

Run:
    python3 hooks/lib/llm/_spikes/v3_langfuse_smoke.py

Verify:
    Open http://localhost:3000 → Traces tab → look for a trace from the last
    minute. Expected attributes: model=claude-sonnet-4-6, input_tokens > 0,
    output_tokens > 0, output_format schema name = ReviewFinding.
"""

import asyncio
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

# R7: import from the V3 wrapper, not claude_agent_sdk directly.
# The wrapper initializes observability at its own import time, guaranteeing
# the monkey-patch is in place before query() resolves.
from hooks.lib.llm.claude import ClaudeAgentOptions, query, ResultMessage

from hooks.lib.llm.schemas import ReviewFinding


async def main() -> int:
    start = time.monotonic()
    prompt = (
        "Review this one-line diff for issues. Return a single ReviewFinding "
        "with severity SUGGESTION if all is well.\n\n"
        "@@ -1 +1 @@\n-print('hi')\n+print('hi')\n"
    )
    options = ClaudeAgentOptions(
        system_prompt="You are a code reviewer. Return one ReviewFinding.",
        model="claude-sonnet-4-6",
        allowed_tools=[],
        max_turns=5,
        output_format={
            "type": "json_schema",
            "schema": ReviewFinding.model_json_schema(),
        },
    )

    async for msg in query(prompt=prompt, options=options):
        if isinstance(msg, ResultMessage):
            if msg.subtype == "success":
                finding = ReviewFinding.model_validate(msg.structured_output)
                print(f"✓ Got ReviewFinding: severity={finding.severity}, "
                      f"category={finding.category}")
            else:
                print(f"✗ query failed: subtype={msg.subtype}")
                return 1

    elapsed = time.monotonic() - start
    print(f"\nElapsed: {elapsed:.1f}s")
    print("→ Now open http://localhost:3000 → Traces and look for the most "
          "recent claude_agent_sdk.query span.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

**Step 3: Verify the spike imports cleanly without running the query**

Run:
```bash
python3 -c "import ast; ast.parse(open('hooks/lib/llm/_spikes/v3_langfuse_smoke.py').read())"
```

Expected: no output (syntax-valid).

**Step 4: (Manual) Run the spike if Langfuse + env vars are set up**

Run:
```bash
python3 hooks/lib/llm/_spikes/v3_langfuse_smoke.py
```

Expected with env vars set + Langfuse running: ~5-30s wall-clock; prints `✓ Got ReviewFinding`; prints elapsed time and UI link. A trace appears in Langfuse UI within 5s of completion.

Expected with env vars unset: still completes successfully (`init_observability` skipped silently); single INFO log line at the top noting observability disabled; no trace produced.

### Task 16: Add the "Local observability" section to `README.md`

**Files:**
- Modify: `README.md`

**Step 1: Find the right anchor**

Open `README.md`. Identify a sensible insertion point — typically just before the "Architecture" or "Development" section, or at the end if those don't exist. Use:

```bash
grep -n '^## ' README.md
```

to see existing top-level sections.

**Step 2: Insert the new section**

Add this section at the chosen location:

````markdown
## Local observability (V3)

V3 LLM calls (Step 11+) can be traced into a self-hosted Langfuse instance.
This is opt-in: with no env vars set, V3 code runs without tracing and no
errors are raised.

### One-time bootstrap

```bash
# 1. Bring up Langfuse + Postgres + ClickHouse + Redis + MinIO
cd infra && docker compose up -d && cd ..

# Wait ~60s for all containers to become healthy
docker compose -f infra/docker-compose.yml ps

# 2. Open the UI and create a user + project
open http://localhost:3000
#    a. Sign up (local-only account — any email works)
#    b. Create an organization (e.g., "local")
#    c. Create a project (e.g., "requirements-framework")
#    d. Settings → API Keys → Create new keys
#    e. Copy the public + secret key

# 3. Save the keys to an environment file
cp infra/.env.example infra/.env
$EDITOR infra/.env    # paste the two keys

# 4. Source the env vars in your shell
set -a; source infra/.env; set +a
```

### Verify the wiring

```bash
python3 hooks/lib/llm/_spikes/v3_langfuse_smoke.py
```

Expected: prints `✓ Got ReviewFinding`, then a UI link. Within 5s, a trace
appears in Langfuse UI → Traces tab.

### Tear down

```bash
docker compose -f infra/docker-compose.yml down       # stop containers, keep data
docker compose -f infra/docker-compose.yml down -v    # stop + delete trace history
```

### Troubleshooting

- **"observability disabled" log line**: one or more of `LANGFUSE_PUBLIC_KEY`,
  `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` is unset. Re-source `infra/.env`.
- **Code runs but no trace appears**: check `OTEL_LOG_LEVEL=debug python3 ...`
  to see exporter retries.
- **Init failure with no traceback**: set `LANGFUSE_DEBUG=1` to get the full
  stack trace.
- **Container `unhealthy` after `up -d`**: `docker compose logs <service>` and
  consult [Langfuse self-hosting docs](https://langfuse.com/self-hosting).
````

**Step 3: Verify the section renders sensibly**

Run:
```bash
grep -A3 'Local observability' README.md | head -20
```

Expected: shows the new heading + first few lines.

### Task 17: Refresh the final patch and run the full verification matrix

**Step 1: Refresh**

Run:
```bash
stg refresh && stg show --stat && stg series
```

Expected: 3 files changed in the smoke patch; stg series shows 10 patches total (7 prior + 3 from Step 11).

**Step 2: Run all tests**

Run:
```bash
python3 hooks/test_requirements.py && python3 tests/test_observability.py && python3 tests/test_schemas.py
```

Expected: `1290/1290 passed`, `9/9 passed`, `20/20 passed`.

**Step 3: Update `refactor-current-status.md` memory**

This is bookkeeping, not a patch — update directly:

Edit `/Users/harm/.claude/projects/-Users-harm-Tools-claude-requirements-framework/memory/refactor-current-status.md`:
- Change Step 11 status from `⬜ **next**` to `✅ done (<short-sha>, branch `refactor/step-08-llm-package-scaffold`, **not yet merged to master**)`
- Bump `Last updated:` to today's date
- Rewrite the "What 'next' means at this moment" section to point at Step 17 (token budget) as the new next step per the revised ordering in ADR-016

**Step 4: Confirm the stack is clean**

Run:
```bash
git status && stg series
```

Expected: clean working tree; 10 patches in the stack.

---

## Final acceptance checklist (consolidated — post arch-review revisions)

Run all of these and confirm before declaring Step 11 done. Items reference the R-numbered revisions in the log at the top of this file.

**Patch 1 (already landed as 4fa65ff):**
- [x] `pyproject.toml [llm]` lists `claude-agent-sdk`, `sentence-transformers`, NOT `pydantic-ai`/`instructor`/`anthropic`/`llama-index-embeddings-openai`

**Patch 2 — observability module:**
- [ ] **R6**: `infra/docker-compose.yml` has a header comment naming `langfuse/langfuse@<sha>` and the fetch date
- [ ] `docker compose -f infra/docker-compose.yml up -d` brings up 5 containers, all healthy within 60s
- [ ] **R1 + R2**: `hooks/lib/llm/observability.py` has both `_disabled_logged` and `_instrumented` flags, with module-name caveat documented in the module docstring
- [ ] **R3**: `observability.py` exposes `_read_langfuse_config`, `_build_tracer_provider`, `_install_claude_sdk_instrumentor` as separate helpers
- [ ] **R4**: `_install_claude_sdk_instrumentor` calls `instrument(tracer_provider=provider)` explicitly
- [ ] **R5**: `hooks/lib/llm/__init__.py:10` no longer references `Instructor`
- [ ] **R7**: `hooks/lib/llm/claude.py` exists and re-exports `query`, `ClaudeSDKClient`, `ClaudeAgentOptions`, `ResultMessage`
- [ ] **R8**: ADR-016 has an "Operational notes" section covering `infra/` location + pinning policy + dual-import-path caveat
- [ ] `python3 tests/test_observability.py` → **10/10** (was 9/9; R1 added one assertion to `test_disabled_when_no_public_key`)
- [ ] `python3 hooks/test_requirements.py` → 1290/1290 (no regression)
- [ ] `python3 tests/test_schemas.py` → 20/20 (no regression)
- [ ] `python3 -c "from hooks.lib.llm import observability"` from a fresh shell never raises
- [ ] `python3 -c "from hooks.lib.llm.claude import query"` from a fresh shell never raises
- [ ] **I2 joint-suite invocation**: a single shell command sequence runs both suites:
       `python3 hooks/test_requirements.py && python3 tests/test_observability.py && python3 tests/test_schemas.py` exits 0

**Patch 3 — smoke + README:**
- [ ] Smoke spike imports from `hooks.lib.llm.claude`, not `claude_agent_sdk` (R7)
- [ ] With env vars set + Langfuse running, smoke spike produces a visible trace in UI
- [ ] With env vars unset, smoke spike completes without error and emits the disabled log line
- [ ] README "Local observability" section walks an unfamiliar reader through bootstrap end-to-end
- [ ] README references the joint-suite invocation in the "Verify the wiring" subsection

**Stack health:**
- [ ] `stg series` shows 3 new Step 11 patches on top of `v3-preserve-spike-artifacts` (+ the 2 design/plan doc patches already landed)
- [ ] Each patch's commit message references the R-numbered revisions it implements

## Rollback

```bash
stg pop                                              # smoke + docs
stg pop                                              # observability module
stg pop                                              # pyproject cleanup
docker compose -f infra/docker-compose.yml down -v   # full local Langfuse teardown
```

## Validated Commit Strategy

**Verdict: the 3-patch breakdown is correct. Do not split Patch 2.**

### Rationale

**Patch 1 — `step-11-pyproject-cleanup`** (Tasks 1–2): One file, one concern (dead extras removal). Already landed as `4fa65ff`. Correct.

**Patch 2 — `step-11-observability-module`** (Tasks 3–13): The concern about "11 tasks, ~150 LOC" conflates *authoring steps* with *commit content*. The 7 TDD red/green cycles are a *process*, not a commit boundary. What lands in the patch is a single logical artifact: a fully implemented, fully tested `observability.py` together with its runtime prerequisites (`infra/docker-compose.yml`, `.env.example`, `.gitignore` update).

Splitting this patch would produce either:
- a "failing tests" commit (tests without implementation), or
- an "untested code" commit (implementation without tests),

both of which break `git bisect` correctness and make code review harder. The infra files belong here too: they are the runtime dependency of the module being tested, and keeping them together makes the patch self-contained.

**Patch 3 — `step-11-smoke-and-docs`** (Tasks 14–17): Consumer-facing artifacts (smoke spike + README section) that make sense only once the module is complete. Docs-only commits bisect cleanly and do not inflate Patch 2.

### Boundary summary

| Patch | Concern | Files |
|-------|---------|-------|
| `step-11-pyproject-cleanup` | Remove dead `[llm]` extras (ADR-016 cleanup) | `pyproject.toml` |
| `step-11-observability-module` | Infra + module + dep-free unit tests (one atomic TDD artifact) | `infra/docker-compose.yml`, `infra/.env.example`, `.gitignore`, `hooks/lib/llm/observability.py`, `tests/test_observability.py` |
| `step-11-smoke-and-docs` | Runnable smoke spike + README walkthrough | `hooks/lib/llm/_spikes/v3_langfuse_smoke.py`, `README.md` |

---

## Preparatory Refactoring

> Analysis performed 2026-05-22 against branch `refactor/step-08-llm-package-scaffold`.

### Finding 1 — MINOR: stale `instructor` reference in `hooks/lib/llm/__init__.py`

**File:** `hooks/lib/llm/__init__.py:10`

The current docstring reads:

```python
    workers        — Instructor-wrapped subagent workers (Step 10+)
```

ADR-016 removed `instructor` from the V3 substrate. Patch 1 (`step-11-pyproject-cleanup`) already drops `instructor` from `pyproject.toml` — the matching one-liner docstring fix belongs in that same patch for consistency and to avoid misleading readers of the package docstring.

**Suggested change:**

```python
    workers        — Claude Agent SDK subagent workers (Step 10+)
```

**Severity:** Minor. One-liner, no tests needed, trivially verifiable. Fix in Patch 1 alongside the `pyproject.toml` cleanup.

---

### Finding 2 — NO ACTION: `tests/` has no `__init__.py`

`tests/test_schemas.py` already uses the `sys.path.insert(0, REPO_ROOT)` direct-invocation pattern. The plan's `tests/test_observability.py` follows the same convention. This works correctly as-is. Do not add `__init__.py` unless pytest integration is explicitly planned — it would be a premature abstraction given the established pattern.

---

### Finding 3 — NO ACTION: `fresh_observability_module()` design is correct

The plan's test helper pops `hooks.lib.llm.observability` from `sys.modules` to force a fresh module load per test. This is the right approach given the module-level `_initialized` flag and the bottom-of-module `init_observability()` auto-call. No preparation needed.

---

### Summary

**One genuine prep action:** fix the stale `instructor` reference in `hooks/lib/llm/__init__.py` as part of Patch 1. Everything else is in good shape for Step 11.

---

## Codex Architecture Analysis

> Analysis performed 2026-05-22 by Codex (gpt-5.5, xhigh reasoning) against branch `refactor/step-08-llm-package-scaffold`. Findings grounded in repo files plus PyPI/OpenInference source.

### HIGH findings (triage: address in Step 11 execution)

**HIGH-1: Import-name split can defeat `_initialized` idempotence**

`hooks/test_requirements.py` adds `hooks/lib` to `sys.path` and imports `llm.observability`. New `tests/test_observability.py` adds the repo root and imports `hooks.lib.llm.observability`. Same physical file, two different module identities, two independent `_initialized` flags in the same process.

*Practical impact today*: the two test files run in separate processes, so there is no current failure. But `test_llm_package_scaffold` (line 11069 of `hooks/test_requirements.py`) calls `importlib.import_module("llm.observability")` — if ever run in the same process as `tests/test_observability.py`, provider setup and log messages can fire twice.

*Mitigation during Step 11 execution*: keep the two test files running as separate scripts (the current pattern). Do not integrate them into a single pytest run. Document the dual-import-path issue in `hooks/lib/llm/__init__.py` with a comment for a future unification task.

**HIGH-2: Import-time auto-init permanently disables observability if env vars are absent at import**

`init_observability()` at module body level sets `_initialized = True` even when env vars are missing. Any process that imports `observability` before setting `LANGFUSE_*` env vars will silently disable observability for the rest of that process lifetime.

*Practical impact today*: the smoke script's intended workflow is "set env vars → run script", so the import fires after the env is set. The unit tests use `fresh_observability_module()` which pops-and-reloads, so they work correctly per-test. The risk is a future worker module that imports observability at module level before env vars are configured.

*Mitigation during Step 11 execution*: separate the "log once that we are disabled" flag from the "instrumentation is complete" flag. Use two module-level booleans: `_instrumented = False` (only True when OTel provider is actually installed) and `_disabled_logged = False` (True once the "disabled" message has been emitted). Do not set `_instrumented = True` on the missing-env-vars path. This means `init_observability()` will retry on the next call if env vars are later set, while still emitting the log only once.

**Note for executor**: Tasks 7 and 10 below assert `obs._initialized is True` after a missing-env call. If you adopt the two-flag approach, rename the module-level flag to `_instrumented` and update those tests to assert `obs._instrumented is False` (not instrumented) and `obs._disabled_logged is True` (log already emitted) for the disabled path. The semantic change is: `_initialized = True` meant "do not retry under any circumstances"; `_instrumented = False, _disabled_logged = True` means "do not re-log, but retry if env vars are set." Adopt whichever semantic fits the intended fail-open contract.

### MEDIUM findings (triage: fix where practical, document otherwise)

**MEDIUM-1: Availability probe is too narrow**

The probe `import openinference.instrumentation.claude_agent_sdk` only checks one of several required packages. `_install_instrumentor()` also needs `opentelemetry.exporter.otlp.proto.http.trace_exporter`. Let `_install_instrumentor()` raise `ImportError` directly (it will) and catch it explicitly alongside `Exception` so the install-hint message fires correctly regardless of which package is missing.

**MEDIUM-2: `ClaudeAgentSDKInstrumentor().instrument()` should receive `tracer_provider` explicitly**

The plan calls `instrument()` after `trace.set_tracer_provider(provider)`, relying on the global OTel state. The upstream OpenInference usage example passes `tracer_provider=provider` as a kwarg. Use the explicit form to avoid a fragile ordering dependency on `trace.set_tracer_provider()`.

In Task 13's `_install_instrumentor` body, change:
```python
trace.set_tracer_provider(provider)
ClaudeAgentSDKInstrumentor().instrument()
```
to:
```python
ClaudeAgentSDKInstrumentor().instrument(tracer_provider=provider)
```
and remove the `trace.set_tracer_provider(provider)` call entirely. The `from opentelemetry import trace` import in `_install_instrumentor` can then be dropped.

**MEDIUM-3: SDK-boundary traces may not fully resolve the 7x latency variance**

`ClaudeAgentSDKInstrumentor` creates AGENT-level spans for `query()` calls. Sub-spans for the SDK's internal Anthropic API calls (retries, `output_format` re-prompting) require Anthropic SDK instrumentation, which V3 does not use (ADR-016). Step 11 will show "this call took 375s" but may not distinguish internal SDK retries from Anthropic-side latency. This is a known scope limitation, not a bug.

**MEDIUM-4: `init_observability()` does too much orchestration**

Env-var reading, logging, availability probe, OTel provider construction, BatchSpanProcessor wiring, exporter construction, monkey-patch installation, and debug-mode error handling are six distinct responsibilities. The plan's `_install_instrumentor()` split is a good start. Add `_read_langfuse_config()` returning a config namedtuple-or-None to make env reading independently testable.

**MEDIUM-5: Import-order requirement is a fragile convention**

The smoke script comment "observability must be imported BEFORE claude_agent_sdk" is correct but fragile. A future worker module that does `from claude_agent_sdk import query` before importing observability will be untraced. The mitigations from HIGH-2 (not marking `_initialized` on missing-env path) partially address this by making re-init possible, but the ordering still matters for the `wrapt`-based monkey-patch. Document this constraint clearly in `hooks/lib/llm/__init__.py`. A future step could introduce a `hooks.lib.llm.claude` thin wrapper that encapsulates the ordering.

### LOW findings (triage: fix in Patch 1)

**LOW-1: Stale `Instructor-wrapped` wording in `hooks/lib/llm/__init__.py:10`**

Already identified in Preparatory Refactoring section above. Fix in Patch 1.

---

## Skills to reference during execution

- `requirements-framework:test-driven-development` — red/green/refactor discipline
- `requirements-framework:executing-plans` — task-by-task execution with checkpoints
- `requirements-framework:verification-before-completion` — final acceptance pass before commit
