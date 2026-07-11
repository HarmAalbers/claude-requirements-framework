# Domain Modeling — For OO / Domain-Heavy Designs

Start with the golden three, for every new or reshaped object:

1. **What concept am I modeling?** — name the domain idea, not the data shape.
2. **Who owns this behavior?** — behavior lives with the data it needs; anemic bags of fields are a smell.
3. **Which layer owns this object?** — API / application / domain / infrastructure; dependencies point inward.

Work boundaries explicitly: what crosses a layer boundary gets mapped, not leaked. Prefer dedicated collection types with behavior over primitive lists/dicts passed around.

If `~/.claude/guidelines/python-architecture.md` exists on this machine, work through its full design-question checklist for Python projects; otherwise the golden three plus boundary mapping above are the portable core.
