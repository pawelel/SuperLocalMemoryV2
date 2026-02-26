#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""
Backward-compatible shim -- delegates to src/trust/ package.

All public symbols are re-exported so existing imports like
``from trust_scorer import TrustScorer`` continue to work unchanged.
"""

# Re-export everything from the trust package
from trust.constants import (  # noqa: F401
    SIGNAL_WEIGHTS,
    SIGNAL_DELTAS,
    INITIAL_ALPHA,
    INITIAL_BETA,
    DECAY_FACTOR,
    DECAY_INTERVAL,
    ALPHA_FLOOR,
    BETA_FLOOR,
    QUICK_DELETE_HOURS,
    BURST_THRESHOLD,
    BURST_WINDOW_MINUTES,
)

from trust.schema import init_trust_schema  # noqa: F401

from trust.scorer import TrustScorer  # noqa: F401

__all__ = [
    "TrustScorer",
    "SIGNAL_WEIGHTS",
    "SIGNAL_DELTAS",
    "INITIAL_ALPHA",
    "INITIAL_BETA",
    "DECAY_FACTOR",
    "DECAY_INTERVAL",
    "ALPHA_FLOOR",
    "BETA_FLOOR",
    "QUICK_DELETE_HOURS",
    "BURST_THRESHOLD",
    "BURST_WINDOW_MINUTES",
    "init_trust_schema",
]
