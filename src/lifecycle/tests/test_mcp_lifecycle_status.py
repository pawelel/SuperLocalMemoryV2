# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Tests for get_lifecycle_status MCP tool handler.

Validates the MCP wrapper around LifecycleEngine — tests state distribution
retrieval, single memory state lookup, and nonexistent memory handling.
"""
import asyncio
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def _create_memory_db(db_path: str) -> None:
    """Create a minimal memory.db with lifecycle columns for testing."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE memories (
            id INTEGER PRIMARY KEY,
            content TEXT,
            lifecycle_state TEXT DEFAULT 'active',
            lifecycle_history TEXT DEFAULT '[]',
            lifecycle_updated_at TIMESTAMP,
            importance INTEGER DEFAULT 5,
            last_accessed TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            access_count INTEGER DEFAULT 0,
            profile TEXT DEFAULT 'default',
            access_level TEXT DEFAULT 'public'
        )"""
    )
    conn.execute(
        "INSERT INTO memories (content, lifecycle_state) VALUES ('test mem 1', 'active')"
    )
    conn.execute(
        "INSERT INTO memories (content, lifecycle_state) VALUES ('test mem 2', 'warm')"
    )
    conn.execute(
        "INSERT INTO memories (content, lifecycle_state) VALUES ('test mem 3', 'active')"
    )
    conn.commit()
    conn.close()


class TestMCPLifecycleStatus:
    """Tests for the get_lifecycle_status tool handler."""

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "memory.db")
        _create_memory_db(self.db_path)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_get_distribution(self):
        """Without memory_id, should return state distribution."""
        import mcp_tools_v28 as tools
        tools.DEFAULT_MEMORY_DB = self.db_path

        result = self._run(tools.get_lifecycle_status())
        assert result["success"] is True
        assert "distribution" in result
        assert result["distribution"]["active"] == 2
        assert result["distribution"]["warm"] == 1
        assert result["total_memories"] == 3

    def test_get_single_active_memory(self):
        """With memory_id=1, should return lifecycle_state='active'."""
        import mcp_tools_v28 as tools
        tools.DEFAULT_MEMORY_DB = self.db_path

        result = self._run(tools.get_lifecycle_status(memory_id=1))
        assert result["success"] is True
        assert result["memory_id"] == 1
        assert result["lifecycle_state"] == "active"

    def test_get_single_warm_memory(self):
        """With memory_id=2, should return lifecycle_state='warm'."""
        import mcp_tools_v28 as tools
        tools.DEFAULT_MEMORY_DB = self.db_path

        result = self._run(tools.get_lifecycle_status(memory_id=2))
        assert result["success"] is True
        assert result["lifecycle_state"] == "warm"

    def test_nonexistent_memory(self):
        """Looking up a nonexistent memory_id should return success=False."""
        import mcp_tools_v28 as tools
        tools.DEFAULT_MEMORY_DB = self.db_path

        result = self._run(tools.get_lifecycle_status(memory_id=999))
        assert result["success"] is False
        assert "not found" in result["error"]

    def test_distribution_all_states_present(self):
        """Distribution dict should always contain all 5 lifecycle states."""
        import mcp_tools_v28 as tools
        tools.DEFAULT_MEMORY_DB = self.db_path

        result = self._run(tools.get_lifecycle_status())
        dist = result["distribution"]
        for state in ("active", "warm", "cold", "archived", "tombstoned"):
            assert state in dist
