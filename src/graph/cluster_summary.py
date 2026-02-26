#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Cluster summary generation for the graph engine.

Generates TF-IDF structured summaries for graph clusters,
analyzing member content to produce human-readable descriptions
of each cluster's theme, key topics, and scope.
"""
import sqlite3
import json
from pathlib import Path
from collections import Counter

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


def generate_cluster_summaries(db_path: Path) -> int:
    """
    Generate TF-IDF structured summaries for all clusters.

    For each cluster, analyzes member content to produce a human-readable
    summary describing the cluster's theme, key topics, and scope.

    Returns:
        Number of clusters with summaries generated
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    active_profile = _get_active_profile()

    try:
        # Get all clusters for this profile
        cursor.execute('''
            SELECT DISTINCT gc.id, gc.name, gc.member_count
            FROM graph_clusters gc
            JOIN memories m ON m.cluster_id = gc.id
            WHERE m.profile = ?
        ''', (active_profile,))
        clusters = cursor.fetchall()

        if not clusters:
            return 0

        summaries_generated = 0

        for cluster_id, cluster_name, member_count in clusters:
            summary = _build_cluster_summary(cursor, cluster_id, active_profile)
            if summary:
                cursor.execute('''
                    UPDATE graph_clusters SET summary = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (summary, cluster_id))
                summaries_generated += 1
                logger.info(f"Summary for cluster {cluster_id} ({cluster_name}): {summary[:80]}...")

        conn.commit()
        logger.info(f"Generated {summaries_generated} cluster summaries")
        return summaries_generated

    except Exception as e:
        logger.error(f"Summary generation failed: {e}")
        conn.rollback()
        return 0
    finally:
        conn.close()


def _build_cluster_summary(cursor, cluster_id: int, profile: str) -> str:
    """Build a TF-IDF structured summary for a single cluster."""
    # Get member content
    cursor.execute('''
        SELECT m.content, m.summary, m.tags, m.category, m.project_name
        FROM memories m
        WHERE m.cluster_id = ? AND m.profile = ?
    ''', (cluster_id, profile))
    members = cursor.fetchall()

    if not members:
        return ""

    # Collect entities from graph nodes
    cursor.execute('''
        SELECT gn.entities
        FROM graph_nodes gn
        JOIN memories m ON gn.memory_id = m.id
        WHERE m.cluster_id = ? AND m.profile = ?
    ''', (cluster_id, profile))
    all_entities = []
    for row in cursor.fetchall():
        if row[0]:
            try:
                all_entities.extend(json.loads(row[0]))
            except (json.JSONDecodeError, TypeError):
                pass

    # Top entities by frequency (TF-IDF already extracted these)
    entity_counts = Counter(all_entities)
    top_entities = [e for e, _ in entity_counts.most_common(5)]

    # Collect unique projects and categories
    projects = set()
    categories = set()
    for m in members:
        if m[3]:  # category
            categories.add(m[3])
        if m[4]:  # project_name
            projects.add(m[4])

    # Build structured summary
    parts = []

    # Theme from top entities
    if top_entities:
        parts.append(f"Key topics: {', '.join(top_entities[:5])}")

    # Scope
    if projects:
        parts.append(f"Projects: {', '.join(sorted(projects)[:3])}")
    if categories:
        parts.append(f"Categories: {', '.join(sorted(categories)[:3])}")

    # Size context
    parts.append(f"{len(members)} memories")

    # Check for hierarchical context
    cursor.execute('SELECT parent_cluster_id FROM graph_clusters WHERE id = ?', (cluster_id,))
    parent_row = cursor.fetchone()
    if parent_row and parent_row[0]:
        cursor.execute('SELECT name FROM graph_clusters WHERE id = ?', (parent_row[0],))
        parent_name_row = cursor.fetchone()
        if parent_name_row:
            parts.append(f"Sub-cluster of: {parent_name_row[0]}")

    return " | ".join(parts)
