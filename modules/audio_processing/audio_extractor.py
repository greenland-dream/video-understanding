import subprocess
from utils.log_config import setup_logger

logger = setup_logger(__name__)

def extract_audio(video_path):
    """
    Extract audio from video file using ffmpeg
    
    Args:
        video_path: Path to input video file
        
    Returns:
        str: Path to extracted audio file (.wav)
    """
    try:
        # Generate output audio path by replacing video extension with .wav
        audio_path = video_path.rsplit('.', 1)[0] + '.wav'
        
        # ffmpeg command to extract audio
        command = [
            'ffmpeg', '-y',
            '-i', video_path,
            '-vn',  # Disable video
            '-acodec', 'pcm_s16le',  # Set audio codec
            '-ar', '16000',  # Set sample rate
            '-ac', '1',  # Set to mono channel
            audio_path
        ]
        
        # Execute ffmpeg command
        result = subprocess.run(command, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error(f"Audio extraction failed: {result.stderr}")
            raise RuntimeError("Failed to extract audio")
            
        logger.info("Audio extracted successfully")
        return audio_path
        
    except Exception as e:
        logger.error(f"Error during audio extraction: {str(e)}")
        raise 