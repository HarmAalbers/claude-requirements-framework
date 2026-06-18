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


def ladder_text(config) -> str:
    """The ladder for injection, or '' when disabled/unavailable.

    Single source of the flag-gate + fail-open used by every injection seam
    (SessionStart, SubagentStart). `config` is a RequirementsConfig.
    """
    try:
        if not config.get_hook_config('lazy_dev', 'enabled'):
            return ""
        return get_ruleset()
    except Exception:
        return ""
