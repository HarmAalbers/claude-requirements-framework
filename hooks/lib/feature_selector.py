"""
Feature Selector Module

Provides interactive feature selection for the `req init` command.
Allows users to cherry-pick specific requirements instead of using presets.

Usage:
    from feature_selector import FeatureSelector

    selector = FeatureSelector()
    selected = selector.select_features_interactive()
    config = selector.build_config_from_features(selected, context='project')
"""
from typing import Dict, List, Any
from pathlib import Path


# Feature catalog - maps requirement keys to user-friendly descriptions
FEATURES = {
    'commit_plan': {
        'name': 'Commit Planning',
        'description': 'Require planning before code changes',
        'category': 'code_quality',
        'type': 'blocking',
        'scope': 'session',
    },
    'adr_reviewed': {
        'name': 'ADR Review',
        'description': 'Check Architecture Decision Records',
        'category': 'code_quality',
        'type': 'blocking',
        'scope': 'session',
    },
    'protected_branch': {
        'name': 'Protected Branches',
        'description': 'Prevent edits on main/master',
        'category': 'branch_protection',
        'type': 'guard',
    },
    'branch_size_limit': {
        'name': 'Branch Size Limits',
        'description': 'Warn/block large PRs',
        'category': 'code_quality',
        'type': 'dynamic',
    },
    'pre_commit_review': {
        'name': 'Pre-Commit Review',
        'description': 'Review before every commit',
        'category': 'code_quality',
        'type': 'blocking',
        'scope': 'single_use',
    },
    'pre_pr_review': {
        'name': 'Pre-PR Review',
        'description': 'Quality check before PR creation',
        'category': 'code_quality',
        'type': 'blocking',
        'scope': 'single_use',
    },
    'codex_reviewer': {
        'name': 'Codex AI Review',
        'description': 'AI-powered review before PR',
        'category': 'code_quality',
        'type': 'blocking',
        'scope': 'single_use',
    },
}


class FeatureSelector:
    """Interactive feature selection for custom init."""

    def select_features_interactive(self) -> List[str]:
        """
        Show interactive checkbox for feature selection.
        Returns list of selected feature keys.
        """
        from lib.interactive import checkbox

        # Build options list and track mapping
        options = []
        option_to_key = {}

        for key, info in FEATURES.items():
            option_str = f"{info['name']} - {info['description']}"
            options.append(option_str)
            option_to_key[option_str] = key

        # Default selections: commit_plan, adr_reviewed, pre_commit_review
        default_keys = ['commit_plan', 'adr_reviewed', 'pre_commit_review']
        defaults = [
            f"{FEATURES[k]['name']} - {FEATURES[k]['description']}"
            for k in default_keys
            if k in FEATURES
        ]

        selected = checkbox(
            "Select features to enable:",
            options,
            default=defaults
        )

        # Map selected option strings back to feature keys
        selected_keys = [option_to_key[opt] for opt in selected if opt in option_to_key]

        return selected_keys

    def build_config_from_features(
        self,
        features: List[str],
        context: str = 'project'
    ) -> Dict[str, Any]:
        """
        Generate config dict from selected features.

        Args:
            features: List of requirement keys to include
            context: Config context - 'global', 'project', or 'local'

        Returns:
            Configuration dict ready to write
        """
        import sys
        from lib.init_presets import get_preset

        config = {
            'version': '1.0',
            'enabled': True,
            'requirements': {}
        }

        # Add inherit flag for project context
        if context == 'project':
            config['inherit'] = True

        # For each selected feature, get full config from advanced preset
        advanced = get_preset('advanced')
        missing_features = []

        for feature_key in features:
            if feature_key in advanced.get('requirements', {}):
                config['requirements'][feature_key] = advanced['requirements'][feature_key]
            else:
                missing_features.append(feature_key)

        # Warn about missing features
        if missing_features:
            try:
                from lib.colors import warning, hint
                print(warning(f"⚠️  Features not found: {', '.join(missing_features)}"), file=sys.stderr)
                print(hint("💡 This may indicate a bug. Please report it."), file=sys.stderr)
            except ImportError:
                print(f"Warning: Features not found: {', '.join(missing_features)}", file=sys.stderr)

        return config
