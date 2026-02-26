#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""
High-level signal helpers and burst detection mixin for TrustScorer.

Contains: on_memory_created, on_memory_deleted, on_memory_recalled,
          _track_write, _is_burst.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from .constants import (
    QUICK_DELETE_HOURS,
    BURST_THRESHOLD,
    BURST_WINDOW_MINUTES,
)

logger = logging.getLogger("superlocalmemory.trust")


class TrustSignalsMixin:
    """Mixin providing high-level signal helpers and burst detection."""

    # =========================================================================
    # High-Level Signal Helpers (called from memory_store_v2 / mcp_server)
    # =========================================================================

    def on_memory_created(self, agent_id: str, memory_id: int, importance: int = 5):
        """Record signals when a memory is created."""
        # Track write timestamp for burst detection
        self._track_write(agent_id)

        if importance >= 7:
            self.record_signal(agent_id, "high_importance_write",
                             context={"memory_id": memory_id, "importance": importance})
        else:
            self.record_signal(agent_id, "normal_write",
                             context={"memory_id": memory_id})

        # Check for burst pattern
        if self._is_burst(agent_id):
            self.record_signal(agent_id, "high_volume_burst",
                             context={"memory_id": memory_id})

    def on_memory_deleted(self, agent_id: str, memory_id: int, created_at: Optional[str] = None):
        """Record signals when a memory is deleted."""
        if created_at:
            try:
                created = datetime.fromisoformat(created_at)
                age_hours = (datetime.now() - created).total_seconds() / 3600
                if age_hours < QUICK_DELETE_HOURS:
                    self.record_signal(agent_id, "quick_delete",
                                     context={"memory_id": memory_id, "age_hours": round(age_hours, 2)})
                    return
            except (ValueError, TypeError):
                pass

        # Normal delete (no negative signal)
        self.record_signal(agent_id, "normal_write",
                         context={"memory_id": memory_id, "action": "delete"})

    def on_memory_recalled(self, agent_id: str, memory_id: int, created_by: Optional[str] = None):
        """Record signals when a memory is recalled."""
        if created_by and created_by != agent_id:
            # Cross-agent validation: another agent found this memory useful
            self.record_signal(created_by, "memory_recalled_by_others",
                             context={"memory_id": memory_id, "recalled_by": agent_id})

        self.record_signal(agent_id, "normal_recall",
                         context={"memory_id": memory_id})

    # =========================================================================
    # Burst Detection
    # =========================================================================

    def _track_write(self, agent_id: str):
        """Track a write timestamp for burst detection."""
        now = datetime.now()
        with self._timestamps_lock:
            if agent_id not in self._write_timestamps:
                self._write_timestamps[agent_id] = []
            timestamps = self._write_timestamps[agent_id]
            timestamps.append(now)
            # Keep only recent timestamps (within burst window)
            cutoff = now - timedelta(minutes=BURST_WINDOW_MINUTES)
            self._write_timestamps[agent_id] = [t for t in timestamps if t > cutoff]

    def _is_burst(self, agent_id: str) -> bool:
        """Check if agent is in a burst write pattern."""
        with self._timestamps_lock:
            timestamps = self._write_timestamps.get(agent_id, [])
            return len(timestamps) > BURST_THRESHOLD
