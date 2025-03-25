"""
Remote API Call Module for Query Parsing

This module provides functionality to call remote LLM APIs for parsing video search queries.
It uses the same provider routing mechanism as call_reasoner.py.
"""
import traceback
from pathlib import Path
import importlib
from utils.log_config import setup_logger
import time
from datetime import datetime, timedelta
import yaml

# Get logger using module name as identifier
logger = setup_logger(__name__)

# Load configuration file
def load_provider_priorities():
    config_path = Path(__file__).parent.parent / "config" / "model_config.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return config.get('provider_priorities', {})

def call_parse_api(provider, query, prompt_file="query_parser.md", format_instructions="", max_retries=3, retry_delay=2, timeout=60):
    """
    Call remote API for parsing video search queries
    
    Args:
        provider: Specific provider name, if None will try all providers by priority
        query: The user's search query
        prompt_file: Prompt template filename (default: query_parser.md)
        format_instructions: Instructions for formatting the output
        max_retries: Maximum retry attempts
        retry_delay: Delay between retries in seconds
        timeout: Request timeout in seconds for API calls
    
    Returns:
        Parsed query intent as JSON string
    """
    # Prepare prompt from template
    current_dir = Path(__file__).resolve().parent
    project_root = current_dir.parent
    config_file = project_root / "config/prompts" / prompt_file
    
    with open(config_file, "r", encoding="utf-8") as f:
        prompt_template = f.read()
    
    # Format prompt with query and format instructions
    formatted_prompt = prompt_template.replace("{query}", query)
    formatted_prompt = formatted_prompt.replace("{format_instructions}", format_instructions)
    
    # Create a temporary prompt file with the formatted prompt
    temp_prompt_file = f"parse_temp_{int(time.time())}.md"
    temp_prompt_path = project_root / "config/prompts" / temp_prompt_file
    
    try:
        # Write the formatted prompt to a temporary file
        with open(temp_prompt_path, "w", encoding="utf-8") as f:
            f.write(formatted_prompt)
        
        # Call the route_providers function to handle API calls
        return route_providers(
            provider=provider,
            meta_data="",
            duration="",
            transcript="",
            video_analyzing_results="",
            prompt=temp_prompt_file,
            max_retries=max_retries,
            retry_delay=retry_delay,
            timeout=timeout
        )
    finally:
        # Clean up the temporary file
        if temp_prompt_path.exists():
            temp_prompt_path.unlink()

class ProviderStatus:
    def __init__(self, name, base_priority):
        self.name = name
        self.base_priority = base_priority  # Base priority (lower is higher priority)
        self.fail_count = 0  # Number of consecutive failures
        self.last_fail_time = None  # Time of last failure
        self.current_priority = base_priority
    
    def record_success(self):
        """Record successful call and reset failure counters"""
        self.fail_count = 0
        self.last_fail_time = None
        self.current_priority = self.base_priority
    
    def record_failure(self):
        """Record failed call and update priority"""
        self.fail_count += 1
        self.last_fail_time = datetime.now()
        # Exponentially increase priority (lower priority) based on consecutive failures
        self.current_priority = self.base_priority * (2 ** self.fail_count)
    
    def should_retry(self, cooldown_minutes=5):
        """Determine if we should retry this provider"""
        if self.last_fail_time is None:
            return True
        
        # If provider has failed recently, wait for cooldown
        cooldown_period = timedelta(minutes=cooldown_minutes)
        time_since_failure = datetime.now() - self.last_fail_time
        
        return time_since_failure > cooldown_period

# Initialize provider status using priorities from config file
PROVIDER_STATUS = {
    name: ProviderStatus(name, priority)
    for name, priority in load_provider_priorities().items()
}

def get_sorted_providers():
    """
    Get providers sorted by current priority, filtering out those in cooldown
    """
    available_providers = [
        p for p in PROVIDER_STATUS.values() 
        if p.should_retry()
    ]
    return sorted(available_providers, key=lambda x: x.current_priority)

def route_providers(provider, meta_data, duration, transcript, video_analyzing_results, prompt, max_retries=3, retry_delay=2, timeout=100):
    """
    Try different API providers to call LLM service with dynamic priority
    
    Args:
        provider: Specific provider name, if None will try all providers by priority
        meta_data: Metadata
        duration: Duration of the video
        transcript: Transcription text
        video_analyzing_results: Video analysis results
        prompt: Prompt template filename
        max_retries: Maximum retry attempts
        retry_delay: Delay between retries in seconds
        timeout: Request timeout in seconds for API calls
    """
    last_error = None
    
    # Record start time
    start_time = time.time()
    logger.info(f"Starting route_providers with API timeout={timeout}s, max_retries={max_retries}")
    
    # If provider specified, only try that provider
    if provider:
        providers_to_try = [PROVIDER_STATUS[provider]] if provider in PROVIDER_STATUS else []
        logger.info(f"Using specified provider: {provider}")
    else:
        # Get available providers sorted by priority
        providers_to_try = get_sorted_providers()
        logger.info(f"Available providers (in priority order): {[p.name for p in providers_to_try]}")
    
    for provider_status in providers_to_try:
        provider_name = provider_status.name
        logger.info(f"Trying provider: {provider_name} (priority: {provider_status.current_priority})")
        
        for attempt in range(max_retries):
            attempt_start = time.time()
            logger.info(f"Attempt {attempt + 1}/{max_retries} for provider {provider_name}")
            
            try:
                # Dynamically import provider module
                logger.info(f"Importing module for provider: {provider_name}")
                module = importlib.import_module(f"modules.LLMcalls.{provider_name}")
                
                # Call provider's unify_results method with timeout parameter
                logger.info(f"Executing API call to {provider_name} with timeout={timeout}s")
                
                # We need to modify the provider modules to accept the timeout parameter
                # For now, we'll try to pass it, and if it fails, we'll catch the exception
                try:
                    result = module.unify_results(
                        meta_data,
                        duration,
                        transcript,
                        video_analyzing_results,
                        prompt,
                        timeout=timeout  # Pass timeout to provider module
                    )
                except TypeError:
                    # If the provider doesn't accept the timeout parameter yet, call without it
                    logger.warning(f"Provider {provider_name} doesn't accept timeout parameter, calling without it")
                    result = module.unify_results(
                        meta_data,
                        duration,
                        transcript,
                        video_analyzing_results,
                        prompt
                    )
                
                attempt_duration = time.time() - attempt_start
                logger.info(f"API call to {provider_name} completed in {attempt_duration:.2f}s")
                
                if result:
                    # Record success and return result
                    provider_status.record_success()
                    total_duration = time.time() - start_time
                    logger.info(f"Successfully got result from {provider_name} in {total_duration:.2f}s")
                    return result
                else:
                    logger.warning(f"{provider_name} returned empty result")
                    
            except Exception as e:
                last_error = e
                attempt_duration = time.time() - attempt_start
                
                # Record failure and update priority
                provider_status.record_failure()
                
                if "timeout" in str(e).lower():
                    logger.error(f"{provider_name} request timeout after {attempt_duration:.2f}s (limit: {timeout}s)")
                else:
                    logger.error(f"{provider_name} attempt {attempt + 1} failed after {attempt_duration:.2f}s: {str(e)}")
                    logger.debug(traceback.format_exc())
                
            if attempt < max_retries - 1:
                logger.info(f"Waiting {retry_delay}s before retry...")
                time.sleep(retry_delay)
    
    # If all providers failed
    total_duration = time.time() - start_time
    logger.error(f"All providers failed after {total_duration:.2f}s")
    if last_error:
        raise last_error
    return None 