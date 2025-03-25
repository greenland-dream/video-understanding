import os
import hashlib
from pathlib import Path
from utils.log_config import setup_logger
from db import VideoDatabase
import logging
from modules.video_processor import process_video_folder_recursive
from modules.audio_processing.sensevoice_recognition import SenseVoiceTranscriber
import torch
from transformers import AutoProcessor, Gemma3ForConditionalGeneration


os.environ["TOKENIZERS_PARALLELISM"] = "false"
logger = setup_logger(__name__)

ckpt = "google/gemma-3-4b-it"
video_understand_model = Gemma3ForConditionalGeneration.from_pretrained(
    ckpt, device_map="auto", torch_dtype=torch.bfloat16,
)
video_understand_processor = AutoProcessor.from_pretrained(ckpt)
transcriber = SenseVoiceTranscriber()

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
        ""
    ]
    
    for folder_path in folder_paths:
        logger.info(f"\n ========================================== Processing folder: {folder_path} ==========================================")
        process_video_folder_recursive(folder_path, db, transcriber, video_understand_model, video_understand_processor)
        
        # No need for redundant memory cleanup here as it's already done at the end of process_video_folder_recursive

if __name__ == "__main__":
    # Example usage
    main()