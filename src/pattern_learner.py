#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""
Pattern Learner - Legacy import compatibility shim.

All implementation has moved to the `patterns` package.
This file re-exports every public symbol so that existing imports
like `from pattern_learner import PatternLearner` continue to work.
"""

from patterns import (  # noqa: F401
    FrequencyAnalyzer,
    ContextAnalyzer,
    TerminologyLearner,
    ConfidenceScorer,
    PatternStore,
    PatternLearner,
    SKLEARN_AVAILABLE,
    MEMORY_DIR,
    DB_PATH,
)

__all__ = [
    'FrequencyAnalyzer',
    'ContextAnalyzer',
    'TerminologyLearner',
    'ConfidenceScorer',
    'PatternStore',
    'PatternLearner',
    'SKLEARN_AVAILABLE',
    'MEMORY_DIR',
    'DB_PATH',
]
