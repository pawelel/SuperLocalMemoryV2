# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Tests for lifecycle state machine transitions.
"""
import sqlite3
import tempfile
import os
import sys
import json
import pytest

# Ensure src/ is importable and takes precedence (matches existing test pattern)
from pathlib import Path
SRC_DIR = Path(__file__).resolve().parent.parent.parent  # src/
_src_str = str(SRC_DIR)
if _src_str not in sys.path:
    sys.path.insert(0, _src_str)


class TestLifecycleStates:
    """Test state definitions and valid transitions."""

    def setup_method(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
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
        conn.execute("""
            INSERT INTO memories (content, importance, lifecycle_state)
            VALUES ('test memory', 5, 'active')
        """)
        conn.commit()
        conn.close()

    def teardown_method(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_valid_states(self):
        from lifecycle.lifecycle_engine import LifecycleEngine
        engine = LifecycleEngine(self.db_path)
        assert set(engine.STATES) == {"active", "warm", "cold", "archived", "tombstoned"}

    def test_valid_transition_active_to_warm(self):
        from lifecycle.lifecycle_engine import LifecycleEngine
        engine = LifecycleEngine(self.db_path)
        assert engine.is_valid_transition("active", "warm") is True

    def test_invalid_transition_active_to_archived(self):
        from lifecycle.lifecycle_engine import LifecycleEngine
        engine = LifecycleEngine(self.db_path)
        assert engine.is_valid_transition("active", "archived") is False

    def test_reactivation_always_valid(self):
        from lifecycle.lifecycle_engine import LifecycleEngine
        engine = LifecycleEngine(self.db_path)
        for state in ["warm", "cold", "archived"]:
            assert engine.is_valid_transition(state, "active") is True

    def test_tombstoned_is_terminal(self):
        from lifecycle.lifecycle_engine import LifecycleEngine
        engine = LifecycleEngine(self.db_path)
        for state in engine.STATES:
            if state != "tombstoned":
                assert engine.is_valid_transition("tombstoned", state) is False

    def test_transition_memory(self):
        from lifecycle.lifecycle_engine import LifecycleEngine
        engine = LifecycleEngine(self.db_path)
        result = engine.transition_memory(1, "warm", reason="no_access_30d")
        assert result["success"] is True
        assert result["from_state"] == "active"
        assert result["to_state"] == "warm"

    def test_transition_updates_db(self):
        from lifecycle.lifecycle_engine import LifecycleEngine
        engine = LifecycleEngine(self.db_path)
        engine.transition_memory(1, "warm", reason="no_access_30d")
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT lifecycle_state FROM memories WHERE id=1").fetchone()
        conn.close()
        assert row[0] == "warm"

    def test_transition_records_history(self):
        from lifecycle.lifecycle_engine import LifecycleEngine
        engine = LifecycleEngine(self.db_path)
        engine.transition_memory(1, "warm", reason="no_access_30d")
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT lifecycle_history FROM memories WHERE id=1").fetchone()
        conn.close()
        history = json.loads(row[0])
        assert len(history) == 1
        assert history[0]["from"] == "active"
        assert history[0]["to"] == "warm"
        assert history[0]["reason"] == "no_access_30d"

    def test_invalid_transition_rejected(self):
        from lifecycle.lifecycle_engine import LifecycleEngine
        engine = LifecycleEngine(self.db_path)
        result = engine.transition_memory(1, "archived", reason="skip")
        assert result["success"] is False
        assert "invalid" in result["error"].lower()

    def test_get_memory_state(self):
        from lifecycle.lifecycle_engine import LifecycleEngine
        engine = LifecycleEngine(self.db_path)
        state = engine.get_memory_state(1)
        assert state == "active"

    def test_get_state_distribution(self):
        from lifecycle.lifecycle_engine import LifecycleEngine
        engine = LifecycleEngine(self.db_path)
        dist = engine.get_state_distribution()
        assert dist["active"] >= 1
        assert dist["warm"] == 0

    def test_reactivation_on_access(self):
        from lifecycle.lifecycle_engine import LifecycleEngine
        engine = LifecycleEngine(self.db_path)
        engine.transition_memory(1, "warm", reason="aged")
        result = engine.reactivate_memory(1, trigger="recall")
        assert result["success"] is True
        assert result["from_state"] == "warm"
        assert result["to_state"] == "active"
