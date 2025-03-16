#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Database Cleanup Script

This script checks for videos that exist in the Chroma vector database but not in the 
SQLite database (video_processing.db) and removes those entries from Chroma.

The two databases share a common identifier (MD5 hash of the file path) to identify videos.
"""

import os
import sys
import hashlib
import argparse
from pathlib import Path
import logging
from typing import List, Set, Tuple

# Add the project root directory to the path to import project modules
current_dir = Path(__file__).parent  # db/cleanup
project_root = current_dir.parent.parent  # Go up two levels to reach project root

sys.path.append(str(project_root))

# Import the database module
from db import VideoDatabase
from utils.log_config import setup_logger

# Setup logging
logger = setup_logger(__name__)

def get_sql_video_ids(db: VideoDatabase) -> Set[str]:
    """
    Get all video IDs from the SQL database.
    
    Args:
        db: VideoDatabase instance
        
    Returns:
        Set of video IDs in the SQL database
    """
    session = db.Session()
    try:
        from db.video_db import ProcessedVideo
        # Query all IDs from the processed_videos table
        result = session.query(ProcessedVideo.id).all()
        # Convert the result to a set of IDs
        return {row[0] for row in result}
    finally:
        session.close()

def get_chroma_document_ids(db: VideoDatabase) -> Tuple[Set[str], Set[str]]:
    """
    Get all document IDs from the Chroma database.
    
    Args:
        db: VideoDatabase instance
        
    Returns:
        Tuple containing:
        - Set of all document IDs in Chroma
        - Set of base video IDs (without "_transcript" suffix)
    """
    # Get all IDs from the Chroma collection
    results = db.collection.get(include=["metadatas"])
    all_ids = set(results["ids"])
    
    # Extract base video IDs (without "_transcript" suffix)
    base_ids = set()
    for doc_id in all_ids:
        if doc_id.endswith("_transcript"):
            base_id = doc_id[:-11]  # Remove "_transcript" suffix
            base_ids.add(base_id)
        else:
            base_ids.add(doc_id)
    
    return all_ids, base_ids

def cleanup_chroma_database(db_path: str, chroma_path: str, dry_run: bool = False) -> None:
    """
    Clean up the Chroma database by removing entries that don't exist in the SQL database.
    
    Args:
        db_path: Path to the SQL database
        chroma_path: Path to the Chroma database
        dry_run: If True, only print what would be deleted without actually deleting
    """
    logger.info(f"Starting Chroma database cleanup")
    logger.info(f"SQL database path: {db_path}")
    logger.info(f"Chroma database path: {chroma_path}")
    
    # Initialize the database
    db = VideoDatabase(db_path=db_path, chroma_path=chroma_path)
    
    try:
        # Get IDs from both databases
        sql_ids = get_sql_video_ids(db)
        chroma_all_ids, chroma_base_ids = get_chroma_document_ids(db)
        
        logger.info(f"Found {len(sql_ids)} videos in SQL database")
        logger.info(f"Found {len(chroma_all_ids)} documents in Chroma database")
        logger.info(f"Found {len(chroma_base_ids)} unique videos in Chroma database")
        
        # Find IDs in Chroma that don't exist in SQL
        missing_base_ids = chroma_base_ids - sql_ids
        
        if not missing_base_ids:
            logger.info("No orphaned entries found in Chroma database")
            return
        
        logger.info(f"Found {len(missing_base_ids)} videos in Chroma that don't exist in SQL database")
        
        # Collect all document IDs to delete (including transcript documents)
        ids_to_delete = set()
        for base_id in missing_base_ids:
            # Add the base ID (description document)
            if base_id in chroma_all_ids:
                ids_to_delete.add(base_id)
            
            # Add the transcript ID if it exists
            transcript_id = f"{base_id}_transcript"
            if transcript_id in chroma_all_ids:
                ids_to_delete.add(transcript_id)
        
        logger.info(f"Will delete {len(ids_to_delete)} documents from Chroma database")
        
        if dry_run:
            logger.info("DRY RUN: No documents will be deleted")
            for doc_id in sorted(ids_to_delete):
                logger.info(f"Would delete: {doc_id}")
        else:
            # Delete the documents in batches to avoid potential issues with large deletions
            batch_size = 100
            for i in range(0, len(ids_to_delete), batch_size):
                batch = list(sorted(ids_to_delete))[i:i+batch_size]
                logger.info(f"Deleting batch of {len(batch)} documents")
                db.collection.delete(ids=batch)
            
            logger.info(f"Successfully deleted {len(ids_to_delete)} documents from Chroma database")
    
    finally:
        # Close the database connection
        db.close()

def main():
    parser = argparse.ArgumentParser(description="Clean up Chroma database by removing entries that don't exist in SQL database")
    parser.add_argument("--dry-run", action="store_true", help="Only print what would be deleted without actually deleting")
    parser.add_argument("--db-path", help="Path to the SQL database file")
    parser.add_argument("--chroma-path", help="Path to the Chroma database directory")
    args = parser.parse_args()
    
    # Get database paths from arguments or use default paths
    db_dir = project_root / "db"
    db_data_dir = db_dir / "data"
    
    db_path = args.db_path or str(db_data_dir / "video_processing.db")
    chroma_path = args.chroma_path or str(db_data_dir / "chroma_db")
    
    # Run the cleanup
    cleanup_chroma_database(db_path, chroma_path, args.dry_run)

if __name__ == "__main__":
    main() 