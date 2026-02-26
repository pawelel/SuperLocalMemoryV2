# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Retention policy loading, evaluation, and enforcement.

Manages retention policies that determine how long memories must be kept
in specific states. Supports GDPR (right to erasure), EU AI Act (audit
retention), and HIPAA (medical record retention) compliance frameworks.

Policies are stored in a `retention_policies` table alongside the memories
database. Each policy specifies criteria (tags, project_name) for matching
memories and an action (retain, archive, tombstone) with a retention period.
"""
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

_POLICIES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS retention_policies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    retention_days INTEGER NOT NULL,
    framework TEXT NOT NULL,
    action TEXT NOT NULL,
    applies_to TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""


class RetentionPolicyManager:
    """Manages retention policies for lifecycle enforcement.

    Evaluates which compliance policies apply to each memory based on
    tag and project_name matching. When multiple policies match, the
    strictest (shortest retention_days) wins.
    """

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path
        if db_path:
            self._ensure_table()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        """Open a connection to the database."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_table(self) -> None:
        """Create the retention_policies table if it doesn't exist."""
        conn = self._connect()
        try:
            conn.execute(_POLICIES_TABLE_SQL)
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_policy(
        self,
        name: str,
        retention_days: int,
        framework: str,
        action: str,
        applies_to: Dict[str, Any],
    ) -> int:
        """Create a new retention policy.

        Args:
            name: Human-readable policy name.
            retention_days: Minimum days to retain (0 = immediate action).
            framework: Compliance framework (gdpr, hipaa, eu_ai_act, internal).
            action: What to do (retain, archive, tombstone).
            applies_to: Criteria dict with optional keys: tags, project_name.

        Returns:
            The auto-generated policy ID.
        """
        conn = self._connect()
        try:
            cursor = conn.execute(
                "INSERT INTO retention_policies (name, retention_days, framework, action, applies_to) "
                "VALUES (?, ?, ?, ?, ?)",
                (name, retention_days, framework, action, json.dumps(applies_to)),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def list_policies(self) -> List[Dict[str, Any]]:
        """Return all retention policies as a list of dicts."""
        conn = self._connect()
        try:
            rows = conn.execute("SELECT * FROM retention_policies ORDER BY id").fetchall()
            return [self._row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def load_policies(self, path: str) -> int:
        """Load retention policies from a JSON file.

        The file must contain a JSON array of policy objects, each with
        keys: name, retention_days, framework, action, applies_to.

        Args:
            path: Absolute or relative path to the JSON policy file.

        Returns:
            Number of policies loaded. Returns 0 if file is missing or
            contains invalid data, without raising an exception.
        """
        policy_path = Path(path)
        if not policy_path.exists():
            logger.debug("Policy file not found: %s", path)
            return 0

        try:
            data = json.loads(policy_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read policy file %s: %s", path, exc)
            return 0

        if not isinstance(data, list):
            logger.warning("Policy file must contain a JSON array: %s", path)
            return 0

        count = 0
        for entry in data:
            try:
                self.create_policy(
                    name=entry["name"],
                    retention_days=entry["retention_days"],
                    framework=entry["framework"],
                    action=entry["action"],
                    applies_to=entry.get("applies_to", {}),
                )
                count += 1
            except (KeyError, TypeError) as exc:
                logger.warning("Skipping invalid policy entry: %s", exc)

        return count

    def evaluate_memory(self, memory_id: int) -> Optional[Dict[str, Any]]:
        """Determine which retention policy applies to a memory.

        Loads the memory's tags and project_name, then checks every
        policy's ``applies_to`` criteria. If multiple policies match,
        the **strictest** one wins (lowest ``retention_days``).

        Args:
            memory_id: The memory row ID.

        Returns:
            A dict with ``policy_name``, ``action``, ``retention_days``,
            and ``framework``; or ``None`` if no policy matches.
        """
        conn = self._connect()
        try:
            mem_row = conn.execute(
                "SELECT tags, project_name FROM memories WHERE id = ?",
                (memory_id,),
            ).fetchone()
            if mem_row is None:
                return None

            mem_tags = self._parse_json_field(mem_row["tags"])
            mem_project = mem_row["project_name"]

            policies = conn.execute(
                "SELECT * FROM retention_policies ORDER BY retention_days ASC"
            ).fetchall()

            for policy in policies:
                criteria = self._parse_json_field(policy["applies_to"])
                if self._policy_matches(criteria, mem_tags, mem_project):
                    return {
                        "policy_name": policy["name"],
                        "action": policy["action"],
                        "retention_days": policy["retention_days"],
                        "framework": policy["framework"],
                    }

            return None
        finally:
            conn.close()

    def get_protected_memory_ids(self) -> Set[int]:
        """Return the set of memory IDs protected by any ``retain`` policy.

        A memory is protected if at least one policy with
        ``action='retain'`` matches its tags or project_name.
        """
        conn = self._connect()
        try:
            retain_policies = conn.execute(
                "SELECT * FROM retention_policies WHERE action = 'retain'"
            ).fetchall()
            if not retain_policies:
                return set()

            memories = conn.execute(
                "SELECT id, tags, project_name FROM memories"
            ).fetchall()

            protected: Set[int] = set()
            for mem in memories:
                mem_tags = self._parse_json_field(mem["tags"])
                mem_project = mem["project_name"]
                for policy in retain_policies:
                    criteria = self._parse_json_field(policy["applies_to"])
                    if self._policy_matches(criteria, mem_tags, mem_project):
                        protected.add(mem["id"])
                        break  # One matching retain policy is enough

            return protected
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        """Convert a sqlite3.Row to a plain dict with parsed applies_to."""
        d = dict(row)
        if "applies_to" in d and isinstance(d["applies_to"], str):
            try:
                d["applies_to"] = json.loads(d["applies_to"])
            except (json.JSONDecodeError, TypeError):
                d["applies_to"] = {}
        return d

    @staticmethod
    def _parse_json_field(value: Any) -> Any:
        """Parse a JSON string field; return as-is if already parsed."""
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
        return value if value is not None else []

    @staticmethod
    def _policy_matches(
        criteria: Any, mem_tags: Any, mem_project: Optional[str]
    ) -> bool:
        """Check if a policy's applies_to criteria match a memory.

        Matching rules:
        - If criteria has ``tags``: memory must have at least one
          overlapping tag.
        - If criteria has ``project_name``: memory's project_name
          must equal the criteria value.
        - If criteria is empty (``{}``): the policy does NOT match
          any memory (opt-in only).
        """
        if not isinstance(criteria, dict) or not criteria:
            return False

        matched = True  # Assume match; any failing criterion flips to False

        if "tags" in criteria:
            policy_tags = set(criteria["tags"]) if criteria["tags"] else set()
            memory_tags = set(mem_tags) if isinstance(mem_tags, list) else set()
            if not policy_tags & memory_tags:
                matched = False

        if "project_name" in criteria:
            if mem_project != criteria["project_name"]:
                matched = False

        return matched
