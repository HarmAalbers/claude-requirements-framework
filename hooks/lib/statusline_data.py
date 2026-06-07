"""Combined statusline data CLI.

Wraps derive_phase() and count_unsatisfied() in one entry point so the
shell statusline can fetch both values with a single python3 invocation
(Python startup is the dominant cost — two invocations doubles the lag).

CLI usage:
    python3 statusline_data.py <state-file-path>
prints `<phase> <unsatisfied_count>` on one line. Fail-open on errors.
"""

import sys
from pathlib import Path

from count_unsatisfied import count_unsatisfied
from derive_phase import DEFAULT_PHASE, derive_phase


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(f"{DEFAULT_PHASE} 0")
        return 0
    try:
        p = Path(argv[1])
        print(f"{derive_phase(p)} {count_unsatisfied(p)}")
    except Exception:
        # Last-resort fail-open: the statusline must never crash on a malformed
        # state file. Helpers already guard their own paths; this catches
        # anything that slips through (PermissionError, unexpected types, etc.).
        print(f"{DEFAULT_PHASE} 0")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
