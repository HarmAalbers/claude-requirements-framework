# ADR-005: Per-Project Init Command

## Status
Accepted

## Date
2024-12-24

## Context

The requirements framework requires per-project configuration to enable requirements. Previously, users had to manually create `.claude/requirements.yaml` by:
1. Finding an example config file
2. Understanding YAML syntax
3. Understanding requirement structure (enabled, scope, trigger_tools, message, checklist)
4. Manually typing/copying the configuration

This created barriers to adoption:
1. **Error-prone**: YAML syntax errors, invalid scopes, missing required fields
2. **Time-consuming**: ~10-15 minutes to set up a basic config
3. **Poor discoverability**: New users didn't know what presets were available
4. **No guidance**: Users didn't know which requirements to enable for their use case

Example manual workflow:
```bash
mkdir .claude
cp ~/.claude/requirements.yaml .claude/requirements.yaml
vim .claude/requirements.yaml  # Edit enabled: false → true, customize...
```

Additionally, when starting a Claude Code session in a project without config, there was no indication that the framework existed or how to set it up.

## Decision

Add `req init` command with an interactive wizard that scaffolds project configuration using preset profiles.

### Core Features

1. **Interactive wizard (default)**
   - Asks which config to create (project vs local)
   - Offers preset selection (strict, relaxed, minimal)
   - Shows preview before writing
   - Confirms before creating files

2. **Non-interactive mode** (`--yes`)
   - For scripts and automation
   - Uses sensible defaults (relaxed preset, project config)
   - Supports all flags without prompts

3. **Preset profiles**
   - `relaxed`: commit_plan only (default, good for most teams)
   - `strict`: commit_plan + protected_branch guard
   - `minimal`: Framework enabled, empty requirements (DIY configuration)

4. **SessionStart detection**
   - Detects missing `.claude/requirements.yaml`
   - Suggests `req init` on session startup (not resume)
   - Non-intrusive hint message

### Design Principles

1. **Zero dependencies maintained**: InquirerPy is optional (rich UI if available)
2. **Stdlib fallback**: Simple numbered menus using `input()` when InquirerPy missing
3. **Safe defaults**: Non-destructive, warns before overwriting
4. **Follow cascade**: Creates project or local config respecting config hierarchy
5. **Preview-first**: Always shows what will be created before writing

## Implementation

### Files Created

- `hooks/lib/interactive.py` (220 lines)
  - `select()`, `confirm()`, `checkbox()` - prompt abstractions
  - InquirerPy detection and fallback logic
  - Stdlib implementations using `input()`

- `hooks/lib/init_presets.py` (280 lines)
  - `PRESETS` dict with strict/relaxed/minimal profiles
  - `get_preset()` - retrieve preset by name
  - `generate_config()` - add version/enabled, merge customizations
  - `config_to_yaml()` - YAML output with PyYAML or stdlib fallback
  - `_needs_quoting()` - robust YAML string safety (handles special chars, booleans, numbers)

### Files Modified

- `hooks/requirements-cli.py`
  - Added `cmd_init(args)` function (75 lines)
  - Added argparse subcommand with flags: `--yes`, `--preset`, `--local`, `--project`, `--force`, `--preview`
  - Interactive flow: detection → config selection → preset selection → preview → confirm → write
  - Non-interactive flow: generate → validate → write

- `hooks/handle-session-start.py`
  - Added project config detection before loading RequirementsConfig
  - Suggests `req init` when no project config exists (startup only)
  - Early return after suggestion (no status output)

- `hooks/test_requirements.py`
  - Added `test_interactive_module()` - 15 tests for prompt functions
  - Added `test_init_presets_module()` - 24 tests for presets and YAML generation
  - Added `test_cli_init_command()` - 17 tests for CLI integration
  - Modified `test_session_start_hook()` - 2 tests for init suggestion

### Test Coverage

**Total: 275 tests (up from 233)**
- 42 new tests specifically for init functionality
- 100% pass rate maintained
- All tests use TDD methodology (RED-GREEN-REFACTOR)

### Implementation Sequence (5 commits)

1. `f83fd76` - feat(init): add interactive prompt module with InquirerPy fallback
2. `68e2ae8` - feat(init): add preset profiles for req init command
3. `1e32ad4` - feat(cli): add req init command with non-interactive mode
4. `67cd9a2` - feat(cli): add interactive wizard flow to req init
5. `965b8e3` - feat(session): suggest req init when no project config exists

Each commit is independently functional and testable.

## Consequences

### Positive

1. **Reduced setup time**: 30 seconds vs 10-15 minutes for manual config
2. **Lower error rate**: Preset configs are pre-validated, no YAML syntax errors
3. **Better discoverability**: SessionStart suggests init automatically
4. **Guided onboarding**: Interactive wizard explains options
5. **Automation-friendly**: `--yes` mode works in scripts/CI
6. **Extensible**: Easy to add new presets in `init_presets.py`
7. **Safe**: Preview before write, warns on overwrites, respects `--force`

### Negative

1. **Code complexity**: +575 lines of code (2 new modules, modified 3 files)
2. **Optional dependency**: InquirerPy is recommended but not required (maintains zero-dependency principle)
3. **Test maintenance**: 42 additional test cases to maintain

### Neutral

1. **Manual config still supported**: Users can still create YAML files by hand if preferred
2. **Existing projects unaffected**: Only triggers suggestion for new projects without config
3. **SessionStart behavior**: Slight change - early return when suggesting init (no status output)

## Alternatives Considered

### 1. Template-based approach (Cookiecutter style)
**Pros**: Simple Jinja2 templates
**Cons**: Extra dependency, harder to maintain, less interactive

**Rejected**: Interactive approach provides better UX and guidance

### 2. Hardcoded example files to copy
**Pros**: No code needed
**Cons**: Still requires manual editing, error-prone

**Rejected**: Doesn't solve the "finding example" or "knowing which preset" problems

### 3. Non-interactive only (flags-based config)
**Pros**: Simpler implementation
**Cons**: Poor UX for first-time users, no guidance

**Rejected**: Interactive wizard significantly improves onboarding experience

### 4. Always suggest init (on every session)
**Pros**: More discoverable
**Cons**: Annoying for users who intentionally don't want project config

**Rejected**: Only suggest once on startup; respect user's choice not to init

## Extending This Pattern

To add a new preset:

1. Add to `PRESETS` dict in `hooks/lib/init_presets.py`:
```python
PRESETS['enterprise'] = {
    'requirements': {
        'commit_plan': {...},
        'github_ticket': {...},
        'adr_reviewed': {...},
        'protected_branch': {...},
    },
    'hooks': {
        'stop': {'verify_requirements': True},
    }
}
```

2. Update argparse choices in `requirements-cli.py`:
```python
init_parser.add_argument('--preset', '-p',
    choices=['strict', 'relaxed', 'minimal', 'enterprise'])
```

3. Add description in interactive wizard

No other changes needed - tests and config generation are already generic.

## Related

- **ADR-003**: Dynamic Sync File Discovery - `sync.sh` automatically includes new `lib/` modules
- **ADR-004**: Guard Requirement Strategy - `strict` preset includes `protected_branch` guard

## Future Enhancements

Potential future additions (out of scope for this ADR):
- `req config` command for modifying individual requirement settings
- More presets (team-specific, language-specific)
- Migration tool for converting old configs to new format
- Config validation command (`req validate`)
