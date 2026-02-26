#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""CLI interface for manual graph operations.

Provides a command-line interface for building graphs, viewing stats,
finding related memories, inspecting clusters, and generating summaries.
"""
import json


def main():
    """CLI interface for manual graph operations."""
    import argparse
    from graph.graph_core import GraphEngine
    from graph.cluster_builder import ClusterBuilder

    parser = argparse.ArgumentParser(description='GraphEngine - Knowledge Graph Management')
    parser.add_argument('command', choices=['build', 'stats', 'related', 'cluster', 'hierarchical', 'summaries'],
                       help='Command to execute')
    parser.add_argument('--memory-id', type=int, help='Memory ID for related/add commands')
    parser.add_argument('--cluster-id', type=int, help='Cluster ID for cluster command')
    parser.add_argument('--min-similarity', type=float, default=0.3,
                       help='Minimum similarity for edges (default: 0.3)')
    parser.add_argument('--hops', type=int, default=2, help='Max hops for related (default: 2)')

    args = parser.parse_args()

    engine = GraphEngine()

    if args.command == 'build':
        print("Building knowledge graph...")
        stats = engine.build_graph(min_similarity=args.min_similarity)
        print(json.dumps(stats, indent=2))

    elif args.command == 'stats':
        print("Graph Statistics:")
        stats = engine.get_stats()
        print(json.dumps(stats, indent=2))

    elif args.command == 'related':
        if not args.memory_id:
            print("Error: --memory-id required for 'related' command")
            return

        print(f"Finding memories related to #{args.memory_id}...")
        related = engine.get_related(args.memory_id, max_hops=args.hops)

        if not related:
            print("No related memories found")
        else:
            for idx, mem in enumerate(related, 1):
                print(f"\n{idx}. Memory #{mem['id']} ({mem['hops']}-hop, weight={mem['weight']:.3f})")
                print(f"   Relationship: {mem['relationship']}")
                summary = mem['summary'] or '[No summary]'
                print(f"   Summary: {summary[:100]}...")
                if mem['shared_entities']:
                    print(f"   Shared: {', '.join(mem['shared_entities'][:5])}")

    elif args.command == 'cluster':
        if not args.cluster_id:
            print("Error: --cluster-id required for 'cluster' command")
            return

        print(f"Cluster #{args.cluster_id} members:")
        members = engine.get_cluster_members(args.cluster_id)

        for idx, mem in enumerate(members, 1):
            print(f"\n{idx}. Memory #{mem['id']} (importance={mem['importance']})")
            summary = mem['summary'] or '[No summary]'
            print(f"   {summary[:100]}...")

    elif args.command == 'hierarchical':
        print("Running hierarchical sub-clustering...")
        cluster_builder = ClusterBuilder(engine.db_path)
        stats = cluster_builder.hierarchical_cluster()
        print(json.dumps(stats, indent=2))

    elif args.command == 'summaries':
        print("Generating cluster summaries...")
        cluster_builder = ClusterBuilder(engine.db_path)
        count = cluster_builder.generate_cluster_summaries()
        print(f"Generated summaries for {count} clusters")


if __name__ == '__main__':
    main()
