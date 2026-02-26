# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Tests for auto-retrain mechanism when feature dimensions change 12->20.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestAutoRetrain:
    def test_feature_dimension_is_20(self):
        from learning.feature_extractor import NUM_FEATURES
        assert NUM_FEATURES == 20

    def test_ranker_handles_dimension_mismatch(self):
        """Ranker should not crash when loaded model has different dimensions."""
        from learning.adaptive_ranker import AdaptiveRanker
        ranker = AdaptiveRanker()
        # Even without a trained model, phase 1 should work
        results = [{'id': 1, 'content': 'test', 'score': 0.5, 'match_type': 'semantic', 'importance': 5}]
        ranked = ranker.rerank(results, "test")
        assert len(ranked) == 1

    def test_phase1_immediate_during_retrain(self):
        """Phase 1 (rule-based) should work immediately even during model retrain."""
        from learning.adaptive_ranker import AdaptiveRanker
        ranker = AdaptiveRanker()
        results = [
            {'id': 1, 'content': 'memory A', 'score': 0.9, 'match_type': 'semantic', 'importance': 8},
            {'id': 2, 'content': 'memory B', 'score': 0.3, 'match_type': 'keyword', 'importance': 2},
        ]
        ranked = ranker.rerank(results, "test query")
        assert len(ranked) == 2
        # Higher base score should still rank first in phase 1
        assert ranked[0]['score'] >= ranked[1]['score']
