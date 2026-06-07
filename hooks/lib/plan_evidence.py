#!/usr/bin/env python3
"""
Plan evidence gating for blocking requirements.

A blocking requirement's satisfied-flag alone no longer unblocks edits when an
``evidence`` config is present: a real plan artifact must ALSO exist on disk.
This turns ``commit_plan`` from a checkbox into a solid plan gate.

The evidence config lives under a requirement and has this shape::

    requirements:
      commit_plan:
        type: blocking
        evidence:
          dirs: ['.claude/plans']            # dirs (relative to project) to scan
          require_markers: ['## Commit Plan'] # ALL must appear in the file
          require_verdict: 'APPROVED'         # optional; must appear in a '## Verdict' section
          max_age_seconds: 86400              # file mtime must be within this

Back-compat: if a requirement has NO ``evidence`` config, verification returns
``(True, "")`` so existing behavior is unchanged.

Fail-safety contract (IMPORTANT):
    This function deliberately does NOT wrap its body in a broad
    ``except: return (True, "")``. Doing so would mask a real "no qualifying
    file" result and defeat the gate. Instead, the CALLER
    (``blocking_strategy``) wraps the call in try/except and fail-opens, so
    genuine crashes (e.g. malformed config) never block work. Internally we only
    treat the EXPECTED non-error conditions gracefully — a non-existent dir is
    simply "no files there", and an unreadable individual file is simply a
    non-qualifying candidate — neither is an error.
"""

import time
from pathlib import Path
from typing import Any


def _as_list(value: Any) -> list:
    """Coerce a scalar/None/list config value into a list of items."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _humanize_age(max_age_seconds: Any) -> str:
    """Render a max-age window as a compact human string (e.g. '24h')."""
    try:
        seconds = float(max_age_seconds)
    except (TypeError, ValueError):
        return str(max_age_seconds)
    if seconds <= 0:
        return f"{max_age_seconds}s"
    if seconds % 3600 == 0:
        return f"{int(seconds // 3600)}h"
    if seconds % 60 == 0:
        return f"{int(seconds // 60)}m"
    return f"{int(seconds)}s"


def _is_h2(stripped_line: str) -> bool:
    """True for a level-2 markdown heading line ('## ...', but not '### ...')."""
    return stripped_line.startswith("## ")


def _verdict_section_contains(text: str, verdict_token: str) -> bool:
    """
    True iff some ``## Verdict`` section contains ``verdict_token`` (case-insensitive).

    The section runs from the ``## Verdict`` heading line (inclusive) until the
    next ``## `` heading or EOF. Because the heading line itself is part of the
    section, an inline heading like ``## Verdict APPROVED`` qualifies too.
    Sub-headings (``### ...``) do NOT close the section — only ``## `` does.
    """
    token = verdict_token.lower()
    lines = text.splitlines()
    n = len(lines)
    i = 0
    while i < n:
        stripped = lines[i].strip()
        if _is_h2(stripped) and stripped[3:].strip().lower().startswith("verdict"):
            section = [lines[i]]
            j = i + 1
            while j < n:
                if _is_h2(lines[j].strip()):
                    break
                section.append(lines[j])
                j += 1
            if token in "\n".join(section).lower():
                return True
            i = j  # keep scanning for additional ## Verdict sections
            continue
        i += 1
    return False


def _file_qualifies(
    path: Path,
    require_markers: list,
    require_verdict: Any,
    max_age_seconds: Any,
    now: float,
) -> bool:
    """
    True iff a single candidate file satisfies the evidence rules.

    Returns False (not raises) for an unreadable/stat-failing file: such a file
    is simply a non-qualifying candidate, which must not abort the whole scan.
    """
    try:
        if max_age_seconds is not None:
            age = now - path.stat().st_mtime
            if age > float(max_age_seconds):
                return False
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False  # unreadable file -> just not a qualifying candidate

    if not all(marker in text for marker in require_markers):
        return False
    if require_verdict and not _verdict_section_contains(text, str(require_verdict)):
        return False
    return True


def _describe_missing(
    dirs: list, require_markers: list, require_verdict: Any, max_age_seconds: Any
) -> str:
    """Build a concise human reason for why no qualifying plan was found."""
    dirs_part = ", ".join(f"{d.rstrip('/')}/" for d in dirs) if dirs else "configured dirs"

    marker_tokens = [f"'{m}'" for m in require_markers]
    if require_verdict:
        marker_tokens.append(f"'## Verdict {require_verdict}'")
    markers_part = f" with {' + '.join(marker_tokens)}" if marker_tokens else ""

    age_part = ""
    if max_age_seconds is not None:
        age_part = f" modified in the last {_humanize_age(max_age_seconds)}"

    return f"no plan in {dirs_part}{markers_part}{age_part}"


def verify_plan_evidence(config, req_name: str, context: dict) -> tuple[bool, str]:
    """
    Verify that a real plan artifact backs a (flag-)satisfied requirement.

    Args:
        config: RequirementsConfig (or any object exposing ``get_attribute``).
        req_name: Requirement name to verify.
        context: Hook context; ``project_dir`` is used to resolve evidence dirs.

    Returns:
        (True, "") if no evidence is required (back-compat) or a qualifying
        plan file exists. (False, <reason>) if evidence is required but no file
        qualifies. Genuine exceptions (e.g. malformed config) are allowed to
        propagate to the caller, which fail-opens.
    """
    ev = config.get_attribute(req_name, "evidence", None)
    if not ev:
        # No evidence config -> don't change behavior (back-compat).
        return (True, "")

    dirs = _as_list(ev.get("dirs")) or [".claude/plans"]
    require_markers = _as_list(ev.get("require_markers"))
    require_verdict = ev.get("require_verdict")
    max_age_seconds = ev.get("max_age_seconds")

    project_dir = context.get("project_dir")
    if not project_dir:
        # Without a project root we cannot resolve evidence dirs -> no plan found.
        return (False, _describe_missing(dirs, require_markers, require_verdict, max_age_seconds))

    project_root = Path(project_dir)
    now = time.time()

    for rel_dir in dirs:
        dir_path = project_root / rel_dir
        # A non-existent dir is just "no files there" (glob yields nothing).
        for candidate in sorted(dir_path.glob("**/*.md")):
            if not candidate.is_file():
                continue
            if _file_qualifies(candidate, require_markers, require_verdict, max_age_seconds, now):
                return (True, "")

    return (False, _describe_missing(dirs, require_markers, require_verdict, max_age_seconds))
