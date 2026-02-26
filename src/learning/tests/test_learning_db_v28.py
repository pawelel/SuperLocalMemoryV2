# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Tests for v2.8 learning.db schema extensions — outcome and behavioral tables.
"""
import pytest
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


@pytest.fixture(autouse=True)
def reset_singleton():
    from learning.learning_db import LearningDB
    LearningDB.reset_instance()
    yield
    LearningDB.reset_instance()


@pytest.fixture
def learning_db(tmp_path):
    from learning.learning_db import LearningDB
    db_path = tmp_path / "learning.db"
    return LearningDB(db_path=db_path)


class TestActionOutcomesTable:
    def test_table_exists(self, learning_db):
        conn = learning_db._get_connection()
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        conn.close()
        assert "action_outcomes" in tables

    def test_store_outcome(self, learning_db):
        oid = learning_db.store_outcome([1, 2], "success", action_type="code_written", project="myproject")
        assert isinstance(oid, int)
        assert oid > 0

    def test_get_outcomes(self, learning_db):
        learning_db.store_outcome([1], "success", project="proj1")
        learning_db.store_outcome([2], "failure", project="proj1")
        results = learning_db.get_outcomes(project="proj1")
        assert len(results) == 2

    def test_get_outcomes_by_memory_id(self, learning_db):
        learning_db.store_outcome([1, 2], "success")
        learning_db.store_outcome([3], "failure")
        results = learning_db.get_outcomes(memory_id=1)
        assert len(results) == 1
        assert 1 in results[0]["memory_ids"]

    def test_outcome_has_profile(self, learning_db):
        learning_db.store_outcome([1], "success")
        results = learning_db.get_outcomes()
        assert results[0]["profile"] == "default"


class TestBehavioralPatternsTable:
    def test_table_exists(self, learning_db):
        conn = learning_db._get_connection()
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        conn.close()
        assert "behavioral_patterns" in tables

    def test_store_pattern(self, learning_db):
        pid = learning_db.store_behavioral_pattern("tag_success", "python", success_rate=0.85, evidence_count=10, confidence=0.8)
        assert isinstance(pid, int)

    def test_get_patterns(self, learning_db):
        learning_db.store_behavioral_pattern("tag_success", "python", confidence=0.8)
        learning_db.store_behavioral_pattern("tag_success", "javascript", confidence=0.6)
        results = learning_db.get_behavioral_patterns(pattern_type="tag_success")
        assert len(results) == 2

    def test_get_patterns_min_confidence(self, learning_db):
        learning_db.store_behavioral_pattern("tag_success", "python", confidence=0.8)
        learning_db.store_behavioral_pattern("tag_success", "javascript", confidence=0.3)
        results = learning_db.get_behavioral_patterns(min_confidence=0.5)
        assert len(results) == 1
        assert results[0]["pattern_key"] == "python"


class TestCrossProjectTable:
    def test_table_exists(self, learning_db):
        conn = learning_db._get_connection()
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        conn.close()
        assert "cross_project_behaviors" in tables

    def test_store_transfer(self, learning_db):
        pid = learning_db.store_behavioral_pattern("tag_success", "python", confidence=0.8)
        tid = learning_db.store_cross_project("project_a", "project_b", pid, confidence=0.7)
        assert isinstance(tid, int)

    def test_get_transfers(self, learning_db):
        pid = learning_db.store_behavioral_pattern("tag_success", "python", confidence=0.8)
        learning_db.store_cross_project("proj_a", "proj_b", pid, confidence=0.7)
        results = learning_db.get_cross_project_transfers(source_project="proj_a")
        assert len(results) == 1
        assert results[0]["target_project"] == "proj_b"

    def test_existing_tables_untouched(self, learning_db):
        """Existing 6 tables should still exist."""
        conn = learning_db._get_connection()
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        conn.close()
        for expected in ["transferable_patterns", "workflow_patterns", "ranking_feedback", "ranking_models", "source_quality", "engagement_metrics"]:
            assert expected in tables
