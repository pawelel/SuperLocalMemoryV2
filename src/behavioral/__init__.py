# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""SLM v2.8 Behavioral Learning Engine — Action Outcome Learning.

Tracks what happens AFTER memories are recalled (success/failure/partial).
Extracts behavioral patterns. Transfers across projects (privacy-safe).
All local, zero-LLM.

Graceful degradation: if this module fails to import,
adaptive ranking continues with v2.7 features only.
"""
import threading
from pathlib import Path
from typing import Optional, Dict, Any

BEHAVIORAL_AVAILABLE = False
_init_error = None

try:
    from .outcome_tracker import OutcomeTracker
    from .behavioral_patterns import BehavioralPatternExtractor
    BEHAVIORAL_AVAILABLE = True
except ImportError as e:
    _init_error = str(e)

_outcome_tracker: Optional["OutcomeTracker"] = None
_tracker_lock = threading.Lock()


def get_outcome_tracker(db_path: Optional[Path] = None) -> Optional["OutcomeTracker"]:
    """Get or create the outcome tracker singleton."""
    global _outcome_tracker
    if not BEHAVIORAL_AVAILABLE:
        return None
    with _tracker_lock:
        if _outcome_tracker is None:
            try:
                _outcome_tracker = OutcomeTracker(db_path)
            except Exception:
                return None
        return _outcome_tracker


def get_status() -> Dict[str, Any]:
    return {
        "behavioral_available": BEHAVIORAL_AVAILABLE,
        "init_error": _init_error,
        "tracker_active": _outcome_tracker is not None,
    }
