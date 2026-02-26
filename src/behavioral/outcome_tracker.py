# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Explicit + implicit action outcome recording.

Records what happens AFTER memories are recalled — success, failure,
or partial outcomes. Self-contained: creates its own table via
CREATE TABLE IF NOT EXISTS so no external migration is needed.

Part of SLM v2.8 Behavioral Learning Engine.
"""
import json
import sqlite3
import threading
from typing import Dict, List, Optional, Any


class OutcomeTracker:
    """Records action outcomes for behavioral learning.

    Each outcome links one or more memory IDs to an outcome label
    (success / failure / partial) with optional context metadata.
    Confidence defaults to 0.9 for explicit (user-reported) outcomes.
    """

    OUTCOMES = ("success", "failure", "partial")

    ACTION_TYPES = (
        "code_written",
        "decision_made",
        "debug_resolved",
        "architecture_chosen",
        "other",
    )

    _CREATE_TABLE = """
        CREATE TABLE IF NOT EXISTS action_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            memory_ids TEXT NOT NULL,
            outcome TEXT NOT NULL,
            action_type TEXT DEFAULT 'other',
            context TEXT DEFAULT '{}',
            confidence REAL DEFAULT 0.9,
            agent_id TEXT DEFAULT 'user',
            project TEXT,
            profile TEXT DEFAULT 'default',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path
        self._lock = threading.Lock()
        if db_path:
            self._ensure_table()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_outcome(
        self,
        memory_ids: List[int],
        outcome: str,
        action_type: str = "other",
        context: Optional[Dict[str, Any]] = None,
        confidence: float = 0.9,
        agent_id: str = "user",
        project: Optional[str] = None,
    ) -> Optional[int]:
        """Record an action outcome against one or more memories.

        Args:
            memory_ids: List of memory IDs involved in this outcome.
            outcome: One of OUTCOMES ("success", "failure", "partial").
            action_type: Category of the action taken.
            context: Arbitrary metadata dict (stored as JSON).
            confidence: Confidence in the outcome label (default 0.9).
            agent_id: Identifier for the reporting agent.
            project: Optional project scope.

        Returns:
            The row ID of the inserted outcome, or None if validation fails.
        """
        if outcome not in self.OUTCOMES:
            return None

        context_json = json.dumps(context or {})
        memory_ids_json = json.dumps(memory_ids)

        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    """INSERT INTO action_outcomes
                       (memory_ids, outcome, action_type, context,
                        confidence, agent_id, project)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        memory_ids_json,
                        outcome,
                        action_type,
                        context_json,
                        confidence,
                        agent_id,
                        project,
                    ),
                )
                conn.commit()
                return cur.lastrowid
            finally:
                conn.close()

    def get_outcomes(
        self,
        memory_id: Optional[int] = None,
        project: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query recorded outcomes with optional filters.

        Args:
            memory_id: If given, return only outcomes that include this
                       memory ID in their memory_ids list.
            project: If given, filter by project scope.
            limit: Maximum rows to return (default 100).

        Returns:
            List of outcome dicts with deserialized memory_ids and context.
        """
        with self._lock:
            conn = self._connect()
            try:
                query = "SELECT * FROM action_outcomes WHERE 1=1"
                params: List[Any] = []

                if project is not None:
                    query += " AND project = ?"
                    params.append(project)

                query += " ORDER BY created_at DESC LIMIT ?"
                params.append(limit)

                rows = conn.execute(query, params).fetchall()
                results = [self._row_to_dict(r) for r in rows]

                if memory_id is not None:
                    results = [
                        r for r in results if memory_id in r["memory_ids"]
                    ]

                return results
            finally:
                conn.close()

    def get_success_rate(self, memory_id: int) -> float:
        """Calculate success rate for a specific memory.

        Counts outcomes where memory_id appears in memory_ids.
        Returns success count / total count, or 0.0 if no outcomes.
        """
        outcomes = self.get_outcomes(memory_id=memory_id)
        if not outcomes:
            return 0.0
        successes = sum(1 for o in outcomes if o["outcome"] == "success")
        return round(successes / len(outcomes), 3)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        """Open a connection with row factory enabled."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_table(self) -> None:
        """Create the action_outcomes table if it doesn't exist."""
        conn = self._connect()
        try:
            conn.execute(self._CREATE_TABLE)
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        """Convert a sqlite3.Row into a plain dict with parsed JSON fields."""
        d = dict(row)
        d["memory_ids"] = json.loads(d.get("memory_ids", "[]"))
        ctx = d.get("context", "{}")
        d["context"] = json.loads(ctx) if isinstance(ctx, str) else ctx
        return d
