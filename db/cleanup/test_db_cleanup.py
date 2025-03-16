#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test script for db_cleanup.py

This script helps verify the functionality of db_cleanup.py by:
1. Connecting to both databases
2. Printing statistics about the databases
3. Identifying potential orphaned entries without deleting them
"""

import os
import sys
from pathlib import Path

# Add the project root directory to the path to import project modules
current_dir = Path(__file__).parent  # db/cleanup
project_root = current_dir.parent.parent  # Go up two levels to reach project root

sys.path.append(str(project_root))

# Import the database module
from db import VideoDatabase
from utils.log_config import setup_logger

# Setup logging
logger = setup_logger(__name__)

def test_database_connections():
    """Test connections to both databases and print basic statistics"""
    # Get database paths
    db_dir = project_root / "db"
    db_data_dir = db_dir / "data"
    
    db_path = str(db_data_dir / "video_processing.db")
    chroma_path = str(db_data_dir / "chroma_db")
    
    logger.info(f"Testing database connections")
    logger.info(f"SQL database path: {db_path}")
    logger.info(f"Chroma database path: {chroma_path}")
    
    # Initialize the database
    db = VideoDatabase(db_path=db_path, chroma_path=chroma_path)
    
    try:
        # Test SQL database connection
        session = db.Session()
        try:
            from db.video_db import ProcessedVideo
            # Count videos in SQL database
            sql_count = session.query(ProcessedVideo).count()
            logger.info(f"SQL database connection successful")
            logger.info(f"Found {sql_count} videos in SQL database")
        finally:
            session.close()
        
        # Test Chroma database connection
        try:
            # Count documents in Chroma database
            chroma_count = db.collection.count()
            logger.info(f"Chroma database connection successful")
            logger.info(f"Found {chroma_count} documents in Chroma database")
        except Exception as e:
            logger.error(f"Error connecting to Chroma database: {str(e)}")
            return False
        
        return True
    
    except Exception as e:
        logger.error(f"Error testing database connections: {str(e)}")
        return False
    
    finally:
        # Close the database connection
        db.close()

def identify_orphaned_entries():
    """Identify entries in Chroma that don't exist in SQL database"""
    # Get database paths
    db_dir = project_root / "db"
    db_data_dir = db_dir / "data"
    
    db_path = str(db_data_dir / "video_processing.db")
    chroma_path = str(db_data_dir / "chroma_db")
    
    logger.info(f"Identifying orphaned entries")
    
    # Initialize the database
    db = VideoDatabase(db_path=db_path, chroma_path=chroma_path)
    
    try:
        # Get IDs from SQL database
        session = db.Session()
        try:
            from db.video_db import ProcessedVideo
            # Query all IDs from the processed_videos table
            result = session.query(ProcessedVideo.id).all()
            # Convert the result to a set of IDs
            sql_ids = {row[0] for row in result}
            logger.info(f"Found {len(sql_ids)} videos in SQL database")
        finally:
            session.close()
        
        # Get IDs from Chroma database
        try:
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
            
            logger.info(f"Found {len(all_ids)} documents in Chroma database")
            logger.info(f"Found {len(base_ids)} unique videos in Chroma database")
            
            # Find IDs in Chroma that don't exist in SQL
            missing_base_ids = base_ids - sql_ids
            
            if not missing_base_ids:
                logger.info("No orphaned entries found in Chroma database")
                return True
            
            logger.info(f"Found {len(missing_base_ids)} videos in Chroma that don't exist in SQL database")
            
            # Print the first 5 missing IDs as examples
            for i, base_id in enumerate(sorted(missing_base_ids)[:5]):
                logger.info(f"Example orphaned entry {i+1}: {base_id}")
            
            if len(missing_base_ids) > 5:
                logger.info(f"... and {len(missing_base_ids) - 5} more")
            
            return True
        
        except Exception as e:
            logger.error(f"Error querying Chroma database: {str(e)}")
            return False
    
    except Exception as e:
        logger.error(f"Error identifying orphaned entries: {str(e)}")
        return False
    
    finally:
        # Close the database connection
        db.close()

def main():
    """Run the test functions"""
    logger.info("Starting database test")
    
    # Test database connections
    if not test_database_connections():
        logger.error("Database connection test failed")
        return
    
    # Identify orphaned entries
    if not identify_orphaned_entries():
        logger.error("Orphaned entry identification failed")
        return
    
    logger.info("Database test completed successfully")
    logger.info("To clean up orphaned entries, run db_cleanup.py")

if __name__ == "__main__":
    main() 