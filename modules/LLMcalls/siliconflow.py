import requests
import json
from pathlib import Path
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
        return config["api_configs"], config.get("default_model", "chat")
    except Exception as e:
        logger.error(f"Failed to load API config file: {str(e)}")
        raise

def unify_results(meta_data: str, duration: str, transcript: str, key_frame_analyzing_results: str, video_analyzing_results: str, prompt: str):
    """
    Unify analysis results using SiliconFlow API
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
    
    logger.info("Prompt sent to SiliconFlow:")
    logger.info(f"{question}")

    # Load API configuration
    api_configs, _ = load_api_configs()
    config = next((config for config in api_configs if config["name"] == "siliconflow"), None)
    if not config:
        raise ValueError("SiliconFlow API configuration not found")

    model = config["models"].get("chat")
    if not model:
        raise ValueError("Chat model configuration not found")

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": question
            }
        ],
        "stream": False,
        "max_tokens": 4096,
        "temperature": 0.3,
        "top_p": 0.9,
        "top_k": 50,
        "frequency_penalty": 0.5,
        "n": 1,
        "response_format": {"type": "text"}
    }

    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json"
    }

    response = requests.post(config["base_url"], json=payload, headers=headers)
    logger.info(f"SiliconFlow response status code: {response.status_code}")
    
    if response.status_code != 200:
        raise Exception(f"API call failed: {response.text}")

    result = json.loads(response.text)
    content = result["choices"][0]["message"]["content"]
    
    logger.info("SiliconFlow response:")
    logger.info(f"{content}")
    return content


