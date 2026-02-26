# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Tests for audit logger EventBus listener.
"""
import tempfile, os, sys, sqlite3
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

class TestAuditLogger:
    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.audit_db_path = os.path.join(self.tmp_dir, "audit.db")

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_creation(self):
        from compliance.audit_logger import AuditLogger
        logger = AuditLogger(self.audit_db_path)
        assert logger is not None

    def test_logs_memory_created(self):
        from compliance.audit_logger import AuditLogger
        logger = AuditLogger(self.audit_db_path)
        logger.handle_event({"event_type": "memory.created", "memory_id": 1, "payload": {}, "timestamp": datetime.now().isoformat(), "source_agent": "user"})
        conn = sqlite3.connect(self.audit_db_path)
        rows = conn.execute("SELECT * FROM audit_events WHERE event_type='memory.created'").fetchall()
        conn.close()
        assert len(rows) == 1

    def test_logs_memory_recalled(self):
        from compliance.audit_logger import AuditLogger
        logger = AuditLogger(self.audit_db_path)
        logger.handle_event({"event_type": "memory.recalled", "memory_id": 2, "payload": {"query": "test"}, "timestamp": datetime.now().isoformat(), "source_agent": "agent_a"})
        conn = sqlite3.connect(self.audit_db_path)
        rows = conn.execute("SELECT * FROM audit_events WHERE event_type='memory.recalled'").fetchall()
        conn.close()
        assert len(rows) == 1

    def test_logs_memory_deleted(self):
        from compliance.audit_logger import AuditLogger
        logger = AuditLogger(self.audit_db_path)
        logger.handle_event({"event_type": "memory.deleted", "memory_id": 3, "payload": {}, "timestamp": datetime.now().isoformat(), "source_agent": "user"})
        conn = sqlite3.connect(self.audit_db_path)
        rows = conn.execute("SELECT * FROM audit_events WHERE event_type='memory.deleted'").fetchall()
        conn.close()
        assert len(rows) == 1

    def test_hash_chain_maintained(self):
        """Multiple events maintain hash chain integrity."""
        from compliance.audit_logger import AuditLogger
        logger = AuditLogger(self.audit_db_path)
        for i in range(5):
            logger.handle_event({"event_type": "memory.created", "memory_id": i, "payload": {}, "timestamp": datetime.now().isoformat(), "source_agent": "user"})
        from compliance.audit_db import AuditDB
        db = AuditDB(self.audit_db_path)
        result = db.verify_chain()
        assert result["valid"] is True
        assert result["entries_checked"] == 5

    def test_logs_lifecycle_transitions(self):
        from compliance.audit_logger import AuditLogger
        logger = AuditLogger(self.audit_db_path)
        logger.handle_event({"event_type": "lifecycle.transitioned", "memory_id": 1, "payload": {"from_state": "active", "to_state": "warm"}, "timestamp": datetime.now().isoformat(), "source_agent": "scheduler"})
        conn = sqlite3.connect(self.audit_db_path)
        rows = conn.execute("SELECT * FROM audit_events").fetchall()
        conn.close()
        assert len(rows) == 1

    def test_ignores_unknown_gracefully(self):
        """Unknown event types logged without error."""
        from compliance.audit_logger import AuditLogger
        logger = AuditLogger(self.audit_db_path)
        logger.handle_event({"event_type": "unknown.event", "payload": {}, "timestamp": datetime.now().isoformat(), "source_agent": "test"})
        assert logger.events_logged >= 1

    def test_graceful_on_malformed_event(self):
        """Malformed events don't crash the logger."""
        from compliance.audit_logger import AuditLogger
        logger = AuditLogger(self.audit_db_path)
        logger.handle_event({})  # Empty event
        logger.handle_event({"event_type": "test"})  # Missing fields
        # Should not crash

    def test_register_with_eventbus(self):
        from compliance.audit_logger import AuditLogger
        logger = AuditLogger(self.audit_db_path)
        result = logger.register_with_eventbus()
        assert isinstance(result, bool)

    def test_get_status(self):
        from compliance.audit_logger import AuditLogger
        logger = AuditLogger(self.audit_db_path)
        status = logger.get_status()
        assert "events_logged" in status
        assert "registered" in status
