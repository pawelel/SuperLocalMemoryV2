# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Tests for v2.8 feature extractor — 20-dimensional feature vectors.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestFeatureExtractorV28:
    def test_feature_count_is_20(self):
        from learning.feature_extractor import FEATURE_NAMES
        assert len(FEATURE_NAMES) == 20

    def test_new_feature_names_present(self):
        from learning.feature_extractor import FEATURE_NAMES
        new_features = ['lifecycle_state', 'outcome_success_rate', 'outcome_count',
                       'behavioral_match', 'cross_project_score', 'retention_priority',
                       'trust_at_creation', 'lifecycle_aware_decay']
        for f in new_features:
            assert f in FEATURE_NAMES

    def test_extract_returns_20_features(self):
        from learning.feature_extractor import FeatureExtractor
        extractor = FeatureExtractor()
        memory = {
            'id': 1, 'content': 'test memory about Python', 'importance': 5,
            'created_at': '2026-02-20T10:00:00', 'last_accessed': '2026-02-25T10:00:00',
            'access_count': 3, 'tags': ['python'], 'project_name': 'myproject',
            'lifecycle_state': 'active', 'score': 0.8, 'match_type': 'semantic',
        }
        features = extractor.extract_features(memory, "Python programming")
        assert len(features) == 20
        assert all(isinstance(f, (int, float)) for f in features)

    def test_lifecycle_state_encoding(self):
        from learning.feature_extractor import FeatureExtractor
        extractor = FeatureExtractor()
        base = {'id': 1, 'content': 'test', 'importance': 5, 'created_at': '2026-02-20',
                'access_count': 0, 'score': 0.5, 'match_type': 'semantic'}

        active = extractor.extract_features({**base, 'lifecycle_state': 'active'}, "test")
        warm = extractor.extract_features({**base, 'lifecycle_state': 'warm'}, "test")
        cold = extractor.extract_features({**base, 'lifecycle_state': 'cold'}, "test")

        assert active[12] > warm[12] > cold[12]

    def test_default_values_when_data_missing(self):
        """Features should return sensible defaults when data is unavailable."""
        from learning.feature_extractor import FeatureExtractor
        extractor = FeatureExtractor()
        minimal = {'id': 1, 'content': 'test', 'importance': 5, 'score': 0.5, 'match_type': 'semantic'}
        features = extractor.extract_features(minimal, "test")
        assert len(features) == 20
        # lifecycle_state default (active) = 1.0
        assert features[12] == 1.0
        # outcome_success_rate default = 0.5
        assert features[13] == 0.5
        # retention_priority default = 0.5
        assert features[17] == 0.5
        # trust_at_creation default = 0.8
        assert features[18] == 0.8

    def test_backward_compat_old_12_features_still_work(self):
        """The first 12 features should still be computed correctly."""
        from learning.feature_extractor import FeatureExtractor
        extractor = FeatureExtractor()
        memory = {'id': 1, 'content': 'Python is great', 'importance': 8,
                  'created_at': '2026-02-20', 'access_count': 5, 'score': 0.9,
                  'match_type': 'semantic', 'lifecycle_state': 'active'}
        features = extractor.extract_features(memory, "Python")
        # importance_norm (index 6) should be 0.8 (8/10)
        assert abs(features[6] - 0.8) < 0.01

    def test_extract_batch_returns_20_wide(self):
        from learning.feature_extractor import FeatureExtractor
        extractor = FeatureExtractor()
        memories = [
            {'id': 1, 'content': 'mem1', 'importance': 5, 'score': 0.5, 'match_type': 'semantic'},
            {'id': 2, 'content': 'mem2', 'importance': 7, 'score': 0.7, 'match_type': 'semantic'},
        ]
        batch = extractor.extract_batch(memories, "test")
        assert len(batch) == 2
        assert all(len(v) == 20 for v in batch)

    def test_outcome_success_rate_from_memory(self):
        """If memory has outcome_success_rate in dict, use it."""
        from learning.feature_extractor import FeatureExtractor
        extractor = FeatureExtractor()
        memory = {'id': 1, 'content': 'test', 'importance': 5, 'score': 0.5,
                  'match_type': 'semantic', 'outcome_success_rate': 0.85}
        features = extractor.extract_features(memory, "test")
        assert abs(features[13] - 0.85) < 0.01
