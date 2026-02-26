#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""SuperLocalMemory V2 - Tests for v2.8 Schema Migration

Tests that the v2.8.0 lifecycle + access control columns are added
via backward-compatible ALTER TABLE migration in memory_store_v2.py.
"""
import json
import sqlite3
import sys
import importlib
from pathlib import Path

import pytest

# Ensure src/ is importable AND takes precedence over ~/.claude-memory/
# (the installed production copy). Other test modules in this suite may
# cause ~/.claude-memory to appear on sys.path earlier, so we must ensure
# our development src/ directory wins.
SRC_DIR = Path(__file__).resolve().parent.parent.parent  # src/
_src_str = str(SRC_DIR)


def _import_memory_store_v2():
    """
    Import MemoryStoreV2 from the development src/ directory.

    When running in a full test suite, other test modules may cause
    ~/.claude-memory/ (the installed production copy) to appear on sys.path
    before src/. This helper ensures we always load from the correct location
    by temporarily prioritizing src/ and invalidating any stale cached import.
    """
    # Ensure src/ is at position 0
    if sys.path[0] != _src_str:
        if _src_str in sys.path:
            sys.path.remove(_src_str)
        sys.path.insert(0, _src_str)

    # If memory_store_v2 was already imported from a different location
    # (e.g., ~/.claude-memory/), force a reimport from src/
    mod = sys.modules.get("memory_store_v2")
    if mod is not None and hasattr(mod, "__file__"):
        mod_path = str(Path(mod.__file__).resolve().parent)
        if mod_path != _src_str:
            del sys.modules["memory_store_v2"]
            # Also clear any cached submodule imports that may hold refs
            for key in list(sys.modules.keys()):
                m = sys.modules[key]
                if m is not None and hasattr(m, "__file__") and m.__file__ and "memory_store_v2" in str(m.__file__):
                    pass  # memory_store_v2 is not a package, no submodules

    from memory_store_v2 import MemoryStoreV2
    return MemoryStoreV2


# ---------------------------------------------------------------------------
# Helper — create a v2.7.6 schema database (WITHOUT lifecycle columns)
# ---------------------------------------------------------------------------

def _create_v276_database(db_path: Path) -> None:
    """
    Create a minimal memories table matching the v2.7.6 schema.
    This deliberately omits the v2.8 lifecycle columns so the migration
    can be verified.
    """
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            summary TEXT,
            project_path TEXT,
            project_name TEXT,
            tags TEXT,
            category TEXT,
            parent_id INTEGER,
            tree_path TEXT,
            depth INTEGER DEFAULT 0,
            memory_type TEXT DEFAULT 'session',
            importance INTEGER DEFAULT 5,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_accessed TIMESTAMP,
            access_count INTEGER DEFAULT 0,
            content_hash TEXT UNIQUE,
            cluster_id INTEGER,
            profile TEXT DEFAULT 'default',
            FOREIGN KEY (parent_id) REFERENCES memories(id) ON DELETE CASCADE
        )
    """)
    conn.commit()
    conn.close()


def _insert_test_memory(db_path: Path, content: str = "test memory content") -> int:
    """Insert a single test memory into a v2.7.6 database and return its id."""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO memories (content, profile) VALUES (?, ?)",
        (content, "default"),
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


def _get_column_names(db_path: Path, table: str = "memories") -> set:
    """Return the set of column names for a table."""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table})")
    columns = {row[1] for row in cursor.fetchall()}
    conn.close()
    return columns


def _get_index_names(db_path: Path) -> set:
    """Return the set of index names in the database."""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
    indexes = {row[0] for row in cursor.fetchall()}
    conn.close()
    return indexes


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def v276_db(tmp_path):
    """
    Create a temporary v2.7.6 schema database with one pre-existing memory.
    Returns (db_path, memory_id).
    """
    db_path = tmp_path / "memory.db"
    _create_v276_database(db_path)
    mem_id = _insert_test_memory(db_path, "pre-existing memory from v2.7.6")
    return db_path, mem_id


@pytest.fixture
def migrated_store(v276_db):
    """
    Initialize MemoryStoreV2 on the v2.7.6 database, triggering the migration.
    Returns (store, db_path, pre_existing_memory_id).
    """
    db_path, mem_id = v276_db
    MemoryStoreV2 = _import_memory_store_v2()
    store = MemoryStoreV2(db_path=db_path)
    return store, db_path, mem_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestV28SchemaMigration:
    """Verify v2.8.0 lifecycle + access control migration."""

    def test_lifecycle_state_column_added(self, migrated_store):
        """After MemoryStoreV2 init, lifecycle_state column exists."""
        _store, db_path, _mem_id = migrated_store
        columns = _get_column_names(db_path)
        assert "lifecycle_state" in columns, (
            f"lifecycle_state column missing. Columns: {sorted(columns)}"
        )

    def test_existing_memories_get_active_state(self, migrated_store):
        """Pre-existing memories get lifecycle_state='active' from DEFAULT."""
        _store, db_path, mem_id = migrated_store
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT lifecycle_state FROM memories WHERE id = ?", (mem_id,)
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None, "Pre-existing memory not found after migration"
        assert row[0] == "active", (
            f"Expected lifecycle_state='active', got '{row[0]}'"
        )

    def test_access_level_column_added(self, migrated_store):
        """access_level column exists with DEFAULT 'public'."""
        _store, db_path, mem_id = migrated_store
        columns = _get_column_names(db_path)
        assert "access_level" in columns, (
            f"access_level column missing. Columns: {sorted(columns)}"
        )

        # Verify default value on pre-existing row
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT access_level FROM memories WHERE id = ?", (mem_id,)
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "public", (
            f"Expected access_level='public', got '{row[0]}'"
        )

    def test_lifecycle_history_column_added(self, migrated_store):
        """lifecycle_history column exists with DEFAULT '[]'."""
        _store, db_path, mem_id = migrated_store
        columns = _get_column_names(db_path)
        assert "lifecycle_history" in columns, (
            f"lifecycle_history column missing. Columns: {sorted(columns)}"
        )

        # Verify default value on pre-existing row
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT lifecycle_history FROM memories WHERE id = ?", (mem_id,)
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "[]", (
            f"Expected lifecycle_history='[]', got '{row[0]}'"
        )
        # Verify it's valid JSON
        parsed = json.loads(row[0])
        assert parsed == []

    def test_lifecycle_updated_at_column_added(self, migrated_store):
        """lifecycle_updated_at column exists (nullable, no default)."""
        _store, db_path, mem_id = migrated_store
        columns = _get_column_names(db_path)
        assert "lifecycle_updated_at" in columns, (
            f"lifecycle_updated_at column missing. Columns: {sorted(columns)}"
        )

        # Pre-existing rows should have NULL for this column
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT lifecycle_updated_at FROM memories WHERE id = ?", (mem_id,)
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[0] is None, (
            f"Expected lifecycle_updated_at=NULL for pre-existing row, got '{row[0]}'"
        )

    def test_migration_is_idempotent(self, v276_db):
        """Running migration twice (two MemoryStoreV2 inits) doesn't error."""
        db_path, mem_id = v276_db
        MemoryStoreV2 = _import_memory_store_v2()

        # First init — migration runs
        store1 = MemoryStoreV2(db_path=db_path)

        # Second init — migration runs again (ALTER TABLE should be caught)
        store2 = MemoryStoreV2(db_path=db_path)

        # Both should succeed, columns should exist exactly once
        columns = _get_column_names(db_path)
        assert "lifecycle_state" in columns
        assert "access_level" in columns
        assert "lifecycle_history" in columns
        assert "lifecycle_updated_at" in columns

        # Pre-existing data should be intact
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT content FROM memories WHERE id = ?", (mem_id,))
        row = cursor.fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "pre-existing memory from v2.7.6"

    def test_existing_queries_still_work(self, migrated_store):
        """list_all() and search() work after migration."""
        store, db_path, mem_id = migrated_store

        # list_all should return the pre-existing memory
        all_memories = store.list_all(limit=10)
        assert len(all_memories) >= 1, "list_all() returned no results after migration"

        found = any(m["id"] == mem_id for m in all_memories)
        assert found, (
            f"Pre-existing memory id={mem_id} not found in list_all() results"
        )

        # Add a memory through the store API (so FTS is properly populated)
        new_id = store.add_memory(
            content="post-migration memory for search test",
            tags=["test"],
        )
        assert new_id is not None, "add_memory() should succeed after migration"

        # search should not crash (may return empty if TF-IDF vectors not rebuilt)
        results = store.search("post-migration", limit=5)
        assert isinstance(results, list), "search() should return a list"

    def test_v28_indexes_created(self, migrated_store):
        """v2.8.0 indexes for lifecycle_state and access_level exist."""
        _store, db_path, _mem_id = migrated_store
        indexes = _get_index_names(db_path)
        assert "idx_lifecycle_state" in indexes, (
            f"idx_lifecycle_state index missing. Indexes: {sorted(indexes)}"
        )
        assert "idx_access_level" in indexes, (
            f"idx_access_level index missing. Indexes: {sorted(indexes)}"
        )
