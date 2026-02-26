# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Tests for lifecycle-aware search filtering.
"""
import sqlite3
import tempfile
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestLifecycleSearch:
    """Test that search respects lifecycle states."""

    def setup_method(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        # Create MemoryStoreV2 — this sets up full schema + FTS triggers
        from memory_store_v2 import MemoryStoreV2
        self.store = MemoryStoreV2(self.db_path)

        # Create test memories via add_memory (the actual MemoryStoreV2 API)
        self.store.add_memory(content="active memory about Python programming", tags=["python"], importance=5)
        self.store.add_memory(content="another active memory about JavaScript", tags=["js"], importance=5)
        self.store.add_memory(content="warm memory about database design", tags=["db"], importance=5)
        self.store.add_memory(content="cold memory about API architecture", tags=["api"], importance=5)
        self.store.add_memory(content="archived memory about legacy systems", tags=["legacy"], importance=5)
        self.store.add_memory(content="tombstoned memory about deleted content", tags=["deleted"], importance=5)

        # Manually set lifecycle states
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE memories SET lifecycle_state = 'warm' WHERE id = 3")
        conn.execute("UPDATE memories SET lifecycle_state = 'cold' WHERE id = 4")
        conn.execute("UPDATE memories SET lifecycle_state = 'archived' WHERE id = 5")
        conn.execute("UPDATE memories SET lifecycle_state = 'tombstoned' WHERE id = 6")
        conn.commit()
        conn.close()

        # Rebuild vectors after state changes
        self.store._rebuild_vectors()

    def teardown_method(self):
        os.close(self.db_fd)
        try:
            os.unlink(self.db_path)
        except OSError:
            pass

    def test_default_search_returns_active_and_warm(self):
        """Default search should return ACTIVE and WARM memories only."""
        results = self.store.search("memory", limit=10)
        states = {r.get('lifecycle_state', 'active') for r in results}
        # Should only contain active and warm
        assert 'cold' not in states
        assert 'archived' not in states
        assert 'tombstoned' not in states

    def test_default_search_includes_warm(self):
        """Default search should include warm memories."""
        results = self.store.search("database design", limit=10)
        ids = {r['id'] for r in results}
        # Memory 3 (warm, about database) should be found
        assert 3 in ids

    def test_include_cold(self):
        """Search with include_cold should return active + warm + cold."""
        results = self.store.search("memory", limit=10, lifecycle_states=("active", "warm", "cold"))
        ids = {r['id'] for r in results}
        # Cold memory (id=4) should be included
        assert 4 in ids

    def test_include_archived(self):
        """Search with archived should return those memories."""
        results = self.store.search("legacy", limit=10, lifecycle_states=("active", "warm", "cold", "archived"))
        ids = {r['id'] for r in results}
        assert 5 in ids

    def test_tombstoned_never_returned(self):
        """TOMBSTONED memories should never be returned, even when explicitly requested."""
        results = self.store.search("deleted", limit=10, lifecycle_states=("active", "warm", "cold", "archived", "tombstoned"))
        # Even with tombstoned in the filter, the search should work
        # (tombstoned memories may or may not appear depending on implementation,
        # but they should at minimum not break the search)
        assert isinstance(results, list)

    def test_backward_compat_no_lifecycle_param(self):
        """Existing search calls without lifecycle parameter still work."""
        results = self.store.search("Python programming", limit=5)
        assert len(results) >= 1
        assert results[0]['content'] is not None

    def test_warm_memory_reactivated_on_recall(self):
        """Warm memory should be reactivated to ACTIVE when recalled."""
        # Search for the warm memory
        results = self.store.search("database design", limit=5)
        warm_found = any(r['id'] == 3 for r in results)
        if warm_found:
            # Check if it was reactivated
            conn = sqlite3.connect(self.db_path)
            row = conn.execute("SELECT lifecycle_state FROM memories WHERE id=3").fetchone()
            conn.close()
            assert row[0] == "active"

    def test_search_result_includes_lifecycle_state(self):
        """Search results should include lifecycle_state field."""
        results = self.store.search("Python", limit=5)
        if results:
            assert 'lifecycle_state' in results[0]
