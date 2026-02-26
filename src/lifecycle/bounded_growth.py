# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Bounded growth enforcement — ensures memory counts stay within limits.

When the count of memories in a given lifecycle state exceeds configurable
bounds, the lowest-scoring memories are transitioned to the next state.

Scoring formula: importance_norm * recency_factor * frequency_factor * behavioral_value
  - importance_norm: importance / 10.0 (0.1 to 1.0)
  - recency_factor: 1.0 / (1.0 + days_stale / 30.0) (exponential decay)
  - frequency_factor: 0.5 + 0.5 * min(access_count / age_days, 1.0)
  - behavioral_value: 1.0 (placeholder for Phase 2 integration)

Lower score = evict first.
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

from .lifecycle_engine import LifecycleEngine


# Default bounds — generous defaults, configurable via lifecycle_config.json
DEFAULT_BOUNDS: Dict[str, int] = {
    "max_active": 10000,
    "max_warm": 5000,
}


class BoundedGrowthEnforcer:
    """Enforces memory count limits by transitioning lowest-scoring memories.

    When active memories exceed max_active, the lowest-scoring transition to warm.
    When warm memories exceed max_warm, the lowest-scoring transition to cold.
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        config_path: Optional[str] = None,
    ):
        if db_path is None:
            db_path = str(Path.home() / ".claude-memory" / "memory.db")
        self._db_path = str(db_path)
        self._config_path = config_path
        self._engine = LifecycleEngine(self._db_path)

    def _get_connection(self) -> sqlite3.Connection:
        """Get a SQLite connection to memory.db."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def enforce_bounds(self, profile: Optional[str] = None) -> Dict[str, Any]:
        """Check memory counts and transition excess memories.

        Args:
            profile: Filter by profile (None = all)

        Returns:
            Dict with enforced status, counts, limits, and transitions list
        """
        bounds = self._load_bounds()
        max_active = bounds.get("max_active", DEFAULT_BOUNDS["max_active"])
        max_warm = bounds.get("max_warm", DEFAULT_BOUNDS["max_warm"])

        transitions: List[Dict[str, Any]] = []

        # Enforce active limit
        active_transitions = self._enforce_state_limit(
            state="active",
            target_state="warm",
            max_count=max_active,
            profile=profile,
        )
        transitions.extend(active_transitions)

        # Enforce warm limit
        warm_transitions = self._enforce_state_limit(
            state="warm",
            target_state="cold",
            max_count=max_warm,
            profile=profile,
        )
        transitions.extend(warm_transitions)

        # Build result
        dist = self._engine.get_state_distribution()
        return {
            "enforced": len(transitions) > 0,
            "active_count": dist.get("active", 0),
            "active_limit": max_active,
            "warm_count": dist.get("warm", 0),
            "warm_limit": max_warm,
            "transitions": transitions,
        }

    def _enforce_state_limit(
        self,
        state: str,
        target_state: str,
        max_count: int,
        profile: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Enforce a single state's count limit.

        Scores all memories in the given state, evicts the lowest-scoring
        excess memories to target_state.
        """
        scored = self.score_all_memories(state=state, profile=profile)
        current_count = len(scored)

        if current_count <= max_count:
            return []

        excess = current_count - max_count
        # Sort ascending by score — lowest scores evicted first
        scored.sort(key=lambda s: s["score"])
        to_evict = scored[:excess]

        # Batch transition for performance — single connection, single commit
        mem_ids = [e["memory_id"] for e in to_evict]
        reasons = [f"bounded_growth_score_{e['score']:.4f}" for e in to_evict]
        score_map = {e["memory_id"]: e["score"] for e in to_evict}

        result = self._engine.batch_transition(mem_ids, target_state, reasons)

        transitions = []
        for entry in result.get("succeeded", []):
            transitions.append({
                "memory_id": entry["memory_id"],
                "from_state": state,
                "to_state": target_state,
                "score": score_map.get(entry["memory_id"], 0.0),
            })
        return transitions

    def score_all_memories(
        self,
        state: Optional[str] = None,
        profile: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Score all memories in a given state.

        Args:
            state: Lifecycle state to filter (None = all non-terminal states)
            profile: Filter by profile

        Returns:
            List of dicts with memory_id and score, sorted descending by score
        """
        conn = self._get_connection()
        try:
            if state:
                query = (
                    "SELECT id, importance, last_accessed, created_at, access_count "
                    "FROM memories WHERE lifecycle_state = ?"
                )
                params: list = [state]
            else:
                query = (
                    "SELECT id, importance, last_accessed, created_at, access_count "
                    "FROM memories WHERE lifecycle_state IN ('active', 'warm', 'cold')"
                )
                params = []

            if profile:
                query += " AND profile = ?"
                params.append(profile)

            rows = conn.execute(query, params).fetchall()
            now = datetime.now()

            scores = []
            for row in rows:
                score = self._score_row(row, now)
                scores.append({"memory_id": row["id"], "score": score})

            scores.sort(key=lambda s: s["score"], reverse=True)
            return scores
        finally:
            conn.close()

    def _score_row(self, row: sqlite3.Row, now: datetime) -> float:
        """Compute composite lifecycle score for a memory.

        Score = importance_norm * recency_factor * frequency_factor * behavioral_value

        Higher score = more valuable = keep longer.
        """
        # Importance: normalize to 0.1-1.0
        importance = max(row["importance"] or 5, 1)
        importance_norm = importance / 10.0

        # Recency: exponential decay, halves every ~30 days
        last_access_str = row["last_accessed"] or row["created_at"]
        days_stale = 0
        if last_access_str:
            try:
                last_access = datetime.fromisoformat(str(last_access_str))
                days_stale = max((now - last_access).days, 0)
            except (ValueError, TypeError):
                days_stale = 0
        recency_factor = 1.0 / (1.0 + days_stale / 30.0)

        # Access frequency: normalized by age
        access_count = row["access_count"] or 0
        created_str = row["created_at"]
        age_days = 1
        if created_str:
            try:
                created = datetime.fromisoformat(str(created_str))
                age_days = max((now - created).days, 1)
            except (ValueError, TypeError):
                age_days = 1
        frequency_factor = 0.5 + 0.5 * min(access_count / age_days, 1.0)

        # Behavioral value: placeholder for Phase 2 integration
        behavioral_value = 1.0

        return importance_norm * recency_factor * frequency_factor * behavioral_value

    def _load_bounds(self) -> Dict[str, int]:
        """Load bounds config from lifecycle_config.json. Returns defaults if missing."""
        try:
            if self._config_path:
                config_path = Path(self._config_path)
            else:
                config_path = Path(self._db_path).parent / "lifecycle_config.json"
            if config_path.exists():
                with open(config_path) as f:
                    user_config = json.load(f)
                bounds = user_config.get("bounds", {})
                return {**DEFAULT_BOUNDS, **bounds}
        except Exception:
            pass
        return dict(DEFAULT_BOUNDS)
