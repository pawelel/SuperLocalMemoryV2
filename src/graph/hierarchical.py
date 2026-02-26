#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Hierarchical sub-clustering for the graph engine.

Implements recursive Leiden-based hierarchical clustering that decomposes
large communities into finer-grained thematic sub-clusters.
"""
import sqlite3
from typing import List, Dict, Tuple

from graph.constants import logger, IGRAPH_AVAILABLE, MEMORY_DIR


def _get_active_profile() -> str:
    """Get the currently active profile name from config."""
    import json
    config_file = MEMORY_DIR / "profiles.json"
    if config_file.exists():
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
            return config.get('active_profile', 'default')
        except (json.JSONDecodeError, IOError):
            pass
    return 'default'


def hierarchical_cluster(db_path, get_avg_importance_fn, generate_cluster_name_fn,
                         min_subcluster_size: int = 5, max_depth: int = 3) -> Dict[str, any]:
    """
    Run recursive Leiden clustering -- cluster the clusters.

    Large communities (>= min_subcluster_size * 2) are recursively sub-clustered
    to reveal finer-grained thematic structure.

    Args:
        db_path: Path to SQLite database
        get_avg_importance_fn: Callback to compute avg importance for memory IDs
        generate_cluster_name_fn: Callback to generate cluster name from memory IDs
        min_subcluster_size: Minimum members to attempt sub-clustering (default 5)
        max_depth: Maximum recursion depth (default 3)

    Returns:
        Dictionary with hierarchical clustering statistics
    """
    if not IGRAPH_AVAILABLE:
        logger.warning("igraph/leidenalg not installed. Hierarchical clustering disabled. Install with: pip3 install python-igraph leidenalg")
        return {'subclusters_created': 0, 'depth_reached': 0}
    import igraph as ig
    import leidenalg

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    active_profile = _get_active_profile()

    try:
        # Get top-level clusters for this profile that are large enough to sub-cluster
        cursor.execute('''
            SELECT cluster_id, COUNT(*) as cnt
            FROM memories
            WHERE cluster_id IS NOT NULL AND profile = ?
            GROUP BY cluster_id
            HAVING cnt >= ?
        ''', (active_profile, min_subcluster_size * 2))
        large_clusters = cursor.fetchall()

        if not large_clusters:
            logger.info("No clusters large enough for hierarchical decomposition")
            return {'subclusters_created': 0, 'depth_reached': 0}

        total_subclusters = 0
        max_depth_reached = 0

        for parent_cid, member_count in large_clusters:
            subs, depth = _recursive_subcluster(
                conn, cursor, parent_cid, active_profile,
                min_subcluster_size, max_depth, current_depth=1,
                get_avg_importance_fn=get_avg_importance_fn,
                generate_cluster_name_fn=generate_cluster_name_fn,
            )
            total_subclusters += subs
            max_depth_reached = max(max_depth_reached, depth)

        conn.commit()
        logger.info(f"Hierarchical clustering: {total_subclusters} sub-clusters, depth {max_depth_reached}")
        return {
            'subclusters_created': total_subclusters,
            'depth_reached': max_depth_reached,
            'parent_clusters_processed': len(large_clusters)
        }

    except Exception as e:
        logger.error(f"Hierarchical clustering failed: {e}")
        conn.rollback()
        return {'subclusters_created': 0, 'error': str(e)}
    finally:
        conn.close()


def _recursive_subcluster(conn, cursor, parent_cluster_id: int,
                           profile: str, min_size: int, max_depth: int,
                           current_depth: int,
                           get_avg_importance_fn, generate_cluster_name_fn) -> Tuple[int, int]:
    """Recursively sub-cluster a community using Leiden."""
    if not IGRAPH_AVAILABLE:
        return 0, current_depth - 1
    import igraph as ig
    import leidenalg

    if current_depth > max_depth:
        return 0, current_depth - 1

    # Get memory IDs in this cluster
    cursor.execute('''
        SELECT id FROM memories
        WHERE cluster_id = ? AND profile = ?
    ''', (parent_cluster_id, profile))
    member_ids = [row[0] for row in cursor.fetchall()]

    if len(member_ids) < min_size * 2:
        return 0, current_depth - 1

    # Get edges between members of this cluster
    placeholders = ','.join('?' * len(member_ids))
    edges = cursor.execute(f'''
        SELECT source_memory_id, target_memory_id, weight
        FROM graph_edges
        WHERE source_memory_id IN ({placeholders})
          AND target_memory_id IN ({placeholders})
    ''', member_ids + member_ids).fetchall()

    if len(edges) < 2:
        return 0, current_depth - 1

    # Build sub-graph
    id_to_vertex = {mid: idx for idx, mid in enumerate(member_ids)}
    vertex_to_id = {idx: mid for mid, idx in id_to_vertex.items()}

    g = ig.Graph()
    g.add_vertices(len(member_ids))
    edge_list, edge_weights = [], []
    for src, tgt, w in edges:
        if src in id_to_vertex and tgt in id_to_vertex:
            edge_list.append((id_to_vertex[src], id_to_vertex[tgt]))
            edge_weights.append(w)

    if not edge_list:
        return 0, current_depth - 1

    g.add_edges(edge_list)

    # Run Leiden with higher resolution for finer communities
    partition = leidenalg.find_partition(
        g, leidenalg.ModularityVertexPartition,
        weights=edge_weights, n_iterations=100, seed=42
    )

    # Only proceed if Leiden found > 1 community (actual split)
    non_singleton = [c for c in partition if len(c) >= 2]
    if len(non_singleton) <= 1:
        return 0, current_depth - 1

    subclusters_created = 0
    deepest = current_depth

    # Get parent depth
    cursor.execute('SELECT depth FROM graph_clusters WHERE id = ?', (parent_cluster_id,))
    parent_row = cursor.fetchone()
    parent_depth = parent_row[0] if parent_row else 0

    for community in non_singleton:
        sub_member_ids = [vertex_to_id[v] for v in community]

        if len(sub_member_ids) < 2:
            continue

        avg_imp = get_avg_importance_fn(cursor, sub_member_ids)
        cluster_name = generate_cluster_name_fn(cursor, sub_member_ids)

        result = cursor.execute('''
            INSERT INTO graph_clusters (name, member_count, avg_importance, parent_cluster_id, depth)
            VALUES (?, ?, ?, ?, ?)
        ''', (cluster_name, len(sub_member_ids), avg_imp, parent_cluster_id, parent_depth + 1))

        sub_cluster_id = result.lastrowid

        # Update memories to point to sub-cluster
        cursor.executemany('''
            UPDATE memories SET cluster_id = ? WHERE id = ?
        ''', [(sub_cluster_id, mid) for mid in sub_member_ids])

        subclusters_created += 1
        logger.info(f"Sub-cluster {sub_cluster_id} under {parent_cluster_id}: "
                    f"'{cluster_name}' ({len(sub_member_ids)} members, depth {parent_depth + 1})")

        # Recurse into this sub-cluster if large enough
        child_subs, child_depth = _recursive_subcluster(
            conn, cursor, sub_cluster_id, profile,
            min_size, max_depth, current_depth + 1,
            get_avg_importance_fn=get_avg_importance_fn,
            generate_cluster_name_fn=generate_cluster_name_fn,
        )
        subclusters_created += child_subs
        deepest = max(deepest, child_depth)

    return subclusters_created, deepest
