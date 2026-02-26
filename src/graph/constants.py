#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Shared constants, imports, and configuration for the graph engine modules.
"""
# SECURITY: Graph build limits to prevent resource exhaustion
MAX_MEMORIES_FOR_GRAPH = 10000

import sqlite3
import json
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Set
from collections import Counter

# Core dependencies
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    import numpy as np
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    raise ImportError("scikit-learn is required. Install: pip install scikit-learn")

# Graph dependencies - lazy import to avoid conflicts with compression module
IGRAPH_AVAILABLE = False
try:
    # Import only when needed to avoid module conflicts
    import importlib
    ig_module = importlib.import_module('igraph')
    leiden_module = importlib.import_module('leidenalg')
    IGRAPH_AVAILABLE = True
except ImportError:
    pass  # Will raise error when building clusters if not available

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('graph_engine')

MEMORY_DIR = Path.home() / ".claude-memory"
DB_PATH = MEMORY_DIR / "memory.db"
