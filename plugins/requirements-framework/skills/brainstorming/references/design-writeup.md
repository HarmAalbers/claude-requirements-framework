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
