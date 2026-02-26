# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Tests for explicit action outcome recording.
"""
import sqlite3
import tempfile
import os
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestOutcomeTracker:
    """Test outcome recording and querying."""

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "learning.db")

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_record_success(self):
        from behavioral.outcome_tracker import OutcomeTracker
        tracker = OutcomeTracker(self.db_path)
        oid = tracker.record_outcome([1, 2], "success", action_type="code_written")
        assert isinstance(oid, int)
        assert oid > 0

    def test_record_failure(self):
        from behavioral.outcome_tracker import OutcomeTracker
        tracker = OutcomeTracker(self.db_path)
        oid = tracker.record_outcome([3], "failure", context={"error": "timeout"})
        assert oid > 0

    def test_record_partial(self):
        from behavioral.outcome_tracker import OutcomeTracker
        tracker = OutcomeTracker(self.db_path)
        oid = tracker.record_outcome([1], "partial", action_type="debug_resolved")
        assert oid > 0

    def test_confidence_for_explicit(self):
        """Explicit outcomes should have confidence >= 0.8."""
        from behavioral.outcome_tracker import OutcomeTracker
        tracker = OutcomeTracker(self.db_path)
        tracker.record_outcome([1], "success")
        outcomes = tracker.get_outcomes()
        assert outcomes[0]["confidence"] >= 0.8

    def test_multiple_memory_ids(self):
        from behavioral.outcome_tracker import OutcomeTracker
        tracker = OutcomeTracker(self.db_path)
        tracker.record_outcome([1, 2, 3], "success")
        outcomes = tracker.get_outcomes()
        assert len(outcomes[0]["memory_ids"]) == 3

    def test_get_outcomes_by_memory(self):
        from behavioral.outcome_tracker import OutcomeTracker
        tracker = OutcomeTracker(self.db_path)
        tracker.record_outcome([1, 2], "success")
        tracker.record_outcome([3], "failure")
        results = tracker.get_outcomes(memory_id=1)
        assert len(results) == 1

    def test_get_outcomes_by_project(self):
        from behavioral.outcome_tracker import OutcomeTracker
        tracker = OutcomeTracker(self.db_path)
        tracker.record_outcome([1], "success", project="proj_a")
        tracker.record_outcome([2], "failure", project="proj_b")
        results = tracker.get_outcomes(project="proj_a")
        assert len(results) == 1

    def test_get_success_rate(self):
        from behavioral.outcome_tracker import OutcomeTracker
        tracker = OutcomeTracker(self.db_path)
        tracker.record_outcome([1], "success")
        tracker.record_outcome([1], "success")
        tracker.record_outcome([1], "failure")
        rate = tracker.get_success_rate(1)
        assert abs(rate - 0.667) < 0.01  # 2/3

    def test_success_rate_no_outcomes(self):
        from behavioral.outcome_tracker import OutcomeTracker
        tracker = OutcomeTracker(self.db_path)
        rate = tracker.get_success_rate(999)
        assert rate == 0.0

    def test_valid_outcomes_only(self):
        """Only success, failure, partial are valid outcomes."""
        from behavioral.outcome_tracker import OutcomeTracker
        tracker = OutcomeTracker(self.db_path)
        result = tracker.record_outcome([1], "invalid_outcome")
        assert result is None  # Rejected
