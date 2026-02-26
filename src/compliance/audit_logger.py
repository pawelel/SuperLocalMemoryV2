# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""EventBus listener that writes all events to audit.db.

Bridges the EventBus (real-time event emission) with AuditDB (tamper-evident
audit trail). Every event that passes through the EventBus gets persisted
into audit.db with full hash-chain integrity.

Thread-safe: handle_event() runs on the emitter's thread and must be fast.
Graceful: malformed events are logged defensively, never crash the caller.
"""
import json
import logging
import threading
from typing import Any, Dict, Optional

from .audit_db import AuditDB

logger = logging.getLogger("superlocalmemory.compliance.audit_logger")


class AuditLogger:
    """Listens to EventBus events and writes them to audit.db.

    Usage:
        audit_logger = AuditLogger("/path/to/audit.db")
        audit_logger.register_with_eventbus()  # auto-subscribe

    Or manually:
        event_bus.add_listener(audit_logger.handle_event)
    """

    def __init__(self, audit_db_path: str):
        self._audit_db = AuditDB(audit_db_path)
        self._lock = threading.Lock()
        self._events_logged: int = 0
        self._errors: int = 0
        self._registered: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def events_logged(self) -> int:
        """Total number of events successfully written to audit.db."""
        return self._events_logged

    def handle_event(self, event: Dict[str, Any]) -> None:
        """Process a single EventBus event and write it to audit.db.

        Extracts event_type, source_agent (actor), memory_id (resource_id),
        and payload (details) from the event dict, then delegates to
        AuditDB.log_event().

        This method MUST NOT raise — it runs on the emitter's thread.
        Any failure is caught, logged, and counted in self._errors.

        Args:
            event: Dict emitted by EventBus. Expected keys:
                   event_type, source_agent, memory_id, payload, timestamp.
                   All keys are optional for graceful degradation.
        """
        try:
            if not isinstance(event, dict):
                logger.warning("AuditLogger received non-dict event: %s", type(event))
                return

            event_type = event.get("event_type", "unknown")
            actor = event.get("source_agent", "system")
            resource_id = event.get("memory_id")
            payload = event.get("payload", {})

            # Build details dict including any extra context
            details = {}
            if isinstance(payload, dict):
                details.update(payload)
            else:
                details["raw_payload"] = str(payload)

            # Include timestamp from event if present
            ts = event.get("timestamp")
            if ts:
                details["event_timestamp"] = ts

            with self._lock:
                self._audit_db.log_event(
                    event_type=event_type,
                    actor=actor,
                    resource_id=resource_id,
                    details=details,
                )
                self._events_logged += 1

        except Exception as exc:
            self._errors += 1
            logger.error(
                "AuditLogger failed to log event: %s (event=%s)",
                exc,
                _safe_repr(event),
            )

    def register_with_eventbus(self) -> bool:
        """Register this logger as an EventBus listener.

        Attempts to find the EventBus singleton and subscribe
        handle_event as a listener. Returns True on success,
        False if EventBus is unavailable.

        Graceful: never raises; returns False on any failure.
        """
        try:
            from event_bus import EventBus as EB

            bus = EB.get_instance()
            bus.add_listener(self.handle_event)
            self._registered = True
            logger.info("AuditLogger registered with EventBus")
            return True
        except Exception as exc:
            logger.warning("AuditLogger could not register with EventBus: %s", exc)
            self._registered = False
            return False

    def get_status(self) -> Dict[str, Any]:
        """Return diagnostic status of this audit logger.

        Returns:
            Dict with keys: events_logged, errors, registered.
        """
        return {
            "events_logged": self._events_logged,
            "errors": self._errors,
            "registered": self._registered,
        }


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _safe_repr(obj: Any, max_len: int = 200) -> str:
    """Safe repr that truncates and never raises."""
    try:
        r = repr(obj)
        return r[:max_len] + "..." if len(r) > max_len else r
    except Exception:
        return "<unrepresentable>"
