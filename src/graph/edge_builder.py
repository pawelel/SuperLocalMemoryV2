#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Edge building for the graph engine.

Builds similarity edges between memories based on entity overlap
and TF-IDF vector cosine similarity. Supports HNSW-accelerated
edge building for large datasets.
"""
import sqlite3
import json
from pathlib import Path
from typing import List

import numpy as np

from graph.constants import logger, cosine_similarity


class EdgeBuilder:
    """Build similarity edges between memories based on entity overlap."""

    def __init__(self, db_path: Path, min_similarity: float = 0.3):
        """
        Initialize edge builder.

        Args:
            db_path: Path to SQLite database
            min_similarity: Minimum cosine similarity to create edge
        """
        self.db_path = db_path
        self.min_similarity = min_similarity

    def build_edges(self, memory_ids: List[int], vectors: np.ndarray,
                   entities_list: List[List[str]]) -> int:
        """
        Build edges between similar memories.

        Args:
            memory_ids: List of memory IDs
            vectors: TF-IDF vectors (n x features)
            entities_list: List of entity lists per memory

        Returns:
            Number of edges created
        """
        if len(memory_ids) < 2:
            logger.warning("Need at least 2 memories to build edges")
            return 0

        # Try HNSW-accelerated edge building first (O(n log n))
        use_hnsw = False
        try:
            from hnsw_index import HNSWIndex
            if len(memory_ids) >= 50:  # HNSW overhead not worth it for small sets
                use_hnsw = True
        except ImportError:
            pass

        edges_added = 0
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            if use_hnsw:
                logger.info("Using HNSW-accelerated edge building for %d memories", len(memory_ids))
                try:
                    dim = vectors.shape[1]
                    hnsw = HNSWIndex(dimension=dim, max_elements=len(memory_ids))
                    hnsw.build(vectors, memory_ids)

                    for i in range(len(memory_ids)):
                        neighbors = hnsw.search(vectors[i], k=min(20, len(memory_ids) - 1))
                        for neighbor_id, similarity in neighbors:
                            if neighbor_id == memory_ids[i]:
                                continue  # Skip self
                            # Only process each pair once (lower ID first)
                            if memory_ids[i] > neighbor_id:
                                continue
                            if similarity >= self.min_similarity:
                                # Find indices for entity lookup
                                j = memory_ids.index(neighbor_id)
                                entities_i = set(entities_list[i])
                                entities_j = set(entities_list[j])
                                shared = list(entities_i & entities_j)
                                rel_type = self._classify_relationship(similarity, shared)

                                cursor.execute('''
                                    INSERT OR REPLACE INTO graph_edges
                                    (source_memory_id, target_memory_id, relationship_type,
                                     weight, shared_entities, similarity_score)
                                    VALUES (?, ?, ?, ?, ?, ?)
                                ''', (
                                    memory_ids[i], neighbor_id, rel_type,
                                    float(similarity), json.dumps(shared), float(similarity)
                                ))
                                edges_added += 1

                except Exception as e:
                    logger.warning("HNSW edge building failed, falling back to O(n²): %s", e)
                    use_hnsw = False  # Fall through to O(n²) below

            if not use_hnsw:
                # Fallback: O(n²) pairwise cosine similarity
                similarity_matrix = cosine_similarity(vectors)

                for i in range(len(memory_ids)):
                    for j in range(i + 1, len(memory_ids)):
                        sim = similarity_matrix[i, j]

                        if sim >= self.min_similarity:
                            entities_i = set(entities_list[i])
                            entities_j = set(entities_list[j])
                            shared = list(entities_i & entities_j)
                            rel_type = self._classify_relationship(sim, shared)

                            cursor.execute('''
                                INSERT OR REPLACE INTO graph_edges
                                (source_memory_id, target_memory_id, relationship_type,
                                 weight, shared_entities, similarity_score)
                                VALUES (?, ?, ?, ?, ?, ?)
                            ''', (
                                memory_ids[i], memory_ids[j], rel_type,
                                float(sim), json.dumps(shared), float(sim)
                            ))
                            edges_added += 1

            conn.commit()
            logger.info(f"Created {edges_added} edges")
            return edges_added

        except Exception as e:
            logger.error(f"Edge building failed: {e}")
            conn.rollback()
            return 0
        finally:
            conn.close()

    def _classify_relationship(self, similarity: float, shared_entities: List[str]) -> str:
        """
        Classify edge type based on similarity and shared entities.

        Args:
            similarity: Cosine similarity score
            shared_entities: List of shared entity strings

        Returns:
            Relationship type: 'similar', 'depends_on', or 'related_to'
        """
        # Check for dependency keywords
        dependency_keywords = {'dependency', 'require', 'import', 'use', 'need'}
        has_dependency = any(
            any(kw in entity.lower() for kw in dependency_keywords)
            for entity in shared_entities
        )

        if similarity > 0.7:
            return 'similar'
        elif has_dependency:
            return 'depends_on'
        else:
            return 'related_to'
