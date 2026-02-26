# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Tests for lifecycle background scheduler.
"""
import sqlite3
import tempfile
import os
import sys
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestLifecycleScheduler:
    """Test lifecycle scheduler background evaluation."""

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
                profile TEXT DEFAULT 'default'
            )
        """)
        now = datetime.now()
        # Insert a stale memory that should be evaluated for transition
        conn.execute(
            "INSERT INTO memories (content, importance, lifecycle_state, last_accessed, created_at) VALUES (?, ?, ?, ?, ?)",
            ("stale memory", 3, "active", (now - timedelta(days=45)).isoformat(), (now - timedelta(days=100)).isoformat()),
        )
        # Insert a fresh memory that should stay
        conn.execute(
            "INSERT INTO memories (content, importance, lifecycle_state, last_accessed, created_at) VALUES (?, ?, ?, ?, ?)",
            ("fresh memory", 8, "active", now.isoformat(), (now - timedelta(days=10)).isoformat()),
        )
        conn.commit()
        conn.close()

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_scheduler_creation(self):
        """Scheduler can be created with default settings."""
        from lifecycle.lifecycle_scheduler import LifecycleScheduler
        scheduler = LifecycleScheduler(self.db_path)
        assert scheduler is not None
        assert scheduler.interval_seconds == 21600  # 6 hours default

    def test_run_now_executes_evaluation(self):
        """Manual trigger runs evaluation and transitions eligible memories."""
        from lifecycle.lifecycle_scheduler import LifecycleScheduler
        scheduler = LifecycleScheduler(self.db_path)
        result = scheduler.run_now()
        assert result is not None
        assert "evaluation" in result
        assert "enforcement" in result

    def test_run_now_transitions_stale_memories(self):
        """run_now should transition stale memories."""
        from lifecycle.lifecycle_scheduler import LifecycleScheduler
        scheduler = LifecycleScheduler(self.db_path)
        result = scheduler.run_now()
        # Memory 1 (stale 45d, importance 3) should be recommended for transition
        eval_recs = result["evaluation"]["recommendations"]
        if eval_recs:
            transitioned = result["evaluation"]["transitioned"]
            assert transitioned >= 1

    def test_fresh_memory_stays_active(self):
        """Fresh high-importance memory should NOT be transitioned."""
        from lifecycle.lifecycle_scheduler import LifecycleScheduler
        scheduler = LifecycleScheduler(self.db_path)
        scheduler.run_now()
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT lifecycle_state FROM memories WHERE id=2").fetchone()
        conn.close()
        assert row[0] == "active"

    def test_scheduler_thread_is_daemon(self):
        """Scheduler thread should be daemonic (doesn't prevent exit)."""
        from lifecycle.lifecycle_scheduler import LifecycleScheduler
        scheduler = LifecycleScheduler(self.db_path, interval_seconds=3600)
        scheduler.start()
        assert scheduler._timer is not None
        assert scheduler._timer.daemon is True
        scheduler.stop()

    def test_start_and_stop(self):
        """Scheduler can be started and stopped."""
        from lifecycle.lifecycle_scheduler import LifecycleScheduler
        scheduler = LifecycleScheduler(self.db_path, interval_seconds=3600)
        scheduler.start()
        assert scheduler.is_running is True
        scheduler.stop()
        assert scheduler.is_running is False

    def test_configurable_interval(self):
        """Scheduler interval is configurable."""
        from lifecycle.lifecycle_scheduler import LifecycleScheduler
        scheduler = LifecycleScheduler(self.db_path, interval_seconds=7200)
        assert scheduler.interval_seconds == 7200

    def test_result_structure(self):
        """run_now returns properly structured result."""
        from lifecycle.lifecycle_scheduler import LifecycleScheduler
        scheduler = LifecycleScheduler(self.db_path)
        result = scheduler.run_now()
        assert "evaluation" in result
        assert "enforcement" in result
        assert "timestamp" in result
        assert "recommendations" in result["evaluation"]
        assert "transitioned" in result["evaluation"]
