# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Tests for ABAC enforcement in memory operations.
"""
import sqlite3
import tempfile
import os
import sys
import json
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestABACEnforcement:
    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "memory.db")
        # Create store with test data
        from memory_store_v2 import MemoryStoreV2
        self.store = MemoryStoreV2(self.db_path)
        self.store.add_memory(
            content="public memory about Python",
            tags=["python"],
            importance=5,
        )
        self.store.add_memory(
            content="private memory about secrets",
            tags=["secrets"],
            importance=8,
        )
        # Set access_level for private memory
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE memories SET access_level='private' WHERE id=2")
        conn.commit()
        conn.close()
        self.store._rebuild_vectors()

    def teardown_method(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_search_without_abac_works(self):
        """Search without ABAC context works (backward compat)."""
        results = self.store.search("Python", limit=5)
        assert len(results) >= 1

    def test_search_with_agent_context(self):
        """Search with agent_context parameter works."""
        results = self.store.search(
            "memory", limit=10, agent_context={"agent_id": "user"}
        )
        assert isinstance(results, list)

    def test_create_without_abac_works(self):
        """Create without ABAC works (backward compat)."""
        mem_id = self.store.add_memory(content="new memory", tags=["test"])
        assert mem_id is not None

    def test_abac_check_method_exists(self):
        """MemoryStoreV2 has _check_abac method."""
        assert hasattr(self.store, "_check_abac")

    def test_check_abac_default_allows(self):
        """Default ABAC check (no policy file) allows everything."""
        result = self.store._check_abac(
            subject={"agent_id": "user"},
            resource={"access_level": "public"},
            action="read",
        )
        assert result["allowed"] is True

    def test_check_abac_with_policy(self):
        """ABAC check with policy file respects deny rules."""
        policy_path = os.path.join(self.tmp_dir, "abac_policies.json")
        with open(policy_path, "w") as f:
            json.dump(
                [
                    {
                        "name": "deny-private",
                        "effect": "deny",
                        "subjects": {"agent_id": "*"},
                        "resources": {"access_level": "private"},
                        "actions": ["read"],
                    }
                ],
                f,
            )
        result = self.store._check_abac(
            subject={"agent_id": "bot"},
            resource={"access_level": "private"},
            action="read",
            policy_path=policy_path,
        )
        assert result["allowed"] is False
