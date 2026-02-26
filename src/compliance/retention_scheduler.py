# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Background scheduler for periodic retention policy enforcement.

Runs on a configurable interval (default: 24 hours) to:
1. Load compliance retention rules from audit.db
2. Scan all memories in memory.db against those rules
3. Tombstone expired memories (age exceeds retention_days)
4. Log every action to audit.db for tamper-evident compliance

Uses daemon threading -- does not prevent process exit.
"""
import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .retention_manager import ComplianceRetentionManager

logger = logging.getLogger(__name__)

# Default interval: 24 hours
DEFAULT_INTERVAL_SECONDS = 86400


class RetentionScheduler:
    """Background scheduler for periodic retention policy enforcement.

    Orchestrates ComplianceRetentionManager on a configurable timer
    interval to automatically enforce retention rules.
    """

    def __init__(
        self,
        memory_db_path: str,
        audit_db_path: str,
        interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
    ):
        self._memory_db_path = memory_db_path
        self._audit_db_path = audit_db_path
        self.interval_seconds = interval_seconds

        self._manager = ComplianceRetentionManager(
            memory_db_path, audit_db_path,
        )

        self._timer: Optional[threading.Timer] = None
        self._running = False
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        """Whether the scheduler is currently running."""
        return self._running

    def start(self) -> None:
        """Start the background scheduler."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._schedule_next()

    def stop(self) -> None:
        """Stop the background scheduler."""
        with self._lock:
            self._running = False
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

    def run_now(self) -> Dict[str, Any]:
        """Execute a retention enforcement cycle immediately.

        Returns:
            Dict with timestamp, actions taken, and rules evaluated.
        """
        return self._execute_cycle()

    def _schedule_next(self) -> None:
        """Schedule the next enforcement cycle."""
        self._timer = threading.Timer(self.interval_seconds, self._run_cycle)
        self._timer.daemon = True
        self._timer.start()

    def _run_cycle(self) -> None:
        """Run one enforcement cycle, then schedule the next."""
        try:
            self._execute_cycle()
        except Exception:
            pass  # Scheduler must not crash
        finally:
            with self._lock:
                if self._running:
                    self._schedule_next()

    def _execute_cycle(self) -> Dict[str, Any]:
        """Core retention enforcement logic.

        1. Load all retention rules from audit.db
        2. Scan every memory against each rule
        3. Tombstone memories that exceed retention_days
        4. Log actions to audit.db
        """
        rules = self._manager.list_rules()
        actions: List[Dict[str, Any]] = []

        # Scan all memories
        memory_ids = self._get_all_memory_ids()

        for mem_id in memory_ids:
            mem = self._get_memory(mem_id)
            if mem is None:
                continue

            # Already tombstoned -- skip
            if mem.get("lifecycle_state") == "tombstoned":
                continue

            match = self._manager.evaluate_memory(mem_id)
            if match is None:
                continue

            # Check if memory age exceeds the rule's retention_days
            created_at = mem.get("created_at")
            if created_at is None:
                continue

            age_days = self._age_in_days(created_at)
            if age_days > match["retention_days"]:
                action = match["action"]
                if action == "tombstone":
                    result = self._manager.execute_erasure_request(
                        mem_id, match["framework"], "retention_scheduler",
                    )
                    actions.append({
                        "memory_id": mem_id,
                        "action": action,
                        "rule_name": match["rule_name"],
                        "framework": match["framework"],
                        "age_days": age_days,
                        "success": result.get("success", False),
                    })

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "actions": actions,
            "rules_evaluated": len(rules),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_all_memory_ids(self) -> List[int]:
        """Return all memory IDs from memory.db."""
        conn = sqlite3.connect(self._memory_db_path)
        try:
            rows = conn.execute("SELECT id FROM memories").fetchall()
            return [r[0] for r in rows]
        finally:
            conn.close()

    def _get_memory(self, memory_id: int) -> Optional[Dict[str, Any]]:
        """Fetch a single memory row as a dict."""
        conn = sqlite3.connect(self._memory_db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT * FROM memories WHERE id = ?", (memory_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    @staticmethod
    def _age_in_days(created_at_str: str) -> float:
        """Calculate age of a memory in days from its created_at."""
        try:
            created = datetime.fromisoformat(created_at_str)
            now = datetime.now(created.tzinfo)
            return (now - created).total_seconds() / 86400
        except (ValueError, TypeError):
            return 0.0
