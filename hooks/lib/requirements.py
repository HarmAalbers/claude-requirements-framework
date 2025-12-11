#!/usr/bin/env python3
"""
Core requirements management API.

The BranchRequirements class provides the main interface for checking
and satisfying requirements. It handles different scopes:

- session: Requirement resets each Claude session (forces daily planning)
- branch: Requirement persists for the branch (one-time per branch)
- permanent: Never resets (rare, use for things like "reviewed security")

Usage:
    reqs = BranchRequirements('feature/auth', 'session-123', '/path/to/project')

    if not reqs.is_satisfied('commit_plan', scope='session'):
        print("Need to satisfy commit_plan")

    reqs.satisfy('commit_plan', scope='session', method='cli')
"""
import time
from typing import Optional

# Handle both package import and direct execution
try:
    from .state_storage import (
        load_state,
        save_state,
        delete_state,
        list_all_states,
    )
    from .git_utils import get_all_branches
except ImportError:
    from state_storage import (
        load_state,
        save_state,
        delete_state,
        list_all_states,
    )
    from git_utils import get_all_branches


class BranchRequirements:
    """
    Requirements manager for a specific branch.

    Tracks which requirements have been satisfied and provides
    methods to check and update satisfaction status.
    """

    def __init__(self, branch: str, session_id: str, project_dir: str):
        """
        Initialize requirements manager.

        Args:
            branch: Git branch name
            session_id: Current session identifier
            project_dir: Project root directory
        """
        self.branch = branch
        self.session_id = session_id
        self.project_dir = project_dir
        self._state = load_state(branch, project_dir)

    def _save(self) -> None:
        """Save current state to disk."""
        save_state(self.branch, self.project_dir, self._state)

    def _get_req_state(self, req_name: str) -> dict:
        """
        Get or create state for a requirement.

        Args:
            req_name: Requirement name

        Returns:
            Requirement state dictionary
        """
        if req_name not in self._state['requirements']:
            self._state['requirements'][req_name] = {}
        return self._state['requirements'][req_name]

    def is_satisfied(self, req_name: str, scope: str = 'session') -> bool:
        """
        Check if requirement is satisfied.

        Handles different scopes and TTL expiration.

        Args:
            req_name: Requirement name
            scope: One of 'session', 'branch', 'permanent'

        Returns:
            True if requirement is currently satisfied
        """
        req_state = self._get_req_state(req_name)
        now = time.time()

        if scope == 'session':
            # Session scope: check current session only
            sessions = req_state.get('sessions', {})
            if self.session_id not in sessions:
                return False

            session_state = sessions[self.session_id]
            if not session_state.get('satisfied', False):
                return False

            # Check TTL expiration
            expires_at = session_state.get('expires_at')
            if expires_at and now > expires_at:
                return False

            return True

        elif scope == 'branch':
            # Branch scope: persists across sessions
            if not req_state.get('satisfied', False):
                return False

            # Check TTL expiration
            expires_at = req_state.get('expires_at')
            if expires_at and now > expires_at:
                return False

            return True

        elif scope == 'permanent':
            # Permanent scope: never expires
            return req_state.get('satisfied', False)

        # Unknown scope defaults to not satisfied
        return False

    def satisfy(
        self,
        req_name: str,
        scope: str = 'session',
        method: str = 'manual',
        metadata: Optional[dict] = None,
        ttl: Optional[int] = None
    ) -> None:
        """
        Mark requirement as satisfied.

        Args:
            req_name: Requirement name
            scope: One of 'session', 'branch', 'permanent'
            method: How it was satisfied ('cli', 'auto', 'api', etc.)
            metadata: Optional extra data (e.g., {"ticket": "#1234"})
            ttl: Optional time-to-live in seconds
        """
        req_state = self._get_req_state(req_name)
        req_state['scope'] = scope
        now = int(time.time())

        if scope == 'session':
            # Session-scoped: store under current session ID
            if 'sessions' not in req_state:
                req_state['sessions'] = {}

            session_state = {
                'satisfied': True,
                'satisfied_at': now,
                'satisfied_by': method,
            }

            if metadata:
                session_state['metadata'] = metadata

            if ttl is not None:
                session_state['expires_at'] = now + ttl
            else:
                session_state['expires_at'] = None

            req_state['sessions'][self.session_id] = session_state

        else:
            # Branch or permanent scope
            req_state['satisfied'] = True
            req_state['satisfied_at'] = now
            req_state['satisfied_by'] = method

            if metadata:
                req_state['metadata'] = metadata

            # TTL only applies to branch scope (permanent never expires)
            if ttl and scope == 'branch':
                req_state['expires_at'] = now + ttl
            else:
                req_state['expires_at'] = None

        self._save()

    def clear(self, req_name: str) -> None:
        """
        Clear a requirement (mark as unsatisfied).

        Args:
            req_name: Requirement name to clear
        """
        if req_name in self._state['requirements']:
            del self._state['requirements'][req_name]
            self._save()

    def clear_all(self) -> None:
        """Clear all requirements for this branch."""
        self._state['requirements'] = {}
        self._save()

    def get_status(self) -> dict:
        """
        Get full status for this branch.

        Returns:
            Dictionary with branch info and all requirements
        """
        return {
            'branch': self.branch,
            'session_id': self.session_id,
            'project': self.project_dir,
            'requirements': self._state['requirements'].copy()
        }

    def get_requirement_details(self, req_name: str, scope: str = 'session') -> dict:
        """
        Get detailed status for a specific requirement.

        Args:
            req_name: Requirement name
            scope: Requirement scope

        Returns:
            Dictionary with satisfaction details
        """
        req_state = self._get_req_state(req_name)
        satisfied = self.is_satisfied(req_name, scope)

        details = {
            'name': req_name,
            'scope': scope,
            'satisfied': satisfied,
        }

        if scope == 'session':
            sessions = req_state.get('sessions', {})
            if self.session_id in sessions:
                session_state = sessions[self.session_id]
                details['satisfied_at'] = session_state.get('satisfied_at')
                details['satisfied_by'] = session_state.get('satisfied_by')
                details['expires_at'] = session_state.get('expires_at')
                details['metadata'] = session_state.get('metadata')
        else:
            details['satisfied_at'] = req_state.get('satisfied_at')
            details['satisfied_by'] = req_state.get('satisfied_by')
            details['expires_at'] = req_state.get('expires_at')
            details['metadata'] = req_state.get('metadata')

        return details

    @staticmethod
    def cleanup_stale_branches(project_dir: str) -> int:
        """
        Remove state files for deleted branches.

        Compares state files against existing git branches
        and removes orphaned state files.

        Args:
            project_dir: Project root directory

        Returns:
            Number of state files removed
        """
        count = 0
        existing_branches = set(get_all_branches(project_dir))

        for branch, _path in list_all_states(project_dir):
            if branch not in existing_branches:
                delete_state(branch, project_dir)
                count += 1

        return count


if __name__ == "__main__":
    import tempfile
    import os

    # Quick test
    with tempfile.TemporaryDirectory() as tmpdir:
        # Simulate git repo
        os.makedirs(f"{tmpdir}/.git")

        # Test session scope
        reqs1 = BranchRequirements("test/branch", "session-1", tmpdir)
        assert not reqs1.is_satisfied("commit_plan", "session")

        reqs1.satisfy("commit_plan", "session", method="test")
        assert reqs1.is_satisfied("commit_plan", "session")

        # Different session should not be satisfied
        reqs2 = BranchRequirements("test/branch", "session-2", tmpdir)
        assert not reqs2.is_satisfied("commit_plan", "session")

        # Test branch scope
        reqs1.satisfy("github_ticket", "branch", metadata={"ticket": "#123"})
        assert reqs1.is_satisfied("github_ticket", "branch")

        # Branch scope persists across sessions
        reqs2 = BranchRequirements("test/branch", "session-2", tmpdir)
        assert reqs2.is_satisfied("github_ticket", "branch")

        # Test clear
        reqs2.clear("github_ticket")
        assert not reqs2.is_satisfied("github_ticket", "branch")

        # Test status
        status = reqs1.get_status()
        print(f"Status: {status}")

    print("✅ Requirements manager tests passed")
