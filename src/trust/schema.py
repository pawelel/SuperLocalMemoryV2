#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""
Database schema initialization for the trust scoring system.

Creates trust_signals table and adds alpha/beta columns to agent_registry.
Extracted from TrustScorer._init_schema for modularity.
"""

from pathlib import Path

from .constants import INITIAL_ALPHA, INITIAL_BETA


def init_trust_schema(db_path: Path):
    """
    Create trust_signals table and add alpha/beta columns to agent_registry.

    Handles both DbConnectionManager (preferred) and direct sqlite3 fallback.

    Args:
        db_path: Path to the SQLite database file.
    """
    try:
        from db_connection_manager import DbConnectionManager
        mgr = DbConnectionManager.get_instance(db_path)

        def _create(conn):
            # Trust signals audit trail
            conn.execute('''
                CREATE TABLE IF NOT EXISTS trust_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT NOT NULL,
                    signal_type TEXT NOT NULL,
                    delta REAL NOT NULL,
                    old_score REAL,
                    new_score REAL,
                    context TEXT DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_trust_agent
                ON trust_signals(agent_id)
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_trust_created
                ON trust_signals(created_at)
            ''')

            # Add trust_alpha and trust_beta columns to agent_registry
            # (backward compatible -- old databases get these columns added)
            for col_name, col_default in [("trust_alpha", INITIAL_ALPHA),
                                           ("trust_beta", INITIAL_BETA)]:
                try:
                    conn.execute(
                        f'ALTER TABLE agent_registry ADD COLUMN {col_name} REAL DEFAULT {col_default}'
                    )
                except Exception:
                    pass  # Column already exists

            conn.commit()

        mgr.execute_write(_create)
    except ImportError:
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        conn.execute('''
            CREATE TABLE IF NOT EXISTS trust_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                delta REAL NOT NULL,
                old_score REAL,
                new_score REAL,
                context TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_trust_agent ON trust_signals(agent_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_trust_created ON trust_signals(created_at)')

        # Add trust_alpha and trust_beta columns (backward compatible)
        for col_name, col_default in [("trust_alpha", INITIAL_ALPHA),
                                       ("trust_beta", INITIAL_BETA)]:
            try:
                conn.execute(
                    f'ALTER TABLE agent_registry ADD COLUMN {col_name} REAL DEFAULT {col_default}'
                )
            except sqlite3.OperationalError:
                pass  # Column already exists

        conn.commit()
        conn.close()
