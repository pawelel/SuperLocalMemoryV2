# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""SuperLocalMemory V2 - Pattern Learning Package

Re-exports all public classes for backward-compatible imports:
    from patterns import PatternLearner, FrequencyAnalyzer, ...
"""
from .analyzers import FrequencyAnalyzer, ContextAnalyzer
from .terminology import TerminologyLearner
from .scoring import ConfidenceScorer
from .store import PatternStore
from .learner import PatternLearner, SKLEARN_AVAILABLE, MEMORY_DIR, DB_PATH

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
