# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Pattern extraction from action outcome histories.

Scans the action_outcomes table, groups by project and action_type,
calculates success rates, and stores discovered patterns in the
behavioral_patterns table. Self-contained: creates its own table via
CREATE TABLE IF NOT EXISTS so no external migration is needed.

Part of SLM v2.8 Behavioral Learning Engine.
"""
import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any


class BehavioralPatternExtractor:
    """Extracts success/failure patterns from outcome data.

    Analyzes action_outcomes rows to discover:
      - project_success: success rate per project
      - action_type_success: success rate per action_type

    Confidence formula:
        min(evidence_count / 10, 1.0) * abs(success_rate - 0.5) * 2
    This yields high confidence only when there is enough evidence AND the
    success rate is far from the 50/50 coin-flip baseline.
    """

    PATTERN_TYPES = ("project_success", "action_type_success")

    _CREATE_TABLE = """
        CREATE TABLE IF NOT EXISTS behavioral_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_type TEXT NOT NULL,
            pattern_key TEXT NOT NULL,
            success_rate REAL DEFAULT 0.0,
            evidence_count INTEGER DEFAULT 0,
            confidence REAL DEFAULT 0.0,
            metadata TEXT DEFAULT '{}',
            project TEXT,
            profile TEXT DEFAULT 'default',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """

    # Minimum outcomes required before we emit a pattern at all.
    MIN_EVIDENCE = 3

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._patterns: List[Dict[str, Any]] = []
        if db_path:
            self._ensure_table()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_patterns(self) -> List[Dict[str, Any]]:
        """Scan action_outcomes and extract success/failure patterns.

        Groups outcomes by project and by action_type, calculates
        success rates, and returns a list of pattern dicts. Also stores
        the result internally so a subsequent ``save_patterns()`` call
        can persist them.

        Returns:
            List of pattern dicts with keys: pattern_type, pattern_key,
            success_rate, evidence_count, confidence, metadata, project.
        """
        patterns: List[Dict[str, Any]] = []
        with self._lock:
            conn = self._connect()
            try:
                patterns.extend(self._extract_project_patterns(conn))
                patterns.extend(self._extract_action_type_patterns(conn))
            finally:
                conn.close()
        self._patterns = patterns
        return patterns

    def save_patterns(self) -> int:
        """Persist the most recently extracted patterns to the DB.

        Inserts (or replaces) rows in the behavioral_patterns table.

        Returns:
            Number of patterns saved.
        """
        if not self._patterns:
            return 0

        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            conn = self._connect()
            try:
                for p in self._patterns:
                    # Upsert: delete any existing row for the same
                    # (pattern_type, pattern_key, project) then insert.
                    conn.execute(
                        """DELETE FROM behavioral_patterns
                           WHERE pattern_type = ? AND pattern_key = ?
                                 AND COALESCE(project, '') = COALESCE(?, '')""",
                        (p["pattern_type"], p["pattern_key"], p.get("project")),
                    )
                    conn.execute(
                        """INSERT INTO behavioral_patterns
                           (pattern_type, pattern_key, success_rate,
                            evidence_count, confidence, metadata,
                            project, created_at, updated_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            p["pattern_type"],
                            p["pattern_key"],
                            p["success_rate"],
                            p["evidence_count"],
                            p["confidence"],
                            json.dumps(p.get("metadata", {})),
                            p.get("project"),
                            now,
                            now,
                        ),
                    )
                conn.commit()
                return len(self._patterns)
            finally:
                conn.close()

    def get_patterns(
        self,
        min_confidence: float = 0.0,
        project: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Read stored patterns from the DB with optional filters.

        Args:
            min_confidence: Only return patterns with confidence >= this.
            project: If given, filter by project scope.

        Returns:
            List of pattern dicts read from the database.
        """
        with self._lock:
            conn = self._connect()
            try:
                query = (
                    "SELECT * FROM behavioral_patterns "
                    "WHERE confidence >= ?"
                )
                params: List[Any] = [min_confidence]
                if project is not None:
                    query += " AND project = ?"
                    params.append(project)
                query += " ORDER BY confidence DESC"
                rows = conn.execute(query, params).fetchall()
                return [self._row_to_dict(r) for r in rows]
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # Internal extraction helpers
    # ------------------------------------------------------------------

    def _extract_project_patterns(
        self, conn: sqlite3.Connection
    ) -> List[Dict[str, Any]]:
        """Group outcomes by project and compute success rates."""
        rows = conn.execute(
            """SELECT project,
                      COUNT(*) AS total,
                      SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) AS wins
               FROM action_outcomes
               WHERE project IS NOT NULL
               GROUP BY project
               HAVING total >= ?""",
            (self.MIN_EVIDENCE,),
        ).fetchall()

        patterns = []
        for row in rows:
            project = row[0]
            total = row[1]
            wins = row[2]
            rate = round(wins / total, 4) if total else 0.0
            confidence = self._compute_confidence(total, rate)
            patterns.append(
                {
                    "pattern_type": "project_success",
                    "pattern_key": project,
                    "success_rate": rate,
                    "evidence_count": total,
                    "confidence": confidence,
                    "metadata": {"wins": wins, "losses": total - wins},
                    "project": project,
                }
            )
        return patterns

    def _extract_action_type_patterns(
        self, conn: sqlite3.Connection
    ) -> List[Dict[str, Any]]:
        """Group outcomes by action_type and compute success rates."""
        rows = conn.execute(
            """SELECT action_type,
                      COUNT(*) AS total,
                      SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) AS wins
               FROM action_outcomes
               WHERE action_type IS NOT NULL
               GROUP BY action_type
               HAVING total >= ?""",
            (self.MIN_EVIDENCE,),
        ).fetchall()

        patterns = []
        for row in rows:
            action_type = row[0]
            total = row[1]
            wins = row[2]
            rate = round(wins / total, 4) if total else 0.0
            confidence = self._compute_confidence(total, rate)
            patterns.append(
                {
                    "pattern_type": "action_type_success",
                    "pattern_key": action_type,
                    "success_rate": rate,
                    "evidence_count": total,
                    "confidence": confidence,
                    "metadata": {"wins": wins, "losses": total - wins},
                    "project": None,
                }
            )
        return patterns

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_confidence(evidence_count: int, success_rate: float) -> float:
        """Confidence = min(evidence/10, 1.0) * abs(rate - 0.5) * 2.

        High confidence requires both sufficient evidence AND a success
        rate that deviates significantly from the 50% baseline.
        """
        evidence_factor = min(evidence_count / 10.0, 1.0)
        deviation_factor = abs(success_rate - 0.5) * 2.0
        return round(evidence_factor * deviation_factor, 4)

    def _connect(self) -> sqlite3.Connection:
        """Open a connection with row factory enabled."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_table(self) -> None:
        """Create the behavioral_patterns table if it doesn't exist."""
        conn = self._connect()
        try:
            conn.execute(self._CREATE_TABLE)
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        """Convert a sqlite3.Row into a plain dict with parsed JSON."""
        d = dict(row)
        meta = d.get("metadata", "{}")
        d["metadata"] = json.loads(meta) if isinstance(meta, str) else meta
        return d
