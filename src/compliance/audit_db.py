# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Audit database management with hash chain tamper detection.

Provides a tamper-evident audit trail stored in a separate audit.db.
Each entry's hash incorporates the previous entry's hash, forming a
chain that can detect any modification to historical records.
"""
import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


_GENESIS = "genesis"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    resource_id INTEGER,
    details TEXT DEFAULT '{}',
    prev_hash TEXT NOT NULL,
    entry_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""


def _compute_hash(
    event_type: str,
    actor: str,
    resource_id: Optional[int],
    details: str,
    prev_hash: str,
    created_at: str,
) -> str:
    """Compute SHA-256 hash for an audit entry."""
    payload = (
        f"{event_type}{actor}{resource_id}{details}{prev_hash}{created_at}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AuditDB:
    """Manages audit.db -- tamper-evident compliance audit trail.

    The hash chain guarantees that any modification to a stored event
    will be detected by verify_chain(). The first entry uses a fixed
    genesis value as its previous hash.
    """

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path
        self._lock = threading.Lock()
        if db_path:
            self._init_db()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        try:
            conn.executescript(_SCHEMA)
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log_event(
        self,
        event_type: str,
        actor: str = "system",
        resource_id: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Append an event to the audit trail and return its row id."""
        details_str = json.dumps(details or {}, sort_keys=True)
        created_at = datetime.now(timezone.utc).isoformat()

        with self._lock:
            conn = self._get_conn()
            try:
                # Fetch the hash of the most recent entry (or genesis)
                row = conn.execute(
                    "SELECT entry_hash FROM audit_events "
                    "ORDER BY id DESC LIMIT 1"
                ).fetchone()
                prev_hash = row["entry_hash"] if row else _GENESIS

                entry_hash = _compute_hash(
                    event_type, actor, resource_id,
                    details_str, prev_hash, created_at,
                )

                cursor = conn.execute(
                    "INSERT INTO audit_events "
                    "(event_type, actor, resource_id, details, "
                    " prev_hash, entry_hash, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        event_type, actor, resource_id,
                        details_str, prev_hash, entry_hash, created_at,
                    ),
                )
                conn.commit()
                return cursor.lastrowid
            finally:
                conn.close()

    def query_events(
        self,
        event_type: Optional[str] = None,
        actor: Optional[str] = None,
        resource_id: Optional[int] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query audit events with optional filters."""
        clauses: List[str] = []
        params: List[Any] = []

        if event_type is not None:
            clauses.append("event_type = ?")
            params.append(event_type)
        if actor is not None:
            clauses.append("actor = ?")
            params.append(actor)
        if resource_id is not None:
            clauses.append("resource_id = ?")
            params.append(resource_id)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            f"SELECT id, event_type, actor, resource_id, details, "
            f"prev_hash, entry_hash, created_at "
            f"FROM audit_events {where} "
            f"ORDER BY id DESC LIMIT ?"
        )
        params.append(limit)

        conn = self._get_conn()
        try:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def verify_chain(self) -> Dict[str, Any]:
        """Verify the integrity of the entire hash chain.

        Returns a dict with:
            valid            -- bool, True if chain is intact
            entries_checked  -- int, number of entries verified
            error            -- str or None, description of first failure
        """
        conn = self._get_conn()
        try:
            rows = conn.execute(
                "SELECT id, event_type, actor, resource_id, details, "
                "prev_hash, entry_hash, created_at "
                "FROM audit_events ORDER BY id"
            ).fetchall()
        finally:
            conn.close()

        if not rows:
            return {"valid": True, "entries_checked": 0, "error": None}

        expected_prev = _GENESIS
        for row in rows:
            row = dict(row)
            # Check the prev_hash link
            if row["prev_hash"] != expected_prev:
                return {
                    "valid": False,
                    "entries_checked": row["id"],
                    "error": f"prev_hash mismatch at entry {row['id']}",
                }
            # Recompute the entry hash
            computed = _compute_hash(
                row["event_type"],
                row["actor"],
                row["resource_id"],
                row["details"],
                row["prev_hash"],
                row["created_at"],
            )
            if computed != row["entry_hash"]:
                return {
                    "valid": False,
                    "entries_checked": row["id"],
                    "error": f"entry_hash mismatch at entry {row['id']}",
                }
            expected_prev = row["entry_hash"]

        return {
            "valid": True,
            "entries_checked": len(rows),
            "error": None,
        }
