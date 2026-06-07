#!/usr/bin/env python3
"""Mirror the hook runtime from ``hooks/`` into the bundled plugin.

This is the ``.py`` analogue of ``scripts/render_prompts.py``. Just as that
script renders committed ``*.md`` from ``*.md.j2`` sources so a marketplace /
``--plugin-dir`` install needs no build step, THIS script copies the hook
runtime (``hooks/*.py`` + ``hooks/lib/``) into
``plugins/requirements-framework/hooks/`` so the bundled plugin is
self-contained.

The source of truth stays at the repo ``hooks/`` tree; the plugin copies are
build artifacts (like the rendered ``.md`` siblings). The hook scripts
self-locate their dependencies via
``sys.path.insert(0, Path(__file__).parent / 'lib')``, so a sibling ``lib/``
next to the copied entry points makes every hook runnable directly from
``${CLAUDE_PLUGIN_ROOT}/hooks/``.

Run this after editing any hook or lib module. A ``--check`` invocation is the
freshness invariant wired into the test suite — it fails if the bundle has
drifted from source.

SOURCE SET
    * ``hooks/*.py`` EXCEPT ``test_*.py`` — the top-level hook entry points.
    * the entire ``hooks/lib/`` package tree.

EXCLUDED everywhere
    * ``__pycache__/`` directories and ``*.pyc`` files.
    * literal ``~`` files/dirs and ``.DS_Store``.
    * ``hooks/lib/llm/_spikes/`` — throwaway smoke spikes, never shipped.
    * ``hooks/lib/llm/prompts/`` — RUNTIME ``*.md.j2`` templates. They
      reference runtime variables, so they MUST NOT enter the plugin build
      tree, which ``scripts/render_prompts.py`` renders with zero variables
      (see that script's docstring). They contain no Python, so the bundled
      hooks lose nothing.

CLI
    python3 scripts/build_plugin_hooks.py            # build (copy)
    python3 scripts/build_plugin_hooks.py --check    # report drift, no writes

Exit codes
    0  build succeeded, or ``--check`` found the bundle in sync.
    1  ``--check`` found drift (missing / stale-extra / content-differs), or a
       fatal setup error (missing source tree).
"""

import argparse
import shutil
import stat
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_HOOKS = REPO_ROOT / "hooks"
DEST_HOOKS = REPO_ROOT / "plugins" / "requirements-framework" / "hooks"

# hooks.json is plugin-owned: its commands point at ${CLAUDE_PLUGIN_ROOT} and it
# is hand-maintained, not copied. The build mirrors runtime *around* it and must
# never overwrite or delete it.
PLUGIN_OWNED = {"hooks.json"}

# Subtrees of hooks/lib that must never enter the plugin build tree (see the
# module docstring for the rationale behind each).
EXCLUDED_LIB_SUBTREES = ("lib/llm/_spikes", "lib/llm/prompts")


def _is_excluded(path: Path) -> bool:
    """Return True if *path* must never be copied into the bundle."""
    parts = path.parts
    if "__pycache__" in parts or "~" in parts:
        return True
    if path.suffix == ".pyc" or path.name in (".DS_Store", "~"):
        return True
    rel = path.relative_to(SRC_HOOKS).as_posix()
    for sub in EXCLUDED_LIB_SUBTREES:
        if rel == sub or rel.startswith(sub + "/"):
            return True
    return False


def _source_files() -> list[Path]:
    """The runtime files mirrored into the bundle.

    Top-level hook entry points (``hooks/*.py`` minus ``test_*.py``) plus the
    whole ``hooks/lib/`` package tree, with EXCLUDED_LIB_SUBTREES and junk
    filtered out.
    """
    files: list[Path] = []
    for p in sorted(SRC_HOOKS.glob("*.py")):
        if p.name.startswith("test_") or _is_excluded(p):
            continue
        files.append(p)
    for p in sorted((SRC_HOOKS / "lib").rglob("*")):
        if p.is_file() and not _is_excluded(p):
            files.append(p)
    return files


def _dest_for(src: Path) -> Path:
    """Map a source file to its bundle location (relpath preserved)."""
    return DEST_HOOKS / src.relative_to(SRC_HOOKS)


def _is_top_level_hook(src: Path) -> bool:
    """True for ``hooks/<name>.py`` entry points (they have shebangs)."""
    rel = src.relative_to(SRC_HOOKS)
    return rel.parent == Path(".") and src.suffix == ".py"


def _make_executable(path: Path) -> None:
    """Add the execute bit for owner/group/other, preserving read/write bits."""
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _dest_py_files() -> list[Path]:
    """Every ``*.py`` currently in the bundle (for stale detection)."""
    return [p for p in DEST_HOOKS.rglob("*.py") if p.is_file()]


def _dest_pycache_dirs() -> list[Path]:
    """Every ``__pycache__`` directory currently in the bundle."""
    return [p for p in DEST_HOOKS.rglob("__pycache__") if p.is_dir()]


def build() -> int:
    """Copy the source set into the bundle and prune stale copies."""
    sources = _source_files()
    expected = {_dest_for(s) for s in sources}

    copied = 0
    made_exec = 0
    for src in sources:
        dest = _dest_for(src)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)  # byte-for-byte content (mode handled below)
        copied += 1
        if _is_top_level_hook(src):
            _make_executable(dest)
            made_exec += 1

    removed = 0
    # Prune stale *.py copies (source renamed/deleted) — never hooks.json.
    for dest_py in _dest_py_files():
        if dest_py.name in PLUGIN_OWNED:
            continue
        if dest_py not in expected:
            dest_py.unlink()
            removed += 1
    # Prune __pycache__ noise (never part of the source set).
    for cache in _dest_pycache_dirs():
        shutil.rmtree(cache, ignore_errors=True)
        removed += 1

    rel_dest = DEST_HOOKS.relative_to(REPO_ROOT)
    print(f"Built bundle into {rel_dest}/")
    print(f"  copied   : {copied} file(s)")
    print(f"  chmod +x : {made_exec} top-level hook script(s)")
    print(f"  pruned   : {removed} stale .py/__pycache__ entr(y/ies)")
    return 0


def check() -> int:
    """Compare the would-be bundle against disk; exit 1 on any drift."""
    sources = _source_files()
    expected = {_dest_for(s): s for s in sources}

    missing: list[Path] = []
    differing: list[Path] = []
    for dest, src in expected.items():
        if not dest.exists():
            missing.append(dest)
        elif dest.read_bytes() != src.read_bytes():
            differing.append(dest)

    extra: list[Path] = []
    for dest_py in _dest_py_files():
        if dest_py.name in PLUGIN_OWNED:
            continue
        if dest_py not in expected:
            extra.append(dest_py)

    # __pycache__/*.pyc in the bundle is NOT drift: it is gitignored bytecode
    # regenerated at runtime whenever anything imports from the bundle tree
    # (e.g. `req verify` smoke-testing the plugin's check-requirements.py, or the
    # test suite itself). Flagging it caused false CI failures. Source integrity
    # is purely about .py CONTENT (missing / content-differs / stale-extra);
    # `build()` still prunes __pycache__ as housekeeping.
    if not (missing or differing or extra):
        print(f"Bundle in sync: {len(expected)} file(s) match source.")
        return 0

    print("Bundle DRIFT — run `python3 scripts/build_plugin_hooks.py`:")
    for label, items in (
        ("missing", missing),
        ("content-differs", differing),
        ("stale-extra", extra),
    ):
        for item in sorted(items):
            print(f"  [{label}] {item.relative_to(REPO_ROOT)}")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Mirror hooks/ into the bundled plugin (build-copy).",
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="report drift without writing; exit 1 on any drift",
    )
    args = ap.parse_args()

    if not SRC_HOOKS.is_dir():
        sys.stderr.write(f"ERROR: source hooks dir not found: {SRC_HOOKS}\n")
        return 1

    return check() if args.check else build()


if __name__ == "__main__":
    sys.exit(main())
