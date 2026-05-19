# Step 19 — Extract dialect plugin (Dutch / .NET auditors)

## Goal

Move the three project-creep auditors (`appsec-auditor`, `tenant-isolation-auditor`, `compliance-auditor`) to a separate optional plugin `requirements-framework-dotnet`. The base plugin becomes truly stack-agnostic.

## Why now (independent of V3 stack)

This is a context-window saver and a quality-of-life improvement orthogonal to V3 features. Could land at any point in the simplification or V3 sequence; placing it here because V3's prompt registry makes the agent extraction mechanical.

## Files touched

- New repo (or new directory): `plugins/requirements-framework-dotnet/`
- Move: `appsec-auditor.md`, `tenant-isolation-auditor.md`, `compliance-auditor.md`
- Update: `plugins/requirements-framework/.claude-plugin/plugin.json` (remove the three agents)
- New: `plugins/requirements-framework-dotnet/.claude-plugin/plugin.json`
- `docs/PLUGIN-INSTALLATION.md` — add the dialect-plugin install steps

## Validated reference

Claude Code's marketplace structure allows multiple plugins per repository or separate repositories. The simplest path is a sibling plugin directory within the same repo, registered separately in the marketplace.

## Implementation

```
plugins/
├── requirements-framework/                  ← base (existing)
│   └── agents/
│       ├── code-reviewer.md
│       ├── tool-validator.md
│       └── ... (22 stack-agnostic agents)
└── requirements-framework-dotnet/           ← new
    ├── .claude-plugin/
    │   └── plugin.json
    └── agents/
        ├── appsec-auditor.md
        ├── tenant-isolation-auditor.md
        └── compliance-auditor.md
```

### Manifest
```jsonc
// plugins/requirements-framework-dotnet/.claude-plugin/plugin.json
{
  "name": "requirements-framework-dotnet",
  "version": "1.0.0",
  "description": "Stack-specific auditors for .NET Core + EF Core + Angular + Azure + Dutch legal-tech compliance.",
  "depends": ["requirements-framework@^3.0"],
  "agents": [
    "agents/appsec-auditor.md",
    "agents/tenant-isolation-auditor.md",
    "agents/compliance-auditor.md"
  ]
}
```

### Update base plugin
Remove the three agent registrations from `plugins/requirements-framework/.claude-plugin/plugin.json`.

### Update `/deep-review` to conditional recruit
```markdown
{# Inside /deep-review.md, at the security team-creation step #}

{% if dotnet_plugin_installed %}
Spawn appsec-auditor, tenant-isolation-auditor, compliance-auditor.
{% else %}
{# Skip security trio if dialect plugin isn't installed #}
{% endif %}
```

(Use a literal check at runtime — Markdown commands can branch on agent availability.)

## Example user experience

User on a Python project: only sees 22 base agents. Initial context overhead drops by ~3 × 250 = ~750 tokens.

User on a .NET Dutch-legal-tech project: installs both plugins. Sees all 25 agents, exactly as today.

## Acceptance

- [ ] Base plugin installs cleanly without the dialect plugin
- [ ] `/deep-review` runs successfully on the base plugin (with 10 review agents instead of 13)
- [ ] Installing the dialect plugin restores the 13-agent team
- [ ] No test in `test_requirements.py` references the dialect agents directly
- [ ] Plugin manifest validates against Claude Code's schema

## Rollback

Move the three agents back into the base plugin. Update both manifests.

## Effort

1 day

## Depends on

Nothing structurally. Can run in parallel with most other V3 steps.

## Honest scope note

If the project later acquires *another* stack-specific need (e.g., Rust/Go-specific auditors), this pattern repeats: `requirements-framework-rust`. The base plugin's contract is "stack-agnostic core" — keep it pure.
