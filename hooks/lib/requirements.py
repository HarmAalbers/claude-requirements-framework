#!/usr/bin/env python3
"""
Core requirements management API.

The BranchRequirements class provides the main interface for checking
and satisfying requirements. It handles different scopes:

- session: Requirement resets each Claude session (forces daily planning)
- branch: Requirement persists for the branch (one-time per branch)
- permanent: Never resets (rare, use for things like "reviewed security")
- single_use: Like session, but auto-clears after the triggering action completes
              (e.g., must review before EACH commit, not just once per session)

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
            session_id: Current session identifier (will be normalized to 8-char format)
            project_dir: Project root directory
        """
        # Normalize session_id to ensure consistent 8-char format
        try:
            from .session import normalize_session_id
        except ImportError:
            from session import normalize_session_id

        self.branch = branch
        self.session_id = normalize_session_id(session_id)
        self.project_dir = project_dir
        self._state = load_state(branch, project_dir)

        # Migrate old state with full UUID session keys to normalized 8-char format
        self._migrate_session_keys()

    def _migrate_session_keys(self) -> None:
        """
        Migrate session keys from full UUID format to 8-char normalized format.

        This is a one-time migration for existing state files that may contain
        full UUID session keys (from when CLAUDE_SESSION_ID provided full UUIDs).
        Runs on every load but is idempotent and fail-safe.

        Example transformation:
            "cad0ac4d-3933-45ad-9a1c-14aec05bb940" → "cad0ac4d"

        Handles conflicts by keeping the newer timestamp if both formats exist.
        """
        try:
            from .session import normalize_session_id
        except ImportError:
            from session import normalize_session_id

        migrated = False

        for req_name, req_state in self._state['requirements'].items():
            if 'sessions' not in req_state:
                continue

            sessions = req_state['sessions']
            old_keys = list(sessions.keys())

            for old_key in old_keys:
                normalized_key = normalize_session_id(old_key)

                # Skip if already normalized (idempotent)
                if old_key == normalized_key:
                    continue

                # Handle conflicts: if normalized key already exists, keep newer
                if normalized_key in sessions:
                    old_data = sessions[old_key]
                    new_data = sessions[normalized_key]

                    old_time = old_data.get('satisfied_at', 0)
                    new_time = new_data.get('satisfied_at', 0)

                    # Keep whichever has the newer timestamp
                    if old_time > new_time:
                        sessions[normalized_key] = old_data
                else:
                    # No conflict: move data to normalized key
                    sessions[normalized_key] = sessions[old_key]

                # Remove old key
                del sessions[old_key]
                migrated = True

        # Save migrated state
        if migrated:
            self._save()

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

        Handles different scopes and TTL expiration. Also checks for branch-level
        overrides that apply to all sessions (set via `req satisfy --branch`).

        Args:
            req_name: Requirement name
            scope: One of 'session', 'branch', 'permanent', 'single_use'

        Returns:
            True if requirement is currently satisfied
        """
        req_state = self._get_req_state(req_name)
        now = time.time()

        # Check for branch-level override first (even for session-scoped requirements)
        # This allows `req satisfy --branch` to satisfy for all sessions
        if scope in ('session', 'single_use') and req_state.get('satisfied', False):
            # Branch-level satisfaction exists - check TTL if present
            expires_at = req_state.get('expires_at')
            if expires_at is None or now <= expires_at:
                return True  # Branch-level override is active

        if scope in ('session', 'single_use'):
            # Session/single_use scope: check current session only
            # (single_use behaves like session for satisfaction check;
            #  the difference is that it auto-clears after the action completes)
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
            scope: One of 'session', 'branch', 'permanent', 'single_use'
            method: How it was satisfied ('cli', 'auto', 'skill', etc.)
            metadata: Optional extra data (e.g., {"ticket": "#1234"})
            ttl: Optional time-to-live in seconds
        """
        req_state = self._get_req_state(req_name)
        req_state['scope'] = scope
        now = int(time.time())

        if scope in ('session', 'single_use'):
            # Session/single_use: store under current session ID
            # (single_use is stored the same way; it's cleared via clear_single_use())
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

    def clear_single_use(self, req_name: str) -> bool:
        """
        Clear a single_use requirement for the current session only.

        This is called after a triggering action (like git commit) completes
        successfully, to ensure the requirement must be satisfied again
        before the next action.

        Only clears if the requirement's scope is 'single_use'. This ensures
        session-scoped requirements aren't accidentally cleared.

        Args:
            req_name: Requirement name to clear

        Returns:
            True if the requirement was cleared, False otherwise
        """
        req_state = self._state['requirements'].get(req_name, {})

        # Only clear if scope is single_use
        if req_state.get('scope') != 'single_use':
            return False

        # Clear only the current session's satisfaction
        sessions = req_state.get('sessions', {})
        if self.session_id in sessions:
            del sessions[self.session_id]
            self._save()
            return True

        return False

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

    def approve_for_session(self, req_name: str, ttl: int, metadata: dict = None) -> None:
        """
        Record user approval for a dynamic requirement.

        This is specifically for dynamic requirements where the user approves
        continuing despite a threshold being exceeded. The approval is
        session-scoped and expires after the TTL.

        Args:
            req_name: Requirement name
            ttl: Time-to-live in seconds (approval duration)
            metadata: Optional metadata (e.g., value at approval time)

        Note:
            Uses the same state structure as satisfy() but specifically
            sets satisfied_by='approval' to distinguish from manual CLI satisfaction.
        """
        req_state = self._get_req_state(req_name)
        req_state['scope'] = 'session'  # Approvals are always session-scoped

        if 'sessions' not in req_state:
            req_state['sessions'] = {}

        if self.session_id not in req_state['sessions']:
            req_state['sessions'][self.session_id] = {}

        now = int(time.time())
        session_state = req_state['sessions'][self.session_id]

        session_state.update({
            'satisfied': True,
            'satisfied_at': now,
            'satisfied_by': 'approval',  # Marks this as approval (vs 'cli')
            'expires_at': now + ttl,
            'metadata': metadata or {}
        })

        self._save()

    def is_approved(self, req_name: str) -> bool:
        """
        Check if dynamic requirement is approved and not expired.

        This specifically checks for approval-based satisfaction (not manual
        CLI satisfaction). Used by dynamic requirement strategies to short-circuit
        calculation when user has recently approved.

        Args:
            req_name: Requirement name

        Returns:
            True if approved and TTL not expired, False otherwise

        Note:
            This is stricter than is_satisfied() - it only returns True for
            approvals (satisfied_by='approval'), not for manual CLI satisfaction.
        """
        req_state = self._get_req_state(req_name)
        sessions = req_state.get('sessions', {})

        if self.session_id not in sessions:
            return False

        session_state = sessions[self.session_id]

        # Must be satisfied
        if not session_state.get('satisfied', False):
            return False

        # Must be via approval (not manual CLI satisfy)
        if session_state.get('satisfied_by') != 'approval':
            return False

        # Must have expiration (approvals always have TTL)
        expires_at = session_state.get('expires_at')
        if not expires_at:
            return False

        # Check if expired
        now = int(time.time())
        if now >= expires_at:
            return False

        return True

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
