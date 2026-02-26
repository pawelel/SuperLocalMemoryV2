# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Tests for ABAC policy engine.
"""
import tempfile
import os
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestABACEngine:
    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.policy_path = os.path.join(self.tmp_dir, "abac_policies.json")

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _write_policies(self, policies):
        with open(self.policy_path, "w") as f:
            json.dump(policies, f)

    def test_creation_no_policy_file(self):
        """Engine works with no policy file — allow all."""
        from compliance.abac_engine import ABACEngine
        engine = ABACEngine(config_path="/nonexistent/path.json")
        assert engine is not None

    def test_missing_policy_allows_all(self):
        """No policy file → all access allowed (backward compat)."""
        from compliance.abac_engine import ABACEngine
        engine = ABACEngine(config_path="/nonexistent/path.json")
        result = engine.evaluate(subject={"agent_id": "user"}, resource={"access_level": "public"}, action="read")
        assert result["allowed"] is True

    def test_load_policies_from_json(self):
        """Can load policies from JSON file."""
        from compliance.abac_engine import ABACEngine
        self._write_policies([
            {"name": "deny-private", "effect": "deny", "subjects": {"agent_id": "*"}, "resources": {"access_level": "private"}, "actions": ["read"]}
        ])
        engine = ABACEngine(config_path=self.policy_path)
        assert len(engine.policies) == 1

    def test_deny_policy_blocks_access(self):
        """Deny policy prevents access to matching resources."""
        from compliance.abac_engine import ABACEngine
        self._write_policies([
            {"name": "deny-private", "effect": "deny", "subjects": {"agent_id": "*"}, "resources": {"access_level": "private"}, "actions": ["read"]}
        ])
        engine = ABACEngine(config_path=self.policy_path)
        result = engine.evaluate(subject={"agent_id": "agent_a"}, resource={"access_level": "private"}, action="read")
        assert result["allowed"] is False
        assert result["policy_name"] == "deny-private"

    def test_allow_policy_grants_access(self):
        """Allow policy explicitly permits access."""
        from compliance.abac_engine import ABACEngine
        self._write_policies([
            {"name": "allow-admin", "effect": "allow", "subjects": {"agent_id": "admin"}, "resources": {"access_level": "*"}, "actions": ["read", "write", "delete"]}
        ])
        engine = ABACEngine(config_path=self.policy_path)
        result = engine.evaluate(subject={"agent_id": "admin"}, resource={"access_level": "private"}, action="write")
        assert result["allowed"] is True

    def test_subject_matching_specific_agent(self):
        """Policy matches specific agent_id."""
        from compliance.abac_engine import ABACEngine
        self._write_policies([
            {"name": "deny-untrusted", "effect": "deny", "subjects": {"agent_id": "untrusted_bot"}, "resources": {"access_level": "*"}, "actions": ["read"]}
        ])
        engine = ABACEngine(config_path=self.policy_path)
        # untrusted_bot denied
        r1 = engine.evaluate(subject={"agent_id": "untrusted_bot"}, resource={"access_level": "public"}, action="read")
        assert r1["allowed"] is False
        # trusted_agent allowed (no matching deny policy)
        r2 = engine.evaluate(subject={"agent_id": "trusted_agent"}, resource={"access_level": "public"}, action="read")
        assert r2["allowed"] is True

    def test_resource_matching_by_project(self):
        """Policy matches by project name."""
        from compliance.abac_engine import ABACEngine
        self._write_policies([
            {"name": "deny-secret-project", "effect": "deny", "subjects": {"agent_id": "*"}, "resources": {"project": "secret_project"}, "actions": ["read"]}
        ])
        engine = ABACEngine(config_path=self.policy_path)
        r1 = engine.evaluate(subject={"agent_id": "user"}, resource={"project": "secret_project"}, action="read")
        assert r1["allowed"] is False
        r2 = engine.evaluate(subject={"agent_id": "user"}, resource={"project": "public_project"}, action="read")
        assert r2["allowed"] is True

    def test_action_matching(self):
        """Policy only applies to specified actions."""
        from compliance.abac_engine import ABACEngine
        self._write_policies([
            {"name": "deny-delete", "effect": "deny", "subjects": {"agent_id": "*"}, "resources": {"access_level": "*"}, "actions": ["delete"]}
        ])
        engine = ABACEngine(config_path=self.policy_path)
        r1 = engine.evaluate(subject={"agent_id": "user"}, resource={"access_level": "public"}, action="delete")
        assert r1["allowed"] is False
        r2 = engine.evaluate(subject={"agent_id": "user"}, resource={"access_level": "public"}, action="read")
        assert r2["allowed"] is True

    def test_deny_takes_precedence(self):
        """When both allow and deny match, deny wins."""
        from compliance.abac_engine import ABACEngine
        self._write_policies([
            {"name": "allow-all", "effect": "allow", "subjects": {"agent_id": "*"}, "resources": {"access_level": "*"}, "actions": ["read"]},
            {"name": "deny-private", "effect": "deny", "subjects": {"agent_id": "*"}, "resources": {"access_level": "private"}, "actions": ["read"]}
        ])
        engine = ABACEngine(config_path=self.policy_path)
        result = engine.evaluate(subject={"agent_id": "user"}, resource={"access_level": "private"}, action="read")
        assert result["allowed"] is False

    def test_evaluate_returns_reason(self):
        """Evaluation result includes reason."""
        from compliance.abac_engine import ABACEngine
        engine = ABACEngine(config_path="/nonexistent/path.json")
        result = engine.evaluate(subject={"agent_id": "user"}, resource={}, action="read")
        assert "reason" in result
