"""Run this model in Python

> pip install azure-ai-inference
"""
import os
from pathlib import Path
from utils.log_config import setup_logger
import json
from openai import OpenAI

# Get logger using module name as identifier
logger = setup_logger(__name__)

def load_api_configs():
    """
    Load API configurations from config file
    """
    try:
        config_path = Path(__file__).resolve().parent.parent.parent / "config" / "api_configs.json"
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config["api_configs"], config.get("default_model", "chat")
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
    try:
        # Load API configurations
        api_configs, _ = load_api_configs()
        config = next((config for config in api_configs if config["name"] == "GitHub"), None)
        if not config:
            raise ValueError("GitHub API configuration not found")

        # Current script directory: modules/LLMCalls
        current_dir = Path(__file__).resolve().parent
        # Go back to project root directory
        project_root = current_dir.parent.parent
        # Construct relative path for config file
        config_file = project_root / "config/prompts" / prompt
        
        # Read file content
        with open(config_file, "r", encoding="utf-8") as f:
            question = f.read()

        question = question.replace("{{meta_data}}", str(meta_data))
        question = question.replace("{{duration}}", str(duration))
        question = question.replace("{{transcript}}", str(transcript))
        question = question.replace("{{key_frame_analyzing_results}}", str(key_frame_analyzing_results))
        question = question.replace("{{video_analyzing_results}}", str(video_analyzing_results))
        
        logger.info("Prompt sent to GitHub:")
        logger.info(f"{question}")

        # Create client and call API
        client = OpenAI(
            api_key=config["api_key"],
            base_url=config["base_url"],
            timeout=timeout  # Set timeout for API calls
        )

        try:
            # Send request using OpenAI format
            response = client.chat.completions.create(
                model=config["model_name"],
                messages=[
                    {"role": "system", "content": "You are a helpful assistant"},
                    {"role": "user", "content": question},
                ],
                stream=False,
                timeout=timeout  # Set timeout for this specific request
            )

            logger.info("GitHub response:")
            content = response.choices[0].message.content
            logger.info(f"{content}")
            
            return content
        except Exception as e:
            if "timeout" in str(e).lower() or "timed out" in str(e).lower():
                logger.error(f"GitHub API request timed out after {timeout}s")
                raise TimeoutError(f"GitHub API request timed out after {timeout}s")
            else:
                logger.error(f"Error calling GitHub API: {str(e)}")
                raise

    except Exception as e:
        logger.error(f"GitHub API call failed: {str(e)}")
        raise

