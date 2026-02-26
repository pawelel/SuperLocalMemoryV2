#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Shared constants and feature-detection for the embeddings package.
"""
import logging
from pathlib import Path

# SECURITY: Embedding generation limits to prevent resource exhaustion
MAX_BATCH_SIZE = 128
MAX_TEXT_LENGTH = 10_000
CACHE_MAX_SIZE = 10_000

# Optional sentence-transformers dependency
SENTENCE_TRANSFORMERS_AVAILABLE = False
try:
    from sentence_transformers import SentenceTransformer  # noqa: F401
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False

# Fallback: TF-IDF vectorization
SKLEARN_AVAILABLE = False
try:
    from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: F401
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

# GPU detection
TORCH_AVAILABLE = False
CUDA_AVAILABLE = False
MPS_AVAILABLE = False  # Apple Silicon

try:
    import torch
    TORCH_AVAILABLE = True
    CUDA_AVAILABLE = torch.cuda.is_available()
    MPS_AVAILABLE = hasattr(torch.backends, 'mps') and torch.backends.mps.is_available()
except ImportError:
    pass

MEMORY_DIR = Path.home() / ".claude-memory"
EMBEDDING_CACHE_PATH = MEMORY_DIR / "embedding_cache.json"
MODEL_CACHE_PATH = MEMORY_DIR / "models"  # Local model storage

logger = logging.getLogger(__name__)
