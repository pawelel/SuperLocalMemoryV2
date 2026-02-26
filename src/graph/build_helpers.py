#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Helper functions for the graph build process.

Provides sampling and cleanup utilities used during full graph builds.
"""
from graph.constants import logger, MAX_MEMORIES_FOR_GRAPH


def apply_sampling(cursor, memories, active_profile):
    """Apply intelligent sampling if memory count exceeds cap.

    Returns a (possibly truncated) list of memory tuples.
    """
    if len(memories) > MAX_MEMORIES_FOR_GRAPH:
        logger.warning(
            "Memory count (%d) exceeds graph cap (%d). Using intelligent sampling.",
            len(memories), MAX_MEMORIES_FOR_GRAPH
        )
        recent_count = int(MAX_MEMORIES_FOR_GRAPH * 0.6)
        important_count = int(MAX_MEMORIES_FOR_GRAPH * 0.4)

        recent_memories = cursor.execute('''
            SELECT id, content, summary FROM memories
            WHERE profile = ? ORDER BY created_at DESC LIMIT ?
        ''', (active_profile, recent_count)).fetchall()

        important_memories = cursor.execute('''
            SELECT id, content, summary FROM memories
            WHERE profile = ? ORDER BY importance DESC, access_count DESC LIMIT ?
        ''', (active_profile, important_count)).fetchall()

        seen_ids = set()
        sampled = []
        for m in recent_memories + important_memories:
            if m[0] not in seen_ids:
                seen_ids.add(m[0])
                sampled.append(m)
        memories = sampled[:MAX_MEMORIES_FOR_GRAPH]
        logger.info("Sampled %d memories for graph build", len(memories))

    elif len(memories) > MAX_MEMORIES_FOR_GRAPH * 0.8:
        logger.warning(
            "Approaching graph cap: %d/%d memories (%.0f%%). "
            "Consider running memory compression.",
            len(memories), MAX_MEMORIES_FOR_GRAPH,
            len(memories) / MAX_MEMORIES_FOR_GRAPH * 100
        )
    return memories


def clear_profile_graph_data(cursor, conn, memories, active_profile):
    """Clear existing graph data for a profile's memories."""
    profile_memory_ids = [m[0] for m in memories]
    if profile_memory_ids:
        placeholders = ','.join('?' * len(profile_memory_ids))
        cursor.execute(f'''
            DELETE FROM graph_edges
            WHERE source_memory_id IN ({placeholders})
               OR target_memory_id IN ({placeholders})
        ''', profile_memory_ids + profile_memory_ids)
        cursor.execute(f'''
            DELETE FROM graph_nodes WHERE memory_id IN ({placeholders})
        ''', profile_memory_ids)
    cursor.execute('''
        DELETE FROM graph_clusters
        WHERE id NOT IN (
            SELECT DISTINCT cluster_id FROM memories WHERE cluster_id IS NOT NULL
        )
    ''')
    cursor.execute('UPDATE memories SET cluster_id = NULL WHERE profile = ?',
                  (active_profile,))
    conn.commit()
