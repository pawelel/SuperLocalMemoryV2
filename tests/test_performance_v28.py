# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Performance regression tests for v2.8 — ensure new features don't slow core operations.
"""
import sqlite3
import tempfile
import time
import os
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR))
sys.path.insert(0, str(REPO_DIR / "src"))


class TestPerformanceV28:
    """Performance benchmarks with pass/fail thresholds."""

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "memory.db")
        self.learning_db = os.path.join(self.tmp_dir, "learning.db")
        self.audit_db = os.path.join(self.tmp_dir, "audit.db")
        # Create 1000 test memories
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
                summary TEXT,
                project_name TEXT
            )
        """)
        now = datetime.now()
        for i in range(1000):
            conn.execute(
                "INSERT INTO memories (content, importance, lifecycle_state, last_accessed, created_at) VALUES (?, ?, ?, ?, ?)",
                (f"Memory about topic_{i % 100} detail_{i}", (i % 10) + 1, "active",
                 (now - timedelta(days=i % 60)).isoformat(), (now - timedelta(days=i)).isoformat()),
            )
        conn.commit()
        conn.close()

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_lifecycle_evaluation_under_500ms(self):
        """Lifecycle evaluation for 1000 memories must complete in <500ms."""
        from lifecycle.lifecycle_evaluator import LifecycleEvaluator
        evaluator = LifecycleEvaluator(self.db_path)
        start = time.perf_counter()
        recs = evaluator.evaluate_memories()
        elapsed = time.perf_counter() - start
        assert elapsed < 0.5, f"Lifecycle evaluation took {elapsed:.3f}s (limit: 0.5s)"

    def test_bounded_growth_under_1s(self):
        """Bounded growth enforcement for 1000 memories must complete in <1s."""
        from lifecycle.bounded_growth import BoundedGrowthEnforcer
        config_path = os.path.join(self.tmp_dir, "lc.json")
        with open(config_path, "w") as f:
            json.dump({"bounds": {"max_active": 500, "max_warm": 250}}, f)
        enforcer = BoundedGrowthEnforcer(self.db_path, config_path=config_path)
        start = time.perf_counter()
        enforcer.enforce_bounds()
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0, f"Bounded growth took {elapsed:.3f}s (limit: 1.0s)"

    def test_audit_event_under_10ms(self):
        """Single audit event insertion must complete in <10ms avg."""
        from compliance.audit_db import AuditDB
        db = AuditDB(self.audit_db)
        times = []
        for i in range(100):
            start = time.perf_counter()
            db.log_event("memory.created", actor="user", resource_id=i)
            times.append(time.perf_counter() - start)
        avg_ms = sum(times) / len(times) * 1000
        p99_ms = sorted(times)[98] * 1000
        assert avg_ms < 10, f"Avg audit insert: {avg_ms:.2f}ms (limit: 10ms)"

    def test_abac_evaluation_under_1ms(self):
        """ABAC policy check must complete in <1ms."""
        from compliance.abac_engine import ABACEngine
        policy_path = os.path.join(self.tmp_dir, "policies.json")
        with open(policy_path, "w") as f:
            json.dump([
                {"name": "allow-all", "effect": "allow", "subjects": {"agent_id": "*"}, "resources": {"access_level": "*"}, "actions": ["read"]},
                {"name": "deny-private", "effect": "deny", "subjects": {"agent_id": "bot"}, "resources": {"access_level": "private"}, "actions": ["read"]},
            ], f)
        engine = ABACEngine(config_path=policy_path)
        start = time.perf_counter()
        for _ in range(1000):
            engine.evaluate(subject={"agent_id": "user"}, resource={"access_level": "public"}, action="read")
        elapsed = (time.perf_counter() - start) / 1000 * 1000  # ms per eval
        assert elapsed < 1, f"ABAC eval: {elapsed:.3f}ms (limit: 1ms)"

    def test_outcome_tracking_under_10ms(self):
        """Outcome recording must complete in <10ms per outcome."""
        from behavioral.outcome_tracker import OutcomeTracker
        tracker = OutcomeTracker(self.learning_db)
        start = time.perf_counter()
        for i in range(100):
            tracker.record_outcome([i + 1], "success", project="perf_test")
        elapsed = (time.perf_counter() - start) / 100 * 1000
        assert elapsed < 10, f"Outcome recording: {elapsed:.2f}ms (limit: 10ms)"

    def test_pattern_extraction_under_1s(self):
        """Pattern extraction for 100 outcomes must complete in <1s."""
        from behavioral.outcome_tracker import OutcomeTracker
        from behavioral.behavioral_patterns import BehavioralPatternExtractor
        tracker = OutcomeTracker(self.learning_db)
        for i in range(100):
            tracker.record_outcome([i % 20 + 1], "success" if i % 3 != 0 else "failure", project="perf_project")
        extractor = BehavioralPatternExtractor(self.learning_db)
        start = time.perf_counter()
        patterns = extractor.extract_patterns()
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0, f"Pattern extraction: {elapsed:.3f}s (limit: 1.0s)"

    def test_audit_chain_verify_under_1s(self):
        """Chain verification for 100 events must complete in <1s."""
        from compliance.audit_db import AuditDB
        db = AuditDB(self.audit_db)
        for i in range(100):
            db.log_event("memory.created", actor="user", resource_id=i)
        start = time.perf_counter()
        result = db.verify_chain()
        elapsed = time.perf_counter() - start
        assert result["valid"] is True
        assert elapsed < 1.0, f"Chain verify: {elapsed:.3f}s (limit: 1.0s)"
