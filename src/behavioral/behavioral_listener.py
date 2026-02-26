# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""EventBus listener that bridges events to the behavioral learning engine.

Listens for memory.recalled, memory.deleted, and usage events.
Feeds recall events to OutcomeInference for implicit outcome detection.
Triggers pattern extraction after configurable outcome count threshold.

Part of SLM v2.8 Behavioral Learning Engine.
"""
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

from .outcome_tracker import OutcomeTracker
from .outcome_inference import OutcomeInference

logger = logging.getLogger("superlocalmemory.behavioral.listener")

# Default: extract patterns every 100 new outcomes
DEFAULT_EXTRACTION_THRESHOLD = 100


class BehavioralListener:
    """EventBus listener that feeds events to the behavioral learning engine.

    Processes:
    - memory.recalled  -> feeds to OutcomeInference (implicit outcome detection)
    - memory.deleted   -> records deletion for inference (Rule 1 signal)
    - Usage signals    -> records for inference (Rule 2/3 signals)

    Thread-safe: handle_event can be called from any thread.
    Listener callbacks run on the emitter's thread -- must be fast.
    """

    # Event types this listener cares about
    _RECALL_EVENT = "memory.recalled"
    _DELETION_EVENT = "memory.deleted"

    def __init__(
        self,
        db_path: Optional[str] = None,
        extraction_threshold: int = DEFAULT_EXTRACTION_THRESHOLD,
    ):
        if db_path is None:
            db_path = str(Path.home() / ".claude-memory" / "learning.db")
        self._db_path = str(db_path)
        self.extraction_threshold = extraction_threshold

        # Core components
        self._tracker = OutcomeTracker(self._db_path)
        self._inference = OutcomeInference()

        # Thread safety
        self._lock = threading.Lock()

        # Counters
        self.events_processed = 0
        self.recall_events_processed = 0
        self.deletion_events_processed = 0
        self._outcome_count_since_extraction = 0
        self._registered = False

    # ------------------------------------------------------------------
    # Event handling (called on emitter's thread — must be fast)
    # ------------------------------------------------------------------

    def handle_event(self, event: Dict[str, Any]) -> None:
        """Process an EventBus event.

        Called on the emitter's thread — must be fast and non-blocking.
        Filters by event_type and dispatches to the appropriate handler.
        """
        event_type = event.get("event_type", "")
        payload = event.get("payload", {})
        memory_id = event.get("memory_id")
        timestamp_str = event.get("timestamp")

        try:
            timestamp = (
                datetime.fromisoformat(timestamp_str)
                if timestamp_str
                else datetime.now()
            )
        except (ValueError, TypeError):
            timestamp = datetime.now()

        with self._lock:
            self.events_processed += 1

            if event_type == self._RECALL_EVENT:
                self._handle_recall(payload, memory_id, timestamp)

            elif event_type == self._DELETION_EVENT:
                self._handle_deletion(memory_id, timestamp)
            # All other event types are silently ignored

    def _handle_recall(
        self,
        payload: Dict[str, Any],
        memory_id: Optional[int],
        timestamp: datetime,
    ) -> None:
        """Process a memory.recalled event. Must be called under self._lock."""
        query = payload.get("query", "")
        memory_ids = payload.get(
            "memory_ids", [memory_id] if memory_id else []
        )
        signal = payload.get("signal")

        self._inference.record_recall(query, memory_ids, timestamp)
        if signal:
            self._inference.record_usage(
                query, signal=signal, timestamp=timestamp
            )
        self.recall_events_processed += 1

        # Periodically run inference (every 10 recall events)
        if self.recall_events_processed % 10 == 0:
            self._run_inference_cycle()

    def _handle_deletion(
        self, memory_id: Optional[int], timestamp: datetime
    ) -> None:
        """Process a memory.deleted event. Must be called under self._lock."""
        if memory_id is not None:
            self._inference.record_deletion(memory_id, timestamp)
            self.deletion_events_processed += 1

    # ------------------------------------------------------------------
    # Inference + pattern extraction
    # ------------------------------------------------------------------

    def _run_inference_cycle(self) -> None:
        """Run outcome inference and optionally trigger pattern extraction."""
        inferences: List[Dict] = self._inference.infer_outcomes(
            datetime.now()
        )
        for inf in inferences:
            self._tracker.record_outcome(
                memory_ids=inf["memory_ids"],
                outcome=inf["outcome"],
                action_type="inferred",
                confidence=inf["confidence"],
                context={"reason": inf.get("reason", "")},
            )
            self._outcome_count_since_extraction += 1

        if self._outcome_count_since_extraction >= self.extraction_threshold:
            self._trigger_extraction()

    def _trigger_extraction(self) -> None:
        """Trigger behavioral pattern extraction. Best-effort."""
        try:
            from .behavioral_patterns import BehavioralPatternExtractor

            extractor = BehavioralPatternExtractor(self._db_path)
            extractor.extract_patterns()
            extractor.save_patterns()
            self._outcome_count_since_extraction = 0
        except Exception as exc:
            logger.warning("Pattern extraction failed: %s", exc)

    # ------------------------------------------------------------------
    # EventBus registration
    # ------------------------------------------------------------------

    def register_with_eventbus(self) -> bool:
        """Register this listener with the EventBus singleton.

        Returns True if registration succeeds, False otherwise.
        Graceful degradation: failure here does NOT break the engine.
        """
        try:
            from event_bus import EventBus

            bus = EventBus.get_instance(Path(self._db_path))
            bus.add_listener(self.handle_event)
            self._registered = True
            return True
        except Exception as exc:
            logger.info(
                "EventBus registration skipped (not available): %s", exc
            )
            self._registered = False
            return False

    # ------------------------------------------------------------------
    # Status / introspection
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Return listener status for diagnostics."""
        return {
            "events_processed": self.events_processed,
            "recall_events_processed": self.recall_events_processed,
            "deletion_events_processed": self.deletion_events_processed,
            "registered": self._registered,
            "outcome_count_since_extraction": self._outcome_count_since_extraction,
            "extraction_threshold": self.extraction_threshold,
        }
