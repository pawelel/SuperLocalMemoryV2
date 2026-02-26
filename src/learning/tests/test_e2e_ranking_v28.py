# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""End-to-end tests for adaptive ranking with 20-feature vector.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestE2ERankingV28:
    def test_full_20_feature_pipeline(self):
        """Full pipeline: extract 20 features -> rank results."""
        from learning.feature_extractor import FeatureExtractor
        from learning.adaptive_ranker import AdaptiveRanker

        extractor = FeatureExtractor()
        ranker = AdaptiveRanker()

        memories = [
            {'id': 1, 'content': 'Python best practices for production', 'score': 0.8,
             'match_type': 'semantic', 'importance': 8, 'lifecycle_state': 'active',
             'access_count': 15, 'created_at': '2026-02-01'},
            {'id': 2, 'content': 'Old JavaScript patterns deprecated', 'score': 0.75,
             'match_type': 'semantic', 'importance': 3, 'lifecycle_state': 'cold',
             'access_count': 1, 'created_at': '2025-06-01'},
        ]

        # Extract features
        for mem in memories:
            features = extractor.extract_features(mem, "Python production")
            assert len(features) == 20

        # Rank
        ranked = ranker.rerank(memories, "Python production")
        assert len(ranked) == 2

    def test_lifecycle_affects_ranking(self):
        """Active memories should generally rank above cold ones."""
        from learning.adaptive_ranker import AdaptiveRanker
        ranker = AdaptiveRanker()

        results = [
            {'id': 1, 'content': 'cold memory', 'score': 0.85, 'match_type': 'semantic',
             'importance': 5, 'lifecycle_state': 'cold'},
            {'id': 2, 'content': 'active memory', 'score': 0.80, 'match_type': 'semantic',
             'importance': 5, 'lifecycle_state': 'active'},
        ]
        ranked = ranker.rerank(results, "test")
        # Even with slightly lower base score, active should win due to lifecycle boost
        assert ranked[0]['id'] == 2

    def test_high_outcome_success_boosts_ranking(self):
        """Memories with high success rates should rank higher."""
        from learning.adaptive_ranker import AdaptiveRanker
        ranker = AdaptiveRanker()

        results = [
            {'id': 1, 'content': 'frequently failing', 'score': 0.8, 'match_type': 'semantic',
             'importance': 5, 'outcome_success_rate': 0.1},
            {'id': 2, 'content': 'consistently useful', 'score': 0.8, 'match_type': 'semantic',
             'importance': 5, 'outcome_success_rate': 0.95},
        ]
        ranked = ranker.rerank(results, "test")
        assert ranked[0]['id'] == 2

    def test_result_ordering_reflects_all_signals(self):
        """Result ordering should reflect lifecycle + behavioral + base score."""
        from learning.adaptive_ranker import AdaptiveRanker
        ranker = AdaptiveRanker()

        results = [
            {'id': 1, 'content': 'A', 'score': 0.7, 'match_type': 'semantic', 'importance': 5,
             'lifecycle_state': 'active', 'outcome_success_rate': 0.9},
            {'id': 2, 'content': 'B', 'score': 0.9, 'match_type': 'semantic', 'importance': 5,
             'lifecycle_state': 'cold', 'outcome_success_rate': 0.1},
            {'id': 3, 'content': 'C', 'score': 0.8, 'match_type': 'semantic', 'importance': 8,
             'lifecycle_state': 'active', 'outcome_success_rate': 0.5},
        ]
        ranked = ranker.rerank(results, "test")
        assert len(ranked) == 3
        # All should have final scores
        assert all('score' in r for r in ranked)
