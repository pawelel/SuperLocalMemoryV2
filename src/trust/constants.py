#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""
Beta-Binomial signal weights and trust scoring constants.

Extracted from trust_scorer.py for modularity.
"""

# ---------------------------------------------------------------------------
# Beta-Binomial signal weights
# ---------------------------------------------------------------------------
# Positive signals increment alpha (building trust).
# Negative signals increment beta (eroding trust).
# Neutral signals give a tiny alpha nudge to reward normal activity.
#
# Asymmetry: negative weights are larger than positive weights.
# This means it's harder to build trust than to lose it -- the system
# is intentionally skeptical. One poisoning event takes many good
# actions to recover from.
# ---------------------------------------------------------------------------

SIGNAL_WEIGHTS = {
    # Positive signals -> alpha += weight
    "memory_recalled_by_others": ("positive", 0.30),   # cross-agent validation
    "memory_updated":            ("positive", 0.15),   # ongoing relevance
    "high_importance_write":     ("positive", 0.20),   # valuable content (importance >= 7)
    "consistent_pattern":        ("positive", 0.15),   # stable write behavior

    # Negative signals -> beta += weight
    "quick_delete":              ("negative", 0.50),   # deleted within 1 hour
    "high_volume_burst":         ("negative", 0.40),   # >20 writes in 5 minutes
    "content_overwritten_by_user": ("negative", 0.25), # user had to fix output

    # Neutral signals -> tiny alpha nudge
    "normal_write":              ("neutral", 0.01),
    "normal_recall":             ("neutral", 0.01),
}

# Backward-compatible: expose SIGNAL_DELTAS as a derived dict so that
# bm6_trust.py (which imports SIGNAL_DELTAS) and any other consumer
# continues to work. The values represent the *direction* and *magnitude*
# of each signal: positive for alpha, negative for beta, zero for neutral.
SIGNAL_DELTAS = {}
for _sig, (_direction, _weight) in SIGNAL_WEIGHTS.items():
    if _direction == "positive":
        SIGNAL_DELTAS[_sig] = +_weight
    elif _direction == "negative":
        SIGNAL_DELTAS[_sig] = -_weight
    else:
        SIGNAL_DELTAS[_sig] = 0.0

# ---------------------------------------------------------------------------
# Beta prior and decay parameters
# ---------------------------------------------------------------------------
INITIAL_ALPHA = 2.0        # Slight positive prior
INITIAL_BETA = 1.0         # -> initial trust = 2/(2+1) = 0.667
DECAY_FACTOR = 0.995       # Multiply alpha & beta every DECAY_INTERVAL signals
DECAY_INTERVAL = 50        # Apply decay every N signals per agent
ALPHA_FLOOR = 1.0          # Never decay alpha below this
BETA_FLOOR = 0.5           # Never decay beta below this

# Thresholds
QUICK_DELETE_HOURS = 1       # Delete within 1 hour = negative signal
BURST_THRESHOLD = 20         # >20 writes in burst window = negative
BURST_WINDOW_MINUTES = 5     # Burst detection window
