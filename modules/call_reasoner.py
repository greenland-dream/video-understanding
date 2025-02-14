import traceback
from pathlib import Path
import importlib
from utils.log_config import setup_logger
import time
from functools import wraps
import signal
from datetime import datetime, timedelta
from utils.log_config import setup_logger
import yaml

# Get logger using module name as identifier
logger = setup_logger(__name__)

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

# 加载配置文件
def load_provider_priorities():
    config_path = Path(__file__).parent.parent / "config" / "model_config.yaml"
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return config.get('provider_priorities', {})

# 初始化 provider 状态，使用配置文件中的优先级
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

def timeout_handler(signum, frame):
    raise TimeoutError("Request timeout")

def with_timeout(timeout_seconds=30):
    """
    Decorator: Add timeout limit to function
    
    Args:
        timeout_seconds: Timeout duration in seconds
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout_seconds)
            try:
                result = func(*args, **kwargs)
                signal.alarm(0)  # Clear alarm
                return result
            except TimeoutError:
                signal.alarm(0)  # Clear alarm
                raise
        return wrapper
    return decorator

def route_providers(provider, meta_data, duration, transcript, key_frame_analyzing_results, video_analyzing_results, prompt, max_retries=2, retry_delay=2, timeout=30):
    """
    Try different API providers to call LLM service with dynamic priority
    
    Args:
        provider: Specific provider name, if None will try all providers by priority
        meta_data: Metadata
        duration: Duration of the video
        transcript: Transcription text
        key_frame_analyzing_results: Key frame analysis results
        video_analyzing_results: Video analysis results
        prompt: Prompt template filename
        max_retries: Maximum retry attempts
        retry_delay: Delay between retries in seconds
        timeout: Request timeout in seconds
    """
    last_error = None
    
    # If provider specified, only try that provider
    if provider:
        providers_to_try = [PROVIDER_STATUS[provider]] if provider in PROVIDER_STATUS else []
    else:
        # Get available providers sorted by priority
        providers_to_try = get_sorted_providers()
    
    for provider_status in providers_to_try:
        provider_name = provider_status.name
        for attempt in range(max_retries):
            try:
                # Dynamically import provider module
                module = importlib.import_module(f"modules.LLMcalls.{provider_name}")
                
                # Add timeout control
                @with_timeout(timeout)
                def call_with_timeout():
                    return module.unify_results(
                        meta_data,
                        duration,
                        transcript,
                        key_frame_analyzing_results,
                        video_analyzing_results,
                        prompt
                    )
                
                # Call provider's unify_results method
                result = call_with_timeout()
                
                if result:
                    # Record success and return result
                    provider_status.record_success()
                    return result
                    
            except (TimeoutError, Exception) as e:
                last_error = e
                # Record failure and update priority
                provider_status.record_failure()
                
                if isinstance(e, TimeoutError):
                    logger.error(f"{provider_name} request timeout ({timeout}s)")
                else:
                    logger.error(f"{provider_name} attempt {attempt + 1} failed: {str(e)}")
                    logger.debug(traceback.format_exc())
                
            if attempt < max_retries - 1:
                logger.info(f"Waiting {retry_delay}s before retry...")
                time.sleep(retry_delay)
    
    # If all providers failed
    logger.error("All providers failed")
    if last_error:
        raise last_error
    return None

