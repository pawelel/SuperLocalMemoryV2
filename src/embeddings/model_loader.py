#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Model loading and backend encoder methods for EmbeddingEngine.
"""
import time
import logging
from typing import List

import numpy as np

from embeddings.constants import (
    SENTENCE_TRANSFORMERS_AVAILABLE,
    SKLEARN_AVAILABLE,
)

logger = logging.getLogger(__name__)


class ModelLoaderMixin:
    """
    Mixin that handles model initialization and raw encoding backends.

    Expects the host class to have:
        - self.use_transformers: bool
        - self.model_cache_path: Path
        - self.model_name: str
        - self.device: str
        - self.model: Optional[SentenceTransformer]
        - self.dimension: int
        - self.tfidf_vectorizer
        - self.tfidf_fitted: bool
    """

    def _load_model(self):
        """Load sentence transformer model or fallback to TF-IDF."""
        if not self.use_transformers:
            logger.warning(
                "sentence-transformers unavailable. Install with: "
                "pip install sentence-transformers"
            )
            self._init_fallback()
            return

        try:
            from sentence_transformers import SentenceTransformer

            # Create model cache directory
            self.model_cache_path.mkdir(parents=True, exist_ok=True)

            logger.info(f"Loading model: {self.model_name}")
            start_time = time.time()

            # Load model with local cache
            self.model = SentenceTransformer(
                self.model_name,
                device=self.device,
                cache_folder=str(self.model_cache_path)
            )

            # Get actual dimension
            self.dimension = self.model.get_sentence_embedding_dimension()

            elapsed = time.time() - start_time
            logger.info(
                f"Loaded {self.model_name} ({self.dimension}D) in {elapsed:.2f}s"
            )

        except Exception as e:
            logger.error(f"Failed to load sentence transformer: {e}")
            logger.info("Falling back to TF-IDF")
            self.use_transformers = False
            self._init_fallback()

    def _init_fallback(self):
        """Initialize TF-IDF fallback."""
        if not SKLEARN_AVAILABLE:
            logger.error(
                "sklearn unavailable - no fallback available. "
                "Install: pip install scikit-learn"
            )
            return

        from sklearn.feature_extraction.text import TfidfVectorizer

        logger.info("Using TF-IDF fallback (dimension will be dynamic)")
        self.tfidf_vectorizer = TfidfVectorizer(
            max_features=384,  # Match sentence transformer dimension
            stop_words='english',
            ngram_range=(1, 2),
            min_df=1
        )
        self.dimension = 384

    def _encode_transformer(
        self,
        texts: List[str],
        batch_size: int,
        show_progress: bool
    ) -> np.ndarray:
        """Generate embeddings using sentence transformer."""
        try:
            start_time = time.time()

            embeddings = self.model.encode(
                texts,
                batch_size=batch_size,
                show_progress_bar=show_progress,
                convert_to_numpy=True,
                normalize_embeddings=False  # We'll normalize separately
            )

            elapsed = time.time() - start_time
            rate = len(texts) / elapsed if elapsed > 0 else 0
            logger.debug(f"Encoded {len(texts)} texts in {elapsed:.2f}s ({rate:.0f} texts/sec)")

            return embeddings

        except Exception as e:
            logger.error(f"Transformer encoding failed: {e}")
            raise

    def _encode_tfidf(self, texts: List[str]) -> np.ndarray:
        """Generate embeddings using TF-IDF fallback."""
        try:
            if not self.tfidf_fitted:
                # Fit on first use
                logger.info("Fitting TF-IDF vectorizer...")
                self.tfidf_vectorizer.fit(texts)
                self.tfidf_fitted = True

            embeddings = self.tfidf_vectorizer.transform(texts).toarray()

            # Pad or truncate to target dimension
            if embeddings.shape[1] < self.dimension:
                padding = np.zeros((embeddings.shape[0], self.dimension - embeddings.shape[1]))
                embeddings = np.hstack([embeddings, padding])
            elif embeddings.shape[1] > self.dimension:
                embeddings = embeddings[:, :self.dimension]

            return embeddings

        except Exception as e:
            logger.error(f"TF-IDF encoding failed: {e}")
            raise
