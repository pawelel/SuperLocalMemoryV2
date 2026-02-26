#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Graph traversal and query operations.

Provides graph traversal (get_related), cluster membership queries,
and graph statistics collection for the active profile.
"""
import sqlite3
import json
from pathlib import Path
from typing import List, Dict

from graph.constants import logger, MEMORY_DIR


def _get_active_profile() -> str:
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


def get_related(db_path: Path, memory_id: int, max_hops: int = 2) -> List[Dict]:
    """
    Get memories connected to this memory via graph edges (active profile only).

    Args:
        db_path: Path to SQLite database
        memory_id: Source memory ID
        max_hops: Maximum traversal depth (1 or 2)

    Returns:
        List of related memory dictionaries
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    active_profile = _get_active_profile()

    try:
        # Get 1-hop neighbors (filtered to active profile)
        edges = cursor.execute('''
            SELECT ge.target_memory_id, ge.relationship_type, ge.weight, ge.shared_entities
            FROM graph_edges ge
            JOIN memories m ON ge.target_memory_id = m.id
            WHERE ge.source_memory_id = ? AND m.profile = ?
            UNION
            SELECT ge.source_memory_id, ge.relationship_type, ge.weight, ge.shared_entities
            FROM graph_edges ge
            JOIN memories m ON ge.source_memory_id = m.id
            WHERE ge.target_memory_id = ? AND m.profile = ?
        ''', (memory_id, active_profile, memory_id, active_profile)).fetchall()

        results = []
        seen_ids = {memory_id}

        for target_id, rel_type, weight, shared_entities in edges:
            if target_id in seen_ids:
                continue

            seen_ids.add(target_id)

            # Get memory details
            memory = cursor.execute('''
                SELECT id, summary, importance, tags
                FROM memories WHERE id = ?
            ''', (target_id,)).fetchone()

            if memory:
                results.append({
                    'id': memory[0],
                    'summary': memory[1],
                    'importance': memory[2],
                    'tags': json.loads(memory[3]) if memory[3] else [],
                    'relationship': rel_type,
                    'weight': weight,
                    'shared_entities': json.loads(shared_entities) if shared_entities else [],
                    'hops': 1
                })

        # If max_hops == 2, get 2-hop neighbors
        if max_hops >= 2:
            for result in results[:]:  # Copy to avoid modification during iteration
                second_hop = cursor.execute('''
                    SELECT target_memory_id, relationship_type, weight
                    FROM graph_edges
                    WHERE source_memory_id = ?
                    UNION
                    SELECT source_memory_id, relationship_type, weight
                    FROM graph_edges
                    WHERE target_memory_id = ?
                ''', (result['id'], result['id'])).fetchall()

                for target_id, rel_type, weight in second_hop:
                    if target_id in seen_ids:
                        continue

                    seen_ids.add(target_id)

                    memory = cursor.execute('''
                        SELECT id, summary, importance, tags
                        FROM memories WHERE id = ?
                    ''', (target_id,)).fetchone()

                    if memory:
                        results.append({
                            'id': memory[0],
                            'summary': memory[1],
                            'importance': memory[2],
                            'tags': json.loads(memory[3]) if memory[3] else [],
                            'relationship': rel_type,
                            'weight': weight,
                            'shared_entities': [],
                            'hops': 2
                        })

        # Sort by weight (strongest connections first)
        results.sort(key=lambda x: (-x['hops'], -x['weight']))

        return results

    finally:
        conn.close()


def get_cluster_members(db_path: Path, cluster_id: int) -> List[Dict]:
    """
    Get all memories in a cluster (filtered by active profile).

    Args:
        db_path: Path to SQLite database
        cluster_id: Cluster ID

    Returns:
        List of memory dictionaries
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    active_profile = _get_active_profile()

    try:
        memories = cursor.execute('''
            SELECT id, summary, importance, tags, created_at
            FROM memories
            WHERE cluster_id = ? AND profile = ?
            ORDER BY importance DESC
        ''', (cluster_id, active_profile)).fetchall()

        return [
            {
                'id': m[0],
                'summary': m[1],
                'importance': m[2],
                'tags': json.loads(m[3]) if m[3] else [],
                'created_at': m[4]
            }
            for m in memories
        ]

    finally:
        conn.close()


def get_stats(db_path: Path) -> Dict[str, any]:
    """Get graph statistics for the active profile."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    active_profile = _get_active_profile()

    try:
        # Count nodes for active profile's memories
        nodes = cursor.execute('''
            SELECT COUNT(*) FROM graph_nodes
            WHERE memory_id IN (SELECT id FROM memories WHERE profile = ?)
        ''', (active_profile,)).fetchone()[0]

        # Count edges where at least one end is in active profile
        edges = cursor.execute('''
            SELECT COUNT(*) FROM graph_edges
            WHERE source_memory_id IN (SELECT id FROM memories WHERE profile = ?)
        ''', (active_profile,)).fetchone()[0]

        # Clusters that have members in active profile
        clusters = cursor.execute('''
            SELECT COUNT(DISTINCT cluster_id) FROM memories
            WHERE cluster_id IS NOT NULL AND profile = ?
        ''', (active_profile,)).fetchone()[0]

        # Cluster breakdown for active profile (including hierarchy)
        cluster_info = cursor.execute('''
            SELECT gc.name, gc.member_count, gc.avg_importance,
                   gc.summary, gc.parent_cluster_id, gc.depth
            FROM graph_clusters gc
            WHERE gc.id IN (
                SELECT DISTINCT cluster_id FROM memories
                WHERE cluster_id IS NOT NULL AND profile = ?
            )
            ORDER BY gc.depth ASC, gc.member_count DESC
            LIMIT 20
        ''', (active_profile,)).fetchall()

        # Count hierarchical depth
        max_depth = max((c[5] or 0 for c in cluster_info), default=0) if cluster_info else 0

        return {
            'profile': active_profile,
            'nodes': nodes,
            'edges': edges,
            'clusters': clusters,
            'max_depth': max_depth,
            'top_clusters': [
                {
                    'name': c[0],
                    'members': c[1],
                    'avg_importance': round(c[2], 1) if c[2] else 5.0,
                    'summary': c[3],
                    'parent_cluster_id': c[4],
                    'depth': c[5] or 0
                }
                for c in cluster_info
            ]
        }

    finally:
        conn.close()
