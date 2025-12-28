#!/usr/bin/env python3
"""
Calculation Cache

TTL-based cache for expensive calculations (performance optimization).

This is kept separate from business state (BranchRequirements) following the
Single Responsibility Principle. The cache is pure performance optimization
and can be cleared without affecting requirement satisfaction state.

Key design decisions:
- User-specific temp files (prevents conflicts on shared systems)
- TTL-based expiration (configurable per requirement)
- Fail-silent on all errors (cache failures never block operations)
- Separate from .git/requirements/ state (different lifecycle)
"""

import json
import os
import tempfile
import time
from typing import Optional
from pathlib import Path


class CalculationCache:
    """
    TTL-based cache for expensive calculations.

    Stores calculation results in a user-specific temp file with timestamps.
    Results expire after their TTL and are recalculated on next access.

    Thread-safety: Not thread-safe (single-user CLI tool, acceptable tradeoff)
    """

    def __init__(self):
        """Initialize cache with user-specific temp file."""
        # User-specific temp file (prevents conflicts on shared systems)
        # Uses UID on Unix, falls back to username on Windows
        try:
            # Unix systems
            user_id = str(os.getuid())
        except AttributeError:
            # Windows fallback
            import getpass
            user_id = getpass.getuser()

        self.cache_file = (
            Path(tempfile.gettempdir()) /
            f"claude-req-calc-cache-{user_id}.json"
        )

    def get(self, cache_key: str, ttl: int) -> Optional[dict]:
        """
        Get cached result if still valid.

        Args:
            cache_key: Unique key for the cached calculation
            ttl: Time-to-live in seconds

        Returns:
            Cached data dict if valid and exists, None otherwise

        Note:
            Any error (missing file, corrupt JSON, etc.) returns None.
            This ensures cache failures never block operations.
        """
        try:
            if not self.cache_file.exists():
                return None

            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache = json.load(f)

            entry = cache.get(cache_key, {})
            timestamp = entry.get('timestamp', 0)
            age = time.time() - timestamp

            if age < ttl:
                return entry.get('data')

            # Cache expired
            return None

        except (json.JSONDecodeError, KeyError, TypeError, OSError):
            # Any error = cache miss
            return None

    def set(self, cache_key: str, data: dict) -> None:
        """
        Store result in cache with current timestamp.

        Args:
            cache_key: Unique key for the calculation
            data: Data to cache (must be JSON-serializable)

        Note:
            Failures are silent - cache writes are non-critical.
            If the cache file is corrupted or write fails, the next
            get() will just miss and recalculate.
        """
        try:
            # Load existing cache (if any)
            cache = {}
            if self.cache_file.exists():
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache = json.load(f)

            # Update cache with new entry
            cache[cache_key] = {
                'timestamp': time.time(),
                'data': data
            }

            # Write back to file
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache, f, indent=2)

        except (json.JSONDecodeError, TypeError, OSError):
            # Silent fail on cache write errors
            pass

    def clear(self, cache_key: Optional[str] = None) -> None:
        """
        Clear cache entry or entire cache.

        Args:
            cache_key: Specific key to clear, or None to clear all

        Note:
            Fails silently on errors.
        """
        try:
            if cache_key is None:
                # Clear entire cache
                if self.cache_file.exists():
                    self.cache_file.unlink()
            else:
                # Clear specific entry
                if not self.cache_file.exists():
                    return

                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache = json.load(f)

                if cache_key in cache:
                    del cache[cache_key]

                    with open(self.cache_file, 'w', encoding='utf-8') as f:
                        json.dump(cache, f, indent=2)

        except (json.JSONDecodeError, TypeError, OSError, KeyError):
            # Silent fail
            pass
