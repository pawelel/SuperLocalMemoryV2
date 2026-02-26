# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Tests for compliance retention manager.
"""
import sqlite3
import tempfile
import os
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestComplianceRetentionManager:
    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.memory_db_path = os.path.join(self.tmp_dir, "memory.db")
        self.audit_db_path = os.path.join(self.tmp_dir, "audit.db")

        # Create memory.db with test data
        conn = sqlite3.connect(self.memory_db_path)
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
        conn.execute("INSERT INTO memories (content, tags, project_name) VALUES ('user PII data', '[\"gdpr\",\"pii\"]', 'eu-app')")
        conn.execute("INSERT INTO memories (content, tags, project_name) VALUES ('medical record', '[\"hipaa\"]', 'healthcare')")
        conn.execute("INSERT INTO memories (content, tags) VALUES ('general note', '[]')")
        conn.commit()
        conn.close()

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_creation(self):
        from compliance.retention_manager import ComplianceRetentionManager
        mgr = ComplianceRetentionManager(self.memory_db_path, self.audit_db_path)
        assert mgr is not None

    def test_create_gdpr_policy(self):
        from compliance.retention_manager import ComplianceRetentionManager
        mgr = ComplianceRetentionManager(self.memory_db_path, self.audit_db_path)
        pid = mgr.create_retention_rule(
            name="GDPR Right to Erasure",
            framework="gdpr",
            retention_days=0,
            action="tombstone",
            applies_to={"tags": ["gdpr"]},
        )
        assert isinstance(pid, int)

    def test_create_eu_ai_act_policy(self):
        from compliance.retention_manager import ComplianceRetentionManager
        mgr = ComplianceRetentionManager(self.memory_db_path, self.audit_db_path)
        pid = mgr.create_retention_rule(
            name="EU AI Act Audit Retention",
            framework="eu_ai_act",
            retention_days=3650,
            action="retain_audit",
            applies_to={"tags": ["gdpr"]},
        )
        assert pid > 0

    def test_gdpr_erasure_tombstones_memory(self):
        """GDPR erasure request tombstones the memory."""
        from compliance.retention_manager import ComplianceRetentionManager
        mgr = ComplianceRetentionManager(self.memory_db_path, self.audit_db_path)
        result = mgr.execute_erasure_request(memory_id=1, framework="gdpr", requested_by="data_subject")
        assert result["success"] is True
        assert result["action"] == "tombstoned"
        # Verify in DB
        conn = sqlite3.connect(self.memory_db_path)
        row = conn.execute("SELECT lifecycle_state FROM memories WHERE id=1").fetchone()
        conn.close()
        assert row[0] == "tombstoned"

    def test_gdpr_erasure_preserves_audit(self):
        """GDPR erasure logs the action to audit.db."""
        from compliance.retention_manager import ComplianceRetentionManager
        mgr = ComplianceRetentionManager(self.memory_db_path, self.audit_db_path)
        mgr.execute_erasure_request(memory_id=1, framework="gdpr", requested_by="data_subject")
        conn = sqlite3.connect(self.audit_db_path)
        rows = conn.execute("SELECT * FROM audit_events WHERE event_type='retention.erasure'").fetchall()
        conn.close()
        assert len(rows) >= 1

    def test_list_rules(self):
        from compliance.retention_manager import ComplianceRetentionManager
        mgr = ComplianceRetentionManager(self.memory_db_path, self.audit_db_path)
        mgr.create_retention_rule("GDPR", "gdpr", 0, "tombstone", {"tags": ["gdpr"]})
        mgr.create_retention_rule("HIPAA", "hipaa", 2555, "retain", {"tags": ["hipaa"]})
        rules = mgr.list_rules()
        assert len(rules) == 2

    def test_evaluate_memory_against_rules(self):
        from compliance.retention_manager import ComplianceRetentionManager
        mgr = ComplianceRetentionManager(self.memory_db_path, self.audit_db_path)
        mgr.create_retention_rule("HIPAA Retention", "hipaa", 2555, "retain", {"tags": ["hipaa"]})
        result = mgr.evaluate_memory(2)  # Memory 2 has hipaa tag
        assert result is not None
        assert result["rule_name"] == "HIPAA Retention"

    def test_no_rule_match_returns_none(self):
        from compliance.retention_manager import ComplianceRetentionManager
        mgr = ComplianceRetentionManager(self.memory_db_path, self.audit_db_path)
        mgr.create_retention_rule("HIPAA", "hipaa", 2555, "retain", {"tags": ["hipaa"]})
        result = mgr.evaluate_memory(3)  # Memory 3 has no hipaa tag
        assert result is None

    def test_get_compliance_status(self):
        from compliance.retention_manager import ComplianceRetentionManager
        mgr = ComplianceRetentionManager(self.memory_db_path, self.audit_db_path)
        status = mgr.get_compliance_status()
        assert "rules_count" in status
        assert "frameworks" in status
