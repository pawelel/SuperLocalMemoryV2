#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""
Trust scoring package -- Bayesian Beta-Binomial trust for AI agents.

Re-exports all public symbols for backward compatibility.
"""

from .constants import (
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

from .schema import init_trust_schema

from .scorer import TrustScorer

__all__ = [
    # Class
    "TrustScorer",
    # Constants
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
    # Schema
    "init_trust_schema",
]
