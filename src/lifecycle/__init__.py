# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""SLM v2.8 Lifecycle Engine — Memory State Machine + Bounded Growth.

Manages memory states: ACTIVE → WARM → COLD → ARCHIVED → TOMBSTONED.
Layers on top of existing tier-based compression.
All features opt-in: absent config = v2.7 behavior.

Graceful degradation: if this module fails to import,
core memory operations continue unchanged.
"""
import threading
from pathlib import Path
from typing import Optional, Dict, Any

# Feature flags
LIFECYCLE_AVAILABLE = False
_init_error = None

try:
    from .lifecycle_engine import LifecycleEngine
    from .lifecycle_evaluator import LifecycleEvaluator
    from .retention_policy import RetentionPolicyManager
    from .bounded_growth import BoundedGrowthEnforcer
    LIFECYCLE_AVAILABLE = True
except ImportError as e:
    _init_error = str(e)

# Lazy singletons
_lifecycle_engine: Optional["LifecycleEngine"] = None
_lifecycle_lock = threading.Lock()


def get_lifecycle_engine(db_path: Optional[Path] = None) -> Optional["LifecycleEngine"]:
    """Get or create the lifecycle engine singleton. Returns None if unavailable."""
    global _lifecycle_engine
    if not LIFECYCLE_AVAILABLE:
        return None
    with _lifecycle_lock:
        if _lifecycle_engine is None:
            try:
                _lifecycle_engine = LifecycleEngine(db_path)
            except Exception:
                return None
        return _lifecycle_engine


def get_status() -> Dict[str, Any]:
    """Return lifecycle engine status."""
    return {
        "lifecycle_available": LIFECYCLE_AVAILABLE,
        "init_error": _init_error,
        "engine_active": _lifecycle_engine is not None,
    }
