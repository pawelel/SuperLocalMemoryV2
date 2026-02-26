#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Entity extraction and cluster naming for the graph engine.

Provides TF-IDF based entity extraction from memory content
and cluster naming utilities.
"""
from typing import List, Tuple
from collections import Counter

import numpy as np

from graph.constants import logger, TfidfVectorizer


class EntityExtractor:
    """Extract key entities/concepts from memory content using TF-IDF."""

    def __init__(self, max_features: int = 20, min_df: int = 1):
        """
        Initialize entity extractor.

        Args:
            max_features: Top N keywords to extract per memory
            min_df: Minimum document frequency (ignore very rare terms)
        """
        self.max_features = max_features
        self.vectorizer = TfidfVectorizer(
            max_features=max_features,
            stop_words='english',
            ngram_range=(1, 2),  # Unigrams + bigrams
            min_df=min_df,
            lowercase=True,
            token_pattern=r'(?u)\b[a-zA-Z][a-zA-Z0-9_-]*\b'  # Alphanumeric tokens
        )

    def extract_entities(self, contents: List[str]) -> Tuple[List[List[str]], np.ndarray]:
        """
        Extract entities from multiple contents.

        Args:
            contents: List of memory content strings

        Returns:
            Tuple of (entities_per_content, tfidf_vectors)
        """
        if not contents:
            return [], np.array([])

        try:
            # Fit and transform all contents
            vectors = self.vectorizer.fit_transform(contents)
            feature_names = self.vectorizer.get_feature_names_out()

            # Extract top entities for each content
            all_entities = []
            for idx in range(len(contents)):
                scores = vectors[idx].toarray()[0]

                # Get indices of top features
                top_indices = np.argsort(scores)[::-1]

                # Extract entities with score > 0
                entities = [
                    feature_names[i]
                    for i in top_indices
                    if scores[i] > 0.05  # Minimum threshold
                ][:self.max_features]

                all_entities.append(entities)

            return all_entities, vectors.toarray()

        except Exception as e:
            logger.error(f"Entity extraction failed: {e}")
            return [[] for _ in contents], np.zeros((len(contents), 1))


class ClusterNamer:
    """Enhanced cluster naming with optional LLM support (future)."""

    @staticmethod
    def generate_name_tfidf(entities: List[str]) -> str:
        """Generate name from entity list (TF-IDF fallback)."""
        if not entities:
            return "Unnamed Cluster"

        entity_counts = Counter(entities)
        top_entities = [e for e, _ in entity_counts.most_common(2)]

        if len(top_entities) >= 2:
            return f"{top_entities[0].title()} & {top_entities[1].title()}"
        else:
            return f"{top_entities[0].title()} Contexts"
