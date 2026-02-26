# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Tests for bounded growth enforcement — memory count limits.
"""
import sqlite3
import tempfile
import os
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestBoundedGrowth:
    """Test bounded growth enforcement and memory scoring."""

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

        # Memory 1: HIGH value — importance 9, accessed today, frequently used
        conn.execute(
            "INSERT INTO memories (content, importance, lifecycle_state, last_accessed, created_at, access_count) VALUES (?, ?, ?, ?, ?, ?)",
            ("high value memory", 9, "active", now.isoformat(), (now - timedelta(days=30)).isoformat(), 20),
        )
        # Memory 2: MEDIUM-HIGH — importance 7, accessed 5d ago
        conn.execute(
            "INSERT INTO memories (content, importance, lifecycle_state, last_accessed, created_at, access_count) VALUES (?, ?, ?, ?, ?, ?)",
            ("medium high memory", 7, "active", (now - timedelta(days=5)).isoformat(), (now - timedelta(days=60)).isoformat(), 10),
        )
        # Memory 3: MEDIUM — importance 5, accessed 10d ago
        conn.execute(
            "INSERT INTO memories (content, importance, lifecycle_state, last_accessed, created_at, access_count) VALUES (?, ?, ?, ?, ?, ?)",
            ("medium memory", 5, "active", (now - timedelta(days=10)).isoformat(), (now - timedelta(days=90)).isoformat(), 5),
        )
        # Memory 4: LOW — importance 3, accessed 20d ago, rarely used
        conn.execute(
            "INSERT INTO memories (content, importance, lifecycle_state, last_accessed, created_at, access_count) VALUES (?, ?, ?, ?, ?, ?)",
            ("low value memory", 3, "active", (now - timedelta(days=20)).isoformat(), (now - timedelta(days=120)).isoformat(), 2),
        )
        # Memory 5: LOWEST — importance 1, accessed 40d ago, never reused
        conn.execute(
            "INSERT INTO memories (content, importance, lifecycle_state, last_accessed, created_at, access_count) VALUES (?, ?, ?, ?, ?, ?)",
            ("lowest value memory", 1, "active", (now - timedelta(days=40)).isoformat(), (now - timedelta(days=150)).isoformat(), 0),
        )
        # Memory 6: Warm state (for warm bounds test) — importance 2, stale
        conn.execute(
            "INSERT INTO memories (content, importance, lifecycle_state, last_accessed, created_at, access_count) VALUES (?, ?, ?, ?, ?, ?)",
            ("warm memory A", 2, "warm", (now - timedelta(days=50)).isoformat(), (now - timedelta(days=200)).isoformat(), 1),
        )
        # Memory 7: Warm state — importance 4
        conn.execute(
            "INSERT INTO memories (content, importance, lifecycle_state, last_accessed, created_at, access_count) VALUES (?, ?, ?, ?, ?, ?)",
            ("warm memory B", 4, "warm", (now - timedelta(days=30)).isoformat(), (now - timedelta(days=100)).isoformat(), 3),
        )
        conn.commit()
        conn.close()

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_no_action_under_limit(self):
        """No transitions when counts are within bounds."""
        from lifecycle.bounded_growth import BoundedGrowthEnforcer
        enforcer = BoundedGrowthEnforcer(self.db_path)
        result = enforcer.enforce_bounds()
        assert result["enforced"] is False
        assert len(result["transitions"]) == 0

    def test_enforce_active_limit(self):
        """When active_count > max_active, excess memories transition to warm."""
        from lifecycle.bounded_growth import BoundedGrowthEnforcer
        config_path = os.path.join(self.tmp_dir, "lifecycle_config.json")
        with open(config_path, "w") as f:
            json.dump({"bounds": {"max_active": 3, "max_warm": 100}}, f)
        enforcer = BoundedGrowthEnforcer(self.db_path, config_path=config_path)
        result = enforcer.enforce_bounds()
        assert result["enforced"] is True
        # 5 active, limit 3 -> 2 should transition
        assert len(result["transitions"]) == 2

    def test_lowest_scoring_evicted_first(self):
        """The lowest-scoring memories should be the ones transitioned."""
        from lifecycle.bounded_growth import BoundedGrowthEnforcer
        config_path = os.path.join(self.tmp_dir, "lifecycle_config.json")
        with open(config_path, "w") as f:
            json.dump({"bounds": {"max_active": 3, "max_warm": 100}}, f)
        enforcer = BoundedGrowthEnforcer(self.db_path, config_path=config_path)
        result = enforcer.enforce_bounds()
        evicted_ids = {t["memory_id"] for t in result["transitions"]}
        # Memory 5 (importance 1, stale 40d) and Memory 4 (importance 3, stale 20d)
        # should be evicted — lowest scores
        assert 5 in evicted_ids
        assert 4 in evicted_ids
        # Top 3 memories (1, 2, 3) should survive
        assert 1 not in evicted_ids
        assert 2 not in evicted_ids
        assert 3 not in evicted_ids

    def test_evicted_memories_now_warm(self):
        """Evicted memories should now be in 'warm' state in the database."""
        from lifecycle.bounded_growth import BoundedGrowthEnforcer
        config_path = os.path.join(self.tmp_dir, "lifecycle_config.json")
        with open(config_path, "w") as f:
            json.dump({"bounds": {"max_active": 3, "max_warm": 100}}, f)
        enforcer = BoundedGrowthEnforcer(self.db_path, config_path=config_path)
        enforcer.enforce_bounds()
        conn = sqlite3.connect(self.db_path)
        row4 = conn.execute("SELECT lifecycle_state FROM memories WHERE id=4").fetchone()
        row5 = conn.execute("SELECT lifecycle_state FROM memories WHERE id=5").fetchone()
        conn.close()
        assert row4[0] == "warm"
        assert row5[0] == "warm"

    def test_enforce_warm_limit(self):
        """When warm_count > max_warm, excess warm memories transition to cold."""
        from lifecycle.bounded_growth import BoundedGrowthEnforcer
        config_path = os.path.join(self.tmp_dir, "lifecycle_config.json")
        with open(config_path, "w") as f:
            json.dump({"bounds": {"max_active": 100, "max_warm": 1}}, f)
        enforcer = BoundedGrowthEnforcer(self.db_path, config_path=config_path)
        result = enforcer.enforce_bounds()
        assert result["enforced"] is True
        # 2 warm (ids 6, 7), limit 1 -> 1 transition
        warm_transitions = [t for t in result["transitions"] if t["from_state"] == "warm"]
        assert len(warm_transitions) == 1
        # Memory 6 (importance 2, stale 50d) should be evicted before Memory 7 (importance 4, stale 30d)
        assert warm_transitions[0]["memory_id"] == 6

    def test_score_memory_importance_matters(self):
        """Higher importance -> higher score, all else equal."""
        from lifecycle.bounded_growth import BoundedGrowthEnforcer
        enforcer = BoundedGrowthEnforcer(self.db_path)
        scores = enforcer.score_all_memories()
        # Memory 1 (importance 9) should score higher than Memory 5 (importance 1)
        score_map = {s["memory_id"]: s["score"] for s in scores}
        assert score_map[1] > score_map[5]

    def test_score_memory_recency_matters(self):
        """More recently accessed -> higher score."""
        from lifecycle.bounded_growth import BoundedGrowthEnforcer
        enforcer = BoundedGrowthEnforcer(self.db_path)
        scores = enforcer.score_all_memories()
        score_map = {s["memory_id"]: s["score"] for s in scores}
        # Memory 1 (accessed today) should score higher than Memory 3 (accessed 10d ago)
        # (both active, Memory 1 also has higher importance, so this should hold)
        assert score_map[1] > score_map[3]

    def test_score_all_returns_all_active(self):
        """score_all_memories returns scores for all memories in given state."""
        from lifecycle.bounded_growth import BoundedGrowthEnforcer
        enforcer = BoundedGrowthEnforcer(self.db_path)
        scores = enforcer.score_all_memories(state="active")
        assert len(scores) == 5  # 5 active memories

    def test_result_structure(self):
        """enforce_bounds returns properly structured result dict."""
        from lifecycle.bounded_growth import BoundedGrowthEnforcer
        enforcer = BoundedGrowthEnforcer(self.db_path)
        result = enforcer.enforce_bounds()
        assert "enforced" in result
        assert "active_count" in result
        assert "active_limit" in result
        assert "warm_count" in result
        assert "warm_limit" in result
        assert "transitions" in result
        assert isinstance(result["transitions"], list)

    def test_default_bounds(self):
        """Default bounds should be max_active=10000, max_warm=5000."""
        from lifecycle.bounded_growth import DEFAULT_BOUNDS
        assert DEFAULT_BOUNDS["max_active"] == 10000
        assert DEFAULT_BOUNDS["max_warm"] == 5000
