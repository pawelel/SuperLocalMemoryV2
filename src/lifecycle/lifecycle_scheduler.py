# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Background scheduler for periodic lifecycle evaluation and enforcement.

Runs on a configurable interval (default: 6 hours) to:
1. Evaluate all memories for lifecycle transitions
2. Execute recommended transitions
3. Enforce bounded growth limits

Uses daemon threading — does not prevent process exit.
"""
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

from .lifecycle_engine import LifecycleEngine
from .lifecycle_evaluator import LifecycleEvaluator
from .bounded_growth import BoundedGrowthEnforcer

# Default interval: 6 hours
DEFAULT_INTERVAL_SECONDS = 21600


class LifecycleScheduler:
    """Background scheduler for periodic lifecycle evaluation.

    Orchestrates the evaluator, engine, and bounded growth enforcer
    on a configurable timer interval.
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        config_path: Optional[str] = None,
        interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
    ):
        if db_path is None:
            db_path = str(Path.home() / ".claude-memory" / "memory.db")
        self._db_path = str(db_path)
        self._config_path = config_path
        self.interval_seconds = interval_seconds

        self._engine = LifecycleEngine(self._db_path, config_path=config_path)
        self._evaluator = LifecycleEvaluator(self._db_path, config_path=config_path)
        self._enforcer = BoundedGrowthEnforcer(self._db_path, config_path=config_path)

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
        """Execute a lifecycle evaluation cycle immediately.

        Returns:
            Dict with evaluation results, enforcement results, and timestamp
        """
        return self._execute_cycle()

    def _schedule_next(self) -> None:
        """Schedule the next evaluation cycle."""
        self._timer = threading.Timer(self.interval_seconds, self._run_cycle)
        self._timer.daemon = True
        self._timer.start()

    def _run_cycle(self) -> None:
        """Run one evaluation cycle, then schedule the next."""
        try:
            self._execute_cycle()
        except Exception:
            pass  # Scheduler must not crash
        finally:
            with self._lock:
                if self._running:
                    self._schedule_next()

    def _execute_cycle(self) -> Dict[str, Any]:
        """Core evaluation + enforcement logic.

        1. Evaluate all memories for potential transitions
        2. Execute recommended transitions via the engine
        3. Enforce bounded growth limits
        """
        # Step 1: Evaluate
        recommendations = self._evaluator.evaluate_memories()

        # Step 2: Execute transitions
        transitioned = 0
        transition_results: List[Dict] = []
        for rec in recommendations:
            result = self._engine.transition_memory(
                rec["memory_id"], rec["to_state"], reason=rec["reason"]
            )
            if result.get("success"):
                transitioned += 1
                transition_results.append(result)

        # Step 3: Enforce bounds
        enforcement = self._enforcer.enforce_bounds()

        return {
            "timestamp": datetime.now().isoformat(),
            "evaluation": {
                "recommendations": recommendations,
                "transitioned": transitioned,
                "transition_results": transition_results,
            },
            "enforcement": enforcement,
        }
