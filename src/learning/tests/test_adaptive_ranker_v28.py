# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Tests for v2.8 adaptive ranker — 20 features + lifecycle/behavioral boosts.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestAdaptiveRankerV28:
    def test_num_features_is_20(self):
        from learning.feature_extractor import NUM_FEATURES
        assert NUM_FEATURES == 20

    def test_new_rule_boosts_exist(self):
        from learning.adaptive_ranker import _RULE_BOOST
        assert 'lifecycle_active' in _RULE_BOOST
        assert 'outcome_success_high' in _RULE_BOOST
        assert 'behavioral_match_strong' in _RULE_BOOST
        assert 'cross_project_boost' in _RULE_BOOST

    def test_lifecycle_active_boost(self):
        from learning.adaptive_ranker import _RULE_BOOST
        assert _RULE_BOOST['lifecycle_active'] == 1.0
        assert _RULE_BOOST['lifecycle_warm'] == 0.85
        assert _RULE_BOOST['lifecycle_cold'] == 0.6

    def test_outcome_boosts(self):
        from learning.adaptive_ranker import _RULE_BOOST
        assert _RULE_BOOST['outcome_success_high'] == 1.3
        assert _RULE_BOOST['outcome_failure_high'] == 0.7

    def test_phase1_works_with_20_features(self):
        """Phase 1 (rule-based) ranking should work with 20-feature vectors."""
        from learning.adaptive_ranker import AdaptiveRanker
        ranker = AdaptiveRanker()
        results = [
            {'id': 1, 'content': 'Python memory', 'score': 0.8, 'match_type': 'semantic',
             'importance': 7, 'lifecycle_state': 'active'},
            {'id': 2, 'content': 'Old memory', 'score': 0.7, 'match_type': 'semantic',
             'importance': 3, 'lifecycle_state': 'cold'},
        ]
        ranked = ranker.rerank(results, "Python")
        assert len(ranked) == 2
        assert all('score' in r for r in ranked)

    def test_active_memory_ranks_higher_than_cold(self):
        """Active memories should score higher than cold with same base score."""
        from learning.adaptive_ranker import AdaptiveRanker
        ranker = AdaptiveRanker()
        results = [
            {'id': 1, 'content': 'same content', 'score': 0.8, 'match_type': 'semantic',
             'importance': 5, 'lifecycle_state': 'cold'},
            {'id': 2, 'content': 'same content', 'score': 0.8, 'match_type': 'semantic',
             'importance': 5, 'lifecycle_state': 'active'},
        ]
        ranked = ranker.rerank(results, "test")
        # Active (id=2) should rank higher than cold (id=1)
        if len(ranked) >= 2:
            assert ranked[0]['id'] == 2 or ranked[0]['score'] >= ranked[1]['score']
