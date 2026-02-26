# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Tree — Hierarchical Memory Tree Management.

Composes the TreeManager class from focused mixin modules:
  - schema.py  : DB initialization and root-node bootstrap
  - nodes.py   : Node CRUD and count aggregation
  - queries.py : Read-only tree traversal and statistics
  - builder.py : Full tree construction from memories table
"""
from pathlib import Path
from typing import Optional

from .schema import TreeSchemaMixin, MEMORY_DIR, DB_PATH
from .nodes import TreeNodesMixin
from .queries import TreeQueriesMixin
from .builder import TreeBuilderMixin


class TreeManager(TreeSchemaMixin, TreeNodesMixin, TreeQueriesMixin, TreeBuilderMixin):
    """
    Manages hierarchical tree structure for memory navigation.

    Tree Structure:
        Root
        +-- Project: NextJS-App
        |   +-- Category: Frontend
        |   |   +-- Memory: React Components
        |   |   +-- Memory: State Management
        |   +-- Category: Backend
        |       +-- Memory: API Routes
        +-- Project: Python-ML

    Materialized Path Format:
        - Root: "1"
        - Project: "1.2"
        - Category: "1.2.3"
        - Memory: "1.2.3.4"

    Benefits:
        - Fast subtree queries: WHERE tree_path LIKE '1.2.%'
        - O(1) depth calculation: count dots in path
        - O(1) parent lookup: parse path
        - No recursive CTEs needed
    """

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize TreeManager.

        Args:
            db_path: Optional custom database path
        """
        self.db_path = db_path or DB_PATH
        self._init_db()
        self.root_id = self._ensure_root()


__all__ = ['TreeManager', 'MEMORY_DIR', 'DB_PATH']
