---
name: req-pause
description: "Pause the framework's blocking gates for this session only (auto-resumes at session end)"
argument-hint: "[reason]"
allowed-tools: ["Bash"]
git_hash: c9a318c
---

> **Workflow position**: escape-hatch (session-scoped). Suppresses the framework's BLOCKING gates (the PreToolUse edit/commit gate and the end-of-turn Stop verification) for the CURRENT session only. Does NOT bypass strict-preflight — use `RF_STRICT_OFF=true` for that. Nudges and status injection keep firing (you will see a `⏸ paused` banner). Auto-resumes when the session ends.

# Pause the Requirements Framework (this session)

Write the session-scoped pause marker via the CLI primitive:

```bash
req pause ${ARGUMENTS:+--reason "$ARGUMENTS"}
```

If `req` is not on PATH, fall back to `python3 hooks/requirements-cli.py pause ${ARGUMENTS:+--reason "$ARGUMENTS"}`.

Then confirm to the user:

- Blocking gates are OFF for this session: edits/commits will not be gated, and the end-of-turn Stop check will not block.
- A `⏸ Framework paused for this session` banner will appear each turn so the paused state is never silently forgotten.
- Strict-preflight is NOT affected (if strict mode blocks this project, use `RF_STRICT_OFF=true`).
- To re-enable: run `/req-resume`, or simply end the session (the marker auto-clears at SessionEnd).
