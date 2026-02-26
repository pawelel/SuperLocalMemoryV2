# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""ABAC middleware for MCP tool integration.

Provides a simple interface for MCP tools to check access before
executing memory operations. Delegates to ABACEngine for policy
evaluation.
"""
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from .abac_engine import ABACEngine


class ABACMiddleware:
    """Thin middleware between MCP tools and ABAC policy engine.

    Usage from MCP tools:
        mw = ABACMiddleware(db_path)
        result = mw.check_access(agent_id="agent_1", action="read",
                                 resource={"access_level": "private"})
        if not result["allowed"]:
            return error_response(result["reason"])
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        policy_path: Optional[str] = None,
    ) -> None:
        if db_path is None:
            db_path = str(Path.home() / ".claude-memory" / "memory.db")
        self._db_path = str(db_path)

        if policy_path is None:
            policy_path = str(
                Path(self._db_path).parent / "abac_policies.json"
            )

        self._lock = threading.Lock()
        self.denied_count = 0
        self.allowed_count = 0

        try:
            self._engine = ABACEngine(config_path=policy_path)
        except Exception:
            self._engine = None

    def check_access(
        self,
        agent_id: str,
        action: str,
        resource: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Check if an agent has access to perform an action.

        Args:
            agent_id: Identifier for the requesting agent.
            action: The action being performed (read, write, delete).
            resource: Resource attributes (access_level, project, tags).

        Returns:
            Dict with ``allowed`` (bool), ``reason`` (str), and
            optionally ``policy_name``.
        """
        if self._engine is None:
            return {
                "allowed": True,
                "reason": "ABAC engine unavailable — default allow",
            }

        subject = {"agent_id": agent_id}
        result = self._engine.evaluate(
            subject=subject,
            resource=resource or {},
            action=action,
        )

        with self._lock:
            if result["allowed"]:
                self.allowed_count += 1
            else:
                self.denied_count += 1

        return result

    def build_agent_context(
        self,
        agent_id: str = "user",
        protocol: str = "mcp",
    ) -> Dict[str, Any]:
        """Build an agent context dict for passing to MemoryStoreV2.

        Args:
            agent_id: Agent identifier.
            protocol: Access protocol (mcp, cli, dashboard).

        Returns:
            Dict suitable for ``MemoryStoreV2.search(agent_context=...)``.
        """
        return {
            "agent_id": agent_id,
            "protocol": protocol,
        }

    def get_status(self) -> Dict[str, Any]:
        """Return middleware status."""
        return {
            "engine_available": self._engine is not None,
            "policies_loaded": (
                len(self._engine.policies) if self._engine else 0
            ),
            "allowed_count": self.allowed_count,
            "denied_count": self.denied_count,
        }
