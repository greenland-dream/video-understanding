import yaml
from pathlib import Path
from utils.log_config import setup_logger

logger = setup_logger(__name__)

def load_config():
    """
    Load configuration from the model_config.yaml file
    
    Returns:
        dict: Configuration dictionary
    """
    config_path = Path(__file__).parent.parent / "config" / "model_config.yaml"
    
    if not config_path.exists():
        logger.error(f"Configuration file not found: {config_path}")
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    logger.info(f"Loading configuration from: {config_path}")
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    return config 