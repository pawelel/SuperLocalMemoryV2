# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Formal memory compaction with information preservation guarantees.

Archives full content before compaction, replaces with compressed summary
containing key entities. Supports lossless restoration from archive.
"""
import re
import sqlite3
from datetime import datetime, timezone
from typing import Dict, List, Optional


# Common English stopwords for entity extraction (no external dependencies)
_STOPWORDS = frozenset(
    "a an the is are was were be been being have has had do does did will would "
    "shall should may might can could am not no nor and but or if then else when "
    "at by for with about against between through during before after above below "
    "to from up down in out on off over under again further once here there all "
    "each every both few more most other some such only own same so than too very "
    "just don doesn didn won wouldn isn aren wasn weren hasn haven hadn it its "
    "i me my myself we our ours ourselves you your yours yourself yourselves he "
    "him his himself she her hers herself they them their theirs themselves what "
    "which who whom this that these those of as into how also many use used uses "
    "using like make makes made includes include including provides provide "
    "widely ideal rapid many".split()
)

# Minimum word length for entity candidates
_MIN_WORD_LEN = 3
# Maximum number of entities to extract
_MAX_ENTITIES = 8


class CompactionEngine:
    """Manages content compaction and restoration for memory lifecycle.

    When a memory transitions to ARCHIVED state, this engine:
    1. Saves the full content to memory_archive (lossless backup)
    2. Replaces content with a compact summary + key entities
    3. Can restore full content if memory is reactivated
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._ensure_archive_table()

    def _get_conn(self) -> sqlite3.Connection:
        """Create a new connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_archive_table(self) -> None:
        """Ensure the memory_archive table exists."""
        conn = self._get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_archive (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    memory_id INTEGER UNIQUE NOT NULL,
                    full_content TEXT NOT NULL,
                    archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_archive_memory "
                "ON memory_archive(memory_id)"
            )
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compact_memory(
        self, memory_id: int, dry_run: bool = False
    ) -> Dict:
        """Compact a memory: archive full content, replace with summary.

        Args:
            memory_id: ID of the memory to compact.
            dry_run: If True, compute result but do not modify the database.

        Returns:
            Dict with keys: success, entities, summary, original_length,
            and optionally dry_run, error.
        """
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT id, content, tags FROM memories WHERE id = ?",
                (memory_id,),
            ).fetchone()

            if row is None:
                return {"success": False, "error": "Memory not found"}

            content = row["content"]
            original_length = len(content)

            # Extract key entities (pure-Python TF-IDF-like approach)
            entities = self._extract_entities(content)
            summary = self._build_summary(content, entities, original_length)

            if dry_run:
                return {
                    "success": True,
                    "dry_run": True,
                    "entities": entities,
                    "summary": summary,
                    "original_length": original_length,
                }

            # Archive the full content (lossless backup)
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT OR REPLACE INTO memory_archive "
                "(memory_id, full_content, archived_at) VALUES (?, ?, ?)",
                (memory_id, content, now),
            )

            # Replace memory content with compacted version
            conn.execute(
                "UPDATE memories SET content = ? WHERE id = ?",
                (summary, memory_id),
            )
            conn.commit()

            return {
                "success": True,
                "entities": entities,
                "summary": summary,
                "original_length": original_length,
            }
        finally:
            conn.close()

    def restore_memory(self, memory_id: int) -> Dict:
        """Restore a compacted memory from its archive.

        Args:
            memory_id: ID of the memory to restore.

        Returns:
            Dict with keys: success, and optionally restored_length, error.
        """
        conn = self._get_conn()
        try:
            archive = conn.execute(
                "SELECT full_content FROM memory_archive WHERE memory_id = ?",
                (memory_id,),
            ).fetchone()

            if archive is None:
                return {"success": False, "error": "No archive found for memory"}

            full_content = archive["full_content"]

            # Restore original content
            conn.execute(
                "UPDATE memories SET content = ? WHERE id = ?",
                (full_content, memory_id),
            )

            # Remove the archive entry (content is back in main table)
            conn.execute(
                "DELETE FROM memory_archive WHERE memory_id = ?",
                (memory_id,),
            )
            conn.commit()

            return {
                "success": True,
                "restored_length": len(full_content),
            }
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_entities(text: str) -> List[str]:
        """Extract key entities using word-frequency ranking.

        Pure Python implementation — no sklearn or external NLP deps.
        Tokenizes, removes stopwords, counts frequency, returns top terms.
        """
        # Tokenize: split on non-alphanumeric, lowercase
        tokens = re.findall(r"[a-zA-Z]+", text.lower())

        # Filter: remove stopwords and short tokens
        meaningful = [
            t for t in tokens
            if t not in _STOPWORDS and len(t) >= _MIN_WORD_LEN
        ]

        # Count frequencies
        freq: Dict[str, int] = {}
        for token in meaningful:
            freq[token] = freq.get(token, 0) + 1

        # Sort by frequency descending, then alphabetically for stability
        ranked = sorted(freq.items(), key=lambda x: (-x[1], x[0]))

        # Return top N entities
        return [word for word, _ in ranked[:_MAX_ENTITIES]]

    @staticmethod
    def _build_summary(
        text: str, entities: List[str], original_length: int
    ) -> str:
        """Build the compacted content string.

        Format: [COMPACTED] Key entities: e1, e2, ... Original length: N chars.
        """
        entity_str = ", ".join(entities) if entities else "none"
        return (
            f"[COMPACTED] Key entities: {entity_str}. "
            f"Original length: {original_length} chars."
        )
