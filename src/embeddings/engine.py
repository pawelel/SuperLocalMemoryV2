#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""EmbeddingEngine - Core encoding logic for local embedding generation.
"""
import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np

from embeddings.constants import (
    MAX_BATCH_SIZE,
    MAX_TEXT_LENGTH,
    CACHE_MAX_SIZE,
    SENTENCE_TRANSFORMERS_AVAILABLE,
    SKLEARN_AVAILABLE,
    TORCH_AVAILABLE,
    CUDA_AVAILABLE,
    MPS_AVAILABLE,
    EMBEDDING_CACHE_PATH,
    MODEL_CACHE_PATH,
)
from embeddings.cache import LRUCache
from embeddings.model_loader import ModelLoaderMixin

logger = logging.getLogger(__name__)


class EmbeddingEngine(ModelLoaderMixin):
    """
    Local embedding generation using sentence-transformers.

    Features:
    - all-MiniLM-L6-v2 model (384 dimensions, 80MB, fast)
    - Batch processing for efficiency (up to 128 texts)
    - GPU acceleration (CUDA/MPS) with automatic detection
    - LRU cache for repeated queries (10K entries)
    - Graceful fallback to TF-IDF if dependencies unavailable

    Performance:
    - CPU: ~100 embeddings/sec
    - GPU (CUDA): ~1000 embeddings/sec
    - Apple Silicon (MPS): ~500 embeddings/sec
    - Cache hit: ~0.001ms
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        device: Optional[str] = None,
        cache_path: Optional[Path] = None,
        model_cache_path: Optional[Path] = None,
        use_cache: bool = True
    ):
        """
        Initialize embedding engine.

        Args:
            model_name: Sentence transformer model name
            device: Device to use ('cuda', 'mps', 'cpu', or None for auto)
            cache_path: Custom path for embedding cache
            model_cache_path: Custom path for model storage
            use_cache: Whether to use LRU cache
        """
        self.model_name = model_name
        self.cache_path = cache_path or EMBEDDING_CACHE_PATH
        self.model_cache_path = model_cache_path or MODEL_CACHE_PATH
        self.use_cache = use_cache

        # Auto-detect device
        if device is None:
            if CUDA_AVAILABLE:
                device = 'cuda'
                logger.info("Using CUDA GPU acceleration")
            elif MPS_AVAILABLE:
                device = 'mps'
                logger.info("Using Apple Silicon (MPS) GPU acceleration")
            else:
                device = 'cpu'
                logger.info("Using CPU (consider GPU for faster processing)")
        self.device = device

        # Initialize model
        self.model = None
        self.dimension = 384  # Default for all-MiniLM-L6-v2
        self.use_transformers = SENTENCE_TRANSFORMERS_AVAILABLE

        # Initialize cache
        self.cache = LRUCache(max_size=CACHE_MAX_SIZE) if use_cache else None
        if self.cache:
            self.cache.load(self.cache_path)

        # Fallback: TF-IDF vectorizer
        self.tfidf_vectorizer = None
        self.tfidf_fitted = False

        # Load model (from ModelLoaderMixin)
        self._load_model()

    def _get_cache_key(self, text: str) -> str:
        """Generate cache key for text."""
        return hashlib.sha256(text.encode('utf-8')).hexdigest()[:32]

    def encode(
        self,
        texts: Union[str, List[str]],
        batch_size: int = 32,
        show_progress: bool = False,
        normalize: bool = True
    ) -> np.ndarray:
        """
        Generate embeddings for text(s).

        Args:
            texts: Single text or list of texts
            batch_size: Batch size for processing (max: 128)
            show_progress: Show progress bar for large batches
            normalize: Normalize embeddings to unit length

        Returns:
            Array of shape (n_texts, dimension) or (dimension,) for single text
        """
        single_input = isinstance(texts, str)
        if single_input:
            texts = [texts]

        if len(texts) == 0:
            return np.array([])

        batch_size = min(batch_size, MAX_BATCH_SIZE)

        # Validate text length
        for i, text in enumerate(texts):
            if not isinstance(text, str):
                raise ValueError(f"Text at index {i} is not a string")
            if len(text) > MAX_TEXT_LENGTH:
                logger.warning(f"Text {i} truncated from {len(text)} to {MAX_TEXT_LENGTH} chars")
                texts[i] = text[:MAX_TEXT_LENGTH]

        # Check cache for hits
        embeddings = []
        uncached_texts = []
        uncached_indices = []

        if self.cache:
            for i, text in enumerate(texts):
                cache_key = self._get_cache_key(text)
                cached = self.cache.get(cache_key)
                if cached is not None:
                    embeddings.append((i, cached))
                else:
                    uncached_texts.append(text)
                    uncached_indices.append(i)
        else:
            uncached_texts = texts
            uncached_indices = list(range(len(texts)))

        # Generate embeddings for uncached texts
        if uncached_texts:
            if self.use_transformers and self.model:
                uncached_embeddings = self._encode_transformer(
                    uncached_texts, batch_size=batch_size, show_progress=show_progress
                )
            elif self.tfidf_vectorizer:
                uncached_embeddings = self._encode_tfidf(uncached_texts)
            else:
                raise RuntimeError("No embedding method available")

            for i, text, embedding in zip(uncached_indices, uncached_texts, uncached_embeddings):
                if self.cache:
                    cache_key = self._get_cache_key(text)
                    self.cache.set(cache_key, embedding)
                embeddings.append((i, embedding))

        # Sort by original index and extract embeddings
        embeddings.sort(key=lambda x: x[0])
        result = np.array([emb for _, emb in embeddings])

        if normalize and len(result) > 0:
            norms = np.linalg.norm(result, axis=1, keepdims=True)
            norms[norms == 0] = 1
            result = result / norms

        if single_input:
            return result[0]
        return result

    def encode_batch(
        self,
        texts: List[str],
        batch_size: int = 32,
        show_progress: bool = True
    ) -> np.ndarray:
        """Convenience method for batch encoding with progress."""
        return self.encode(texts, batch_size=batch_size, show_progress=show_progress)

    def similarity(self, embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """Compute cosine similarity between two embeddings. Returns [0, 1]."""
        emb1 = embedding1 / (np.linalg.norm(embedding1) + 1e-8)
        emb2 = embedding2 / (np.linalg.norm(embedding2) + 1e-8)
        similarity = np.dot(emb1, emb2)
        return float(max(0.0, min(1.0, similarity)))

    def save_cache(self):
        """Save embedding cache to disk."""
        if self.cache:
            self.cache.save(self.cache_path)

    def clear_cache(self):
        """Clear embedding cache."""
        if self.cache:
            self.cache.cache.clear()
            logger.info("Cleared embedding cache")

    def get_stats(self) -> Dict[str, Any]:
        """Get embedding engine statistics."""
        return {
            'sentence_transformers_available': SENTENCE_TRANSFORMERS_AVAILABLE,
            'use_transformers': self.use_transformers,
            'sklearn_available': SKLEARN_AVAILABLE,
            'torch_available': TORCH_AVAILABLE,
            'cuda_available': CUDA_AVAILABLE,
            'mps_available': MPS_AVAILABLE,
            'device': self.device,
            'model_name': self.model_name,
            'dimension': self.dimension,
            'cache_enabled': self.cache is not None,
            'cache_size': len(self.cache.cache) if self.cache else 0,
            'cache_max_size': CACHE_MAX_SIZE,
            'model_loaded': self.model is not None or self.tfidf_vectorizer is not None
        }

    def add_to_database(
        self,
        db_path,
        embedding_column: str = 'embedding',
        batch_size: int = 32
    ):
        """
        Generate embeddings for all memories in database.

        Delegates to :func:`embeddings.database.add_embeddings_to_database`.
        """
        from embeddings.database import add_embeddings_to_database
        add_embeddings_to_database(self, db_path, embedding_column, batch_size)
