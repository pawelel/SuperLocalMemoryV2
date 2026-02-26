# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Compliance retention manager — regulatory retention enforcement.

Unlike the lifecycle ``retention_policy.py`` (which manages lifecycle-level
policies stored alongside memory.db), this compliance module is the
*regulatory* layer that:

- Links retention rules to regulatory frameworks (GDPR, EU AI Act, HIPAA).
- Enforces GDPR right-to-erasure (tombstone memory + preserve audit trail).
- Enforces EU AI Act audit retention (10-year minimum for audit records).
- Records every retention action in audit.db for tamper-evident compliance.

Rules are stored in audit.db (``compliance_retention_rules`` table) so that
the audit database remains the single source of truth for all compliance
configuration and evidence.
"""
import hashlib
import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_RULES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS compliance_retention_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    framework TEXT NOT NULL,
    retention_days INTEGER NOT NULL,
    action TEXT NOT NULL,
    applies_to TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

_AUDIT_EVENTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    resource_id INTEGER,
    details TEXT DEFAULT '{}',
    prev_hash TEXT NOT NULL DEFAULT 'genesis',
    entry_hash TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""


def _compute_hash(event_type: str, actor: str, resource_id: Any,
                  details: str, prev_hash: str, ts: str) -> str:
    """Compute a SHA-256 hash for a single audit event."""
    payload = f"{event_type}|{actor}|{resource_id}|{details}|{prev_hash}|{ts}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ComplianceRetentionManager:
    """Enforces regulatory retention policies across memory and audit DBs.

    Connects to *both* databases:
    - ``memory_db_path``: where memories live (tombstoning happens here).
    - ``audit_db_path``: where rules and audit events are stored.
    """

    def __init__(self, memory_db_path: str, audit_db_path: str):
        self._memory_db_path = memory_db_path
        self._audit_db_path = audit_db_path
        self._ensure_tables()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _connect_audit(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._audit_db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _connect_memory(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._memory_db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self) -> None:
        conn = self._connect_audit()
        try:
            conn.execute(_RULES_TABLE_SQL)
            conn.execute(_AUDIT_EVENTS_TABLE_SQL)
            conn.commit()
        finally:
            conn.close()

    def _log_audit_event(self, event_type: str, actor: str,
                         resource_id: Optional[int],
                         details: Dict[str, Any]) -> None:
        """Append a tamper-evident audit event to audit.db."""
        conn = self._connect_audit()
        try:
            last = conn.execute(
                "SELECT entry_hash FROM audit_events ORDER BY id DESC LIMIT 1"
            ).fetchone()
            prev_hash = last["entry_hash"] if last else "genesis"
            ts = datetime.now(timezone.utc).isoformat()
            details_json = json.dumps(details, default=str)
            entry_hash = _compute_hash(
                event_type, actor, resource_id, details_json, prev_hash, ts,
            )
            conn.execute(
                "INSERT INTO audit_events "
                "(event_type, actor, resource_id, details, prev_hash, entry_hash, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (event_type, actor, resource_id, details_json, prev_hash,
                 entry_hash, ts),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _parse_json(value: Any) -> Any:
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
        return value if value is not None else []

    @staticmethod
    def _matches(criteria: Any, mem_tags: Any, mem_project: Optional[str]) -> bool:
        """Return True when a rule's ``applies_to`` matches the memory."""
        if not isinstance(criteria, dict) or not criteria:
            return False
        ok = True
        if "tags" in criteria:
            rule_tags = set(criteria["tags"]) if criteria["tags"] else set()
            m_tags = set(mem_tags) if isinstance(mem_tags, list) else set()
            if not rule_tags & m_tags:
                ok = False
        if "project_name" in criteria:
            if mem_project != criteria["project_name"]:
                ok = False
        return ok

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_retention_rule(self, name: str, framework: str,
                              retention_days: int, action: str,
                              applies_to: Dict[str, Any]) -> int:
        """Create a compliance retention rule in audit.db.

        Returns the auto-generated rule ID.
        """
        conn = self._connect_audit()
        try:
            cur = conn.execute(
                "INSERT INTO compliance_retention_rules "
                "(name, framework, retention_days, action, applies_to) "
                "VALUES (?, ?, ?, ?, ?)",
                (name, framework, retention_days, action,
                 json.dumps(applies_to)),
            )
            conn.commit()
            rule_id = cur.lastrowid
        finally:
            conn.close()

        self._log_audit_event(
            "retention.rule_created", "system", rule_id,
            {"name": name, "framework": framework},
        )
        return rule_id

    def list_rules(self) -> List[Dict[str, Any]]:
        """Return all compliance retention rules."""
        conn = self._connect_audit()
        try:
            rows = conn.execute(
                "SELECT * FROM compliance_retention_rules ORDER BY id"
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                if isinstance(d.get("applies_to"), str):
                    d["applies_to"] = self._parse_json(d["applies_to"])
                result.append(d)
            return result
        finally:
            conn.close()

    def evaluate_memory(self, memory_id: int) -> Optional[Dict[str, Any]]:
        """Check which compliance rule applies to a memory.

        Reads the memory's tags/project from memory.db, then evaluates
        all rules from audit.db. The first matching rule (ordered by id)
        is returned.

        Returns a dict with ``rule_name``, ``action``, ``retention_days``,
        ``framework``; or ``None`` if no rule matches.
        """
        mem_conn = self._connect_memory()
        try:
            mem = mem_conn.execute(
                "SELECT tags, project_name FROM memories WHERE id = ?",
                (memory_id,),
            ).fetchone()
            if mem is None:
                return None
            mem_tags = self._parse_json(mem["tags"])
            mem_project = mem["project_name"]
        finally:
            mem_conn.close()

        audit_conn = self._connect_audit()
        try:
            rules = audit_conn.execute(
                "SELECT * FROM compliance_retention_rules ORDER BY id"
            ).fetchall()
            for rule in rules:
                criteria = self._parse_json(rule["applies_to"])
                if self._matches(criteria, mem_tags, mem_project):
                    return {
                        "rule_name": rule["name"],
                        "action": rule["action"],
                        "retention_days": rule["retention_days"],
                        "framework": rule["framework"],
                    }
            return None
        finally:
            audit_conn.close()

    def execute_erasure_request(self, memory_id: int, framework: str,
                                requested_by: str) -> Dict[str, Any]:
        """Execute a GDPR (or other framework) right-to-erasure request.

        1. Tombstones the memory in memory.db.
        2. Logs the erasure event in audit.db (preserving the audit trail).

        Returns a result dict with ``success``, ``action``, and ``memory_id``.
        """
        mem_conn = self._connect_memory()
        try:
            row = mem_conn.execute(
                "SELECT id FROM memories WHERE id = ?", (memory_id,),
            ).fetchone()
            if row is None:
                return {"success": False, "error": "memory_not_found",
                        "memory_id": memory_id}

            ts = datetime.now(timezone.utc).isoformat()
            mem_conn.execute(
                "UPDATE memories SET lifecycle_state = 'tombstoned', "
                "lifecycle_updated_at = ? WHERE id = ?",
                (ts, memory_id),
            )
            mem_conn.commit()
        finally:
            mem_conn.close()

        self._log_audit_event(
            "retention.erasure", requested_by, memory_id,
            {"framework": framework, "action": "tombstoned"},
        )

        return {"success": True, "action": "tombstoned",
                "memory_id": memory_id}

    def get_compliance_status(self) -> Dict[str, Any]:
        """Return a summary of current compliance retention state."""
        conn = self._connect_audit()
        try:
            rules = conn.execute(
                "SELECT * FROM compliance_retention_rules"
            ).fetchall()
            frameworks = list({r["framework"] for r in rules})
            events_count = conn.execute(
                "SELECT COUNT(*) AS cnt FROM audit_events"
            ).fetchone()["cnt"]
            return {
                "rules_count": len(rules),
                "frameworks": sorted(frameworks),
                "audit_events_count": events_count,
            }
        finally:
            conn.close()
