# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Tests for audit database with hash chain tamper detection.
"""
import sqlite3
import tempfile
import os
import sys
import hashlib
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestAuditDB:
    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "audit.db")

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_creation(self):
        from compliance.audit_db import AuditDB
        db = AuditDB(self.db_path)
        assert db is not None

    def test_schema_created(self):
        from compliance.audit_db import AuditDB
        db = AuditDB(self.db_path)
        conn = sqlite3.connect(self.db_path)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        conn.close()
        assert "audit_events" in tables

    def test_log_event(self):
        from compliance.audit_db import AuditDB
        db = AuditDB(self.db_path)
        eid = db.log_event(event_type="memory.created", actor="user", resource_id=1, details={"action": "create"})
        assert isinstance(eid, int)
        assert eid > 0

    def test_hash_chain_first_entry(self):
        """First entry's prev_hash should be a known genesis value."""
        from compliance.audit_db import AuditDB
        db = AuditDB(self.db_path)
        db.log_event("memory.created", actor="user", resource_id=1)
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT prev_hash, entry_hash FROM audit_events WHERE id=1").fetchone()
        conn.close()
        assert row[0] == "genesis"
        assert row[1] is not None and len(row[1]) == 64  # SHA-256 hex

    def test_hash_chain_links(self):
        """Each entry's prev_hash should equal the previous entry's entry_hash."""
        from compliance.audit_db import AuditDB
        db = AuditDB(self.db_path)
        db.log_event("memory.created", actor="user", resource_id=1)
        db.log_event("memory.recalled", actor="agent_a", resource_id=2)
        db.log_event("memory.deleted", actor="user", resource_id=1)
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("SELECT id, prev_hash, entry_hash FROM audit_events ORDER BY id").fetchall()
        conn.close()
        assert rows[1][1] == rows[0][2]  # Entry 2's prev = Entry 1's hash
        assert rows[2][1] == rows[1][2]  # Entry 3's prev = Entry 2's hash

    def test_verify_chain_valid(self):
        """verify_chain returns True for untampered chain."""
        from compliance.audit_db import AuditDB
        db = AuditDB(self.db_path)
        db.log_event("memory.created", actor="user", resource_id=1)
        db.log_event("memory.recalled", actor="agent_a", resource_id=1)
        result = db.verify_chain()
        assert result["valid"] is True
        assert result["entries_checked"] == 2

    def test_verify_chain_detects_tampering(self):
        """verify_chain returns False if an entry was modified."""
        from compliance.audit_db import AuditDB
        db = AuditDB(self.db_path)
        db.log_event("memory.created", actor="user", resource_id=1)
        db.log_event("memory.recalled", actor="agent_a", resource_id=1)
        # Tamper with the first entry
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE audit_events SET actor='hacker' WHERE id=1")
        conn.commit()
        conn.close()
        result = db.verify_chain()
        assert result["valid"] is False

    def test_query_by_type(self):
        from compliance.audit_db import AuditDB
        db = AuditDB(self.db_path)
        db.log_event("memory.created", actor="user", resource_id=1)
        db.log_event("memory.recalled", actor="user", resource_id=1)
        db.log_event("memory.created", actor="user", resource_id=2)
        results = db.query_events(event_type="memory.created")
        assert len(results) == 2

    def test_query_by_actor(self):
        from compliance.audit_db import AuditDB
        db = AuditDB(self.db_path)
        db.log_event("memory.created", actor="user", resource_id=1)
        db.log_event("memory.recalled", actor="agent_a", resource_id=1)
        results = db.query_events(actor="agent_a")
        assert len(results) == 1

    def test_query_by_time_range(self):
        from compliance.audit_db import AuditDB
        db = AuditDB(self.db_path)
        db.log_event("memory.created", actor="user", resource_id=1)
        results = db.query_events(limit=10)
        assert len(results) >= 1
        assert "created_at" in results[0]

    def test_empty_chain_is_valid(self):
        from compliance.audit_db import AuditDB
        db = AuditDB(self.db_path)
        result = db.verify_chain()
        assert result["valid"] is True
        assert result["entries_checked"] == 0
