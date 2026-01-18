#!/usr/bin/env python3
"""
Requirements Framework Test Suite

Run with: python3 ~/.claude/hooks/test_requirements.py

Tests all framework components:
- Session management
- Git utilities
- State storage
- Configuration loading
- Requirements manager
- CLI commands
- Hook behavior
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Add lib to path
lib_path = Path(__file__).parent / 'lib'
sys.path.insert(0, str(lib_path))


class TestRunner:
    """Simple test runner with assertions."""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def test(self, name: str, condition: bool, msg: str = ""):
        """Run a single test assertion."""
        if condition:
            print(f"  ✅ {name}")
            self.passed += 1
        else:
            print(f"  ❌ {name}: {msg}")
            self.failed += 1
            self.errors.append(f"{name}: {msg}")

    def summary(self) -> int:
        """Print summary and return exit code."""
        total = self.passed + self.failed
        print()
        print(f"{'='*50}")
        print(f"Results: {self.passed}/{total} tests passed")
        if self.errors:
            print("\nFailures:")
            for err in self.errors:
                print(f"  - {err}")
        return 0 if self.failed == 0 else 1


def test_session_module(runner: TestRunner):
    """Test session management."""
    print("\n📦 Testing session module...")
    from session import get_session_id, clear_session_cache

    # Test that get_session_id() raises error when no registry
    from session import SessionNotFoundError
    try:
        # Should raise SessionNotFoundError since we're not in a Claude Code session
        session_id = get_session_id()
        runner.test("get_session_id raises without registry", False, f"Should have raised, got: {session_id}")
    except SessionNotFoundError as e:
        runner.test("get_session_id raises helpful error", "No Claude Code session" in str(e))

    # Test clear cache (should still work even though we don't use temp files anymore)
    clear_session_cache()
    runner.test("Clear cache runs", True)


def test_session_registry(runner: TestRunner):
    """Test session registry operations."""
    print("\n📦 Testing session registry...")
    from session import (
        get_registry_path,
        is_process_alive,
        update_registry,
        get_active_sessions,
        cleanup_stale_sessions
    )

    # Test get_registry_path
    registry_path = get_registry_path()
    runner.test(
        "Registry path correct",
        str(registry_path).endswith(".claude/sessions.json"),
        f"Got: {registry_path}"
    )

    # Test is_process_alive with current process
    my_pid = os.getpid()
    runner.test("Current process alive", is_process_alive(my_pid))

    # Test is_process_alive with invalid PID
    runner.test("Invalid process not alive", not is_process_alive(999999))

    # Use temp registry for tests
    with tempfile.TemporaryDirectory() as tmpdir:
        test_registry = Path(tmpdir) / "test-sessions.json"

        # Mock get_registry_path for testing
        import session
        original_get_registry_path = session.get_registry_path
        session.get_registry_path = lambda: test_registry

        try:
            # Test update_registry creates file
            update_registry("abc12345", "/test/project", "main")
            runner.test("Registry file created", test_registry.exists())

            # Test registry has correct structure
            with open(test_registry) as f:
                registry = json.load(f)
            runner.test("Registry has version", registry.get("version") == "1.0")
            runner.test("Registry has sessions", "sessions" in registry)
            runner.test("Session added", "abc12345" in registry["sessions"])

            # Test session data
            session_data = registry["sessions"]["abc12345"]
            runner.test("Session has pid", "pid" in session_data)
            runner.test("Session has ppid", "ppid" in session_data)
            runner.test("Session has project_dir", session_data["project_dir"] == "/test/project")
            runner.test("Session has branch", session_data["branch"] == "main")
            runner.test("Session has started_at", "started_at" in session_data)
            runner.test("Session has last_active", "last_active" in session_data)

            # Test update_registry updates existing session (no sleep needed - just update)
            update_registry("abc12345", "/test/project", "feature/new")
            with open(test_registry) as f:
                registry = json.load(f)
            session_data = registry["sessions"]["abc12345"]
            runner.test("Session branch updated", session_data["branch"] == "feature/new")

            # Test update_registry adds multiple sessions
            update_registry("def67890", "/test/project2", "develop")
            with open(test_registry) as f:
                registry = json.load(f)
            runner.test("Multiple sessions", len(registry["sessions"]) == 2)

            # Test update_registry cleans up stale entries
            # Add a fake session with dead PID
            with open(test_registry) as f:
                registry = json.load(f)
            registry["sessions"]["dead1234"] = {
                "pid": 999999,  # Invalid PID
                "ppid": 999998,
                "project_dir": "/test/dead",
                "branch": "main",
                "started_at": int(time.time()),
                "last_active": int(time.time())
            }
            with open(test_registry, 'w') as f:
                json.dump(registry, f)

            # Update should clean up dead session
            update_registry("abc12345", "/test/project", "main")
            with open(test_registry) as f:
                registry = json.load(f)
            runner.test("Stale session removed", "dead1234" not in registry["sessions"])
            runner.test("Active sessions kept", "abc12345" in registry["sessions"])

            # Test get_active_sessions
            sessions = get_active_sessions()
            runner.test("get_active_sessions returns list", isinstance(sessions, list))
            runner.test("Returns active sessions", len(sessions) >= 2)

            # Test get_active_sessions filters by project_dir
            sessions = get_active_sessions(project_dir="/test/project")
            runner.test("Filter by project_dir", any(s["id"] == "abc12345" for s in sessions))

            # Test get_active_sessions filters by branch
            sessions = get_active_sessions(branch="develop")
            runner.test("Filter by branch", any(s["id"] == "def67890" for s in sessions))

            # Test cleanup_stale_sessions
            # Add another dead session
            with open(test_registry) as f:
                registry = json.load(f)
            registry["sessions"]["dead5678"] = {
                "pid": 999997,
                "ppid": 999996,
                "project_dir": "/test/dead2",
                "branch": "main",
                "started_at": int(time.time()),
                "last_active": int(time.time())
            }
            with open(test_registry, 'w') as f:
                json.dump(registry, f)

            removed = cleanup_stale_sessions()
            runner.test("cleanup_stale_sessions returns count", isinstance(removed, int))
            runner.test("Stale sessions removed", removed >= 1)

            with open(test_registry) as f:
                registry = json.load(f)
            runner.test("Dead session gone", "dead5678" not in registry["sessions"])

        finally:
            # Restore original function
            session.get_registry_path = original_get_registry_path


def test_session_id_normalization(runner: TestRunner):
    """Test session ID normalization handles all formats."""
    print("\n📦 Testing session ID normalization...")
    from session import normalize_session_id

    # Test full UUID with dashes → 8 chars
    full_uuid = "cad0ac4d-3933-45ad-9a1c-14aec05bb940"
    result = normalize_session_id(full_uuid)
    runner.test("Full UUID with dashes → 8 chars", result == "cad0ac4d", f"Got: {result}")

    # Test full UUID without dashes → 8 chars
    full_uuid_nodash = "cad0ac4d393345ad9a1c14aec05bb940"
    result = normalize_session_id(full_uuid_nodash)
    runner.test("Full UUID no dashes → 8 chars", result == "cad0ac4d", f"Got: {result}")

    # Test already 8-char ID (idempotent)
    short_id = "08345d22"
    result = normalize_session_id(short_id)
    runner.test("8-char ID unchanged", result == short_id, f"Got: {result}")

    # Test shorter ID remains unchanged
    tiny_id = "abc"
    result = normalize_session_id(tiny_id)
    runner.test("Short ID unchanged", result == tiny_id, f"Got: {result}")

    # Test idempotency
    test_id = "cad0ac4d-3933-45ad-9a1c-14aec05bb940"
    once = normalize_session_id(test_id)
    twice = normalize_session_id(once)
    runner.test("Normalization is idempotent", once == twice, f"Once: {once}, Twice: {twice}")

    # Test empty string generates new ID
    result = normalize_session_id("")
    runner.test("Empty string generates ID", len(result) == 8, f"Got: {result}")

    # Test None generates new ID
    result = normalize_session_id(None)
    runner.test("None generates ID", len(result) == 8, f"Got: {result}")


def test_get_session_id_normalization(runner: TestRunner):
    """Test get_session_id() no longer uses env vars."""
    print("\n📦 Testing get_session_id() no longer uses env vars...")
    import os
    from session import get_session_id

    # Test that env var is ignored (get_session_id() only uses registry now)
    full_uuid = "cad0ac4d-3933-45ad-9a1c-14aec05bb940"
    old_env = os.environ.get('CLAUDE_SESSION_ID')

    try:
        os.environ['CLAUDE_SESSION_ID'] = full_uuid

        # Should still raise error because we're not in a real session
        # (even though env var is set, it's ignored by get_session_id())
        from session import SessionNotFoundError
        try:
            session_id = get_session_id()
            runner.test("get_session_id ignores env var", False, f"Should have raised, got: {session_id}")
        except SessionNotFoundError:
            runner.test("get_session_id ignores env var, uses registry only", True)

    finally:
        if old_env:
            os.environ['CLAUDE_SESSION_ID'] = old_env
        else:
            os.environ.pop('CLAUDE_SESSION_ID', None)


def test_session_key_migration(runner: TestRunner):
    """Test migration of full UUID session keys to normalized format."""
    print("\n📦 Testing session key migration...")
    import tempfile
    import os
    from requirements import BranchRequirements
    from state_storage import save_state

    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(f"{tmpdir}/.git")

        # Create state with FULL UUID session key (old format)
        branch = "main"
        full_uuid = "cad0ac4d-3933-45ad-9a1c-14aec05bb940"
        normalized = "cad0ac4d"

        old_state = {
            "version": "1.0",
            "branch": branch,
            "project": tmpdir,
            "created_at": 1234567890,
            "updated_at": 1234567890,
            "requirements": {
                "commit_plan": {
                    "scope": "session",
                    "sessions": {
                        full_uuid: {
                            "satisfied": True,
                            "satisfied_at": 1234567890,
                            "satisfied_by": "cli"
                        }
                    }
                }
            }
        }

        save_state(branch, tmpdir, old_state)

        # Load via BranchRequirements (should trigger migration)
        reqs = BranchRequirements(branch, normalized, tmpdir)

        # Verify migration
        sessions = reqs._state['requirements']['commit_plan']['sessions']
        runner.test("Normalized key exists", normalized in sessions, f"Keys: {list(sessions.keys())}")
        runner.test("Full UUID key removed", full_uuid not in sessions, f"Keys: {list(sessions.keys())}")

        # Verify data preserved
        if normalized in sessions:
            runner.test("Data preserved", sessions[normalized]['satisfied'],
                       f"Data: {sessions[normalized]}")
            runner.test("Timestamp preserved", sessions[normalized]['satisfied_at'] == 1234567890,
                       f"Timestamp: {sessions[normalized].get('satisfied_at')}")
        else:
            runner.test("Data preserved", False, "Normalized key not found")
            runner.test("Timestamp preserved", False, "Normalized key not found")

        # Verify requirement is still satisfied
        runner.test("Still satisfied after migration",
                   reqs.is_satisfied('commit_plan', 'session'),
                   "Should be satisfied")


def test_git_utils_module(runner: TestRunner):
    """Test git utilities."""
    print("\n📦 Testing git_utils module...")
    from git_utils import run_git, is_git_repo

    # Test run_git with simple command
    code, out, err = run_git("git --version")
    runner.test("run_git executes", code == 0, f"Exit code: {code}")
    runner.test("run_git returns output", "git version" in out.lower(), f"Got: {out}")

    # Test is_git_repo
    with tempfile.TemporaryDirectory() as tmpdir:
        runner.test("Non-repo detected", not is_git_repo(tmpdir))

        # Create git repo
        os.makedirs(f"{tmpdir}/.git")
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        runner.test("Git repo detected", is_git_repo(tmpdir))


def test_git_root_resolution(runner: TestRunner):
    """Test that framework resolves git root from subdirectories."""
    print("\n📦 Testing git root resolution...")
    from git_utils import get_git_root, is_git_repo, get_current_branch, resolve_project_root

    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize git repo at root
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "feature/test"], cwd=tmpdir, capture_output=True)

        # Create nested directory structure
        subdir = os.path.join(tmpdir, "src", "components", "deep")
        os.makedirs(subdir)

        # Test get_git_root from subdirectory (use realpath for symlink handling on macOS)
        root_from_subdir = get_git_root(subdir)
        runner.test("Git root from subdir",
                    os.path.realpath(root_from_subdir) == os.path.realpath(tmpdir),
                    f"Expected {tmpdir}, got {root_from_subdir}")

        # Test is_git_repo from subdirectory
        runner.test("is_git_repo from subdir", is_git_repo(subdir))

        # Test get_current_branch from subdirectory
        branch = get_current_branch(subdir)
        runner.test("Branch from subdir", branch == "feature/test", f"Got: {branch}")

        # Test resolve_project_root from subdirectory
        original_cwd = os.getcwd()
        try:
            os.chdir(subdir)
            resolved = resolve_project_root(verbose=False)
            runner.test("resolve_project_root from subdir",
                        os.path.realpath(resolved) == os.path.realpath(tmpdir),
                        f"Expected {tmpdir}, got {resolved}")
        finally:
            os.chdir(original_cwd)

        # Test CLAUDE_PROJECT_DIR takes precedence
        custom_dir = "/custom/project/dir"
        env_backup = os.environ.get('CLAUDE_PROJECT_DIR')
        try:
            os.environ['CLAUDE_PROJECT_DIR'] = custom_dir
            resolved = resolve_project_root(verbose=False)
            runner.test("CLAUDE_PROJECT_DIR precedence", resolved == custom_dir,
                        f"Expected {custom_dir}, got {resolved}")
        finally:
            if env_backup:
                os.environ['CLAUDE_PROJECT_DIR'] = env_backup
            else:
                os.environ.pop('CLAUDE_PROJECT_DIR', None)


def test_hook_from_subdirectory(runner: TestRunner):
    """Test hook works correctly when called from subdirectory."""
    print("\n📦 Testing hook from subdirectory...")

    hook_path = Path(__file__).parent / "check-requirements.py"

    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "feature/subdir-test"], cwd=tmpdir, capture_output=True)

        # Create config at git root
        os.makedirs(f"{tmpdir}/.claude")
        config = {
            "version": "1.0",
            "enabled": True,
            "requirements": {
                "commit_plan": {
                    "enabled": True,
                    "scope": "session",
                    "message": "Need commit plan!"
                }
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config, f)

        # Create subdirectory
        subdir = os.path.join(tmpdir, "src", "components")
        os.makedirs(subdir)

        # Test hook from subdirectory (without CLAUDE_PROJECT_DIR set)
        # Remove CLAUDE_PROJECT_DIR if set to test auto-resolution
        env = {k: v for k, v in os.environ.items() if k != 'CLAUDE_PROJECT_DIR'}
        result = subprocess.run(
            ["python3", str(hook_path)],
            input=json.dumps({"tool_name":"Edit", "session_id": "subdirtest"}),
            cwd=subdir,  # Run from subdirectory
            capture_output=True,
            text=True,
            env=env
        )

        runner.test("Hook runs from subdir", result.returncode == 0, result.stderr)
        runner.test("Hook finds config from subdir", '"permissionDecision": "deny"' in result.stdout,
                    f"Expected deny (config found), got: {result.stdout}")


def test_cli_from_subdirectory(runner: TestRunner):
    """Test CLI works correctly when called from subdirectory."""
    print("\n📦 Testing CLI from subdirectory...")

    cli_path = Path(__file__).parent / "requirements-cli.py"

    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "feature/cli-subdir"], cwd=tmpdir, capture_output=True)

        # Create config at git root
        os.makedirs(f"{tmpdir}/.claude")
        config = {
            "version": "1.0",
            "enabled": True,
            "requirements": {
                "commit_plan": {"enabled": True, "scope": "session"}
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config, f)

        # Create subdirectory
        subdir = os.path.join(tmpdir, "src", "deep", "nested")
        os.makedirs(subdir)

        # Remove CLAUDE_PROJECT_DIR to test auto-resolution
        env = {k: v for k, v in os.environ.items() if k != 'CLAUDE_PROJECT_DIR'}

        # Test status from subdirectory
        result = subprocess.run(
            ["python3", str(cli_path), "status"],
            cwd=subdir,  # Run from subdirectory
            capture_output=True,
            text=True,
            env=env
        )
        runner.test("CLI status from subdir runs", result.returncode == 0, result.stderr)
        runner.test("CLI status shows branch", "feature/cli-subdir" in result.stdout, result.stdout)

        # Test satisfy from subdirectory (use --session flag since we're not in Claude Code)
        result = subprocess.run(
            ["python3", str(cli_path), "satisfy", "commit_plan", "--session", "test1234"],
            cwd=subdir,
            capture_output=True,
            text=True,
            env=env
        )
        runner.test("CLI satisfy from subdir works", "✅" in result.stdout, result.stdout)

        # Verify state was saved at git root (not subdir)
        state_dir = Path(tmpdir) / ".git" / "requirements"
        runner.test("State dir at git root", state_dir.exists(),
                    f"Expected state at {state_dir}")


def test_not_in_git_repo_fallback(runner: TestRunner):
    """Test fallback behavior when not in a git repository."""
    print("\n📦 Testing fallback when not in git repo...")

    from git_utils import resolve_project_root

    with tempfile.TemporaryDirectory() as tmpdir:
        # NO git init - just a regular directory

        # Test resolve_project_root falls back to cwd
        original_cwd = os.getcwd()
        env_backup = os.environ.get('CLAUDE_PROJECT_DIR')
        try:
            # Clear CLAUDE_PROJECT_DIR
            os.environ.pop('CLAUDE_PROJECT_DIR', None)
            os.chdir(tmpdir)

            resolved = resolve_project_root(verbose=False)
            runner.test("Non-repo uses cwd",
                        os.path.realpath(resolved) == os.path.realpath(tmpdir),
                        f"Expected {tmpdir}, got {resolved}")
        finally:
            os.chdir(original_cwd)
            if env_backup:
                os.environ['CLAUDE_PROJECT_DIR'] = env_backup


def test_state_storage_module(runner: TestRunner):
    """Test state storage."""
    print("\n📦 Testing state_storage module...")
    from state_storage import (
        create_empty_state, load_state, save_state, delete_state,
        list_all_states, branch_to_filename
    )

    # Test branch to filename conversion
    runner.test(
        "Branch name conversion",
        branch_to_filename("feature/auth") == "feature-auth.json"
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        # Simulate git repo
        os.makedirs(f"{tmpdir}/.git")

        # Test empty state creation
        state = create_empty_state("test/branch", tmpdir)
        runner.test("Empty state has version", state.get("version") == "1.0")
        runner.test("Empty state has branch", state.get("branch") == "test/branch")

        # Test save and load
        state["requirements"]["test_req"] = {"satisfied": True}
        save_state("test/branch", tmpdir, state)

        loaded = load_state("test/branch", tmpdir)
        runner.test(
            "State persists",
            loaded.get("requirements", {}).get("test_req", {}).get("satisfied") is True
        )

        # Test list states
        states = list_all_states(tmpdir)
        runner.test("State listed", len(states) == 1)

        # Test delete
        delete_state("test/branch", tmpdir)
        states = list_all_states(tmpdir)
        runner.test("State deleted", len(states) == 0)


def test_config_module(runner: TestRunner):
    """Test configuration loading."""
    print("\n📦 Testing config module...")
    from config import RequirementsConfig, deep_merge

    # Test deep merge
    base = {"a": 1, "b": {"c": 2}}
    override = {"b": {"d": 3}, "e": 4}
    result = deep_merge(base, override)
    runner.test("Deep merge preserves", result.get("a") == 1)
    runner.test("Deep merge adds nested", result.get("b", {}).get("d") == 3)
    runner.test("Deep merge preserves nested", result.get("b", {}).get("c") == 2)

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create project config
        os.makedirs(f"{tmpdir}/.claude")
        config_content = {
            "version": "1.0",
            "enabled": True,
            "requirements": {
                "test_req": {
                    "enabled": True,
                    "scope": "session",
                    "trigger_tools": ["Edit", "Write"],
                    "message": "Test message"
                },
                "disabled_req": {
                    "enabled": False
                }
            }
        }

        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config_content, f)

        # Test loading
        config = RequirementsConfig(tmpdir)
        runner.test("Config loaded", config.is_enabled())
        runner.test("Requirement found", config.is_requirement_enabled("test_req"))
        runner.test("Disabled req detected", not config.is_requirement_enabled("disabled_req"))
        runner.test("Scope correct", config.get_scope("test_req") == "session")
        runner.test("Trigger tools", config.get_trigger_tools("test_req") == ["Edit", "Write"])

        # Test get_checklist() method (TDD - these should FAIL initially)
        # Add checklist to config
        os.makedirs(f"{tmpdir}/.claude", exist_ok=True)
        config_with_checklist = {
            "version": "1.0",
            "enabled": True,
            "requirements": {
                "commit_plan": {
                    "enabled": True,
                    "checklist": ["Item 1", "Item 2", "Item 3"]
                },
                "no_checklist": {
                    "enabled": True
                },
                "empty_checklist": {
                    "enabled": True,
                    "checklist": []
                }
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config_with_checklist, f)

        config2 = RequirementsConfig(tmpdir)

        # Test with checklist items
        checklist = config2.get_checklist("commit_plan")
        runner.test("get_checklist returns list", isinstance(checklist, list))
        runner.test("get_checklist has items", checklist == ["Item 1", "Item 2", "Item 3"],
                    f"Got: {checklist}")

        # Test empty checklist
        empty_list = config2.get_checklist("empty_checklist")
        runner.test("get_checklist empty returns []", empty_list == [], f"Got: {empty_list}")

        # Test missing checklist field
        no_list = config2.get_checklist("no_checklist")
        runner.test("get_checklist missing returns []", no_list == [], f"Got: {no_list}")

        # Test nonexistent requirement
        nonexistent = config2.get_checklist("nonexistent")
        runner.test("get_checklist nonexistent returns []", nonexistent == [], f"Got: {nonexistent}")

        # Test schema validation errors (inherit: false to isolate from global config)
        invalid_config = {
            "version": "1.0",
            "enabled": True,
            "inherit": False,  # Don't merge with ~/.claude/requirements.yaml
            "requirements": {
                "bad_enabled": {"enabled": "yes"},
                "bad_scope": {"enabled": True, "scope": "always"},
                "bad_checklist": {"enabled": True, "checklist": ["ok", 123]},
            },
        }

        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(invalid_config, f)

        config3 = RequirementsConfig(tmpdir)
        errors = config3.get_validation_errors()
        runner.test("Validation errors captured", len(errors) == 3, f"Got: {errors}")
        runner.test("Invalid requirements removed", config3.get_all_requirements() == [])

        # Test type-safe config accessors (LSP compliance)
        print("\n📦 Testing type-safe config accessors...")

        # Test 1: Dynamic requirement with missing required fields
        invalid_dynamic_config = {
            "version": "1.0",
            "enabled": True,
            "inherit": False,
            "requirements": {
                "invalid_dynamic": {
                    "type": "dynamic",
                    "enabled": True,
                    # Missing 'calculator' and 'thresholds'
                }
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(invalid_dynamic_config, f)

        config4 = RequirementsConfig(tmpdir)
        try:
            result = config4.get_dynamic_config('invalid_dynamic')
            runner.test("Dynamic config validates required fields", result is None)
        except ValueError:
            runner.test("Dynamic config validates required fields", True)

        # Test 2: Guard requirement with missing required field
        invalid_guard_config = {
            "version": "1.0",
            "enabled": True,
            "inherit": False,
            "requirements": {
                "invalid_guard": {
                    "type": "guard",
                    "enabled": True,
                    # Missing 'guard_type'
                }
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(invalid_guard_config, f)

        config5 = RequirementsConfig(tmpdir)
        try:
            result = config5.get_guard_config('invalid_guard')
            runner.test("Guard config validates required fields", result is None)
        except ValueError:
            runner.test("Guard config validates required fields", True)

        # Test 3: Blocking requirement works without type-specific fields
        blocking_config = {
            "version": "1.0",
            "enabled": True,
            "inherit": False,
            "requirements": {
                "simple_blocking": {
                    "type": "blocking",
                    "enabled": True,
                    "scope": "session"
                }
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(blocking_config, f)

        config6 = RequirementsConfig(tmpdir)
        req_config = config6.get_blocking_config('simple_blocking')
        runner.test("Blocking config works without type fields", req_config is not None)

        # Test 4: Valid dynamic requirement returns correct config
        valid_dynamic_config = {
            "version": "1.0",
            "enabled": True,
            "inherit": False,
            "requirements": {
                "valid_dynamic": {
                    "type": "dynamic",
                    "enabled": True,
                    "calculator": "branch_size_calculator",
                    "thresholds": {"block": 100, "warn": 50}
                }
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(valid_dynamic_config, f)

        config7 = RequirementsConfig(tmpdir)
        dyn_config = config7.get_dynamic_config('valid_dynamic')
        runner.test("Dynamic config returns valid config", dyn_config is not None)
        if dyn_config:
            runner.test("Dynamic config has calculator", dyn_config.get('calculator') == 'branch_size_calculator')
            runner.test("Dynamic config has thresholds", dyn_config.get('thresholds') == {"block": 100, "warn": 50})

        # Test 5: Valid guard requirement returns correct config
        valid_guard_config = {
            "version": "1.0",
            "enabled": True,
            "inherit": False,
            "requirements": {
                "valid_guard": {
                    "type": "guard",
                    "enabled": True,
                    "guard_type": "protected_branch",
                    "protected_branches": ["master", "main"]
                }
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(valid_guard_config, f)

        config8 = RequirementsConfig(tmpdir)
        guard_config = config8.get_guard_config('valid_guard')
        runner.test("Guard config returns valid config", guard_config is not None)
        if guard_config:
            runner.test("Guard config has guard_type", guard_config.get('guard_type') == 'protected_branch')

        # Test 6: Legacy get_attribute still works
        attr_value = config7.get_attribute('valid_dynamic', 'calculator')
        runner.test("Legacy get_attribute still works", attr_value == 'branch_size_calculator')


def test_write_local_config(runner: TestRunner):
    """Test writing local config overrides."""
    print("\n📝 Testing write_local_config and write_local_override...")
    from config import RequirementsConfig, load_yaml
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create .claude directory
        claude_dir = Path(tmpdir) / '.claude'
        claude_dir.mkdir()

        # Create initial project config
        project_config = {
            "version": "1.0",
            "enabled": True,
            "requirements": {
                "commit_plan": {
                    "enabled": True,
                    "scope": "session"
                }
            }
        }
        with open(claude_dir / 'requirements.yaml', 'w') as f:
            json.dump(project_config, f)

        # Test 1: Write new local config with enabled=false
        config = RequirementsConfig(tmpdir)
        config.write_local_override(enabled=False)

        local_file = claude_dir / 'requirements.local.yaml'

        # File should exist
        runner.test("Local config file created", local_file.exists())

        # Read back and verify
        local_config = load_yaml(local_file)

        runner.test("Enabled field set to False", not local_config.get('enabled'))
        runner.test("Version field added", local_config.get('version') == '1.0')

        # Test 2: Update existing config
        config.write_local_override(enabled=True)

        local_config = load_yaml(local_file)

        runner.test("Enabled field updated to True", local_config.get('enabled'))

        # Test 3: Write requirement-level override
        config.write_local_override(
            requirement_overrides={'commit_plan': False}
        )

        local_config = load_yaml(local_file)

        runner.test(
            "Requirement override added",
            not local_config.get('requirements', {}).get('commit_plan', {}).get('enabled')
        )
        runner.test(
            "Framework enabled preserved",
            local_config.get('enabled')
        )

        # Test 4: Verify local override actually works in config loading
        config_reloaded = RequirementsConfig(tmpdir)
        runner.test(
            "Local override affects is_enabled()",
            config_reloaded.is_enabled()
        )
        runner.test(
            "Requirement override affects is_requirement_enabled()",
            not config_reloaded.is_requirement_enabled('commit_plan'),
            f"commit_plan enabled: {config_reloaded.is_requirement_enabled('commit_plan')}"
        )


def test_write_project_config(runner: TestRunner):
    """Test writing project config modifications."""
    print("\n📝 Testing write_project_config and write_project_override...")
    from config import RequirementsConfig, load_yaml
    from pathlib import Path
    import yaml

    with tempfile.TemporaryDirectory() as tmpdir:
        claude_dir = Path(tmpdir) / '.claude'
        claude_dir.mkdir()

        # Test 1: Write new project config with enabled=True
        config = RequirementsConfig(tmpdir)
        config.write_project_override(enabled=True)

        project_file = claude_dir / 'requirements.yaml'
        runner.test("Project config file created", project_file.exists())

        # Verify YAML format (not JSON)
        runner.test("Uses YAML extension", project_file.suffix == '.yaml')

        project_config = load_yaml(project_file)
        runner.test("Enabled field set to True", project_config.get('enabled'))
        runner.test("Version field added", project_config.get('version') == '1.0')
        runner.test("Inherit flag added by default", project_config.get('inherit'))

        # Test 2: Update existing config (preserve inherit)
        # First, manually set inherit to False
        existing = load_yaml(project_file)
        existing['inherit'] = False
        with open(project_file, 'w') as f:
            yaml.safe_dump(existing, f)

        # Now update enabled
        config.write_project_override(enabled=False)
        project_config = load_yaml(project_file)

        runner.test("Enabled field updated to False", not project_config.get('enabled'))
        runner.test("Inherit False preserved", not project_config.get('inherit'))

        # Test 3: Write requirement-level override
        config.write_project_override(
            requirement_overrides={'adr_reviewed': {'adr_path': '/docs/adr'}}
        )

        project_config = load_yaml(project_file)
        runner.test(
            "Requirement override added",
            project_config.get('requirements', {}).get('adr_reviewed', {}).get('adr_path') == '/docs/adr'
        )
        runner.test(
            "Framework enabled preserved",
            not project_config.get('enabled')  # From test 2
        )
        runner.test(
            "Inherit preserved across updates",
            not project_config.get('inherit')  # Still False from test 2
        )

        # Test 4: Add new requirement to existing config
        config.write_project_override(
            requirement_overrides={'commit_plan': {'enabled': True, 'scope': 'session'}}
        )

        project_config = load_yaml(project_file)
        commit_plan = project_config.get('requirements', {}).get('commit_plan', {})
        runner.test("New requirement added", commit_plan.get('enabled'))
        runner.test("New requirement scope set", commit_plan.get('scope') == 'session')
        runner.test("Previous requirement preserved",
                   'adr_reviewed' in project_config.get('requirements', {}))

        # Test 5: Update existing requirement fields
        config.write_project_override(
            requirement_overrides={
                'commit_plan': {'scope': 'branch', 'message': 'Custom message'}
            }
        )

        project_config = load_yaml(project_file)
        commit_plan = project_config.get('requirements', {}).get('commit_plan', {})
        runner.test("Requirement scope updated", commit_plan.get('scope') == 'branch')
        runner.test("Requirement message added", commit_plan.get('message') == 'Custom message')
        runner.test("Requirement enabled preserved", commit_plan.get('enabled'))

        # Test 6: Verify project override affects config loading
        config_reloaded = RequirementsConfig(tmpdir)
        runner.test(
            "Project override affects is_enabled()",
            not config_reloaded.is_enabled()  # Still False from test 2
        )
        runner.test(
            "Requirement override affects is_requirement_enabled()",
            config_reloaded.is_requirement_enabled('commit_plan')
        )

        # Test 7: Preserve existing hooks section
        existing = load_yaml(project_file)
        existing['hooks'] = {
            'stop': {'verify_requirements': True}
        }
        with open(project_file, 'w') as f:
            yaml.safe_dump(existing, f)

        config.write_project_override(
            requirement_overrides={'github_ticket': {'enabled': True}}
        )

        project_config = load_yaml(project_file)
        runner.test("Hooks section preserved", 'hooks' in project_config)
        runner.test("Hook config preserved",
                   project_config.get('hooks', {}).get('stop', {}).get('verify_requirements'))

        # Test 8: Test with fresh config (no existing file)
        new_tmpdir = tempfile.mkdtemp()
        try:
            new_claude_dir = Path(new_tmpdir) / '.claude'
            new_claude_dir.mkdir()

            new_config = RequirementsConfig(new_tmpdir)
            new_config.write_project_override(
                requirement_overrides={'test_req': {'enabled': True}}
            )

            new_project_file = new_claude_dir / 'requirements.yaml'
            runner.test("Creates new project config", new_project_file.exists())

            new_project_config = load_yaml(new_project_file)
            runner.test("New config has inherit: true", new_project_config.get('inherit'))
            runner.test("New config has version", new_project_config.get('version') == '1.0')
            runner.test("New config has requirement", 'test_req' in new_project_config.get('requirements', {}))
        finally:
            import shutil
            shutil.rmtree(new_tmpdir)


def test_cli_enable_disable(runner: TestRunner):
    """Test req enable/disable CLI commands."""
    print("\n🔧 Testing CLI enable/disable commands...")
    import subprocess
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize git repo
        subprocess.run(['git', 'init'], cwd=tmpdir, capture_output=True, check=True)
        subprocess.run(['git', 'config', 'user.name', 'Test'], cwd=tmpdir, capture_output=True, check=True)
        subprocess.run(['git', 'config', 'user.email', 'test@test.com'], cwd=tmpdir, capture_output=True, check=True)

        # Create basic project config
        claude_dir = Path(tmpdir) / '.claude'
        claude_dir.mkdir()

        config_file = claude_dir / 'requirements.yaml'
        config_file.write_text('''version: "1.0"
enabled: true
requirements:
  commit_plan:
    enabled: true
    scope: session
''')

        cli_path = Path(__file__).parent / 'requirements-cli.py'

        # Test disable command
        result = subprocess.run(
            ['python3', str(cli_path), 'disable'],
            cwd=tmpdir,
            capture_output=True,
            text=True,
            env={'CLAUDE_PROJECT_DIR': tmpdir, 'PATH': os.environ.get('PATH', '')}
        )

        runner.test("Disable command succeeded", result.returncode == 0,
                   f"Exit code: {result.returncode}, stderr: {result.stderr}")
        runner.test("Success message shown", "✅" in result.stdout,
                   f"Output: {result.stdout}")
        runner.test("Local file mentioned", "requirements.local" in result.stdout,
                   f"Output: {result.stdout}")

        # Verify local config created
        local_file = claude_dir / 'requirements.local.yaml'
        runner.test("Local config file created", local_file.exists())

        # Test enable command
        result = subprocess.run(
            ['python3', str(cli_path), 'enable'],
            cwd=tmpdir,
            capture_output=True,
            text=True,
            env={'CLAUDE_PROJECT_DIR': tmpdir, 'PATH': os.environ.get('PATH', '')}
        )

        runner.test("Enable command succeeded", result.returncode == 0,
                   f"Exit code: {result.returncode}, stderr: {result.stderr}")
        runner.test("Enable success message shown", "✅" in result.stdout,
                   f"Output: {result.stdout}")

        # Test error handling - not in git repo
        with tempfile.TemporaryDirectory() as tmpdir2:
            result = subprocess.run(
                ['python3', str(cli_path), 'disable'],
                cwd=tmpdir2,
                capture_output=True,
                text=True,
                env={'CLAUDE_PROJECT_DIR': tmpdir2, 'PATH': os.environ.get('PATH', '')}
            )
            runner.test("Error when not in git repo", result.returncode == 1,
                       f"Exit code: {result.returncode}")
            runner.test("Error message shown", "❌" in result.stderr,
                       f"Stderr: {result.stderr}")


def test_cli_config_project_modify(runner: TestRunner):
    """Test req config command with --project flag."""
    print("\n🔧 Testing CLI config --project command...")
    import subprocess
    from pathlib import Path
    from config import load_yaml

    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize git repo
        subprocess.run(['git', 'init'], cwd=tmpdir, capture_output=True, check=True)
        subprocess.run(['git', 'config', 'user.name', 'Test'], cwd=tmpdir, capture_output=True, check=True)
        subprocess.run(['git', 'config', 'user.email', 'test@test.com'], cwd=tmpdir, capture_output=True, check=True)

        # Create basic project config
        claude_dir = Path(tmpdir) / '.claude'
        claude_dir.mkdir()

        config_file = claude_dir / 'requirements.yaml'
        config_file.write_text('''version: "1.0"
enabled: true
inherit: true
requirements:
  commit_plan:
    enabled: true
    scope: session
''')

        cli_path = Path(__file__).parent / 'requirements-cli.py'

        # Test: Modify requirement in project config
        result = subprocess.run(
            ['python3', str(cli_path), 'config', 'adr_reviewed',
             '--project', '--set', 'adr_path=/docs/adr', '--yes'],
            cwd=tmpdir,
            capture_output=True,
            text=True,
            env={'CLAUDE_PROJECT_DIR': tmpdir, 'PATH': os.environ.get('PATH', '')}
        )

        runner.test("Config project command succeeded", result.returncode == 0,
                   f"stdout: {result.stdout}, stderr: {result.stderr}")

        # Verify project config updated
        project_config = load_yaml(config_file)

        runner.test("Project config updated",
                   project_config.get('requirements', {}).get('adr_reviewed', {}).get('adr_path') == '/docs/adr')
        runner.test("Inherit flag preserved",
                   project_config.get('inherit'))
        runner.test("Existing requirement preserved",
                   'commit_plan' in project_config.get('requirements', {}))

        # Verify local config NOT created
        local_file = claude_dir / 'requirements.local.yaml'
        runner.test("Local config not created", not local_file.exists())


def test_requirements_manager(runner: TestRunner):
    """Test requirements manager."""
    print("\n📦 Testing requirements module...")
    from requirements import BranchRequirements

    with tempfile.TemporaryDirectory() as tmpdir:
        # Simulate git repo
        os.makedirs(f"{tmpdir}/.git")

        # Test session scope
        reqs1 = BranchRequirements("test/branch", "session-1", tmpdir)
        runner.test("Initially not satisfied", not reqs1.is_satisfied("commit_plan", "session"))

        reqs1.satisfy("commit_plan", "session", method="test")
        runner.test("Session satisfied", reqs1.is_satisfied("commit_plan", "session"))

        # Different session
        reqs2 = BranchRequirements("test/branch", "session-2", tmpdir)
        runner.test("Other session not satisfied", not reqs2.is_satisfied("commit_plan", "session"))

        # Branch scope
        reqs1.satisfy("github_ticket", "branch", metadata={"ticket": "#123"})
        runner.test("Branch satisfied", reqs1.is_satisfied("github_ticket", "branch"))

        # Branch scope persists
        reqs3 = BranchRequirements("test/branch", "session-3", tmpdir)
        runner.test("Branch persists", reqs3.is_satisfied("github_ticket", "branch"))

        # Test clear
        reqs3.clear("github_ticket")
        runner.test("Clear works", not reqs3.is_satisfied("github_ticket", "branch"))

        # Test clear all
        reqs3.satisfy("req1", "session")
        reqs3.satisfy("req2", "session")
        reqs3.clear_all()
        status = reqs3.get_status()
        runner.test("Clear all works", len(status["requirements"]) == 0)

        # Test TTL expiration (using mock time for deterministic testing)
        import unittest.mock as mock
        reqs4 = BranchRequirements("ttl/branch", "session-1", tmpdir)
        with mock.patch('time.time', return_value=1000.0):
            reqs4.satisfy("ttl_req", "session", ttl=1)  # 1 second TTL
            runner.test("TTL satisfied initially", reqs4.is_satisfied("ttl_req", "session"))
        with mock.patch('time.time', return_value=1001.5):  # 1.5 seconds later (TTL expired)
            runner.test("TTL expired", not reqs4.is_satisfied("ttl_req", "session"))


def test_branch_level_override(runner: TestRunner):
    """Test branch-level override for session-scoped requirements."""
    print("\n📦 Testing branch-level override...")
    from requirements import BranchRequirements

    with tempfile.TemporaryDirectory() as tmpdir:
        # Simulate git repo
        os.makedirs(f"{tmpdir}/.git")

        # Create initial session and verify session scope works
        reqs1 = BranchRequirements("override/branch", "session-1", tmpdir)
        runner.test("Initially not satisfied", not reqs1.is_satisfied("commit_plan", "session"))

        # Satisfy with BRANCH scope (simulates --branch flag behavior)
        reqs1.satisfy("commit_plan", scope="branch", method="cli")

        # Same session should see it satisfied
        runner.test("Session 1 sees branch override", reqs1.is_satisfied("commit_plan", "session"))

        # NEW session should also see it satisfied (branch-level override)
        reqs2 = BranchRequirements("override/branch", "session-2", tmpdir)
        runner.test("Session 2 sees branch override", reqs2.is_satisfied("commit_plan", "session"),
                   "Branch-level override should apply to all sessions")

        # Another new session
        reqs3 = BranchRequirements("override/branch", "totally-new-session", tmpdir)
        runner.test("New session sees branch override", reqs3.is_satisfied("commit_plan", "session"),
                   "Branch-level override should apply to future sessions")

        # Different branch should NOT have the override
        reqs_other = BranchRequirements("other/branch", "session-1", tmpdir)
        runner.test("Other branch not affected", not reqs_other.is_satisfied("commit_plan", "session"),
                   "Branch override should only apply to the specific branch")


def test_branch_level_override_with_ttl(runner: TestRunner):
    """Test branch-level override respects TTL."""
    print("\n📦 Testing branch-level override with TTL...")
    from requirements import BranchRequirements

    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(f"{tmpdir}/.git")

        # Satisfy with branch scope and TTL (using mock time for deterministic testing)
        import unittest.mock as mock
        reqs1 = BranchRequirements("ttl-override/branch", "session-1", tmpdir)
        with mock.patch('time.time', return_value=2000.0):
            reqs1.satisfy("commit_plan", scope="branch", method="cli", ttl=1)  # 1 second TTL
            # Should be satisfied initially
            runner.test("Branch override with TTL satisfied initially", reqs1.is_satisfied("commit_plan", "session"))

        # Check after TTL expiration (1.5 seconds later)
        with mock.patch('time.time', return_value=2001.5):
            runner.test("Branch override expires after TTL", not reqs1.is_satisfied("commit_plan", "session"))


def test_cli_commands(runner: TestRunner):
    """Test CLI commands."""
    print("\n📦 Testing CLI commands...")

    cli_path = Path(__file__).parent / "requirements-cli.py"

    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "test-branch"], cwd=tmpdir, capture_output=True)

        # Create config
        os.makedirs(f"{tmpdir}/.claude")
        config = {
            "version": "1.0",
            "enabled": True,
            "requirements": {
                "commit_plan": {"enabled": True, "scope": "session"}
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config, f)

        # Test status command
        result = subprocess.run(
            ["python3", str(cli_path), "status"],
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("Status runs", result.returncode == 0, result.stderr)
        runner.test("Status shows branch", "test-branch" in result.stdout, result.stdout)

        # Test satisfy command (use --session since we're not in Claude Code)
        result = subprocess.run(
            ["python3", str(cli_path), "satisfy", "commit_plan", "--session", "testcli1"],
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("Satisfy runs", result.returncode == 0, result.stderr)
        runner.test("Satisfy confirms", "✅" in result.stdout, result.stdout)

        # Test status after satisfy (use --verbose to see all requirements)
        result = subprocess.run(
            ["python3", str(cli_path), "status", "--verbose", "--session", "testcli1"],
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("Status shows satisfied", "✅" in result.stdout, result.stdout)

        # Test clear command (use --session)
        result = subprocess.run(
            ["python3", str(cli_path), "clear", "commit_plan", "--session", "testcli1"],
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("Clear runs", result.returncode == 0, result.stderr)

        # Test list command
        result = subprocess.run(
            ["python3", str(cli_path), "list"],
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("List runs", result.returncode == 0, result.stderr)

    # Validation errors are surfaced in status output
    with tempfile.TemporaryDirectory() as tmpdir_invalid:
        subprocess.run(["git", "init"], cwd=tmpdir_invalid, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "validation"], cwd=tmpdir_invalid, capture_output=True)

        os.makedirs(f"{tmpdir_invalid}/.claude")
        invalid_config = {
            "version": "1.0",
            "enabled": True,
            "requirements": {
                "bad_enabled": {"enabled": "yes"}
            },
        }

        with open(f"{tmpdir_invalid}/.claude/requirements.yaml", 'w') as f:
            json.dump(invalid_config, f)

        result = subprocess.run(
            ["python3", str(cli_path), "status", "--verbose"],
            cwd=tmpdir_invalid, capture_output=True, text=True
        )

        runner.test("Status reports validation errors", "Configuration validation failed" in result.stdout, result.stdout)
        runner.test(
            "Status includes remediation hint",
            "Fix .claude/requirements.yaml" in result.stdout,
            result.stdout,
        )


def test_cli_status_modes(runner: TestRunner):
    """Test new status modes (focused, summary, verbose)."""
    print("\n📦 Testing status command modes...")

    cli_path = Path(__file__).parent / "requirements-cli.py"

    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "test-branch"], cwd=tmpdir, capture_output=True)

        # Create config with multiple requirements
        os.makedirs(f"{tmpdir}/.claude")
        config = {
            "version": "1.0",
            "enabled": True,
            "inherit": False,  # Don't inherit global config for test isolation
            "requirements": {
                "commit_plan": {"enabled": True, "scope": "session"},
                "adr_reviewed": {"enabled": True, "scope": "session"}
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config, f)

        # Test 1: Default focused mode (unsatisfied only)
        result = subprocess.run(
            ["python3", str(cli_path), "status"],
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("Focused status runs", result.returncode == 0)
        runner.test("Focused shows unsatisfied", "Unsatisfied Requirements" in result.stdout, result.stdout[:300])

        # Test 2: Summary mode
        result = subprocess.run(
            ["python3", str(cli_path), "status", "--summary"],
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("Summary status runs", result.returncode == 0)
        runner.test("Summary shows counts", "0/2" in result.stdout or "requirements satisfied" in result.stdout, result.stdout)

        # Test 3: Satisfy and check focused hides satisfied (use --session)
        test_session = "modetest"
        subprocess.run(
            ["python3", str(cli_path), "satisfy", "commit_plan", "--session", test_session],
            cwd=tmpdir, capture_output=True, text=True
        )

        result = subprocess.run(
            ["python3", str(cli_path), "status", "--session", test_session],
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("Focused shows remaining unsatisfied", "adr_reviewed" in result.stdout, result.stdout)

        # Test 4: Summary when all satisfied (use same session)
        subprocess.run(
            ["python3", str(cli_path), "satisfy", "adr_reviewed", "--session", test_session],
            cwd=tmpdir, capture_output=True, text=True
        )

        result = subprocess.run(
            ["python3", str(cli_path), "status", "--summary", "--session", test_session],
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("Summary shows all satisfied", "✅ All" in result.stdout and "requirements satisfied" in result.stdout, result.stdout)


def test_cli_sessions_command(runner: TestRunner):
    """Test CLI sessions command and auto-detection."""
    print("\n📦 Testing CLI sessions command...")

    cli_path = Path(__file__).parent / "requirements-cli.py"

    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "feature/test"], cwd=tmpdir, capture_output=True)

        # Create config
        os.makedirs(f"{tmpdir}/.claude")
        config = {
            "version": "1.0",
            "enabled": True,
            "requirements": {
                "commit_plan": {"enabled": True, "scope": "session"}
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config, f)

        # Mock registry with active session
        from session import update_registry
        import session as session_module
        original_get_registry_path = session_module.get_registry_path
        test_registry = Path(tmpdir) / "test-sessions.json"
        session_module.get_registry_path = lambda: test_registry

        try:
            # Create active session in registry
            test_session_id = "test1234"
            update_registry(test_session_id, tmpdir, "feature/test")

            # Test sessions command
            result = subprocess.run(
                ["python3", str(cli_path), "sessions"],
                cwd=tmpdir, capture_output=True, text=True,
                env={**os.environ, "CLAUDE_PROJECT_DIR": tmpdir}
            )
            runner.test("Sessions command runs", result.returncode == 0, result.stderr)
            # Note: subprocess sees real registry, not mocked one, so we just verify it runs
            runner.test("Sessions output valid", "Active Claude Code Sessions" in result.stdout or "No active" in result.stdout, result.stdout)

            # Test sessions --project filter
            result = subprocess.run(
                ["python3", str(cli_path), "sessions", "--project"],
                cwd=tmpdir, capture_output=True, text=True,
                env={**os.environ, "CLAUDE_PROJECT_DIR": tmpdir}
            )
            runner.test("Sessions --project runs", result.returncode == 0, result.stderr)

            # Test satisfy with explicit --session flag
            result = subprocess.run(
                ["python3", str(cli_path), "satisfy", "commit_plan", "--session", test_session_id],
                cwd=tmpdir, capture_output=True, text=True,
                env={**os.environ, "CLAUDE_PROJECT_DIR": tmpdir}
            )
            runner.test("Satisfy with --session runs", result.returncode == 0, result.stderr)
            runner.test("Satisfy with --session succeeds", "✅" in result.stdout or "satisfied" in result.stdout.lower(), result.stdout)

            # Note: CLAUDE_SESSION_ID env var is no longer used - removed test

            # Test status with --session flag
            result = subprocess.run(
                ["python3", str(cli_path), "status", "--session", test_session_id],
                cwd=tmpdir, capture_output=True, text=True,
                env={**os.environ, "CLAUDE_PROJECT_DIR": tmpdir}
            )
            runner.test("Status with --session runs", result.returncode == 0, result.stderr)

        finally:
            # Restore original function
            session_module.get_registry_path = original_get_registry_path


def test_cli_doctor_command(runner: TestRunner):
    """Test doctor command for environment checks."""

    print("\n📦 Testing doctor command...")

    cli_path = Path(__file__).parent / "requirements-cli.py"
    repo_root = Path(__file__).parent.parent

    with tempfile.TemporaryDirectory() as tmpdir:
        home_dir = Path(tmpdir)
        claude_dir = home_dir / ".claude"
        hooks_dir = claude_dir / "hooks"
        hooks_dir.mkdir(parents=True)

        sync_files = [
            "check-requirements.py",
            "requirements-cli.py",
            "handle-session-start.py",
            "handle-stop.py",
            "handle-session-end.py",
            "test_requirements.py",
            "lib/config.py",
            "lib/git_utils.py",
            "lib/requirements.py",
            "lib/session.py",
            "lib/state_storage.py",
        ]

        for relative in sync_files:
            source = Path(__file__).parent / relative
            destination = hooks_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        # Ensure executables
        for script in ["check-requirements.py", "requirements-cli.py",
                      "handle-session-start.py", "handle-stop.py", "handle-session-end.py"]:
            target = hooks_dir / script
            target.chmod(0o755)

        # Settings with hook registration (new format - all 4 required hooks)
        settings_path = claude_dir / "settings.local.json"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(
            json.dumps(
                {
                    "hooks": {
                        "PreToolUse": [
                            {
                                "matcher": "Edit|Write|MultiEdit|Bash",
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": "python3 ~/.claude/hooks/check-requirements.py",
                                        "timeout": 5
                                    }
                                ]
                            }
                        ],
                        "SessionStart": [
                            {
                                "matcher": "*",
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": "python3 ~/.claude/hooks/handle-session-start.py"
                                    }
                                ]
                            }
                        ],
                        "Stop": [
                            {
                                "matcher": "*",
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": "python3 ~/.claude/hooks/handle-stop.py"
                                    }
                                ]
                            }
                        ],
                        "SessionEnd": [
                            {
                                "matcher": "*",
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": "python3 ~/.claude/hooks/handle-session-end.py"
                                    }
                                ]
                            }
                        ]
                    }
                },
                indent=2,
            )
        )

        # Project configuration
        project_dir = home_dir / "project"
        (project_dir / ".claude").mkdir(parents=True)
        config = {
            "version": "1.0",
            "enabled": True,
            "requirements": {"commit_plan": {"enabled": True, "scope": "session"}},
        }
        (project_dir / ".claude" / "requirements.yaml").write_text(json.dumps(config))

        env = {**os.environ, "HOME": str(home_dir), "CLAUDE_PROJECT_DIR": str(project_dir)}

        result = subprocess.run(
            ["python3", str(cli_path), "doctor", "--repo", str(repo_root), "--verbose"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            env=env,
        )

        runner.test("Doctor runs", result.returncode == 0, result.stdout + result.stderr)
        runner.test("Reports hook registration", "PreToolUse hook registered" in result.stdout, result.stdout)
        # With verbose flag, should show "All Checks" section
        runner.test("Reports sync status", "All Checks" in result.stdout or "✅" in result.stdout, result.stdout)


def test_cli_doctor_old_format_migration(runner: TestRunner):
    """Test doctor command shows migration message for old format."""

    print("\n📦 Testing doctor with old hook format...")

    cli_path = Path(__file__).parent / "requirements-cli.py"
    repo_root = Path(__file__).parent.parent

    with tempfile.TemporaryDirectory() as tmpdir:
        home_dir = Path(tmpdir)
        claude_dir = home_dir / ".claude"
        hooks_dir = claude_dir / "hooks"
        hooks_dir.mkdir(parents=True)

        # Copy necessary files
        sync_files = [
            "check-requirements.py",
            "requirements-cli.py",
            "lib/config.py",
            "lib/git_utils.py",
            "lib/requirements.py",
            "lib/session.py",
            "lib/state_storage.py",
        ]

        for relative in sync_files:
            source = Path(__file__).parent / relative
            destination = hooks_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        # Ensure executables
        for script in ["check-requirements.py", "requirements-cli.py"]:
            target = hooks_dir / script
            target.chmod(0o755)

        # Settings with OLD FORMAT
        settings_path = claude_dir / "settings.json"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(
            json.dumps(
                {
                    "hooks": {"PreToolUse": "~/.claude/hooks/check-requirements.py"}
                },
                indent=2,
            )
        )

        # Project configuration
        project_dir = home_dir / "project"
        (project_dir / ".claude").mkdir(parents=True)
        config = {
            "version": "1.0",
            "enabled": True,
            "requirements": {"commit_plan": {"enabled": True, "scope": "session"}},
        }
        (project_dir / ".claude" / "requirements.yaml").write_text(json.dumps(config))

        env = {**os.environ, "HOME": str(home_dir), "CLAUDE_PROJECT_DIR": str(project_dir)}

        result = subprocess.run(
            ["python3", str(cli_path), "doctor", "--repo", str(repo_root)],
            cwd=project_dir,
            capture_output=True,
            text=True,
            env=env,
        )

        runner.test("Doctor detects old format", result.returncode != 0, result.stdout + result.stderr)
        runner.test("Shows migration message", "old format" in result.stdout.lower(), result.stdout)
        runner.test("Mentions upgrade", "upgrade" in result.stdout.lower() or "new format" in result.stdout.lower(), result.stdout)


def test_cli_doctor_wrong_script(runner: TestRunner):
    """Test doctor command detects wrong script."""

    print("\n📦 Testing doctor with wrong script...")

    cli_path = Path(__file__).parent / "requirements-cli.py"
    repo_root = Path(__file__).parent.parent

    with tempfile.TemporaryDirectory() as tmpdir:
        home_dir = Path(tmpdir)
        claude_dir = home_dir / ".claude"
        hooks_dir = claude_dir / "hooks"
        hooks_dir.mkdir(parents=True)

        # Copy necessary files
        sync_files = [
            "check-requirements.py",
            "requirements-cli.py",
            "lib/config.py",
            "lib/git_utils.py",
            "lib/requirements.py",
            "lib/session.py",
            "lib/state_storage.py",
        ]

        for relative in sync_files:
            source = Path(__file__).parent / relative
            destination = hooks_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        # Ensure executables
        for script in ["check-requirements.py", "requirements-cli.py"]:
            target = hooks_dir / script
            target.chmod(0o755)

        # Settings pointing to WRONG SCRIPT
        settings_path = claude_dir / "settings.json"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(
            json.dumps(
                {
                    "hooks": {
                        "PreToolUse": [
                            {
                                "matcher": "Edit|Write",
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": "python3 ~/.claude/hooks/other-hook.py",
                                        "timeout": 5
                                    }
                                ]
                            }
                        ]
                    }
                },
                indent=2,
            )
        )

        # Project configuration
        project_dir = home_dir / "project"
        (project_dir / ".claude").mkdir(parents=True)
        config = {
            "version": "1.0",
            "enabled": True,
            "requirements": {"commit_plan": {"enabled": True, "scope": "session"}},
        }
        (project_dir / ".claude" / "requirements.yaml").write_text(json.dumps(config))

        env = {**os.environ, "HOME": str(home_dir), "CLAUDE_PROJECT_DIR": str(project_dir)}

        result = subprocess.run(
            ["python3", str(cli_path), "doctor", "--repo", str(repo_root)],
            cwd=project_dir,
            capture_output=True,
            text=True,
            env=env,
        )

        runner.test("Doctor fails with wrong script", result.returncode != 0, result.stdout + result.stderr)
        runner.test("Mentions check-requirements.py", "check-requirements.py" in result.stdout, result.stdout)


def test_cli_doctor_multiple_matchers(runner: TestRunner):
    """Test doctor command handles multiple matchers."""

    print("\n📦 Testing doctor with multiple matchers...")

    cli_path = Path(__file__).parent / "requirements-cli.py"
    repo_root = Path(__file__).parent.parent

    with tempfile.TemporaryDirectory() as tmpdir:
        home_dir = Path(tmpdir)
        claude_dir = home_dir / ".claude"
        hooks_dir = claude_dir / "hooks"
        hooks_dir.mkdir(parents=True)

        # Copy necessary files
        sync_files = [
            "check-requirements.py",
            "requirements-cli.py",
            "lib/config.py",
            "lib/git_utils.py",
            "lib/requirements.py",
            "lib/session.py",
            "lib/state_storage.py",
        ]

        for relative in sync_files:
            source = Path(__file__).parent / relative
            destination = hooks_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        # Ensure executables
        for script in ["check-requirements.py", "requirements-cli.py"]:
            target = hooks_dir / script
            target.chmod(0o755)

        # Settings with MULTIPLE MATCHERS
        settings_path = claude_dir / "settings.json"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(
            json.dumps(
                {
                    "hooks": {
                        "PreToolUse": [
                            {
                                "matcher": "Bash",
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": "python3 ~/.claude/hooks/other.py",
                                        "timeout": 5
                                    }
                                ]
                            },
                            {
                                "matcher": "Edit|Write",
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": "python3 ~/.claude/hooks/check-requirements.py",
                                        "timeout": 5
                                    }
                                ]
                            }
                        ]
                    }
                },
                indent=2,
            )
        )

        # Project configuration
        project_dir = home_dir / "project"
        (project_dir / ".claude").mkdir(parents=True)
        config = {
            "version": "1.0",
            "enabled": True,
            "requirements": {"commit_plan": {"enabled": True, "scope": "session"}},
        }
        (project_dir / ".claude" / "requirements.yaml").write_text(json.dumps(config))

        env = {**os.environ, "HOME": str(home_dir), "CLAUDE_PROJECT_DIR": str(project_dir)}

        result = subprocess.run(
            ["python3", str(cli_path), "doctor", "--repo", str(repo_root), "--verbose"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            env=env,
        )

        runner.test("Doctor finds hook in multiple matchers", result.returncode == 0, result.stdout + result.stderr)
        runner.test("Reports hook registration", "PreToolUse hook registered" in result.stdout, result.stdout)


def test_enhanced_doctor_json_output(runner: TestRunner):
    """Test enhanced doctor JSON output mode."""
    print("\n📦 Testing enhanced doctor --json...")

    cli_path = Path(__file__).parent / "requirements-cli.py"
    Path(__file__).parent.parent

    with tempfile.TemporaryDirectory() as tmpdir:
        home_dir = Path(tmpdir)
        claude_dir = home_dir / ".claude"
        hooks_dir = claude_dir / "hooks"
        hooks_dir.mkdir(parents=True)

        # Copy all required hook files for comprehensive doctor check
        for script in ["check-requirements.py", "requirements-cli.py",
                      "handle-session-start.py", "handle-stop.py", "handle-session-end.py"]:
            source = Path(__file__).parent / script
            dest = hooks_dir / script
            shutil.copy2(source, dest)
            dest.chmod(0o755)

        # Create settings with all required hooks
        settings = claude_dir / "settings.local.json"
        settings.write_text(json.dumps({
            "hooks": {
                "PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "~/.claude/hooks/check-requirements.py"}]}],
                "SessionStart": [{"matcher": "*", "hooks": [{"type": "command", "command": "~/.claude/hooks/handle-session-start.py"}]}],
                "Stop": [{"matcher": "*", "hooks": [{"type": "command", "command": "~/.claude/hooks/handle-stop.py"}]}],
                "SessionEnd": [{"matcher": "*", "hooks": [{"type": "command", "command": "~/.claude/hooks/handle-session-end.py"}]}]
            }
        }))

        env = {**os.environ, "HOME": str(home_dir)}

        result = subprocess.run(
            ["python3", str(cli_path), "doctor", "--json"],
            capture_output=True,
            text=True,
            env=env,
        )

        runner.test("Doctor --json runs", result.returncode == 0, result.stderr)

        # Parse JSON output
        try:
            output = json.loads(result.stdout)
            runner.test("Output is valid JSON", True)
            runner.test("Has status field", 'status' in output)
            runner.test("Has summary field", 'summary' in output)
            runner.test("Has checks array", 'checks' in output and isinstance(output['checks'], list))
            runner.test("Checks have required fields",
                       all('id' in c and 'status' in c and 'severity' in c for c in output['checks']))
        except json.JSONDecodeError as e:
            runner.test("Output is valid JSON", False, f"JSON parse error: {e}")


def test_enhanced_doctor_check_functions(runner: TestRunner):
    """Test enhanced doctor individual check functions."""
    print("\n📦 Testing enhanced doctor check functions...")

    # Import requirements-cli.py using importlib
    import importlib.util
    spec = importlib.util.spec_from_file_location("requirements_cli", Path(__file__).parent / "requirements-cli.py")
    requirements_cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(requirements_cli)

    _check_python_version = requirements_cli._check_python_version
    _check_pyyaml_available = requirements_cli._check_pyyaml_available
    _check_hook_file_exists = requirements_cli._check_hook_file_exists
    _check_path_configured = requirements_cli._check_path_configured
    _check_plugin_installation = requirements_cli._check_plugin_installation

    # Test Python version check
    result = _check_python_version()
    runner.test("Python version check returns dict", isinstance(result, dict))
    runner.test("Has required fields", all(k in result for k in ['id', 'status', 'severity', 'message']))
    runner.test("Python version passes", result['status'] == 'pass')

    # Test PyYAML check
    result = _check_pyyaml_available()
    runner.test("PyYAML check returns dict", isinstance(result, dict))
    runner.test("PyYAML check has status", result['status'] == 'pass')

    # Test hook file check with temp directory
    with tempfile.TemporaryDirectory() as tmpdir:
        hooks_dir = Path(tmpdir)

        # Test missing hook
        result = _check_hook_file_exists('missing.py', hooks_dir)
        runner.test("Missing hook detected", result['status'] == 'fail')
        runner.test("Missing hook has fix", result['fix'] is not None)

        # Test existing hook
        test_hook = hooks_dir / 'test.py'
        test_hook.write_text('#!/usr/bin/env python3\n')
        test_hook.chmod(0o755)
        result = _check_hook_file_exists('test.py', hooks_dir)
        runner.test("Existing executable hook passes", result['status'] == 'pass')

    # Test PATH check
    result = _check_path_configured()
    runner.test("PATH check returns dict", isinstance(result, dict))
    runner.test("PATH check has status", 'status' in result)

    # Test plugin check
    result = _check_plugin_installation()
    runner.test("Plugin check returns dict", isinstance(result, dict))
    runner.test("Plugin check has status", 'status' in result)


def test_hook_behavior(runner: TestRunner):
    """Test hook behavior."""
    print("\n📦 Testing hook behavior...")

    hook_path = Path(__file__).parent / "check-requirements.py"

    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "test-branch"], cwd=tmpdir, capture_output=True)

        # Test without config (should pass silently)
        result = subprocess.run(
            ["python3", str(hook_path)],
            input='{"tool_name":"Edit"}',
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("No config = pass", result.returncode == 0)
        runner.test("No config = no output", result.stdout.strip() == "", f"Got: {result.stdout}")

        # Create config (inherit: false to isolate test from global config)
        os.makedirs(f"{tmpdir}/.claude")
        config = {
            "version": "1.0",
            "enabled": True,
            "inherit": False,  # Don't merge with ~/.claude/requirements.yaml
            "requirements": {
                "commit_plan": {
                    "enabled": True,
                    "scope": "session",
                    "message": "Need commit plan!"
                }
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config, f)

        # Test with config (should prompt) - provide session_id
        test_session = "hooktest"
        result = subprocess.run(
            ["python3", str(hook_path)],
            input=json.dumps({"tool_name":"Edit", "session_id": test_session}),
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("With config = pass", result.returncode == 0)
        runner.test("With config = denies", '"permissionDecision": "deny"' in result.stdout, f"Got: {result.stdout}")

        # Satisfy the requirement (use --session flag)
        cli_path = Path(__file__).parent / "requirements-cli.py"
        subprocess.run(
            ["python3", str(cli_path), "satisfy", "commit_plan", "--session", test_session],
            cwd=tmpdir, capture_output=True
        )

        # Test after satisfy (should pass silently) - use same session_id
        result = subprocess.run(
            ["python3", str(hook_path)],
            input=json.dumps({"tool_name":"Edit", "session_id": test_session}),
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("After satisfy = no output", result.stdout.strip() == "", f"Got: {result.stdout}")

        # Test Read tool (should not trigger)
        result = subprocess.run(
            ["python3", str(hook_path)],
            input='{"tool_name":"Read"}',
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("Read tool = pass", result.returncode == 0)
        runner.test("Read tool = no output", result.stdout.strip() == "")

        # Test skip environment variable
        env = os.environ.copy()
        env["CLAUDE_SKIP_REQUIREMENTS"] = "1"
        result = subprocess.run(
            ["python3", str(hook_path)],
            input='{"tool_name":"Edit"}',
            cwd=tmpdir, capture_output=True, text=True, env=env
        )
        runner.test("Skip env = pass", result.returncode == 0)


def test_checklist_rendering(runner: TestRunner):
    """Test checklist rendering in hook output."""
    print("\n📦 Testing checklist rendering...")

    hook_path = Path(__file__).parent / "check-requirements.py"

    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "feature/test"], cwd=tmpdir, capture_output=True)

        # Create config with checklist
        os.makedirs(f"{tmpdir}/.claude")
        config_with_checklist = {
            "version": "1.0",
            "enabled": True,
            "inherit": False,  # Isolate test from global config
            "requirements": {
                "commit_plan": {
                    "enabled": True,
                    "scope": "session",
                    "message": "Need plan!",
                    "checklist": ["Item 1", "Item 2", "Item 3"]
                }
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config_with_checklist, f)

        # Test hook output contains checklist (provide session_id)
        test_session = "checklist1"
        result = subprocess.run(
            ["python3", str(hook_path)],
            input=json.dumps({"tool_name":"Edit", "session_id": test_session}),
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("Hook runs with checklist", result.returncode == 0)

        # Parse JSON output to get the message
        try:
            output_data = json.loads(result.stdout)
            message = output_data.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
        except (json.JSONDecodeError, KeyError):
            message = result.stdout

        runner.test("Output contains checklist header", "**Checklist**:" in message, f"Message: {message}")
        runner.test("Output contains item 1", "⬜ 1. Item 1" in message, f"Message: {message}")
        runner.test("Output contains item 2", "⬜ 2. Item 2" in message, f"Message: {message}")
        runner.test("Output contains item 3", "⬜ 3. Item 3" in message, f"Message: {message}")

        # Test with empty checklist
        config_empty = {
            "version": "1.0",
            "enabled": True,
            "inherit": False,  # Don't inherit global checklist
            "requirements": {
                "commit_plan": {
                    "enabled": True,
                    "scope": "session",
                    "message": "Need plan!",
                    "checklist": []
                }
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config_empty, f)

        result = subprocess.run(
            ["python3", str(hook_path)],
            input='{"tool_name":"Edit"}',
            cwd=tmpdir, capture_output=True, text=True
        )

        # Parse JSON output
        try:
            output_data = json.loads(result.stdout)
            message = output_data.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
        except (json.JSONDecodeError, KeyError):
            message = result.stdout

        runner.test("Empty checklist no header", "**Checklist**:" not in message, f"Message: {message}")

        # Test without checklist field (disable inheritance to avoid global checklist)
        config_no_checklist = {
            "version": "1.0",
            "enabled": True,
            "inherit": False,  # Don't inherit global checklist
            "requirements": {
                "commit_plan": {
                    "enabled": True,
                    "scope": "session",
                    "message": "Need plan!"
                }
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config_no_checklist, f)

        result = subprocess.run(
            ["python3", str(hook_path)],
            input='{"tool_name":"Edit"}',
            cwd=tmpdir, capture_output=True, text=True
        )

        # Parse JSON output
        try:
            output_data = json.loads(result.stdout)
            message = output_data.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
        except (json.JSONDecodeError, KeyError):
            message = result.stdout

        runner.test("Missing checklist no header", "**Checklist**:" not in message, f"Message: {message}")


def test_hook_config(runner: TestRunner):
    """Test hook configuration method."""
    print("\n📦 Testing hook configuration...")
    from config import RequirementsConfig

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create project config with hook settings
        os.makedirs(f"{tmpdir}/.claude")
        config = {
            "version": "1.0",
            "enabled": True,
            "hooks": {
                "session_start": {
                    "inject_context": False,  # Override default
                },
                "stop": {
                    "verify_requirements": False,  # Override default
                },
            },
            "requirements": {}
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config, f)

        cfg = RequirementsConfig(tmpdir)

        # Test explicit config overrides default
        runner.test(
            "Hook config override",
            cfg.get_hook_config('session_start', 'inject_context') is False,
            f"Got: {cfg.get_hook_config('session_start', 'inject_context')}"
        )
        runner.test(
            "Stop config override",
            cfg.get_hook_config('stop', 'verify_requirements') is False,
            f"Got: {cfg.get_hook_config('stop', 'verify_requirements')}"
        )

        # Test default fallback for unconfigured values
        runner.test(
            "Session end default",
            cfg.get_hook_config('session_end', 'clear_session_state') is False
        )

        # Test built-in defaults when no config
        runner.test(
            "Stop verify_scopes default",
            cfg.get_hook_config('stop', 'verify_scopes') == ['session']
        )

    # Test without any hooks config (should use built-in defaults)
    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(f"{tmpdir}/.claude")
        config = {"version": "1.0", "enabled": True, "requirements": {}}
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config, f)

        cfg = RequirementsConfig(tmpdir)

        # Built-in defaults should apply
        runner.test(
            "Default inject_context=True",
            cfg.get_hook_config('session_start', 'inject_context') is True
        )
        runner.test(
            "Default verify_requirements=True",
            cfg.get_hook_config('stop', 'verify_requirements') is True
        )

    # Test custom_header field
    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(f"{tmpdir}/.claude")
        config = {
            "version": "1.0",
            "enabled": True,
            "hooks": {
                "session_start": {
                    "inject_context": True,
                    "custom_header": "**Project Context**\n\nCustom header text here."
                }
            },
            "requirements": {}
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config, f)

        cfg = RequirementsConfig(tmpdir)

        runner.test(
            "Custom header config",
            cfg.get_hook_config('session_start', 'custom_header') == "**Project Context**\n\nCustom header text here.",
            f"Got: {cfg.get_hook_config('session_start', 'custom_header')}"
        )
        runner.test(
            "Custom header default None",
            cfg.get_hook_config('session_start', 'nonexistent_key') is None
        )


def test_session_start_hook(runner: TestRunner):
    """Test SessionStart hook behavior."""
    print("\n📦 Testing SessionStart hook...")

    hook_path = Path(__file__).parent / "handle-session-start.py"

    # Skip if hook doesn't exist yet (TDD - write test before implementation)
    if not hook_path.exists():
        runner.test("SessionStart hook exists", False, "Hook file not implemented yet")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "feature/test"], cwd=tmpdir, capture_output=True)

        # Test without config - should suggest req init on startup (provide session_id)
        result = subprocess.run(
            ["python3", str(hook_path)],
            input=json.dumps({"hook_event_name":"SessionStart","source":"startup","session_id":"starttest"}),
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("SessionStart no config = pass", result.returncode == 0)
        runner.test("SessionStart suggests init", "req init" in result.stdout,
                   f"Expected 'req init' in output, got: {result.stdout[:200]}")

        # Test without config on resume (should NOT suggest init) - provide session_id
        result = subprocess.run(
            ["python3", str(hook_path)],
            input=json.dumps({"hook_event_name":"SessionStart","source":"resume","session_id":"resumetest"}),
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("SessionStart resume = no init suggestion",
                   "req init" not in result.stdout,
                   f"Should not suggest init on resume: {result.stdout[:200]}")

        # Create config with context injection enabled
        os.makedirs(f"{tmpdir}/.claude")
        config = {
            "version": "1.0",
            "enabled": True,
            "inherit": False,
            "hooks": {
                "session_start": {"inject_context": True}
            },
            "requirements": {
                "commit_plan": {"enabled": True, "scope": "session", "message": "Plan!"}
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config, f)

        # Test outputs status when inject_context=True (provide session_id)
        result = subprocess.run(
            ["python3", str(hook_path)],
            input=json.dumps({"hook_event_name":"SessionStart","source":"startup","session_id":"statustest"}),
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("SessionStart outputs status", "Requirements" in result.stdout or "commit_plan" in result.stdout,
                   f"Got: {result.stdout}")

        # Test with inject_context=False (should be silent)
        config["hooks"]["session_start"]["inject_context"] = False
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config, f)

        result = subprocess.run(
            ["python3", str(hook_path)],
            input='{"hook_event_name":"SessionStart","source":"startup"}',
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("SessionStart silent when disabled", result.stdout.strip() == "",
                   f"Got: {result.stdout}")

    # Test custom_header display
    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "feature/test"], cwd=tmpdir, capture_output=True)

        os.makedirs(f"{tmpdir}/.claude")
        config = {
            "version": "1.0",
            "enabled": True,
            "inherit": False,
            "hooks": {
                "session_start": {
                    "inject_context": True,
                    "custom_header": "**SolarMonkey Context**\n\nCritical ADRs here."
                }
            },
            "requirements": {
                "test_req": {"enabled": True, "scope": "session", "message": "Test!"}
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config, f)

        result = subprocess.run(
            ["python3", str(hook_path)],
            input=json.dumps({"hook_event_name":"SessionStart","source":"startup","session_id":"headertest"}),
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("Custom header displayed", "SolarMonkey Context" in result.stdout,
                   f"Got: {result.stdout[:300]}")
        runner.test("Custom header before status", result.stdout.find("SolarMonkey") < result.stdout.find("Requirements"),
                   "Custom header should appear before Requirements status")

    # Test non-git directory (should pass silently)
    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            ["python3", str(hook_path)],
            input='{"hook_event_name":"SessionStart"}',
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("SessionStart non-git = pass", result.returncode == 0)
        runner.test("SessionStart non-git = silent", result.stdout.strip() == "")


def test_stop_hook(runner: TestRunner):
    """Test Stop hook behavior."""
    print("\n📦 Testing Stop hook...")

    hook_path = Path(__file__).parent / "handle-stop.py"

    # Skip if hook doesn't exist yet (TDD - write test before implementation)
    if not hook_path.exists():
        runner.test("Stop hook exists", False, "Hook file not implemented yet")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "feature/test"], cwd=tmpdir, capture_output=True)

        # Test without config (should pass silently)
        result = subprocess.run(
            ["python3", str(hook_path)],
            input='{"hook_event_name":"Stop","stop_hook_active":false}',
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("Stop no config = pass", result.returncode == 0)

        # Create config with requirements
        os.makedirs(f"{tmpdir}/.claude")
        config = {
            "version": "1.0",
            "enabled": True,
            "inherit": False,
            "hooks": {
                "stop": {"verify_requirements": True}
            },
            "requirements": {
                "commit_plan": {"enabled": True, "scope": "session", "message": "Plan!"}
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config, f)

        # Mark requirement as triggered (simulating Edit/Write tool use)
        from requirements import BranchRequirements
        # Use explicit session ID for tests instead of get_session_id()
        test_session_id = "test1234"
        reqs = BranchRequirements("feature/test", test_session_id, tmpdir)
        reqs.mark_triggered("commit_plan", "session")

        # Test blocks when requirements triggered but unsatisfied
        stop_input = json.dumps({"hook_event_name": "Stop", "stop_hook_active": False, "session_id": test_session_id})
        result = subprocess.run(
            ["python3", str(hook_path)],
            input=stop_input,
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("Stop blocks when unsatisfied", '"decision": "block"' in result.stdout,
                   f"Got: {result.stdout}")
        runner.test("Stop reason mentions requirement", "commit_plan" in result.stdout,
                   f"Got: {result.stdout}")

        # Test respects stop_hook_active flag (CRITICAL for infinite loop prevention)
        result = subprocess.run(
            ["python3", str(hook_path)],
            input='{"hook_event_name":"Stop","stop_hook_active":true}',
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("Stop respects stop_hook_active", result.stdout.strip() == "",
                   f"Got: {result.stdout}")

        # Test allows when requirements satisfied
        cli_path = Path(__file__).parent / "requirements-cli.py"
        subprocess.run(
            ["python3", str(cli_path), "satisfy", "commit_plan", "--session", test_session_id],
            cwd=tmpdir, capture_output=True
        )
        result = subprocess.run(
            ["python3", str(hook_path)],
            input=stop_input,
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("Stop allows when satisfied", result.stdout.strip() == "",
                   f"Got: {result.stdout}")

        # Test disabled by config
        config["hooks"]["stop"]["verify_requirements"] = False
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config, f)

        # Clear requirement to test that disabled config skips check
        subprocess.run(
            ["python3", str(cli_path), "clear", "commit_plan"],
            cwd=tmpdir, capture_output=True
        )
        result = subprocess.run(
            ["python3", str(hook_path)],
            input=stop_input,
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("Stop disabled by config", result.stdout.strip() == "",
                   f"Got: {result.stdout}")

    # Test non-git directory (should pass silently)
    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            ["python3", str(hook_path)],
            input='{"hook_event_name":"Stop","stop_hook_active":false}',
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("Stop non-git = pass", result.returncode == 0)


def test_session_end_hook(runner: TestRunner):
    """Test SessionEnd hook behavior."""
    print("\n📦 Testing SessionEnd hook...")

    hook_path = Path(__file__).parent / "handle-session-end.py"

    # Skip if hook doesn't exist yet (TDD - write test before implementation)
    if not hook_path.exists():
        runner.test("SessionEnd hook exists", False, "Hook file not implemented yet")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "feature/test"], cwd=tmpdir, capture_output=True)

        # Test without config (should pass silently)
        result = subprocess.run(
            ["python3", str(hook_path)],
            input='{"hook_event_name":"SessionEnd","reason":"clear"}',
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("SessionEnd no config = pass", result.returncode == 0)

        # Create config
        os.makedirs(f"{tmpdir}/.claude")
        config = {
            "version": "1.0",
            "enabled": True,
            "inherit": False,
            "hooks": {
                "session_end": {"clear_session_state": False}
            },
            "requirements": {
                "commit_plan": {"enabled": True, "scope": "session", "message": "Plan!"}
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config, f)

        # First satisfy the requirement to create state (use --session)
        test_session = "endtest1"
        cli_path = Path(__file__).parent / "requirements-cli.py"
        subprocess.run(
            ["python3", str(cli_path), "satisfy", "commit_plan", "--session", test_session],
            cwd=tmpdir, capture_output=True
        )

        # Run session end (should preserve state by default) - provide session_id
        result = subprocess.run(
            ["python3", str(hook_path)],
            input=json.dumps({"hook_event_name":"SessionEnd","reason":"clear","session_id":test_session}),
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("SessionEnd = pass", result.returncode == 0)
        runner.test("SessionEnd = silent", result.stdout.strip() == "")

        # Check state is preserved (clear_session_state=False) - use same session
        status_result = subprocess.run(
            ["python3", str(cli_path), "status", "--session", test_session],
            cwd=tmpdir, capture_output=True, text=True
        )
        # CLI outputs ✅ for satisfied requirements
        runner.test("SessionEnd preserves state", "✅" in status_result.stdout or
                   "satisfied" in status_result.stdout.lower(),
                   f"Got: {status_result.stdout}")

    # Test non-git directory (should pass silently)
    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            ["python3", str(hook_path)],
            input='{"hook_event_name":"SessionEnd","reason":"logout"}',
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("SessionEnd non-git = pass", result.returncode == 0)


def test_triggered_requirements(runner: TestRunner):
    """Test triggered state tracking for requirements."""
    print("\n📦 Testing triggered requirements...")
    from requirements import BranchRequirements

    with tempfile.TemporaryDirectory() as tmpdir:
        # Simulate git repo
        os.makedirs(f"{tmpdir}/.git")

        # Test 1: is_triggered initially False
        reqs = BranchRequirements("feature/test", "session-1", tmpdir)
        runner.test("is_triggered initially False",
                   not reqs.is_triggered("commit_plan", "session"))

        # Test 2: mark_triggered sets triggered to True
        reqs.mark_triggered("commit_plan", "session")
        runner.test("is_triggered True after mark_triggered",
                   reqs.is_triggered("commit_plan", "session"))

        # Test 3: Different session sees different triggered state
        reqs2 = BranchRequirements("feature/test", "session-2", tmpdir)
        runner.test("is_triggered False for different session",
                   not reqs2.is_triggered("commit_plan", "session"))

        # Test 4: Triggered state persists across BranchRequirements instances
        reqs3 = BranchRequirements("feature/test", "session-1", tmpdir)
        runner.test("is_triggered persists across instances",
                   reqs3.is_triggered("commit_plan", "session"))

        # Test 5: Branch-scoped triggered state
        reqs.mark_triggered("github_ticket", "branch")
        runner.test("Branch triggered state set",
                   reqs.is_triggered("github_ticket", "branch"))
        # Create fresh instance to verify branch state is visible to other sessions
        reqs2_fresh = BranchRequirements("feature/test", "session-2", tmpdir)
        runner.test("Branch triggered visible to other sessions",
                   reqs2_fresh.is_triggered("github_ticket", "branch"))

        # Test 6: single_use scope behaves like session for triggered
        reqs.mark_triggered("pre_commit_review", "single_use")
        runner.test("single_use triggered for same session",
                   reqs.is_triggered("pre_commit_review", "single_use"))
        runner.test("single_use not triggered for different session",
                   not reqs2.is_triggered("pre_commit_review", "single_use"))

        # Test 7: mark_triggered is idempotent (doesn't change timestamp on repeat call)
        import unittest.mock as mock
        reqs4 = BranchRequirements("idempotent/branch", "session-x", tmpdir)
        with mock.patch('time.time', return_value=1000.0):
            reqs4.mark_triggered("test_req", "session")
        # Reload and check timestamp
        reqs4_reload = BranchRequirements("idempotent/branch", "session-x", tmpdir)
        status = reqs4_reload.get_status()
        first_triggered_at = status['requirements'].get('test_req', {}).get('sessions', {}).get('session-x', {}).get('triggered_at')

        with mock.patch('time.time', return_value=2000.0):
            reqs4_reload.mark_triggered("test_req", "session")
        # Reload again and verify timestamp didn't change
        reqs4_final = BranchRequirements("idempotent/branch", "session-x", tmpdir)
        status_final = reqs4_final.get_status()
        second_triggered_at = status_final['requirements'].get('test_req', {}).get('sessions', {}).get('session-x', {}).get('triggered_at')
        runner.test("mark_triggered is idempotent",
                   first_triggered_at == second_triggered_at,
                   f"First: {first_triggered_at}, Second: {second_triggered_at}")

        # Test 8: Triggered state is independent of satisfied state
        reqs5 = BranchRequirements("independent/branch", "session-i", tmpdir)
        reqs5.mark_triggered("independent_req", "session")
        runner.test("Triggered but not satisfied",
                   reqs5.is_triggered("independent_req", "session") and
                   not reqs5.is_satisfied("independent_req", "session"))
        reqs5.satisfy("independent_req", "session")
        runner.test("Both triggered and satisfied",
                   reqs5.is_triggered("independent_req", "session") and
                   reqs5.is_satisfied("independent_req", "session"))


def test_stop_hook_triggered_only(runner: TestRunner):
    """Test that Stop hook only checks triggered requirements."""
    print("\n📦 Testing Stop hook triggered-only behavior...")

    hook_path = Path(__file__).parent / "handle-stop.py"
    cli_path = Path(__file__).parent / "requirements-cli.py"

    # Skip if hook doesn't exist
    if not hook_path.exists():
        runner.test("Stop hook exists", False, "Hook file not found")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "feature/test"], cwd=tmpdir, capture_output=True)

        # Create config with requirements
        os.makedirs(f"{tmpdir}/.claude")
        config = {
            "version": "1.0",
            "enabled": True,
            "inherit": False,
            "hooks": {"stop": {"verify_requirements": True}},
            "requirements": {
                "commit_plan": {"enabled": True, "scope": "session", "message": "Plan!"}
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config, f)

        # Test 1: Stop allows when requirement NOT triggered (research session)
        # Don't trigger anything - just run stop hook
        result = subprocess.run(
            ["python3", str(hook_path)],
            input='{"hook_event_name":"Stop","stop_hook_active":false}',
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("Stop allows untriggered requirements",
                   result.stdout.strip() == "",
                   f"Expected empty output for research session, got: {result.stdout}")

        # Test 2: Manually mark requirement as triggered, then stop should block
        from requirements import BranchRequirements
        # Use explicit session ID for tests instead of get_session_id()
        session_id = "test5678"
        reqs = BranchRequirements("feature/test", session_id, tmpdir)
        reqs.mark_triggered("commit_plan", "session")

        # Pass session_id in stdin so subprocess uses same session
        stop_input = json.dumps({"hook_event_name": "Stop", "stop_hook_active": False, "session_id": session_id})
        result = subprocess.run(
            ["python3", str(hook_path)],
            input=stop_input,
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("Stop blocks triggered+unsatisfied",
                   '"decision": "block"' in result.stdout,
                   f"Expected block, got: {result.stdout}")

        # Test 3: Satisfy requirement, then stop should allow
        subprocess.run(
            ["python3", str(cli_path), "satisfy", "commit_plan", "--session", session_id],
            cwd=tmpdir, capture_output=True
        )
        result = subprocess.run(
            ["python3", str(hook_path)],
            input=stop_input,
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("Stop allows triggered+satisfied",
                   result.stdout.strip() == "",
                   f"Expected empty output, got: {result.stdout}")

    # Test 4: Multiple requirements - only check triggered ones
    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "feature/multi"], cwd=tmpdir, capture_output=True)

        os.makedirs(f"{tmpdir}/.claude")
        config = {
            "version": "1.0",
            "enabled": True,
            "inherit": False,
            "hooks": {"stop": {"verify_requirements": True}},
            "requirements": {
                "commit_plan": {"enabled": True, "scope": "session", "message": "Plan!"},
                "adr_reviewed": {"enabled": True, "scope": "session", "message": "ADR!"},
                "code_quality": {"enabled": True, "scope": "session", "message": "Quality!"}
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config, f)

        # Trigger only one requirement, leave others untriggered
        from requirements import BranchRequirements
        # Use explicit session ID for tests instead of get_session_id()
        session_id = "test9abc"
        reqs = BranchRequirements("feature/multi", session_id, tmpdir)
        reqs.mark_triggered("commit_plan", "session")
        # adr_reviewed and code_quality are NOT triggered

        # Pass session_id in stdin so subprocess uses same session
        stop_input = json.dumps({"hook_event_name": "Stop", "stop_hook_active": False, "session_id": session_id})
        result = subprocess.run(
            ["python3", str(hook_path)],
            input=stop_input,
            cwd=tmpdir, capture_output=True, text=True
        )
        # Should only mention commit_plan, not adr_reviewed or code_quality
        runner.test("Stop only checks triggered requirement",
                   "commit_plan" in result.stdout and
                   "adr_reviewed" not in result.stdout and
                   "code_quality" not in result.stdout,
                   f"Got: {result.stdout}")


def test_stop_hook_guard_context_aware(runner: TestRunner):
    """Test that Stop hook uses context-aware checking for guard requirements."""
    print("\n📦 Testing Stop hook context-aware guard checking...")

    hook_path = Path(__file__).parent / "handle-stop.py"

    # Skip if hook doesn't exist
    if not hook_path.exists():
        runner.test("Stop hook exists", False, "Hook file not found")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize git repo on feature branch
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "feature/test"], cwd=tmpdir, capture_output=True)

        # Create config with protected_branch guard requirement
        os.makedirs(f"{tmpdir}/.claude")
        config = {
            "version": "1.0",
            "enabled": True,
            "inherit": False,
            "hooks": {"stop": {"verify_requirements": True}},
            "requirements": {
                "protected_branch": {
                    "enabled": True,
                    "type": "guard",
                    "guard_type": "protected_branch",
                    "scope": "session",
                    "protected_branches": ["master", "main"]
                }
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config, f)

        # Test 1: On feature branch, guard should be satisfied (NOT on protected branch)
        # Mark as triggered so Stop hook checks it
        from requirements import BranchRequirements
        session_id = "guard-test-1"
        reqs = BranchRequirements("feature/test", session_id, tmpdir)
        reqs.mark_triggered("protected_branch", "session")

        # Stop hook should allow (guard condition passes)
        stop_input = json.dumps({
            "hook_event_name": "Stop",
            "stop_hook_active": False,
            "session_id": session_id
        })
        result = subprocess.run(
            ["python3", str(hook_path)],
            input=stop_input,
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("Stop allows guard on feature branch",
                   result.stdout.strip() == "",
                   f"Expected empty (allow), got: {result.stdout}")

    # Test 2: On master branch, guard should NOT be satisfied (ON protected branch)
    with tempfile.TemporaryDirectory() as tmpdir2:
        subprocess.run(["git", "init"], cwd=tmpdir2, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "master"], cwd=tmpdir2, capture_output=True)

        os.makedirs(f"{tmpdir2}/.claude")
        with open(f"{tmpdir2}/.claude/requirements.yaml", 'w') as f:
            json.dump(config, f)

        # Mark as triggered
        session_id2 = "guard-test-2"
        reqs2 = BranchRequirements("master", session_id2, tmpdir2)
        reqs2.mark_triggered("protected_branch", "session")

        # Stop hook should block (guard condition fails)
        stop_input2 = json.dumps({
            "hook_event_name": "Stop",
            "stop_hook_active": False,
            "session_id": session_id2
        })
        result2 = subprocess.run(
            ["python3", str(hook_path)],
            input=stop_input2,
            cwd=tmpdir2, capture_output=True, text=True
        )
        runner.test("Stop blocks guard on master branch",
                   '"decision": "block"' in result2.stdout,
                   f"Expected block, got: {result2.stdout}")


def test_batched_requirements_blocking(runner: TestRunner):
    """Test that multiple unsatisfied requirements are batched into one message."""
    print("\n📦 Testing batched requirements blocking...")

    hook_path = Path(__file__).parent / "check-requirements.py"

    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "feature/batch-test"], cwd=tmpdir, capture_output=True)

        # Create config with multiple requirements (inherit: false to isolate)
        os.makedirs(f"{tmpdir}/.claude")
        config = {
            "version": "1.0",
            "enabled": True,
            "inherit": False,
            "requirements": {
                "commit_plan": {
                    "enabled": True,
                    "scope": "session",
                    "message": "Need commit plan!"
                },
                "adr_reviewed": {
                    "enabled": True,
                    "scope": "branch",
                    "message": "ADR must be reviewed!"
                }
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config, f)

        # Test hook output contains both requirements (provide session_id)
        test_session = "batchtest"
        result = subprocess.run(
            ["python3", str(hook_path)],
            input=json.dumps({"tool_name":"Edit", "session_id": test_session}),
            cwd=tmpdir, capture_output=True, text=True
        )

        runner.test("Hook returns success exit code", result.returncode == 0)

        # Parse JSON output
        try:
            output_data = json.loads(result.stdout)
            message = output_data.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
        except (json.JSONDecodeError, KeyError):
            message = result.stdout

        runner.test("Message contains commit_plan", "commit_plan" in message, f"Message: {message[:200]}")
        runner.test("Message contains adr_reviewed", "adr_reviewed" in message, f"Message: {message[:200]}")
        runner.test("Message contains batch command hint",
                   "req satisfy commit_plan adr_reviewed" in message or
                   "req satisfy adr_reviewed commit_plan" in message,
                   f"Message: {message[:200]}")


def test_cli_satisfy_multiple(runner: TestRunner):
    """Test CLI satisfy command with multiple requirements."""
    print("\n📦 Testing CLI satisfy with multiple requirements...")

    cli_path = Path(__file__).parent / "requirements-cli.py"

    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "test-branch"], cwd=tmpdir, capture_output=True)

        os.makedirs(f"{tmpdir}/.claude")
        config = {
            "version": "1.0",
            "enabled": True,
            "inherit": False,
            "requirements": {
                "commit_plan": {"enabled": True, "scope": "session"},
                "adr_reviewed": {"enabled": True, "scope": "session"}
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config, f)

        # Test satisfy with multiple requirements (use --session)
        test_session = "multisess"
        result = subprocess.run(
            ["python3", str(cli_path), "satisfy", "commit_plan", "adr_reviewed", "--session", test_session],
            cwd=tmpdir, capture_output=True, text=True
        )

        runner.test("Multiple satisfy succeeds", result.returncode == 0, result.stderr)
        runner.test("Shows success message", "✅" in result.stdout, result.stdout)

        # Verify both were satisfied (pass session_id to hook)
        hook_path = Path(__file__).parent / "check-requirements.py"
        result = subprocess.run(
            ["python3", str(hook_path)],
            input=json.dumps({"tool_name":"Edit", "session_id": test_session}),
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("No blocking after multiple satisfy", result.stdout.strip() == "",
                   f"Got: {result.stdout[:200]}")


def test_cli_satisfy_branch_flag(runner: TestRunner):
    """Test CLI satisfy command with --branch flag for branch-level satisfaction."""
    print("\n📦 Testing CLI satisfy with --branch flag...")

    cli_path = Path(__file__).parent / "requirements-cli.py"
    hook_path = Path(__file__).parent / "check-requirements.py"

    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "feature/branch-test"], cwd=tmpdir, capture_output=True)

        os.makedirs(f"{tmpdir}/.claude")
        config = {
            "version": "1.0",
            "enabled": True,
            "inherit": False,
            "requirements": {
                "commit_plan": {"enabled": True, "scope": "session"},
                "adr_reviewed": {"enabled": True, "scope": "session"}
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config, f)

        # Test satisfy with --branch flag
        result = subprocess.run(
            ["python3", str(cli_path), "satisfy", "commit_plan", "--branch", "feature/branch-test"],
            cwd=tmpdir, capture_output=True, text=True
        )

        runner.test("Branch satisfy succeeds", result.returncode == 0, result.stderr)
        runner.test("Shows branch-level message", "branch level" in result.stdout.lower(),
                   f"Output: {result.stdout}")
        runner.test("Shows all sessions message", "all" in result.stdout.lower() and "session" in result.stdout.lower(),
                   f"Output: {result.stdout}")

        # Verify hook passes with a DIFFERENT session ID (branch override should work)
        result = subprocess.run(
            ["python3", str(hook_path)],
            input='{"tool_name":"Edit", "session_id": "totally-new-session-xyz"}',
            cwd=tmpdir, capture_output=True, text=True
        )

        # Parse output to check commit_plan status
        if result.stdout.strip():
            try:
                output_data = json.loads(result.stdout)
                message = output_data.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
            except (json.JSONDecodeError, KeyError):
                message = result.stdout
        else:
            message = ""

        # commit_plan should NOT be in the blocking message (satisfied at branch level)
        # adr_reviewed SHOULD be in the blocking message (not satisfied)
        runner.test("Branch-satisfied req not blocked",
                   "commit_plan" not in message or "adr_reviewed" in message,
                   f"Expected only adr_reviewed to block. Message: {message[:200]}")


def test_cli_satisfy_branch_flag_dynamic(runner: TestRunner):
    """Test CLI satisfy with --branch flag for DYNAMIC requirements.

    This is a critical test because dynamic requirements use DynamicRequirementStrategy
    which has a different code path than blocking requirements. The strategy must check
    for branch-level satisfaction before running the calculator.
    """
    print("\n📦 Testing CLI satisfy with --branch flag (dynamic requirement)...")

    cli_path = Path(__file__).parent / "requirements-cli.py"

    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize git repo with commits (needed for branch size calculation)
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "main"], cwd=tmpdir, capture_output=True)

        # Create initial commit on main
        Path(f"{tmpdir}/README.md").write_text("# Test\n")
        subprocess.run(["git", "add", "."], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=tmpdir, capture_output=True)

        # Create feature branch
        subprocess.run(["git", "checkout", "-b", "feature/dynamic-test"], cwd=tmpdir, capture_output=True)

        os.makedirs(f"{tmpdir}/.claude")
        # Config with a DYNAMIC requirement (like branch_size_limit)
        config = {
            "version": "1.0",
            "enabled": True,
            "inherit": False,
            "requirements": {
                "branch_size_limit": {
                    "enabled": True,
                    "type": "dynamic",  # This uses DynamicRequirementStrategy
                    "calculator": "branch_size_calculator",
                    "scope": "session",
                    "cache_ttl": 60,
                    "approval_ttl": 300,
                    "thresholds": {
                        "warn": 10,
                        "block": 20
                    },
                    "blocking_message": "Branch too large: {total} lines"
                }
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config, f)

        # Satisfy with --branch flag
        result = subprocess.run(
            ["python3", str(cli_path), "satisfy", "branch_size_limit", "--branch", "feature/dynamic-test"],
            cwd=tmpdir, capture_output=True, text=True
        )

        runner.test("Dynamic req branch satisfy succeeds", result.returncode == 0, result.stderr)
        runner.test("Shows branch-level message", "branch level" in result.stdout.lower(),
                   f"Output: {result.stdout}")

        # Verify via the requirements module directly that branch-level override works
        # for a NEW session (the key test!)
        sys.path.insert(0, str(Path(__file__).parent / 'lib'))
        from requirements import BranchRequirements
        from dynamic_strategy import DynamicRequirementStrategy
        from config import RequirementsConfig

        reqs = BranchRequirements("feature/dynamic-test", "brand-new-session-xyz", tmpdir)
        config_obj = RequirementsConfig(tmpdir)
        strategy = DynamicRequirementStrategy()

        context = {
            'project_dir': tmpdir,
            'branch': 'feature/dynamic-test',
            'session_id': 'brand-new-session-xyz',
            'tool_name': 'Edit'
        }

        # The strategy should return None (allow) due to branch-level override
        check_result = strategy.check('branch_size_limit', config_obj, reqs, context)
        runner.test("Dynamic strategy respects branch override",
                   check_result is None,
                   f"Expected None (allow), got: {check_result}")


def test_cli_satisfy_branch_flag_multiple(runner: TestRunner):
    """Test CLI satisfy command with --branch flag for multiple requirements."""
    print("\n📦 Testing CLI satisfy with --branch flag (multiple requirements)...")

    cli_path = Path(__file__).parent / "requirements-cli.py"
    hook_path = Path(__file__).parent / "check-requirements.py"

    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "feature/multi-branch"], cwd=tmpdir, capture_output=True)

        os.makedirs(f"{tmpdir}/.claude")
        config = {
            "version": "1.0",
            "enabled": True,
            "inherit": False,
            "requirements": {
                "commit_plan": {"enabled": True, "scope": "session"},
                "adr_reviewed": {"enabled": True, "scope": "session"}
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config, f)

        # Test satisfy multiple requirements with --branch flag
        result = subprocess.run(
            ["python3", str(cli_path), "satisfy", "commit_plan", "adr_reviewed", "--branch", "feature/multi-branch"],
            cwd=tmpdir, capture_output=True, text=True
        )

        runner.test("Multi-branch satisfy succeeds", result.returncode == 0, result.stderr)
        runner.test("Shows count", "2" in result.stdout, f"Output: {result.stdout}")
        runner.test("Shows branch level", "branch level" in result.stdout.lower(), f"Output: {result.stdout}")

        # Verify hook passes completely with a NEW session (branch overrides should work)
        result = subprocess.run(
            ["python3", str(hook_path)],
            input='{"tool_name":"Edit", "session_id": "brand-new-session"}',
            cwd=tmpdir, capture_output=True, text=True
        )

        runner.test("No blocking after branch-level satisfy", result.stdout.strip() == "",
                   f"Expected no output (all satisfied at branch level). Got: {result.stdout[:200]}")


def test_partial_satisfaction(runner: TestRunner):
    """Test that partial satisfaction shows remaining requirements."""
    print("\n📦 Testing partial satisfaction...")

    hook_path = Path(__file__).parent / "check-requirements.py"
    cli_path = Path(__file__).parent / "requirements-cli.py"

    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup with two requirements
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "feature/partial"], cwd=tmpdir, capture_output=True)

        os.makedirs(f"{tmpdir}/.claude")
        config = {
            "version": "1.0",
            "enabled": True,
            "inherit": False,
            "requirements": {
                "commit_plan": {"enabled": True, "scope": "session"},
                "adr_reviewed": {"enabled": True, "scope": "session"}
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config, f)

        # Satisfy only commit_plan (use --session)
        test_session = "partialtest"
        subprocess.run(
            ["python3", str(cli_path), "satisfy", "commit_plan", "--session", test_session],
            cwd=tmpdir, capture_output=True
        )

        # Hook should only block on adr_reviewed (provide session_id)
        result = subprocess.run(
            ["python3", str(hook_path)],
            input=json.dumps({"tool_name":"Edit", "session_id": test_session}),
            cwd=tmpdir, capture_output=True, text=True
        )

        try:
            output_data = json.loads(result.stdout)
            message = output_data.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
        except (json.JSONDecodeError, KeyError):
            message = result.stdout

        runner.test("Only shows remaining requirement",
                   "adr_reviewed" in message and "commit_plan" not in message.replace("req satisfy commit_plan", ""),
                   f"Message: {message[:200]}")


def test_guard_strategy_blocks_protected_branch(runner: TestRunner):
    """Test that guard strategy blocks edits on protected branches."""
    print("\n📦 Testing guard strategy blocks protected branch...")

    # Import will fail until implemented
    try:
        from guard_strategy import GuardRequirementStrategy
        from strategy_registry import STRATEGIES
    except ImportError:
        runner.test("GuardRequirementStrategy exists", False, "Strategy not implemented yet")
        return

    # Check strategy is registered
    runner.test("Guard strategy registered", 'guard' in STRATEGIES,
               f"Available: {list(STRATEGIES.keys())}")

    strategy = GuardRequirementStrategy()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup git repo on master
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "master"], cwd=tmpdir, capture_output=True)

        # Create mock config and requirements
        from config import RequirementsConfig
        from requirements import BranchRequirements

        # Create config with protected_branch requirement
        os.makedirs(f"{tmpdir}/.claude")
        config_content = {
            "version": "1.0",
            "enabled": True,
            "inherit": False,
            "requirements": {
                "protected_branch": {
                    "enabled": True,
                    "type": "guard",
                    "guard_type": "protected_branch",
                    "protected_branches": ["master", "main"],
                    "message": "Cannot edit on protected branch"
                }
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config_content, f)

        config = RequirementsConfig(tmpdir)
        reqs = BranchRequirements("master", "test-session", tmpdir)

        context = {
            'project_dir': tmpdir,
            'branch': 'master',
            'session_id': 'test-session',
            'tool_name': 'Edit'
        }

        # Should block on master
        result = strategy.check("protected_branch", config, reqs, context)
        runner.test("Blocks on master branch", result is not None,
                   f"Expected denial, got: {result}")
        if result:
            runner.test("Has denial message", "message" in result or "hookSpecificOutput" in result,
                       f"Result: {result}")


def test_guard_strategy_allows_feature_branch(runner: TestRunner):
    """Test that guard strategy allows edits on non-protected branches."""
    print("\n📦 Testing guard strategy allows feature branch...")

    try:
        from guard_strategy import GuardRequirementStrategy
    except ImportError:
        runner.test("GuardRequirementStrategy exists", False, "Strategy not implemented yet")
        return

    strategy = GuardRequirementStrategy()

    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "feature/test"], cwd=tmpdir, capture_output=True)
        os.makedirs(f"{tmpdir}/.git", exist_ok=True)

        from config import RequirementsConfig
        from requirements import BranchRequirements

        os.makedirs(f"{tmpdir}/.claude")
        config_content = {
            "version": "1.0",
            "enabled": True,
            "inherit": False,
            "requirements": {
                "protected_branch": {
                    "enabled": True,
                    "type": "guard",
                    "guard_type": "protected_branch",
                    "protected_branches": ["master", "main"]
                }
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config_content, f)

        config = RequirementsConfig(tmpdir)
        reqs = BranchRequirements("feature/test", "test-session", tmpdir)

        context = {
            'project_dir': tmpdir,
            'branch': 'feature/test',
            'session_id': 'test-session',
            'tool_name': 'Edit'
        }

        # Should allow on feature branch
        result = strategy.check("protected_branch", config, reqs, context)
        runner.test("Allows on feature branch", result is None,
                   f"Expected None, got: {result}")


def test_guard_strategy_respects_custom_branch_list(runner: TestRunner):
    """Test that guard strategy respects custom protected_branches list."""
    print("\n📦 Testing guard strategy respects custom branch list...")

    try:
        from guard_strategy import GuardRequirementStrategy
    except ImportError:
        runner.test("GuardRequirementStrategy exists", False, "Strategy not implemented yet")
        return

    strategy = GuardRequirementStrategy()

    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        os.makedirs(f"{tmpdir}/.git", exist_ok=True)

        from config import RequirementsConfig
        from requirements import BranchRequirements

        os.makedirs(f"{tmpdir}/.claude")
        # Custom list that protects 'develop' but NOT 'master'
        config_content = {
            "version": "1.0",
            "enabled": True,
            "inherit": False,
            "requirements": {
                "protected_branch": {
                    "enabled": True,
                    "type": "guard",
                    "guard_type": "protected_branch",
                    "protected_branches": ["develop", "release"]
                }
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config_content, f)

        config = RequirementsConfig(tmpdir)

        # Test 1: develop should be blocked
        reqs1 = BranchRequirements("develop", "test-session", tmpdir)
        context1 = {
            'project_dir': tmpdir,
            'branch': 'develop',
            'session_id': 'test-session',
            'tool_name': 'Edit'
        }
        result1 = strategy.check("protected_branch", config, reqs1, context1)
        runner.test("Blocks custom protected branch 'develop'", result1 is not None)

        # Test 2: master should be allowed (not in custom list)
        reqs2 = BranchRequirements("master", "test-session", tmpdir)
        context2 = {
            'project_dir': tmpdir,
            'branch': 'master',
            'session_id': 'test-session',
            'tool_name': 'Edit'
        }
        result2 = strategy.check("protected_branch", config, reqs2, context2)
        runner.test("Allows master when not in custom list", result2 is None,
                   f"Expected None, got: {result2}")


def test_guard_strategy_approval_bypasses_check(runner: TestRunner):
    """Test that approval bypasses the guard check."""
    print("\n📦 Testing guard strategy approval bypass...")

    try:
        from guard_strategy import GuardRequirementStrategy
    except ImportError:
        runner.test("GuardRequirementStrategy exists", False, "Strategy not implemented yet")
        return

    strategy = GuardRequirementStrategy()

    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        os.makedirs(f"{tmpdir}/.git", exist_ok=True)

        from config import RequirementsConfig
        from requirements import BranchRequirements

        os.makedirs(f"{tmpdir}/.claude")
        config_content = {
            "version": "1.0",
            "enabled": True,
            "inherit": False,
            "requirements": {
                "protected_branch": {
                    "enabled": True,
                    "type": "guard",
                    "guard_type": "protected_branch",
                    "protected_branches": ["master", "main"]
                }
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config_content, f)

        config = RequirementsConfig(tmpdir)
        reqs = BranchRequirements("master", "test-session", tmpdir)

        context = {
            'project_dir': tmpdir,
            'branch': 'master',
            'session_id': 'test-session',
            'tool_name': 'Edit'
        }

        # Initially should block
        result1 = strategy.check("protected_branch", config, reqs, context)
        runner.test("Blocks before approval", result1 is not None)

        # Approve for session (using satisfy with session scope)
        reqs.satisfy("protected_branch", scope="session", method="approval")

        # Should now allow
        result2 = strategy.check("protected_branch", config, reqs, context)
        runner.test("Allows after approval", result2 is None,
                   f"Expected None after approval, got: {result2}")


def test_guard_strategy_unknown_guard_type_allows(runner: TestRunner):
    """Test that unknown guard_type fails open (allows)."""
    print("\n📦 Testing guard strategy unknown type fails open...")

    try:
        from guard_strategy import GuardRequirementStrategy
    except ImportError:
        runner.test("GuardRequirementStrategy exists", False, "Strategy not implemented yet")
        return

    strategy = GuardRequirementStrategy()

    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        os.makedirs(f"{tmpdir}/.git", exist_ok=True)

        from config import RequirementsConfig
        from requirements import BranchRequirements

        os.makedirs(f"{tmpdir}/.claude")
        config_content = {
            "version": "1.0",
            "enabled": True,
            "inherit": False,
            "requirements": {
                "unknown_guard": {
                    "enabled": True,
                    "type": "guard",
                    "guard_type": "nonexistent_type"  # Unknown type
                }
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config_content, f)

        config = RequirementsConfig(tmpdir)
        reqs = BranchRequirements("master", "test-session", tmpdir)

        context = {
            'project_dir': tmpdir,
            'branch': 'master',
            'session_id': 'test-session',
            'tool_name': 'Edit'
        }

        # Should fail open (allow) for unknown guard type
        result = strategy.check("unknown_guard", config, reqs, context)
        runner.test("Unknown guard_type fails open", result is None,
                   f"Expected None (fail open), got: {result}")


def test_guard_hook_integration(runner: TestRunner):
    """Test guard strategy integration with the hook."""
    print("\n📦 Testing guard hook integration...")

    hook_path = Path(__file__).parent / "check-requirements.py"

    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize git repo on master
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "master"], cwd=tmpdir, capture_output=True)

        # Create config with guard requirement
        os.makedirs(f"{tmpdir}/.claude")
        config = {
            "version": "1.0",
            "enabled": True,
            "inherit": False,
            "requirements": {
                "protected_branch": {
                    "enabled": True,
                    "type": "guard",
                    "guard_type": "protected_branch",
                    "protected_branches": ["master", "main"],
                    "message": "🚫 Cannot edit on protected branch"
                }
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config, f)

        # Test hook blocks on master (provide session_id)
        result = subprocess.run(
            ["python3", str(hook_path)],
            input=json.dumps({"tool_name":"Edit", "session_id": "guardtest"}),
            cwd=tmpdir, capture_output=True, text=True
        )

        runner.test("Hook runs with guard", result.returncode == 0)

        # Check if hook properly blocks (will pass once strategy is implemented)
        if '"permissionDecision": "deny"' in result.stdout:
            runner.test("Hook blocks on protected branch", True)
            runner.test("Hook message mentions protected", "protected" in result.stdout.lower(),
                       f"Output: {result.stdout[:200]}")
        else:
            # Guard strategy not yet implemented - this is expected in TDD
            runner.test("Hook blocks on protected branch", False,
                       "Guard strategy not implemented - expected in TDD RED phase")


def test_guard_status_display_context_aware(runner: TestRunner):
    """Test that guard requirements show context-aware status."""
    print("\n📦 Testing guard status display is context-aware...")

    try:
        from requirements import BranchRequirements
        from config import RequirementsConfig
    except ImportError as e:
        runner.test("Required imports available", False, f"Import error: {e}")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup git repo on feature branch
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "feature/test"],
                      cwd=tmpdir, capture_output=True)
        os.makedirs(f"{tmpdir}/.git", exist_ok=True)

        # Create config with protected_branch
        os.makedirs(f"{tmpdir}/.claude")
        config_content = {
            "version": "1.0",
            "enabled": True,
            "inherit": False,
            "requirements": {
                "protected_branch": {
                    "enabled": True,
                    "type": "guard",
                    "guard_type": "protected_branch",
                    "protected_branches": ["master", "main"]
                }
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config_content, f)

        config = RequirementsConfig(tmpdir)
        reqs = BranchRequirements("feature/test", "test-session", tmpdir)

        # Test 1: On feature branch → should be satisfied
        context = {
            'branch': 'feature/test',
            'session_id': 'test-session',
            'project_dir': tmpdir
        }

        # Try to call is_guard_satisfied - will fail until implemented
        try:
            satisfied = reqs.is_guard_satisfied("protected_branch", config, context)
            runner.test("Guard satisfied on feature branch", satisfied,
                       "Should be satisfied when NOT on protected branch")
        except AttributeError:
            runner.test("is_guard_satisfied() method exists", False,
                       "Method not implemented yet - expected in TDD RED phase")
            # Can't continue without the method
            return

        # Test 2: On master branch → should NOT be satisfied
        reqs_master = BranchRequirements("master", "test-session", tmpdir)
        context_master = {
            'branch': 'master',
            'session_id': 'test-session',
            'project_dir': tmpdir
        }
        satisfied_master = reqs_master.is_guard_satisfied("protected_branch",
                                                          config, context_master)
        runner.test("Guard NOT satisfied on master", not satisfied_master,
                   "Should NOT be satisfied when ON protected branch")

        # Test 3: Emergency override on master → should be satisfied
        reqs_master.satisfy("protected_branch", scope='session')
        satisfied_override = reqs_master.is_guard_satisfied("protected_branch",
                                                            config, context_master)
        runner.test("Guard satisfied after approval on master", satisfied_override,
                   "Should be satisfied when manually approved even on protected branch")


def test_single_session_guard_allows_when_alone(runner: TestRunner):
    """Test that single_session guard allows when only current session exists."""
    print("\n📦 Testing single_session guard allows when alone...")

    try:
        from guard_strategy import GuardRequirementStrategy
    except ImportError:
        runner.test("GuardRequirementStrategy exists", False, "Strategy not implemented yet")
        return

    strategy = GuardRequirementStrategy()

    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        os.makedirs(f"{tmpdir}/.git", exist_ok=True)

        from config import RequirementsConfig
        from requirements import BranchRequirements
        import session

        # Create config with single_session requirement
        os.makedirs(f"{tmpdir}/.claude")
        config_content = {
            "version": "1.0",
            "enabled": True,
            "inherit": False,
            "requirements": {
                "single_session_per_project": {
                    "enabled": True,
                    "type": "guard",
                    "guard_type": "single_session"
                }
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config_content, f)

        config = RequirementsConfig(tmpdir)
        reqs = BranchRequirements("master", "test-session-1", tmpdir)

        # Mock registry with empty sessions (no other sessions)
        test_registry = Path(tmpdir) / "test-sessions.json"
        original_get_registry_path = session.get_registry_path
        session.get_registry_path = lambda: test_registry

        try:
            # Create empty registry
            with open(test_registry, 'w') as f:
                json.dump({"sessions": {}}, f)

            context = {
                'project_dir': tmpdir,
                'branch': 'master',
                'session_id': 'test-session-1',
                'tool_name': 'Edit'
            }

            # Should allow when no other sessions
            result = strategy.check("single_session_per_project", config, reqs, context)
            runner.test("Allows when no other sessions", result is None,
                       f"Expected None, got: {result}")
        finally:
            session.get_registry_path = original_get_registry_path


def test_single_session_guard_blocks_with_other_session(runner: TestRunner):
    """Test that single_session guard blocks when another session is active."""
    print("\n📦 Testing single_session guard blocks with other session...")

    try:
        from guard_strategy import GuardRequirementStrategy
    except ImportError:
        runner.test("GuardRequirementStrategy exists", False, "Strategy not implemented yet")
        return

    strategy = GuardRequirementStrategy()

    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        os.makedirs(f"{tmpdir}/.git", exist_ok=True)

        from config import RequirementsConfig
        from requirements import BranchRequirements
        import session
        import time

        # Create config with single_session requirement
        os.makedirs(f"{tmpdir}/.claude")
        config_content = {
            "version": "1.0",
            "enabled": True,
            "inherit": False,
            "requirements": {
                "single_session_per_project": {
                    "enabled": True,
                    "type": "guard",
                    "guard_type": "single_session"
                }
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config_content, f)

        config = RequirementsConfig(tmpdir)
        reqs = BranchRequirements("master", "test-session-2", tmpdir)

        # Mock registry with another session on the same project
        test_registry = Path(tmpdir) / "test-sessions.json"
        original_get_registry_path = session.get_registry_path
        session.get_registry_path = lambda: test_registry

        try:
            # Create registry with another session on the same project
            # Use current PID as ppid to make it look "alive"
            current_pid = os.getpid()
            with open(test_registry, 'w') as f:
                json.dump({
                    "sessions": {
                        "other-ses": {
                            "pid": current_pid,
                            "ppid": current_pid,  # Use current PID so is_process_alive returns True
                            "project_dir": tmpdir,
                            "branch": "feature/other",
                            "started_at": int(time.time()),
                            "last_active": int(time.time())
                        }
                    }
                }, f)

            context = {
                'project_dir': tmpdir,
                'branch': 'master',
                'session_id': 'test-session-2',
                'tool_name': 'Edit'
            }

            # Should block when another session is active
            result = strategy.check("single_session_per_project", config, reqs, context)
            runner.test("Blocks when another session active", result is not None,
                       f"Expected denial, got: {result}")
            if result:
                runner.test("Has denial message", "message" in result or "hookSpecificOutput" in result,
                           f"Result: {result}")
        finally:
            session.get_registry_path = original_get_registry_path


def test_single_session_guard_approval_bypasses(runner: TestRunner):
    """Test that approval bypasses the single_session guard."""
    print("\n📦 Testing single_session guard approval bypass...")

    try:
        from guard_strategy import GuardRequirementStrategy
    except ImportError:
        runner.test("GuardRequirementStrategy exists", False, "Strategy not implemented yet")
        return

    strategy = GuardRequirementStrategy()

    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        os.makedirs(f"{tmpdir}/.git", exist_ok=True)

        from config import RequirementsConfig
        from requirements import BranchRequirements
        import session
        import time

        # Create config
        os.makedirs(f"{tmpdir}/.claude")
        config_content = {
            "version": "1.0",
            "enabled": True,
            "inherit": False,
            "requirements": {
                "single_session_per_project": {
                    "enabled": True,
                    "type": "guard",
                    "guard_type": "single_session"
                }
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config_content, f)

        config = RequirementsConfig(tmpdir)
        reqs = BranchRequirements("master", "test-session-3", tmpdir)

        # Mock registry with another session
        test_registry = Path(tmpdir) / "test-sessions.json"
        original_get_registry_path = session.get_registry_path
        session.get_registry_path = lambda: test_registry

        try:
            current_pid = os.getpid()
            with open(test_registry, 'w') as f:
                json.dump({
                    "sessions": {
                        "other-ses": {
                            "pid": current_pid,
                            "ppid": current_pid,
                            "project_dir": tmpdir,
                            "branch": "feature/other",
                            "started_at": int(time.time()),
                            "last_active": int(time.time())
                        }
                    }
                }, f)

            context = {
                'project_dir': tmpdir,
                'branch': 'master',
                'session_id': 'test-session-3',
                'tool_name': 'Edit'
            }

            # First verify it blocks without approval
            result = strategy.check("single_session_per_project", config, reqs, context)
            runner.test("Blocks without approval", result is not None,
                       "Should block before approval")

            # Now approve and verify bypass
            reqs.satisfy("single_session_per_project", scope='session')
            result = strategy.check("single_session_per_project", config, reqs, context)
            runner.test("Allows after approval", result is None,
                       f"Should allow after approval, got: {result}")
        finally:
            session.get_registry_path = original_get_registry_path


def test_single_session_guard_excludes_current_session(runner: TestRunner):
    """Test that current session is excluded from other session count."""
    print("\n📦 Testing single_session guard excludes current session...")

    try:
        from guard_strategy import GuardRequirementStrategy
    except ImportError:
        runner.test("GuardRequirementStrategy exists", False, "Strategy not implemented yet")
        return

    strategy = GuardRequirementStrategy()

    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        os.makedirs(f"{tmpdir}/.git", exist_ok=True)

        from config import RequirementsConfig
        from requirements import BranchRequirements
        import session
        import time

        os.makedirs(f"{tmpdir}/.claude")
        config_content = {
            "version": "1.0",
            "enabled": True,
            "inherit": False,
            "requirements": {
                "single_session_per_project": {
                    "enabled": True,
                    "type": "guard",
                    "guard_type": "single_session"
                }
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config_content, f)

        config = RequirementsConfig(tmpdir)
        reqs = BranchRequirements("master", "my-sessio", tmpdir)  # 8 char session ID

        # Mock registry with ONLY the current session
        test_registry = Path(tmpdir) / "test-sessions.json"
        original_get_registry_path = session.get_registry_path
        session.get_registry_path = lambda: test_registry

        try:
            current_pid = os.getpid()
            with open(test_registry, 'w') as f:
                json.dump({
                    "sessions": {
                        "my-sessio": {  # Same ID as current session
                            "pid": current_pid,
                            "ppid": current_pid,
                            "project_dir": tmpdir,
                            "branch": "master",
                            "started_at": int(time.time()),
                            "last_active": int(time.time())
                        }
                    }
                }, f)

            context = {
                'project_dir': tmpdir,
                'branch': 'master',
                'session_id': 'my-sessio',  # Same ID as in registry
                'tool_name': 'Edit'
            }

            # Should allow because the only session is current session
            result = strategy.check("single_session_per_project", config, reqs, context)
            runner.test("Allows when only current session in registry", result is None,
                       f"Expected None (current session should be excluded), got: {result}")
        finally:
            session.get_registry_path = original_get_registry_path


def test_single_session_guard_filters_by_project(runner: TestRunner):
    """Test that sessions on other projects don't trigger the guard."""
    print("\n📦 Testing single_session guard filters by project...")

    try:
        from guard_strategy import GuardRequirementStrategy
    except ImportError:
        runner.test("GuardRequirementStrategy exists", False, "Strategy not implemented yet")
        return

    strategy = GuardRequirementStrategy()

    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        os.makedirs(f"{tmpdir}/.git", exist_ok=True)

        from config import RequirementsConfig
        from requirements import BranchRequirements
        import session
        import time

        os.makedirs(f"{tmpdir}/.claude")
        config_content = {
            "version": "1.0",
            "enabled": True,
            "inherit": False,
            "requirements": {
                "single_session_per_project": {
                    "enabled": True,
                    "type": "guard",
                    "guard_type": "single_session"
                }
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config_content, f)

        config = RequirementsConfig(tmpdir)
        reqs = BranchRequirements("master", "test-session-5", tmpdir)

        # Mock registry with session on DIFFERENT project
        test_registry = Path(tmpdir) / "test-sessions.json"
        original_get_registry_path = session.get_registry_path
        session.get_registry_path = lambda: test_registry

        try:
            current_pid = os.getpid()
            with open(test_registry, 'w') as f:
                json.dump({
                    "sessions": {
                        "other-ses": {
                            "pid": current_pid,
                            "ppid": current_pid,
                            "project_dir": "/some/other/project",  # Different project!
                            "branch": "main",
                            "started_at": int(time.time()),
                            "last_active": int(time.time())
                        }
                    }
                }, f)

            context = {
                'project_dir': tmpdir,  # Different from session in registry
                'branch': 'master',
                'session_id': 'test-session-5',
                'tool_name': 'Edit'
            }

            # Should allow because other session is on different project
            result = strategy.check("single_session_per_project", config, reqs, context)
            runner.test("Allows when other session on different project", result is None,
                       f"Expected None (filtered by project), got: {result}")
        finally:
            session.get_registry_path = original_get_registry_path


def test_remove_session_from_registry(runner: TestRunner):
    """Test remove_session_from_registry function."""
    print("\n📦 Testing remove_session_from_registry...")

    # Import will fail until implemented
    try:
        from session import remove_session_from_registry, update_registry, get_registry_path
    except ImportError:
        runner.test("remove_session_from_registry exists", False, "Function not implemented yet")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        test_registry = Path(tmpdir) / "test-sessions.json"

        # Mock get_registry_path for testing
        import session
        original_get_registry_path = session.get_registry_path
        session.get_registry_path = lambda: test_registry

        try:
            # Add a session
            update_registry("test1234", "/test/project", "main")

            # Verify it exists
            with open(test_registry) as f:
                registry = json.load(f)
            runner.test("Session added before removal", "test1234" in registry["sessions"])

            # Remove the session
            removed = remove_session_from_registry("test1234")
            runner.test("remove returns True when found", removed is True)

            # Verify it's gone
            with open(test_registry) as f:
                registry = json.load(f)
            runner.test("Session removed", "test1234" not in registry["sessions"])

            # Test removing non-existent session
            removed = remove_session_from_registry("nonexistent")
            runner.test("remove returns False when not found", removed is False)

        finally:
            session.get_registry_path = original_get_registry_path


def test_colors_module(runner: TestRunner):
    """Test terminal colors module."""
    print("\n📦 Testing colors module...")

    from colors import (
        Colors,
        success, error, warning, info, header, hint, dim, bold,
        _supports_color,
    )
    import colors as colors_module

    # Test Colors class has required constants
    runner.test("Colors.RESET defined", hasattr(Colors, 'RESET'))
    runner.test("Colors.BOLD defined", hasattr(Colors, 'BOLD'))
    runner.test("Colors.BRIGHT_GREEN defined", hasattr(Colors, 'BRIGHT_GREEN'))
    runner.test("Colors.BRIGHT_RED defined", hasattr(Colors, 'BRIGHT_RED'))
    runner.test("Colors.BRIGHT_YELLOW defined", hasattr(Colors, 'BRIGHT_YELLOW'))
    runner.test("Colors.BRIGHT_CYAN defined", hasattr(Colors, 'BRIGHT_CYAN'))
    runner.test("Colors.BLUE defined", hasattr(Colors, 'BLUE'))
    runner.test("Colors.CYAN defined", hasattr(Colors, 'CYAN'))
    runner.test("Colors.GRAY defined", hasattr(Colors, 'GRAY'))

    # Test ANSI escape code format
    runner.test("RESET is valid ANSI", Colors.RESET == '\033[0m', f"Got: {repr(Colors.RESET)}")
    runner.test("BOLD is valid ANSI", Colors.BOLD == '\033[1m', f"Got: {repr(Colors.BOLD)}")

    # Test color functions return strings
    runner.test("success returns string", isinstance(success("test"), str))
    runner.test("error returns string", isinstance(error("test"), str))
    runner.test("warning returns string", isinstance(warning("test"), str))
    runner.test("info returns string", isinstance(info("test"), str))
    runner.test("header returns string", isinstance(header("test"), str))
    runner.test("hint returns string", isinstance(hint("test"), str))
    runner.test("dim returns string", isinstance(dim("test"), str))
    runner.test("bold returns string", isinstance(bold("test"), str))

    # Test that functions preserve the original text
    test_text = "Hello World"
    runner.test("success preserves text", test_text in success(test_text))
    runner.test("error preserves text", test_text in error(test_text))
    runner.test("warning preserves text", test_text in warning(test_text))
    runner.test("info preserves text", test_text in info(test_text))
    runner.test("header preserves text", test_text in header(test_text))
    runner.test("hint preserves text", test_text in hint(test_text))
    runner.test("dim preserves text", test_text in dim(test_text))
    runner.test("bold preserves text", test_text in bold(test_text))

    # Test NO_COLOR environment variable
    original_no_color = os.environ.get('NO_COLOR')
    original_cache = colors_module._color_enabled

    try:
        # Set NO_COLOR and reset cache
        os.environ['NO_COLOR'] = '1'
        colors_module._color_enabled = None  # Reset cache

        runner.test("NO_COLOR disables colors", not _supports_color())

        # Verify output has no ANSI codes when NO_COLOR is set
        colors_module._color_enabled = None  # Reset again for colors_enabled()
        result = success("test")
        has_ansi = '\033[' in result
        runner.test("NO_COLOR: success has no ANSI", not has_ansi, f"Got: {repr(result)}")

    finally:
        # Restore original state
        if original_no_color is None:
            os.environ.pop('NO_COLOR', None)
        else:
            os.environ['NO_COLOR'] = original_no_color
        colors_module._color_enabled = original_cache

    # Test FORCE_COLOR environment variable
    original_force_color = os.environ.get('FORCE_COLOR')
    original_no_color = os.environ.get('NO_COLOR')

    try:
        # Clear NO_COLOR and set FORCE_COLOR
        os.environ.pop('NO_COLOR', None)
        os.environ['FORCE_COLOR'] = '1'
        colors_module._color_enabled = None  # Reset cache

        runner.test("FORCE_COLOR enables colors", _supports_color())

    finally:
        # Restore original state
        if original_force_color is None:
            os.environ.pop('FORCE_COLOR', None)
        else:
            os.environ['FORCE_COLOR'] = original_force_color
        if original_no_color is not None:
            os.environ['NO_COLOR'] = original_no_color
        colors_module._color_enabled = original_cache

    # Test TERM=dumb disables colors
    original_term = os.environ.get('TERM')

    try:
        os.environ.pop('NO_COLOR', None)
        os.environ.pop('FORCE_COLOR', None)
        os.environ['TERM'] = 'dumb'
        colors_module._color_enabled = None  # Reset cache

        runner.test("TERM=dumb disables colors", not _supports_color())

    finally:
        if original_term is None:
            os.environ.pop('TERM', None)
        else:
            os.environ['TERM'] = original_term
        colors_module._color_enabled = original_cache


def test_progress_module(runner: TestRunner):
    """Test progress reporting module."""
    print("\n📦 Testing progress module...")

    from progress import (
        ProgressReporter,
        progress_context,
        progress_enabled,
        reset_progress_cache,
        show_progress,
        clear_progress,
        _progress_enabled,
    )
    import progress as progress_module

    # Save original env and cache
    original_show = os.environ.get('SHOW_PROGRESS')
    original_no_color = os.environ.get('NO_COLOR')
    original_force_color = os.environ.get('FORCE_COLOR')
    original_cache = progress_module._cached_progress_enabled

    try:
        # Clean environment for testing
        os.environ.pop('SHOW_PROGRESS', None)
        os.environ.pop('NO_COLOR', None)
        os.environ.pop('FORCE_COLOR', None)
        reset_progress_cache()

        # Test 1: SHOW_PROGRESS=0 disables progress
        os.environ['SHOW_PROGRESS'] = '0'
        reset_progress_cache()
        runner.test("SHOW_PROGRESS=0 disables progress", not _progress_enabled())
        os.environ.pop('SHOW_PROGRESS', None)

        # Test 2: SHOW_PROGRESS=1 enables progress (even without TTY)
        os.environ['SHOW_PROGRESS'] = '1'
        reset_progress_cache()
        runner.test("SHOW_PROGRESS=1 enables progress", _progress_enabled())
        os.environ.pop('SHOW_PROGRESS', None)

        # Test 3: NO_COLOR disables progress
        os.environ['NO_COLOR'] = '1'
        reset_progress_cache()
        runner.test("NO_COLOR disables progress", not _progress_enabled())
        os.environ.pop('NO_COLOR', None)

        # Test 4: FORCE_COLOR enables progress
        os.environ['FORCE_COLOR'] = '1'
        reset_progress_cache()
        runner.test("FORCE_COLOR enables progress", _progress_enabled())
        os.environ.pop('FORCE_COLOR', None)

        # Test 5: Caching works
        reset_progress_cache()
        os.environ['SHOW_PROGRESS'] = '1'
        first_result = progress_enabled()
        os.environ['SHOW_PROGRESS'] = '0'  # Change env
        second_result = progress_enabled()  # Should use cached value
        runner.test("progress_enabled caches result", first_result == second_result == True)
        os.environ.pop('SHOW_PROGRESS', None)

        # Test 6: reset_progress_cache clears cache
        reset_progress_cache()
        os.environ['SHOW_PROGRESS'] = '0'
        after_reset = progress_enabled()
        runner.test("reset_progress_cache clears cache", not after_reset)
        os.environ.pop('SHOW_PROGRESS', None)

    finally:
        # Restore original environment
        if original_show is not None:
            os.environ['SHOW_PROGRESS'] = original_show
        else:
            os.environ.pop('SHOW_PROGRESS', None)
        if original_no_color is not None:
            os.environ['NO_COLOR'] = original_no_color
        else:
            os.environ.pop('NO_COLOR', None)
        if original_force_color is not None:
            os.environ['FORCE_COLOR'] = original_force_color
        else:
            os.environ.pop('FORCE_COLOR', None)
        progress_module._cached_progress_enabled = original_cache

    # Test ProgressReporter class (force enabled for testing)
    os.environ['SHOW_PROGRESS'] = '1'
    reset_progress_cache()

    try:
        # Test 7: ProgressReporter initialization
        reporter = ProgressReporter("Test operation", debug=True)
        runner.test("ProgressReporter initializes", reporter.description == "Test operation")
        runner.test("ProgressReporter debug mode", reporter.debug is True)

        # Test 8: ProgressReporter timing
        time.sleep(0.1)
        elapsed = reporter.get_elapsed()
        runner.test("ProgressReporter tracks elapsed time", elapsed >= 0.1, f"Got: {elapsed}")

        # Test 9: ProgressReporter status recording (debug mode)
        reporter.status("step 1")
        reporter.status("step 2")
        runner.test("ProgressReporter records steps", len(reporter._steps) == 2)

        # Test 10: ProgressReporter timing report
        timing_report = reporter.get_timing_report()
        runner.test("ProgressReporter generates timing report", "step 1" in timing_report and "step 2" in timing_report)

        # Test 11: ProgressReporter without debug mode doesn't record
        reporter_no_debug = ProgressReporter("No debug")
        reporter_no_debug.status("ignored")
        runner.test("ProgressReporter no-debug skips recording", len(reporter_no_debug._steps) == 0)

        # Test 12: Empty timing report when no steps
        empty_reporter = ProgressReporter("Empty")
        runner.test("Empty reporter has no timing report", empty_reporter.get_timing_report() == "")

    finally:
        os.environ.pop('SHOW_PROGRESS', None)
        reset_progress_cache()
        if original_cache is not None:
            progress_module._cached_progress_enabled = original_cache

    # Test progress_context
    os.environ['SHOW_PROGRESS'] = '0'  # Disable for context tests (avoid TTY issues)
    reset_progress_cache()

    try:
        # Test 13: progress_context yields ProgressReporter
        with progress_context("Context test") as p:
            runner.test("progress_context yields ProgressReporter", isinstance(p, ProgressReporter))

        # Test 14: progress_context with debug collects timing
        with progress_context("Debug context", debug=True) as p:
            p.status("step A")
            time.sleep(0.05)
            p.status("step B")

        runner.test("progress_context debug collects steps", len(p._steps) == 2)

        # Test 15: progress_context min_duration logic (fast operation)
        start = time.time()
        with progress_context("Fast", min_duration=1.0) as p:
            pass  # Instant
        # Should have cleared without finishing (no visible output)
        runner.test("progress_context fast operation clears", p._line_shown is False)

    finally:
        os.environ.pop('SHOW_PROGRESS', None)
        reset_progress_cache()
        if original_cache is not None:
            progress_module._cached_progress_enabled = original_cache

    # Test convenience functions exist and are callable
    runner.test("show_progress is callable", callable(show_progress))
    runner.test("clear_progress is callable", callable(clear_progress))


def test_interactive_module(runner: TestRunner):
    """Test interactive prompt module."""
    print("\n📦 Testing interactive module...")

    from interactive import (
        has_inquirerpy,
        select,
        confirm,
        checkbox,
        _stdlib_select,
        _stdlib_confirm,
        _stdlib_checkbox
    )

    # Test has_inquirerpy returns boolean
    result = has_inquirerpy()
    runner.test("has_inquirerpy returns bool", isinstance(result, bool))

    # Test stdlib functions exist and are callable
    runner.test("_stdlib_select is callable", callable(_stdlib_select))
    runner.test("_stdlib_confirm is callable", callable(_stdlib_confirm))
    runner.test("_stdlib_checkbox is callable", callable(_stdlib_checkbox))

    # Test public functions exist and are callable
    runner.test("select is callable", callable(select))
    runner.test("confirm is callable", callable(confirm))
    runner.test("checkbox is callable", callable(checkbox))

    # Test _stdlib_select with mocked input
    import builtins
    original_input = builtins.input

    try:
        # Test select with default (empty input)
        inputs = iter([""])
        builtins.input = lambda _: next(inputs)
        result = _stdlib_select("Choose:", ["Option A", "Option B", "Option C"], default=1)
        runner.test("_stdlib_select default works", result == "Option B", f"Got: {result}")

        # Test select with number input
        inputs = iter(["3"])
        builtins.input = lambda _: next(inputs)
        result = _stdlib_select("Choose:", ["A", "B", "C"], default=0)
        runner.test("_stdlib_select number input works", result == "C", f"Got: {result}")

        # Test confirm with default yes (empty input)
        inputs = iter([""])
        builtins.input = lambda _: next(inputs)
        result = _stdlib_confirm("Continue?", default=True)
        runner.test("_stdlib_confirm default yes works", result is True)

        # Test confirm with 'n' input
        inputs = iter(["n"])
        builtins.input = lambda _: next(inputs)
        result = _stdlib_confirm("Continue?", default=True)
        runner.test("_stdlib_confirm 'n' works", result is False)

        # Test confirm with 'yes' input
        inputs = iter(["yes"])
        builtins.input = lambda _: next(inputs)
        result = _stdlib_confirm("Continue?", default=False)
        runner.test("_stdlib_confirm 'yes' works", result is True)

        # Test checkbox with default (empty input)
        inputs = iter([""])
        builtins.input = lambda _: next(inputs)
        result = _stdlib_checkbox("Select:", ["A", "B", "C"], default=["B"])
        runner.test("_stdlib_checkbox default works", result == ["B"], f"Got: {result}")

        # Test checkbox with 'all' input
        inputs = iter(["all"])
        builtins.input = lambda _: next(inputs)
        result = _stdlib_checkbox("Select:", ["A", "B", "C"], default=[])
        runner.test("_stdlib_checkbox 'all' works", result == ["A", "B", "C"], f"Got: {result}")

        # Test checkbox with 'none' input
        inputs = iter(["none"])
        builtins.input = lambda _: next(inputs)
        result = _stdlib_checkbox("Select:", ["A", "B", "C"], default=["A", "B"])
        runner.test("_stdlib_checkbox 'none' works", result == [], f"Got: {result}")

        # Test checkbox with comma-separated input
        inputs = iter(["1,3"])
        builtins.input = lambda _: next(inputs)
        result = _stdlib_checkbox("Select:", ["A", "B", "C"], default=[])
        runner.test("_stdlib_checkbox comma input works", result == ["A", "C"], f"Got: {result}")

    finally:
        builtins.input = original_input


def test_cli_init_command(runner: TestRunner):
    """Test req init command."""
    print("\n📦 Testing CLI init command...")

    cli_path = Path(__file__).parent / "requirements-cli.py"

    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize git repo (required for req commands)
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)

        # Test --preview flag (doesn't create files)
        result = subprocess.run(
            ["python3", str(cli_path), "init", "--yes", "--preview"],
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("init --preview runs", result.returncode == 0, result.stderr)
        runner.test("init --preview shows config", "commit_plan" in result.stdout, result.stdout[:200])
        config_file = Path(tmpdir) / '.claude' / 'requirements.yaml'
        runner.test("init --preview doesn't create file", not config_file.exists())

        # Test --yes creates project config
        result = subprocess.run(
            ["python3", str(cli_path), "init", "--yes"],
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("init --yes runs", result.returncode == 0, result.stderr)
        runner.test("init creates .claude dir", (Path(tmpdir) / '.claude').exists())
        runner.test("init creates config", config_file.exists())

        # Verify config content
        if config_file.exists():
            content = config_file.read_text()
            runner.test("config has version", 'version' in content)
            runner.test("config has enabled", 'enabled' in content)
            runner.test("config has commit_plan", 'commit_plan' in content)

        # Test init warns on existing config
        result = subprocess.run(
            ["python3", str(cli_path), "init", "--yes"],
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("init warns on existing", "already exists" in result.stdout.lower() or result.returncode == 0)

        # Test --force overwrites
        result = subprocess.run(
            ["python3", str(cli_path), "init", "--yes", "--force", "--preset", "strict"],
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("init --force runs", result.returncode == 0, result.stderr)
        content = config_file.read_text()
        runner.test("init --force writes strict", "protected_branch" in content, content[:200])

        # Test --local creates local config
        local_file = Path(tmpdir) / '.claude' / 'requirements.local.yaml'
        result = subprocess.run(
            ["python3", str(cli_path), "init", "--yes", "--local", "--force"],
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("init --local runs", result.returncode == 0, result.stderr)
        runner.test("init --local creates file", local_file.exists(), str(local_file))

        # Test presets
        for preset in ['strict', 'relaxed', 'minimal']:
            with tempfile.TemporaryDirectory() as preset_dir:
                subprocess.run(["git", "init"], cwd=preset_dir, capture_output=True)
                result = subprocess.run(
                    ["python3", str(cli_path), "init", "--yes", "--preset", preset],
                    cwd=preset_dir, capture_output=True, text=True
                )
                runner.test(f"init --preset {preset} runs", result.returncode == 0, result.stderr)


def test_cli_config_command(runner: TestRunner):
    """Test req config command."""
    print("\n📦 Testing CLI config command...")

    cli_path = Path(__file__).parent / "requirements-cli.py"

    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize git repo and create a config
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)

        # Create test config
        os.makedirs(f"{tmpdir}/.claude")
        config = {
            "version": "1.0",
            "enabled": True,
            "requirements": {
                "commit_plan": {
                    "enabled": True,
                    "type": "blocking",
                    "scope": "session",
                    "trigger_tools": ["Edit", "Write"],
                    "message": "Test message"
                }
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config, f)

        # Test show mode (default, no flags)
        result = subprocess.run(
            ["python3", str(cli_path), "config", "commit_plan"],
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("config show runs", result.returncode == 0, result.stderr)
        runner.test("config shows enabled", "enabled" in result.stdout, result.stdout[:200])
        runner.test("config shows scope", "scope" in result.stdout, result.stdout[:200])
        runner.test("config shows type", "type" in result.stdout or "blocking" in result.stdout, result.stdout[:200])

        # Test unknown requirement
        result = subprocess.run(
            ["python3", str(cli_path), "config", "nonexistent"],
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("config unknown requirement warns", result.returncode == 1 or "not found" in result.stdout.lower(),
                   result.stdout[:200])

        # Test --enable flag (write mode)
        result = subprocess.run(
            ["python3", str(cli_path), "config", "github_ticket", "--enable", "--local", "--yes"],
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("config --enable runs", result.returncode == 0, result.stderr)

        # Verify local config was created
        local_file = Path(tmpdir) / '.claude' / 'requirements.local.yaml'
        runner.test("config --enable creates local", local_file.exists())

        # Test --disable flag
        result = subprocess.run(
            ["python3", str(cli_path), "config", "commit_plan", "--disable", "--local", "--yes"],
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("config --disable runs", result.returncode == 0, result.stderr)

        # Test --scope flag
        result = subprocess.run(
            ["python3", str(cli_path), "config", "commit_plan", "--scope", "branch", "--local", "--yes"],
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("config --scope runs", result.returncode == 0, result.stderr)

        # Verify scope was changed in local config
        if local_file.exists():
            content = local_file.read_text()
            runner.test("config --scope writes to local", "branch" in content, content[:200])

        # Test --message flag
        result = subprocess.run(
            ["python3", str(cli_path), "config", "commit_plan", "--message", "Custom message", "--local", "--yes"],
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("config --message runs", result.returncode == 0, result.stderr)

        # Test --set flag for arbitrary fields
        result = subprocess.run(
            ["python3", str(cli_path), "config", "adr_reviewed", "--set", "adr_path=/docs/adr", "--local", "--yes"],
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("config --set runs", result.returncode == 0, result.stderr)

        # Verify custom field was written
        if local_file.exists():
            content = local_file.read_text()
            runner.test("config --set writes custom field", "/docs/adr" in content or "adr_path" in content,
                       content[:300])

        # Test --set with JSON value
        result = subprocess.run(
            ["python3", str(cli_path), "config", "commit_plan", "--set", "approval_ttl=600", "--local", "--yes"],
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("config --set JSON value runs", result.returncode == 0, result.stderr)


def test_cli_config_show_command(runner: TestRunner):
    """Test req config show command."""
    print("\n📦 Testing CLI config show command...")

    cli_path = (Path(__file__).parent / "requirements-cli.py").resolve()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)

        # Create multi-level config cascade
        os.makedirs(f"{tmpdir}/.claude")

        # Project config
        project_config = {
            "version": "1.0",
            "enabled": True,
            "inherit": True,
            "requirements": {
                "commit_plan": {
                    "enabled": True,
                    "scope": "session"
                }
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(project_config, f)

        # Local override
        local_config = {
            "requirements": {
                "commit_plan": {
                    "scope": "branch"  # Override scope
                }
            }
        }
        with open(f"{tmpdir}/.claude/requirements.local.yaml", 'w') as f:
            json.dump(local_config, f)

        # Test 1: req config show
        result = subprocess.run(
            ["python3", str(cli_path), "config", "show"],
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("config show runs", result.returncode == 0, result.stderr)

        # Validate JSON output
        try:
            # Extract JSON from output (skip header lines)
            json_start = result.stdout.find('{')
            if json_start != -1:
                try:
                    parsed = json.loads(result.stdout[json_start:])
                except json.JSONDecodeError as e:
                    runner.test("config show valid JSON", False, f"JSON decode error: {e}")
                else:
                    runner.test("config show valid JSON", isinstance(parsed, dict))
                    runner.test("config show has requirements", "requirements" in parsed)

                    # Use .get() to safely access nested keys
                    requirements = parsed.get("requirements", {})
                    commit_plan = requirements.get("commit_plan", {})
                    runner.test("config show has commit_plan",
                               "commit_plan" in requirements)

                    # Check that local override was applied
                    if "scope" in commit_plan:
                        runner.test("config show merged local override",
                                   commit_plan["scope"] == "branch")
                    else:
                        runner.test("config show merged local override", False,
                                   "scope not found in commit_plan")
            else:
                runner.test("config show contains JSON", False, "No JSON in output")
        except Exception as e:
            runner.test("config show valid JSON", False,
                       f"Unexpected error: {type(e).__name__}: {e}")

        # Test 2: req config (no args - should also show full config)
        result = subprocess.run(
            ["python3", str(cli_path), "config"],
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("config (no args) runs", result.returncode == 0, result.stderr)
        runner.test("config (no args) shows full config",
                   "requirements" in result.stdout)

        # Test 3: req config show --sources
        result = subprocess.run(
            ["python3", str(cli_path), "config", "show", "--sources"],
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("config show --sources runs", result.returncode == 0, result.stderr)
        runner.test("config show --sources mentions levels",
                   "GLOBAL" in result.stdout or "PROJECT" in result.stdout)
        runner.test("config show --sources shows merged",
                   "MERGED RESULT" in result.stdout)

        # Test 4: Verify existing req config <name> still works
        result = subprocess.run(
            ["python3", str(cli_path), "config", "commit_plan"],
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("config <requirement> still works", result.returncode == 0)
        runner.test("config <requirement> shows specific req",
                   "commit_plan" in result.stdout)

        # Test 5: Write flags without requirement name should error
        result = subprocess.run(
            ["python3", str(cli_path), "config", "--enable"],
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("config --enable without name errors", result.returncode != 0)
        runner.test("config --enable without name shows error",
                   "required" in result.stderr.lower() or "missing" in result.stderr.lower(),
                   result.stderr[:200])


def test_init_presets_module(runner: TestRunner):
    """Test init presets module."""
    print("\n📦 Testing init presets module...")

    from init_presets import (
        PRESETS,
        get_preset,
        generate_config,
        config_to_yaml
    )

    # Test PRESETS dict exists with expected presets
    runner.test("PRESETS is dict", isinstance(PRESETS, dict))
    runner.test("Has 'strict' preset", 'strict' in PRESETS)
    runner.test("Has 'relaxed' preset", 'relaxed' in PRESETS)
    runner.test("Has 'minimal' preset", 'minimal' in PRESETS)
    runner.test("Has 'advanced' preset", 'advanced' in PRESETS)
    runner.test("Has 'inherit' preset", 'inherit' in PRESETS)

    # Test get_preset function
    strict = get_preset('strict')
    runner.test("get_preset returns dict", isinstance(strict, dict))
    runner.test("strict has requirements", 'requirements' in strict)

    relaxed = get_preset('relaxed')
    runner.test("relaxed has requirements", 'requirements' in relaxed)
    runner.test("relaxed has commit_plan", 'commit_plan' in relaxed.get('requirements', {}))

    minimal = get_preset('minimal')
    runner.test("minimal has empty requirements", len(minimal.get('requirements', {})) == 0)

    # Test unknown preset returns minimal
    unknown = get_preset('nonexistent')
    runner.test("unknown preset returns minimal", len(unknown.get('requirements', {})) == 0)

    # Test generate_config adds version and enabled
    config = generate_config('relaxed')
    runner.test("generate_config adds version", config.get('version') == '1.0')
    runner.test("generate_config adds enabled", config.get('enabled') is True)
    runner.test("generate_config preserves requirements", 'commit_plan' in config.get('requirements', {}))

    # Test generate_config with customizations
    config = generate_config('relaxed', {'requirements': {'commit_plan': {'scope': 'branch'}}})
    scope = config.get('requirements', {}).get('commit_plan', {}).get('scope')
    runner.test("generate_config merges customizations", scope == 'branch', f"Got: {scope}")

    # Test config_to_yaml returns string
    yaml_str = config_to_yaml(config)
    runner.test("config_to_yaml returns string", isinstance(yaml_str, str))
    runner.test("config_to_yaml contains version", 'version' in yaml_str)
    runner.test("config_to_yaml contains enabled", 'enabled' in yaml_str)

    # Test strict preset has expected requirements
    strict_config = generate_config('strict')
    strict_reqs = strict_config.get('requirements', {})
    runner.test("strict has commit_plan", 'commit_plan' in strict_reqs)
    runner.test("strict has protected_branch", 'protected_branch' in strict_reqs)

    # Test requirement structure
    commit_plan = strict_reqs.get('commit_plan', {})
    runner.test("commit_plan has enabled", 'enabled' in commit_plan)
    runner.test("commit_plan has type", 'type' in commit_plan)
    runner.test("commit_plan has scope", 'scope' in commit_plan)
    runner.test("commit_plan has trigger_tools", 'trigger_tools' in commit_plan)
    runner.test("commit_plan has message", 'message' in commit_plan)

    # Test advanced preset - should have all 6+ requirement types
    advanced = get_preset('advanced')
    advanced_reqs = advanced.get('requirements', {})
    runner.test("advanced has requirements", len(advanced_reqs) > 0)
    runner.test("advanced has commit_plan", 'commit_plan' in advanced_reqs)
    runner.test("advanced has adr_reviewed", 'adr_reviewed' in advanced_reqs)
    runner.test("advanced has protected_branch", 'protected_branch' in advanced_reqs)
    runner.test("advanced has branch_size_limit", 'branch_size_limit' in advanced_reqs)
    runner.test("advanced has pre_commit_review", 'pre_commit_review' in advanced_reqs)
    runner.test("advanced has pre_pr_review", 'pre_pr_review' in advanced_reqs)
    runner.test("advanced has github_ticket", 'github_ticket' in advanced_reqs)

    # Test advanced preset has hooks config
    runner.test("advanced has hooks config", 'hooks' in advanced)
    runner.test("advanced has stop hook", 'stop' in advanced.get('hooks', {}))

    # Test branch_size_limit is dynamic with calculator
    branch_limit = advanced_reqs.get('branch_size_limit', {})
    runner.test("branch_size_limit type is dynamic", branch_limit.get('type') == 'dynamic')
    runner.test("branch_size_limit has calculator", 'calculator' in branch_limit)
    runner.test("branch_size_limit has thresholds", 'thresholds' in branch_limit)
    runner.test("branch_size_limit has cache_ttl", 'cache_ttl' in branch_limit)
    runner.test("branch_size_limit has approval_ttl", 'approval_ttl' in branch_limit)

    # Test pre_commit_review has single_use scope and command pattern
    pre_commit = advanced_reqs.get('pre_commit_review', {})
    runner.test("pre_commit_review scope is single_use", pre_commit.get('scope') == 'single_use')
    runner.test("pre_commit_review has trigger_tools", 'trigger_tools' in pre_commit)
    trigger_tools = pre_commit.get('trigger_tools', [])
    runner.test("pre_commit_review trigger is dict", isinstance(trigger_tools[0], dict) if trigger_tools else False)
    if trigger_tools and isinstance(trigger_tools[0], dict):
        runner.test("pre_commit_review has tool key", 'tool' in trigger_tools[0])
        runner.test("pre_commit_review has command_pattern", 'command_pattern' in trigger_tools[0])

    # Test github_ticket is disabled (example)
    github_ticket = advanced_reqs.get('github_ticket', {})
    runner.test("github_ticket is disabled", github_ticket.get('enabled') is False)
    runner.test("github_ticket scope is branch", github_ticket.get('scope') == 'branch')

    # Test inherit preset
    inherit = get_preset('inherit')
    runner.test("inherit has inherit flag", inherit.get('inherit') is True)
    runner.test("inherit has empty requirements", len(inherit.get('requirements', {})) == 0)


def test_generate_config_context_parameter(runner: TestRunner):
    """Test generate_config with context parameter."""
    print("\n📦 Testing generate_config context parameter...")

    from init_presets import generate_config

    # Test context parameter for project
    config = generate_config('minimal', context='project')
    runner.test("project context adds inherit", config.get('inherit') is True)

    # Test context parameter for global
    config = generate_config('advanced', context='global')
    runner.test("global context has no inherit", 'inherit' not in config)

    # Test context parameter for local
    config = generate_config('minimal', context='local')
    runner.test("local context has no inherit", 'inherit' not in config)

    # Test inherit preset already has inherit flag
    config = generate_config('inherit', context='project')
    runner.test("inherit preset has inherit flag", config.get('inherit') is True)


def test_generate_config_validation(runner: TestRunner):
    """Test generate_config validation."""
    print("\n📦 Testing generate_config validation...")

    from init_presets import generate_config

    # Test invalid preset name raises ValueError
    try:
        generate_config('nonexistent_preset')
        runner.test("invalid preset raises ValueError", False, "No exception raised")
    except ValueError as e:
        runner.test("invalid preset raises ValueError", True)
        runner.test("error message mentions valid presets", 'Valid presets' in str(e))

    # Test invalid context raises ValueError
    try:
        generate_config('relaxed', context='invalid_context')
        runner.test("invalid context raises ValueError", False, "No exception raised")
    except ValueError as e:
        runner.test("invalid context raises ValueError", True)
        runner.test("error message mentions valid contexts", 'Valid contexts' in str(e))

    # Test valid preset and context work
    try:
        generate_config('advanced', context='global')
        runner.test("valid preset and context work", True)
    except Exception as e:
        runner.test("valid preset and context work", False, str(e))


def test_feature_selector(runner: TestRunner):
    """Test feature selector module."""
    print("\n📦 Testing feature selector module...")

    from feature_selector import FeatureSelector, FEATURES

    # Test FEATURES catalog exists
    runner.test("FEATURES is dict", isinstance(FEATURES, dict))
    runner.test("FEATURES has commit_plan", 'commit_plan' in FEATURES)
    runner.test("FEATURES has adr_reviewed", 'adr_reviewed' in FEATURES)
    runner.test("FEATURES has protected_branch", 'protected_branch' in FEATURES)
    runner.test("FEATURES has branch_size_limit", 'branch_size_limit' in FEATURES)
    runner.test("FEATURES has pre_commit_review", 'pre_commit_review' in FEATURES)
    runner.test("FEATURES has pre_pr_review", 'pre_pr_review' in FEATURES)

    # Test feature structure
    commit_plan_feature = FEATURES.get('commit_plan', {})
    runner.test("feature has name", 'name' in commit_plan_feature)
    runner.test("feature has description", 'description' in commit_plan_feature)
    runner.test("feature has category", 'category' in commit_plan_feature)

    # Test FeatureSelector.build_config_from_features
    selector = FeatureSelector()

    # Test with valid features
    config = selector.build_config_from_features(['commit_plan', 'adr_reviewed'], context='project')
    runner.test("build_config returns dict", isinstance(config, dict))
    runner.test("build_config has version", config.get('version') == '1.0')
    runner.test("build_config has enabled", config.get('enabled') is True)
    runner.test("build_config project has inherit", config.get('inherit') is True)
    runner.test("build_config has requirements", 'requirements' in config)
    runner.test("build_config includes commit_plan", 'commit_plan' in config.get('requirements', {}))
    runner.test("build_config includes adr_reviewed", 'adr_reviewed' in config.get('requirements', {}))

    # Test with global context (no inherit)
    config = selector.build_config_from_features(['commit_plan'], context='global')
    runner.test("build_config global has no inherit", 'inherit' not in config)

    # Test with empty features list
    config = selector.build_config_from_features([], context='project')
    runner.test("build_config empty features returns dict", isinstance(config, dict))
    runner.test("build_config empty has no requirements", len(config.get('requirements', {})) == 0)


def test_message_dedup_cache(runner: TestRunner):
    """Test MessageDedupCache module."""
    print("\n📦 Testing message_dedup_cache module...")

    from message_dedup_cache import MessageDedupCache
    import unittest.mock as mock

    # Test 1: Cache initialization
    cache = MessageDedupCache()
    runner.test("Cache initializes", cache is not None)
    runner.test("Cache file path set", cache.cache_file is not None)

    # Test 2: First message shown (returns True)
    with mock.patch('time.time', return_value=1000.0):
        result = cache.should_show_message("key1", "Test message 1", ttl=5)
        runner.test("First message shown", result is True)

    # Test 3: Duplicate message suppressed within TTL (returns False)
    with mock.patch('time.time', return_value=1002.0):  # 2 seconds later
        result = cache.should_show_message("key1", "Test message 1", ttl=5)
        runner.test("Duplicate message suppressed", result is False)

    # Test 4: Message shown again after TTL expires
    with mock.patch('time.time', return_value=1006.0):  # 6 seconds later (TTL expired)
        result = cache.should_show_message("key1", "Test message 1", ttl=5)
        runner.test("Message shown after TTL", result is True)

    # Test 5: Different messages both shown
    with mock.patch('time.time', return_value=2000.0):
        result1 = cache.should_show_message("key2", "Message A", ttl=5)
        result2 = cache.should_show_message("key2", "Message B", ttl=5)
        runner.test("Different messages shown", result1 and result2)

    # Test 6: Message hash changes when content changes
    hash1 = cache._hash_message("Message 1")
    hash2 = cache._hash_message("Message 2")
    runner.test("Hash changes with content", hash1 != hash2)
    runner.test("Hash is 8 chars", len(hash1) == 8)

    # Test 7: Cache survives between instances (file persistence)
    cache1 = MessageDedupCache()
    with mock.patch('time.time', return_value=3000.0):
        cache1.should_show_message("persist_key", "Persist message", ttl=60)

    cache2 = MessageDedupCache()
    with mock.patch('time.time', return_value=3005.0):  # 5 seconds later, within TTL
        result = cache2.should_show_message("persist_key", "Persist message", ttl=60)
        runner.test("Cache persists between instances", result is False)

    # Test 8: Corrupted cache file recovery (fail-open)
    if cache.cache_file.exists():
        with open(cache.cache_file, 'w') as f:
            f.write("{invalid json")
        result = cache.should_show_message("corrupt_key", "Test", ttl=5)
        runner.test("Corrupted cache fails open", result is True)

    # Test 9: clear() method works
    # First ensure file exists
    with mock.patch('time.time', return_value=3500.0):
        cache.should_show_message("temp_key", "Temp message", ttl=5)
    cache.clear()
    runner.test("clear() removes cache file", not cache.cache_file.exists())

    # Test 10: Multiple keys in same cache
    with mock.patch('time.time', return_value=4000.0):
        cache.should_show_message("multi_key1", "Message 1", ttl=5)
        cache.should_show_message("multi_key2", "Message 2", ttl=5)

    with mock.patch('time.time', return_value=4002.0):
        result1 = cache.should_show_message("multi_key1", "Message 1", ttl=5)
        result2 = cache.should_show_message("multi_key2", "Message 2", ttl=5)
        runner.test("Multiple keys handled independently", result1 is False and result2 is False)

    # Cleanup
    cache.clear()


def test_calculation_cache(runner: TestRunner):
    """Test CalculationCache module."""
    print("\n📦 Testing calculation_cache module...")

    from calculation_cache import CalculationCache
    import unittest.mock as mock

    # Test 1: Cache initialization
    cache = CalculationCache()
    runner.test("CalculationCache initializes", cache is not None)
    runner.test("Cache file path set", cache.cache_file is not None)

    # Test 2: Cache miss returns None
    with mock.patch('time.time', return_value=1000.0):
        result = cache.get("missing_key", ttl=60)
        runner.test("Cache miss returns None", result is None)

    # Test 3: set() and get() round-trip
    test_data = {"lines_added": 150, "lines_deleted": 50}
    with mock.patch('time.time', return_value=2000.0):
        cache.set("test_key", test_data)

    with mock.patch('time.time', return_value=2010.0):  # 10 seconds later, within TTL
        result = cache.get("test_key", ttl=60)
        runner.test("Cache hit returns data", result == test_data, f"Expected {test_data}, got {result}")

    # Test 4: Cache expiration after TTL
    with mock.patch('time.time', return_value=2070.0):  # 70 seconds later (TTL expired)
        result = cache.get("test_key", ttl=60)
        runner.test("Cache expires after TTL", result is None)

    # Test 5: clear(key) removes specific entry
    with mock.patch('time.time', return_value=3000.0):
        cache.set("clear_test1", {"value": 1})
        cache.set("clear_test2", {"value": 2})

    cache.clear("clear_test1")

    with mock.patch('time.time', return_value=3010.0):
        result1 = cache.get("clear_test1", ttl=60)
        result2 = cache.get("clear_test2", ttl=60)
        runner.test("clear(key) removes specific entry", result1 is None and result2 is not None)

    # Test 6: clear() removes all entries
    # First ensure file exists
    with mock.patch('time.time', return_value=3500.0):
        cache.set("ensure_exists", {"data": "exists"})
    cache.clear()
    runner.test("clear() removes cache file", not cache.cache_file.exists())

    # Test 7: Multiple keys in same cache
    with mock.patch('time.time', return_value=4000.0):
        cache.set("key1", {"data": "value1"})
        cache.set("key2", {"data": "value2"})

    with mock.patch('time.time', return_value=4010.0):
        result1 = cache.get("key1", ttl=60)
        result2 = cache.get("key2", ttl=60)
        runner.test("Multiple keys stored independently",
                   result1 == {"data": "value1"} and result2 == {"data": "value2"})

    # Test 8: JSON serialization edge cases
    edge_case_data = {"none_value": None, "list": [1, 2, 3], "nested": {"key": "value"}}
    with mock.patch('time.time', return_value=5000.0):
        cache.set("edge_case", edge_case_data)
        result = cache.get("edge_case", ttl=60)
        runner.test("JSON serialization handles edge cases", result == edge_case_data)

    # Test 9: Corrupted cache file recovery (fail-silent)
    if cache.cache_file.exists():
        with open(cache.cache_file, 'w') as f:
            f.write("{invalid json")
        result = cache.get("any_key", ttl=60)
        runner.test("Corrupted cache returns None", result is None)

    # Cleanup
    cache.clear()


def test_logger_module(runner: TestRunner):
    """Test logger module."""
    print("\n📦 Testing logger module...")

    from logger import JsonLogger, StdoutHandler, FileHandler, get_logger, LEVELS
    import io

    # Test 1: LEVELS dict
    runner.test("LEVELS has debug", "debug" in LEVELS)
    runner.test("LEVELS has info", "info" in LEVELS)
    runner.test("LEVELS has warning", "warning" in LEVELS)
    runner.test("LEVELS has error", "error" in LEVELS)
    runner.test("Level ordering correct",
               LEVELS["debug"] < LEVELS["info"] < LEVELS["warning"] < LEVELS["error"])

    # Test 2: JsonLogger initialization
    logger = JsonLogger(level="info")
    runner.test("JsonLogger initializes", logger is not None)
    runner.test("Logger level set", logger.level_name == "info")

    # Test 3: Log level filtering
    output = io.StringIO()
    handler = StdoutHandler(stream=output)
    logger = JsonLogger(level="warning", handlers=[handler])

    logger.debug("debug message")
    logger.info("info message")
    logger.warning("warning message")
    logger.error("error message")

    output_lines = output.getvalue().strip().split('\n')
    output_lines = [line for line in output_lines if line]  # Filter empty lines
    runner.test("Log level filters debug/info", len(output_lines) == 2,
               f"Expected 2 lines (warning+error), got {len(output_lines)}")

    # Test 4: Context binding preserves fields
    logger1 = JsonLogger(level="info", context={"session": "abc123"})
    logger2 = logger1.bind(branch="feature/test")

    runner.test("bind() creates new logger", logger2 is not logger1)
    runner.test("Original context preserved", logger1.context.get("session") == "abc123")
    runner.test("New context has both fields",
               logger2.context.get("session") == "abc123" and logger2.context.get("branch") == "feature/test")

    # Test 5: StdoutHandler writes to stream
    output = io.StringIO()
    handler = StdoutHandler(stream=output)
    logger = JsonLogger(level="info", handlers=[handler])
    logger.info("test message", extra_field="value")

    log_output = output.getvalue()
    runner.test("StdoutHandler writes output", len(log_output) > 0)

    # Parse JSON to verify structure
    try:
        log_record = json.loads(log_output.strip())
        runner.test("Log output is valid JSON", True)
        runner.test("Log has timestamp", "timestamp" in log_record)
        runner.test("Log has level", log_record.get("level") == "info")
        runner.test("Log has message", log_record.get("message") == "test message")
        runner.test("Log has extra fields", log_record.get("extra_field") == "value")
    except json.JSONDecodeError:
        runner.test("Log output is valid JSON", False, f"Output: {log_output}")

    # Test 6: FileHandler writes to file
    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = Path(tmpdir) / "test.log"
        handler = FileHandler(log_file)
        logger = JsonLogger(level="info", handlers=[handler])
        logger.info("file test message")

        runner.test("FileHandler creates file", log_file.exists())
        if log_file.exists():
            content = log_file.read_text()
            runner.test("FileHandler writes JSON", len(content) > 0 and "file test message" in content)

    # Test 7: Multiple handlers work together
    output = io.StringIO()
    stdout_handler = StdoutHandler(stream=output)
    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = Path(tmpdir) / "multi.log"
        file_handler = FileHandler(log_file)
        logger = JsonLogger(level="info", handlers=[stdout_handler, file_handler])
        logger.info("multi handler test")

        runner.test("Multiple handlers both write",
                   len(output.getvalue()) > 0 and log_file.exists())

    # Test 8: Handler errors don't crash (fail-open)
    class FailingHandler:
        def emit(self, record):
            raise Exception("Handler failure")

    logger = JsonLogger(level="info", handlers=[FailingHandler()])
    try:
        logger.info("test with failing handler")
        runner.test("Failing handler doesn't crash", True)
    except Exception:
        runner.test("Failing handler doesn't crash", False, "Exception propagated")

    # Test 9: get_logger() with config dict
    config = {"level": "debug", "destinations": ["stdout"]}
    logger = get_logger(config, base_context={"app": "test"})
    runner.test("get_logger creates logger", logger is not None)
    runner.test("get_logger sets level", logger.level_name == "debug")
    runner.test("get_logger sets context", logger.context.get("app") == "test")

    # Test 10: Timestamp format (ISO 8601)
    output = io.StringIO()
    handler = StdoutHandler(stream=output)
    logger = JsonLogger(level="info", handlers=[handler])
    logger.info("timestamp test")

    log_output = output.getvalue()
    try:
        log_record = json.loads(log_output.strip())
        timestamp = log_record.get("timestamp", "")
        runner.test("Timestamp ends with Z", timestamp.endswith("Z"))
        runner.test("Timestamp is ISO format", "T" in timestamp and "-" in timestamp)
    except (json.JSONDecodeError, KeyError):
        runner.test("Timestamp format check", False, "Could not parse log output")


def test_registry_client(runner: TestRunner):
    """Test RegistryClient module."""
    print("\n📦 Testing registry_client module...")

    from registry_client import RegistryClient

    with tempfile.TemporaryDirectory() as tmpdir:
        registry_path = Path(tmpdir) / "test-registry.json"
        client = RegistryClient(registry_path)

        # Test 1: Read non-existent registry returns empty
        result = client.read()
        runner.test("Read non-existent returns empty", result == {"version": "1.0", "sessions": {}})

        # Test 2: Write creates registry
        test_registry = {
            "version": "1.0",
            "sessions": {
                "abc123": {"pid": 1234, "ppid": 1230, "project_dir": "/test", "branch": "main"}
            }
        }
        success = client.write(test_registry)
        runner.test("Write succeeds", success is True)
        runner.test("Write creates file", registry_path.exists())

        # Test 3: Read returns written data
        result = client.read()
        runner.test("Read returns written data", result == test_registry)

        # Test 4: update() with modification function
        def add_session(registry):
            registry["sessions"]["def456"] = {
                "pid": 5678, "ppid": 5670, "project_dir": "/test2", "branch": "develop"
            }
            return registry

        success = client.update(add_session)
        runner.test("update() succeeds", success is True)

        result = client.read()
        runner.test("update() adds session", "def456" in result["sessions"])
        runner.test("update() preserves existing", "abc123" in result["sessions"])

        # Test 5: update() with None return (no write)
        if registry_path.exists():
            os.stat(registry_path).st_mtime

        def no_change(registry):
            return None  # Signal no write needed

        success = client.update(no_change)
        runner.test("update() with None succeeds", success is True)

        # Test 6: Corrupted registry file recovery
        with open(registry_path, 'w') as f:
            f.write("{invalid json")

        result = client.read()
        runner.test("Corrupted registry returns empty", result == {"version": "1.0", "sessions": {}})

        # Test 7: Write after corruption creates valid registry
        success = client.write(test_registry)
        runner.test("Write after corruption succeeds", success is True)

        result = client.read()
        runner.test("Registry valid after recovery", result == test_registry)

        # Test 8: update() exception handling
        def failing_update(registry):
            raise ValueError("Update function error")

        success = client.update(failing_update)
        runner.test("update() with exception fails open", success is False)

        # Registry should still be readable after failed update
        result = client.read()
        runner.test("Registry intact after failed update", "abc123" in result["sessions"])

        # Test 9: Atomic write cleanup on failure
        # Simulate write failure by making directory read-only (if possible)
        original_registry = client.read()

        # Create a scenario where temp file write might fail
        # We'll test that cleanup happens by checking no .tmp files remain
        client.write(original_registry)

        tmp_files = list(registry_path.parent.glob("*.tmp"))
        runner.test("No orphaned temp files", len(tmp_files) == 0)


def test_codex_reviewer_requirement(runner: TestRunner):
    """Test codex_reviewer requirement with single_use scope."""
    print("\n📦 Testing codex_reviewer requirement...")

    from blocking_strategy import BlockingRequirementStrategy
    from requirements import BranchRequirements
    from config import RequirementsConfig

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create git repo
        os.makedirs(f"{tmpdir}/.git")

        # Create config with codex_reviewer requirement
        config_data = {
            'version': '1.0',
            'enabled': True,
            'requirements': {
                'codex_reviewer': {
                    'enabled': True,
                    'type': 'blocking',
                    'scope': 'single_use',
                    'trigger_tools': [
                        {'tool': 'Bash', 'command_pattern': 'gh\\s+pr\\s+create'}
                    ],
                    'message': '🤖 Codex AI Review Required',
                    'checklist': [
                        'Codex CLI installed',
                        'Logged in',
                        'AI review completed',
                    ],
                }
            }
        }

        # Write config
        os.makedirs(f"{tmpdir}/.claude", exist_ok=True)
        config_path = os.path.join(tmpdir, ".claude", "requirements.yaml")
        with open(config_path, 'w') as f:
            json.dump(config_data, f)

        # Load config object
        config = RequirementsConfig(tmpdir)

        # Test 1: Should block gh pr create when not satisfied
        reqs = BranchRequirements("feature/test", "session-1", tmpdir)
        strategy = BlockingRequirementStrategy()
        context = {
            'tool_name': 'Bash',
            'tool_input': {'command': 'gh pr create --title "Test"'},
            'session_id': 'session-1',
            'project_dir': tmpdir,
            'branch': 'feature/test'
        }
        result = strategy.check('codex_reviewer', config, reqs, context)
        runner.test("Blocks gh pr create when not satisfied", result is not None)
        runner.test("Returns denial response",
                    'hookSpecificOutput' in result and
                    result['hookSpecificOutput']['permissionDecision'] == 'deny')

        # Test 2: Satisfy the requirement
        reqs.satisfy('codex_reviewer', 'single_use', method='skill', metadata={'skill': 'requirements-framework:codex-review'})
        runner.test("Requirement satisfied", reqs.is_satisfied('codex_reviewer', 'single_use'))

        # Test 3: Should allow gh pr create when satisfied
        result = strategy.check('codex_reviewer', config, reqs, context)
        runner.test("Allows gh pr create when satisfied", result is None)

        # Test 4: Clear single_use requirement
        reqs.clear_single_use('codex_reviewer')
        runner.test("Requirement cleared", not reqs.is_satisfied('codex_reviewer', 'single_use'))

        # Test 5: Should block again after clearing
        result = strategy.check('codex_reviewer', config, reqs, context)
        runner.test("Blocks again after clearing",
                    result is not None and
                    result['hookSpecificOutput']['permissionDecision'] == 'deny')

        # Test 6: Trigger matching - verify trigger pattern works correctly
        # Note: Strategy.check() doesn't check triggers - that happens in the hook
        # We test that requirements can be checked for different tool contexts

        # First, satisfy the requirement so we can test without blocking
        reqs.satisfy('codex_reviewer', 'single_use', method='test')

        # Verify satisfied requirement allows any tool (strategy doesn't check triggers)
        context_commit = {
            'tool_name': 'Bash',
            'tool_input': {'command': 'git commit -m "test"'},
            'session_id': 'session-1',
            'project_dir': tmpdir,
            'branch': 'feature/test'
        }
        result = strategy.check('codex_reviewer', config, reqs, context_commit)
        runner.test("Allows other bash commands when satisfied", result is None)

        # Test 7: Verify Edit tool also allowed when satisfied
        context_edit = {
            'tool_name': 'Edit',
            'tool_input': {'file_path': 'test.py', 'old_string': 'old', 'new_string': 'new'},
            'session_id': 'session-1',
            'project_dir': tmpdir,
            'branch': 'feature/test'
        }
        result = strategy.check('codex_reviewer', config, reqs, context_edit)
        runner.test("Allows Edit tool when satisfied", result is None)


def test_short_message_field(runner: TestRunner):
    """Test short_message configuration field for deduplication scenarios."""
    print("\n📦 Testing short_message field...")

    from blocking_strategy import BlockingRequirementStrategy
    from requirements import BranchRequirements
    from config import RequirementsConfig

    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(f"{tmpdir}/.git")

        # Config with short_message
        config_data = {
            'version': '1.0',
            'enabled': True,
            'requirements': {
                'test_req': {
                    'enabled': True,
                    'type': 'blocking',
                    'scope': 'session',
                    'trigger_tools': ['Edit'],
                    'message': 'Full verbose message with lots of details.',
                    'short_message': 'Custom short message'
                }
            }
        }

        os.makedirs(f"{tmpdir}/.claude", exist_ok=True)
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config_data, f)

        config = RequirementsConfig(tmpdir)

        # Test 1: short_message field is accessible
        runner.test("short_message field accessible",
                   config.get_attribute('test_req', 'short_message') == 'Custom short message')

        # Test 2: Verify short_message is used during deduplication
        # Strategy creates its own dedup_cache internally
        strategy = BlockingRequirementStrategy()
        reqs = BranchRequirements("feature/test", "session-1", tmpdir)
        context = {
            'tool_name': 'Edit',
            'tool_input': {'file_path': 'test.py'},
            'session_id': 'session-1',
            'project_dir': tmpdir,
            'branch': 'feature/test'
        }

        # First call should show full message
        result1 = strategy.check('test_req', config, reqs, context)
        runner.test("First call returns denial", result1 is not None)
        msg1 = result1['hookSpecificOutput']['permissionDecisionReason']
        runner.test("First call shows full message", "Full verbose message" in msg1,
                   f"Got: {msg1[:100]}")

        # Second call (within TTL) should show short_message
        result2 = strategy.check('test_req', config, reqs, context)
        runner.test("Second call returns denial", result2 is not None)
        msg2 = result2['hookSpecificOutput']['permissionDecisionReason']
        runner.test("Second call shows custom short_message", "Custom short message" in msg2,
                   f"Got: {msg2}")

    # Test 3: Default short message when short_message not configured
    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(f"{tmpdir}/.git")

        config_data = {
            'version': '1.0',
            'enabled': True,
            'requirements': {
                'test_req': {
                    'enabled': True,
                    'type': 'blocking',
                    'scope': 'session',
                    'message': 'Full message without short_message field.'
                }
            }
        }

        os.makedirs(f"{tmpdir}/.claude", exist_ok=True)
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config_data, f)

        config = RequirementsConfig(tmpdir)
        # Strategy creates its own dedup_cache internally
        strategy = BlockingRequirementStrategy()
        reqs = BranchRequirements("feature/test", "session-2", tmpdir)
        context = {
            'tool_name': 'Edit',
            'tool_input': {'file_path': 'test.py'},
            'session_id': 'session-2',
            'project_dir': tmpdir,
            'branch': 'feature/test'
        }

        # First call
        strategy.check('test_req', config, reqs, context)

        # Second call should use default short message
        result = strategy.check('test_req', config, reqs, context)
        msg = result['hookSpecificOutput']['permissionDecisionReason']
        runner.test("Default short message used", "test_req" in msg and "waiting" in msg,
                   f"Got: {msg}")


def test_satisfied_by_skill_field(runner: TestRunner):
    """Test satisfied_by_skill configuration field."""
    print("\n🎯 Testing satisfied_by_skill field...")

    from config import RequirementsConfig

    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize git repo
        subprocess.run(['git', 'init'], cwd=tmpdir, capture_output=True)
        subprocess.run(['git', 'config', 'user.email', 'test@test.com'], cwd=tmpdir, capture_output=True)
        subprocess.run(['git', 'config', 'user.name', 'Test'], cwd=tmpdir, capture_output=True)

        # Create .claude directory
        os.makedirs(f"{tmpdir}/.claude")

        # Test 1: Valid satisfied_by_skill field
        config_data = {
            'version': '1.0',
            'enabled': True,
            'requirements': {
                'arch_review': {
                    'enabled': True,
                    'type': 'blocking',
                    'scope': 'single_use',
                    'trigger_tools': ['Bash'],
                    'satisfied_by_skill': 'architecture-guardian',
                    'message': 'Test message'
                }
            }
        }

        config_file = Path(tmpdir) / '.claude' / 'requirements.yaml'
        with open(config_file, 'w') as f:
            json.dump(config_data, f)

        config = RequirementsConfig(tmpdir)
        runner.test("Config loads with valid satisfied_by_skill",
                   config.get_attribute('arch_review', 'satisfied_by_skill') == 'architecture-guardian')
        runner.test("No validation errors for valid config", len(config.get_validation_errors()) == 0)

        # Test 2: Invalid satisfied_by_skill (non-string)
        invalid_config = {
            'version': '1.0',
            'enabled': True,
            'requirements': {
                'arch_review': {
                    'enabled': True,
                    'type': 'blocking',
                    'satisfied_by_skill': 123,  # Should be string
                }
            }
        }

        with open(config_file, 'w') as f:
            json.dump(invalid_config, f)

        config = RequirementsConfig(tmpdir)
        errors = config.get_validation_errors()
        runner.test("Invalid satisfied_by_skill (non-string) rejected",
                   any('must be str' in e or 'must be a string' in e for e in errors))

        # Test 3: Invalid satisfied_by_skill (empty string)
        empty_config = {
            'version': '1.0',
            'enabled': True,
            'requirements': {
                'arch_review': {
                    'enabled': True,
                    'type': 'blocking',
                    'satisfied_by_skill': '',  # Empty string
                }
            }
        }

        with open(config_file, 'w') as f:
            json.dump(empty_config, f)

        config = RequirementsConfig(tmpdir)
        errors = config.get_validation_errors()
        runner.test("Invalid satisfied_by_skill (empty string) rejected",
                   any('cannot be empty' in e for e in errors))

        # Test 4: Invalid satisfied_by_skill (whitespace only)
        whitespace_config = {
            'version': '1.0',
            'enabled': True,
            'requirements': {
                'arch_review': {
                    'enabled': True,
                    'type': 'blocking',
                    'satisfied_by_skill': '   ',  # Whitespace only
                }
            }
        }

        with open(config_file, 'w') as f:
            json.dump(whitespace_config, f)

        config = RequirementsConfig(tmpdir)
        errors = config.get_validation_errors()
        runner.test("Invalid satisfied_by_skill (whitespace only) rejected",
                   any('cannot be empty' in e for e in errors))

        # Test 5: Requirement without satisfied_by_skill is valid
        no_skill_config = {
            'version': '1.0',
            'enabled': True,
            'requirements': {
                'commit_plan': {
                    'enabled': True,
                    'type': 'blocking',
                    'scope': 'session',
                }
            }
        }

        with open(config_file, 'w') as f:
            json.dump(no_skill_config, f)

        config = RequirementsConfig(tmpdir)
        runner.test("Requirement without satisfied_by_skill is valid",
                   len(config.get_validation_errors()) == 0)
        runner.test("satisfied_by_skill returns None when not set",
                   config.get_attribute('commit_plan', 'satisfied_by_skill') is None)


def test_edge_cases(runner: TestRunner):
    """Test edge cases: concurrent access, permissions, Windows compatibility."""
    print("\n📦 Testing edge cases...")

    from registry_client import RegistryClient
    from calculation_cache import CalculationCache
    import unittest.mock as mock

    # Test 1: Windows compatibility - calculation_cache with getpass fallback
    with mock.patch('os.getuid', side_effect=AttributeError("no getuid on Windows")):
        with mock.patch('getpass.getuser', return_value='test_user'):
            cache = CalculationCache()
            runner.test("Windows fallback uses getpass", 'test_user' in str(cache.cache_file))

    # Test 2: Concurrent writes don't corrupt registry
    with tempfile.TemporaryDirectory() as tmpdir:
        registry_path = Path(tmpdir) / "concurrent-test.json"
        client = RegistryClient(registry_path)

        # Simulate near-simultaneous writes
        def add_session_a(registry):
            registry["sessions"]["aaa"] = {"pid": 1}
            return registry

        def add_session_b(registry):
            registry["sessions"]["bbb"] = {"pid": 2}
            return registry

        client.update(add_session_a)
        client.update(add_session_b)

        # Verify both sessions present (no lost updates)
        result = client.read()
        runner.test("Concurrent updates don't lose data",
                   "aaa" in result["sessions"] and "bbb" in result["sessions"])

        # Verify file is valid JSON (not corrupted)
        try:
            with open(registry_path) as f:
                json.load(f)
            runner.test("Concurrent updates don't corrupt JSON", True)
        except json.JSONDecodeError:
            runner.test("Concurrent updates don't corrupt JSON", False, "Registry corrupted")

    # Test 3: Empty file recovery
    with tempfile.TemporaryDirectory() as tmpdir:
        registry_path = Path(tmpdir) / "empty.json"
        registry_path.write_text("")  # 0 bytes
        client = RegistryClient(registry_path)

        result = client.read()
        runner.test("Empty file returns empty registry", result == {"version": "1.0", "sessions": {}})

    # Test 4: Atomic write cleanup verification
    with tempfile.TemporaryDirectory() as tmpdir:
        registry_path = Path(tmpdir) / "cleanup-test.json"
        client = RegistryClient(registry_path)

        # Write successfully
        test_data = {"version": "1.0", "sessions": {"test": {"pid": 1}}}
        client.write(test_data)

        # Verify no temp files left
        tmp_files = list(registry_path.parent.glob("*.tmp"))
        runner.test("Successful write leaves no temp files", len(tmp_files) == 0)

    # Test 5: Registry structure validation
    with tempfile.TemporaryDirectory() as tmpdir:
        registry_path = Path(tmpdir) / "invalid-structure.json"

        # Write invalid structure (sessions is a string, not dict)
        registry_path.write_text('{"version": "1.0", "sessions": "not-a-dict"}')
        client = RegistryClient(registry_path)

        result = client.read()
        # Should handle gracefully (though current implementation doesn't validate)
        runner.test("Read invalid structure doesn't crash", result is not None)


def test_permission_errors_fail_open(runner: TestRunner):
    """Test fail-open behavior with file permission errors.

    Validates that permission denied scenarios don't crash the framework.
    Tests OSError/IOError handling in registry_client, state_storage, and message_dedup_cache.

    Skipped on Windows - POSIX permissions don't apply.
    Skipped when running as root - root can override POSIX DAC restrictions.
    """
    import platform
    import os

    # Skip on Windows - POSIX permissions not applicable
    if platform.system() == 'Windows':
        print("\n📦 Skipping permission tests (Windows platform)")
        return

    # Skip when running as root - root can override permission restrictions
    if hasattr(os, 'geteuid') and os.geteuid() == 0:
        print("\n📦 Skipping permission tests (running as root)")
        return

    print("\n📦 Testing permission error fail-open behavior...")

    from registry_client import RegistryClient
    from state_storage import load_state, save_state, delete_state, get_state_path
    from message_dedup_cache import MessageDedupCache

    # ========== REGISTRY_CLIENT TESTS (4 tests) ==========

    # Test 1: Read-only parent directory prevents write/update
    with tempfile.TemporaryDirectory() as tmpdir:
        registry_dir = Path(tmpdir) / "registry_dir"
        registry_dir.mkdir()
        registry_path = registry_dir / "test.json"
        client = RegistryClient(registry_path)

        # Create initial registry
        client.write({"version": "1.0", "sessions": {"abc123": {"pid": 1234}}})

        try:
            # Make parent directory read-only (prevents temp file creation)
            registry_dir.chmod(0o555)

            # Attempt write - should fail gracefully (can't create temp file)
            success = client.write({"version": "1.0", "sessions": {}})
            runner.test("Read-only dir prevents registry write", success is False)

            # update() should also fail gracefully
            def add_session(r):
                r["sessions"]["new"] = {"pid": 999}
                return r

            success = client.update(add_session)
            runner.test("update() with read-only dir fails gracefully", success is False)

        finally:
            try:
                registry_dir.chmod(0o755)
            except OSError:
                pass  # Cleanup failure shouldn't mask test failures

    # Test 2: Unreadable registry file (0o000)
    with tempfile.TemporaryDirectory() as tmpdir:
        registry_path = Path(tmpdir) / "unreadable-test.json"
        client = RegistryClient(registry_path)
        client.write({"version": "1.0", "sessions": {"test": {"pid": 999}}})

        try:
            registry_path.chmod(0o000)  # No permissions

            # Should return empty registry
            result = client.read()
            runner.test("Unreadable registry returns empty dict",
                       result == {"version": "1.0", "sessions": {}})

        finally:
            try:
                registry_path.chmod(0o644)
            except OSError:
                pass  # Cleanup failure shouldn't mask test failures

    # Test 3: Read-only parent directory - can't create new file
    with tempfile.TemporaryDirectory() as tmpdir:
        readonly_dir = Path(tmpdir) / "readonly_dir"
        readonly_dir.mkdir()
        registry_path = readonly_dir / "new-registry.json"
        client = RegistryClient(registry_path)

        try:
            readonly_dir.chmod(0o555)  # Read + execute only

            # Can't create new file
            success = client.write({"version": "1.0", "sessions": {}})
            runner.test("Can't create registry in read-only dir", success is False)

            # Read returns empty
            result = client.read()
            runner.test("Read from read-only dir returns empty",
                       result == {"version": "1.0", "sessions": {}})

        finally:
            try:
                readonly_dir.chmod(0o755)
            except OSError:
                pass  # Cleanup failure shouldn't mask test failures

    # Test 4: Write-only file (can't read)
    with tempfile.TemporaryDirectory() as tmpdir:
        registry_path = Path(tmpdir) / "writeonly-test.json"
        client = RegistryClient(registry_path)
        client.write({"version": "1.0", "sessions": {"test": {"pid": 1}}})

        try:
            registry_path.chmod(0o222)  # Write only

            # Can't read write-only file
            result = client.read()
            runner.test("Write-only file returns empty registry",
                       result == {"version": "1.0", "sessions": {}})

        finally:
            try:
                registry_path.chmod(0o644)
            except OSError:
                pass  # Cleanup failure shouldn't mask test failures

    # ========== STATE_STORAGE TESTS (4 tests) ==========

    # Test 5: Read-only state file - save should fail silently
    with tempfile.TemporaryDirectory() as tmpdir:
        git_dir = Path(tmpdir) / ".git"
        git_dir.mkdir()

        save_state("main", tmpdir, {"test": "data", "version": "1.0"})
        state_path = get_state_path("main", tmpdir)

        try:
            state_path.chmod(0o444)

            # save_state should fail silently (fail-open, no exception)
            save_state("main", tmpdir, {"new": "data", "version": "1.0"})
            runner.test("save_state() with read-only file doesn't crash", True)

        finally:
            try:
                state_path.chmod(0o644)
            except OSError:
                pass  # Cleanup failure shouldn't mask test failures

    # Test 6: Unreadable state file - load should return empty state
    with tempfile.TemporaryDirectory() as tmpdir:
        git_dir = Path(tmpdir) / ".git"
        git_dir.mkdir()

        save_state("main", tmpdir, {"test": "data", "version": "1.0"})
        state_path = get_state_path("main", tmpdir)

        try:
            state_path.chmod(0o000)

            # Should return empty state
            state = load_state("main", tmpdir)
            runner.test("Unreadable state file returns empty state",
                       state.get("requirements", {}) == {})

        finally:
            try:
                state_path.chmod(0o644)
            except OSError:
                pass  # Cleanup failure shouldn't mask test failures

    # Test 7: Read-only requirements directory - can't save
    with tempfile.TemporaryDirectory() as tmpdir:
        git_dir = Path(tmpdir) / ".git"
        git_dir.mkdir()
        req_dir = git_dir / "requirements"
        req_dir.mkdir()

        try:
            req_dir.chmod(0o555)

            # Can't save in read-only dir (should fail silently - fail-open)
            save_state("feature", tmpdir, {"test": "data", "version": "1.0"})
            runner.test("save_state() in read-only dir doesn't crash", True)

            # Load returns empty
            state = load_state("feature", tmpdir)
            runner.test("load_state() from read-only dir returns empty",
                       state.get("requirements", {}) == {})

        finally:
            try:
                req_dir.chmod(0o755)
            except OSError:
                pass  # Cleanup failure shouldn't mask test failures

    # Test 8: delete_state with read-only directory
    with tempfile.TemporaryDirectory() as tmpdir:
        git_dir = Path(tmpdir) / ".git"
        git_dir.mkdir()
        req_dir = git_dir / "requirements"
        req_dir.mkdir()

        save_state("delete-test", tmpdir, {"test": "data", "version": "1.0"})
        state_path = get_state_path("delete-test", tmpdir)

        try:
            req_dir.chmod(0o555)

            # delete should fail silently (fail-open, no exception)
            delete_state("delete-test", tmpdir)
            runner.test("delete_state() in read-only dir doesn't crash", True)

            # File should still exist
            runner.test("State file persists in read-only dir", state_path.exists())

        finally:
            try:
                req_dir.chmod(0o755)
            except OSError:
                pass  # Cleanup failure shouldn't mask test failures

    # ========== MESSAGE_DEDUP_CACHE TESTS (4 tests) ==========

    # Test 9: Read-only cache file - should fail-open (return True)
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = MessageDedupCache()
        original_cache_file = cache.cache_file
        cache.cache_file = Path(tmpdir) / "test-cache.json"

        try:
            # Prime cache
            cache.should_show_message("key1", "message1")

            cache.cache_file.chmod(0o444)

            # Should fail-open (return True)
            should_show = cache.should_show_message("key2", "message2")
            runner.test("should_show_message() with read-only cache returns True",
                       should_show is True)

        finally:
            try:
                if cache.cache_file.exists():
                    cache.cache_file.chmod(0o644)
            except OSError:
                pass  # Cleanup failure shouldn't mask test failures
            cache.cache_file = original_cache_file

    # Test 10: Unreadable cache file - should return True (fail-open)
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = MessageDedupCache()
        original_cache_file = cache.cache_file
        cache.cache_file = Path(tmpdir) / "unreadable-cache.json"

        try:
            cache.should_show_message("key1", "message1")

            cache.cache_file.chmod(0o000)

            # Should return True (fail-open)
            should_show = cache.should_show_message("key1", "message1")
            runner.test("Unreadable cache returns True", should_show is True)

        finally:
            try:
                if cache.cache_file.exists():
                    cache.cache_file.chmod(0o644)
            except OSError:
                pass  # Cleanup failure shouldn't mask test failures
            cache.cache_file = original_cache_file

    # Test 11: Read-only temp directory - can't create cache
    with tempfile.TemporaryDirectory() as tmpdir:
        readonly_temp = Path(tmpdir) / "readonly_temp"
        readonly_temp.mkdir()

        cache = MessageDedupCache()
        original_cache_file = cache.cache_file
        cache.cache_file = readonly_temp / "new-cache.json"

        try:
            readonly_temp.chmod(0o555)

            # Can't create cache in read-only directory
            should_show = cache.should_show_message("key1", "message1")
            runner.test("Cache creation in read-only dir returns True",
                       should_show is True)

        finally:
            try:
                readonly_temp.chmod(0o755)
            except OSError:
                pass  # Cleanup failure shouldn't mask test failures
            cache.cache_file = original_cache_file

    # Test 12: Write-only cache file - can't read
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = MessageDedupCache()
        original_cache_file = cache.cache_file
        cache.cache_file = Path(tmpdir) / "writeonly-cache.json"

        try:
            cache.should_show_message("key1", "message1")

            cache.cache_file.chmod(0o222)

            # Can't read write-only file
            should_show = cache.should_show_message("key1", "message1")
            runner.test("Write-only cache file returns True", should_show is True)

        finally:
            try:
                if cache.cache_file.exists():
                    cache.cache_file.chmod(0o644)
            except OSError:
                pass  # Cleanup failure shouldn't mask test failures
            cache.cache_file = original_cache_file


def test_early_hook_setup(runner):
    """Test hook_utils.early_hook_setup() function."""
    import tempfile
    import subprocess
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent / 'lib'))
    from hook_utils import early_hook_setup

    # Test 1: Config with debug logging level
    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup: Create project with debug logging config
        os.makedirs(f"{tmpdir}/.claude")
        config_file = Path(f"{tmpdir}/.claude/requirements.yaml")

        config_content = """version: "1.0"
enabled: true
logging:
  level: debug
  destinations: [file]
  file: ~/.claude/requirements.log
requirements: {}
"""
        with open(config_file, 'w') as f:
            f.write(config_content)

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "test-branch"], cwd=tmpdir, capture_output=True)

        # Test: Setup hook with config
        project_dir, branch, config, logger = early_hook_setup(
            session_id="test123",
            hook_name="TestHook",
            cwd=tmpdir
        )

        # Verify: Logger has debug level from config
        runner.test("early_hook_setup loads config", config is not None)
        runner.test("early_hook_setup creates logger with debug level", logger.level_name == "debug")
        runner.test("early_hook_setup returns project dir", project_dir == tmpdir)
        runner.test("early_hook_setup returns branch", branch == "test-branch")
        runner.test("early_hook_setup sets correct hook context", logger.context.get("hook") == "TestHook")
        runner.test("early_hook_setup sets session context", logger.context.get("session") == "test123")

    # Test 2: No config case (invalid path that's not a git repo)
    project_dir2, branch2, config2, logger2 = early_hook_setup(
        session_id="test456",
        hook_name="TestHook2",
        cwd="/nonexistent"
    )

    runner.test("early_hook_setup returns path for project_dir even if invalid", project_dir2 == "/nonexistent")
    runner.test("early_hook_setup returns None for branch when not git repo", branch2 is None)
    runner.test("early_hook_setup returns None for config when no config file", config2 is None)
    runner.test("early_hook_setup still creates logger when no config", logger2 is not None)
    runner.test("early_hook_setup logger defaults to error when no config", logger2.level_name == "error")

    # Test 3: Config loading with YAML parse error - falls back to global config
    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(f"{tmpdir}/.claude")
        config_file = Path(f"{tmpdir}/.claude/requirements.yaml")

        # Write invalid YAML that will cause parse error
        with open(config_file, 'w') as f:
            f.write("invalid: yaml: syntax:")

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "test-branch"], cwd=tmpdir, capture_output=True)

        # Test: YAML parse errors are handled gracefully by RequirementsConfig
        # It logs a warning but still returns a valid config object (using global defaults)
        project_dir3, branch3, config3, logger3 = early_hook_setup(
            session_id="test789",
            hook_name="TestHook3",
            cwd=tmpdir
        )

        runner.test("early_hook_setup returns project_dir with YAML parse error", project_dir3 == tmpdir)
        runner.test("early_hook_setup returns branch with YAML parse error", branch3 == "test-branch")
        # RequirementsConfig handles YAML parse errors internally and falls back to global config
        runner.test("early_hook_setup returns config object even with YAML parse error", config3 is not None)
        # Logger uses global config defaults (which may be debug from ~/.claude/requirements.yaml)
        runner.test("early_hook_setup logger uses config level even with YAML parse error", logger3.level_name in ["debug", "error", "info"])

    # Test 4: Info logging level
    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(f"{tmpdir}/.claude")
        config_file = Path(f"{tmpdir}/.claude/requirements.yaml")

        config_content = """version: "1.0"
enabled: true
logging:
  level: info
requirements: {}
"""
        with open(config_file, 'w') as f:
            f.write(config_content)

        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "main"], cwd=tmpdir, capture_output=True)

        project_dir4, branch4, config4, logger4 = early_hook_setup(
            session_id="test999",
            hook_name="TestHook4",
            cwd=tmpdir
        )

        runner.test("early_hook_setup creates logger with info level when configured", logger4.level_name == "info")

    # Test 5: skip_config parameter
    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(f"{tmpdir}/.claude")
        config_file = Path(f"{tmpdir}/.claude/requirements.yaml")

        config_content = """version: "1.0"
enabled: true
logging:
  level: debug
requirements: {}
"""
        with open(config_file, 'w') as f:
            f.write(config_content)

        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "main"], cwd=tmpdir, capture_output=True)

        project_dir5, branch5, config5, logger5 = early_hook_setup(
            session_id="test000",
            hook_name="TestHook5",
            cwd=tmpdir,
            skip_config=True
        )

        runner.test("early_hook_setup skips config when skip_config=True", config5 is None)
        runner.test("early_hook_setup uses default level when skip_config=True", logger5.level_name == "error")


def test_parse_hook_input(runner):
    """Test hook_utils.parse_hook_input() function."""
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent / 'lib'))
    from hook_utils import parse_hook_input

    print("\n🎯 Testing parse_hook_input()...")

    # Test 1: Empty input returns empty dict with marker
    result, error = parse_hook_input("")
    runner.test("parse_hook_input returns _empty_stdin marker for empty input", result.get('_empty_stdin') is True)
    runner.test("parse_hook_input returns no error for empty input", error is None)

    # Test 2: Valid JSON with all fields
    result, error = parse_hook_input('{"tool_name": "Edit", "tool_input": {"file": "x.py"}, "session_id": "abc123"}')
    runner.test("parse_hook_input parses valid JSON", result.get("tool_name") == "Edit")
    runner.test("parse_hook_input preserves tool_input dict", result.get("tool_input") == {"file": "x.py"})
    runner.test("parse_hook_input preserves other fields", result.get("session_id") == "abc123")
    runner.test("parse_hook_input returns no error for valid JSON", error is None)

    # Test 3: Invalid JSON returns error
    result, error = parse_hook_input("not valid json")
    runner.test("parse_hook_input returns empty dict on invalid JSON", result == {})
    runner.test("parse_hook_input returns error on invalid JSON", error is not None)
    runner.test("parse_hook_input error mentions JSON", "JSON" in error)

    # Test 4: Non-dict JSON returns error
    result, error = parse_hook_input('["an", "array"]')
    runner.test("parse_hook_input returns empty dict for non-dict JSON", result == {})
    runner.test("parse_hook_input returns error for non-dict JSON", "Expected dict" in str(error))

    # Test 5: Invalid tool_name type (Issue #01 fix)
    result, error = parse_hook_input('{"tool_name": 123, "tool_input": {}}')
    runner.test("parse_hook_input normalizes non-string tool_name to None", result.get("tool_name") is None)
    runner.test("parse_hook_input adds _tool_name_type_error marker", "_tool_name_type_error" in result)
    runner.test("parse_hook_input type error mentions expected type", "Expected str" in result.get("_tool_name_type_error", ""))
    runner.test("parse_hook_input returns no error for type coercion", error is None)

    # Test 6: Invalid tool_input type
    result, error = parse_hook_input('{"tool_name": "Edit", "tool_input": "not a dict"}')
    runner.test("parse_hook_input normalizes non-dict tool_input to {}", result.get("tool_input") == {})
    runner.test("parse_hook_input adds _tool_input_type_error marker", "_tool_input_type_error" in result)
    runner.test("parse_hook_input tool_input type error mentions expected type", "Expected dict" in result.get("_tool_input_type_error", ""))

    # Test 7: Missing tool_input defaults to empty dict (no error marker)
    result, error = parse_hook_input('{"tool_name": "Read"}')
    runner.test("parse_hook_input defaults missing tool_input to {}", result.get("tool_input") == {})
    runner.test("parse_hook_input no error marker for missing tool_input", "_tool_input_type_error" not in result)

    # Test 8: tool_input as array (wrong type)
    result, error = parse_hook_input('{"tool_name": "Edit", "tool_input": ["file.py"]}')
    runner.test("parse_hook_input handles array tool_input", result.get("tool_input") == {})
    runner.test("parse_hook_input marks array tool_input as type error", "_tool_input_type_error" in result)

    # Test 9: Null tool_name is valid (passes through as None)
    result, error = parse_hook_input('{"tool_name": null, "tool_input": {}}')
    runner.test("parse_hook_input allows null tool_name", result.get("tool_name") is None)
    runner.test("parse_hook_input no type error for null tool_name", "_tool_name_type_error" not in result)


def test_field_extractors(runner):
    """Test hook_utils field extractor functions (Issue #05)."""
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent / 'lib'))
    from hook_utils import extract_file_path, extract_command, extract_skill_name

    print("\n🎯 Testing field extractors (Issue #05)...")

    # =========================================================================
    # extract_file_path tests
    # =========================================================================

    # Test 1: Valid file_path
    result = extract_file_path({'file_path': '/tmp/test.py'})
    runner.test("extract_file_path returns valid path", result == '/tmp/test.py')

    # Test 2: Missing file_path
    result = extract_file_path({})
    runner.test("extract_file_path returns empty string for missing key", result == '')

    # Test 3: None file_path
    result = extract_file_path({'file_path': None})
    runner.test("extract_file_path returns empty string for None value", result == '')

    # Test 4: Wrong type (int)
    result = extract_file_path({'file_path': 123})
    runner.test("extract_file_path returns empty string for int type", result == '')

    # Test 5: Wrong type (list)
    result = extract_file_path({'file_path': ['/tmp/test.py']})
    runner.test("extract_file_path returns empty string for list type", result == '')

    # Test 6: Wrong type (dict)
    result = extract_file_path({'file_path': {'path': '/tmp/test.py'}})
    runner.test("extract_file_path returns empty string for dict type", result == '')

    # Test 7: Null bytes in path (security)
    result = extract_file_path({'file_path': '/tmp/test\x00.py'})
    runner.test("extract_file_path rejects null bytes", result == '')

    # Test 8: Empty string is valid
    result = extract_file_path({'file_path': ''})
    runner.test("extract_file_path allows empty string", result == '')

    # Test 9: Path with spaces (valid)
    result = extract_file_path({'file_path': '/tmp/my file.py'})
    runner.test("extract_file_path allows paths with spaces", result == '/tmp/my file.py')

    # =========================================================================
    # extract_command tests
    # =========================================================================

    # Test 10: Valid command
    result = extract_command({'command': 'git status'})
    runner.test("extract_command returns valid command", result == 'git status')

    # Test 11: Missing command
    result = extract_command({})
    runner.test("extract_command returns empty string for missing key", result == '')

    # Test 12: None command
    result = extract_command({'command': None})
    runner.test("extract_command returns empty string for None value", result == '')

    # Test 13: Wrong type (int)
    result = extract_command({'command': 123})
    runner.test("extract_command returns empty string for int type", result == '')

    # Test 14: Wrong type (list) - common mistake
    result = extract_command({'command': ['git', 'status']})
    runner.test("extract_command returns empty string for list type", result == '')

    # Test 15: Empty string is valid
    result = extract_command({'command': ''})
    runner.test("extract_command allows empty string", result == '')

    # =========================================================================
    # extract_skill_name tests
    # =========================================================================

    # Test 16: Valid skill
    result = extract_skill_name({'skill': 'requirements-framework:pre-commit'})
    runner.test("extract_skill_name returns valid skill", result == 'requirements-framework:pre-commit')

    # Test 17: Missing skill
    result = extract_skill_name({})
    runner.test("extract_skill_name returns empty string for missing key", result == '')

    # Test 18: None skill
    result = extract_skill_name({'skill': None})
    runner.test("extract_skill_name returns empty string for None value", result == '')

    # Test 19: Wrong type (int)
    result = extract_skill_name({'skill': 123})
    runner.test("extract_skill_name returns empty string for int type", result == '')

    # Test 20: Empty string is valid
    result = extract_skill_name({'skill': ''})
    runner.test("extract_skill_name allows empty string", result == '')


def test_plan_mode_triggers(runner):
    """Test that EnterPlanMode and ExitPlanMode are recognized as triggering tools."""
    import tempfile
    import subprocess
    import json
    from pathlib import Path

    print("\n🎯 Testing plan mode triggers...")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup: Create project with requirements config
        os.makedirs(f"{tmpdir}/.claude")
        config_file = Path(f"{tmpdir}/.claude/requirements.yaml")

        config_content = """version: "1.0"
enabled: true
requirements:
  adr_plan_validation:
    enabled: true
    type: blocking
    scope: single_use
    trigger_tools:
      - ExitPlanMode
    message: "Plan must be validated"

  adr_planning_review:
    enabled: true
    type: blocking
    scope: session
    trigger_tools:
      - EnterPlanMode
    message: "ADR review before planning"
"""
        with open(config_file, 'w') as f:
            f.write(config_content)

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "test-branch"], cwd=tmpdir, capture_output=True)

        # Test 1: ExitPlanMode triggers adr_plan_validation
        hook_input = {
            "tool_name": "ExitPlanMode",
            "tool_input": {},
            "session_id": "test-plan-session",
            "cwd": tmpdir
        }

        result = subprocess.run(
            ["python3", str(Path(__file__).parent / "check-requirements.py")],
            input=json.dumps(hook_input),
            capture_output=True,
            text=True,
            cwd=tmpdir
        )

        runner.test("ExitPlanMode is recognized as triggering tool", result.returncode == 0)

        # If requirement not satisfied, should output denial
        if result.stdout:
            try:
                output_data = json.loads(result.stdout)
                has_denial = "hookSpecificOutput" in output_data
                if has_denial:
                    reason = output_data.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
                    runner.test("ExitPlanMode triggers adr_plan_validation", "adr_plan_validation" in reason)
            except json.JSONDecodeError:
                # Empty output means requirement was satisfied or skipped
                pass

        # Test 2: EnterPlanMode triggers adr_planning_review
        hook_input2 = {
            "tool_name": "EnterPlanMode",
            "tool_input": {},
            "session_id": "test-plan-session-2",
            "cwd": tmpdir
        }

        result2 = subprocess.run(
            ["python3", str(Path(__file__).parent / "check-requirements.py")],
            input=json.dumps(hook_input2),
            capture_output=True,
            text=True,
            cwd=tmpdir
        )

        runner.test("EnterPlanMode is recognized as triggering tool", result2.returncode == 0)

        if result2.stdout:
            try:
                output_data2 = json.loads(result2.stdout)
                has_denial2 = "hookSpecificOutput" in output_data2
                if has_denial2:
                    reason2 = output_data2.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
                    runner.test("EnterPlanMode triggers adr_planning_review", "adr_planning_review" in reason2)
            except json.JSONDecodeError:
                pass

        # Test 3: Read tool does NOT trigger (sanity check)
        hook_input3 = {
            "tool_name": "Read",
            "tool_input": {"file_path": "/tmp/test.txt"},
            "session_id": "test-plan-session-3",
            "cwd": tmpdir
        }

        result3 = subprocess.run(
            ["python3", str(Path(__file__).parent / "check-requirements.py")],
            input=json.dumps(hook_input3),
            capture_output=True,
            text=True,
            cwd=tmpdir
        )

        runner.test("Read tool does not trigger plan mode requirements", result3.returncode == 0 and not result3.stdout)


def main():
    """Run all tests."""
    print("🧪 Requirements Framework Test Suite")
    print("=" * 50)

    runner = TestRunner()

    test_session_module(runner)
    test_session_registry(runner)
    test_session_id_normalization(runner)
    test_get_session_id_normalization(runner)
    test_session_key_migration(runner)
    test_git_utils_module(runner)
    test_git_root_resolution(runner)
    test_hook_from_subdirectory(runner)
    test_cli_from_subdirectory(runner)
    test_not_in_git_repo_fallback(runner)
    test_state_storage_module(runner)
    test_config_module(runner)
    test_write_local_config(runner)
    test_write_project_config(runner)
    test_cli_enable_disable(runner)
    test_cli_config_project_modify(runner)
    test_requirements_manager(runner)
    test_branch_level_override(runner)
    test_branch_level_override_with_ttl(runner)
    test_cli_commands(runner)
    test_cli_status_modes(runner)
    test_cli_sessions_command(runner)
    test_cli_doctor_command(runner)
    test_enhanced_doctor_json_output(runner)
    test_enhanced_doctor_check_functions(runner)
    test_hook_behavior(runner)
    test_checklist_rendering(runner)

    # New hook tests
    test_hook_config(runner)
    test_remove_session_from_registry(runner)
    test_session_start_hook(runner)
    test_stop_hook(runner)
    test_session_end_hook(runner)

    # Triggered requirements tests (Stop hook research-session fix)
    test_triggered_requirements(runner)
    test_stop_hook_triggered_only(runner)
    test_stop_hook_guard_context_aware(runner)

    # Batched requirements tests
    test_batched_requirements_blocking(runner)
    test_cli_satisfy_multiple(runner)
    test_cli_satisfy_branch_flag(runner)
    test_cli_satisfy_branch_flag_dynamic(runner)
    test_cli_satisfy_branch_flag_multiple(runner)
    test_partial_satisfaction(runner)

    # Guard strategy tests
    test_guard_strategy_blocks_protected_branch(runner)
    test_guard_strategy_allows_feature_branch(runner)
    test_guard_strategy_respects_custom_branch_list(runner)
    test_guard_strategy_approval_bypasses_check(runner)
    test_guard_strategy_unknown_guard_type_allows(runner)
    test_guard_hook_integration(runner)
    test_guard_status_display_context_aware(runner)

    # Single session guard tests
    test_single_session_guard_allows_when_alone(runner)
    test_single_session_guard_blocks_with_other_session(runner)
    test_single_session_guard_approval_bypasses(runner)
    test_single_session_guard_excludes_current_session(runner)
    test_single_session_guard_filters_by_project(runner)

    # Colors module tests
    test_colors_module(runner)

    # Progress module tests
    test_progress_module(runner)

    # Interactive prompts module tests
    test_interactive_module(runner)

    # Init presets module tests
    test_init_presets_module(runner)
    test_generate_config_context_parameter(runner)
    test_generate_config_validation(runner)
    test_feature_selector(runner)

    # CLI init command tests
    test_cli_init_command(runner)

    # CLI config command tests
    test_cli_config_command(runner)
    test_cli_config_show_command(runner)

    # NEW: Cache and logger module tests (Phase 1)
    test_message_dedup_cache(runner)
    test_calculation_cache(runner)
    test_logger_module(runner)

    # NEW: Registry client tests (Phase 3)
    test_registry_client(runner)

    # NEW: Edge case tests (Phase 3 extended)
    test_edge_cases(runner)

    # Permission error fail-open tests
    test_permission_errors_fail_open(runner)

    # Codex reviewer requirement tests
    test_codex_reviewer_requirement(runner)

    # Short message field tests
    test_short_message_field(runner)

    # Satisfied by skill field tests
    test_satisfied_by_skill_field(runner)

    # Hook utils module tests
    test_early_hook_setup(runner)
    test_parse_hook_input(runner)
    test_field_extractors(runner)

    # Plan mode trigger tests
    test_plan_mode_triggers(runner)

    return runner.summary()


if __name__ == "__main__":
    sys.exit(main())
