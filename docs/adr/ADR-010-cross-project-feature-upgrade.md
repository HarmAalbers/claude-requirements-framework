# ADR-010: Cross-Project Feature Upgrade System

## Status
Approved (2026-01-21)

## Context

When the requirements framework plugin is updated with new features (like `session_learning`), there's no way to:
1. Discover all projects using the plugin on a machine
2. Show which features are available vs. configured per project
3. Recommend how to integrate new features into existing projects

Users have to manually remember which projects use the framework and individually check each one for missing features. This becomes tedious as the framework grows and more features are added.

## Decision

**Implement a `req upgrade` command that tracks projects machine-wide and helps users adopt new features.**

### Architecture

#### Feature Catalog (`hooks/lib/feature_catalog.py`)
A comprehensive catalog of all framework features with metadata:
- Name, description, category (requirements/guards/hooks)
- Config path (e.g., `requirements.commit_plan`, `hooks.session_learning`)
- Version introduced (for "new since" queries)
- Example YAML snippets for integration

#### Project Registry (`hooks/lib/project_registry.py`)
Machine-wide tracking of projects in `~/.claude/project_registry.json`:
- Stores discovered project paths
- Records which features each project has configured
- Tracks last-seen timestamps for stale detection

#### CLI Commands
```
req upgrade scan               # Scan machine for projects
req upgrade status             # Show features for current project
req upgrade status --all       # Show all tracked projects
req upgrade recommend          # Generate YAML snippets for missing features
req upgrade recommend -f NAME  # Show snippet for specific feature
```

### Auto-Registration
Projects are opportunistically registered when sessions start (in `handle-session-start.py`), keeping the registry fresh without requiring explicit scans.

## Consequences

### Positive
- Users can discover all framework-enabled projects on their machine
- Easy to see which features are missing from each project
- Ready-to-copy YAML snippets reduce integration friction
- Auto-registration keeps the registry current during normal use

### Negative
- Additional storage (~1KB JSON file in `~/.claude/`)
- Slight overhead during session start (one file write)

### Neutral
- Scanning uses default paths (`~/Projects`, `~/Work`, `~/Code`, `~/Developer`, `~/dev`, `~/Tools`)
- Max scan depth of 4 levels prevents filesystem overload

## Implementation Notes

1. **Fail-open design**: All registry operations fail silently to never block workflow
2. **Atomic writes**: Uses same pattern as session registry (temp file + rename)
3. **Feature detection**: Navigates config paths to detect enabled vs. configured features
4. **Version tracking**: Features include `introduced` field for "new since X" queries

## Example Output

```
$ req upgrade status
Feature Status: /Users/harm/Work/my-project
────────────────────────────────────────────────────────────

  Requirements:
    commit_plan               ✓ Enabled
    adr_reviewed              ✓ Enabled
    session_learning          ○ Not configured
      └─ Analyze sessions to improve future efficiency

────────────────────────────────────────────────────────────
  Enabled: 2/12 features

Run 'req upgrade recommend' to see integration snippets
```
