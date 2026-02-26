# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Tests for set_retention_policy MCP tool handler.

Validates the MCP wrapper around RetentionPolicyManager — tests policy
creation with tags, project scope, and various framework types.
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
    """Create a minimal memory.db for RetentionPolicyManager."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE memories (
            id INTEGER PRIMARY KEY,
            content TEXT,
            tags TEXT DEFAULT '[]',
            project_name TEXT,
            lifecycle_state TEXT DEFAULT 'active',
            profile TEXT DEFAULT 'default'
        )"""
    )
    conn.commit()
    conn.close()


class TestMCPRetentionPolicy:
    """Tests for the set_retention_policy tool handler."""

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "memory.db")
        _create_memory_db(self.db_path)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_create_gdpr_policy(self):
        """Creating a GDPR tombstone policy should return success with policy_id."""
        import mcp_tools_v28 as tools
        tools.DEFAULT_MEMORY_DB = self.db_path

        result = self._run(
            tools.set_retention_policy(
                "GDPR Erasure", "gdpr", 0, "tombstone", ["gdpr"]
            )
        )
        assert result["success"] is True
        assert isinstance(result["policy_id"], int)
        assert result["policy_id"] > 0
        assert result["name"] == "GDPR Erasure"
        assert result["framework"] == "gdpr"

    def test_create_hipaa_policy(self):
        """Creating a HIPAA retention policy should succeed."""
        import mcp_tools_v28 as tools
        tools.DEFAULT_MEMORY_DB = self.db_path

        result = self._run(
            tools.set_retention_policy(
                "HIPAA Retention", "hipaa", 2190, "retain", ["medical"]
            )
        )
        assert result["success"] is True
        assert result["framework"] == "hipaa"

    def test_create_policy_with_project(self):
        """Policy scoped to a project should succeed."""
        import mcp_tools_v28 as tools
        tools.DEFAULT_MEMORY_DB = self.db_path

        result = self._run(
            tools.set_retention_policy(
                "Internal Retention",
                "internal",
                365,
                "archive",
                applies_to_project="myproject",
            )
        )
        assert result["success"] is True

    def test_create_policy_with_tags_and_project(self):
        """Policy with both tags and project scope should succeed."""
        import mcp_tools_v28 as tools
        tools.DEFAULT_MEMORY_DB = self.db_path

        result = self._run(
            tools.set_retention_policy(
                "EU AI Act",
                "eu_ai_act",
                1825,
                "retain",
                applies_to_tags=["ai-decision"],
                applies_to_project="ml-pipeline",
            )
        )
        assert result["success"] is True

    def test_multiple_policies_unique_ids(self):
        """Consecutive policies should get distinct IDs."""
        import mcp_tools_v28 as tools
        tools.DEFAULT_MEMORY_DB = self.db_path

        r1 = self._run(
            tools.set_retention_policy("Policy A", "gdpr", 0, "tombstone", ["a"])
        )
        r2 = self._run(
            tools.set_retention_policy("Policy B", "hipaa", 365, "retain", ["b"])
        )
        assert r1["policy_id"] != r2["policy_id"]
