"""Combined statusline data CLI.

Wraps derive_phase() and count_unsatisfied() in one entry point so the
shell statusline can fetch both values with a single python3 invocation
(Python startup is the dominant cost — two invocations doubles the lag).

derive_phase needs the project's `workflow:` config to name the phases, and
both statuslines invoke this file with a bare `python3` that routinely has no
PyYAML. Writers stamp the resolved phase order into the JSON state file
(ADR-025), so the common path reads it with stdlib json and never touches YAML.

Only on a cache miss does this fall back to parsing the cascade, which may cost
a uv re-exec via _bootstrap.ensure() (ADR-024). That keeps the hot path at its
original ~35ms while still answering correctly on a state file nothing has
stamped yet.

CLI usage:
    python3 statusline_data.py <state-file-path>
prints `<phase> <unsatisfied_count>` on one line. Fail-open on errors.
"""

import sys
from pathlib import Path

from count_unsatisfied import count_unsatisfied
from derive_phase import DEFAULT_PHASE, cached_workflow, derive_phase


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(f"{DEFAULT_PHASE} 0")
        return 0
    try:
        p = Path(argv[1])
        if cached_workflow(p) is None:
            # Nothing stamped (fresh clone, or a writer that could not resolve
            # config): fall back to reading the cascade, which needs PyYAML and
            # therefore possibly a uv re-exec. ensure() is a no-op when yaml
            # imports, and returns quietly when uv is nowhere to be found.
            import _bootstrap

            _bootstrap.ensure()
        print(f"{derive_phase(p)} {count_unsatisfied(p)}")
    except Exception:
        # Last-resort fail-open: the statusline must never crash on a malformed
        # state file. Helpers already guard their own paths; this catches
        # anything that slips through (PermissionError, unexpected types, etc.).
        print(f"{DEFAULT_PHASE} 0")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
