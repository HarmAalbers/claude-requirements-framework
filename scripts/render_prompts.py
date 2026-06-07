#!/usr/bin/env python3
"""Render *.md.j2 sources to *.md siblings under a directory tree (Steps 16b–16c).

Build-time rendering for plugin files. Source `.md.j2` templates that have
NO runtime variables get rendered to plain `.md` files that Claude Code
reads directly via plugin dispatch.

The plumbing was introduced in Step 16 and fully populated through Step 16c
(25 agents + 11 commands + 21 skills = 57 templates). Running this script
with the default `plugins/requirements-framework/` path discovers all of
them automatically — no per-directory logic needed.

CLI:
    python3 scripts/render_prompts.py [PATH] [--dry-run] [--check]

Args:
    PATH       Directory to walk for *.md.j2 files (default:
               plugins/requirements-framework/). Recursive.
    --dry-run  Print what would be rendered without writing.
    --check    Exit 1 if any rendered .md sibling is stale vs its source
               (suitable for pre-commit hook in Step 16b).

Exit codes:
    0  — all sources processed successfully (or no sources found, or no
         drift in --check mode)
    1  — --check found stale rendered output, OR a source failed to render
         (e.g. references undefined runtime vars — those belong under
         hooks/lib/llm/prompts/, not in the plugin tree)
    2  — jinja2 missing
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

try:
    from hooks.lib.llm.templates import render
except ImportError as exc:
    sys.stderr.write(
        f"ERROR: cannot import hooks.lib.llm.templates: {exc}\n"
        "Install Jinja2 with: pip install -e '.[llm]'\n"
    )
    sys.exit(2)


def _rendered_path(src: Path) -> Path:
    """Strip the trailing .j2 from a .md.j2 path → .md sibling."""
    # Path.with_suffix('') strips only the rightmost suffix, so
    # 'foo.md.j2' becomes 'foo.md' — exactly what we want.
    return src.with_suffix("")


def _render_one(src: Path) -> str:
    """Render one source file. Raises if the template references runtime vars."""
    return render(src.read_text())


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Render *.md.j2 to *.md siblings under a tree."
    )
    ap.add_argument(
        "path", nargs="?",
        default=str(REPO_ROOT / "plugins" / "requirements-framework"),
        help="Directory to walk for *.md.j2 files (default: %(default)s)",
    )
    ap.add_argument("--dry-run", action="store_true",
                    help="Print what would be rendered without writing")
    ap.add_argument("--check", action="store_true",
                    help="Exit 1 if any rendered .md is stale vs its source")
    args = ap.parse_args()

    root = Path(args.path)
    if not root.is_dir():
        sys.stderr.write(f"ERROR: {root} is not a directory\n")
        return 1

    sources = sorted(root.rglob("*.md.j2"))
    if not sources:
        print(f"No .md.j2 sources under {root} — nothing to render.")
        return 0

    print(f"Found {len(sources)} source(s) under {root}")
    render_failures: list[tuple[Path, str]] = []
    stale: list[Path] = []
    rendered: list[Path] = []

    for src in sources:
        target = _rendered_path(src)
        try:
            new_content = _render_one(src)
        except Exception as exc:
            render_failures.append((src, f"{type(exc).__name__}: {exc}"))
            print(f"  ✗ {src.relative_to(root)} — {type(exc).__name__}: {exc}")
            continue

        if args.dry_run:
            print(f"  would render: {src.relative_to(root)} → {target.name}")
            continue

        if args.check:
            current = target.read_text() if target.exists() else None
            if current != new_content:
                stale.append(target)
                print(f"  STALE: {target.relative_to(root)}")
            continue

        target.write_text(new_content)
        rendered.append(target)
        print(f"  ✓ {src.relative_to(root)} → {target.name}")

    print()
    if render_failures:
        print(f"FAIL: {len(render_failures)} source(s) failed to render.")
        print("  These templates likely reference runtime variables.")
        print("  Runtime-rendered templates belong under hooks/lib/llm/prompts/,")
        print("  not in the plugin tree where build-time rendering applies.")
        return 1

    if args.check and stale:
        print(f"FAIL: {len(stale)} rendered .md file(s) are stale.")
        print("  Run `python3 scripts/render_prompts.py` to refresh.")
        return 1

    if args.dry_run:
        print(f"Dry-run: would render {len(sources)} file(s).")
    elif args.check:
        print(f"OK: all {len(sources)} rendered file(s) are fresh.")
    else:
        print(f"Rendered {len(rendered)} file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
