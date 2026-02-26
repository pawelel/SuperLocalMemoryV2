# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Tests for v2.8 outcome signal types in feedback collector.
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestOutcomeSignalTypes:
    """Verify outcome signal types are registered and have correct values."""

    def test_outcome_success_registered(self):
        from learning.feedback_collector import FeedbackCollector
        assert "outcome_success" in FeedbackCollector.SIGNAL_VALUES
        assert FeedbackCollector.SIGNAL_VALUES["outcome_success"] == 1.0

    def test_outcome_partial_registered(self):
        from learning.feedback_collector import FeedbackCollector
        assert "outcome_partial" in FeedbackCollector.SIGNAL_VALUES
        assert FeedbackCollector.SIGNAL_VALUES["outcome_partial"] == 0.5

    def test_outcome_failure_registered(self):
        from learning.feedback_collector import FeedbackCollector
        assert "outcome_failure" in FeedbackCollector.SIGNAL_VALUES
        assert FeedbackCollector.SIGNAL_VALUES["outcome_failure"] == 0.0

    def test_outcome_retry_registered(self):
        from learning.feedback_collector import FeedbackCollector
        assert "outcome_retry" in FeedbackCollector.SIGNAL_VALUES
        assert FeedbackCollector.SIGNAL_VALUES["outcome_retry"] == 0.2

    def test_existing_signals_unchanged(self):
        """All 17 original signal types still present with correct values."""
        from learning.feedback_collector import FeedbackCollector
        SV = FeedbackCollector.SIGNAL_VALUES
        assert SV["mcp_used_high"] == 1.0
        assert SV["dashboard_thumbs_up"] == 1.0
        assert SV["implicit_positive_timegap"] == 0.6
        assert SV["passive_decay"] == 0.0
        assert len(SV) == 21  # 17 original + 4 new

    def test_total_signal_count(self):
        """Should have exactly 21 signal types (17 + 4)."""
        from learning.feedback_collector import FeedbackCollector
        assert len(FeedbackCollector.SIGNAL_VALUES) == 21
