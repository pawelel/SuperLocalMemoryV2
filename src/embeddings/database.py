#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SuperLocalMemory (superlocalmemory.com)
"""Database integration for batch embedding generation.
"""
import json
import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def add_embeddings_to_database(
    engine,
    db_path: Path,
    embedding_column: str = 'embedding',
    batch_size: int = 32
):
    """
    Generate embeddings for all memories in database.

    Args:
        engine: An EmbeddingEngine instance
        db_path: Path to SQLite database
        embedding_column: Column name to store embeddings
        batch_size: Batch size for processing
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if embedding column exists
        cursor.execute("PRAGMA table_info(memories)")
        columns = {row[1] for row in cursor.fetchall()}

        if embedding_column not in columns:
            # Add column
            logger.info(f"Adding '{embedding_column}' column to database")
            cursor.execute(f'ALTER TABLE memories ADD COLUMN {embedding_column} TEXT')
            conn.commit()

        # Get memories without embeddings
        cursor.execute(f'''
            SELECT id, content, summary
            FROM memories
            WHERE {embedding_column} IS NULL OR {embedding_column} = ''
        ''')
        rows = cursor.fetchall()

        if not rows:
            logger.info("All memories already have embeddings")
            conn.close()
            return

        logger.info(f"Generating embeddings for {len(rows)} memories...")

        # Process in batches
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i+batch_size]
            memory_ids = [row[0] for row in batch]

            # Combine content and summary
            texts = []
            for row in batch:
                content = row[1] or ""
                summary = row[2] or ""
                text = f"{content} {summary}".strip()
                texts.append(text)

            # Generate embeddings
            embeddings = engine.encode(texts, batch_size=batch_size)

            # Store in database
            for mem_id, embedding in zip(memory_ids, embeddings):
                embedding_json = json.dumps(embedding.tolist())
                cursor.execute(
                    f'UPDATE memories SET {embedding_column} = ? WHERE id = ?',
                    (embedding_json, mem_id)
                )

            conn.commit()
            logger.info(f"Processed {min(i+batch_size, len(rows))}/{len(rows)} memories")

        # Save cache
        engine.save_cache()

        logger.info(f"Successfully generated embeddings for {len(rows)} memories")

    finally:
        conn.close()
