#!/usr/bin/env python3
"""Frontmatter parses for every dispatched plugin prompt.

Claude Code reads the YAML frontmatter of each agent, command and skill to
build its registry. When that block fails to parse it does not error — it logs
a WARN, drops the frontmatter and falls back to a placeholder description, so
agent selection quietly loses everything it steers on. Eighteen agents shipped
that way for months because nothing checked.

The failure mode is always the same: an unquoted scalar containing a colon.
`description: Use this agent when: (1) ...` ends the scalar at the first colon,
and the `user:` lines inside the `<example>` blocks below it are then read as
mapping keys.

This guards both the `.md.j2` sources and their rendered `.md` siblings — the
`.md` is what Claude Code actually dispatches, so checking only the source
would miss a rendering that mangles the block.

Run with: python3 tests/test_frontmatter.py
"""

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_TREE = REPO_ROOT / "plugins" / "requirements-framework"

# Not dispatched prompts: plugin docs and the refactor-orchestration scaffolding
# that the skill reads with Read at runtime. Mirrors the exclusion list in
# tests/test_render_prompts.py::test_all_plugin_md_files_have_j2_source.
EXCLUDED_NAMES = {
    "README.md",
    "ATTRIBUTION.md",
    "orchestrator-prompt-template.md",
    "plan-template.md",
    "retrospective-template.md",
}


class TestRunner:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.failed_tests: list[tuple[str, str]] = []

    def test(self, name: str, condition: bool, msg: str = "") -> None:
        if condition:
            self.passed += 1
            print(f"  ✓ {name}")
        else:
            self.failed += 1
            self.failed_tests.append((name, msg))
            print(f"  ✗ {name}: {msg}")

    def summary(self) -> int:
        total = self.passed + self.failed
        print(f"\n{self.passed}/{total} passed")
        if self.failed:
            print("\nFailures:")
            for name, msg in self.failed_tests:
                print(f"  - {name}: {msg}")
            return 1
        return 0


def check_frontmatter(text: str) -> str:
    """Return "" when the frontmatter is usable, else why it is not.

    Mirrors what Claude Code needs from the block: a leading `---` fence, a
    mapping, and a non-empty `description` to steer selection on.
    """
    if not text.startswith("---\n"):
        return "no leading --- fence"
    end = text.find("\n---", 3)
    if end == -1:
        return "unterminated frontmatter fence"
    try:
        data = yaml.safe_load(text[4 : end + 1])
    except yaml.YAMLError as e:
        problem = getattr(e, "problem", None) or str(e).splitlines()[0]
        mark = getattr(e, "problem_mark", None)
        where = f" at line {mark.line + 1}" if mark else ""
        return f"YAML error{where}: {problem}"
    if not isinstance(data, dict):
        return f"frontmatter is {type(data).__name__}, not a mapping"
    description = data.get("description")
    if not isinstance(description, str) or not description.strip():
        return f"description is {description!r}, want a non-empty string"
    return ""


def dispatched_prompts() -> list[Path]:
    """Every plugin file Claude Code parses frontmatter from, plus its source."""
    found: list[Path] = []
    for sub in ("agents", "commands"):
        for md in sorted((PLUGIN_TREE / sub).glob("*.md")):
            if md.name not in EXCLUDED_NAMES:
                found.append(md)
    found += sorted(PLUGIN_TREE.glob("skills/*/SKILL.md"))
    # The .md.j2 source of each, when it exists — a source that stops parsing
    # would otherwise only surface at the next render.
    found += [j2 for md in list(found) if (j2 := Path(str(md) + ".j2")).exists()]
    return found


# ---------- The guard ----------


def test_every_dispatched_prompt_parses(r: TestRunner) -> None:
    files = dispatched_prompts()
    broken = [
        f"{f.relative_to(PLUGIN_TREE)} ({why})"
        for f in files
        if (why := check_frontmatter(f.read_text()))
    ]
    r.test(
        f"frontmatter parses in all {len(files)} dispatched plugin prompts",
        not broken,
        "; ".join(broken),
    )


def test_the_tree_is_actually_scanned(r: TestRunner) -> None:
    # A path typo would make the check above vacuously pass over an empty list.
    count = len(dispatched_prompts())
    r.test(
        "the scan finds a plausible number of prompts",
        count >= 100,
        f"found only {count} — has the plugin tree moved?",
    )


# ---------- The guard is sensitive to the bug it exists for ----------


def test_unquoted_colon_description_is_rejected(r: TestRunner) -> None:
    # The exact shape that shipped broken for months.
    broken = (
        "---\n"
        "name: demo\n"
        "description: Use this agent when: (1) planning changes\n"
        "\n"
        "Examples:\n"
        "<example>\n"
        'user: "do the thing"\n'
        "</example>\n"
        "---\n\n"
        "# Demo\n"
    )
    r.test(
        "an unquoted description containing a colon is rejected",
        check_frontmatter(broken) != "",
        "the guard accepted the very frontmatter shape it exists to catch",
    )


def test_quoted_equivalent_is_accepted(r: TestRunner) -> None:
    fixed = (
        "---\n"
        "name: demo\n"
        'description: "Use this agent when: (1) planning changes\\n\\n'
        'Examples:\\n<example>\\nuser: \\"do the thing\\"\\n</example>"\n'
        "---\n\n"
        "# Demo\n"
    )
    r.test(
        "the JSON-quoted equivalent is accepted",
        check_frontmatter(fixed) == "",
        check_frontmatter(fixed),
    )


def test_missing_description_is_rejected(r: TestRunner) -> None:
    r.test(
        "frontmatter without a description is rejected",
        check_frontmatter("---\nname: demo\n---\n\n# Demo\n") != "",
        "a description-less agent would list as a placeholder",
    )


def main() -> int:
    print("Running plugin frontmatter tests...")
    r = TestRunner()

    test_every_dispatched_prompt_parses(r)
    test_the_tree_is_actually_scanned(r)
    test_unquoted_colon_description_is_rejected(r)
    test_quoted_equivalent_is_accepted(r)
    test_missing_description_is_rejected(r)

    return r.summary()


if __name__ == "__main__":
    sys.exit(main())
