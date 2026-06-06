#!/usr/bin/env python3
"""
Message Deduplication Cache

TTL-based cache to prevent repetitive hook spam when Claude makes parallel tool calls.

Problem:
    Claude often calls Edit/Write tools in rapid parallel bursts (e.g., modifying
    3-5 files simultaneously). Without deduplication, users see identical blocking
    messages repeated 3-5 times within milliseconds, creating overwhelming spam.

Solution:
    Cache message fingerprints with 5-second TTL. Show full message once, then
    suppress duplicates with minimal indicator until TTL expires.

This is kept separate from business state (BranchRequirements) following the
Single Responsibility Principle. Message deduplication is pure UI optimization
and can be cleared without affecting requirement satisfaction state.

Key design decisions:
- User-specific temp files (prevents conflicts on shared systems)
- TTL-based expiration (5 seconds - balances spam prevention with showing
  updated messages when Claude retries after user fixes issues)
- Fail-open on all errors (cache failures never block operations)
- Separate from .git/requirements/ state (different lifecycle)
- Auto-cleanup of expired entries (60s max age, 12x TTL for buffer)
- Atomic writes to prevent corrupted cache files

Cache file structure:
{
    "cache_key_1": {"timestamp": 1234567890.123, "message_hash": "a1b2c3d4"},
    "cache_key_2": {"timestamp": 1234567891.456, "message_hash": "e5f6g7h8"}
}
"""

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Optional

from logger import get_logger

class MessageDedupCache:
    """
    TTL-based cache for blocking message deduplication.

    Prevents showing the same blocking message repeatedly when Claude
    makes parallel Edit/Write calls within a short time window.

    Thread-safety:
        Not thread-safe. Race conditions could cause:
        - Same message shown twice if parallel reads miss cache simultaneously
        - Lost cache writes if simultaneous writes occur
        This is acceptable for single-user CLI - worst case is showing duplicate
        messages, which is the fail-open default behavior anyway.
    """

    def __init__(self):
        """
        Initialize cache with user-specific temp file.

        Raises:
            Never - initialization failures are logged but don't prevent construction
        """
        try:
            # User-specific identifier (cross-platform)
            try:
                # Unix systems
                user_id = str(os.getuid())
            except AttributeError:
                # Windows fallback
                import getpass
                user_id = getpass.getuser()

            self.cache_file = (
                Path(tempfile.gettempdir()) /
                f"claude-message-dedup-{user_id}.json"
            )

            # Optional debug mode
            self.debug = os.getenv('CLAUDE_DEDUP_DEBUG') == '1'

        except Exception as e:
            # Log initialization error but don't fail
            get_logger().warning(f"⚠️ Failed to initialize message dedup cache: {e}")
            # Fallback to home directory
            self.cache_file = Path.home() / '.claude' / 'message-dedup.json'
            self.debug = False

    def should_show_message(self, cache_key: str, message: str, ttl: int = 5) -> bool:
        """
        Check if message should be shown to user.

        Args:
            cache_key: Unique identifier for this message context (format determined by caller)
            message: The formatted message to show
            ttl: Time-to-live in seconds (default 5)

        Returns:
            True if message should be shown (first time or after TTL)
            False if recently shown (suppress to avoid spam)

        Note:
            Fails open - any error returns True (show message).
            This ensures cache failures never prevent users from seeing important info.
        """
        try:
            message_hash = self._hash_message(message)

            # Check if we recently showed this exact message
            cached = self._get_entry(cache_key, ttl)
            if cached and cached.get('message_hash') == message_hash:
                # Same message shown recently - suppress to avoid spam
                if self.debug:
                    get_logger().debug(f"[DEDUP] Suppressing: {cache_key[:50]}...")
                return False

            # Show message and cache it for future calls
            self._set_entry(cache_key, message_hash)
            if self.debug:
                get_logger().debug(
                    f"[DEDUP] Showing (first time or expired): {cache_key[:50]}..."
                )
            return True

        except (OSError, json.JSONDecodeError, KeyError, TypeError) as e:
            # Expected errors - fail-open silently
            if self.debug:
                get_logger().debug(f"[DEDUP] Expected error (failing open): {e}")
            return True
        except Exception as e:
            # Unexpected errors - log for debugging
            get_logger().warning(f"⚠️ Unexpected error in message dedup cache: {e}")
            return True  # Still fail-open

    def _hash_message(self, message: str) -> str:
        """
        Hash message for fingerprinting.

        Uses SHA256 and returns first 8 chars for compact storage.
        This detects if message content changed (e.g., requirement updated).

        Args:
            message: Full message text

        Returns:
            First 8 chars of SHA256 hex digest
        """
        return hashlib.sha256(message.encode('utf-8')).hexdigest()[:8]

    def _get_entry(self, cache_key: str, ttl: int) -> Optional[dict]:
        """
        Get cache entry if valid (not expired).

        Args:
            cache_key: Unique key for the entry
            ttl: Time-to-live in seconds

        Returns:
            Entry dict if valid and exists, None otherwise

        Expected errors (all return None):
            - FileNotFoundError: No cache file yet
            - PermissionError: Can't read temp dir
            - json.JSONDecodeError: Corrupted cache file
            - KeyError/TypeError: Malformed cache structure
        """
        try:
            if not self.cache_file.exists():
                return None

            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache = json.load(f)

            entry = cache.get(cache_key)
            if not entry:
                return None

            # Check TTL
            age = time.time() - entry.get('timestamp', 0)
            if age < ttl:
                return entry

            # Cache expired
            return None

        except json.JSONDecodeError as e:
            # Corrupted cache - log and auto-recover
            if self.debug:
                get_logger().debug(f"[DEDUP] Corrupted cache, resetting: {e}")
            try:
                self.cache_file.unlink()  # Delete corrupted file
            except OSError:
                pass
            return None
        except (FileNotFoundError, PermissionError, KeyError, TypeError, OSError):
            return None

    def _set_entry(self, cache_key: str, message_hash: str) -> None:
        """
        Store cache entry with current timestamp using atomic write.

        Args:
            cache_key: Unique key for the entry
            message_hash: Hash of the message content

        Note:
            Uses atomic write (temp file + rename) to prevent corruption.
            Failures are silent - cache writes are non-critical.
        """
        try:
            # Load existing cache (if any)
            cache = {}
            if self.cache_file.exists():
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache = json.load(f)

            # Add entry
            cache[cache_key] = {
                'timestamp': time.time(),
                'message_hash': message_hash
            }

            # Cleanup old entries (60s = 12x default TTL, provides buffer for custom TTLs)
            self._cleanup_expired(cache, max_age=60)

            # Atomic write: write to temp file, then rename
            import tempfile as tf
            cache_dir = self.cache_file.parent
            fd, temp_path = tf.mkstemp(dir=cache_dir, suffix='.json')
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(cache, f, indent=2)
                # Atomic on POSIX, best-effort on Windows
                os.replace(temp_path, self.cache_file)
            except Exception:
                # Clean up temp file on failure
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
                raise

        except (json.JSONDecodeError, TypeError, OSError):
            pass

    def _cleanup_expired(self, cache: dict, max_age: int) -> None:
        """
        Remove expired entries in-place.

        This prevents unbounded cache growth by removing entries
        older than max_age seconds.

        Args:
            cache: Cache dict to clean
            max_age: Maximum age in seconds before removal (60s by default,
                    which is 12x the default 5s TTL to handle custom TTL values
                    and provide buffer against clock skew)

        Note:
            Modifies cache dict in-place.
        """
        try:
            now = time.time()
            expired = [
                key for key, val in cache.items()
                if now - val.get('timestamp', 0) > max_age
            ]
            for key in expired:
                del cache[key]
        except Exception:
            pass

    def clear(self) -> None:
        """
        Clear entire cache by deleting the cache file.

        Useful for testing or manual reset.
        """
        try:
            if self.cache_file.exists():
                self.cache_file.unlink()
        except OSError:
            pass
