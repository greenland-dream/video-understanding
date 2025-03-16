import subprocess
import json
import os
import traceback
from pathlib import Path
from utils.log_config import setup_logger
from modules.config_loader import load_config

logger = setup_logger(__name__)

def analyze_video_content(video_path):
    """
    Call OWL3 API to analyze video content
    
    Args:
        video_path: Path to the video file
        
    Returns:
        dict: Analysis results from OWL3
    """
    config = load_config()
    func2_dir = Path(__file__).parent
    
    # Check if video file exists
    if not os.path.exists(video_path):
        logger.error(f"Video file not found: {video_path}")
        return {
            "error": "File not found",
            "answer": "Failed to analyze movements"
        }
    
    # Build OWL3 command
    cmd = [
        config['owl3']['python_path'],
        "-W", "ignore",
        "call_owl3.py",
        "--video", video_path,
        "--prompt", config['owl3']['prompt_file'],
        "--model", config['owl3']['model'],
        "--max_tokens", str(config['owl3']['max_tokens']),
        "--max_frames", str(config['owl3']['max_frames']),
        "--device", config['owl3']['device'],
    ]
    
    # Log start of analysis
    logger.info(f"Starting OWL3 video analysis: {os.path.basename(video_path)}")
    
    # Set timeout (3 minutes)
    timeout = 180  # seconds
    
    try:
        # Start subprocess
        logger.info("Starting OWL3 subprocess...")
        
        # Use subprocess.run with timeout instead of Popen for simpler handling
        try:
            logger.info(f"Running command: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=func2_dir,
                text=True,
                timeout=timeout  # Direct timeout setting
            )
            
            # Get output
            stdout = result.stdout
            stderr = result.stderr
            
            # Log key steps
            logger.info("OWL3 process completed, processing output...")
            logger.info(f"OWL3 output: {stdout}")
            logger.info(f"OWL3 stderr: {stderr}")

            # Check process exit status
            if result.returncode != 0:
                logger.error(f"OWL3 process exited abnormally, return code: {result.returncode}")
                return {"answer": "Failed to analyze movements"}
            
        except subprocess.TimeoutExpired:
            logger.warning(f"OWL3 process timed out after {timeout} seconds")
            return {"answer": "Failed to analyze movements due to timeout"}
        

        # Try to parse JSON output
        result = stdout.strip().split('\n')[-1].strip()
        logger.info(f"Response from Owl3: {result}")

        return json.loads(result)
        
    except Exception as e:
        # Catch all exceptions
        logger.error(f"Error during video analysis: {str(e)}")
        logger.error(traceback.format_exc())
        return {"answer": "Failed to analyze movements"} 