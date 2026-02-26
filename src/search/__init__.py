# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""search package - Hybrid Search System for SuperLocalMemory V2

Re-exports all public classes so that
``from search import HybridSearchEngine`` works.
"""
from search.engine import HybridSearchEngine
from search.fusion import FusionMixin
from search.methods import SearchMethodsMixin
from search.index_loader import IndexLoaderMixin
from search.cli import main

__all__ = [
    "HybridSearchEngine",
    "FusionMixin",
    "SearchMethodsMixin",
    "IndexLoaderMixin",
    "main",
]
