#!/usr/bin/env python3
"""
Feature Catalog Module

Provides a comprehensive catalog of all available framework features
(both requirements and hooks) with metadata for discovery and upgrade workflows.

This module enables:
- Detecting which features are configured in a project
- Identifying missing/new features
- Generating YAML snippets for feature integration

Usage:
    from feature_catalog import (
        get_all_features,
        detect_configured_features,
        get_missing_features,
        get_unconfigured_features,
        get_feature_yaml
    )

    # Get all available features
    features = get_all_features()

    # Detect what's configured
    configured = detect_configured_features(config)

    # Find missing features
    missing = get_missing_features(config)

    # Get YAML snippet for a feature
    yaml = get_feature_yaml('session_learning')
"""
from typing import Any, Dict, List, Optional

# Feature categories for organization
CATEGORY_REQUIREMENTS = "requirements"
CATEGORY_HOOKS = "hooks"
CATEGORY_GUARDS = "guards"

# Feature catalog - comprehensive list of all framework features
FEATURE_CATALOG: Dict[str, Dict[str, Any]] = {
    # =========================================================================
    # REQUIREMENTS
    # =========================================================================
    "commit_plan": {
        "name": "Commit Planning",
        "category": CATEGORY_REQUIREMENTS,
        "config_path": "requirements.commit_plan",
        "description": "Require planning before code changes",
        "introduced": "1.0",
        "default_enabled": True,
        "example_yaml": """requirements:
  commit_plan:
    enabled: true
    type: blocking
    scope: session
    description: "Ensures an atomic commit strategy exists before implementation."
    trigger_tools:
      - Edit
      - Write
      - MultiEdit
    auto_resolve_skill: "requirements-framework:plan-review"
    message: |
      ## Blocked: commit_plan

      **Execute**: `/requirements-framework:plan-review`

      Generates atomic commit strategy after ADR and TDD validation.

      ---
      Fallback: `req satisfy commit_plan`""",
    },
    "adr_reviewed": {
        "name": "ADR Review",
        "category": CATEGORY_REQUIREMENTS,
        "config_path": "requirements.adr_reviewed",
        "description": "Check Architecture Decision Records before changes",
        "introduced": "1.0",
        "default_enabled": True,
        "example_yaml": """requirements:
  adr_reviewed:
    enabled: true
    type: blocking
    scope: session
    description: "Ensures changes align with Architecture Decision Records."
    trigger_tools:
      - Edit
      - Write
      - MultiEdit
    auto_resolve_skill: "requirements-framework:plan-review"
    message: |
      ## Blocked: adr_reviewed

      **Execute**: `/requirements-framework:plan-review`

      ---
      Fallback: `req satisfy adr_reviewed`""",
    },
    "tdd_planned": {
        "name": "TDD Planning",
        "category": CATEGORY_REQUIREMENTS,
        "config_path": "requirements.tdd_planned",
        "description": "Ensure plan includes TDD strategy and test cases per feature",
        "introduced": "1.2",
        "default_enabled": True,
        "example_yaml": """requirements:
  tdd_planned:
    enabled: true
    type: blocking
    scope: session
    description: "Ensures the plan includes TDD strategy and test cases per feature."
    trigger_tools:
      - Edit
      - Write
      - MultiEdit
    auto_resolve_skill: "requirements-framework:plan-review"
    message: |
      ## Blocked: tdd_planned

      **Execute**: `/requirements-framework:plan-review`

      Validates TDD readiness: test strategy and test cases per feature.

      ---
      Fallback: `req satisfy tdd_planned`""",
    },
    "solid_reviewed": {
        "name": "SOLID Review",
        "category": CATEGORY_REQUIREMENTS,
        "config_path": "requirements.solid_reviewed",
        "description": "Validate plan against SOLID design principles",
        "introduced": "2.2",
        "default_enabled": True,
        "example_yaml": """requirements:
  solid_reviewed:
    enabled: true
    type: blocking
    scope: session
    description: "Ensures the plan follows SOLID principles with Python-specific patterns."
    trigger_tools:
      - Edit
      - Write
      - MultiEdit
    auto_resolve_skill: "requirements-framework:plan-review"
    message: |
      ## Blocked: solid_reviewed

      **Execute**: `/requirements-framework:plan-review`

      Validates SOLID principles adherence in the implementation plan.

      ---
      Fallback: `req satisfy solid_reviewed`""",
    },
    "pre_commit_review": {
        "name": "Pre-Commit Review",
        "category": CATEGORY_REQUIREMENTS,
        "config_path": "requirements.pre_commit_review",
        "description": "Code review before each commit",
        "introduced": "1.0",
        "default_enabled": True,
        "example_yaml": """requirements:
  pre_commit_review:
    enabled: true
    type: blocking
    scope: single_use
    description: "Code review before each commit."
    trigger_tools:
      - tool: Bash
        command_pattern: "git\\\\s+(commit|cherry-pick|revert|merge)"
    auto_resolve_skill: "requirements-framework:pre-commit"
    satisfied_by_skill: 'requirements-framework:pre-commit'
    message: |
      ## Blocked: pre_commit_review

      **Execute**: `/requirements-framework:pre-commit`

      ---
      Fallback: `req satisfy pre_commit_review`""",
    },
    "pre_pr_review": {
        "name": "Pre-PR Review",
        "category": CATEGORY_REQUIREMENTS,
        "config_path": "requirements.pre_pr_review",
        "description": "Comprehensive quality check before PR creation",
        "introduced": "1.0",
        "default_enabled": True,
        "example_yaml": """requirements:
  pre_pr_review:
    enabled: true
    type: blocking
    scope: single_use
    description: "Comprehensive quality review before PR creation."
    trigger_tools:
      - tool: Bash
        command_pattern: "gh\\\\s+pr\\\\s+create"
    auto_resolve_skill: "requirements-framework:quality-check"
    satisfied_by_skill: 'requirements-framework:quality-check'
    message: |
      ## Blocked: pre_pr_review

      **Execute**: `/requirements-framework:quality-check`

      ---
      Fallback: `req satisfy pre_pr_review`""",
    },
    "codex_reviewer": {
        "name": "Codex AI Review",
        "category": CATEGORY_REQUIREMENTS,
        "config_path": "requirements.codex_reviewer",
        "description": "AI-powered code review via OpenAI Codex CLI",
        "introduced": "1.0",
        "default_enabled": True,
        "example_yaml": """requirements:
  codex_reviewer:
    enabled: true
    type: blocking
    scope: single_use
    description: "AI-powered code review via OpenAI Codex CLI."
    trigger_tools:
      - tool: Bash
        command_pattern: "gh\\\\s+pr\\\\s+create"
    auto_resolve_skill: "requirements-framework:codex-review"
    satisfied_by_skill: 'requirements-framework:codex-review'
    message: |
      ## Blocked: codex_reviewer

      **Execute**: `/requirements-framework:codex-review`

      ---
      Fallback: `req satisfy codex_reviewer`""",
    },
    "github_ticket": {
        "name": "GitHub Ticket",
        "category": CATEGORY_REQUIREMENTS,
        "config_path": "requirements.github_ticket",
        "description": "Link work to GitHub issue tracking",
        "introduced": "1.0",
        "default_enabled": False,
        "example_yaml": """requirements:
  github_ticket:
    enabled: true
    type: blocking
    scope: branch
    description: "Links work to GitHub issue tracking."
    trigger_tools:
      - Edit
      - Write
      - MultiEdit
    message: |
      ## Blocked: github_ticket

      No GitHub issue linked to this branch.

      ---
      Fallback: `req satisfy github_ticket --metadata '{"ticket":"#1234"}'`""",
    },
    # =========================================================================
    # DYNAMIC REQUIREMENTS
    # =========================================================================
    "branch_size_limit": {
        "name": "Branch Size Limits",
        "category": CATEGORY_REQUIREMENTS,
        "config_path": "requirements.branch_size_limit",
        "description": "Automatically calculate and enforce PR size limits",
        "introduced": "1.0",
        "default_enabled": True,
        "example_yaml": """requirements:
  branch_size_limit:
    enabled: true
    type: dynamic
    calculator: branch_size_calculator
    description: "Automatically calculates branch size and enforces limits."
    scope: session
    trigger_tools:
      - Edit
      - Write
      - MultiEdit
    cache_ttl: 60
    approval_ttl: 3600
    thresholds:
      warn: 250
      block: 400
    blocking_message: |
      ## Blocked: branch_size_limit

      Branch has **{total}** line changes (limit: {block_threshold}).

      ---
      Override: `req approve branch_size_limit`""",
    },
    # =========================================================================
    # GUARDS
    # =========================================================================
    "protected_branch": {
        "name": "Protected Branches",
        "category": CATEGORY_GUARDS,
        "config_path": "requirements.protected_branch",
        "description": "Prevent direct edits on main/master branches",
        "introduced": "1.0",
        "default_enabled": True,
        "example_yaml": """requirements:
  protected_branch:
    enabled: true
    type: guard
    guard_type: protected_branch
    description: "Prevents direct edits on main/master branches."
    protected_branches:
      - master
      - main
    trigger_tools:
      - Edit
      - Write
      - MultiEdit
    message: |
      ## Blocked: protected_branch

      Cannot edit files on protected branch `{branch}`.

      **Actions**:
      1. Create feature branch: `git checkout -b feature/your-feature-name`
      2. Emergency override: `req approve protected_branch`""",
    },
    "single_session_per_project": {
        "name": "Single Session Guard",
        "category": CATEGORY_GUARDS,
        "config_path": "requirements.single_session_per_project",
        "description": "Prevent multiple sessions editing same project",
        "introduced": "1.0",
        "default_enabled": False,
        "example_yaml": """requirements:
  single_session_per_project:
    enabled: true
    type: guard
    guard_type: single_session
    description: "Prevents multiple sessions from editing same project."
    scope: session
    trigger_tools:
      - Edit
      - Write
      - MultiEdit
    message: |
      ## Blocked: single_session_per_project

      Another Claude Code session is active on this project.

      ---
      Override: `req approve single_session_per_project`""",
    },
    # =========================================================================
    # HOOKS
    # =========================================================================
    "session_learning": {
        "name": "Session Learning",
        "category": CATEGORY_HOOKS,
        "config_path": "hooks.session_learning",
        "description": "Analyze sessions to improve future efficiency",
        "introduced": "1.1",
        "default_enabled": False,
        "example_yaml": """hooks:
  session_learning:
    enabled: true
    prompt_on_stop: true
    min_tool_uses: 5""",
    },
    "session_start": {
        "name": "Session Start Context",
        "category": CATEGORY_HOOKS,
        "config_path": "hooks.session_start",
        "description": "Inject requirement context at session start",
        "introduced": "1.0",
        "default_enabled": True,
        "example_yaml": """hooks:
  session_start:
    inject_context: true
    injection_mode: auto""",
    },
    "stop_verification": {
        "name": "Stop Verification",
        "category": CATEGORY_HOOKS,
        "config_path": "hooks.stop",
        "description": "Verify requirements before session ends",
        "introduced": "1.0",
        "default_enabled": True,
        "example_yaml": """hooks:
  stop:
    verify_requirements: true""",
    },
}


def get_all_features() -> Dict[str, Dict[str, Any]]:
    """
    Get the complete feature catalog.

    Returns:
        Dict mapping feature names to their metadata
    """
    return FEATURE_CATALOG.copy()


def get_features_by_category(category: str) -> Dict[str, Dict[str, Any]]:
    """
    Get features filtered by category.

    Args:
        category: One of 'requirements', 'hooks', 'guards'

    Returns:
        Dict of features in that category
    """
    return {
        name: info
        for name, info in FEATURE_CATALOG.items()
        if info.get("category") == category
    }


def detect_configured_features(config: Dict[str, Any]) -> Dict[str, bool]:
    """
    Check which features are configured in a config dict.

    Args:
        config: Loaded requirements config dict

    Returns:
        Dict mapping feature names to enabled status (True/False/None if not configured)
    """
    result: Dict[str, bool] = {}

    for feature_name, feature_info in FEATURE_CATALOG.items():
        config_path = feature_info.get("config_path", "")
        parts = config_path.split(".")

        # Navigate config path
        current = config
        found = True
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                found = False
                break

        if found and isinstance(current, dict):
            # Feature is configured - check if enabled
            result[feature_name] = current.get("enabled", True)
        else:
            # Feature not configured
            result[feature_name] = False

    return result


def get_missing_features(config: Dict[str, Any]) -> List[str]:
    """
    Get list of features not configured in a config.

    Args:
        config: Loaded requirements config dict

    Returns:
        List of feature names that are not configured
    """
    configured = detect_configured_features(config)
    return [name for name, enabled in configured.items() if not enabled]


def get_unconfigured_features(config: Dict[str, Any]) -> List[str]:
    """
    Get features that are truly absent from config (not just disabled).

    Unlike get_missing_features() which treats disabled features as missing,
    this only returns features with no config entry at all. Used by
    'req upgrade apply' to avoid re-adding deliberately disabled features.

    Args:
        config: Loaded requirements config dict

    Returns:
        List of feature names not present in config
    """
    result = []
    for feature_name, feature_info in FEATURE_CATALOG.items():
        config_path = feature_info.get("config_path", "")
        parts = config_path.split(".")

        current = config
        found = True
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                found = False
                break

        if not found:
            result.append(feature_name)

    return result


def get_enabled_features(config: Dict[str, Any]) -> List[str]:
    """
    Get list of features that are configured and enabled.

    Args:
        config: Loaded requirements config dict

    Returns:
        List of enabled feature names
    """
    configured = detect_configured_features(config)
    return [name for name, enabled in configured.items() if enabled]


def get_feature_yaml(feature_name: str) -> Optional[str]:
    """
    Get the example YAML snippet for a feature.

    Args:
        feature_name: Name of the feature

    Returns:
        YAML snippet string, or None if feature not found
    """
    feature = FEATURE_CATALOG.get(feature_name)
    if feature:
        return feature.get("example_yaml")
    return None


def get_feature_info(feature_name: str) -> Optional[Dict[str, Any]]:
    """
    Get full metadata for a feature.

    Args:
        feature_name: Name of the feature

    Returns:
        Feature metadata dict, or None if not found
    """
    return FEATURE_CATALOG.get(feature_name)


def get_new_features_since(version: str) -> List[str]:
    """
    Get features introduced after a given version.

    Args:
        version: Version string (e.g., "1.0")

    Returns:
        List of feature names introduced after that version
    """
    # Simple version comparison (assumes major.minor format)
    try:
        major, minor = map(int, version.split("."))
        target_version = (major, minor)
    except ValueError:
        return []

    new_features = []
    for name, info in FEATURE_CATALOG.items():
        introduced = info.get("introduced", "1.0")
        try:
            intro_major, intro_minor = map(int, introduced.split("."))
            if (intro_major, intro_minor) > target_version:
                new_features.append(name)
        except ValueError:
            continue

    return new_features
