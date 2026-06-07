#!/usr/bin/env python3
"""Mirror bundled prompt .md.j2 files into Langfuse Prompt Management.

Step 12 (publisher) + Step 16 (Jinja2 source format). Reads
`hooks/lib/llm/prompts/*.md.j2` and upserts each one as a text-typed
Langfuse prompt with the `production` label. After this runs, the
PromptLoader at `hooks.lib.llm.prompts.load_prompt` fetches from Langfuse
on its next cache-miss instead of falling back to the file.

Templates are stored in Langfuse as **opaque Jinja2 text**, per the
[Langfuse FAQ on external templating libraries][faq] (the
maintainer-blessed pattern for prompts that need loops/conditionals/
includes — Langfuse's native `compile()` is mustache-only). Rendering
happens client-side in `templates.render()`.

Known Langfuse UI limitations on Jinja2-stored prompts (see the FAQ):
  - Playground can't auto-render templates with `{% %}` blocks.
  - In-UI prompt experiments require SDK-side compile (which we do).
  - Variable hints only detect top-level alphanumeric `{{ var }}` —
    `{% for hit in retrieved %}` won't surface `retrieved` in the UI's
    variable list.

These are accepted trade-offs. The TTL caching + version-label rollback
story Step 12 built remains intact (Langfuse caches the raw text; our
loader bypasses Langfuse's `compile()`).

Why the client-side compare: `langfuse.create_prompt` is NOT idempotent —
the server happily mints a new version for byte-identical content
(verified empirically 2026-06-07: a re-sync created identical v2s for all
11 unchanged prompts; an earlier docstring claimed server-side dedup and
was wrong). So before creating, this script fetches the current labeled
version and skips files whose content already matches. Changed/missing
content creates a new version and moves the label. Clean "edit file → run
sync → next workers see new version" loop, without version-history noise.

`--check` runs the same comparison without writing and exits 1 on any
drift (loud, pre-commit/CI-suitable): a stale registry silently serves old
prompts at runtime because the loader prefers Langfuse over the bundled
files — drift must fail loudly, not fail open.

Why we use `prompt.prompt` (raw) instead of `get_langfuse_prompt()`:
  - `get_langfuse_prompt()` was the subject of [Issue #1912][issue1912]
    (closed 2024-05-14), which over-eagerly transformed `{{ }}` blocks it
    interpreted as Langfuse variables, mangling Jinja2 expressions with
    function calls or quoting. The fix uses a heuristic
    (alphanumeric-only contents = Langfuse var; anything else = leave
    alone), which means simple Jinja2 variables like `{{ scope }}` could
    still collide. Our raw `.prompt` path bypasses the transformation
    entirely. Anyone reaching for `get_langfuse_prompt` in a future patch
    needs to know.

Why Langfuse doesn't ship Jinja2 server-side: per
[Discussion #4315][disc4315] — server-side rendering would defeat
client-side caching, requiring a Langfuse round-trip on every LLM
invocation. Maintainer position: client-side rendering is the right
seam for control flow.

[faq]: https://langfuse.com/faq/all/using-external-templating-libraries
[issue1912]: https://github.com/langfuse/langfuse/issues/1912
[disc4315]: https://github.com/orgs/langfuse/discussions/4315

Usage:
    # Prereqs (same as the Step 11 smoke):
    cd infra && docker compose up -d
    export LANGFUSE_PUBLIC_KEY=pk-...
    export LANGFUSE_SECRET_KEY=sk-...
    export LANGFUSE_HOST=http://localhost:3000

    python3 scripts/sync_prompts_to_langfuse.py            # publish
    python3 scripts/sync_prompts_to_langfuse.py --dry-run  # list, don't push
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = REPO_ROOT / "hooks" / "lib" / "llm" / "prompts"
SOURCE_EXT = ".md.j2"


def _prompt_name(path: Path) -> str:
    """Strip the `.md.j2` extension to get the Langfuse prompt name.

    `Path.stem` only strips the rightmost suffix, so
    `Path('code-reviewer.md.j2').stem == 'code-reviewer.md'` — wrong.
    We need both suffixes off to register the prompt as `code-reviewer`.
    """
    name = path.name
    if name.endswith(SOURCE_EXT):
        return name[: -len(SOURCE_EXT)]
    return path.stem


def _load_dotenv() -> None:
    """Load `infra/.env` (then repo `.env`) so this script picks up LANGFUSE_*
    without the caller exporting them — same loader as `review_cli` and the
    Langfuse smoke, for one consistent cred source. Shell env wins. Soft-dep on
    python-dotenv; absent → shell env only and `_require_env` reports what's missing.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for candidate in (REPO_ROOT / "infra" / ".env", REPO_ROOT / ".env"):
        if candidate.is_file():
            load_dotenv(candidate, override=False)


def _require_env() -> None:
    missing = [
        k for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST")
        if not os.getenv(k)
    ]
    if missing:
        sys.stderr.write(
            "ERROR: Langfuse env vars not set: "
            + ", ".join(missing)
            + "\nSee scripts/sync_prompts_to_langfuse.py docstring for setup.\n"
        )
        sys.exit(2)


def _discover_prompts() -> list[Path]:
    if not PROMPTS_DIR.is_dir():
        sys.stderr.write(f"ERROR: prompts dir not found: {PROMPTS_DIR}\n")
        sys.exit(2)
    # Top-level only — partials/ subdirectory holds `{% include %}` targets
    # that don't have their own Langfuse prompt entries.
    files = sorted(PROMPTS_DIR.glob(f"*{SOURCE_EXT}"))
    if not files:
        sys.stderr.write(f"ERROR: no {SOURCE_EXT} files in {PROMPTS_DIR}\n")
        sys.exit(2)
    return files


def _registry_content(lf, name: str, label: str) -> str | None:
    """Current prompt text under `label`, or None if absent.

    Any exception from `get_prompt` is treated as "not in registry" —
    for a missing prompt the SDK raises, and creating is the correct
    response either way. Genuine connectivity failures will surface
    loudly on the subsequent `create_prompt` call instead.
    """
    try:
        return lf.get_prompt(name, label=label).prompt
    except Exception:
        return None


def sync_prompts(files: list[Path], lf, *, label: str, check: bool) -> list[str]:
    """Compare each file against the registry; create or report drift.

    Returns the names that changed (sync mode: created; check mode:
    would be created). Identical content is skipped — Langfuse does NOT
    dedup server-side (see module docstring), so the compare lives here.
    """
    changed: list[str] = []
    for p in files:
        content = p.read_text()
        name = _prompt_name(p)
        current = _registry_content(lf, name, label)
        if current == content:
            print(f"unchanged: {name}")
            continue
        changed.append(name)
        if check:
            state = "MISSING from registry" if current is None else "DRIFTED"
            print(f"drift: {name}  ({state}, label {label!r})")
            continue
        result = lf.create_prompt(
            name=name,
            type="text",
            prompt=content,
            labels=[label],
        )
        version = getattr(result, "version", "?")
        print(f"synced: {name}  -> version {version}, label {label!r}")
    return changed


def main() -> int:
    description = (__doc__ or "Mirror prompts to Langfuse.").split("\n\n")[0]
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="list what would be synced; don't talk to Langfuse",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="compare only; exit 1 if any prompt drifted from the registry",
    )
    parser.add_argument(
        "--label", default="production",
        help="label to attach (default: production)",
    )
    args = parser.parse_args()

    files = _discover_prompts()

    if args.dry_run:
        print(f"Would sync {len(files)} prompt(s) to Langfuse with label={args.label!r}:")
        for p in files:
            print(f"  {_prompt_name(p)}  ({p.stat().st_size} bytes, source: {p.name})")
        return 0

    _load_dotenv()
    _require_env()
    from langfuse import Langfuse
    lf = Langfuse()

    changed = sync_prompts(files, lf, label=args.label, check=args.check)
    lf.flush()

    if args.check:
        if changed:
            sys.stderr.write(
                f"ERROR: {len(changed)} prompt(s) drifted from the registry; "
                "run scripts/sync_prompts_to_langfuse.py to publish.\n"
            )
            return 1
        print("registry in sync")
    return 0


if __name__ == "__main__":
    sys.exit(main())
