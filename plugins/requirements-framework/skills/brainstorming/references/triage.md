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
