#!/bin/bash
# Pre-commit check (Steps 16b–16c): assert plugin `.md` siblings are fresh
# vs their `.md.j2` sources across agents, commands, and skills. Fails the
# commit if rendering has not been run after editing a template. Wire as
# `.git/hooks/pre-commit` via:
#
#   ln -sf ../../scripts/pre-commit-check.sh .git/hooks/pre-commit
#   chmod +x .git/hooks/pre-commit
#
# Run manually: ./scripts/pre-commit-check.sh

set -e

cd "$(git rev-parse --show-toplevel)"

if [ ! -f "scripts/render_prompts.py" ]; then
    # Tolerate older checkouts that pre-date Step 16; do not block their commits.
    exit 0
fi

# Prefer `uv` so both tools match CI's pinned versions without a global
# `pip install -e '.[llm]'`. render_prompts.py needs jinja2; the default
# python3 here often lacks it, which would otherwise make this gate unusable
# locally. Keep RUFF_VERSION in sync with .github/workflows/ci.yml.
RUFF_VERSION="0.12.12"
HAVE_UV=0
command -v uv >/dev/null 2>&1 && HAVE_UV=1

# --- Plugin template freshness (.md siblings vs .md.j2 sources) ---
if [ "$HAVE_UV" -eq 1 ]; then
    RENDER="uv run --quiet --with jinja2 python3 scripts/render_prompts.py"
elif command -v python3 >/dev/null 2>&1; then
    RENDER="python3 scripts/render_prompts.py"  # needs a global jinja2
else
    echo "WARN: no uv/python3 — skipping plugin template freshness check" >&2
    RENDER=""
fi

if [ -n "$RENDER" ] && ! $RENDER --check; then
    echo "" >&2
    echo "✗ Plugin template render check failed." >&2
    echo "  Run:  ${RENDER}" >&2
    echo "  Then: git add plugins/requirements-framework/" >&2
    echo "        (no -u: stages both re-rendered .md files AND new .md/.j2 pairs)" >&2
    echo "  And re-attempt the commit." >&2
    exit 1
fi

# --- Lint gate (ruff) — mirror CI so a lint error is caught locally, not after
# a push. CI runs `ruff check .`; the local TestRunner does NOT run ruff, so
# tests can pass here yet fail CI. ---
if [ "$HAVE_UV" -eq 1 ]; then
    RUFF="uv run --quiet --with ruff==${RUFF_VERSION} ruff"  # exact CI version
elif command -v ruff >/dev/null 2>&1; then
    RUFF="ruff"  # global ruff may differ from CI's pinned version
else
    echo "WARN: neither uv nor ruff found — skipping ruff lint" >&2
    RUFF=""
fi

if [ -n "$RUFF" ] && ! $RUFF check .; then
    echo "" >&2
    echo "✗ ruff lint failed (CI runs ruff==${RUFF_VERSION} \`ruff check .\`)." >&2
    echo "  Fix:  uv run --with ruff==${RUFF_VERSION} ruff check --fix ." >&2
    echo "  Then re-attempt the commit." >&2
    exit 1
fi
