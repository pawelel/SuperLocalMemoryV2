# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Tests for compact_memories MCP tool handler.

Validates the MCP wrapper around LifecycleEvaluator + LifecycleEngine —
tests dry_run mode, recommendations output, and live transition execution.
"""
import asyncio
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def _create_memory_db(db_path: str) -> None:
    """Create memory.db with a mix of stale and fresh memories."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE memories (
            id INTEGER PRIMARY KEY,
            content TEXT,
            importance INTEGER DEFAULT 5,
            lifecycle_state TEXT DEFAULT 'active',
            lifecycle_history TEXT DEFAULT '[]',
            lifecycle_updated_at TIMESTAMP,
            last_accessed TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            access_count INTEGER DEFAULT 0,
            profile TEXT DEFAULT 'default',
            access_level TEXT DEFAULT 'public'
        )"""
    )
    now = datetime.now()
    # Stale: 45 days old, low importance -> should be recommended for active->warm
    conn.execute(
        "INSERT INTO memories (content, importance, lifecycle_state, last_accessed, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            "stale memory",
            3,
            "active",
            (now - timedelta(days=45)).isoformat(),
            (now - timedelta(days=100)).isoformat(),
        ),
    )
    # Fresh: just accessed, high importance -> should NOT be recommended
    conn.execute(
        "INSERT INTO memories (content, importance, lifecycle_state, last_accessed, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("fresh memory", 8, "active", now.isoformat(), now.isoformat()),
    )
    conn.commit()
    conn.close()


class TestMCPCompact:
    """Tests for the compact_memories tool handler."""

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "memory.db")
        _create_memory_db(self.db_path)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_dry_run_default(self):
        """Default call should be dry_run=True."""
        import mcp_tools_v28 as tools
        tools.DEFAULT_MEMORY_DB = self.db_path

        result = self._run(tools.compact_memories())
        assert result["success"] is True
        assert result["dry_run"] is True

    def test_dry_run_shows_recommendations(self):
        """Dry run should report recommendation count."""
        import mcp_tools_v28 as tools
        tools.DEFAULT_MEMORY_DB = self.db_path

        result = self._run(tools.compact_memories(dry_run=True))
        assert "recommendations" in result
        assert isinstance(result["recommendations"], int)

    def test_dry_run_has_stale_recommendation(self):
        """The stale memory should appear in recommendations."""
        import mcp_tools_v28 as tools
        tools.DEFAULT_MEMORY_DB = self.db_path

        result = self._run(tools.compact_memories(dry_run=True))
        assert result["recommendations"] >= 1
        # The stale memory (id=1) should be recommended active -> warm
        detail_ids = [d["memory_id"] for d in result.get("details", [])]
        assert 1 in detail_ids

    def test_dry_run_details_structure(self):
        """Each detail entry should have the right keys."""
        import mcp_tools_v28 as tools
        tools.DEFAULT_MEMORY_DB = self.db_path

        result = self._run(tools.compact_memories(dry_run=True))
        if result["recommendations"] > 0:
            detail = result["details"][0]
            assert "memory_id" in detail
            assert "from" in detail
            assert "to" in detail
            assert "reason" in detail

    def test_execute_transitions(self):
        """Non-dry-run should actually transition memories."""
        import mcp_tools_v28 as tools
        tools.DEFAULT_MEMORY_DB = self.db_path

        result = self._run(tools.compact_memories(dry_run=False))
        assert result["success"] is True
        assert result["dry_run"] is False
        assert "transitioned" in result
        assert "evaluated" in result

    def test_execute_changes_state(self):
        """After execution, the stale memory should be in 'warm' state."""
        import mcp_tools_v28 as tools
        tools.DEFAULT_MEMORY_DB = self.db_path

        self._run(tools.compact_memories(dry_run=False))
        # Verify the stale memory transitioned
        result = self._run(tools.get_lifecycle_status(memory_id=1))
        assert result["success"] is True
        assert result["lifecycle_state"] == "warm"

    def test_fresh_memory_untouched(self):
        """After execution, the fresh memory should remain 'active'."""
        import mcp_tools_v28 as tools
        tools.DEFAULT_MEMORY_DB = self.db_path

        self._run(tools.compact_memories(dry_run=False))
        result = self._run(tools.get_lifecycle_status(memory_id=2))
        assert result["success"] is True
        assert result["lifecycle_state"] == "active"
