import subprocess, os
from utils.log_config import setup_logger
import json
from typing import Tuple, Literal

logger = setup_logger(__name__)

def _get_video_duration(video_file):
    """
    Get video duration in seconds using ffprobe
    """
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        duration = float(result.stdout.strip())
        return duration
    except Exception as e:
        print(f"Failed to get video duration: {e}")
        return None

def extract_representative_frame(video_file, output_image):
    """
    Extract representative frame from video in following order:
      1. Try to extract I-frame first
      2. If I-frame not available, use scene detection (threshold adjustable, e.g. 0.4)
      3. If scene detection fails, extract middle frame
    """
    logger.info("Attempting to extract I-frame...")
    duration = _get_video_duration(video_file)
    command_i = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", video_file,
        "-vf", "select=eq(pict_type\\,I)",
        "-frames:v", "1",
        output_image
    ]
    try:
        subprocess.run(command_i, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error extracting I-frame: {e}")
    
    if os.path.exists(output_image) and os.path.getsize(output_image) > 0:
        logger.info("Successfully extracted I-frame.")
        return True, duration
    else:
        logger.warning("Failed to extract I-frame.")
    
    # # --- Method 2: Scene detection ---
    # print("Attempting to extract frame using scene detection...")
    # # Threshold 0.4 can be adjusted as needed
    # command_scene = [
    #     "ffmpeg", "-hide_banner", "-loglevel", "error",
    #     "-i", video_file,
    #     "-vf", "select=gt(scene\\,0.4),setpts=N/FRAME_RATE/TB",
    #     "-frames:v", "1",
    #     output_image
    # ]
    # try:
    #     subprocess.run(command_scene, check=True)
    # except subprocess.CalledProcessError as e:
    #     print(f"Error in scene detection: {e}")
    
    # if os.path.exists(output_image) and os.path.getsize(output_image) > 0:
    #     print("Successfully extracted frame using scene detection.")
    #     return True
    # else:
    #     print("Scene detection method failed.")
    
    # --- Method 3: Extract middle frame ---
    logger.info("Attempting to extract middle frame...")

    if duration is None:
        print("Cannot get video duration, unable to extract middle frame.")
        return False, duration
    mid_time = duration / 2
    command_middle = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-ss", str(mid_time),
        "-i", video_file,
        "-frames:v", "1",
        output_image
    ]
    try:
        subprocess.run(command_middle, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error extracting middle frame: {e}")
    
    if os.path.exists(output_image) and os.path.getsize(output_image) > 0:
        print("Successfully extracted middle frame.")
        return True, duration
    else:
        print("Failed to extract any representative frame.")
        return False, duration

def get_video_orientation(video_path: str) -> Literal["horizontal", "vertical", "square"]:
    """
    Determine video orientation
    
    Args:
        video_path: Path to video file
        
    Returns:
        "horizontal": Landscape orientation
        "vertical": Portrait orientation
        "square": Square aspect ratio
    """
    try:
        # Get video info using ffprobe
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",  # Select first video stream
            "-show_entries", "stream=width,height",
            "-of", "json",
            video_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffprobe failed: {result.stderr}")
            
        # Parse JSON output
        data = json.loads(result.stdout)
        width = int(data["streams"][0]["width"])
        height = int(data["streams"][0]["height"])
        
        # Determine orientation
        if width == height:
            return "square"
        elif width > height:
            return "horizontal"
        else:
            return "vertical"
            
    except Exception as e:
        logger.error(f"Failed to get video orientation: {str(e)}")
        raise

def get_video_duration(video_path: str) -> float:
    """
    Get video duration in seconds
    
    Args:
        video_path: Path to video file
        
    Returns:
        float: Video duration in seconds
    """
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "format=duration",
            "-of", "json",
            video_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffprobe failed: {result.stderr}")
            
        data = json.loads(result.stdout)
        duration = float(data["format"]["duration"])
        
        return duration
            
    except Exception as e:
        logger.error(f"Failed to get video duration: {str(e)}")
        raise
