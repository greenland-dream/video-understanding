"""
Azure API Call Module
"""
import json
from typing import List, Dict, Any, Optional
from pathlib import Path

from utils.log_config import setup_logger
from openai import AzureOpenAI  
from utils.log_config import setup_logger

# Configure logging
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

def unify_results(meta_data: str, duration: str, transcript: str, video_analyzing_results: str, prompt: str, timeout: int = 100):
    """
    Unify analysis results using Azure API
    
    Args:
        meta_data: Metadata
        duration: Duration of the video
        transcript: Transcription text
        video_analyzing_results: Video analysis results
        prompt: Prompt template filename
        timeout: Request timeout in seconds (default: 100)
    """
    try:
        # Read prompt template
        current_dir = Path(__file__).resolve().parent
        project_root = current_dir.parent.parent
        config_file = project_root / "config/prompts" / prompt
        
        with open(config_file, "r", encoding="utf-8") as f:
            question = f.read()

        # Replace template variables
        question = question.replace("{{meta_data}}", str(meta_data))
        question = question.replace("{{duration}}", str(duration))
        question = question.replace("{{transcript}}", str(transcript))
        question = question.replace("{{video_analyzing_results}}", str(video_analyzing_results))
        
        logger.info("Prompt sent to Azure:")
        logger.info(f"{question}")

        # Load API configuration
        api_configs, _ = load_api_configs()
        config = next((config for config in api_configs if config["name"] == "azure"), None)
        if not config:
            raise ValueError("Azure API configuration not found")

        # Use ChatAPI class for API call
        client = AzureOpenAI(  
            azure_endpoint=config["base_url"],  
            api_key=config["api_key"],  
            api_version=config["api_version"],
            timeout=timeout  # Set timeout for API calls
        )
            
        #Prepare the chat prompt 
        chat_prompt = [
            {"role": "user", "content": question}
        ]
        
        model = config["models"].get("chat")
        
        try:
            # Generate the completion  
            completion = client.chat.completions.create(  
                model=model,
                messages=chat_prompt,
                max_tokens=4096,  
                temperature=0.2,  
                top_p=0.95,  
                frequency_penalty=0,  
                presence_penalty=0,
                stop=None,  
                stream=False,
                timeout=timeout  # Set timeout for this specific request
            )

            content = completion.choices[0].message.content

            logger.info("Azure response:")
            logger.info(f"{content}")
            return content
        except Exception as e:
            if "timeout" in str(e).lower() or "timed out" in str(e).lower():
                logger.error(f"Azure API request timed out after {timeout}s")
                raise TimeoutError(f"Azure API request timed out after {timeout}s")
            else:
                raise

    except Exception as e:
        logger.error(f"Azure API call failed: {str(e)}")
        raise


