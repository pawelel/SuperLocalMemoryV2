# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""embeddings package - Local Embedding Generation for SuperLocalMemory V2

Re-exports all public classes and constants so that
``from embeddings import EmbeddingEngine`` works.
"""
from embeddings.constants import (
    MAX_BATCH_SIZE,
    MAX_TEXT_LENGTH,
    CACHE_MAX_SIZE,
    SENTENCE_TRANSFORMERS_AVAILABLE,
    SKLEARN_AVAILABLE,
    TORCH_AVAILABLE,
    CUDA_AVAILABLE,
    MPS_AVAILABLE,
    MEMORY_DIR,
    EMBEDDING_CACHE_PATH,
    MODEL_CACHE_PATH,
)
from embeddings.cache import LRUCache
from embeddings.model_loader import ModelLoaderMixin
from embeddings.engine import EmbeddingEngine
from embeddings.database import add_embeddings_to_database
from embeddings.cli import main

__all__ = [
    # Constants
    "MAX_BATCH_SIZE",
    "MAX_TEXT_LENGTH",
    "CACHE_MAX_SIZE",
    "SENTENCE_TRANSFORMERS_AVAILABLE",
    "SKLEARN_AVAILABLE",
    "TORCH_AVAILABLE",
    "CUDA_AVAILABLE",
    "MPS_AVAILABLE",
    "MEMORY_DIR",
    "EMBEDDING_CACHE_PATH",
    "MODEL_CACHE_PATH",
    # Classes
    "LRUCache",
    "ModelLoaderMixin",
    "EmbeddingEngine",
    # Functions
    "add_embeddings_to_database",
    "main",
]
