# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Privacy-safe cross-project behavioral pattern transfer.

Transfers behavioral patterns between projects using ONLY metadata
(pattern type, success rate, confidence). Never transfers memory
content or content hashes.

Eligibility criteria:
  - confidence >= 0.7
  - evidence_count >= 5
  - source project != target project

Part of SLM v2.8 Behavioral Learning Engine.
"""
import sqlite3
import threading
from typing import Dict, List, Optional, Any


# Thresholds for transfer eligibility
MIN_CONFIDENCE = 0.7
MIN_EVIDENCE = 5


class CrossProjectTransfer:
    """Privacy-safe cross-project behavioral pattern transfer.

    Only metadata (pattern_type, pattern_key, success_rate,
    evidence_count, confidence) is transferred — never content
    or content hashes.
    """

    _CREATE_CROSS_TABLE = """
        CREATE TABLE IF NOT EXISTS cross_project_behaviors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_project TEXT NOT NULL,
            target_project TEXT NOT NULL,
            pattern_id INTEGER NOT NULL,
            transfer_type TEXT DEFAULT 'metadata',
            confidence REAL DEFAULT 0.0,
            profile TEXT DEFAULT 'default',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (pattern_id) REFERENCES behavioral_patterns(id)
        )
    """

    def __init__(self, db_path: Optional[str] = None, enabled: bool = True):
        self._db_path = db_path
        self._enabled = enabled
        self._lock = threading.Lock()
        if db_path:
            self._ensure_tables()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate_transfers(
        self, target_project: str
    ) -> List[Dict[str, Any]]:
        """Find patterns eligible for transfer to the target project.

        Eligibility: confidence >= 0.7 AND evidence_count >= 5
        AND source project != target project.

        Returns:
            List of dicts with metadata-only fields: pattern_id,
            pattern_type, pattern_key, success_rate, evidence_count,
            confidence, source_project, transfer_type.
        """
        if not self._enabled:
            return []

        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    """SELECT id, pattern_type, pattern_key, success_rate,
                              evidence_count, confidence, project
                       FROM behavioral_patterns
                       WHERE confidence >= ?
                         AND evidence_count >= ?
                         AND project IS NOT NULL
                         AND project != ?
                       ORDER BY confidence DESC""",
                    (MIN_CONFIDENCE, MIN_EVIDENCE, target_project),
                ).fetchall()

                return [self._eligible_to_dict(row) for row in rows]
            finally:
                conn.close()

    def apply_transfer(
        self, pattern_id: int, target_project: str
    ) -> Dict[str, Any]:
        """Record a cross-project transfer in the database.

        Looks up the source pattern to get its project and confidence,
        then inserts a record into cross_project_behaviors.

        Returns:
            Dict with success status and transfer id.
        """
        with self._lock:
            conn = self._connect()
            try:
                # Look up the source pattern
                pattern = conn.execute(
                    "SELECT project, confidence FROM behavioral_patterns WHERE id = ?",
                    (pattern_id,),
                ).fetchone()

                if pattern is None:
                    return {"success": False, "error": "pattern_not_found"}

                source_project = pattern["project"]
                confidence = pattern["confidence"]

                cur = conn.execute(
                    """INSERT INTO cross_project_behaviors
                       (source_project, target_project, pattern_id,
                        transfer_type, confidence)
                       VALUES (?, ?, ?, 'metadata', ?)""",
                    (source_project, target_project, pattern_id, confidence),
                )
                conn.commit()
                return {
                    "success": True,
                    "transfer_id": cur.lastrowid,
                    "source_project": source_project,
                    "target_project": target_project,
                }
            finally:
                conn.close()

    def get_transfers(
        self,
        target_project: Optional[str] = None,
        source_project: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Query recorded cross-project transfers.

        Args:
            target_project: Filter by target project.
            source_project: Filter by source project.

        Returns:
            List of transfer record dicts.
        """
        with self._lock:
            conn = self._connect()
            try:
                query = "SELECT * FROM cross_project_behaviors WHERE 1=1"
                params: List[Any] = []

                if target_project is not None:
                    query += " AND target_project = ?"
                    params.append(target_project)

                if source_project is not None:
                    query += " AND source_project = ?"
                    params.append(source_project)

                query += " ORDER BY created_at DESC"

                rows = conn.execute(query, params).fetchall()
                return [dict(row) for row in rows]
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        """Open a connection with row factory enabled."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self) -> None:
        """Create the cross_project_behaviors table if missing."""
        conn = self._connect()
        try:
            conn.execute(self._CREATE_CROSS_TABLE)
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _eligible_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        """Convert a pattern row to a privacy-safe transfer dict.

        Only metadata fields are included. No content, no hashes.
        """
        return {
            "pattern_id": row["id"],
            "pattern_type": row["pattern_type"],
            "pattern_key": row["pattern_key"],
            "success_rate": row["success_rate"],
            "evidence_count": row["evidence_count"],
            "confidence": row["confidence"],
            "source_project": row["project"],
            "transfer_type": "metadata",
        }
