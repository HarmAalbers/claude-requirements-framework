# Brainstorming Skill v2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use requirements-framework:executing-plans to implement this plan task-by-task.

**Goal:** Rebuild the brainstorming skill as a tiered router + 5 on-demand playbooks, and align the 4 pieces of machinery that currently contradict it.

**Architecture:** One catalog entry (`skills/brainstorming/`) whose short SKILL.md routes by tier (small/standard/deep); phase/concern/depth content lives in `references/*.md` loaded on demand. Four bounded machinery fixes: mode-agnostic nudge directive, delete the `/brainstorm` command shim (slug unified on `/brainstorming`), conditional private-path pointer, ponytail attribution. Design doc: `.claude/plans/2026-07-11-brainstorming-skill-v2-design.md`.

**Tech Stack:** Markdown skill prose + Jinja2 (`.md.j2` → `.md` via `scripts/render_prompts.py`, `rglob("*.md.j2")` — references/ subdirs are picked up automatically), Python hooks (`hooks/lib/brainstorm.py`), custom TestRunner suite (`hooks/test_requirements.py`), Stacked Git.

**House rules (every task):**
- NEVER `git commit` — always `stg new` (start patch) + `stg refresh` (fold changes in).
- `stg refresh` does NOT pick up untracked files — `git add <new files>` first.
- All Python via `uv run`. Green local suite = **1483/1488** (5 known local-only failures; zero NEW failures allowed).
- Branch: `feat/brainstorming-v2` (exists, stg initialized, carries the `design-doc` patch).

---

## Task 0: Preflight

**Step 1: Verify branch + baseline**

Run: `git branch --show-current && stg series && git status --short`
Expected: `feat/brainstorming-v2`, series shows `> design-doc`, no unexpected modifications (untracked `.claude/plans/2026-07-06-uv-standardization.md` is pre-existing — leave it).

**Step 2: Baseline test run**

Run: `uv run python hooks/test_requirements.py 2>&1 | tail -5`
Expected: 1483/1488 passed (the 5 config-validation failures are local-only). Record the number — later tasks must not go below it.

---

## Task 1: Rewrite skill as router + playbooks (patch `skill-v2-router`)

**Files:**
- Rewrite: `plugins/requirements-framework/skills/brainstorming/SKILL.md.j2`
- Create: `plugins/requirements-framework/skills/brainstorming/references/triage.md`
- Create: `plugins/requirements-framework/skills/brainstorming/references/interview.md`
- Create: `plugins/requirements-framework/skills/brainstorming/references/approaches.md.j2`
- Create: `plugins/requirements-framework/skills/brainstorming/references/design-writeup.md`
- Create: `plugins/requirements-framework/skills/brainstorming/references/domain-modeling.md`
- Modify: `plugins/requirements-framework/.claude-plugin/plugin.json` (version `5.0.2` → `5.1.0`)
- Generated: `SKILL.md` + `references/approaches.md` (via render)

**Step 1: Start the patch**

```bash
stg new skill-v2-router -m "feat(brainstorming): v2 tiered router + on-demand playbooks

Replaces the monolithic 6-step skill (4x-duplicated flow, mandatory full
ceremony for every task) with a triage router (small/standard/deep tiers)
plus five references/ playbooks. Mode-agnostic artifact rules. Absorbs the
vagueness-gate intent in prose. Bumps plugin to 5.1.0."
```

**Step 2: Replace `SKILL.md.j2` with the router**

Keep the frontmatter `name`/`description`/`git_hash` lines EXACTLY as they are today (description is CSO-conformant; git_hash is CI-managed). Body becomes:

````markdown
# Brainstorming Ideas Into Designs

Turn an idea into a design the user has approved — with ceremony that matches the stakes.

<HARD-GATE>
Do NOT write code, scaffold a project, or take any implementation action until the user has approved a design. Every task gets a design; only its SIZE varies with the tier.
</HARD-GATE>

## Step 0 — Triage (always, first)

Read `references/triage.md`. Run its vagueness check, classify the task into a tier, and announce the tier in one line ("Treating this as standard tier — feature-sized, one subsystem").

| Tier | Fits when | Interview | Artifact | Terminal |
|------|-----------|-----------|----------|----------|
| **small** | Localized, reversible, few files | 1–2 questions max | A few sentences, inline in conversation | User OK → proceed directly |
| **standard** | Feature-sized | Full flow | Design doc, committed | Invoke writing-plans |
| **deep** | Multi-subsystem / architectural | Full flow + decomposition check | Design doc, committed; user reviews the file | Invoke writing-plans (per sub-design) |

Mis-tiering is recoverable: if the problem grows mid-flow, re-triage upward, announce it, and continue. Never silently stay in a too-small tier.

## The Flow

Work through these in order, loading each playbook when you reach it:

1. **Triage** — vagueness check + tier (`references/triage.md`)
2. **Anchor peek** — read just enough code to sketch credible approaches; not an exploration spree. Deeper reads happen later, on demand.
3. **Approaches early** — 2–3 candidates with a recommendation (`references/approaches.md`)
4. **Interview, write-as-you-go** — one question per message; settled answers land in the artifact immediately (`references/interview.md`, `references/design-writeup.md`)
5. **Self-review** — inline checklist, fix inline (`references/design-writeup.md`)
6. **Approval** — small: inline OK; standard: per-section; deep: user also reviews the written file
7. **Terminal** — small: proceed directly; standard/deep: invoke `requirements-framework:writing-plans`, telling it the tier

For object-oriented / domain-heavy designs, also work through `references/domain-modeling.md`.

## Invariants (every tier)

- **One question per message** — multiple choice preferred; never a question wall.
- **Approaches before deep interviewing** — questions come from trade-off deltas, not a generic checklist.
- **Write-as-you-go** — a settled answer lands in the artifact immediately (standard/deep) or the running summary (small).
- **No implementation before approval** — the HARD-GATE above.
- **YAGNI ruthlessly** — strike speculative features from every design.
- **Artifact rules are keyed on tier only — never on editor mode.** If file writes are unavailable right now, present the design and write the doc at the first opportunity.

## Edge Rules

- User rejects a section → revise that section only; don't restart the flow.
- Request turns out to be multiple independent subsystems → decompose (`references/approaches.md`), sequence sub-designs with the user.
- User answers "you decide" twice in a row → stop interviewing; present the recommended design and ask for one approval.

## Requirements Integration

Completing this skill satisfies the `design_approved` gate of the workflow's design phase (the framework nudges rather than blocks under the default `enforcement: nudge`). After standard/deep approval, `requirements-framework:writing-plans` is the ONLY skill to invoke next.
````

Note: the `{% include 'RULESET.md' %}`, the dot graph, "Anti-Pattern", "The Process", "After the Design", "Plan Mode Behavior", and "Key Principles" sections are all deliberately GONE from the router (ladder moves to approaches.md.j2; plan-mode section is deleted per the mode-agnostic decision).

**Step 3: Create `references/triage.md`**

````markdown
# Triage — Vagueness Check and Tier

## Vagueness check (before reading the repo)

State, in one sentence each: the **goal**, the **constraints**, the **success criterion**. If any of the three can't be stated yet, ask the user before exploring the codebase — reading dozens of files to guess is anchoring, not research. One or two targeted questions usually unblock all three.

## Tier heuristics

Score the task on four axes; the highest axis wins. When in doubt, round up one tier.

- **Stakes** — what breaks if the design is wrong? (annoyance → small; data loss, broken contracts → deep)
- **Blast radius** — how many files/modules/consumers does it touch?
- **Reversibility** — trivially revertible, or does it migrate state/contracts?
- **Novelty** — pattern already exists in the repo (small) vs new architecture (deep)

| Signal | Tier |
|---|---|
| One file, existing pattern, reversible | small |
| New feature, several files, one subsystem | standard |
| Cross-subsystem, new architecture, migrations, public contracts | deep |

## Announce and route

Announce the tier and why in ONE line, then follow the tier's row in the router table. Re-tiering upward mid-flow is normal — announce it the same way.
````

**Step 4: Create `references/interview.md`**

````markdown
# Interview — Question Craft

## Anchor questions in approaches

Ask questions the approach comparison actually raises: "A and B diverge on X — which constraint wins?" beats "what are your requirements?". If a question wouldn't change which approach or design decision you pick, don't ask it.

## Mechanics

- One question per message. Break compound topics into a sequence.
- Multiple choice preferred, with your recommended option marked; open-ended when choices would bias the answer.
- Every settled answer lands in the artifact immediately (see `design-writeup.md`).
- Explore code between questions only when the next question needs grounding.

## Concern modes

Match the question style to the concern:
- **Product / requirements** — purpose, users, success criteria, non-goals.
- **Technical** — constraints, integration points, performance/compat budgets, failure modes.
- **Domain modeling** — switch to `domain-modeling.md` when the design shapes domain objects.

## Stop conditions

Stop interviewing when: answers repeat what you already know · remaining unknowns wouldn't change the design · the user answers "you decide" twice in a row (present the recommended design, ask for one approval) · the small tier's 1–2 question budget is spent.
````

**Step 5: Create `references/approaches.md.j2`**

````markdown
# Approaches — Sketch Early, Compare Honestly

Sketch 2–3 credible approaches BEFORE the deep interview — the comparison generates the questions worth asking. Lead with your recommendation and why. Small tier: one recommended approach is enough; name the rejected alternative in a line.

Design for the least code that works — let this ladder shape every approach you propose:

{% include 'RULESET.md' %}

## Scope check — decompose before refining

If the request describes multiple independent subsystems, flag it immediately — don't spend questions refining details of a project that needs decomposition first. Split into sub-projects; each gets its own design → plan cycle, sequenced with the user.

## Design for isolation

Prefer units with one clear purpose behind well-defined interfaces. Test: can you change the internals without breaking consumers? If not, the boundaries need work. Smaller, isolated units are easier to reason about — for you and for the next reader.

## Existing codebases

Follow the repo's existing patterns; targeted improvements that serve the task are welcome, unrelated refactoring is not. When an existing pattern and a better pattern conflict, surface the trade-off in the approaches instead of silently picking.
````

**Step 6: Create `references/design-writeup.md`**

````markdown
# Design Write-up — As You Go, Then Self-Review

## Write-as-you-go

Open the artifact at the FIRST settled decision, not after the interview. Each settled answer lands immediately:

- **small** — a running summary in conversation; final form is a few sentences.
- **standard / deep** — a design doc in the project's plan directory (`docs/plans/YYYY-MM-DD-<topic>-design.md` or `.claude/plans/`), committed when complete.

Artifact rules are keyed on tier only — never on editor mode. If file writes are unavailable at that moment, keep the design in conversation and write the doc at the first opportunity.

## Structure (standard/deep)

Sections scaled to complexity — a few sentences when straightforward, up to 200–300 words when nuanced. Cover: problem, decisions (with the user's answers), architecture, components, data flow, error handling, testing. Record rejected approaches in one line each — future readers need the why-nots.

## Self-review (before approval)

Run this checklist inline; fix issues inline, no re-review loop:

1. **Placeholder scan** — any TBD/TODO/???
2. **Internal consistency** — do sections contradict each other?
3. **Scope check** — does anything exceed what the user asked for? (YAGNI)
4. **Ambiguity check** — could any requirement be read two ways? Pick one reading, make it explicit.

## Approval

- **small** — present the summary; get an explicit user OK.
- **standard** — approval per section as they're presented.
- **deep** — after section approvals, ask the user to review the committed design FILE before invoking writing-plans: "Design written to `<path>`. Please review it before we plan the implementation."
````

**Step 7: Create `references/domain-modeling.md`**

````markdown
# Domain Modeling — For OO / Domain-Heavy Designs

Start with the golden three, for every new or reshaped object:

1. **What concept am I modeling?** — name the domain idea, not the data shape.
2. **Who owns this behavior?** — behavior lives with the data it needs; anemic bags of fields are a smell.
3. **Which layer owns this object?** — API / application / domain / infrastructure; dependencies point inward.

Work boundaries explicitly: what crosses a layer boundary gets mapped, not leaked. Prefer dedicated collection types with behavior over primitive lists/dicts passed around.

If `~/.claude/guidelines/python-architecture.md` exists on this machine, work through its full design-question checklist for Python projects; otherwise the golden three plus boundary mapping above are the portable core.
````

**Step 8: Bump plugin version**

In `plugins/requirements-framework/.claude-plugin/plugin.json` line 3: `"version": "5.0.2",` → `"version": "5.1.0",`

**Step 9: Render + verify**

```bash
uv run python scripts/render_prompts.py
uv run python scripts/render_prompts.py --check
```
Expected: renders `SKILL.md` and `references/approaches.md`; check reports all fresh (source count rises from 61 to 62). Read the rendered `SKILL.md` once to confirm no stray Jinja and the RULESET landed in `references/approaches.md` only.

**Step 10: Run the suite**

Run: `uv run python hooks/test_requirements.py 2>&1 | tail -5`
Expected: same pass count as baseline (no test pins brainstorming SKILL body content; auto-satisfy tests key on the skill NAME, which is unchanged).

**Step 11: Commit**

```bash
git add plugins/requirements-framework/skills/brainstorming/ plugins/requirements-framework/.claude-plugin/plugin.json
stg refresh
git show --stat HEAD   # verify: SKILL.md.j2 + SKILL.md + 6 references files + plugin.json
```

---

## Task 2: Mode-agnostic nudge directive (patch `directive-mode-agnostic`)

**Files:**
- Test: `hooks/test_requirements.py` (extend the existing `brainstorm_directive` pin block at ~line 10828)
- Modify: `hooks/lib/brainstorm.py:34-51` (`brainstorm_directive`)
- Generated: `plugins/requirements-framework/hooks/lib/brainstorm.py` (bundle rebuild)

**Step 1: Start the patch**

```bash
stg new directive-mode-agnostic -m "fix(nudge): brainstorm directive is mode-agnostic

The directive fired on UserPromptSubmit in every mode but instructed
'write into the plan file / do NOT create a design document or commit' —
contradicting the skill's own artifact rules outside plan mode. Artifact
rules now live solely in the skill; the directive stops mentioning modes,
plan files, and git."
```

**Step 2: Write the failing tests**

In `hooks/test_requirements.py`, directly after the existing skill-agnostic pin (the `custom = brainstorm_directive(...)` block ending ~line 10834), add:

```python
    # v5.1.0: the directive is mode-agnostic — artifact rules live in the skill.
    for banned in ("plan mode", "plan file", "Do NOT create"):
        runner.test(f"brainstorm_directive has no mode-specific phrasing: {banned!r}",
                   banned not in directive, f"Got: {directive}")
    runner.test("brainstorm_directive mentions tier triage",
               "triage" in directive.lower(), f"Got: {directive}")
```

**Step 3: Run tests to verify they fail**

Run: `uv run python hooks/test_requirements.py 2>&1 | grep -A1 "mode-specific\|tier triage"`
Expected: FAIL on all three banned-phrase pins and the triage pin (current directive contains all banned phrases, no "triage").

**Step 4: Rewrite the directive body**

In `hooks/lib/brainstorm.py`, replace the return of `brainstorm_directive` (keep the `## Brainstorm Before Planning` heading — ~12 downstream hook-output assertions pin it; keep `command` interpolation):

```python
    command = '/' + skill.split(':')[-1]
    return f"""\
## Brainstorm Before Planning

Before implementing (or writing an implementation plan), invoke the brainstorming skill to design the approach first.

**Action**: Invoke `{command}` now.

The skill starts with a triage step so the design ceremony matches the task's size, then asks clarifying questions, proposes approaches, and gets the design approved. Follow its artifact rules for what to capture where."""
```

Also update the docstring's last sentence to: `Mode-agnostic: artifact rules live in the skill, so the directive never mentions plan files, design documents, or git.`

**Step 5: Run tests to verify they pass**

Run: `uv run python hooks/test_requirements.py 2>&1 | tail -5`
Expected: baseline count + 4 new passes, zero new failures (heading/slug pins at 10627/10650/10753/10829/10897+ all still match).

**Step 6: Rebuild the bundle + commit**

```bash
uv run python scripts/build_plugin_hooks.py
git diff --stat   # expect: hooks/lib/brainstorm.py + bundle copy + test file
git add -A hooks/ plugins/requirements-framework/hooks/
stg refresh
```

---

## Task 3: Delete `/brainstorm` command, unify slug (patch `drop-brainstorm-command`)

**Files:**
- Delete: `plugins/requirements-framework/commands/brainstorm.md` + `brainstorm.md.j2`
- Test: `hooks/test_requirements.py` (`test_plugin_command_files_exist`, ~line 10549)
- Modify (slug `/brainstorm` → `/brainstorming`): `plugins/requirements-framework/README.md:69,97` · `skills/requirements-framework-usage/SKILL.md.j2:273` · `skills/workflow-index/SKILL.md.j2:27,39` · `skills/using-requirements-framework/references/skill-catalog.md:27` · `examples/global-requirements.yaml:267`
- Modify (command count 16 → 15): `README.md:14,297` · `CLAUDE.md:101` · `DEVELOPMENT.md:287,325` · `plugins/requirements-framework/README.md:18` · `docs/PLUGIN-INSTALLATION.md:33`

**Step 1: Start the patch**

```bash
stg new drop-brainstorm-command -m "feat!: remove /brainstorm command shim, unify on /brainstorming

The command was a 3-line delegation wrapper nothing programmatic
referenced; nudges emit /brainstorming while YAML messages and docs said
/brainstorm — two slugs for one action. No compat shim per house rules."
```

**Step 2: Update the test first (TDD for the absence)**

In `test_plugin_command_files_exist` (~line 10557): remove `'brainstorm.md'` from `new_commands`, and after the `/quality-check` absence block add (mirroring the established pattern):

```python
    # Absence test: /brainstorm command shim removed in plugin v5.1.0
    brainstorm_cmd_path = commands_dir / 'brainstorm.md'
    runner.test("Command shim /brainstorm removed in 5.1.0",
               not brainstorm_cmd_path.exists(),
               f"File should be deleted: {brainstorm_cmd_path}")
```

Run: `uv run python hooks/test_requirements.py 2>&1 | grep "removed in 5.1.0"`
Expected: FAIL (file still exists).

**Step 3: Delete the command + fix slugs and counts**

```bash
git rm plugins/requirements-framework/commands/brainstorm.md plugins/requirements-framework/commands/brainstorm.md.j2
```

Then apply the slug and count edits listed under **Files** (edit `.j2` sources where one exists, never the rendered `.md` alone). In `examples/global-requirements.yaml:267` the message line becomes ``**Execute**: `/brainstorming` ``. In `plugins/requirements-framework/README.md:69` the design row becomes `` `/brainstorming` (skill)``; line 97's command-table row is deleted outright (it lists commands; /brainstorm no longer is one).

**Step 4: Re-render + sweep for stragglers**

```bash
uv run python scripts/render_prompts.py
grep -rn "/brainstorm\b" --include="*.md" --include="*.j2" --include="*.yaml" plugins/ docs/ examples/ README.md CLAUDE.md DEVELOPMENT.md | grep -v "/brainstorming" | grep -v "\.claude/plans"
```
Expected: zero hits (any hit = a missed reference; fix it). Note the root README and PLUGIN-INSTALLATION may hold `/brainstorm` spellings the earlier sweep flagged — the grep is the authority.

**Step 5: Run tests to verify they pass**

Run: `uv run python hooks/test_requirements.py 2>&1 | tail -5`
Expected: baseline + new absence pass, zero new failures.

**Step 6: Commit**

```bash
git add -A
stg refresh
```

---

## Task 4: Adjacent doc-rot chore (patch `docs-rot-chore`)

Pre-existing wrong docs found during the design sweep — separate patch, no behavior change.

**Files:**
- Modify: `plugins/requirements-framework/commands/req.md.j2` (and rendered `req.md`): line 3 phase list `design, plan-write, plan-validate, implement, review, refactor, ship` → `design, plan, validate, build, review, verify, ship`; in the fallback table (~lines 49–58) rename rows to the ADR-022 names and ADD the missing verify row (`verify | verified | requirements-framework:verification-before-completion`).
- Modify: `plugins/requirements-framework/scripts/req-phase:14-15`: same stale phase list in the comment.
- Modify: `skills/using-requirements-framework/references/skill-catalog.md:48-49`: `writing-plans → satisfies plan_written and commit_plan` → `writing-plans → satisfies plan_written`; delete the `test-driven-development → satisfies tdd_planned` line (gate retired).
- Modify: `docs/PLUGIN-INSTALLATION.md:309`: `/pre-commit` satisfies `pre_commit_review` (not `implementation_done`).

**Step 1: Start patch, edit, verify**

```bash
stg new docs-rot-chore -m "docs: fix stale phase names, retired gates, wrong /pre-commit gate

req.md + req-phase still described the pre-ADR-022 phase vocabulary and
omitted the verify phase; skill-catalog documented retired gates
(commit_plan, tdd_planned); PLUGIN-INSTALLATION assigned /pre-commit the
wrong gate."
```

Cross-check every edited gate/phase name against `WORKFLOW_DEFAULTS` in `hooks/lib/config.py:911-973` — that dict is the single source of truth.

**Step 2: Re-render, test, commit**

```bash
uv run python scripts/render_prompts.py && uv run python scripts/render_prompts.py --check
uv run python hooks/test_requirements.py 2>&1 | tail -3
git add -A
stg refresh
```

---

## Task 5: Final verification

**Step 1: Full gate**

```bash
uv run python hooks/test_requirements.py 2>&1 | tail -5   # 1483/1488 local (zero NEW failures)
uv run ruff check .                                        # clean — CI runs this, local suite does not
uv run python scripts/render_prompts.py --check            # all fresh
uv run python scripts/build_plugin_hooks.py && git status --short   # no drift after rebuild
stg series                                                 # design-doc, plan-doc, skill-v2-router, directive-mode-agnostic, drop-brainstorm-command, docs-rot-chore
```

**Step 2: Live smoke (user-run)**

Fresh session in the repo with the dev build (`claude --plugin-dir plugins/requirements-framework`), then a substantive prompt: confirm the nudge shows the new directive text (no "plan file"/"plan mode"), `/brainstorming` triages and announces a tier, and small-tier flow ends at inline approval without a doc. Claude must NOT launch this itself — hand to the user via `!`.

**Step 3: Ship decision**

Hand back to the user: review the series, then merge/push per `finishing-a-development-branch`. Watch-out: CI auto-publish pushes a git_hash auto-bump back after any push to master — fetch+rebase before a second push.
