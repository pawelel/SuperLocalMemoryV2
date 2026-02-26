# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Tests for report_outcome MCP tool handler.

Validates the MCP wrapper around OutcomeTracker — tests success/failure/partial
outcomes, context handling, and invalid outcome rejection.
"""
import asyncio
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure src/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestMCPReportOutcome:
    """Tests for the report_outcome tool handler."""

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "learning.db")

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _run(self, coro):
        """Helper to run async functions synchronously."""
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_report_success_outcome(self):
        """Reporting a 'success' outcome should return success=True and an outcome_id."""
        import mcp_tools_v28 as tools
        tools.DEFAULT_LEARNING_DB = self.db_path

        result = self._run(tools.report_outcome([1, 2], "success"))
        assert result["success"] is True
        assert isinstance(result["outcome_id"], int)
        assert result["outcome_id"] > 0
        assert result["outcome"] == "success"
        assert result["memory_ids"] == [1, 2]

    def test_report_failure_outcome(self):
        """Reporting a 'failure' outcome should succeed."""
        import mcp_tools_v28 as tools
        tools.DEFAULT_LEARNING_DB = self.db_path

        result = self._run(tools.report_outcome([5], "failure"))
        assert result["success"] is True
        assert result["outcome"] == "failure"

    def test_report_partial_outcome(self):
        """Reporting a 'partial' outcome should succeed."""
        import mcp_tools_v28 as tools
        tools.DEFAULT_LEARNING_DB = self.db_path

        result = self._run(tools.report_outcome([3], "partial"))
        assert result["success"] is True
        assert result["outcome"] == "partial"

    def test_report_invalid_outcome(self):
        """An invalid outcome label should return success=False."""
        import mcp_tools_v28 as tools
        tools.DEFAULT_LEARNING_DB = self.db_path

        result = self._run(tools.report_outcome([1], "invalid"))
        assert result["success"] is False
        assert "Invalid outcome" in result["error"]

    def test_report_with_context_json(self):
        """Context passed as JSON string should be accepted."""
        import mcp_tools_v28 as tools
        tools.DEFAULT_LEARNING_DB = self.db_path

        result = self._run(
            tools.report_outcome(
                [1], "partial", context='{"note": "worked partially"}'
            )
        )
        assert result["success"] is True

    def test_report_with_action_type(self):
        """Custom action_type should be accepted."""
        import mcp_tools_v28 as tools
        tools.DEFAULT_LEARNING_DB = self.db_path

        result = self._run(
            tools.report_outcome(
                [1, 2, 3], "success", action_type="code_written"
            )
        )
        assert result["success"] is True

    def test_report_with_agent_and_project(self):
        """agent_id and project parameters should be forwarded."""
        import mcp_tools_v28 as tools
        tools.DEFAULT_LEARNING_DB = self.db_path

        result = self._run(
            tools.report_outcome(
                [1], "success", agent_id="agent_a", project="slm-v28"
            )
        )
        assert result["success"] is True

    def test_multiple_outcomes_unique_ids(self):
        """Consecutive outcomes should get distinct IDs."""
        import mcp_tools_v28 as tools
        tools.DEFAULT_LEARNING_DB = self.db_path

        r1 = self._run(tools.report_outcome([1], "success"))
        r2 = self._run(tools.report_outcome([2], "failure"))
        assert r1["outcome_id"] != r2["outcome_id"]
