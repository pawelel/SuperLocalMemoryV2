# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Tests for ABAC enforcement via MCP tool integration.
"""
import tempfile
import os
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestABACMCPIntegration:
    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "memory.db")

    def teardown_method(self):
        import shutil

        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_middleware_creation(self):
        from compliance.abac_middleware import ABACMiddleware

        mw = ABACMiddleware(self.db_path)
        assert mw is not None

    def test_check_read_access_default_allow(self):
        """Default (no policies) allows all reads."""
        from compliance.abac_middleware import ABACMiddleware

        mw = ABACMiddleware(self.db_path)
        result = mw.check_access(
            agent_id="any_agent",
            action="read",
            resource={"access_level": "public"},
        )
        assert result["allowed"] is True

    def test_check_write_access_default_allow(self):
        from compliance.abac_middleware import ABACMiddleware

        mw = ABACMiddleware(self.db_path)
        result = mw.check_access(
            agent_id="any_agent", action="write", resource={}
        )
        assert result["allowed"] is True

    def test_check_access_with_deny_policy(self):
        """Deny policy blocks access when enforced."""
        from compliance.abac_middleware import ABACMiddleware

        policy_path = os.path.join(self.tmp_dir, "abac_policies.json")
        with open(policy_path, "w") as f:
            json.dump(
                [
                    {
                        "name": "deny-bots",
                        "effect": "deny",
                        "subjects": {"agent_id": "untrusted_bot"},
                        "resources": {"access_level": "*"},
                        "actions": ["read", "write"],
                    }
                ],
                f,
            )
        mw = ABACMiddleware(self.db_path, policy_path=policy_path)
        result = mw.check_access(
            agent_id="untrusted_bot",
            action="read",
            resource={"access_level": "public"},
        )
        assert result["allowed"] is False

    def test_denied_access_logged(self):
        """Denied access is recorded for audit trail."""
        from compliance.abac_middleware import ABACMiddleware

        policy_path = os.path.join(self.tmp_dir, "abac_policies.json")
        with open(policy_path, "w") as f:
            json.dump(
                [
                    {
                        "name": "deny-all-write",
                        "effect": "deny",
                        "subjects": {"agent_id": "*"},
                        "resources": {"access_level": "*"},
                        "actions": ["write"],
                    }
                ],
                f,
            )
        mw = ABACMiddleware(self.db_path, policy_path=policy_path)
        mw.check_access(agent_id="user", action="write", resource={})
        assert mw.denied_count >= 1

    def test_build_agent_context(self):
        """build_agent_context creates proper context dict for store."""
        from compliance.abac_middleware import ABACMiddleware

        mw = ABACMiddleware(self.db_path)
        ctx = mw.build_agent_context(agent_id="claude_agent", protocol="mcp")
        assert ctx["agent_id"] == "claude_agent"
        assert ctx["protocol"] == "mcp"

    def test_graceful_when_compliance_unavailable(self):
        """Middleware works even if ABACEngine import fails."""
        from compliance.abac_middleware import ABACMiddleware

        mw = ABACMiddleware(
            self.db_path, policy_path="/nonexistent/path.json"
        )
        result = mw.check_access(
            agent_id="user", action="read", resource={}
        )
        assert result["allowed"] is True
