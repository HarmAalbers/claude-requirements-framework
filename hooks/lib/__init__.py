"""
Requirements Framework Library

A standalone requirements enforcement framework for Claude Code.
Ensures developers satisfy requirements (like commit plans) before making code changes.

Architecture:
- session.py: Session ID management
- git_utils.py: Git operations
- state_storage.py: Per-branch state persistence
- config.py: Configuration loading (global → project → local)
- requirements.py: Core BranchRequirements API

Usage:
    from lib.requirements import BranchRequirements
    from lib.config import RequirementsConfig

    config = RequirementsConfig('/path/to/project')
    reqs = BranchRequirements('feature/auth', 'session-123', '/path/to/project')

    if not reqs.is_satisfied('commit_plan', scope='session'):
        print("Requirement not satisfied")

    reqs.satisfy('commit_plan', scope='session', method='cli')
"""

__version__ = "1.0.0"
