#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""SuperLocalMemory V2 - Trust Scorer (core class)
. MIT License.

Bayesian Beta-Binomial trust scoring for AI agents.
Core class with Beta parameter management and signal recording.
Query/stats via TrustQueryMixin; signal helpers via TrustSignalsMixin.
"""
import json
import logging
import threading
from pathlib import Path
from typing import Optional, Dict

from .constants import (
    SIGNAL_WEIGHTS,
    INITIAL_ALPHA,
    INITIAL_BETA,
    DECAY_FACTOR,
    DECAY_INTERVAL,
    ALPHA_FLOOR,
    BETA_FLOOR,
)
from .schema import init_trust_schema
from .signals import TrustSignalsMixin
from .queries import TrustQueryMixin

logger = logging.getLogger("superlocalmemory.trust")


class TrustScorer(TrustSignalsMixin, TrustQueryMixin):
    """
    Bayesian Beta-Binomial trust scorer for AI agents.

    Each agent is modeled as Beta(alpha, beta). Positive signals
    increment alpha, negative signals increment beta. The trust
    score is the posterior mean: alpha / (alpha + beta).

    Thread-safe singleton per database path.
    """

    _instances: Dict[str, "TrustScorer"] = {}
    _instances_lock = threading.Lock()

    @classmethod
    def get_instance(cls, db_path: Optional[Path] = None) -> "TrustScorer":
        """Get or create the singleton TrustScorer."""
        if db_path is None:
            db_path = Path.home() / ".claude-memory" / "memory.db"
        key = str(db_path)
        with cls._instances_lock:
            if key not in cls._instances:
                cls._instances[key] = cls(db_path)
            return cls._instances[key]

    @classmethod
    def reset_instance(cls, db_path: Optional[Path] = None):
        """Remove singleton. Used for testing."""
        with cls._instances_lock:
            if db_path is None:
                cls._instances.clear()
            else:
                key = str(db_path)
                if key in cls._instances:
                    del cls._instances[key]

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

        # In-memory signal log for burst detection (agent_id -> list of timestamps)
        self._write_timestamps: Dict[str, list] = {}
        self._timestamps_lock = threading.Lock()

        # Signal count per agent (for decay interval tracking)
        self._signal_counts: Dict[str, int] = {}

        # In-memory cache of Beta parameters per agent
        # Key: agent_id, Value: (alpha, beta)
        self._beta_params: Dict[str, tuple] = {}
        self._beta_lock = threading.Lock()

        self._init_schema()
        logger.info("TrustScorer initialized (Beta-Binomial -- alpha=%.1f, beta=%.1f prior)",
                     INITIAL_ALPHA, INITIAL_BETA)

    def _init_schema(self):
        """Create trust_signals table and add alpha/beta columns to agent_registry."""
        init_trust_schema(self.db_path)

    # =========================================================================
    # Beta Parameter Management
    # =========================================================================

    def _get_beta_params(self, agent_id: str) -> tuple:
        """
        Get (alpha, beta) for an agent. Checks in-memory cache first,
        then database, then falls back to prior defaults.

        Returns:
            (alpha, beta) tuple
        """
        with self._beta_lock:
            if agent_id in self._beta_params:
                return self._beta_params[agent_id]

        # Not in cache -- read from database
        alpha, beta = None, None
        try:
            from db_connection_manager import DbConnectionManager
            mgr = DbConnectionManager.get_instance(self.db_path)

            with mgr.read_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT trust_alpha, trust_beta FROM agent_registry WHERE agent_id = ?",
                    (agent_id,)
                )
                row = cursor.fetchone()
                if row:
                    alpha = row[0]
                    beta = row[1]
        except Exception:
            pass

        # Fall back to defaults if NULL or missing
        if alpha is None or beta is None:
            alpha = INITIAL_ALPHA
            beta = INITIAL_BETA

        with self._beta_lock:
            self._beta_params[agent_id] = (alpha, beta)

        return (alpha, beta)

    def _set_beta_params(self, agent_id: str, alpha: float, beta: float):
        """
        Update (alpha, beta) in cache and persist to agent_registry.
        Also computes and stores the derived trust_score = alpha/(alpha+beta).
        """
        trust_score = alpha / (alpha + beta) if (alpha + beta) > 0 else 0.0

        with self._beta_lock:
            self._beta_params[agent_id] = (alpha, beta)

        try:
            from db_connection_manager import DbConnectionManager
            mgr = DbConnectionManager.get_instance(self.db_path)

            def _update(conn):
                conn.execute(
                    """UPDATE agent_registry
                       SET trust_score = ?, trust_alpha = ?, trust_beta = ?
                       WHERE agent_id = ?""",
                    (round(trust_score, 4), round(alpha, 4), round(beta, 4), agent_id)
                )
                conn.commit()

            mgr.execute_write(_update)
        except Exception as e:
            logger.error("Failed to persist Beta params for %s: %s", agent_id, e)

    def _apply_decay(self, agent_id: str, alpha: float, beta: float) -> tuple:
        """
        Apply periodic decay to alpha and beta to forget very old signals.

        Called every DECAY_INTERVAL signals per agent.
        Multiplies both by DECAY_FACTOR with floor constraints.

        Returns:
            (decayed_alpha, decayed_beta)
        """
        new_alpha = max(ALPHA_FLOOR, alpha * DECAY_FACTOR)
        new_beta = max(BETA_FLOOR, beta * DECAY_FACTOR)
        return (new_alpha, new_beta)

    # =========================================================================
    # Signal Recording (Beta-Binomial Update)
    # =========================================================================

    def record_signal(
        self,
        agent_id: str,
        signal_type: str,
        context: Optional[dict] = None,
    ) -> bool:
        """
        Record a trust signal for an agent using Beta-Binomial update.

        Args:
            agent_id: Agent that generated the signal
            signal_type: One of SIGNAL_WEIGHTS keys
            context: Additional context (memory_id, etc.)

        Returns:
            True if signal was recorded successfully
        """
        if signal_type not in SIGNAL_WEIGHTS:
            logger.warning("Unknown trust signal: %s", signal_type)
            return False

        direction, weight = SIGNAL_WEIGHTS[signal_type]

        # Get current Beta parameters
        alpha, beta = self._get_beta_params(agent_id)
        old_score = alpha / (alpha + beta) if (alpha + beta) > 0 else 0.0

        # Apply Beta-Binomial update
        if direction == "positive":
            alpha += weight
        elif direction == "negative":
            beta += weight
        else:  # neutral -- tiny alpha nudge
            alpha += weight

        # Apply periodic decay
        count = self._signal_counts.get(agent_id, 0) + 1
        self._signal_counts[agent_id] = count

        if count % DECAY_INTERVAL == 0:
            alpha, beta = self._apply_decay(agent_id, alpha, beta)

        # Compute new trust score (posterior mean)
        new_score = alpha / (alpha + beta) if (alpha + beta) > 0 else 0.0

        # Compute delta for audit trail
        delta = new_score - old_score

        # Persist signal to audit trail
        self._persist_signal(agent_id, signal_type, delta, old_score, new_score, context)

        # Persist updated Beta parameters and derived trust_score
        self._set_beta_params(agent_id, alpha, beta)

        logger.debug(
            "Trust signal: agent=%s, type=%s (%s, w=%.2f), "
            "alpha=%.2f, beta=%.2f, score=%.4f->%.4f",
            agent_id, signal_type, direction, weight,
            alpha, beta, old_score, new_score
        )

        return True

    def _persist_signal(self, agent_id, signal_type, delta, old_score, new_score, context):
        """Save signal to trust_signals table."""
        try:
            from db_connection_manager import DbConnectionManager
            mgr = DbConnectionManager.get_instance(self.db_path)

            def _insert(conn):
                conn.execute('''
                    INSERT INTO trust_signals (agent_id, signal_type, delta, old_score, new_score, context)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (agent_id, signal_type, delta, old_score, new_score, json.dumps(context or {})))
                conn.commit()

            mgr.execute_write(_insert)
        except Exception as e:
            logger.error("Failed to persist trust signal: %s", e)

    def _get_agent_trust(self, agent_id: str) -> Optional[float]:
        """Get current trust score from agent_registry."""
        try:
            from db_connection_manager import DbConnectionManager
            mgr = DbConnectionManager.get_instance(self.db_path)

            with mgr.read_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT trust_score FROM agent_registry WHERE agent_id = ?",
                    (agent_id,)
                )
                row = cursor.fetchone()
                return row[0] if row else None
        except Exception:
            return None

    def _update_agent_trust(self, agent_id: str, new_score: float):
        """
        Update trust score in agent_registry (legacy compatibility method).

        In Beta-Binomial mode, _set_beta_params already updates trust_score
        alongside alpha and beta. Kept for backward compatibility.
        """
        try:
            from db_connection_manager import DbConnectionManager
            mgr = DbConnectionManager.get_instance(self.db_path)

            def _update(conn):
                conn.execute(
                    "UPDATE agent_registry SET trust_score = ? WHERE agent_id = ?",
                    (round(new_score, 4), agent_id)
                )
                conn.commit()

            mgr.execute_write(_update)
        except Exception as e:
            logger.error("Failed to update agent trust: %s", e)
