#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""
TreeManager - Thin re-export shim.

Implementation lives in src/tree/ (schema, nodes, queries, builder).
This file preserves backward compatibility for any existing imports.
"""

from tree.schema import MEMORY_DIR, DB_PATH
from tree import TreeManager

__all__ = ['TreeManager', 'MEMORY_DIR', 'DB_PATH']

# CLI interface
if __name__ == "__main__":
    from tree.builder import run_cli
    run_cli()
