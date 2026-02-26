# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Tests for implicit outcome inference from recall behavior patterns.
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestOutcomeInference:
    """Test inference rules for implicit outcome detection."""

    def test_no_requery_implies_success(self):
        """No re-query for 10+ min after recall -> success (0.6)."""
        from behavioral.outcome_inference import OutcomeInference
        engine = OutcomeInference()
        now = datetime.now()
        # Record a recall event
        engine.record_recall("query_abc", [1, 2], now - timedelta(minutes=12))
        # Infer outcomes after enough time has passed
        results = engine.infer_outcomes(now)
        assert len(results) >= 1
        result = results[0]
        assert result["outcome"] == "success"
        assert abs(result["confidence"] - 0.6) < 0.01

    def test_memory_used_high_confirms_success(self):
        """memory_used(high) within 5 min -> confirmed success (0.8)."""
        from behavioral.outcome_inference import OutcomeInference
        engine = OutcomeInference()
        now = datetime.now()
        engine.record_recall("query_abc", [1], now - timedelta(minutes=3))
        engine.record_usage("query_abc", signal="mcp_used_high", timestamp=now - timedelta(minutes=1))
        results = engine.infer_outcomes(now)
        success_results = [r for r in results if r["outcome"] == "success"]
        assert len(success_results) >= 1
        assert success_results[0]["confidence"] >= 0.8

    def test_immediate_requery_implies_failure(self):
        """Immediate re-query with different terms -> failure (0.2)."""
        from behavioral.outcome_inference import OutcomeInference
        engine = OutcomeInference()
        now = datetime.now()
        engine.record_recall("query_abc", [1], now - timedelta(minutes=1))
        engine.record_recall("different_query", [3], now - timedelta(seconds=30))
        results = engine.infer_outcomes(now)
        failure_results = [r for r in results if r["outcome"] == "failure"]
        assert len(failure_results) >= 1
        assert failure_results[0]["confidence"] <= 0.3

    def test_memory_deleted_implies_failure(self):
        """Memory deleted within 1 hour -> failure (0.0)."""
        from behavioral.outcome_inference import OutcomeInference
        engine = OutcomeInference()
        now = datetime.now()
        engine.record_recall("query_abc", [1], now - timedelta(minutes=30))
        engine.record_deletion(memory_id=1, timestamp=now - timedelta(minutes=5))
        results = engine.infer_outcomes(now)
        failure_results = [r for r in results if r["outcome"] == "failure" and 1 in r["memory_ids"]]
        assert len(failure_results) >= 1
        assert failure_results[0]["confidence"] <= 0.05

    def test_rapid_fire_queries_implies_failure(self):
        """3+ queries in 2 min -> failure (0.1)."""
        from behavioral.outcome_inference import OutcomeInference
        engine = OutcomeInference()
        now = datetime.now()
        engine.record_recall("q1", [1], now - timedelta(seconds=90))
        engine.record_recall("q2", [2], now - timedelta(seconds=60))
        engine.record_recall("q3", [3], now - timedelta(seconds=30))
        results = engine.infer_outcomes(now)
        # At least some should be failure due to rapid-fire pattern
        failure_results = [r for r in results if r["outcome"] == "failure"]
        assert len(failure_results) >= 1

    def test_cross_tool_access_implies_success(self):
        """Cross-tool access after recall -> success (0.7)."""
        from behavioral.outcome_inference import OutcomeInference
        engine = OutcomeInference()
        now = datetime.now()
        engine.record_recall("query_abc", [1], now - timedelta(minutes=3))
        engine.record_usage("query_abc", signal="implicit_positive_cross_tool", timestamp=now - timedelta(minutes=1))
        results = engine.infer_outcomes(now)
        success_results = [r for r in results if r["outcome"] == "success"]
        assert len(success_results) >= 1
        assert success_results[0]["confidence"] >= 0.7

    def test_empty_buffer_returns_empty(self):
        """No recorded events -> no inferences."""
        from behavioral.outcome_inference import OutcomeInference
        engine = OutcomeInference()
        results = engine.infer_outcomes(datetime.now())
        assert results == []

    def test_infer_clears_processed_events(self):
        """After inference, processed events are cleared from buffer."""
        from behavioral.outcome_inference import OutcomeInference
        engine = OutcomeInference()
        now = datetime.now()
        engine.record_recall("q1", [1], now - timedelta(minutes=12))
        results1 = engine.infer_outcomes(now)
        assert len(results1) >= 1
        # Second call should have nothing new
        results2 = engine.infer_outcomes(now)
        assert len(results2) == 0
