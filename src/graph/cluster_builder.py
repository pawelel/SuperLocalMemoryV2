#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Community detection and cluster management for the graph engine.

Implements Leiden algorithm based community detection. Hierarchical
sub-clustering is delegated to the ``hierarchical`` module.
"""
import sqlite3
import json
from typing import List, Dict
from collections import Counter

from graph.constants import logger, IGRAPH_AVAILABLE, MEMORY_DIR
from graph.cluster_summary import generate_cluster_summaries as _generate_summaries
from graph.hierarchical import hierarchical_cluster as _hierarchical_cluster


class ClusterBuilder:
    """Detect memory communities using Leiden algorithm."""

    def __init__(self, db_path):
        """Initialize cluster builder."""
        self.db_path = db_path

    def _get_active_profile(self) -> str:
        """Get the currently active profile name from config."""
        config_file = MEMORY_DIR / "profiles.json"
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
                return config.get('active_profile', 'default')
            except (json.JSONDecodeError, IOError):
                pass
        return 'default'

    def detect_communities(self) -> int:
        """
        Run Leiden algorithm to find memory clusters (active profile only).

        Returns:
            Number of clusters created
        """
        if not IGRAPH_AVAILABLE:
            logger.warning("igraph/leidenalg not installed. Graph clustering disabled. Install with: pip3 install python-igraph leidenalg")
            return 0
        import igraph as ig
        import leidenalg

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        active_profile = self._get_active_profile()

        try:
            # Load edges for active profile's memories only
            edges = cursor.execute('''
                SELECT ge.source_memory_id, ge.target_memory_id, ge.weight
                FROM graph_edges ge
                WHERE ge.source_memory_id IN (SELECT id FROM memories WHERE profile = ?)
                  AND ge.target_memory_id IN (SELECT id FROM memories WHERE profile = ?)
            ''', (active_profile, active_profile)).fetchall()

            if not edges:
                logger.warning("No edges found - cannot build clusters")
                return 0

            # Build memory ID mapping
            memory_ids = set()
            for source, target, _ in edges:
                memory_ids.add(source)
                memory_ids.add(target)

            memory_ids = sorted(list(memory_ids))
            memory_id_to_vertex = {mid: idx for idx, mid in enumerate(memory_ids)}
            vertex_to_memory_id = {idx: mid for mid, idx in memory_id_to_vertex.items()}

            # Create igraph graph
            g = ig.Graph()
            g.add_vertices(len(memory_ids))

            edge_list = []
            edge_weights = []
            for source, target, weight in edges:
                edge_list.append((memory_id_to_vertex[source], memory_id_to_vertex[target]))
                edge_weights.append(weight)

            g.add_edges(edge_list)

            # Run Leiden algorithm
            logger.info(f"Running Leiden on {len(memory_ids)} nodes, {len(edges)} edges")
            partition = leidenalg.find_partition(
                g, leidenalg.ModularityVertexPartition,
                weights=edge_weights, n_iterations=100, seed=42
            )

            clusters_created = 0
            for cluster_idx, community in enumerate(partition):
                if len(community) < 2:
                    continue

                cluster_memory_ids = [vertex_to_memory_id[v] for v in community]
                avg_importance = self._get_avg_importance(cursor, cluster_memory_ids)
                cluster_name = self._generate_cluster_name(cursor, cluster_memory_ids)

                result = cursor.execute('''
                    INSERT INTO graph_clusters (name, member_count, avg_importance)
                    VALUES (?, ?, ?)
                ''', (cluster_name, len(cluster_memory_ids), avg_importance))

                cluster_id = result.lastrowid
                cursor.executemany('''
                    UPDATE memories SET cluster_id = ? WHERE id = ?
                ''', [(cluster_id, mid) for mid in cluster_memory_ids])

                clusters_created += 1
                logger.info(f"Cluster {cluster_id}: '{cluster_name}' ({len(cluster_memory_ids)} members)")

            conn.commit()
            logger.info(f"Created {clusters_created} clusters")
            return clusters_created

        except Exception as e:
            logger.error(f"Community detection failed: {e}")
            conn.rollback()
            return 0
        finally:
            conn.close()

    def _get_avg_importance(self, cursor, memory_ids: List[int]) -> float:
        """Calculate average importance for cluster."""
        placeholders = ','.join('?' * len(memory_ids))
        result = cursor.execute(f'''
            SELECT AVG(importance) FROM memories WHERE id IN ({placeholders})
        ''', memory_ids).fetchone()
        return result[0] if result and result[0] else 5.0

    def _generate_cluster_name(self, cursor, memory_ids: List[int]) -> str:
        """Generate cluster name from member entities (TF-IDF approach)."""
        placeholders = ','.join('?' * len(memory_ids))
        nodes = cursor.execute(f'''
            SELECT entities FROM graph_nodes WHERE memory_id IN ({placeholders})
        ''', memory_ids).fetchall()

        all_entities = []
        for node in nodes:
            if node[0]:
                all_entities.extend(json.loads(node[0]))

        if not all_entities:
            return f"Cluster (ID auto-assigned)"

        entity_counts = Counter(all_entities)
        top_entities = [e for e, _ in entity_counts.most_common(3)]

        if len(top_entities) >= 2:
            name = f"{top_entities[0].title()} & {top_entities[1].title()}"
        elif len(top_entities) == 1:
            name = f"{top_entities[0].title()} Contexts"
        else:
            name = "Mixed Contexts"

        return name[:100]

    def hierarchical_cluster(self, min_subcluster_size: int = 5, max_depth: int = 3) -> Dict[str, any]:
        """
        Run recursive Leiden clustering -- cluster the clusters.

        Delegates to the hierarchical module.

        Args:
            min_subcluster_size: Minimum members to attempt sub-clustering (default 5)
            max_depth: Maximum recursion depth (default 3)

        Returns:
            Dictionary with hierarchical clustering statistics
        """
        return _hierarchical_cluster(
            self.db_path,
            get_avg_importance_fn=self._get_avg_importance,
            generate_cluster_name_fn=self._generate_cluster_name,
            min_subcluster_size=min_subcluster_size,
            max_depth=max_depth,
        )

    def generate_cluster_summaries(self) -> int:
        """Generate TF-IDF structured summaries for all clusters."""
        return _generate_summaries(self.db_path)
