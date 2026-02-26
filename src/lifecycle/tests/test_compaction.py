# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Tests for compaction engine — content archival and restoration.
"""
import sqlite3
import tempfile
import os
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestCompactionEngine:
    """Test memory compaction and restoration."""

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "test.db")
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                importance INTEGER DEFAULT 5,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_accessed TIMESTAMP,
                access_count INTEGER DEFAULT 0,
                lifecycle_state TEXT DEFAULT 'active',
                lifecycle_updated_at TIMESTAMP,
                lifecycle_history TEXT DEFAULT '[]',
                access_level TEXT DEFAULT 'public',
                profile TEXT DEFAULT 'default',
                tags TEXT DEFAULT '[]',
                summary TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_archive (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory_id INTEGER UNIQUE NOT NULL,
                full_content TEXT NOT NULL,
                archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_archive_memory ON memory_archive(memory_id)")

        # Memory 1: Long content suitable for compaction
        long_content = (
            "The Python programming language is widely used for machine learning and data science. "
            "It provides libraries like scikit-learn, TensorFlow, and PyTorch for building models. "
            "Python's simplicity and readability make it ideal for rapid prototyping. "
            "The ecosystem includes tools for data preprocessing, visualization, and deployment. "
            "Many enterprise applications use Python for backend services and API development."
        )
        conn.execute(
            "INSERT INTO memories (content, importance, lifecycle_state, tags) VALUES (?, ?, ?, ?)",
            (long_content, 5, "cold", '["python","ml"]'),
        )
        # Memory 2: Short content
        conn.execute(
            "INSERT INTO memories (content, importance, lifecycle_state) VALUES (?, ?, ?)",
            ("brief note about testing", 3, "cold"),
        )
        # Memory 3: Already archived
        conn.execute(
            "INSERT INTO memories (content, importance, lifecycle_state) VALUES (?, ?, ?)",
            ("[COMPACTED] Key entities: database, SQL", 5, "archived"),
        )
        conn.execute(
            "INSERT INTO memory_archive (memory_id, full_content) VALUES (?, ?)",
            (3, "The database management system uses SQL for querying and PostgreSQL for storage."),
        )
        conn.commit()
        conn.close()

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_compact_memory_archives_content(self):
        """Compaction stores full content in memory_archive."""
        from lifecycle.compaction_engine import CompactionEngine
        engine = CompactionEngine(self.db_path)
        result = engine.compact_memory(1)
        assert result["success"] is True
        # Verify archive has full content
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT full_content FROM memory_archive WHERE memory_id=1").fetchone()
        conn.close()
        assert row is not None
        assert "Python programming" in row[0]

    def test_compact_memory_replaces_content(self):
        """Compacted memory content is replaced with summary + entities."""
        from lifecycle.compaction_engine import CompactionEngine
        engine = CompactionEngine(self.db_path)
        engine.compact_memory(1)
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT content FROM memories WHERE id=1").fetchone()
        conn.close()
        # Content should be shorter than original
        assert len(row[0]) < 300
        assert "[COMPACTED]" in row[0]

    def test_compact_preserves_key_entities(self):
        """Compacted content preserves key entities/terms."""
        from lifecycle.compaction_engine import CompactionEngine
        engine = CompactionEngine(self.db_path)
        result = engine.compact_memory(1)
        assert "entities" in result
        assert len(result["entities"]) >= 3
        # Should extract key terms like "python", "learning", "data"
        entities_lower = [e.lower() for e in result["entities"]]
        assert any("python" in e for e in entities_lower)

    def test_compact_preserves_tags(self):
        """Compaction does NOT remove tags from the memory."""
        from lifecycle.compaction_engine import CompactionEngine
        engine = CompactionEngine(self.db_path)
        engine.compact_memory(1)
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT tags FROM memories WHERE id=1").fetchone()
        conn.close()
        assert row[0] is not None
        tags = json.loads(row[0])
        assert "python" in tags

    def test_restore_memory_from_archive(self):
        """Restoring a compacted memory brings back full content."""
        from lifecycle.compaction_engine import CompactionEngine
        engine = CompactionEngine(self.db_path)
        result = engine.restore_memory(3)  # Already archived memory
        assert result["success"] is True
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT content FROM memories WHERE id=3").fetchone()
        conn.close()
        assert "database management" in row[0]

    def test_restore_cleans_archive(self):
        """After restoration, the archive entry is removed."""
        from lifecycle.compaction_engine import CompactionEngine
        engine = CompactionEngine(self.db_path)
        engine.restore_memory(3)
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT * FROM memory_archive WHERE memory_id=3").fetchone()
        conn.close()
        assert row is None

    def test_dry_run_no_changes(self):
        """dry_run mode shows what would happen without modifying DB."""
        from lifecycle.compaction_engine import CompactionEngine
        engine = CompactionEngine(self.db_path)
        result = engine.compact_memory(1, dry_run=True)
        assert result["success"] is True
        assert result["dry_run"] is True
        # Verify DB was NOT modified
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT content FROM memories WHERE id=1").fetchone()
        archive = conn.execute("SELECT * FROM memory_archive WHERE memory_id=1").fetchone()
        conn.close()
        assert "Python programming" in row[0]  # Original content still there
        assert archive is None  # No archive entry created

    def test_compact_nonexistent_memory(self):
        """Compacting nonexistent memory returns failure."""
        from lifecycle.compaction_engine import CompactionEngine
        engine = CompactionEngine(self.db_path)
        result = engine.compact_memory(999)
        assert result["success"] is False

    def test_restore_nonexistent_archive(self):
        """Restoring memory without archive entry returns failure."""
        from lifecycle.compaction_engine import CompactionEngine
        engine = CompactionEngine(self.db_path)
        result = engine.restore_memory(1)  # Memory 1 has no archive
        assert result["success"] is False
