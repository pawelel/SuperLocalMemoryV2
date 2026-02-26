#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""GraphEngine - Knowledge Graph Clustering for SuperLocalMemory V2

BACKWARD-COMPATIBILITY SHIM
----------------------------
This file re-exports every public symbol from the ``graph`` package so that
existing code using ``from graph_engine import GraphEngine`` (or any other
name) continues to work without modification.

The actual implementation now lives in:
    src/graph/constants.py        - Shared imports, constants, logger
    src/graph/entity_extractor.py - EntityExtractor, ClusterNamer
    src/graph/edge_builder.py     - EdgeBuilder
    src/graph/cluster_builder.py  - ClusterBuilder
    src/graph/graph_core.py       - GraphEngine, main()
"""
# Re-export everything from the graph package
from graph import (
    # Constants
    MAX_MEMORIES_FOR_GRAPH,
    SKLEARN_AVAILABLE,
    IGRAPH_AVAILABLE,
    MEMORY_DIR,
    DB_PATH,
    # Classes
    EntityExtractor,
    ClusterNamer,
    EdgeBuilder,
    ClusterBuilder,
    GraphEngine,
    # Functions
    main,
)

__all__ = [
    "MAX_MEMORIES_FOR_GRAPH",
    "SKLEARN_AVAILABLE",
    "IGRAPH_AVAILABLE",
    "MEMORY_DIR",
    "DB_PATH",
    "EntityExtractor",
    "ClusterNamer",
    "EdgeBuilder",
    "ClusterBuilder",
    "GraphEngine",
    "main",
]

if __name__ == '__main__':
    main()
