"""Combined statusline data CLI.

Wraps derive_phase() and count_unsatisfied() in one entry point so the
shell statusline can fetch both values with a single python3 invocation
(Python startup is the dominant cost — two invocations doubles the lag).

derive_phase reads the project's `workflow:` config, which needs PyYAML. Both
statuslines invoke this file with a bare `python3`, so on a machine whose
ambient interpreter lacks PyYAML the config lookup used to fail and fall back
to the PHASE_GATES constants — a project that renamed its phases then showed
the default name with nothing to say why. _bootstrap.ensure() closes that.

The re-exec costs ~22ms per render against a ~35ms baseline (measured, warm uv
cache) and does not fire at all when PyYAML is already importable, which is the
common case. When uv is missing entirely, ensure() returns and the old
fail-open path still applies.

CLI usage:
    python3 statusline_data.py <state-file-path>
prints `<phase> <unsatisfied_count>` on one line. Fail-open on errors.
"""

import sys
from pathlib import Path

import _bootstrap

_bootstrap.ensure()

from count_unsatisfied import count_unsatisfied  # noqa: E402 — must follow ensure()
from derive_phase import DEFAULT_PHASE, derive_phase  # noqa: E402


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
