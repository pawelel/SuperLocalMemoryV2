# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""SLM v2.8 Compliance Engine — ABAC + Audit Trail + Retention.

Enterprise-grade access control, tamper-evident audit trail,
and retention policy management for GDPR/EU AI Act/HIPAA.

Graceful degradation: if this module fails to import,
all agents have full access (v2.7 behavior).
"""
import threading
from pathlib import Path
from typing import Optional, Dict, Any

COMPLIANCE_AVAILABLE = False
_init_error = None

try:
    from .abac_engine import ABACEngine
    from .audit_db import AuditDB
    COMPLIANCE_AVAILABLE = True
except ImportError as e:
    _init_error = str(e)

_abac_engine: Optional["ABACEngine"] = None
_abac_lock = threading.Lock()


def get_abac_engine(config_path: Optional[Path] = None) -> Optional["ABACEngine"]:
    """Get or create the ABAC engine singleton."""
    global _abac_engine
    if not COMPLIANCE_AVAILABLE:
        return None
    with _abac_lock:
        if _abac_engine is None:
            try:
                _abac_engine = ABACEngine(config_path)
            except Exception:
                return None
        return _abac_engine


def get_status() -> Dict[str, Any]:
    return {
        "compliance_available": COMPLIANCE_AVAILABLE,
        "init_error": _init_error,
        "abac_active": _abac_engine is not None,
    }
