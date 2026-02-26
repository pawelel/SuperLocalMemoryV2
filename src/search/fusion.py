#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Score fusion strategies for combining multi-method search results.
"""
from collections import defaultdict
from typing import List, Dict, Tuple


class FusionMixin:
    """
    Mixin providing score normalization and fusion strategies.

    No external dependencies -- operates purely on (id, score) tuples.
    """

    def _normalize_scores(
        self,
        results: List[Tuple[int, float]]
    ) -> List[Tuple[int, float]]:
        """
        Normalize scores to [0, 1] range using min-max normalization.

        Args:
            results: List of (id, score) tuples

        Returns:
            Normalized results
        """
        if not results:
            return []

        scores = [score for _, score in results]
        min_score = min(scores)
        max_score = max(scores)

        if max_score == min_score:
            # All scores equal - return uniform scores
            return [(id, 1.0) for id, _ in results]

        normalized = []
        for mem_id, score in results:
            norm_score = (score - min_score) / (max_score - min_score)
            normalized.append((mem_id, norm_score))

        return normalized

    def _reciprocal_rank_fusion(
        self,
        results_list: List[List[Tuple[int, float]]],
        k: int = 60
    ) -> List[Tuple[int, float]]:
        """
        Combine multiple result lists using Reciprocal Rank Fusion.

        RRF formula: score(d) = sum 1 / (k + rank(d))

        RRF is rank-based and doesn't depend on score magnitudes,
        making it robust to different scoring scales.

        Args:
            results_list: List of result lists from different methods
            k: RRF constant (default: 60, standard value)

        Returns:
            Fused results sorted by RRF score
        """
        # Build rank maps for each method
        rrf_scores = defaultdict(float)

        for results in results_list:
            for rank, (mem_id, _) in enumerate(results, start=1):
                rrf_scores[mem_id] += 1.0 / (k + rank)

        # Convert to sorted list
        fused = [(mem_id, score) for mem_id, score in rrf_scores.items()]
        fused.sort(key=lambda x: x[1], reverse=True)

        return fused

    def _weighted_fusion(
        self,
        results_dict: Dict[str, List[Tuple[int, float]]],
        weights: Dict[str, float]
    ) -> List[Tuple[int, float]]:
        """
        Combine results using weighted score fusion.

        Normalizes scores from each method then combines with weights.

        Args:
            results_dict: Dictionary mapping method name to results
            weights: Dictionary mapping method name to weight

        Returns:
            Fused results sorted by combined score
        """
        # Normalize scores for each method
        normalized = {}
        for method, results in results_dict.items():
            normalized[method] = self._normalize_scores(results)

        # Combine with weights
        combined_scores = defaultdict(float)
        max_weight_sum = defaultdict(float)  # Track possible max score per doc

        for method, results in normalized.items():
            weight = weights.get(method, 0.0)

            for mem_id, score in results:
                combined_scores[mem_id] += weight * score
                max_weight_sum[mem_id] += weight

        # Normalize by actual weights (some docs may not appear in all methods)
        fused = []
        for mem_id, score in combined_scores.items():
            normalized_score = score / max_weight_sum[mem_id] if max_weight_sum[mem_id] > 0 else 0
            fused.append((mem_id, normalized_score))

        fused.sort(key=lambda x: x[1], reverse=True)

        return fused
