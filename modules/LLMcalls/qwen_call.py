# Please install OpenAI SDK first: `pip3 install openai`

from openai import OpenAI
from pathlib import Path
import json
from utils.log_config import setup_logger

logger = setup_logger(__name__)

def load_api_configs():
    """
    Load API configurations from config file
    """
    try:
        config_path = Path(__file__).resolve().parent.parent.parent / "config" / "api_configs.json"
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config["api_configs"], config.get("default_model", "reasoner")
    except Exception as e:
        logger.error(f"Failed to load API config file: {str(e)}")
        raise

def unify_results(meta_data: str, duration: str, transcript: str, key_frame_analyzing_results: str, video_analyzing_results: str, prompt: str, timeout: int = 100):
    """
    Analyze two results and return the analysis result
    
    Args:
        meta_data: Metadata
        duration: Duration of the video
        transcript: Transcription text
        key_frame_analyzing_results: Key frame analysis results
        video_analyzing_results: Video analysis results
        prompt: Prompt template filename
        timeout: Request timeout in seconds (default: 100)
    """
    current_dir = Path(__file__).resolve().parent
    project_root = current_dir.parent.parent
    config_file = project_root / "config/prompts" / prompt
    
    with open(config_file, "r", encoding="utf-8") as f:
        question = f.read()

    question = question.replace("{{meta_data}}", str(meta_data))
    question = question.replace("{{duration}}", str(duration))
    question = question.replace("{{transcript}}", str(transcript))
    question = question.replace("{{key_frame_analyzing_results}}", str(key_frame_analyzing_results))
    question = question.replace("{{video_analyzing_results}}", str(video_analyzing_results))
    
    logger.info("Prompt sent to Qwen:")
    logger.info(f"{question}")

    # Load API configuration
    api_configs, _ = load_api_configs()
    config = next((config for config in api_configs if config["name"] == "qwen"), None)
    if not config:
        raise ValueError("Qwen API configuration not found")

    # Create client and call API
    client = OpenAI(
        api_key=config["api_key"],
        base_url=config["base_url"],
        timeout=timeout  # Set timeout for API calls
    )

    model = config["models"].get("reasoner")
    if not model:
        raise ValueError("Reasoner model configuration not found")

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant"},
                {"role": "user", "content": question},
            ],
            stream=False,
            timeout=timeout  # Set timeout for this specific request
        )
        
        result = response.choices[0].message.content
        logger.info("Qwen response:")
        logger.info(f"{result}")
        return result
    except Exception as e:
        if "timeout" in str(e).lower() or "timed out" in str(e).lower():
            logger.error(f"Qwen API request timed out after {timeout}s")
            raise TimeoutError(f"Qwen API request timed out after {timeout}s")
        else:
            logger.error(f"Error calling Qwen API: {str(e)}")
            raise
