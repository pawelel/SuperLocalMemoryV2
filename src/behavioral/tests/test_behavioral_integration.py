# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Tests for behavioral engine EventBus integration.
"""
import sqlite3
import tempfile
import os
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestBehavioralIntegration:
    """Test behavioral engine wiring with EventBus."""

    def setup_method(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmp_dir, "learning.db")

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_create_behavioral_listener(self):
        """BehavioralListener can be instantiated."""
        from behavioral.behavioral_listener import BehavioralListener
        listener = BehavioralListener(self.db_path)
        assert listener is not None

    def test_listener_handles_recall_event(self):
        """Listener processes memory.recalled events."""
        from behavioral.behavioral_listener import BehavioralListener
        listener = BehavioralListener(self.db_path)
        event = {
            "event_type": "memory.recalled",
            "memory_id": 1,
            "payload": {"query": "test query", "memory_ids": [1, 2]},
            "timestamp": datetime.now().isoformat(),
        }
        # Should not raise
        listener.handle_event(event)
        assert listener.events_processed >= 1

    def test_listener_ignores_irrelevant_events(self):
        """Listener ignores non-recall events."""
        from behavioral.behavioral_listener import BehavioralListener
        listener = BehavioralListener(self.db_path)
        event = {
            "event_type": "memory.created",
            "memory_id": 1,
            "payload": {},
            "timestamp": datetime.now().isoformat(),
        }
        listener.handle_event(event)
        assert listener.recall_events_processed == 0

    def test_listener_handles_deletion_event(self):
        """Listener records deletion events for inference."""
        from behavioral.behavioral_listener import BehavioralListener
        listener = BehavioralListener(self.db_path)
        event = {
            "event_type": "memory.deleted",
            "memory_id": 5,
            "payload": {},
            "timestamp": datetime.now().isoformat(),
        }
        listener.handle_event(event)
        assert listener.deletion_events_processed >= 1

    def test_listener_tracks_usage_signals(self):
        """Listener records usage signals (memory_used) for inference."""
        from behavioral.behavioral_listener import BehavioralListener
        listener = BehavioralListener(self.db_path)
        event = {
            "event_type": "memory.recalled",
            "memory_id": 1,
            "payload": {"query": "test", "memory_ids": [1], "signal": "mcp_used_high"},
            "timestamp": datetime.now().isoformat(),
        }
        listener.handle_event(event)
        assert listener.events_processed >= 1

    def test_graceful_degradation_no_eventbus(self):
        """If EventBus unavailable, behavioral engine still works."""
        from behavioral.behavioral_listener import BehavioralListener
        listener = BehavioralListener(self.db_path)
        # register_with_eventbus should not crash even if EventBus fails
        result = listener.register_with_eventbus()
        # Result depends on whether EventBus is importable in test env
        assert isinstance(result, bool)

    def test_pattern_extraction_threshold(self):
        """Pattern extraction triggers after outcome count threshold."""
        from behavioral.behavioral_listener import BehavioralListener
        listener = BehavioralListener(self.db_path, extraction_threshold=5)
        assert listener.extraction_threshold == 5

    def test_get_status(self):
        """Listener reports its status."""
        from behavioral.behavioral_listener import BehavioralListener
        listener = BehavioralListener(self.db_path)
        status = listener.get_status()
        assert "events_processed" in status
        assert "recall_events_processed" in status
        assert "registered" in status
