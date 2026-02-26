#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""CLI interface for testing the embedding engine.
"""
import sys
import json
import time
import logging

from embeddings.constants import MEMORY_DIR
from embeddings.engine import EmbeddingEngine
from embeddings.database import add_embeddings_to_database


def main():
    """Run the embedding engine CLI."""
    # Configure logging
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    if len(sys.argv) < 2:
        print("EmbeddingEngine CLI - Local Embedding Generation")
        print("\nCommands:")
        print("  python embedding_engine.py stats              # Show engine statistics")
        print("  python embedding_engine.py generate           # Generate embeddings for database")
        print("  python embedding_engine.py test               # Run performance test")
        print("  python embedding_engine.py clear-cache        # Clear embedding cache")
        sys.exit(0)

    command = sys.argv[1]

    if command == "stats":
        engine = EmbeddingEngine()
        stats = engine.get_stats()
        print(json.dumps(stats, indent=2))

    elif command == "generate":
        db_path = MEMORY_DIR / "memory.db"
        if not db_path.exists():
            print(f"Database not found at {db_path}")
            sys.exit(1)

        print("Generating embeddings for all memories...")
        engine = EmbeddingEngine()
        add_embeddings_to_database(engine, db_path)
        print("Generation complete!")
        print(json.dumps(engine.get_stats(), indent=2))

    elif command == "clear-cache":
        engine = EmbeddingEngine()
        engine.clear_cache()
        engine.save_cache()
        print("Cache cleared!")

    elif command == "test":
        print("Running embedding performance test...")

        engine = EmbeddingEngine()

        # Test single encoding
        print("\nTest 1: Single text encoding")
        text = "This is a test sentence for embedding generation."
        start = time.time()
        embedding = engine.encode(text)
        elapsed = time.time() - start
        print(f"  Time: {elapsed*1000:.2f}ms")
        print(f"  Dimension: {len(embedding)}")
        print(f"  Sample values: {embedding[:5]}")

        # Test batch encoding
        print("\nTest 2: Batch encoding (100 texts)")
        texts = [f"This is test sentence number {i} with some content." for i in range(100)]
        start = time.time()
        embeddings = engine.encode(texts, batch_size=32)
        elapsed = time.time() - start
        print(f"  Time: {elapsed*1000:.2f}ms ({100/elapsed:.0f} texts/sec)")
        print(f"  Shape: {embeddings.shape}")

        # Test cache
        print("\nTest 3: Cache performance")
        start = time.time()
        embedding_cached = engine.encode(text)
        elapsed = time.time() - start
        print(f"  Cache hit time: {elapsed*1000:.4f}ms")
        print(f"  Speedup: {(elapsed*1000):.0f}x faster")

        # Test similarity
        print("\nTest 4: Similarity computation")
        text1 = "The weather is nice today."
        text2 = "It's a beautiful day outside."
        text3 = "Python is a programming language."

        emb1 = engine.encode(text1)
        emb2 = engine.encode(text2)
        emb3 = engine.encode(text3)

        sim_12 = engine.similarity(emb1, emb2)
        sim_13 = engine.similarity(emb1, emb3)

        print(f"  Similarity (weather vs beautiful day): {sim_12:.3f}")
        print(f"  Similarity (weather vs programming): {sim_13:.3f}")

        # Print stats
        print("\nEngine statistics:")
        print(json.dumps(engine.get_stats(), indent=2))

        # Save cache
        engine.save_cache()
        print("\nCache saved!")

    else:
        print(f"Unknown command: {command}")
        print("Run without arguments to see available commands.")
