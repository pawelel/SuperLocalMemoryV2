# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Attribute-Based Access Control policy evaluation.

Evaluates access requests against JSON-defined policies using
subject, resource, and action attributes. Deny-first semantics
ensure any matching deny policy blocks access regardless of
allow policies. When no policies exist, all access is permitted
(backward compatible with v2.7 default-allow behavior).

Policy format:
    {
        "name": str,          # Human-readable policy name
        "effect": str,        # "allow" or "deny"
        "subjects": dict,     # Attribute constraints on the requester
        "resources": dict,    # Attribute constraints on the resource
        "actions": list[str]  # Actions this policy applies to
    }

Matching rules:
    - "*" matches any value for that attribute
    - Specific values require exact match
    - All attributes in the policy must match for the policy to apply
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ABACEngine:
    """Evaluates ABAC policies for memory access control.

    Deny-first evaluation: if ANY deny policy matches the request,
    access is denied. If no deny matches, access is allowed
    (default-allow preserves v2.7 backward compatibility).
    """

    def __init__(self, config_path: Optional[str] = None) -> None:
        self._config_path = config_path
        self.policies: List[Dict[str, Any]] = []
        if config_path:
            self._load_policies(config_path)

    def _load_policies(self, path: str) -> None:
        """Load policies from a JSON file. Graceful on missing/invalid."""
        try:
            raw = Path(path).read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, list):
                self.policies = data
                logger.info("Loaded %d ABAC policies from %s", len(data), path)
            else:
                logger.warning("ABAC policy file is not a list: %s", path)
        except FileNotFoundError:
            logger.debug("No ABAC policy file at %s — default allow", path)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to parse ABAC policies: %s", exc)

    def evaluate(
        self,
        subject: Dict[str, Any],
        resource: Dict[str, Any],
        action: str,
    ) -> Dict[str, Any]:
        """Evaluate an access request against loaded policies.

        Args:
            subject:  Attributes of the requester (e.g. agent_id).
            resource: Attributes of the target resource.
            action:   The action being requested (read/write/delete).

        Returns:
            Dict with keys: allowed (bool), reason (str),
            and policy_name (str) when a specific policy decided.
        """
        if not self.policies:
            return {"allowed": True, "reason": "no_policies_loaded"}

        # Phase 1: check all deny policies first
        for policy in self.policies:
            if policy.get("effect") != "deny":
                continue
            if self._matches(policy, subject, resource, action):
                return {
                    "allowed": False,
                    "reason": "denied_by_policy",
                    "policy_name": policy.get("name", "unnamed"),
                }

        # Phase 2: check allow policies
        for policy in self.policies:
            if policy.get("effect") != "allow":
                continue
            if self._matches(policy, subject, resource, action):
                return {
                    "allowed": True,
                    "reason": "allowed_by_policy",
                    "policy_name": policy.get("name", "unnamed"),
                }

        # Phase 3: no matching policy — default allow (backward compat)
        return {"allowed": True, "reason": "no_matching_policy"}

    # ------------------------------------------------------------------
    # Internal matching helpers
    # ------------------------------------------------------------------

    def _matches(
        self,
        policy: Dict[str, Any],
        subject: Dict[str, Any],
        resource: Dict[str, Any],
        action: str,
    ) -> bool:
        """Return True if policy matches the request."""
        if not self._action_matches(policy.get("actions", []), action):
            return False
        if not self._attrs_match(policy.get("subjects", {}), subject):
            return False
        if not self._attrs_match(policy.get("resources", {}), resource):
            return False
        return True

    @staticmethod
    def _action_matches(policy_actions: List[str], action: str) -> bool:
        """Check if the requested action is in the policy's action list."""
        if "*" in policy_actions:
            return True
        return action in policy_actions

    @staticmethod
    def _attrs_match(
        policy_attrs: Dict[str, Any],
        request_attrs: Dict[str, Any],
    ) -> bool:
        """Check if all policy attribute constraints are satisfied.

        Every key in policy_attrs must either be "*" (match anything)
        or exactly equal the corresponding value in request_attrs.
        """
        for key, expected in policy_attrs.items():
            if expected == "*":
                continue
            if request_attrs.get(key) != expected:
                return False
        return True
