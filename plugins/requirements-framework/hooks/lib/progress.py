#!/usr/bin/env python3
"""
Progress Reporting for Requirements Framework

Provides streaming progress indicators for slow operations.
All output goes to stderr only - never interferes with hook JSON on stdout.

Usage:
    from progress import ProgressReporter, progress_context

    # Context manager (auto-hides if operation is fast)
    with progress_context("Branch analysis", min_duration=0.3) as progress:
        progress.status("finding base branch")
        base = find_base_branch()
        progress.status("calculating changes")
        changes = calculate_changes()

    # Manual control
    progress = ProgressReporter("Stacked PR detection")
    for i, candidate in enumerate(candidates):
        progress.status(f"{candidate} ({i+1}/{len(candidates)})")
        # ... work
    progress.clear()  # Remove progress line

Environment Variables:
    NO_COLOR=1          Disable progress indicators (same as colors.py)
    FORCE_COLOR=1       Force progress even in non-TTY (same as colors.py)
    SHOW_PROGRESS=0     Explicitly disable progress indicators
    SHOW_PROGRESS=1     Force progress indicators on

Design:
    - All output to stderr (hook JSON uses stdout)
    - TTY detection: only shows progress on interactive terminals
    - Uses \\r\\033[K for inline updates (carriage return + clear line)
    - Respects NO_COLOR, FORCE_COLOR, and SHOW_PROGRESS env vars
    - Context manager auto-hides for fast operations (< min_duration)
"""
import os
import sys
import time
from contextlib import contextmanager
from typing import Generator, Optional


def _progress_enabled() -> bool:
    """
    Check if progress indicators should be shown.

    Checks in order:
    1. SHOW_PROGRESS=0 - explicitly disabled
    2. SHOW_PROGRESS=1 - explicitly enabled (even non-TTY)
    3. NO_COLOR env var - disables progress (consistent with colors.py)
    4. FORCE_COLOR env var - forces progress on (consistent with colors.py)
    5. stderr.isatty() - must be an interactive terminal

    Returns:
        True if progress should be shown
    """
    # Check explicit SHOW_PROGRESS override first
    show_progress = os.environ.get('SHOW_PROGRESS', '').lower()
    if show_progress == '0' or show_progress == 'false':
        return False
    if show_progress == '1' or show_progress == 'true':
        return True

    # Respect NO_COLOR standard (https://no-color.org/)
    if os.environ.get('NO_COLOR'):
        return False

    # Check FORCE_COLOR override
    if os.environ.get('FORCE_COLOR'):
        return True

    # Check if stderr is a TTY
    if not hasattr(sys.stderr, 'isatty') or not sys.stderr.isatty():
        return False

    return True


# Cache the result at module load time
_cached_progress_enabled: Optional[bool] = None

# Default timing threshold (can be overridden via config)
_default_timing_threshold: float = 0.3


def configure_progress(
    show_progress: Optional[bool] = None,
    timing_threshold: Optional[float] = None
) -> None:
    """
    Configure progress behavior from requirements config.

    Called by RequirementsConfig after loading to apply config-based settings.
    Config settings take precedence over environment variables.

    Args:
        show_progress: Force progress on/off (None = use env/TTY detection)
        timing_threshold: Min duration before showing completion (default: 0.3s)
    """
    global _cached_progress_enabled, _default_timing_threshold

    if show_progress is not None:
        _cached_progress_enabled = show_progress
    else:
        # Reset cache to re-evaluate from environment
        _cached_progress_enabled = None

    if timing_threshold is not None:
        _default_timing_threshold = timing_threshold


def get_default_timing_threshold() -> float:
    """Get the default timing threshold for progress_context."""
    return _default_timing_threshold


def progress_enabled() -> bool:
    """
    Check if progress is enabled (cached).

    Returns:
        True if progress should be shown
    """
    global _cached_progress_enabled
    if _cached_progress_enabled is None:
        _cached_progress_enabled = _progress_enabled()
    return _cached_progress_enabled


def reset_progress_cache() -> None:
    """Reset the cached progress enabled state. Useful for testing."""
    global _cached_progress_enabled
    _cached_progress_enabled = None


class ProgressReporter:
    """
    Reports progress to stderr with timing information.

    All output goes to stderr, never stdout. This ensures hook JSON
    output is never corrupted by progress messages.

    Attributes:
        description: Short description of the operation (e.g., "Branch analysis")
        debug: If True, collect timing data for detailed report
        start_time: When the operation started
    """

    def __init__(self, description: str, debug: bool = False):
        """
        Initialize a progress reporter.

        Args:
            description: Short description shown at start of progress line
            debug: If True, collect detailed timing data
        """
        self.description = description
        self.debug = debug
        self.start_time = time.time()
        self._steps: list[tuple[str, float]] = []
        self._enabled = progress_enabled()
        self._line_shown = False

    def status(self, message: str) -> None:
        """
        Show/update status message (overwrites previous line on TTY).

        If debug mode is enabled, also records timing data for later report.

        Args:
            message: Current operation status (e.g., "finding base branch")
        """
        elapsed = time.time() - self.start_time

        # Always collect timing data if debug mode
        if self.debug:
            self._steps.append((message, elapsed))

        if not self._enabled:
            return

        # \r = carriage return (start of line)
        # \033[K = ANSI escape: clear from cursor to end of line
        line = f"\r\033[K{self.description}: {message} ({elapsed:.1f}s)"
        try:
            sys.stderr.write(line)
            sys.stderr.flush()
            self._line_shown = True
        except Exception:
            # Never fail on progress output
            pass

    def finish(self, message: str = "done") -> None:
        """
        Complete progress with final message and newline.

        Use this when you want to leave a completion message visible
        after the operation finishes.

        Args:
            message: Final status message (default: "done")
        """
        elapsed = time.time() - self.start_time

        if self.debug:
            self._steps.append((message, elapsed))

        if not self._enabled:
            return

        # Clear line and write final message with newline
        line = f"\r\033[K{self.description}: {message} ({elapsed:.1f}s)\n"
        try:
            sys.stderr.write(line)
            sys.stderr.flush()
            self._line_shown = False  # Line is "finished" with newline
        except Exception:
            pass

    def clear(self) -> None:
        """
        Clear progress line (remove without leaving any message).

        Use this when the operation completed silently or the progress
        was just for debugging slow operations.
        """
        if not self._enabled or not self._line_shown:
            return

        try:
            # \r\033[K clears the current line
            sys.stderr.write("\r\033[K")
            sys.stderr.flush()
            self._line_shown = False
        except Exception:
            pass

    def get_elapsed(self) -> float:
        """
        Get elapsed time since reporter was created.

        Returns:
            Elapsed time in seconds
        """
        return time.time() - self.start_time

    def get_timing_report(self) -> str:
        """
        Return detailed timing breakdown for debugging.

        Only contains data if debug=True was set and status() was called.

        Returns:
            Multi-line string with timing breakdown, or empty string if no data
        """
        if not self._steps:
            return ""

        lines = [f"{self.description} timing:"]
        prev_time = 0.0
        for step, elapsed in self._steps:
            delta = elapsed - prev_time
            lines.append(f"  {step}: +{delta:.3f}s (total: {elapsed:.3f}s)")
            prev_time = elapsed

        return "\n".join(lines)


@contextmanager
def progress_context(
    description: str,
    min_duration: Optional[float] = None,
    debug: bool = False
) -> Generator[ProgressReporter, None, None]:
    """
    Context manager that only shows progress if operation is slow.

    If the operation completes faster than min_duration, no progress
    output is shown at all. This prevents visual noise for fast operations.

    Args:
        description: Short description of the operation
        min_duration: Minimum duration (seconds) before showing completion.
                     If None, uses the configured default (0.3s).
        debug: If True, collect timing data even when not shown

    Yields:
        ProgressReporter instance for calling status() during the operation

    Example:
        with progress_context("Branch analysis", min_duration=0.3) as progress:
            progress.status("finding base branch")
            base = find_base()

            progress.status("calculating changes")
            changes = calculate()

        # If operation took <0.3s, nothing was printed
        # If operation took >=0.3s, completion message is shown
    """
    # Use configured default if min_duration not specified
    threshold = min_duration if min_duration is not None else _default_timing_threshold

    reporter = ProgressReporter(description, debug=debug)
    yield reporter

    elapsed = reporter.get_elapsed()

    if elapsed >= threshold and progress_enabled():
        # Operation was slow enough to warrant showing completion
        reporter.finish()
    else:
        # Fast operation - just clear any progress shown
        reporter.clear()


# Convenience function for simple progress output
def show_progress(description: str, message: str = "") -> None:
    """
    Simple one-shot progress message to stderr.

    For operations where you just want to show a message without
    the full ProgressReporter machinery.

    Args:
        description: Operation description
        message: Optional additional message

    Example:
        show_progress("Checking requirements", "branch_size_limit")
    """
    if not progress_enabled():
        return

    if message:
        line = f"{description}: {message}"
    else:
        line = description

    try:
        sys.stderr.write(f"\r\033[K{line}")
        sys.stderr.flush()
    except Exception:
        pass


def clear_progress() -> None:
    """
    Clear any progress line on stderr.

    Safe to call even if no progress was shown.
    """
    if not progress_enabled():
        return

    try:
        sys.stderr.write("\r\033[K")
        sys.stderr.flush()
    except Exception:
        pass


if __name__ == "__main__":
    # Quick demo
    print("Demo 1: Progress reporter with timing")
    progress = ProgressReporter("Demo operation", debug=True)
    progress.status("step 1")
    time.sleep(0.2)
    progress.status("step 2")
    time.sleep(0.3)
    progress.status("step 3")
    time.sleep(0.1)
    progress.finish("complete")
    print(progress.get_timing_report())

    print("\nDemo 2: Context manager (fast operation - should be silent)")
    with progress_context("Fast operation", min_duration=1.0) as p:
        p.status("working")
        time.sleep(0.1)
    print("(fast operation done)")

    print("\nDemo 3: Context manager (slow operation - should show)")
    with progress_context("Slow operation", min_duration=0.2) as p:
        p.status("step 1")
        time.sleep(0.15)
        p.status("step 2")
        time.sleep(0.15)
    print("(slow operation done)")

    print("\n✅ Demo complete")
