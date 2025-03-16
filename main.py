import os
import hashlib
from pathlib import Path
from utils.log_config import setup_logger
from db import VideoDatabase
import logging
from modules.video_processor import process_video_folder_recursive

os.environ["TOKENIZERS_PARALLELISM"] = "false"
logger = setup_logger(__name__)

def main():
    # Create database directories if they don't exist
    workspace_dir = Path(__file__).parent
    db_dir = workspace_dir / "db"
    db_dir.mkdir(exist_ok=True)
    
    # Database files will be stored in db/data directory
    db_data_dir = db_dir / "data"
    db_data_dir.mkdir(exist_ok=True)
    
    # Initialize the database
    db = VideoDatabase(
        db_path=str(db_data_dir / "video_processing.db"),
        chroma_path=str(db_data_dir / "chroma_db")
   )
    
    # put your folder path here
    folder_paths = [
        # "/Volumes/SSD_4T/videos"
    ]
    
    for folder_path in folder_paths:
        logger.info(f"\n ========================================== Processing folder: {folder_path} ==========================================")
        process_video_folder_recursive(folder_path, db)

if __name__ == "__main__":
    # Example usage
    main()