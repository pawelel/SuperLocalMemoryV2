# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Tests for get_behavioral_patterns MCP tool handler.

Validates the MCP wrapper around BehavioralPatternExtractor — tests
pattern retrieval, confidence filtering, and project filtering.
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


def _create_learning_db_with_patterns(db_path: str) -> None:
    """Create learning.db with pre-seeded behavioral patterns."""
    conn = sqlite3.connect(db_path)
    # The BehavioralPatternExtractor creates this table itself, but we need
    # pre-seeded data for read-only tests. Create it manually.
    conn.execute(
        """CREATE TABLE IF NOT EXISTS behavioral_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_type TEXT NOT NULL,
            pattern_key TEXT NOT NULL,
            success_rate REAL DEFAULT 0.0,
            evidence_count INTEGER DEFAULT 0,
            confidence REAL DEFAULT 0.0,
            metadata TEXT DEFAULT '{}',
            project TEXT,
            profile TEXT DEFAULT 'default',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    # Pattern 1: high confidence, project-scoped
    conn.execute(
        "INSERT INTO behavioral_patterns "
        "(pattern_type, pattern_key, success_rate, evidence_count, confidence, project) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("project_success", "slm-v28", 0.85, 12, 0.8, "slm-v28"),
    )
    # Pattern 2: low confidence, no project
    conn.execute(
        "INSERT INTO behavioral_patterns "
        "(pattern_type, pattern_key, success_rate, evidence_count, confidence, project) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("action_type_success", "code_written", 0.55, 4, 0.15, None),
    )
    conn.commit()
    conn.close()


class TestMCPBehavioralPatterns:
    """Tests for the get_behavioral_patterns tool handler."""

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "learning.db")
        _create_learning_db_with_patterns(self.db_path)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_get_all_patterns(self):
        """Without filters, should return all patterns."""
        import mcp_tools_v28 as tools
        tools.DEFAULT_LEARNING_DB = self.db_path

        result = self._run(tools.get_behavioral_patterns())
        assert result["success"] is True
        assert result["count"] == 2

    def test_filter_by_high_confidence(self):
        """Filtering with min_confidence=0.9 should return 0 (none that high)."""
        import mcp_tools_v28 as tools
        tools.DEFAULT_LEARNING_DB = self.db_path

        result = self._run(tools.get_behavioral_patterns(min_confidence=0.9))
        assert result["success"] is True
        assert result["count"] == 0

    def test_filter_by_medium_confidence(self):
        """Filtering with min_confidence=0.5 should return only the high-confidence one."""
        import mcp_tools_v28 as tools
        tools.DEFAULT_LEARNING_DB = self.db_path

        result = self._run(tools.get_behavioral_patterns(min_confidence=0.5))
        assert result["success"] is True
        assert result["count"] == 1
        assert result["patterns"][0]["pattern_key"] == "slm-v28"

    def test_filter_by_project(self):
        """Filtering by project should scope results."""
        import mcp_tools_v28 as tools
        tools.DEFAULT_LEARNING_DB = self.db_path

        result = self._run(tools.get_behavioral_patterns(project="slm-v28"))
        assert result["success"] is True
        assert result["count"] == 1

    def test_filter_by_nonexistent_project(self):
        """Filtering by a project with no patterns should return 0."""
        import mcp_tools_v28 as tools
        tools.DEFAULT_LEARNING_DB = self.db_path

        result = self._run(tools.get_behavioral_patterns(project="nonexistent"))
        assert result["success"] is True
        assert result["count"] == 0

    def test_patterns_have_required_keys(self):
        """Each returned pattern should have standard keys."""
        import mcp_tools_v28 as tools
        tools.DEFAULT_LEARNING_DB = self.db_path

        result = self._run(tools.get_behavioral_patterns())
        for pattern in result["patterns"]:
            assert "pattern_type" in pattern
            assert "pattern_key" in pattern
            assert "success_rate" in pattern
            assert "confidence" in pattern

    def test_empty_db_returns_zero(self):
        """An empty learning DB should return count=0."""
        import mcp_tools_v28 as tools
        empty_path = os.path.join(self.tmp_dir, "empty_learning.db")
        tools.DEFAULT_LEARNING_DB = empty_path

        result = self._run(tools.get_behavioral_patterns())
        assert result["success"] is True
        assert result["count"] == 0
