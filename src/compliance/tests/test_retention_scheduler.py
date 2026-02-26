# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Tests for retention policy background scheduler.
"""
import sqlite3, tempfile, os, sys, json, threading
from datetime import datetime, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

class TestRetentionScheduler:
    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.memory_db = os.path.join(self.tmp_dir, "memory.db")
        self.audit_db = os.path.join(self.tmp_dir, "audit.db")
        conn = sqlite3.connect(self.memory_db)
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
        now = datetime.now()
        # Memory 1: old GDPR data (created 400 days ago)
        conn.execute("INSERT INTO memories (content, tags, created_at, lifecycle_state) VALUES (?, ?, ?, ?)",
            ("old PII data", '["gdpr"]', (now - timedelta(days=400)).isoformat(), "active"))
        # Memory 2: recent data
        conn.execute("INSERT INTO memories (content, tags) VALUES (?, ?)",
            ("fresh data", '[]'))
        # Memory 3: tombstoned (should be checked for final deletion)
        conn.execute("INSERT INTO memories (content, lifecycle_state, created_at) VALUES (?, ?, ?)",
            ("tombstoned data", "tombstoned", (now - timedelta(days=100)).isoformat()))
        conn.commit()
        conn.close()

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_creation(self):
        from compliance.retention_scheduler import RetentionScheduler
        sched = RetentionScheduler(self.memory_db, self.audit_db)
        assert sched is not None

    def test_default_interval(self):
        from compliance.retention_scheduler import RetentionScheduler
        sched = RetentionScheduler(self.memory_db, self.audit_db)
        assert sched.interval_seconds == 86400  # 24 hours

    def test_run_now(self):
        from compliance.retention_scheduler import RetentionScheduler
        sched = RetentionScheduler(self.memory_db, self.audit_db)
        result = sched.run_now()
        assert "timestamp" in result
        assert "actions" in result

    def test_start_and_stop(self):
        from compliance.retention_scheduler import RetentionScheduler
        sched = RetentionScheduler(self.memory_db, self.audit_db, interval_seconds=3600)
        sched.start()
        assert sched.is_running is True
        sched.stop()
        assert sched.is_running is False

    def test_thread_is_daemon(self):
        from compliance.retention_scheduler import RetentionScheduler
        sched = RetentionScheduler(self.memory_db, self.audit_db, interval_seconds=3600)
        sched.start()
        assert sched._timer.daemon is True
        sched.stop()

    def test_manual_trigger_works(self):
        from compliance.retention_scheduler import RetentionScheduler
        sched = RetentionScheduler(self.memory_db, self.audit_db)
        result = sched.run_now()
        assert isinstance(result["actions"], list)

    def test_configurable_interval(self):
        from compliance.retention_scheduler import RetentionScheduler
        sched = RetentionScheduler(self.memory_db, self.audit_db, interval_seconds=7200)
        assert sched.interval_seconds == 7200

    def test_result_structure(self):
        from compliance.retention_scheduler import RetentionScheduler
        sched = RetentionScheduler(self.memory_db, self.audit_db)
        result = sched.run_now()
        assert "timestamp" in result
        assert "actions" in result
        assert "rules_evaluated" in result
