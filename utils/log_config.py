import logging
import os
from datetime import datetime
from pathlib import Path

# Global variable to store logger instance
_logger_instance = None

def setup_logger(name=None):
    """
    Set up or get global logger
    
    Args:
        name: Module name to identify log source
        
    Returns:
        logging.Logger: Configured logger instance
    """
    global _logger_instance
    
    # If logger instance already exists, return child logger
    if _logger_instance is not None:
        if name:
            child_logger = _logger_instance.getChild(name)
            # Allow log propagation to parent logger
            child_logger.propagate = True
            # Ensure child logger has no handlers
            child_logger.handlers = []
            return child_logger
        return _logger_instance
        
    # Create new logger instance
    logger = logging.getLogger("VideoAnalysis")
    logger.setLevel(logging.INFO)
    
    # Clear all existing handlers
    logger.handlers.clear()
    
    # Create logs directory
    log_dir = Path(__file__).resolve().parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    
    # Generate log filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"video_analysis_{timestamp}.log"
    
    # Create file handler
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    
    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # Set log format
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    # Store logger instance
    _logger_instance = logger
    
    return logger 