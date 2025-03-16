from pathlib import Path
from utils.log_config import setup_logger
from modules.call_jenus import analyze_frame
from modules.config_loader import load_config

logger = setup_logger(__name__)

def analyze_key_frame(image_path):
    """
    Call Janus API to analyze key frame
    
    Args:
        image_path: Path to the extracted key frame image
        
    Returns:
        dict: Analysis results from Janus
    """
    config = load_config()
    response = analyze_frame(
        image_path,
        prompt=config['janus']['prompt_file'],
        model_path=config['janus']['model']
    )
    logger.info("Response from Janus:")
    logger.info(f"{response}")
    return {"answer": response} 