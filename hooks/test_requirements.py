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

    # Test session ID generation
    session1 = get_session_id()
    runner.test("Session ID generated", len(session1) == 8, f"Got: {session1}")

    # Test session ID stability
    session2 = get_session_id()
    runner.test("Session ID stable", session1 == session2, f"{session1} != {session2}")

    # Test clear cache
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

            # Test update_registry updates existing session
            time.sleep(0.01)  # Ensure different timestamp
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


def test_git_utils_module(runner: TestRunner):
    """Test git utilities."""
    print("\n📦 Testing git_utils module...")
    from git_utils import run_git, is_git_repo, get_git_root

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
    from config import RequirementsConfig, load_yaml_or_json, deep_merge

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

        # Test TTL expiration
        reqs4 = BranchRequirements("ttl/branch", "session-1", tmpdir)
        reqs4.satisfy("ttl_req", "session", ttl=1)  # 1 second TTL
        runner.test("TTL satisfied initially", reqs4.is_satisfied("ttl_req", "session"))
        time.sleep(1.5)
        runner.test("TTL expired", not reqs4.is_satisfied("ttl_req", "session"))


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

        # Test satisfy command
        result = subprocess.run(
            ["python3", str(cli_path), "satisfy", "commit_plan"],
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("Satisfy runs", result.returncode == 0, result.stderr)
        runner.test("Satisfy confirms", "✅" in result.stdout, result.stdout)

        # Test status after satisfy
        result = subprocess.run(
            ["python3", str(cli_path), "status"],
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("Status shows satisfied", "✅" in result.stdout, result.stdout)

        # Test clear command
        result = subprocess.run(
            ["python3", str(cli_path), "clear", "commit_plan"],
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("Clear runs", result.returncode == 0, result.stderr)

        # Test list command
        result = subprocess.run(
            ["python3", str(cli_path), "list"],
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("List runs", result.returncode == 0, result.stderr)


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
        from session import get_registry_path, update_registry
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

            # Test satisfy with CLAUDE_SESSION_ID env var
            result = subprocess.run(
                ["python3", str(cli_path), "satisfy", "commit_plan"],
                cwd=tmpdir, capture_output=True, text=True,
                env={**os.environ, "CLAUDE_PROJECT_DIR": tmpdir, "CLAUDE_SESSION_ID": test_session_id}
            )
            runner.test("Satisfy with env var runs", result.returncode == 0, result.stderr)

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

        # Create config
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

        # Test with config (should prompt)
        result = subprocess.run(
            ["python3", str(hook_path)],
            input='{"tool_name":"Edit"}',
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("With config = pass", result.returncode == 0)
        runner.test("With config = denies", '"permissionDecision": "deny"' in result.stdout, f"Got: {result.stdout}")

        # Satisfy the requirement
        cli_path = Path(__file__).parent / "requirements-cli.py"
        subprocess.run(
            ["python3", str(cli_path), "satisfy", "commit_plan"],
            cwd=tmpdir, capture_output=True
        )

        # Test after satisfy (should pass silently)
        result = subprocess.run(
            ["python3", str(hook_path)],
            input='{"tool_name":"Edit"}',
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

        # Test hook output contains checklist
        result = subprocess.run(
            ["python3", str(hook_path)],
            input='{"tool_name":"Edit"}',
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


def test_main_master_skip(runner: TestRunner):
    """Test that main/master branches are skipped."""
    print("\n📦 Testing main/master branch skip...")

    hook_path = Path(__file__).parent / "check-requirements.py"

    with tempfile.TemporaryDirectory() as tmpdir:
        # Initialize git repo on main
        subprocess.run(["git", "init", "-b", "main"], cwd=tmpdir, capture_output=True)

        # Create config
        os.makedirs(f"{tmpdir}/.claude")
        config = {
            "version": "1.0",
            "enabled": True,
            "requirements": {
                "commit_plan": {"enabled": True, "scope": "session", "message": "Need plan!"}
            }
        }
        with open(f"{tmpdir}/.claude/requirements.yaml", 'w') as f:
            json.dump(config, f)

        # Test on main (should skip)
        result = subprocess.run(
            ["python3", str(hook_path)],
            input='{"tool_name":"Edit"}',
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("Main branch = skip", result.stdout.strip() == "", f"Got: {result.stdout}")


def main():
    """Run all tests."""
    print("🧪 Requirements Framework Test Suite")
    print("=" * 50)

    runner = TestRunner()

    test_session_module(runner)
    test_session_registry(runner)
    test_git_utils_module(runner)
    test_state_storage_module(runner)
    test_config_module(runner)
    test_requirements_manager(runner)
    test_cli_commands(runner)
    test_cli_sessions_command(runner)
    test_hook_behavior(runner)
    test_checklist_rendering(runner)
    test_main_master_skip(runner)

    return runner.summary()


if __name__ == "__main__":
    sys.exit(main())
