# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Tests for lifecycle evaluation rules — which memories should transition.
"""
import sqlite3
import tempfile
import os
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestLifecycleEvaluation:
    """Test evaluation rules for memory lifecycle transitions."""

    def setup_method(self):
        # Create temp dir for DB + config isolation
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

        # Memory 1: Active, stale (35d), low importance (5) → should recommend WARM
        conn.execute(
            "INSERT INTO memories (content, importance, lifecycle_state, last_accessed, created_at) VALUES (?, ?, ?, ?, ?)",
            ("stale low importance", 5, "active", (now - timedelta(days=35)).isoformat(), (now - timedelta(days=100)).isoformat()),
        )
        # Memory 2: Active, recent (10d), low importance (5) → should STAY
        conn.execute(
            "INSERT INTO memories (content, importance, lifecycle_state, last_accessed, created_at) VALUES (?, ?, ?, ?, ?)",
            ("recent access", 5, "active", (now - timedelta(days=10)).isoformat(), (now - timedelta(days=100)).isoformat()),
        )
        # Memory 3: Active, stale (35d), HIGH importance (8) → should STAY (importance resists)
        conn.execute(
            "INSERT INTO memories (content, importance, lifecycle_state, last_accessed, created_at) VALUES (?, ?, ?, ?, ?)",
            ("stale high importance", 8, "active", (now - timedelta(days=35)).isoformat(), (now - timedelta(days=100)).isoformat()),
        )
        # Memory 4: Warm, stale (95d), low importance (3) → should recommend COLD
        conn.execute(
            "INSERT INTO memories (content, importance, lifecycle_state, last_accessed, created_at) VALUES (?, ?, ?, ?, ?)",
            ("warm stale", 3, "warm", (now - timedelta(days=95)).isoformat(), (now - timedelta(days=200)).isoformat()),
        )
        # Memory 5: Cold, very stale (200d), importance 5 → should recommend ARCHIVED
        conn.execute(
            "INSERT INTO memories (content, importance, lifecycle_state, last_accessed, created_at) VALUES (?, ?, ?, ?, ?)",
            ("cold very stale", 5, "cold", (now - timedelta(days=200)).isoformat(), (now - timedelta(days=300)).isoformat()),
        )
        # Memory 6: Active, NULL last_accessed, created 40d ago, importance 4 → WARM (uses created_at)
        conn.execute(
            "INSERT INTO memories (content, importance, lifecycle_state, last_accessed, created_at) VALUES (?, ?, ?, ?, ?)",
            ("never accessed", 4, "active", None, (now - timedelta(days=40)).isoformat()),
        )
        conn.commit()
        conn.close()

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_active_to_warm_stale_low_importance(self):
        """Memory 1: stale 35d, importance 5 → recommend ACTIVE→WARM."""
        from lifecycle.lifecycle_evaluator import LifecycleEvaluator
        evaluator = LifecycleEvaluator(self.db_path)
        rec = evaluator.evaluate_single(1)
        assert rec is not None
        assert rec["from_state"] == "active"
        assert rec["to_state"] == "warm"
        assert rec["memory_id"] == 1

    def test_active_stays_recent_access(self):
        """Memory 2: accessed 10d ago → no transition recommended."""
        from lifecycle.lifecycle_evaluator import LifecycleEvaluator
        evaluator = LifecycleEvaluator(self.db_path)
        rec = evaluator.evaluate_single(2)
        assert rec is None

    def test_active_stays_high_importance(self):
        """Memory 3: importance 8 resists transition even when stale."""
        from lifecycle.lifecycle_evaluator import LifecycleEvaluator
        evaluator = LifecycleEvaluator(self.db_path)
        rec = evaluator.evaluate_single(3)
        assert rec is None

    def test_warm_to_cold_stale(self):
        """Memory 4: warm, stale 95d, importance 3 → recommend COLD."""
        from lifecycle.lifecycle_evaluator import LifecycleEvaluator
        evaluator = LifecycleEvaluator(self.db_path)
        rec = evaluator.evaluate_single(4)
        assert rec is not None
        assert rec["from_state"] == "warm"
        assert rec["to_state"] == "cold"

    def test_cold_to_archived(self):
        """Memory 5: cold, stale 200d → recommend ARCHIVED."""
        from lifecycle.lifecycle_evaluator import LifecycleEvaluator
        evaluator = LifecycleEvaluator(self.db_path)
        rec = evaluator.evaluate_single(5)
        assert rec is not None
        assert rec["from_state"] == "cold"
        assert rec["to_state"] == "archived"

    def test_never_accessed_uses_created_at(self):
        """Memory 6: NULL last_accessed, created 40d ago → recommend WARM."""
        from lifecycle.lifecycle_evaluator import LifecycleEvaluator
        evaluator = LifecycleEvaluator(self.db_path)
        rec = evaluator.evaluate_single(6)
        assert rec is not None
        assert rec["to_state"] == "warm"

    def test_retention_override_skips_memory(self):
        """Memory 1 should be skipped when in retention_overrides set."""
        from lifecycle.lifecycle_evaluator import LifecycleEvaluator
        evaluator = LifecycleEvaluator(self.db_path)
        rec = evaluator.evaluate_single(1, retention_overrides={1})
        assert rec is None

    def test_evaluate_memories_returns_recommendations(self):
        """Full scan should return list with recommendations for eligible memories."""
        from lifecycle.lifecycle_evaluator import LifecycleEvaluator
        evaluator = LifecycleEvaluator(self.db_path)
        recs = evaluator.evaluate_memories()
        # Should recommend: Memory 1 (active→warm), 4 (warm→cold), 5 (cold→archived), 6 (active→warm)
        assert isinstance(recs, list)
        assert len(recs) >= 3  # At least memories 1, 4, 5
        rec_ids = {r["memory_id"] for r in recs}
        assert 1 in rec_ids  # stale active
        assert 4 in rec_ids  # stale warm
        assert 5 in rec_ids  # stale cold

    def test_evaluate_memories_excludes_retained(self):
        """evaluate_memories with retention_overrides skips those memory IDs."""
        from lifecycle.lifecycle_evaluator import LifecycleEvaluator
        evaluator = LifecycleEvaluator(self.db_path)
        recs = evaluator.evaluate_memories(retention_overrides={1, 4})
        rec_ids = {r["memory_id"] for r in recs}
        assert 1 not in rec_ids
        assert 4 not in rec_ids
        assert 5 in rec_ids  # cold→archived not overridden

    def test_custom_config_thresholds(self):
        """Custom config should override default thresholds."""
        from lifecycle.lifecycle_evaluator import LifecycleEvaluator
        # Write custom config: raise active_to_warm threshold to 50 days
        config_path = os.path.join(self.tmp_dir, "lifecycle_config.json")
        with open(config_path, "w") as f:
            json.dump({
                "active_to_warm": {"no_access_days": 50, "max_importance": 6}
            }, f)
        evaluator = LifecycleEvaluator(self.db_path, config_path=config_path)
        # Memory 1 is stale 35d — below new 50d threshold → no recommendation
        rec = evaluator.evaluate_single(1)
        assert rec is None

    def test_evaluate_single_nonexistent_memory(self):
        """Evaluating a nonexistent memory returns None."""
        from lifecycle.lifecycle_evaluator import LifecycleEvaluator
        evaluator = LifecycleEvaluator(self.db_path)
        rec = evaluator.evaluate_single(999)
        assert rec is None
