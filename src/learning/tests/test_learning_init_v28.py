# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Tests for unified learning status with v2.8 engines.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestUnifiedLearningStatus:
    def test_get_status_has_v28_engines(self):
        """Status should include lifecycle, behavioral, compliance info."""
        from learning import get_status
        status = get_status()
        assert "v28_engines" in status

    def test_v28_engines_structure(self):
        from learning import get_status
        status = get_status()
        engines = status["v28_engines"]
        assert "lifecycle" in engines
        assert "behavioral" in engines
        assert "compliance" in engines

    def test_lifecycle_status_included(self):
        from learning import get_status
        status = get_status()
        lifecycle = status["v28_engines"]["lifecycle"]
        assert "available" in lifecycle

    def test_behavioral_status_included(self):
        from learning import get_status
        status = get_status()
        behavioral = status["v28_engines"]["behavioral"]
        assert "available" in behavioral

    def test_compliance_status_included(self):
        from learning import get_status
        status = get_status()
        compliance = status["v28_engines"]["compliance"]
        assert "available" in compliance

    def test_graceful_when_engines_unavailable(self):
        """Status should not crash even if engine imports fail."""
        from learning import get_status
        status = get_status()
        # Should always return a dict with v28_engines
        assert isinstance(status["v28_engines"], dict)
