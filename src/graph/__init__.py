# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""graph package - Knowledge Graph Clustering for SuperLocalMemory V2

Re-exports all public classes, constants, and functions so that
``from graph import GraphEngine`` (or any other symbol) works.
"""
from graph.constants import (
    MAX_MEMORIES_FOR_GRAPH,
    SKLEARN_AVAILABLE,
    IGRAPH_AVAILABLE,
    MEMORY_DIR,
    DB_PATH,
)
from graph.entity_extractor import EntityExtractor, ClusterNamer
from graph.edge_builder import EdgeBuilder
from graph.cluster_builder import ClusterBuilder
from graph.graph_core import GraphEngine
from graph.cli import main

__all__ = [
    # Constants
    "MAX_MEMORIES_FOR_GRAPH",
    "SKLEARN_AVAILABLE",
    "IGRAPH_AVAILABLE",
    "MEMORY_DIR",
    "DB_PATH",
    # Classes
    "EntityExtractor",
    "ClusterNamer",
    "EdgeBuilder",
    "ClusterBuilder",
    "GraphEngine",
    # Functions
    "main",
]
