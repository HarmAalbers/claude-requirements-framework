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
