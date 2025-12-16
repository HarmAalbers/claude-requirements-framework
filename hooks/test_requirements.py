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
            ["python3", str(cli_path), "status"],
            cwd=tmpdir_invalid, capture_output=True, text=True
        )

        runner.test("Status reports validation errors", "Configuration validation failed" in result.stdout, result.stdout)
        runner.test(
            "Status includes remediation hint",
            "Fix .claude/requirements.yaml" in result.stdout,
            result.stdout,
        )


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

        # Test without config (should pass silently)
        result = subprocess.run(
            ["python3", str(hook_path)],
            input='{"hook_event_name":"SessionStart","source":"startup"}',
            cwd=tmpdir, capture_output=True, text=True
        )
        runner.test("SessionStart no config = pass", result.returncode == 0)

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
    test_cli_commands(runner)
    test_cli_sessions_command(runner)
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
    test_partial_satisfaction(runner)

    # Guard strategy tests
    test_guard_strategy_blocks_protected_branch(runner)
    test_guard_strategy_allows_feature_branch(runner)
    test_guard_strategy_respects_custom_branch_list(runner)
    test_guard_strategy_approval_bypasses_check(runner)
    test_guard_strategy_unknown_guard_type_allows(runner)
    test_guard_hook_integration(runner)

    return runner.summary()


if __name__ == "__main__":
    sys.exit(main())
