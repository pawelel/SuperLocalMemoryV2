#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""EmbeddingEngine - Local Embedding Generation for SuperLocalMemory V2

BACKWARD-COMPATIBILITY SHIM
----------------------------
This file re-exports every public symbol from the ``embeddings`` package so
that existing code using ``from embedding_engine import EmbeddingEngine``
continues to work without modification.

The actual implementation now lives in:
    src/embeddings/constants.py  - Feature detection, constants, logger
    src/embeddings/cache.py      - LRUCache for embedding vectors
    src/embeddings/engine.py     - EmbeddingEngine core encode logic
    src/embeddings/database.py   - Batch embedding generation for SQLite
    src/embeddings/cli.py        - CLI interface
"""
# Re-export everything from the embeddings package
from embeddings import (
    # Constants
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
    # Classes
    LRUCache,
    EmbeddingEngine,
    # Functions
    add_embeddings_to_database,
    main,
)

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
    "EmbeddingEngine",
    # Functions
    "add_embeddings_to_database",
    "main",
]

if __name__ == '__main__':
    main()
