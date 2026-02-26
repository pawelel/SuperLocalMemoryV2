# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Tests for retention policy management.
"""
import sqlite3
import tempfile
import os
import sys
import json
from pathlib import Path

# Ensure src/ is importable and takes precedence (matches existing test pattern)
SRC_DIR = Path(__file__).resolve().parent.parent.parent  # src/
_src_str = str(SRC_DIR)
if _src_str not in sys.path:
    sys.path.insert(0, _src_str)


class TestRetentionPolicy:
    """Test retention policy loading, evaluation, and enforcement."""

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "test.db")
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                importance INTEGER DEFAULT 5,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_accessed TIMESTAMP,
                access_count INTEGER DEFAULT 0,
                lifecycle_state TEXT DEFAULT 'active',
                lifecycle_updated_at TIMESTAMP,
                lifecycle_history TEXT DEFAULT '[]',
                access_level TEXT DEFAULT 'public',
                profile TEXT DEFAULT 'default',
                tags TEXT DEFAULT '[]',
                project_name TEXT
            )
        """)
        conn.execute("INSERT INTO memories (content, tags, project_name) VALUES ('general memory', '[]', 'myproject')")
        conn.execute("INSERT INTO memories (content, tags, project_name) VALUES ('medical record', '[\"hipaa\"]', 'healthcare')")
        conn.execute("INSERT INTO memories (content, tags, project_name) VALUES ('user PII data', '[\"gdpr\",\"pii\"]', 'eu-app')")
        conn.commit()
        conn.close()

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_create_policy(self):
        """Can create a retention policy programmatically."""
        from lifecycle.retention_policy import RetentionPolicyManager
        mgr = RetentionPolicyManager(self.db_path)
        policy_id = mgr.create_policy(
            name="GDPR Erasure",
            retention_days=0,
            framework="gdpr",
            action="tombstone",
            applies_to={"tags": ["gdpr"]},
        )
        assert isinstance(policy_id, int)
        assert policy_id > 0

    def test_list_policies(self):
        """Can list all policies."""
        from lifecycle.retention_policy import RetentionPolicyManager
        mgr = RetentionPolicyManager(self.db_path)
        mgr.create_policy(name="Policy A", retention_days=30, framework="internal", action="archive", applies_to={})
        mgr.create_policy(name="Policy B", retention_days=365, framework="hipaa", action="retain", applies_to={})
        policies = mgr.list_policies()
        assert len(policies) == 2
        names = {p["name"] for p in policies}
        assert "Policy A" in names
        assert "Policy B" in names

    def test_evaluate_memory_matching_tag(self):
        """Policy with tag filter matches memories with that tag."""
        from lifecycle.retention_policy import RetentionPolicyManager
        mgr = RetentionPolicyManager(self.db_path)
        mgr.create_policy(
            name="HIPAA Retention",
            retention_days=2555,  # ~7 years
            framework="hipaa",
            action="retain",
            applies_to={"tags": ["hipaa"]},
        )
        result = mgr.evaluate_memory(2)  # Memory 2 has hipaa tag
        assert result is not None
        assert result["policy_name"] == "HIPAA Retention"
        assert result["action"] == "retain"

    def test_evaluate_memory_no_match(self):
        """Memory without matching tags returns None."""
        from lifecycle.retention_policy import RetentionPolicyManager
        mgr = RetentionPolicyManager(self.db_path)
        mgr.create_policy(
            name="HIPAA Retention",
            retention_days=2555,
            framework="hipaa",
            action="retain",
            applies_to={"tags": ["hipaa"]},
        )
        result = mgr.evaluate_memory(1)  # Memory 1 has no hipaa tag
        assert result is None

    def test_gdpr_erasure_policy(self):
        """GDPR erasure: retention_days=0, action=tombstone."""
        from lifecycle.retention_policy import RetentionPolicyManager
        mgr = RetentionPolicyManager(self.db_path)
        mgr.create_policy(
            name="GDPR Right to Erasure",
            retention_days=0,
            framework="gdpr",
            action="tombstone",
            applies_to={"tags": ["gdpr"]},
        )
        result = mgr.evaluate_memory(3)  # Memory 3 has gdpr tag
        assert result is not None
        assert result["action"] == "tombstone"

    def test_strictest_policy_wins(self):
        """When multiple policies match, the strictest (shortest retention) wins."""
        from lifecycle.retention_policy import RetentionPolicyManager
        mgr = RetentionPolicyManager(self.db_path)
        mgr.create_policy(name="Lenient", retention_days=365, framework="internal", action="archive", applies_to={"tags": ["gdpr"]})
        mgr.create_policy(name="Strict", retention_days=0, framework="gdpr", action="tombstone", applies_to={"tags": ["gdpr"]})
        result = mgr.evaluate_memory(3)
        assert result["policy_name"] == "Strict"
        assert result["action"] == "tombstone"

    def test_load_policies_from_json(self):
        """Can load policies from a JSON file."""
        from lifecycle.retention_policy import RetentionPolicyManager
        mgr = RetentionPolicyManager(self.db_path)
        policy_file = os.path.join(self.tmp_dir, "policies.json")
        with open(policy_file, "w") as f:
            json.dump([
                {"name": "EU AI Act", "retention_days": 3650, "framework": "eu_ai_act", "action": "retain", "applies_to": {"project_name": "eu-app"}},
            ], f)
        count = mgr.load_policies(policy_file)
        assert count == 1
        policies = mgr.list_policies()
        assert len(policies) == 1

    def test_missing_policy_file_no_error(self):
        """Missing policy file returns 0 loaded, no crash."""
        from lifecycle.retention_policy import RetentionPolicyManager
        mgr = RetentionPolicyManager(self.db_path)
        count = mgr.load_policies("/nonexistent/path/policies.json")
        assert count == 0

    def test_get_protected_memory_ids(self):
        """get_protected_memory_ids returns set of IDs protected by retention policies."""
        from lifecycle.retention_policy import RetentionPolicyManager
        mgr = RetentionPolicyManager(self.db_path)
        mgr.create_policy(name="Retain HIPAA", retention_days=2555, framework="hipaa", action="retain", applies_to={"tags": ["hipaa"]})
        protected = mgr.get_protected_memory_ids()
        assert 2 in protected  # Memory 2 has hipaa tag
        assert 1 not in protected  # Memory 1 has no matching tags
