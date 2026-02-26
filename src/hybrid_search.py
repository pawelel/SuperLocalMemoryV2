#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""SuperLocalMemory V2 - Hybrid Search System

Solution Architect & Original Creator

 (see LICENSE file)

ATTRIBUTION REQUIRED: This notice must be preserved in all copies.
"""
"""
BACKWARD-COMPATIBILITY SHIM
----------------------------
This file re-exports every public symbol from the ``search`` package so that
existing code using ``from hybrid_search import HybridSearchEngine`` continues
to work without modification.

The actual implementation now lives in:
    src/search/constants.py      - Shared imports and constants
    src/search/index_loader.py   - Index building and graph lazy-loading
    src/search/methods.py        - BM25, semantic, and graph search methods
    src/search/fusion.py         - Score normalization and fusion strategies
    src/search/engine.py         - HybridSearchEngine orchestrator
    src/search/cli.py            - CLI demo interface
"""

# Re-export everything from the search package
from search import (
    HybridSearchEngine,
    FusionMixin,
    SearchMethodsMixin,
    IndexLoaderMixin,
    main,
)

__all__ = [
    "HybridSearchEngine",
    "FusionMixin",
    "SearchMethodsMixin",
    "IndexLoaderMixin",
    "main",
]

if __name__ == '__main__':
    main()
