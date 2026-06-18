from pathlib import Path

_RULESET = Path(__file__).parent / "RULESET.md"
COMPACT_REMINDER = ("Lazy-dev: prefer the least code that works — stdlib/native/"
                    "installed-dep/one-line before custom; never skimp on validation, "
                    "security, error handling, or accessibility.")


def get_ruleset() -> str:
    """Full lazy-dev ladder text. Fail-open to '' if the file is missing."""
    try:
        return _RULESET.read_text(encoding="utf-8")
    except Exception:
        return ""
