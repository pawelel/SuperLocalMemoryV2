# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Tests for behavioral pattern extraction from outcomes.
"""
import sqlite3
import tempfile
import os
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestBehavioralPatterns:
    """Test pattern extraction from action outcomes."""

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "learning.db")
        conn = sqlite3.connect(self.db_path)
        # Create action_outcomes table (populated by OutcomeTracker)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS action_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_ids TEXT NOT NULL,
                outcome TEXT NOT NULL,
                action_type TEXT DEFAULT 'other',
                context TEXT DEFAULT '{}',
                confidence REAL DEFAULT 0.9,
                agent_id TEXT DEFAULT 'user',
                project TEXT,
                profile TEXT DEFAULT 'default',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Create behavioral_patterns table
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
        # Insert sample outcomes for pattern extraction
        # Project A: 8 success, 2 failure -> 80% success
        for i in range(8):
            conn.execute("INSERT INTO action_outcomes (memory_ids, outcome, project, action_type) VALUES (?, ?, ?, ?)",
                (json.dumps([i+1]), "success", "project_a", "code_written"))
        for i in range(2):
            conn.execute("INSERT INTO action_outcomes (memory_ids, outcome, project, action_type) VALUES (?, ?, ?, ?)",
                (json.dumps([i+20]), "failure", "project_a", "code_written"))
        # Project B: 2 success, 8 failure -> 20% success
        for i in range(2):
            conn.execute("INSERT INTO action_outcomes (memory_ids, outcome, project, action_type) VALUES (?, ?, ?, ?)",
                (json.dumps([i+30]), "success", "project_b", "debug_resolved"))
        for i in range(8):
            conn.execute("INSERT INTO action_outcomes (memory_ids, outcome, project, action_type) VALUES (?, ?, ?, ?)",
                (json.dumps([i+40]), "failure", "project_b", "debug_resolved"))
        conn.commit()
        conn.close()

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_extract_patterns(self):
        """extract_patterns returns list of discovered patterns."""
        from behavioral.behavioral_patterns import BehavioralPatternExtractor
        extractor = BehavioralPatternExtractor(self.db_path)
        patterns = extractor.extract_patterns()
        assert isinstance(patterns, list)
        assert len(patterns) >= 2  # At least project_a and project_b patterns

    def test_project_success_rate(self):
        """Patterns should reflect actual success rates per project."""
        from behavioral.behavioral_patterns import BehavioralPatternExtractor
        extractor = BehavioralPatternExtractor(self.db_path)
        patterns = extractor.extract_patterns()
        proj_a = [p for p in patterns if p["pattern_key"] == "project_a" and p["pattern_type"] == "project_success"]
        assert len(proj_a) == 1
        assert abs(proj_a[0]["success_rate"] - 0.8) < 0.01

    def test_success_pattern_high_rate(self):
        """Projects with >70% success and 5+ evidence -> success pattern."""
        from behavioral.behavioral_patterns import BehavioralPatternExtractor
        extractor = BehavioralPatternExtractor(self.db_path)
        patterns = extractor.extract_patterns()
        proj_a = [p for p in patterns if p["pattern_key"] == "project_a" and p["pattern_type"] == "project_success"]
        assert proj_a[0]["success_rate"] > 0.7
        assert proj_a[0]["evidence_count"] >= 5

    def test_failure_pattern_low_rate(self):
        """Projects with <30% success and 5+ evidence -> failure pattern."""
        from behavioral.behavioral_patterns import BehavioralPatternExtractor
        extractor = BehavioralPatternExtractor(self.db_path)
        patterns = extractor.extract_patterns()
        proj_b = [p for p in patterns if p["pattern_key"] == "project_b" and p["pattern_type"] == "project_success"]
        assert proj_b[0]["success_rate"] < 0.3

    def test_action_type_patterns(self):
        """Should extract patterns grouped by action_type."""
        from behavioral.behavioral_patterns import BehavioralPatternExtractor
        extractor = BehavioralPatternExtractor(self.db_path)
        patterns = extractor.extract_patterns()
        action_patterns = [p for p in patterns if p["pattern_type"] == "action_type_success"]
        assert len(action_patterns) >= 1

    def test_get_patterns_with_min_confidence(self):
        """get_patterns filters by minimum confidence."""
        from behavioral.behavioral_patterns import BehavioralPatternExtractor
        extractor = BehavioralPatternExtractor(self.db_path)
        extractor.extract_patterns()
        # Store patterns to DB first
        extractor.save_patterns()
        high_conf = extractor.get_patterns(min_confidence=0.5)
        all_patterns = extractor.get_patterns(min_confidence=0.0)
        assert len(high_conf) <= len(all_patterns)

    def test_pattern_confidence_scoring(self):
        """Patterns with more evidence should have higher confidence."""
        from behavioral.behavioral_patterns import BehavioralPatternExtractor
        extractor = BehavioralPatternExtractor(self.db_path)
        patterns = extractor.extract_patterns()
        for p in patterns:
            assert 0.0 <= p["confidence"] <= 1.0
            # Confidence should increase with evidence
            if p["evidence_count"] >= 10:
                assert p["confidence"] >= 0.5

    def test_save_patterns_to_db(self):
        """save_patterns stores extracted patterns in behavioral_patterns table."""
        from behavioral.behavioral_patterns import BehavioralPatternExtractor
        extractor = BehavioralPatternExtractor(self.db_path)
        extractor.extract_patterns()
        count = extractor.save_patterns()
        assert count >= 2
        # Verify in DB
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("SELECT COUNT(*) FROM behavioral_patterns").fetchone()
        conn.close()
        assert rows[0] >= 2
