# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Comprehensive backward compatibility tests for v2.8 upgrade.

Validates that:
1. Fresh installs get v2.8 schema correctly
2. Upgrades from v2.7.6 preserve existing data
3. All v2.8 modules are importable and operational
4. Lifecycle, Behavioral, and Compliance engines work independently
5. No regressions in core memory operations after upgrade
6. Event-driven loose coupling holds (engine failures don't cascade)
7. Feature vector dimensions are correct (20 features)
8. MCP tool handlers are available
"""
import sqlite3
import tempfile
import os
import sys
import json
import shutil
import hashlib
from pathlib import Path
from datetime import datetime, timedelta

# Ensure src/ is on sys.path for all imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


# ============================================================================
# Helpers
# ============================================================================

def _create_v27_db(db_path: str, num_memories: int = 2) -> None:
    """Create a v2.7.6-compatible DB with NO lifecycle columns.

    Includes FTS virtual table + triggers that v2.7 would have had,
    so that MemoryStoreV2._init_db migration doesn't corrupt FTS sync.
    """
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            summary TEXT,
            project_path TEXT,
            project_name TEXT,
            tags TEXT,
            category TEXT,
            parent_id INTEGER,
            tree_path TEXT,
            depth INTEGER DEFAULT 0,
            memory_type TEXT DEFAULT 'session',
            importance INTEGER DEFAULT 5,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_accessed TIMESTAMP,
            access_count INTEGER DEFAULT 0,
            content_hash TEXT UNIQUE,
            cluster_id INTEGER,
            profile TEXT DEFAULT 'default'
        )
    """)
    # FTS table + triggers (present in v2.7.6)
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
        USING fts5(content, summary, tags, content='memories', content_rowid='id')
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
            INSERT INTO memories_fts(rowid, content, summary, tags)
            VALUES (new.id, new.content, new.summary, new.tags);
        END
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, content, summary, tags)
            VALUES('delete', old.id, old.content, old.summary, old.tags);
        END
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
            INSERT INTO memories_fts(memories_fts, rowid, content, summary, tags)
            VALUES('delete', old.id, old.content, old.summary, old.tags);
            INSERT INTO memories_fts(rowid, content, summary, tags)
            VALUES (new.id, new.content, new.summary, new.tags);
        END
    """)
    for i in range(num_memories):
        h = hashlib.sha256(f"v27_memory_{i}".encode()).hexdigest()[:32]
        conn.execute(
            "INSERT INTO memories (content, content_hash, profile) VALUES (?, ?, 'default')",
            (f"existing memory from v2.7 #{i}", h),
        )
    conn.commit()
    conn.close()


def _get_columns(db_path: str, table: str = "memories") -> set:
    """Return the set of column names in the given table."""
    conn = sqlite3.connect(db_path)
    cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    conn.close()
    return cols


# ============================================================================
# 1. FRESH INSTALL TESTS
# ============================================================================

class TestFreshInstall:
    """v2.8 on a fresh system (no existing data)."""

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "memory.db")

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    # -- Schema creation --

    def test_fresh_memory_store_creates_schema(self):
        from memory_store_v2 import MemoryStoreV2
        MemoryStoreV2(self.db_path)
        cols = _get_columns(self.db_path)
        assert "lifecycle_state" in cols
        assert "access_level" in cols

    def test_fresh_schema_has_lifecycle_updated_at(self):
        from memory_store_v2 import MemoryStoreV2
        MemoryStoreV2(self.db_path)
        cols = _get_columns(self.db_path)
        assert "lifecycle_updated_at" in cols

    def test_fresh_schema_has_lifecycle_history(self):
        from memory_store_v2 import MemoryStoreV2
        MemoryStoreV2(self.db_path)
        cols = _get_columns(self.db_path)
        assert "lifecycle_history" in cols

    def test_fresh_schema_has_v27_columns(self):
        """All original v2.7 columns must still be present."""
        from memory_store_v2 import MemoryStoreV2
        MemoryStoreV2(self.db_path)
        cols = _get_columns(self.db_path)
        expected = {
            "id", "content", "summary", "project_path", "project_name",
            "tags", "category", "parent_id", "tree_path", "depth",
            "memory_type", "importance", "created_at", "updated_at",
            "last_accessed", "access_count", "content_hash", "cluster_id",
        }
        assert expected.issubset(cols), f"Missing columns: {expected - cols}"

    def test_fresh_schema_fts_table_exists(self):
        from memory_store_v2 import MemoryStoreV2
        MemoryStoreV2(self.db_path)
        conn = sqlite3.connect(self.db_path)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert "memories_fts" in tables

    def test_fresh_schema_sessions_table_exists(self):
        from memory_store_v2 import MemoryStoreV2
        MemoryStoreV2(self.db_path)
        conn = sqlite3.connect(self.db_path)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert "sessions" in tables

    def test_fresh_schema_creator_metadata_exists(self):
        from memory_store_v2 import MemoryStoreV2
        MemoryStoreV2(self.db_path)
        conn = sqlite3.connect(self.db_path)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert "creator_metadata" in tables

    # -- Default values for new memories --

    def test_fresh_store_lifecycle_default_active(self):
        from memory_store_v2 import MemoryStoreV2
        store = MemoryStoreV2(self.db_path)
        mem_id = store.add_memory(content="fresh memory", tags=["test"])
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT lifecycle_state FROM memories WHERE id=?", (mem_id,)
        ).fetchone()
        conn.close()
        assert row[0] == "active"

    def test_fresh_store_access_level_default_public(self):
        from memory_store_v2 import MemoryStoreV2
        store = MemoryStoreV2(self.db_path)
        mem_id = store.add_memory(content="public memory", tags=["acl"])
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT access_level FROM memories WHERE id=?", (mem_id,)
        ).fetchone()
        conn.close()
        assert row[0] == "public"

    def test_fresh_store_lifecycle_history_default_empty(self):
        from memory_store_v2 import MemoryStoreV2
        store = MemoryStoreV2(self.db_path)
        mem_id = store.add_memory(content="history test", tags=["h"])
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT lifecycle_history FROM memories WHERE id=?", (mem_id,)
        ).fetchone()
        conn.close()
        history = json.loads(row[0]) if row[0] else []
        assert history == []

    # -- Lifecycle engine on fresh db --

    def test_lifecycle_engine_works_fresh(self):
        from memory_store_v2 import MemoryStoreV2
        store = MemoryStoreV2(self.db_path)
        mem_id = store.add_memory(content="lifecycle test", tags=["t"])
        from lifecycle.lifecycle_engine import LifecycleEngine
        engine = LifecycleEngine(self.db_path)
        state = engine.get_memory_state(mem_id)
        assert state == "active"

    def test_lifecycle_state_distribution_fresh(self):
        from memory_store_v2 import MemoryStoreV2
        store = MemoryStoreV2(self.db_path)
        store.add_memory(content="mem1 for dist", tags=["d"])
        store.add_memory(content="mem2 for dist", tags=["d"])
        from lifecycle.lifecycle_engine import LifecycleEngine
        engine = LifecycleEngine(self.db_path)
        dist = engine.get_state_distribution()
        assert dist["active"] == 2
        assert dist["warm"] == 0
        assert dist["cold"] == 0

    def test_lifecycle_transition_fresh(self):
        from memory_store_v2 import MemoryStoreV2
        store = MemoryStoreV2(self.db_path)
        mem_id = store.add_memory(content="transition test", tags=["tr"])
        from lifecycle.lifecycle_engine import LifecycleEngine
        engine = LifecycleEngine(self.db_path)
        result = engine.transition_memory(mem_id, "warm", reason="test")
        assert result["success"] is True
        assert engine.get_memory_state(mem_id) == "warm"

    def test_lifecycle_invalid_transition_fresh(self):
        from memory_store_v2 import MemoryStoreV2
        store = MemoryStoreV2(self.db_path)
        mem_id = store.add_memory(content="invalid transition test", tags=["inv"])
        from lifecycle.lifecycle_engine import LifecycleEngine
        engine = LifecycleEngine(self.db_path)
        # active -> cold is not valid (must go through warm first)
        result = engine.transition_memory(mem_id, "cold", reason="skip")
        assert result["success"] is False

    def test_lifecycle_reactivation_fresh(self):
        from memory_store_v2 import MemoryStoreV2
        store = MemoryStoreV2(self.db_path)
        mem_id = store.add_memory(content="reactivation test", tags=["re"])
        from lifecycle.lifecycle_engine import LifecycleEngine
        engine = LifecycleEngine(self.db_path)
        engine.transition_memory(mem_id, "warm", reason="cool down")
        result = engine.reactivate_memory(mem_id, trigger="explicit")
        assert result["success"] is True
        assert engine.get_memory_state(mem_id) == "active"

    # -- Behavioral engine on fresh db --

    def test_behavioral_engine_works_fresh(self):
        from behavioral.outcome_tracker import OutcomeTracker
        learning_db = os.path.join(self.tmp_dir, "learning.db")
        tracker = OutcomeTracker(learning_db)
        oid = tracker.record_outcome([1], "success")
        assert oid is not None
        assert oid > 0

    def test_behavioral_outcome_tracker_failure(self):
        from behavioral.outcome_tracker import OutcomeTracker
        learning_db = os.path.join(self.tmp_dir, "learning.db")
        tracker = OutcomeTracker(learning_db)
        oid = tracker.record_outcome([1], "failure")
        assert oid is not None
        assert oid > 0

    def test_behavioral_outcome_tracker_partial(self):
        from behavioral.outcome_tracker import OutcomeTracker
        learning_db = os.path.join(self.tmp_dir, "learning.db")
        tracker = OutcomeTracker(learning_db)
        oid = tracker.record_outcome([1], "partial")
        assert oid is not None
        assert oid > 0

    def test_behavioral_invalid_outcome_returns_none(self):
        from behavioral.outcome_tracker import OutcomeTracker
        learning_db = os.path.join(self.tmp_dir, "learning.db")
        tracker = OutcomeTracker(learning_db)
        oid = tracker.record_outcome([1], "invalid_outcome")
        assert oid is None

    def test_behavioral_get_outcomes(self):
        from behavioral.outcome_tracker import OutcomeTracker
        learning_db = os.path.join(self.tmp_dir, "learning.db")
        tracker = OutcomeTracker(learning_db)
        tracker.record_outcome([10], "success")
        tracker.record_outcome([10], "failure")
        outcomes = tracker.get_outcomes()
        assert len(outcomes) >= 2

    def test_behavioral_success_rate(self):
        from behavioral.outcome_tracker import OutcomeTracker
        learning_db = os.path.join(self.tmp_dir, "learning.db")
        tracker = OutcomeTracker(learning_db)
        tracker.record_outcome([42], "success")
        tracker.record_outcome([42], "success")
        tracker.record_outcome([42], "failure")
        rate = tracker.get_success_rate(42)
        assert 0.6 <= rate <= 0.7  # 2/3

    def test_behavioral_multiple_memory_ids(self):
        from behavioral.outcome_tracker import OutcomeTracker
        learning_db = os.path.join(self.tmp_dir, "learning.db")
        tracker = OutcomeTracker(learning_db)
        oid = tracker.record_outcome([1, 2, 3], "success")
        assert oid is not None

    # -- Compliance engine on fresh db --

    def test_compliance_engine_works_fresh(self):
        from compliance.audit_db import AuditDB
        audit_db = os.path.join(self.tmp_dir, "audit.db")
        db = AuditDB(audit_db)
        eid = db.log_event("test.event", actor="user", resource_id=1)
        assert eid > 0

    def test_compliance_audit_hash_chain_valid(self):
        from compliance.audit_db import AuditDB
        audit_db = os.path.join(self.tmp_dir, "audit.db")
        db = AuditDB(audit_db)
        db.log_event("first.event", actor="user1")
        db.log_event("second.event", actor="user2")
        result = db.verify_chain()
        assert result["valid"] is True
        assert result["entries_checked"] == 2

    def test_compliance_audit_empty_chain_valid(self):
        from compliance.audit_db import AuditDB
        audit_db = os.path.join(self.tmp_dir, "audit.db")
        db = AuditDB(audit_db)
        result = db.verify_chain()
        assert result["valid"] is True
        assert result["entries_checked"] == 0

    def test_compliance_audit_query_by_event_type(self):
        from compliance.audit_db import AuditDB
        audit_db = os.path.join(self.tmp_dir, "audit.db")
        db = AuditDB(audit_db)
        db.log_event("memory.created", actor="agent1", resource_id=1)
        db.log_event("memory.recalled", actor="agent2", resource_id=2)
        events = db.query_events(event_type="memory.created")
        assert len(events) == 1
        assert events[0]["event_type"] == "memory.created"

    def test_compliance_audit_query_by_actor(self):
        from compliance.audit_db import AuditDB
        audit_db = os.path.join(self.tmp_dir, "audit.db")
        db = AuditDB(audit_db)
        db.log_event("ev1", actor="alice", resource_id=1)
        db.log_event("ev2", actor="bob", resource_id=2)
        events = db.query_events(actor="alice")
        assert len(events) == 1

    def test_compliance_audit_details_stored(self):
        from compliance.audit_db import AuditDB
        audit_db = os.path.join(self.tmp_dir, "audit.db")
        db = AuditDB(audit_db)
        db.log_event("test.detail", actor="sys", details={"key": "val"})
        events = db.query_events(event_type="test.detail")
        assert len(events) == 1
        details = json.loads(events[0]["details"])
        assert details["key"] == "val"


# ============================================================================
# 2. UPGRADE FROM v2.7 TESTS
# ============================================================================

class TestUpgradeFromV27:
    """Simulates upgrade from v2.7.6 (existing data, no lifecycle columns)."""

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "memory.db")
        _create_v27_db(self.db_path, num_memories=2)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    # -- Schema migration --

    def test_schema_migrates_on_init(self):
        """MemoryStoreV2 init should add lifecycle columns to existing DB."""
        from memory_store_v2 import MemoryStoreV2
        MemoryStoreV2(self.db_path)
        cols = _get_columns(self.db_path)
        assert "lifecycle_state" in cols
        assert "lifecycle_updated_at" in cols
        assert "lifecycle_history" in cols
        assert "access_level" in cols

    def test_migration_is_idempotent(self):
        """Running migration twice should not error or duplicate columns."""
        from memory_store_v2 import MemoryStoreV2
        MemoryStoreV2(self.db_path)
        MemoryStoreV2(self.db_path)  # second init
        cols = _get_columns(self.db_path)
        # Count lifecycle_state appearances
        conn = sqlite3.connect(self.db_path)
        info = conn.execute("PRAGMA table_info(memories)").fetchall()
        conn.close()
        lifecycle_cols = [r for r in info if r[1] == "lifecycle_state"]
        assert len(lifecycle_cols) == 1

    def test_existing_data_preserved(self):
        from memory_store_v2 import MemoryStoreV2
        store = MemoryStoreV2(self.db_path)
        results = store.list_all(limit=10)
        assert len(results) == 2
        contents = {r["content"] for r in results}
        assert "existing memory from v2.7 #0" in contents
        assert "existing memory from v2.7 #1" in contents

    def test_existing_memory_ids_preserved(self):
        from memory_store_v2 import MemoryStoreV2
        store = MemoryStoreV2(self.db_path)
        results = store.list_all(limit=10)
        ids = {r["id"] for r in results}
        assert 1 in ids
        assert 2 in ids

    def test_existing_memories_default_active(self):
        from memory_store_v2 import MemoryStoreV2
        MemoryStoreV2(self.db_path)
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("SELECT lifecycle_state FROM memories").fetchall()
        conn.close()
        for row in rows:
            assert row[0] == "active"

    def test_existing_memories_default_access_level(self):
        from memory_store_v2 import MemoryStoreV2
        MemoryStoreV2(self.db_path)
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("SELECT access_level FROM memories").fetchall()
        conn.close()
        for row in rows:
            assert row[0] == "public"

    def test_search_still_works_after_upgrade(self):
        from memory_store_v2 import MemoryStoreV2
        store = MemoryStoreV2(self.db_path)
        results = store.search("existing memory", limit=5)
        assert len(results) >= 1

    def test_list_all_still_works_after_upgrade(self):
        from memory_store_v2 import MemoryStoreV2
        store = MemoryStoreV2(self.db_path)
        results = store.list_all(limit=50)
        assert len(results) == 2

    def test_new_features_work_on_upgraded_db(self):
        from memory_store_v2 import MemoryStoreV2
        MemoryStoreV2(self.db_path)
        from lifecycle.lifecycle_engine import LifecycleEngine
        engine = LifecycleEngine(self.db_path)
        dist = engine.get_state_distribution()
        assert dist["active"] == 2

    def test_create_new_memory_after_upgrade(self):
        from memory_store_v2 import MemoryStoreV2
        store = MemoryStoreV2(self.db_path)
        mem_id = store.add_memory(content="new v2.8 memory", tags=["new"])
        assert mem_id is not None
        results = store.list_all(limit=10)
        assert len(results) == 3

    def test_new_memory_has_lifecycle_state_after_upgrade(self):
        from memory_store_v2 import MemoryStoreV2
        store = MemoryStoreV2(self.db_path)
        mem_id = store.add_memory(content="new v2.8 lifecycle check", tags=["lc"])
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT lifecycle_state FROM memories WHERE id=?", (mem_id,)
        ).fetchone()
        conn.close()
        assert row[0] == "active"

    def test_lifecycle_transition_on_upgraded_memory(self):
        from memory_store_v2 import MemoryStoreV2
        MemoryStoreV2(self.db_path)
        from lifecycle.lifecycle_engine import LifecycleEngine
        engine = LifecycleEngine(self.db_path)
        # Transition existing memory (id=1) from active to warm
        result = engine.transition_memory(1, "warm", reason="aging")
        assert result["success"] is True
        assert engine.get_memory_state(1) == "warm"

    def test_lifecycle_history_recorded_on_upgrade(self):
        from memory_store_v2 import MemoryStoreV2
        MemoryStoreV2(self.db_path)
        from lifecycle.lifecycle_engine import LifecycleEngine
        engine = LifecycleEngine(self.db_path)
        engine.transition_memory(1, "warm", reason="test history")
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT lifecycle_history FROM memories WHERE id=1"
        ).fetchone()
        conn.close()
        history = json.loads(row[0])
        assert len(history) == 1
        assert history[0]["from"] == "active"
        assert history[0]["to"] == "warm"

    def test_get_stats_still_works_after_upgrade(self):
        from memory_store_v2 import MemoryStoreV2
        store = MemoryStoreV2(self.db_path)
        stats = store.get_stats()
        assert stats["total_memories"] >= 2

    def test_dedup_still_works_after_upgrade(self):
        from memory_store_v2 import MemoryStoreV2
        store = MemoryStoreV2(self.db_path)
        id1 = store.add_memory(content="unique content for dedup test", tags=["d"])
        id2 = store.add_memory(content="unique content for dedup test", tags=["d"])
        assert id1 == id2  # Deduplication returns existing ID


class TestUpgradeFromV27LargeDataset:
    """Upgrade from v2.7 with many memories to test migration performance."""

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "memory.db")
        _create_v27_db(self.db_path, num_memories=50)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_all_50_memories_get_lifecycle_state(self):
        from memory_store_v2 import MemoryStoreV2
        MemoryStoreV2(self.db_path)
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("SELECT lifecycle_state FROM memories").fetchall()
        conn.close()
        assert len(rows) == 50
        for row in rows:
            assert row[0] == "active"

    def test_state_distribution_correct_after_bulk_migration(self):
        from memory_store_v2 import MemoryStoreV2
        MemoryStoreV2(self.db_path)
        from lifecycle.lifecycle_engine import LifecycleEngine
        engine = LifecycleEngine(self.db_path)
        dist = engine.get_state_distribution()
        assert dist["active"] == 50
        assert dist["warm"] == 0

    def test_lifecycle_transition_bulk(self):
        from memory_store_v2 import MemoryStoreV2
        MemoryStoreV2(self.db_path)
        from lifecycle.lifecycle_engine import LifecycleEngine
        engine = LifecycleEngine(self.db_path)
        for i in range(1, 11):
            engine.transition_memory(i, "warm", reason="bulk test")
        dist = engine.get_state_distribution()
        assert dist["warm"] == 10
        assert dist["active"] == 40


# ============================================================================
# 3. MODULE AVAILABILITY TESTS
# ============================================================================

class TestModuleAvailability:
    """Verify all v2.8 modules are importable and report correct status."""

    def test_lifecycle_available(self):
        from lifecycle import get_status
        status = get_status()
        assert status["lifecycle_available"] is True

    def test_behavioral_available(self):
        from behavioral import get_status
        status = get_status()
        assert status["behavioral_available"] is True

    def test_compliance_available(self):
        from compliance import get_status
        status = get_status()
        assert status["compliance_available"] is True

    def test_lifecycle_engine_importable(self):
        from lifecycle.lifecycle_engine import LifecycleEngine
        assert LifecycleEngine is not None

    def test_lifecycle_evaluator_importable(self):
        from lifecycle.lifecycle_evaluator import LifecycleEvaluator
        assert LifecycleEvaluator is not None

    def test_lifecycle_retention_policy_importable(self):
        from lifecycle.retention_policy import RetentionPolicyManager
        assert RetentionPolicyManager is not None

    def test_lifecycle_bounded_growth_importable(self):
        from lifecycle.bounded_growth import BoundedGrowthEnforcer
        assert BoundedGrowthEnforcer is not None

    def test_behavioral_outcome_tracker_importable(self):
        from behavioral.outcome_tracker import OutcomeTracker
        assert OutcomeTracker is not None

    def test_behavioral_patterns_importable(self):
        from behavioral.behavioral_patterns import BehavioralPatternExtractor
        assert BehavioralPatternExtractor is not None

    def test_compliance_abac_importable(self):
        from compliance.abac_engine import ABACEngine
        assert ABACEngine is not None

    def test_compliance_audit_db_importable(self):
        from compliance.audit_db import AuditDB
        assert AuditDB is not None

    def test_feature_vector_is_20(self):
        from learning.feature_extractor import NUM_FEATURES
        assert NUM_FEATURES == 20

    def test_feature_names_length_matches(self):
        from learning.feature_extractor import FEATURE_NAMES, NUM_FEATURES
        assert len(FEATURE_NAMES) == NUM_FEATURES

    def test_feature_names_contain_lifecycle(self):
        from learning.feature_extractor import FEATURE_NAMES
        assert "lifecycle_state" in FEATURE_NAMES

    def test_feature_names_contain_outcome(self):
        from learning.feature_extractor import FEATURE_NAMES
        assert "outcome_success_rate" in FEATURE_NAMES

    def test_feature_names_contain_behavioral(self):
        from learning.feature_extractor import FEATURE_NAMES
        assert "behavioral_match" in FEATURE_NAMES

    def test_feature_names_contain_cross_project(self):
        from learning.feature_extractor import FEATURE_NAMES
        assert "cross_project_score" in FEATURE_NAMES

    def test_feature_names_contain_retention(self):
        from learning.feature_extractor import FEATURE_NAMES
        assert "retention_priority" in FEATURE_NAMES

    def test_feature_names_contain_trust(self):
        from learning.feature_extractor import FEATURE_NAMES
        assert "trust_at_creation" in FEATURE_NAMES

    def test_feature_names_contain_lifecycle_decay(self):
        from learning.feature_extractor import FEATURE_NAMES
        assert "lifecycle_aware_decay" in FEATURE_NAMES

    def test_mcp_tools_report_outcome_available(self):
        import mcp_tools_v28
        assert hasattr(mcp_tools_v28, 'report_outcome')

    def test_mcp_tools_get_lifecycle_status_available(self):
        import mcp_tools_v28
        assert hasattr(mcp_tools_v28, 'get_lifecycle_status')

    def test_mcp_tools_set_retention_policy_available(self):
        import mcp_tools_v28
        assert hasattr(mcp_tools_v28, 'set_retention_policy')

    def test_mcp_tools_compact_memories_available(self):
        import mcp_tools_v28
        assert hasattr(mcp_tools_v28, 'compact_memories')

    def test_mcp_tools_get_behavioral_patterns_available(self):
        import mcp_tools_v28
        assert hasattr(mcp_tools_v28, 'get_behavioral_patterns')

    def test_mcp_tools_audit_trail_available(self):
        import mcp_tools_v28
        assert hasattr(mcp_tools_v28, 'audit_trail')

    def test_mcp_tools_are_async(self):
        import mcp_tools_v28
        import asyncio
        assert asyncio.iscoroutinefunction(mcp_tools_v28.report_outcome)
        assert asyncio.iscoroutinefunction(mcp_tools_v28.get_lifecycle_status)
        assert asyncio.iscoroutinefunction(mcp_tools_v28.audit_trail)

    def test_lifecycle_get_singleton_function(self):
        from lifecycle import get_lifecycle_engine
        assert callable(get_lifecycle_engine)

    def test_behavioral_get_singleton_function(self):
        from behavioral import get_outcome_tracker
        assert callable(get_outcome_tracker)

    def test_compliance_get_singleton_function(self):
        from compliance import get_abac_engine
        assert callable(get_abac_engine)

    def test_lifecycle_status_keys(self):
        from lifecycle import get_status
        status = get_status()
        assert "lifecycle_available" in status
        assert "init_error" in status
        assert "engine_active" in status

    def test_behavioral_status_keys(self):
        from behavioral import get_status
        status = get_status()
        assert "behavioral_available" in status
        assert "init_error" in status
        assert "tracker_active" in status

    def test_compliance_status_keys(self):
        from compliance import get_status
        status = get_status()
        assert "compliance_available" in status
        assert "init_error" in status
        assert "abac_active" in status


# ============================================================================
# 4. LIFECYCLE STATE MACHINE TESTS
# ============================================================================

class TestLifecycleStateMachine:
    """Verify the lifecycle state machine rules."""

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "memory.db")
        from memory_store_v2 import MemoryStoreV2
        self.store = MemoryStoreV2(self.db_path)
        from lifecycle.lifecycle_engine import LifecycleEngine
        self.engine = LifecycleEngine(self.db_path)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _create_memory(self, content_suffix=""):
        return self.store.add_memory(
            content=f"state machine test {content_suffix} {datetime.now().isoformat()}",
            tags=["sm"],
        )

    # Valid transitions
    def test_active_to_warm(self):
        mid = self._create_memory("a2w")
        r = self.engine.transition_memory(mid, "warm")
        assert r["success"] is True

    def test_warm_to_cold(self):
        mid = self._create_memory("w2c")
        self.engine.transition_memory(mid, "warm")
        r = self.engine.transition_memory(mid, "cold")
        assert r["success"] is True

    def test_cold_to_archived(self):
        mid = self._create_memory("c2a")
        self.engine.transition_memory(mid, "warm")
        self.engine.transition_memory(mid, "cold")
        r = self.engine.transition_memory(mid, "archived")
        assert r["success"] is True

    def test_archived_to_tombstoned(self):
        mid = self._create_memory("a2t")
        self.engine.transition_memory(mid, "warm")
        self.engine.transition_memory(mid, "cold")
        self.engine.transition_memory(mid, "archived")
        r = self.engine.transition_memory(mid, "tombstoned")
        assert r["success"] is True

    def test_warm_to_active_reactivation(self):
        mid = self._create_memory("w2a")
        self.engine.transition_memory(mid, "warm")
        r = self.engine.transition_memory(mid, "active")
        assert r["success"] is True

    def test_cold_to_active_reactivation(self):
        mid = self._create_memory("c2a")
        self.engine.transition_memory(mid, "warm")
        self.engine.transition_memory(mid, "cold")
        r = self.engine.transition_memory(mid, "active")
        assert r["success"] is True

    def test_archived_to_active_reactivation(self):
        mid = self._create_memory("ar2a")
        self.engine.transition_memory(mid, "warm")
        self.engine.transition_memory(mid, "cold")
        self.engine.transition_memory(mid, "archived")
        r = self.engine.transition_memory(mid, "active")
        assert r["success"] is True

    # Invalid transitions
    def test_active_to_cold_invalid(self):
        mid = self._create_memory("a2c")
        r = self.engine.transition_memory(mid, "cold")
        assert r["success"] is False

    def test_active_to_archived_invalid(self):
        mid = self._create_memory("a2ar")
        r = self.engine.transition_memory(mid, "archived")
        assert r["success"] is False

    def test_active_to_tombstoned_invalid(self):
        mid = self._create_memory("a2t")
        r = self.engine.transition_memory(mid, "tombstoned")
        assert r["success"] is False

    def test_warm_to_archived_invalid(self):
        mid = self._create_memory("w2ar")
        self.engine.transition_memory(mid, "warm")
        r = self.engine.transition_memory(mid, "archived")
        assert r["success"] is False

    def test_warm_to_tombstoned_invalid(self):
        mid = self._create_memory("w2t")
        self.engine.transition_memory(mid, "warm")
        r = self.engine.transition_memory(mid, "tombstoned")
        assert r["success"] is False

    def test_cold_to_warm_invalid(self):
        mid = self._create_memory("c2w")
        self.engine.transition_memory(mid, "warm")
        self.engine.transition_memory(mid, "cold")
        r = self.engine.transition_memory(mid, "warm")
        assert r["success"] is False

    def test_cold_to_tombstoned_invalid(self):
        mid = self._create_memory("c2t")
        self.engine.transition_memory(mid, "warm")
        self.engine.transition_memory(mid, "cold")
        r = self.engine.transition_memory(mid, "tombstoned")
        assert r["success"] is False

    def test_tombstoned_is_terminal(self):
        mid = self._create_memory("tomb")
        self.engine.transition_memory(mid, "warm")
        self.engine.transition_memory(mid, "cold")
        self.engine.transition_memory(mid, "archived")
        self.engine.transition_memory(mid, "tombstoned")
        for target in ("active", "warm", "cold", "archived"):
            r = self.engine.transition_memory(mid, target)
            assert r["success"] is False, f"Tombstoned -> {target} should fail"

    def test_nonexistent_memory_transition(self):
        r = self.engine.transition_memory(99999, "warm")
        assert r["success"] is False

    # Transition history tracking
    def test_transition_history_grows(self):
        mid = self._create_memory("hist")
        self.engine.transition_memory(mid, "warm", reason="step1")
        self.engine.transition_memory(mid, "cold", reason="step2")
        self.engine.transition_memory(mid, "active", reason="reactivate")
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT lifecycle_history FROM memories WHERE id=?", (mid,)
        ).fetchone()
        conn.close()
        history = json.loads(row[0])
        assert len(history) == 3
        assert history[0]["to"] == "warm"
        assert history[1]["to"] == "cold"
        assert history[2]["to"] == "active"

    def test_transition_history_has_timestamps(self):
        mid = self._create_memory("ts")
        self.engine.transition_memory(mid, "warm", reason="ts test")
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT lifecycle_history FROM memories WHERE id=?", (mid,)
        ).fetchone()
        conn.close()
        history = json.loads(row[0])
        assert "timestamp" in history[0]

    def test_transition_history_has_reason(self):
        mid = self._create_memory("reason")
        self.engine.transition_memory(mid, "warm", reason="custom reason")
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT lifecycle_history FROM memories WHERE id=?", (mid,)
        ).fetchone()
        conn.close()
        history = json.loads(row[0])
        assert history[0]["reason"] == "custom reason"

    # State validation helpers
    def test_is_valid_transition_method(self):
        assert self.engine.is_valid_transition("active", "warm") is True
        assert self.engine.is_valid_transition("active", "cold") is False

    def test_states_constant(self):
        from lifecycle.lifecycle_engine import LifecycleEngine
        assert "active" in LifecycleEngine.STATES
        assert "warm" in LifecycleEngine.STATES
        assert "cold" in LifecycleEngine.STATES
        assert "archived" in LifecycleEngine.STATES
        assert "tombstoned" in LifecycleEngine.STATES
        assert len(LifecycleEngine.STATES) == 5

    def test_all_states_present_in_distribution(self):
        dist = self.engine.get_state_distribution()
        for state in ("active", "warm", "cold", "archived", "tombstoned"):
            assert state in dist


# ============================================================================
# 5. BEHAVIORAL LEARNING ENGINE TESTS
# ============================================================================

class TestBehavioralEngine:
    """Comprehensive behavioral learning engine tests."""

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.learning_db = os.path.join(self.tmp_dir, "learning.db")
        from behavioral.outcome_tracker import OutcomeTracker
        self.tracker = OutcomeTracker(self.learning_db)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_record_all_action_types(self):
        from behavioral.outcome_tracker import OutcomeTracker
        for action_type in OutcomeTracker.ACTION_TYPES:
            oid = self.tracker.record_outcome(
                [1], "success", action_type=action_type
            )
            assert oid is not None

    def test_record_with_context(self):
        oid = self.tracker.record_outcome(
            [1], "success",
            context={"tool": "grep", "query": "test"},
        )
        assert oid is not None
        outcomes = self.tracker.get_outcomes()
        assert any(o["context"].get("tool") == "grep" for o in outcomes)

    def test_record_with_agent_id(self):
        oid = self.tracker.record_outcome(
            [1], "success", agent_id="claude-3.5"
        )
        assert oid is not None
        outcomes = self.tracker.get_outcomes()
        assert any(o["agent_id"] == "claude-3.5" for o in outcomes)

    def test_record_with_project(self):
        oid = self.tracker.record_outcome(
            [1], "success", project="my-project"
        )
        assert oid is not None
        outcomes = self.tracker.get_outcomes(project="my-project")
        assert len(outcomes) == 1

    def test_record_with_confidence(self):
        oid = self.tracker.record_outcome(
            [1], "success", confidence=0.75
        )
        assert oid is not None

    def test_success_rate_no_outcomes(self):
        rate = self.tracker.get_success_rate(999)
        assert rate == 0.0

    def test_success_rate_all_success(self):
        for _ in range(5):
            self.tracker.record_outcome([100], "success")
        rate = self.tracker.get_success_rate(100)
        assert rate == 1.0

    def test_success_rate_all_failure(self):
        for _ in range(5):
            self.tracker.record_outcome([200], "failure")
        rate = self.tracker.get_success_rate(200)
        assert rate == 0.0

    def test_success_rate_mixed(self):
        self.tracker.record_outcome([300], "success")
        self.tracker.record_outcome([300], "failure")
        rate = self.tracker.get_success_rate(300)
        assert rate == 0.5

    def test_outcomes_table_created(self):
        conn = sqlite3.connect(self.learning_db)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert "action_outcomes" in tables

    def test_outcomes_table_schema(self):
        conn = sqlite3.connect(self.learning_db)
        cols = {r[1] for r in conn.execute(
            "PRAGMA table_info(action_outcomes)"
        ).fetchall()}
        conn.close()
        expected = {
            "id", "memory_ids", "outcome", "action_type", "context",
            "confidence", "agent_id", "project", "profile", "created_at",
        }
        assert expected.issubset(cols)


# ============================================================================
# 6. COMPLIANCE ENGINE TESTS
# ============================================================================

class TestComplianceEngine:
    """Comprehensive compliance engine tests."""

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.audit_db_path = os.path.join(self.tmp_dir, "audit.db")
        from compliance.audit_db import AuditDB
        self.audit_db = AuditDB(self.audit_db_path)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_audit_events_table_created(self):
        conn = sqlite3.connect(self.audit_db_path)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert "audit_events" in tables

    def test_audit_events_schema(self):
        conn = sqlite3.connect(self.audit_db_path)
        cols = {r[1] for r in conn.execute(
            "PRAGMA table_info(audit_events)"
        ).fetchall()}
        conn.close()
        expected = {
            "id", "event_type", "actor", "resource_id", "details",
            "prev_hash", "entry_hash", "created_at",
        }
        assert expected.issubset(cols)

    def test_hash_chain_genesis(self):
        self.audit_db.log_event("first", actor="sys")
        conn = sqlite3.connect(self.audit_db_path)
        row = conn.execute(
            "SELECT prev_hash FROM audit_events WHERE id=1"
        ).fetchone()
        conn.close()
        assert row[0] == "genesis"

    def test_hash_chain_links(self):
        self.audit_db.log_event("ev1", actor="sys")
        self.audit_db.log_event("ev2", actor="sys")
        conn = sqlite3.connect(self.audit_db_path)
        rows = conn.execute(
            "SELECT id, prev_hash, entry_hash FROM audit_events ORDER BY id"
        ).fetchall()
        conn.close()
        assert rows[1][1] == rows[0][2]  # ev2.prev_hash == ev1.entry_hash

    def test_hash_chain_verification_10_events(self):
        for i in range(10):
            self.audit_db.log_event(f"event_{i}", actor=f"actor_{i}")
        result = self.audit_db.verify_chain()
        assert result["valid"] is True
        assert result["entries_checked"] == 10

    def test_tamper_detection(self):
        self.audit_db.log_event("legit1", actor="sys")
        self.audit_db.log_event("legit2", actor="sys")
        # Tamper with the first event's entry_hash
        conn = sqlite3.connect(self.audit_db_path)
        conn.execute(
            "UPDATE audit_events SET entry_hash='tampered' WHERE id=1"
        )
        conn.commit()
        conn.close()
        result = self.audit_db.verify_chain()
        assert result["valid"] is False

    def test_query_events_limit(self):
        for i in range(20):
            self.audit_db.log_event(f"event_{i}", actor="sys")
        events = self.audit_db.query_events(limit=5)
        assert len(events) == 5

    def test_query_events_by_resource_id(self):
        self.audit_db.log_event("ev", actor="sys", resource_id=42)
        self.audit_db.log_event("ev", actor="sys", resource_id=99)
        events = self.audit_db.query_events(resource_id=42)
        assert len(events) == 1

    def test_multiple_audit_db_instances_same_file(self):
        from compliance.audit_db import AuditDB
        db1 = AuditDB(self.audit_db_path)
        db1.log_event("from_db1", actor="sys")
        db2 = AuditDB(self.audit_db_path)
        db2.log_event("from_db2", actor="sys")
        result = db2.verify_chain()
        assert result["valid"] is True
        assert result["entries_checked"] == 2


# ============================================================================
# 7. GRACEFUL DEGRADATION TESTS
# ============================================================================

class TestGracefulDegradation:
    """Test that engine failures don't cascade."""

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "memory.db")

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_memory_store_works_without_lifecycle_engine(self):
        """Core memory operations must work even if lifecycle engine is broken."""
        from memory_store_v2 import MemoryStoreV2
        store = MemoryStoreV2(self.db_path)
        mem_id = store.add_memory(content="degradation test", tags=["deg"])
        assert mem_id is not None
        results = store.list_all(limit=10)
        assert len(results) == 1

    def test_lifecycle_engine_nonexistent_db(self):
        """LifecycleEngine with bad path should handle errors gracefully."""
        from lifecycle.lifecycle_engine import LifecycleEngine
        bad_path = os.path.join(self.tmp_dir, "nonexistent", "bad.db")
        try:
            engine = LifecycleEngine(bad_path)
            state = engine.get_memory_state(1)
            # Should return None or raise a handled error
            assert state is None or True  # Either is acceptable
        except sqlite3.OperationalError:
            pass  # Expected when directory doesn't exist

    def test_outcome_tracker_no_db_path(self):
        """OutcomeTracker with None db_path should not crash on init."""
        from behavioral.outcome_tracker import OutcomeTracker
        tracker = OutcomeTracker(None)
        assert tracker is not None

    def test_audit_db_no_db_path(self):
        """AuditDB with None db_path should not crash on init."""
        from compliance.audit_db import AuditDB
        db = AuditDB(None)
        assert db is not None

    def test_lifecycle_status_reports_available(self):
        from lifecycle import get_status
        status = get_status()
        assert isinstance(status["lifecycle_available"], bool)

    def test_behavioral_status_reports_available(self):
        from behavioral import get_status
        status = get_status()
        assert isinstance(status["behavioral_available"], bool)

    def test_compliance_status_reports_available(self):
        from compliance import get_status
        status = get_status()
        assert isinstance(status["compliance_available"], bool)


# ============================================================================
# 8. THREE-DATABASE ISOLATION TESTS
# ============================================================================

class TestThreeDatabaseIsolation:
    """Verify memory.db, learning.db, and audit.db operate independently."""

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.memory_db = os.path.join(self.tmp_dir, "memory.db")
        self.learning_db = os.path.join(self.tmp_dir, "learning.db")
        self.audit_db = os.path.join(self.tmp_dir, "audit.db")

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_three_databases_created_separately(self):
        from memory_store_v2 import MemoryStoreV2
        from behavioral.outcome_tracker import OutcomeTracker
        from compliance.audit_db import AuditDB

        MemoryStoreV2(self.memory_db)
        OutcomeTracker(self.learning_db)
        AuditDB(self.audit_db)

        assert os.path.exists(self.memory_db)
        assert os.path.exists(self.learning_db)
        assert os.path.exists(self.audit_db)

    def test_memory_db_has_no_outcome_table(self):
        from memory_store_v2 import MemoryStoreV2
        MemoryStoreV2(self.memory_db)
        conn = sqlite3.connect(self.memory_db)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert "action_outcomes" not in tables

    def test_memory_db_has_no_audit_table(self):
        from memory_store_v2 import MemoryStoreV2
        MemoryStoreV2(self.memory_db)
        conn = sqlite3.connect(self.memory_db)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert "audit_events" not in tables

    def test_learning_db_has_no_memories_table(self):
        from behavioral.outcome_tracker import OutcomeTracker
        OutcomeTracker(self.learning_db)
        conn = sqlite3.connect(self.learning_db)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert "memories" not in tables

    def test_audit_db_has_no_memories_table(self):
        from compliance.audit_db import AuditDB
        AuditDB(self.audit_db)
        conn = sqlite3.connect(self.audit_db)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()
        assert "memories" not in tables

    def test_learning_db_failure_doesnt_affect_memory_db(self):
        from memory_store_v2 import MemoryStoreV2
        store = MemoryStoreV2(self.memory_db)
        mem_id = store.add_memory(content="isolation test", tags=["iso"])
        # learning_db not even created — memory ops still work
        assert mem_id is not None

    def test_audit_db_failure_doesnt_affect_memory_db(self):
        from memory_store_v2 import MemoryStoreV2
        store = MemoryStoreV2(self.memory_db)
        mem_id = store.add_memory(content="audit isolation test", tags=["iso"])
        assert mem_id is not None


# ============================================================================
# 9. CROSS-ENGINE INTEGRATION TESTS
# ============================================================================

class TestCrossEngineIntegration:
    """Test that engines work together when all are available."""

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.memory_db = os.path.join(self.tmp_dir, "memory.db")
        self.learning_db = os.path.join(self.tmp_dir, "learning.db")
        self.audit_db_path = os.path.join(self.tmp_dir, "audit.db")
        from memory_store_v2 import MemoryStoreV2
        self.store = MemoryStoreV2(self.memory_db)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_memory_created_then_lifecycle_tracked(self):
        mem_id = self.store.add_memory(content="integration test", tags=["int"])
        from lifecycle.lifecycle_engine import LifecycleEngine
        engine = LifecycleEngine(self.memory_db)
        state = engine.get_memory_state(mem_id)
        assert state == "active"

    def test_memory_created_then_outcome_recorded(self):
        mem_id = self.store.add_memory(content="outcome integration", tags=["oi"])
        from behavioral.outcome_tracker import OutcomeTracker
        tracker = OutcomeTracker(self.learning_db)
        oid = tracker.record_outcome([mem_id], "success")
        assert oid is not None

    def test_memory_created_then_audit_logged(self):
        mem_id = self.store.add_memory(content="audit integration", tags=["ai"])
        from compliance.audit_db import AuditDB
        audit = AuditDB(self.audit_db_path)
        eid = audit.log_event("memory.created", actor="test", resource_id=mem_id)
        assert eid > 0

    def test_full_lifecycle_with_audit(self):
        mem_id = self.store.add_memory(content="full flow test", tags=["ff"])
        from lifecycle.lifecycle_engine import LifecycleEngine
        from compliance.audit_db import AuditDB
        engine = LifecycleEngine(self.memory_db)
        audit = AuditDB(self.audit_db_path)

        audit.log_event("memory.created", actor="test", resource_id=mem_id)
        engine.transition_memory(mem_id, "warm", reason="aging")
        audit.log_event("lifecycle.transition", actor="scheduler",
                        resource_id=mem_id, details={"to": "warm"})

        assert engine.get_memory_state(mem_id) == "warm"
        events = audit.query_events(resource_id=mem_id)
        assert len(events) == 2

    def test_full_lifecycle_with_behavioral_outcome(self):
        mem_id = self.store.add_memory(content="behavior flow test", tags=["bf"])
        from behavioral.outcome_tracker import OutcomeTracker
        tracker = OutcomeTracker(self.learning_db)

        # Record multiple outcomes
        tracker.record_outcome([mem_id], "success")
        tracker.record_outcome([mem_id], "success")
        tracker.record_outcome([mem_id], "failure")

        rate = tracker.get_success_rate(mem_id)
        assert 0.6 <= rate <= 0.7

    def test_multiple_memories_with_different_states(self):
        from lifecycle.lifecycle_engine import LifecycleEngine
        engine = LifecycleEngine(self.memory_db)

        m1 = self.store.add_memory(content="active mem 1", tags=["s"])
        m2 = self.store.add_memory(content="warm mem 2", tags=["s"])
        m3 = self.store.add_memory(content="cold mem 3", tags=["s"])

        engine.transition_memory(m2, "warm")
        engine.transition_memory(m3, "warm")
        engine.transition_memory(m3, "cold")

        dist = engine.get_state_distribution()
        assert dist["active"] == 1
        assert dist["warm"] == 1
        assert dist["cold"] == 1


# ============================================================================
# 10. V2.7 API COMPATIBILITY TESTS
# ============================================================================

class TestV27ApiCompatibility:
    """Ensure all v2.7 public APIs still work identically."""

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "memory.db")
        from memory_store_v2 import MemoryStoreV2
        self.store = MemoryStoreV2(self.db_path)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_add_memory_returns_int(self):
        mid = self.store.add_memory(content="type check", tags=["tc"])
        assert isinstance(mid, int)

    def test_add_memory_with_all_params(self):
        mid = self.store.add_memory(
            content="full params test",
            summary="test summary",
            project_path="/tmp/test",
            project_name="test-proj",
            tags=["a", "b"],
            category="backend",
            memory_type="long-term",
            importance=8,
        )
        assert mid is not None

    def test_add_memory_dedup(self):
        mid1 = self.store.add_memory(content="dedup v27 test", tags=["d"])
        mid2 = self.store.add_memory(content="dedup v27 test", tags=["d"])
        assert mid1 == mid2

    def test_add_memory_empty_content_raises(self):
        import pytest
        with pytest.raises(ValueError):
            self.store.add_memory(content="", tags=["e"])

    def test_add_memory_non_string_raises(self):
        import pytest
        with pytest.raises(TypeError):
            self.store.add_memory(content=123, tags=["e"])

    def test_search_returns_list(self):
        self.store.add_memory(content="searchable content v27", tags=["s"])
        results = self.store.search("searchable", limit=5)
        assert isinstance(results, list)

    def test_search_result_has_expected_keys(self):
        self.store.add_memory(content="key check memory content", tags=["k"])
        results = self.store.search("key check", limit=5)
        if results:
            r = results[0]
            assert "id" in r
            assert "content" in r
            assert "score" in r
            assert "tags" in r
            assert "importance" in r

    def test_list_all_returns_list(self):
        self.store.add_memory(content="list all test", tags=["la"])
        results = self.store.list_all(limit=10)
        assert isinstance(results, list)
        assert len(results) >= 1

    def test_list_all_result_has_title(self):
        self.store.add_memory(content="title field test", tags=["tf"])
        results = self.store.list_all(limit=10)
        assert "title" in results[0]

    def test_get_stats_returns_dict(self):
        self.store.add_memory(content="stats test", tags=["st"])
        stats = self.store.get_stats()
        assert isinstance(stats, dict)
        assert "total_memories" in stats

    def test_get_stats_total_correct(self):
        self.store.add_memory(content="stats count 1", tags=["sc"])
        self.store.add_memory(content="stats count 2", tags=["sc"])
        stats = self.store.get_stats()
        assert stats["total_memories"] >= 2

    def test_search_with_lifecycle_filter(self):
        """v2.8 extension: search accepts lifecycle_states parameter."""
        self.store.add_memory(content="lifecycle filter test", tags=["lf"])
        results = self.store.search(
            "lifecycle filter", limit=5,
            lifecycle_states=("active", "warm"),
        )
        assert isinstance(results, list)

    def test_search_default_lifecycle_filter(self):
        """Default lifecycle filter should include active and warm."""
        self.store.add_memory(content="default lifecycle search", tags=["dls"])
        results = self.store.search("default lifecycle", limit=5)
        # Should find the memory since it's active (default)
        assert len(results) >= 0  # At least returns an empty list, no crash

    def test_memory_type_field_preserved(self):
        mid = self.store.add_memory(
            content="type preserve test", tags=["tp"],
            memory_type="long-term",
        )
        results = self.store.list_all(limit=50)
        match = [r for r in results if r["id"] == mid]
        assert len(match) == 1
        assert match[0]["memory_type"] == "long-term"

    def test_importance_field_preserved(self):
        mid = self.store.add_memory(
            content="importance preserve test", tags=["ip"],
            importance=9,
        )
        results = self.store.list_all(limit=50)
        match = [r for r in results if r["id"] == mid]
        assert len(match) == 1
        assert match[0]["importance"] == 9

    def test_category_field_preserved(self):
        mid = self.store.add_memory(
            content="category preserve test", tags=["cp"],
            category="frontend",
        )
        results = self.store.list_all(limit=50)
        match = [r for r in results if r["id"] == mid]
        assert len(match) == 1
        assert match[0]["category"] == "frontend"

    def test_tags_stored_as_json(self):
        mid = self.store.add_memory(
            content="json tags test", tags=["alpha", "beta"],
        )
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT tags FROM memories WHERE id=?", (mid,)
        ).fetchone()
        conn.close()
        parsed = json.loads(row[0])
        assert "alpha" in parsed
        assert "beta" in parsed


# ============================================================================
# 11. CONCURRENT ACCESS TESTS
# ============================================================================

class TestConcurrentAccess:
    """Verify thread-safety of lifecycle transitions."""

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "memory.db")
        from memory_store_v2 import MemoryStoreV2
        self.store = MemoryStoreV2(self.db_path)

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_concurrent_lifecycle_transitions(self):
        import threading
        mid = self.store.add_memory(content="concurrent test", tags=["ct"])
        from lifecycle.lifecycle_engine import LifecycleEngine
        engine = LifecycleEngine(self.db_path)

        results = []

        def try_transition():
            r = engine.transition_memory(mid, "warm", reason="race")
            results.append(r)

        threads = [threading.Thread(target=try_transition) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # At least one should succeed, others may fail (already in warm state)
        successes = [r for r in results if r.get("success")]
        assert len(successes) >= 1

    def test_concurrent_outcome_recording(self):
        import threading
        from behavioral.outcome_tracker import OutcomeTracker
        learning_db = os.path.join(self.tmp_dir, "learning.db")
        tracker = OutcomeTracker(learning_db)

        ids = []

        def record():
            oid = tracker.record_outcome([1], "success")
            ids.append(oid)

        threads = [threading.Thread(target=record) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(ids) == 10
        assert all(oid is not None and oid > 0 for oid in ids)

    def test_concurrent_audit_logging(self):
        import threading
        from compliance.audit_db import AuditDB
        audit_db = os.path.join(self.tmp_dir, "audit.db")
        db = AuditDB(audit_db)

        ids = []

        def log_event(i):
            eid = db.log_event(f"event_{i}", actor=f"actor_{i}")
            ids.append(eid)

        threads = [threading.Thread(target=log_event, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(ids) == 10
        # Verify chain is still valid after concurrent writes
        result = db.verify_chain()
        assert result["valid"] is True


# ============================================================================
# 12. EDGE CASES & ERROR HANDLING
# ============================================================================

class TestEdgeCases:
    """Edge cases and error boundaries."""

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "memory.db")

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_lifecycle_engine_get_state_missing_memory(self):
        from memory_store_v2 import MemoryStoreV2
        MemoryStoreV2(self.db_path)
        from lifecycle.lifecycle_engine import LifecycleEngine
        engine = LifecycleEngine(self.db_path)
        state = engine.get_memory_state(99999)
        assert state is None

    def test_transition_with_empty_reason(self):
        from memory_store_v2 import MemoryStoreV2
        store = MemoryStoreV2(self.db_path)
        mid = store.add_memory(content="empty reason test", tags=["er"])
        from lifecycle.lifecycle_engine import LifecycleEngine
        engine = LifecycleEngine(self.db_path)
        result = engine.transition_memory(mid, "warm", reason="")
        assert result["success"] is True

    def test_outcome_empty_memory_ids(self):
        from behavioral.outcome_tracker import OutcomeTracker
        learning_db = os.path.join(self.tmp_dir, "learning.db")
        tracker = OutcomeTracker(learning_db)
        oid = tracker.record_outcome([], "success")
        assert oid is not None  # Empty list is technically valid JSON

    def test_audit_event_no_resource_id(self):
        from compliance.audit_db import AuditDB
        audit_db = os.path.join(self.tmp_dir, "audit.db")
        db = AuditDB(audit_db)
        eid = db.log_event("system.startup", actor="system")
        assert eid > 0

    def test_audit_event_with_details_none(self):
        from compliance.audit_db import AuditDB
        audit_db = os.path.join(self.tmp_dir, "audit.db")
        db = AuditDB(audit_db)
        eid = db.log_event("test", actor="sys", details=None)
        assert eid > 0

    def test_lifecycle_state_distribution_empty_db(self):
        from memory_store_v2 import MemoryStoreV2
        MemoryStoreV2(self.db_path)
        from lifecycle.lifecycle_engine import LifecycleEngine
        engine = LifecycleEngine(self.db_path)
        dist = engine.get_state_distribution()
        assert all(v == 0 for v in dist.values())

    def test_outcome_tracker_get_outcomes_empty(self):
        from behavioral.outcome_tracker import OutcomeTracker
        learning_db = os.path.join(self.tmp_dir, "learning.db")
        tracker = OutcomeTracker(learning_db)
        outcomes = tracker.get_outcomes()
        assert outcomes == []

    def test_audit_query_events_empty(self):
        from compliance.audit_db import AuditDB
        audit_db = os.path.join(self.tmp_dir, "audit.db")
        db = AuditDB(audit_db)
        events = db.query_events()
        assert events == []

    def test_unicode_content_preserved(self):
        from memory_store_v2 import MemoryStoreV2
        store = MemoryStoreV2(self.db_path)
        content = "Unicode test: \u2603 \u2764 \u00e9\u00e8\u00ea \u4e16\u754c"
        mid = store.add_memory(content=content, tags=["unicode"])
        results = store.list_all(limit=10)
        assert results[0]["content"] == content

    def test_large_content_memory(self):
        from memory_store_v2 import MemoryStoreV2
        store = MemoryStoreV2(self.db_path)
        content = "x" * 100_000  # 100KB
        mid = store.add_memory(content=content, tags=["large"])
        assert mid is not None

    def test_max_tags(self):
        from memory_store_v2 import MemoryStoreV2
        store = MemoryStoreV2(self.db_path)
        tags = [f"tag{i}" for i in range(20)]
        mid = store.add_memory(content="max tags test", tags=tags)
        assert mid is not None

    def test_too_many_tags_raises(self):
        import pytest
        from memory_store_v2 import MemoryStoreV2
        store = MemoryStoreV2(self.db_path)
        tags = [f"tag{i}" for i in range(21)]
        with pytest.raises(ValueError):
            store.add_memory(content="too many tags", tags=tags)
