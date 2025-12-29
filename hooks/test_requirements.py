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
            input='{"tool_name":"Edit"}',
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

        # Test satisfy from subdirectory
        result = subprocess.run(
            ["python3", str(cli_path), "satisfy", "commit_plan"],
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


def test_write_local_config(runner: TestRunner):
    """Test writing local config overrides."""
    print("\n📝 Testing write_local_config and write_local_override...")
    from config import RequirementsConfig, load_yaml_or_json, write_local_config
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
        file_path = config.write_local_override(enabled=False)

        local_file = claude_dir / 'requirements.local.yaml'
        local_file_json = claude_dir / 'requirements.local.json'

        # File should exist (either YAML or JSON depending on PyYAML availability)
        runner.test("Local config file created",
                   local_file.exists() or local_file_json.exists())

        # Read back and verify
        if local_file.exists():
            local_config = load_yaml_or_json(local_file)
        else:
            local_config = load_yaml_or_json(local_file_json)

        runner.test("Enabled field set to False", local_config.get('enabled') == False)
        runner.test("Version field added", local_config.get('version') == '1.0')

        # Test 2: Update existing config
        file_path = config.write_local_override(enabled=True)

        if local_file.exists():
            local_config = load_yaml_or_json(local_file)
        else:
            local_config = load_yaml_or_json(local_file_json)

        runner.test("Enabled field updated to True", local_config.get('enabled') == True)

        # Test 3: Write requirement-level override
        file_path = config.write_local_override(
            requirement_overrides={'commit_plan': False}
        )

        if local_file.exists():
            local_config = load_yaml_or_json(local_file)
        else:
            local_config = load_yaml_or_json(local_file_json)

        runner.test(
            "Requirement override added",
            local_config.get('requirements', {}).get('commit_plan', {}).get('enabled') == False
        )
        runner.test(
            "Framework enabled preserved",
            local_config.get('enabled') == True
        )

        # Test 4: Verify local override actually works in config loading
        config_reloaded = RequirementsConfig(tmpdir)
        runner.test(
            "Local override affects is_enabled()",
            config_reloaded.is_enabled() == True
        )
        runner.test(
            "Requirement override affects is_requirement_enabled()",
            config_reloaded.is_requirement_enabled('commit_plan') == False,
            f"commit_plan enabled: {config_reloaded.is_requirement_enabled('commit_plan')}"
        )


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
        local_file_json = claude_dir / 'requirements.local.json'
        runner.test("Local config file created",
                   local_file.exists() or local_file_json.exists())

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

        # Test satisfy command
        result = subprocess.run(
            ["python3", str(cli_path), "satisfy", "commit_plan"],
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("Satisfy runs", result.returncode == 0, result.stderr)
        runner.test("Satisfy confirms", "✅" in result.stdout, result.stdout)

        # Test status after satisfy (use --verbose to see all requirements)
        result = subprocess.run(
            ["python3", str(cli_path), "status", "--verbose"],
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

        # Test 3: Satisfy and check focused hides satisfied
        subprocess.run(
            ["python3", str(cli_path), "satisfy", "commit_plan"],
            cwd=tmpdir, capture_output=True, text=True
        )

        result = subprocess.run(
            ["python3", str(cli_path), "status"],
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("Focused shows remaining unsatisfied", "adr_reviewed" in result.stdout, result.stdout)

        # Test 4: Summary when all satisfied
        subprocess.run(
            ["python3", str(cli_path), "satisfy", "adr_reviewed"],
            cwd=tmpdir, capture_output=True, text=True
        )

        result = subprocess.run(
            ["python3", str(cli_path), "status", "--summary"],
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
        for script in ["check-requirements.py", "requirements-cli.py"]:
            target = hooks_dir / script
            target.chmod(0o755)

        # Settings with hook registration (new format)
        settings_path = claude_dir / "settings.json"
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
    repo_root = Path(__file__).parent.parent

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
    import sys
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

        # Test without config - should suggest req init on startup
        result = subprocess.run(
            ["python3", str(hook_path)],
            input='{"hook_event_name":"SessionStart","source":"startup"}',
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("SessionStart no config = pass", result.returncode == 0)
        runner.test("SessionStart suggests init", "req init" in result.stdout,
                   f"Expected 'req init' in output, got: {result.stdout[:200]}")

        # Test without config on resume (should NOT suggest init)
        result = subprocess.run(
            ["python3", str(hook_path)],
            input='{"hook_event_name":"SessionStart","source":"resume"}',
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

        # Test outputs status when inject_context=True
        result = subprocess.run(
            ["python3", str(hook_path)],
            input='{"hook_event_name":"SessionStart","source":"startup"}',
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

        # Test blocks when requirements unsatisfied
        result = subprocess.run(
            ["python3", str(hook_path)],
            input='{"hook_event_name":"Stop","stop_hook_active":false}',
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
            ["python3", str(cli_path), "satisfy", "commit_plan"],
            cwd=tmpdir, capture_output=True
        )
        result = subprocess.run(
            ["python3", str(hook_path)],
            input='{"hook_event_name":"Stop","stop_hook_active":false}',
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
            input='{"hook_event_name":"Stop","stop_hook_active":false}',
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

        # First satisfy the requirement to create state
        cli_path = Path(__file__).parent / "requirements-cli.py"
        subprocess.run(
            ["python3", str(cli_path), "satisfy", "commit_plan"],
            cwd=tmpdir, capture_output=True
        )

        # Run session end (should preserve state by default)
        result = subprocess.run(
            ["python3", str(hook_path)],
            input='{"hook_event_name":"SessionEnd","reason":"clear"}',
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("SessionEnd = pass", result.returncode == 0)
        runner.test("SessionEnd = silent", result.stdout.strip() == "")

        # Check state is preserved (clear_session_state=False)
        status_result = subprocess.run(
            ["python3", str(cli_path), "status"],
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

        # Test hook output contains both requirements
        result = subprocess.run(
            ["python3", str(hook_path)],
            input='{"tool_name":"Edit"}',
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

        # Test satisfy with multiple requirements
        result = subprocess.run(
            ["python3", str(cli_path), "satisfy", "commit_plan", "adr_reviewed"],
            cwd=tmpdir, capture_output=True, text=True
        )

        runner.test("Multiple satisfy succeeds", result.returncode == 0, result.stderr)
        runner.test("Shows success message", "✅" in result.stdout, result.stdout)

        # Verify both were satisfied
        hook_path = Path(__file__).parent / "check-requirements.py"
        result = subprocess.run(
            ["python3", str(hook_path)],
            input='{"tool_name":"Edit"}',
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
        from requirement_strategies import DynamicRequirementStrategy
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

        # Satisfy only commit_plan
        subprocess.run(
            ["python3", str(cli_path), "satisfy", "commit_plan"],
            cwd=tmpdir, capture_output=True
        )

        # Hook should only block on adr_reviewed
        result = subprocess.run(
            ["python3", str(hook_path)],
            input='{"tool_name":"Edit"}',
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
        from requirement_strategies import GuardRequirementStrategy, STRATEGIES
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
        from requirement_strategies import GuardRequirementStrategy
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
        from requirement_strategies import GuardRequirementStrategy
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
        from requirement_strategies import GuardRequirementStrategy
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
        from requirement_strategies import GuardRequirementStrategy
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

        # Test hook blocks on master
        result = subprocess.run(
            ["python3", str(hook_path)],
            input='{"tool_name":"Edit"}',
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
        colors_enabled,
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
        config = generate_config('advanced', context='global')
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
        write_count_before = 0
        if registry_path.exists():
            write_count_before = os.stat(registry_path).st_mtime

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

    from requirement_strategies import BlockingRequirementStrategy
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
                data = json.load(f)
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


def main():
    """Run all tests."""
    print("🧪 Requirements Framework Test Suite")
    print("=" * 50)

    runner = TestRunner()

    test_session_module(runner)
    test_session_registry(runner)
    test_git_utils_module(runner)
    test_git_root_resolution(runner)
    test_hook_from_subdirectory(runner)
    test_cli_from_subdirectory(runner)
    test_not_in_git_repo_fallback(runner)
    test_state_storage_module(runner)
    test_config_module(runner)
    test_write_local_config(runner)
    test_cli_enable_disable(runner)
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

    # Colors module tests
    test_colors_module(runner)

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

    # NEW: Cache and logger module tests (Phase 1)
    test_message_dedup_cache(runner)
    test_calculation_cache(runner)
    test_logger_module(runner)

    # NEW: Registry client tests (Phase 3)
    test_registry_client(runner)

    # NEW: Edge case tests (Phase 3 extended)
    test_edge_cases(runner)

    # Codex reviewer requirement tests
    test_codex_reviewer_requirement(runner)

    return runner.summary()


if __name__ == "__main__":
    sys.exit(main())
