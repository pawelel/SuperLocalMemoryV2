#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Individual search methods (BM25, semantic, graph) for hybrid search.
"""
from typing import List, Tuple


class SearchMethodsMixin:
    """
    Mixin providing individual search method implementations.

    Expects the host class to have:
        - self.bm25: BM25SearchEngine
        - self.optimizer: QueryOptimizer
        - self._tfidf_vectorizer
        - self._tfidf_vectors
        - self._memory_ids: list
        - self._load_graph_engine() method
        - self.search_bm25() method (for graph seed)
    """

    def search_bm25(
        self,
        query: str,
        limit: int = 10,
        score_threshold: float = 0.0
    ) -> List[Tuple[int, float]]:
        """
        Search using BM25 keyword matching.

        Args:
            query: Search query
            limit: Maximum results
            score_threshold: Minimum score threshold

        Returns:
            List of (memory_id, score) tuples
        """
        # Optimize query
        optimized = self.optimizer.optimize(
            query,
            enable_spell_correction=True,
            enable_expansion=False  # Expansion can hurt precision
        )

        # Search with BM25
        results = self.bm25.search(optimized, limit, score_threshold)

        return results

    def search_semantic(
        self,
        query: str,
        limit: int = 10,
        score_threshold: float = 0.05
    ) -> List[Tuple[int, float]]:
        """
        Search using TF-IDF semantic similarity.

        Args:
            query: Search query
            limit: Maximum results
            score_threshold: Minimum similarity threshold

        Returns:
            List of (memory_id, score) tuples
        """
        if self._tfidf_vectorizer is None or self._tfidf_vectors is None:
            return []

        try:
            from sklearn.metrics.pairwise import cosine_similarity
            import numpy as np

            # Vectorize query
            query_vec = self._tfidf_vectorizer.transform([query])

            # Calculate similarities
            similarities = cosine_similarity(query_vec, self._tfidf_vectors).flatten()

            # Get top results above threshold
            results = []
            for idx, score in enumerate(similarities):
                if score >= score_threshold:
                    memory_id = self._memory_ids[idx]
                    results.append((memory_id, float(score)))

            # Sort by score and limit
            results.sort(key=lambda x: x[1], reverse=True)
            return results[:limit]

        except Exception as e:
            # Fallback gracefully
            return []

    def search_graph(
        self,
        query: str,
        limit: int = 10,
        max_depth: int = 2
    ) -> List[Tuple[int, float]]:
        """
        Search using graph traversal from initial matches.

        Strategy:
        1. Get seed memories from BM25
        2. Traverse graph to find related memories
        3. Score by distance from seed nodes

        Args:
            query: Search query
            limit: Maximum results
            max_depth: Maximum graph traversal depth

        Returns:
            List of (memory_id, score) tuples
        """
        graph = self._load_graph_engine()
        if graph is None:
            return []

        # Get seed memories from BM25
        seed_results = self.search_bm25(query, limit=5)
        if not seed_results:
            return []

        seed_ids = [mem_id for mem_id, _ in seed_results]

        # Traverse graph from seed nodes
        visited = set(seed_ids)
        results = []

        # BFS traversal
        queue = [(mem_id, 1.0, 0) for mem_id in seed_ids]  # (id, score, depth)

        while queue and len(results) < limit:
            current_id, current_score, depth = queue.pop(0)

            if depth > max_depth:
                continue

            # Add to results
            if current_id not in [r[0] for r in results]:
                results.append((current_id, current_score))

            # Get related memories from graph
            try:
                related = graph.get_related_memories(current_id, limit=5)

                for rel_id, similarity in related:
                    if rel_id not in visited:
                        visited.add(rel_id)
                        # Decay score by depth
                        new_score = current_score * similarity * (0.7 ** depth)
                        queue.append((rel_id, new_score, depth + 1))

            except Exception:
                # Graph operation failed - skip
                continue

        return results[:limit]
