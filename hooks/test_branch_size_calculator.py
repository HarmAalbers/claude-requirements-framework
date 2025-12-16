#!/usr/bin/env python3
"""
Test Suite for Branch Size Calculator

Tests the BranchSizeCalculator implementation following TDD principles.
This file is written BEFORE the implementation (Red phase).

Run with: python3 test_branch_size_calculator.py
"""

import sys
import os
import subprocess
import tempfile
import time
from pathlib import Path

# Add lib directory to path
lib_path = Path(__file__).parent / 'lib'
sys.path.insert(0, str(lib_path))

from branch_size_calculator import BranchSizeCalculator


class TestRunner:
    """Simple test runner with colored output."""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.failed_tests = []

    def test(self, name: str, condition: bool, msg: str = ""):
        """Run a test and record the result."""
        if condition:
            print(f"  ✅ {name}")
            self.passed += 1
        else:
            print(f"  ❌ {name}: {msg}")
            self.failed += 1
            self.failed_tests.append((name, msg))

    def summary(self):
        """Print summary and return exit code."""
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"Results: {self.passed}/{total} passed")

        if self.failed_tests:
            print(f"\nFailed tests:")
            for name, msg in self.failed_tests:
                print(f"  • {name}: {msg}")

        return 0 if self.failed == 0 else 1


def setup_git_repo(tmpdir: str, branch_name: str = 'main') -> None:
    """Initialize a git repo with basic config."""
    subprocess.run(['git', 'init'], cwd=tmpdir, capture_output=True)
    subprocess.run(['git', 'config', 'user.email', 'test@test.com'],
                  cwd=tmpdir, capture_output=True)
    subprocess.run(['git', 'config', 'user.name', 'Test User'],
                  cwd=tmpdir, capture_output=True)
    subprocess.run(['git', 'branch', '-M', branch_name],
                  cwd=tmpdir, capture_output=True)


# ============================================================================
# Skip Conditions Tests
# ============================================================================

def test_skip_main_branch(runner: TestRunner):
    """Test that main branch returns None (skip check)."""
    print("\n📦 Testing skip conditions...")

    with tempfile.TemporaryDirectory() as tmpdir:
        setup_git_repo(tmpdir, 'main')

        calc = BranchSizeCalculator()
        result = calc.calculate(tmpdir, 'main')

        runner.test(
            "Skip main branch",
            result is None,
            f"Expected None, got {result}"
        )


def test_skip_master_branch(runner: TestRunner):
    """Test that master branch returns None (skip check)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        setup_git_repo(tmpdir, 'master')

        calc = BranchSizeCalculator()
        result = calc.calculate(tmpdir, 'master')

        runner.test(
            "Skip master branch",
            result is None,
            f"Expected None, got {result}"
        )


def test_skip_no_base_branch(runner: TestRunner):
    """Test that branches with no base return None."""
    with tempfile.TemporaryDirectory() as tmpdir:
        setup_git_repo(tmpdir, 'feature/test')

        # No commits, no origin - can't find base
        calc = BranchSizeCalculator()
        result = calc.calculate(tmpdir, 'feature/test')

        runner.test(
            "Skip when no base branch found",
            result is None,
            f"Expected None, got {result}"
        )


# ============================================================================
# Basic Calculation Tests
# ============================================================================

def test_calculate_simple_branch(runner: TestRunner):
    """Test basic branch size calculation."""
    print("\n📦 Testing basic calculation...")

    with tempfile.TemporaryDirectory() as tmpdir:
        setup_git_repo(tmpdir, 'main')

        # Create base commit
        Path(tmpdir, 'base.txt').write_text('line1\nline2\nline3\n')
        subprocess.run(['git', 'add', '.'], cwd=tmpdir, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'base'], cwd=tmpdir, capture_output=True)

        # Create feature branch with changes
        subprocess.run(['git', 'checkout', '-b', 'feature/test'],
                      cwd=tmpdir, capture_output=True)

        # Add 5 lines (committed)
        Path(tmpdir, 'file1.txt').write_text('line1\nline2\nline3\nline4\nline5\n')
        subprocess.run(['git', 'add', '.'], cwd=tmpdir, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'add file1'],
                      cwd=tmpdir, capture_output=True)

        calc = BranchSizeCalculator()
        result = calc.calculate(tmpdir, 'feature/test')

        runner.test(
            "Returns dict for valid branch",
            result is not None and isinstance(result, dict),
            f"Expected dict, got {type(result)}"
        )

        if result:
            runner.test(
                "Has 'value' key",
                'value' in result,
                f"Missing 'value' key in {result.keys()}"
            )

            runner.test(
                "Has 'summary' key",
                'summary' in result,
                f"Missing 'summary' key in {result.keys()}"
            )

            runner.test(
                "Has 'base_branch' key",
                'base_branch' in result,
                f"Missing 'base_branch' key in {result.keys()}"
            )

            runner.test(
                "Correct total (5 lines)",
                result.get('value') == 5,
                f"Expected 5, got {result.get('value')}"
            )


def test_calculate_with_staged_and_unstaged(runner: TestRunner):
    """Test calculation includes committed + staged + unstaged changes."""
    print("\n📦 Testing three-way calculation...")

    with tempfile.TemporaryDirectory() as tmpdir:
        setup_git_repo(tmpdir, 'main')

        # Base commit
        Path(tmpdir, 'base.txt').write_text('base\n')
        subprocess.run(['git', 'add', '.'], cwd=tmpdir, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'base'], cwd=tmpdir, capture_output=True)

        # Feature branch
        subprocess.run(['git', 'checkout', '-b', 'feature/test'],
                      cwd=tmpdir, capture_output=True)

        # Committed: +5 lines
        Path(tmpdir, 'file1.txt').write_text('1\n2\n3\n4\n5\n')
        subprocess.run(['git', 'add', '.'], cwd=tmpdir, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'add file1'],
                      cwd=tmpdir, capture_output=True)

        # Staged: +3 lines
        Path(tmpdir, 'file2.txt').write_text('1\n2\n3\n')
        subprocess.run(['git', 'add', '.'], cwd=tmpdir, capture_output=True)

        # Unstaged: +2 lines
        Path(tmpdir, 'file3.txt').write_text('1\n2\n')

        calc = BranchSizeCalculator()
        result = calc.calculate(tmpdir, 'feature/test')

        if result:
            runner.test(
                "Total = committed + staged + unstaged (10)",
                result.get('value') == 10,
                f"Expected 10, got {result.get('value')}"
            )


# ============================================================================
# Stacked PR Tests
# ============================================================================

def test_stacked_pr_2_levels(runner: TestRunner):
    """Test 2-level stacked PR: main → PR1 → PR2."""
    print("\n📦 Testing stacked PRs...")

    with tempfile.TemporaryDirectory() as tmpdir:
        setup_git_repo(tmpdir, 'main')

        # Base commit on main
        Path(tmpdir, 'base.txt').write_text('base\n')
        subprocess.run(['git', 'add', '.'], cwd=tmpdir, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'base'], cwd=tmpdir, capture_output=True)

        # PR1: +10 lines
        subprocess.run(['git', 'checkout', '-b', 'feature/pr1'],
                      cwd=tmpdir, capture_output=True)
        Path(tmpdir, 'pr1.txt').write_text('\n'.join([f'line{i}' for i in range(10)]))
        subprocess.run(['git', 'add', '.'], cwd=tmpdir, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'pr1'], cwd=tmpdir, capture_output=True)

        # PR2 (stacked on PR1): +5 lines
        subprocess.run(['git', 'checkout', '-b', 'feature/pr2'],
                      cwd=tmpdir, capture_output=True)
        Path(tmpdir, 'pr2.txt').write_text('\n'.join([f'line{i}' for i in range(5)]))
        subprocess.run(['git', 'add', '.'], cwd=tmpdir, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'pr2'], cwd=tmpdir, capture_output=True)

        calc = BranchSizeCalculator()
        result = calc.calculate(tmpdir, 'feature/pr2')

        if result:
            runner.test(
                "PR2 counts only its 5 changes (not PR1's 10)",
                result.get('value') == 5,
                f"Expected 5, got {result.get('value')} - should only count PR2 changes"
            )

            runner.test(
                "Base branch is PR1 (not main)",
                'pr1' in result.get('base_branch', ''),
                f"Expected base 'feature/pr1', got {result.get('base_branch')}"
            )


def test_stacked_pr_3_levels(runner: TestRunner):
    """Test 3-level stacked PR: main → PR1 → PR2 → PR3."""
    with tempfile.TemporaryDirectory() as tmpdir:
        setup_git_repo(tmpdir, 'main')

        # Base
        Path(tmpdir, 'base.txt').write_text('base\n')
        subprocess.run(['git', 'add', '.'], cwd=tmpdir, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'base'], cwd=tmpdir, capture_output=True)

        # PR1: +10
        subprocess.run(['git', 'checkout', '-b', 'feature/pr1'],
                      cwd=tmpdir, capture_output=True)
        Path(tmpdir, 'pr1.txt').write_text('\n'.join([f'line{i}' for i in range(10)]))
        subprocess.run(['git', 'add', '.'], cwd=tmpdir, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'pr1'], cwd=tmpdir, capture_output=True)

        # PR2: +5
        subprocess.run(['git', 'checkout', '-b', 'feature/pr2'],
                      cwd=tmpdir, capture_output=True)
        Path(tmpdir, 'pr2.txt').write_text('\n'.join([f'line{i}' for i in range(5)]))
        subprocess.run(['git', 'add', '.'], cwd=tmpdir, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'pr2'], cwd=tmpdir, capture_output=True)

        # PR3: +3
        subprocess.run(['git', 'checkout', '-b', 'feature/pr3'],
                      cwd=tmpdir, capture_output=True)
        Path(tmpdir, 'pr3.txt').write_text('\n'.join([f'line{i}' for i in range(3)]))
        subprocess.run(['git', 'add', '.'], cwd=tmpdir, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'pr3'], cwd=tmpdir, capture_output=True)

        calc = BranchSizeCalculator()
        result = calc.calculate(tmpdir, 'feature/pr3')

        if result:
            runner.test(
                "PR3 counts only its 3 changes",
                result.get('value') == 3,
                f"Expected 3, got {result.get('value')}"
            )


# ============================================================================
# Shortstat Parsing Tests
# ============================================================================

def test_parse_shortstat(runner: TestRunner):
    """Test shortstat parsing."""
    print("\n📦 Testing shortstat parsing...")

    calc = BranchSizeCalculator()

    # Test insertions only
    result = calc._parse_shortstat(" 5 files changed, 120 insertions(+)")
    runner.test(
        "Parse insertions only",
        result == {'ins': 120, 'del': 0},
        f"Expected {{'ins': 120, 'del': 0}}, got {result}"
    )

    # Test deletions only
    result = calc._parse_shortstat(" 2 files changed, 50 deletions(-)")
    runner.test(
        "Parse deletions only",
        result == {'ins': 0, 'del': 50},
        f"Expected {{'ins': 0, 'del': 50}}, got {result}"
    )

    # Test both
    result = calc._parse_shortstat(" 10 files changed, 200 insertions(+), 150 deletions(-)")
    runner.test(
        "Parse both ins and del",
        result == {'ins': 200, 'del': 150},
        f"Expected {{'ins': 200, 'del': 150}}, got {result}"
    )

    # Test empty
    result = calc._parse_shortstat("")
    runner.test(
        "Parse empty string",
        result == {'ins': 0, 'del': 0},
        f"Expected {{'ins': 0, 'del': 0}}, got {result}"
    )


# ============================================================================
# Error Path Tests (CRITICAL - Must Fail Open)
# ============================================================================

def test_no_git_repo(runner: TestRunner):
    """Test that non-git directory returns None (fail open)."""
    print("\n📦 Testing error paths...")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Don't initialize git
        calc = BranchSizeCalculator()
        result = calc.calculate(tmpdir, 'feature/test')

        runner.test(
            "Fail open on non-git repo",
            result is None,
            f"Expected None, got {result}"
        )


def test_detached_head(runner: TestRunner):
    """Test that detached HEAD returns None."""
    with tempfile.TemporaryDirectory() as tmpdir:
        setup_git_repo(tmpdir, 'main')

        # Create commit
        Path(tmpdir, 'file.txt').write_text('content')
        subprocess.run(['git', 'add', '.'], cwd=tmpdir, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'commit'], cwd=tmpdir, capture_output=True)

        # Detach HEAD
        result = subprocess.run(['git', 'rev-parse', 'HEAD'],
                               cwd=tmpdir, capture_output=True, text=True)
        commit_hash = result.stdout.strip()
        subprocess.run(['git', 'checkout', commit_hash],
                      cwd=tmpdir, capture_output=True)

        calc = BranchSizeCalculator()
        # Detached HEAD shows as commit hash
        result_calc = calc.calculate(tmpdir, commit_hash)

        runner.test(
            "Fail open on detached HEAD",
            result_calc is None,
            f"Expected None for detached HEAD, got {result_calc}"
        )


# ============================================================================
# Main Test Runner
# ============================================================================

def main():
    """Run all tests."""
    print("🧪 Branch Size Calculator Test Suite (TDD Red Phase)")
    print("=" * 60)

    runner = TestRunner()

    # Skip conditions
    test_skip_main_branch(runner)
    test_skip_master_branch(runner)
    test_skip_no_base_branch(runner)

    # Basic calculation
    test_calculate_simple_branch(runner)
    test_calculate_with_staged_and_unstaged(runner)

    # Stacked PRs
    test_stacked_pr_2_levels(runner)
    test_stacked_pr_3_levels(runner)

    # Parsing
    test_parse_shortstat(runner)

    # Error paths
    test_no_git_repo(runner)
    test_detached_head(runner)

    return runner.summary()


if __name__ == "__main__":
    sys.exit(main())
