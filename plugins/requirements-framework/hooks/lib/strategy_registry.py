#!/usr/bin/env python3
"""
Strategy registry - maps requirement types to strategy instances.

This module sits at the top of the dependency graph and instantiates
all concrete strategy implementations. It provides the central dispatch
mechanism for requirement checking.

The registry uses single instances per strategy type (lazy-initialized
at module load time) to avoid repeated initialization overhead.
"""

from blocking_strategy import BlockingRequirementStrategy
from dynamic_strategy import DynamicRequirementStrategy
from guard_strategy import GuardRequirementStrategy


# Strategy registry - single instance per type
STRATEGIES = {
    'blocking': BlockingRequirementStrategy(),
    'dynamic': DynamicRequirementStrategy(),
    'guard': GuardRequirementStrategy(),
}
