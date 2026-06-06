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

if ! command -v python3 >/dev/null 2>&1; then
    # python3 absent (e.g., minimal CI image): warn but do not block.
    # Same fail-open policy as the render_prompts.py absence guard above.
    echo "WARN: python3 not found — skipping plugin template freshness check" >&2
    exit 0
fi

if ! python3 scripts/render_prompts.py --check; then
    echo "" >&2
    echo "✗ Plugin template render check failed." >&2
    echo "  Run:  python3 scripts/render_prompts.py" >&2
    echo "  Then: git add plugins/requirements-framework/" >&2
    echo "        (no -u: stages both re-rendered .md files AND new .md/.j2 pairs)" >&2
    echo "  And re-attempt the commit." >&2
    exit 1
fi
