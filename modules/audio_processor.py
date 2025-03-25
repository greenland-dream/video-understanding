import os
from pathlib import Path
from utils.log_config import setup_logger
from modules.audio_processing.audio_extractor import extract_audio


logger = setup_logger(__name__)

def process_audio(video_path, transcriber):
    """
    Process the audio part of the video: extract and transcribe
    
    Args:
        video_path (str): Path to the video file
    
    Returns:
        str: Audio transcription result
        
    Raises:
        Exception: When audio processing fails
    """
    try:
        # 1. Extract audio
        logger.info("Extracting audio...")
        audio_path = extract_audio(video_path)
        
        # 2. Transcribe audio
        logger.info("Starting audio transcription...")
        transcript = transcriber.transcribe(audio_path)
        logger.info(f"Transcription result: {transcript}")
        
        # Clean up temp files
        if os.path.exists(audio_path):
            os.remove(audio_path)
            
        return transcript
        
    except Exception as e:
        logger.error(f"Error processing audio for video {video_path}: {str(e)}")
        raise 