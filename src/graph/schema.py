#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Database schema management for the graph engine.

Creates and maintains the graph_nodes, graph_edges, and graph_clusters
tables, including safe schema migrations for existing databases.
"""
import sqlite3
from pathlib import Path

from graph.constants import logger


def ensure_graph_tables(db_path: Path):
    """Create graph tables if they don't exist, or recreate if schema is incomplete."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if existing tables have correct schema (not just id column)
    for table_name, required_cols in [
        ('graph_nodes', {'memory_id', 'entities'}),
        ('graph_edges', {'source_memory_id', 'target_memory_id', 'weight'}),
        ('graph_clusters', {'name', 'member_count'}),
    ]:
        cursor.execute(f"PRAGMA table_info({table_name})")
        existing_cols = {row[1] for row in cursor.fetchall()}
        if existing_cols and not required_cols.issubset(existing_cols):
            # Table exists but has incomplete schema -- drop and recreate
            logger.warning(f"Dropping incomplete {table_name} table (missing: {required_cols - existing_cols})")
            cursor.execute(f'DROP TABLE IF EXISTS {table_name}')

    # Graph nodes table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS graph_nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            memory_id INTEGER UNIQUE NOT NULL,
            entities TEXT,
            embedding_vector TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
        )
    ''')

    # Graph edges table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS graph_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_memory_id INTEGER NOT NULL,
            target_memory_id INTEGER NOT NULL,
            relationship_type TEXT,
            weight REAL DEFAULT 1.0,
            shared_entities TEXT,
            similarity_score REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (source_memory_id) REFERENCES memories(id) ON DELETE CASCADE,
            FOREIGN KEY (target_memory_id) REFERENCES memories(id) ON DELETE CASCADE,
            UNIQUE(source_memory_id, target_memory_id)
        )
    ''')

    # Graph clusters table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS graph_clusters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            summary TEXT,
            member_count INTEGER DEFAULT 0,
            avg_importance REAL,
            parent_cluster_id INTEGER,
            depth INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (parent_cluster_id) REFERENCES graph_clusters(id) ON DELETE SET NULL
        )
    ''')

    # Safe column additions for existing databases
    for col, col_type in [('summary', 'TEXT'), ('parent_cluster_id', 'INTEGER'), ('depth', 'INTEGER DEFAULT 0')]:
        try:
            cursor.execute(f'ALTER TABLE graph_clusters ADD COLUMN {col} {col_type}')
        except sqlite3.OperationalError:
            pass

    # Add cluster_id to memories if not exists
    try:
        cursor.execute('ALTER TABLE memories ADD COLUMN cluster_id INTEGER')
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Create indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_graph_source ON graph_edges(source_memory_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_graph_target ON graph_edges(target_memory_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_cluster_members ON memories(cluster_id)')

    conn.commit()
    conn.close()
    logger.info("Graph tables initialized")
