# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Tests for privacy-safe cross-project behavioral transfer.
"""
import sqlite3
import tempfile
import os
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestCrossProjectTransfer:
    """Test cross-project behavioral pattern transfer."""

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "learning.db")
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS behavioral_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_type TEXT NOT NULL,
                pattern_key TEXT NOT NULL,
                success_rate REAL DEFAULT 0.0,
                evidence_count INTEGER DEFAULT 0,
                confidence REAL DEFAULT 0.0,
                metadata TEXT DEFAULT '{}',
                project TEXT,
                profile TEXT DEFAULT 'default',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cross_project_behaviors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_project TEXT NOT NULL,
                target_project TEXT NOT NULL,
                pattern_id INTEGER NOT NULL,
                transfer_type TEXT DEFAULT 'metadata',
                confidence REAL DEFAULT 0.0,
                profile TEXT DEFAULT 'default',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (pattern_id) REFERENCES behavioral_patterns(id)
            )
        """)
        # Insert patterns: high-confidence pattern in project_a
        conn.execute(
            "INSERT INTO behavioral_patterns (pattern_type, pattern_key, success_rate, evidence_count, confidence, project) VALUES (?, ?, ?, ?, ?, ?)",
            ("action_type_success", "code_written", 0.85, 12, 0.9, "project_a"),
        )
        # Low-confidence pattern (should NOT transfer)
        conn.execute(
            "INSERT INTO behavioral_patterns (pattern_type, pattern_key, success_rate, evidence_count, confidence, project) VALUES (?, ?, ?, ?, ?, ?)",
            ("action_type_success", "debug_resolved", 0.4, 3, 0.2, "project_a"),
        )
        # High-confidence pattern for project_b
        conn.execute(
            "INSERT INTO behavioral_patterns (pattern_type, pattern_key, success_rate, evidence_count, confidence, project) VALUES (?, ?, ?, ?, ?, ?)",
            ("project_success", "project_b", 0.9, 15, 0.95, "project_b"),
        )
        conn.commit()
        conn.close()

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_evaluate_transfers(self):
        """evaluate_transfers returns eligible patterns."""
        from behavioral.cross_project_transfer import CrossProjectTransfer
        transfer = CrossProjectTransfer(self.db_path)
        eligible = transfer.evaluate_transfers(target_project="project_c")
        assert isinstance(eligible, list)
        assert len(eligible) >= 1  # At least the high-confidence pattern

    def test_only_high_confidence_transfers(self):
        """Only patterns with confidence >= 0.7 and evidence >= 5 transfer."""
        from behavioral.cross_project_transfer import CrossProjectTransfer
        transfer = CrossProjectTransfer(self.db_path)
        eligible = transfer.evaluate_transfers(target_project="project_c")
        for e in eligible:
            assert e["confidence"] >= 0.7
            assert e["evidence_count"] >= 5

    def test_low_confidence_excluded(self):
        """Low confidence patterns (id=2, confidence=0.2) should NOT transfer."""
        from behavioral.cross_project_transfer import CrossProjectTransfer
        transfer = CrossProjectTransfer(self.db_path)
        eligible = transfer.evaluate_transfers(target_project="project_c")
        pattern_ids = {e["pattern_id"] for e in eligible}
        assert 2 not in pattern_ids  # Low confidence pattern excluded

    def test_only_metadata_transfers(self):
        """Transfers must be metadata-only — never content."""
        from behavioral.cross_project_transfer import CrossProjectTransfer
        transfer = CrossProjectTransfer(self.db_path)
        eligible = transfer.evaluate_transfers(target_project="project_c")
        for e in eligible:
            assert e["transfer_type"] == "metadata"
            assert "content" not in e  # No content field
            assert "content_hash" not in e  # No content hashes

    def test_apply_transfer(self):
        """apply_transfer records the transfer in cross_project_behaviors."""
        from behavioral.cross_project_transfer import CrossProjectTransfer
        transfer = CrossProjectTransfer(self.db_path)
        result = transfer.apply_transfer(pattern_id=1, target_project="project_c")
        assert result["success"] is True
        # Verify in DB
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT * FROM cross_project_behaviors WHERE target_project='project_c'").fetchone()
        conn.close()
        assert row is not None

    def test_transfer_logged(self):
        """Transfers are logged with source and target projects."""
        from behavioral.cross_project_transfer import CrossProjectTransfer
        transfer = CrossProjectTransfer(self.db_path)
        transfer.apply_transfer(pattern_id=1, target_project="project_c")
        transfers = transfer.get_transfers(target_project="project_c")
        assert len(transfers) == 1
        assert transfers[0]["source_project"] == "project_a"

    def test_no_self_transfer(self):
        """Patterns should not transfer to their own project."""
        from behavioral.cross_project_transfer import CrossProjectTransfer
        transfer = CrossProjectTransfer(self.db_path)
        eligible = transfer.evaluate_transfers(target_project="project_a")
        # Pattern 1 is from project_a — should not be eligible for project_a
        source_projects = {e.get("source_project") for e in eligible}
        assert "project_a" not in source_projects

    def test_disable_via_config(self):
        """Transfers can be disabled via config."""
        from behavioral.cross_project_transfer import CrossProjectTransfer
        transfer = CrossProjectTransfer(self.db_path, enabled=False)
        eligible = transfer.evaluate_transfers(target_project="project_c")
        assert eligible == []
