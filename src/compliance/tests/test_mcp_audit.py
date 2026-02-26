# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Tests for audit_trail MCP tool handler.

Validates the MCP wrapper around AuditDB — tests empty trail, event logging,
event_type and actor filtering, and hash chain verification.
"""
import asyncio
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestMCPAuditTrail:
    """Tests for the audit_trail tool handler."""

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "audit.db")

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_empty_trail(self):
        """Fresh audit DB should return count=0."""
        import mcp_tools_v28 as tools
        tools.DEFAULT_AUDIT_DB = self.db_path

        result = self._run(tools.audit_trail())
        assert result["success"] is True
        assert result["count"] == 0
        assert result["events"] == []

    def test_verify_empty_chain(self):
        """Hash chain verification on empty DB should be valid."""
        import mcp_tools_v28 as tools
        tools.DEFAULT_AUDIT_DB = self.db_path

        result = self._run(tools.audit_trail(verify_chain=True))
        assert result["success"] is True
        assert result["chain_valid"] is True
        assert result["chain_entries"] == 0

    def test_query_with_events(self):
        """After logging events, query should return them."""
        from compliance.audit_db import AuditDB

        db = AuditDB(self.db_path)
        db.log_event("memory.created", actor="user", resource_id=1)
        db.log_event("memory.recalled", actor="agent_a", resource_id=1)
        db.log_event("memory.created", actor="user", resource_id=2)

        import mcp_tools_v28 as tools
        tools.DEFAULT_AUDIT_DB = self.db_path

        result = self._run(tools.audit_trail())
        assert result["success"] is True
        assert result["count"] == 3

    def test_filter_by_event_type(self):
        """Filtering by event_type should narrow results."""
        from compliance.audit_db import AuditDB

        db = AuditDB(self.db_path)
        db.log_event("memory.created", actor="user", resource_id=1)
        db.log_event("memory.recalled", actor="agent_a", resource_id=1)

        import mcp_tools_v28 as tools
        tools.DEFAULT_AUDIT_DB = self.db_path

        result = self._run(tools.audit_trail(event_type="memory.created"))
        assert result["count"] == 1
        assert result["events"][0]["event_type"] == "memory.created"

    def test_filter_by_actor(self):
        """Filtering by actor should narrow results."""
        from compliance.audit_db import AuditDB

        db = AuditDB(self.db_path)
        db.log_event("memory.created", actor="user", resource_id=1)
        db.log_event("memory.recalled", actor="agent_a", resource_id=1)

        import mcp_tools_v28 as tools
        tools.DEFAULT_AUDIT_DB = self.db_path

        result = self._run(tools.audit_trail(actor="agent_a"))
        assert result["count"] == 1
        assert result["events"][0]["actor"] == "agent_a"

    def test_verify_chain_with_events(self):
        """Hash chain with events should verify successfully."""
        from compliance.audit_db import AuditDB

        db = AuditDB(self.db_path)
        db.log_event("memory.created", actor="user", resource_id=1)
        db.log_event("memory.recalled", actor="user", resource_id=1)
        db.log_event("memory.updated", actor="user", resource_id=1)

        import mcp_tools_v28 as tools
        tools.DEFAULT_AUDIT_DB = self.db_path

        result = self._run(tools.audit_trail(verify_chain=True))
        assert result["success"] is True
        assert result["chain_valid"] is True
        assert result["chain_entries"] == 3

    def test_limit_parameter(self):
        """Limit parameter should cap returned events."""
        from compliance.audit_db import AuditDB

        db = AuditDB(self.db_path)
        for i in range(10):
            db.log_event("memory.created", actor="user", resource_id=i)

        import mcp_tools_v28 as tools
        tools.DEFAULT_AUDIT_DB = self.db_path

        result = self._run(tools.audit_trail(limit=3))
        assert result["count"] == 3
