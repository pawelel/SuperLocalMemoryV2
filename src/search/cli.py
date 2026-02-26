#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""CLI interface for testing the hybrid search engine.
"""
import sys
from pathlib import Path

from search.engine import HybridSearchEngine


def main():
    """Run the hybrid search CLI demo."""
    print("Hybrid Search Engine - Demo")
    print("=" * 60)

    # Use test database or default
    db_path = Path.home() / ".claude-memory" / "memory.db"

    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        print("Please run memory_store_v2.py to create database first.")
        sys.exit(1)

    # Initialize hybrid search
    print(f"\nInitializing hybrid search engine...")
    print(f"Database: {db_path}")

    hybrid = HybridSearchEngine(db_path, enable_cache=True)

    stats = hybrid.get_stats()
    print(f"\nIndexed {stats['bm25']['num_documents']} memories")
    print(f"  Vocabulary: {stats['bm25']['vocabulary_size']} terms")
    print(f"  TF-IDF: {'Available' if stats['tfidf_available'] else 'Not available'}")
    print(f"  Graph: {'Available' if stats['graph_available'] else 'Not available'}")

    # Test search
    if len(sys.argv) > 1:
        query = ' '.join(sys.argv[1:])
    else:
        query = "python web development"

    print("\n" + "=" * 60)
    print(f"Search Query: '{query}'")
    print("=" * 60)

    # Test different methods
    methods = ["bm25", "hybrid"]

    for method in methods:
        print(f"\nMethod: {method.upper()}")
        results = hybrid.search(query, limit=5, method=method)

        print(f"  Found {len(results)} results in {hybrid.last_search_time*1000:.2f}ms")

        for i, mem in enumerate(results, 1):
            print(f"\n  [{i}] Score: {mem['score']:.3f} | ID: {mem['id']}")
            if mem.get('category'):
                print(f"      Category: {mem['category']}")
            if mem.get('tags'):
                print(f"      Tags: {', '.join(mem['tags'][:3])}")
            print(f"      Content: {mem['content'][:100]}...")

    # Display final stats
    print("\n" + "=" * 60)
    print("Performance Summary:")
    print("=" * 60)

    final_stats = hybrid.get_stats()
    print(f"  Last search time: {final_stats['last_search_time_ms']:.2f}ms")
    print(f"  Last fusion time: {final_stats['last_fusion_time_ms']:.2f}ms")
    print(f"  Target: <50ms for 1K memories")

    if 'cache' in final_stats:
        cache_stats = final_stats['cache']
        print(f"\n  Cache hit rate: {cache_stats['hit_rate']*100:.1f}%")
        print(f"  Cache size: {cache_stats['current_size']}/{cache_stats['max_size']}")
