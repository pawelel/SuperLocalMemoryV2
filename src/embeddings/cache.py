#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""LRU cache for embedding vectors.
"""
import json
import logging
from pathlib import Path
from typing import Optional
from collections import OrderedDict

import numpy as np

from embeddings.constants import CACHE_MAX_SIZE

logger = logging.getLogger(__name__)


class LRUCache:
    """Simple LRU cache for embeddings."""

    def __init__(self, max_size: int = CACHE_MAX_SIZE):
        self.cache = OrderedDict()
        self.max_size = max_size

    def get(self, key: str) -> Optional[np.ndarray]:
        """Get item from cache, moving to end (most recent)."""
        if key not in self.cache:
            return None

        # Move to end (most recently used)
        self.cache.move_to_end(key)
        return np.array(self.cache[key])

    def set(self, key: str, value: np.ndarray):
        """Set item in cache, evicting oldest if full."""
        if key in self.cache:
            # Update existing
            self.cache.move_to_end(key)
            self.cache[key] = value.tolist()
        else:
            # Add new
            if len(self.cache) >= self.max_size:
                # Evict oldest
                self.cache.popitem(last=False)
            self.cache[key] = value.tolist()

    def save(self, path: Path):
        """Save cache to disk."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w') as f:
                json.dump(dict(self.cache), f)
            logger.debug(f"Saved {len(self.cache)} cached embeddings")
        except Exception as e:
            logger.error(f"Failed to save embedding cache: {e}")

    def load(self, path: Path):
        """Load cache from disk."""
        if not path.exists():
            return

        try:
            with open(path, 'r') as f:
                data = json.load(f)
                self.cache = OrderedDict(data)
            logger.info(f"Loaded {len(self.cache)} cached embeddings")
        except Exception as e:
            logger.error(f"Failed to load embedding cache: {e}")
            self.cache = OrderedDict()
