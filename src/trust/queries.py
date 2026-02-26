#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""
Trust query and enforcement mixin for TrustScorer.

Contains: get_trust_score, get_beta_params, check_trust, get_signals, get_trust_stats.
"""

import json
import logging
from typing import Dict, List

from .constants import INITIAL_ALPHA, INITIAL_BETA

logger = logging.getLogger("superlocalmemory.trust")


class TrustQueryMixin:
    """Mixin providing trust query, enforcement, and stats methods."""

    def get_trust_score(self, agent_id: str) -> float:
        """
        Get current trust score for an agent.

        Computes alpha/(alpha+beta) from cached or stored Beta params.
        Returns INITIAL_ALPHA/(INITIAL_ALPHA+INITIAL_BETA) = 0.667 for
        unknown agents.
        """
        alpha, beta = self._get_beta_params(agent_id)
        if (alpha + beta) > 0:
            return alpha / (alpha + beta)
        return INITIAL_ALPHA / (INITIAL_ALPHA + INITIAL_BETA)

    def get_beta_params(self, agent_id: str) -> Dict[str, float]:
        """
        Get the Beta distribution parameters for an agent.

        Returns:
            {"alpha": float, "beta": float, "trust_score": float}
        """
        alpha, beta = self._get_beta_params(agent_id)
        score = alpha / (alpha + beta) if (alpha + beta) > 0 else 0.0
        return {
            "alpha": round(alpha, 4),
            "beta": round(beta, 4),
            "trust_score": round(score, 4),
        }

    def check_trust(self, agent_id: str, operation: str = "write") -> bool:
        """
        Check if agent is trusted enough for the given operation.

        v2.6 enforcement: blocks write/delete for agents with trust < 0.3.

        Args:
            agent_id: The agent identifier
            operation: One of "read", "write", "delete"

        Returns:
            True if operation is allowed, False if blocked
        """
        if operation == "read":
            return True  # Reads are always allowed

        score = self.get_trust_score(agent_id)

        threshold = 0.3  # Block write/delete below this
        if score < threshold:
            logger.warning(
                "Trust enforcement: agent '%s' blocked from '%s' (trust=%.4f < %.2f)",
                agent_id, operation, score, threshold
            )
            return False

        return True

    def get_signals(self, agent_id: str, limit: int = 50) -> List[dict]:
        """Get recent trust signals for an agent."""
        try:
            from db_connection_manager import DbConnectionManager
            mgr = DbConnectionManager.get_instance(self.db_path)

            with mgr.read_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT signal_type, delta, old_score, new_score, context, created_at
                    FROM trust_signals
                    WHERE agent_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (agent_id, limit))

                signals = []
                for row in cursor.fetchall():
                    ctx = {}
                    try:
                        ctx = json.loads(row[4]) if row[4] else {}
                    except (json.JSONDecodeError, TypeError):
                        pass
                    signals.append({
                        "signal_type": row[0],
                        "delta": row[1],
                        "old_score": row[2],
                        "new_score": row[3],
                        "context": ctx,
                        "created_at": row[5],
                    })
                return signals

        except Exception as e:
            logger.error("Failed to get trust signals: %s", e)
            return []

    def get_trust_stats(self) -> dict:
        """Get trust system statistics."""
        try:
            from db_connection_manager import DbConnectionManager
            mgr = DbConnectionManager.get_instance(self.db_path)

            with mgr.read_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("SELECT COUNT(*) FROM trust_signals")
                total_signals = cursor.fetchone()[0]

                cursor.execute("""
                    SELECT signal_type, COUNT(*) FROM trust_signals
                    GROUP BY signal_type ORDER BY COUNT(*) DESC
                """)
                by_type = dict(cursor.fetchall())

                cursor.execute("""
                    SELECT agent_id, COUNT(*) FROM trust_signals
                    GROUP BY agent_id ORDER BY COUNT(*) DESC LIMIT 10
                """)
                by_agent = dict(cursor.fetchall())

                cursor.execute("""
                    SELECT AVG(trust_score) FROM agent_registry
                    WHERE trust_score IS NOT NULL
                """)
                avg = cursor.fetchone()[0]

            return {
                "total_signals": total_signals,
                "by_signal_type": by_type,
                "by_agent": by_agent,
                "avg_trust_score": round(avg, 4) if avg else INITIAL_ALPHA / (INITIAL_ALPHA + INITIAL_BETA),
                "scoring_model": "Beta-Binomial",
                "prior": f"Beta({INITIAL_ALPHA}, {INITIAL_BETA})",
                "enforcement": "enabled (v2.6 -- write/delete blocked below 0.3 trust)",
            }

        except Exception as e:
            logger.error("Failed to get trust stats: %s", e)
            return {"total_signals": 0, "error": str(e)}
