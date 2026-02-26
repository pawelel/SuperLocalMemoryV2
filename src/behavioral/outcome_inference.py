# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Implicit outcome detection from recall behavior patterns.

Pure logic module — no database, no I/O. Takes recall events and
returns inference results. The caller (EventBus integration) passes
these to OutcomeTracker for persistence.

Inference rules (checked in priority order, first match wins per recall):
1. Deletion of recalled memory within 60 min  -> failure,  confidence 0.0
2. Usage signal "mcp_used_high" within 5 min   -> success,  confidence 0.8
3. Usage signal cross-tool within 5 min        -> success,  confidence 0.7
4. Rapid-fire: 3+ recalls in 2 min window      -> failure,  confidence 0.1
5. Different-query recall within 2 min          -> failure,  confidence 0.2
6. No re-query for 10+ min elapsed             -> success,  confidence 0.6
7. Otherwise                                   -> not yet inferrable (keep)
"""
from datetime import datetime, timedelta
from typing import Dict, List, Optional


# ── Thresholds (seconds) ─────────────────────────────────────────────
_DELETION_WINDOW = 60 * 60      # 60 min
_USAGE_WINDOW = 5 * 60          # 5 min
_RAPID_FIRE_WINDOW = 2 * 60     # 2 min
_RAPID_FIRE_COUNT = 3
_REQUERY_WINDOW = 2 * 60        # 2 min
_QUIET_WINDOW = 10 * 60         # 10 min


class OutcomeInference:
    """Infer implicit success/failure from post-recall user behavior."""

    def __init__(self) -> None:
        self._recalls: List[Dict] = []      # {query, memory_ids, ts}
        self._usages: List[Dict] = []       # {query, signal, ts}
        self._deletions: List[Dict] = []    # {memory_id, ts}

    # ── Recording API ────────────────────────────────────────────────

    def record_recall(
        self,
        query: str,
        memory_ids: List[int],
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Buffer a recall event."""
        self._recalls.append({
            "query": query,
            "memory_ids": list(memory_ids),
            "ts": timestamp or datetime.now(),
        })

    def record_usage(
        self,
        query: str,
        signal: str,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Buffer a post-recall usage signal."""
        self._usages.append({
            "query": query,
            "signal": signal,
            "ts": timestamp or datetime.now(),
        })

    def record_deletion(
        self,
        memory_id: int,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """Buffer a memory deletion event."""
        self._deletions.append({
            "memory_id": memory_id,
            "ts": timestamp or datetime.now(),
        })

    # ── Inference engine ─────────────────────────────────────────────

    def infer_outcomes(self, now: Optional[datetime] = None) -> List[Dict]:
        """Process buffered events, apply rules, return inferences.

        Processed recall events are removed from the buffer.
        Events that are not yet inferrable remain for later.

        Returns:
            List of dicts with keys: outcome, confidence, memory_ids, reason
        """
        now = now or datetime.now()
        results: List[Dict] = []
        remaining: List[Dict] = []

        for recall in self._recalls:
            result = self._evaluate(recall, now)
            if result is not None:
                results.append(result)
            else:
                remaining.append(recall)

        # Clear processed; keep un-inferrable recalls
        self._recalls = remaining
        # Consumed usages and deletions are cleared entirely
        self._usages.clear()
        self._deletions.clear()

        return results

    # ── Private rule evaluation ──────────────────────────────────────

    def _evaluate(self, recall: Dict, now: datetime) -> Optional[Dict]:
        """Apply rules in priority order. First match wins."""
        query = recall["query"]
        mem_ids = recall["memory_ids"]
        ts = recall["ts"]
        elapsed = (now - ts).total_seconds()

        # Rule 1: Deletion of recalled memory within 60 min
        for d in self._deletions:
            if d["memory_id"] in mem_ids:
                delta = (d["ts"] - ts).total_seconds()
                if 0 <= delta <= _DELETION_WINDOW:
                    return self._result(
                        "failure", 0.0, mem_ids,
                        "memory_deleted_after_recall",
                    )

        # Rule 2: Usage signal "mcp_used_high" within 5 min
        for u in self._usages:
            if u["query"] == query and u["signal"] == "mcp_used_high":
                delta = (u["ts"] - ts).total_seconds()
                if 0 <= delta <= _USAGE_WINDOW:
                    return self._result(
                        "success", 0.8, mem_ids,
                        "mcp_used_high_after_recall",
                    )

        # Rule 3: Cross-tool usage within 5 min
        for u in self._usages:
            if u["query"] == query and u["signal"] == "implicit_positive_cross_tool":
                delta = (u["ts"] - ts).total_seconds()
                if 0 <= delta <= _USAGE_WINDOW:
                    return self._result(
                        "success", 0.7, mem_ids,
                        "cross_tool_access_after_recall",
                    )

        # Rule 4: Rapid-fire — 3+ recalls within 2 min window
        window_start = ts - timedelta(seconds=_RAPID_FIRE_WINDOW)
        nearby = [
            r for r in self._recalls
            if r is not recall and window_start <= r["ts"] <= ts + timedelta(seconds=_RAPID_FIRE_WINDOW)
        ]
        # Count total including this recall
        if len(nearby) + 1 >= _RAPID_FIRE_COUNT:
            return self._result(
                "failure", 0.1, mem_ids,
                "rapid_fire_queries",
            )

        # Rule 5: Different-query recall within 2 min
        for r in self._recalls:
            if r is recall:
                continue
            if r["query"] != query:
                delta = abs((r["ts"] - ts).total_seconds())
                if delta <= _REQUERY_WINDOW:
                    return self._result(
                        "failure", 0.2, mem_ids,
                        "immediate_requery_different_terms",
                    )

        # Rule 6: 10+ min elapsed with no subsequent activity
        if elapsed >= _QUIET_WINDOW:
            return self._result(
                "success", 0.6, mem_ids,
                "no_requery_after_recall",
            )

        # Rule 7: Not yet inferrable
        return None

    @staticmethod
    def _result(
        outcome: str,
        confidence: float,
        memory_ids: List[int],
        reason: str,
    ) -> Dict:
        return {
            "outcome": outcome,
            "confidence": confidence,
            "memory_ids": memory_ids,
            "reason": reason,
        }
