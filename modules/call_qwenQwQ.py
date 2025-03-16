from mlx_lm import load, generate
from pathlib import Path
import time

def generate_response(
    # model_path="mlx-community/QwQ-32B-8bit",
    # model_path="Qwen/Qwen2.5-14B-Instruct-1M",
    # model_path="mlx-community/Qwen2.5-14B-Instruct-1M-8bit",
    model_path="mlx-community/Qwen2.5-7B-Instruct-1M-3bit",
    prompt="Hello, how are you?",
    max_tokens=512,
    temperature=0.7,
    verbose=True
):
    """
    Generate a response using the QwQ model.
    
    Args:
        model_path: Path to the model
        prompt: Input prompt text
        max_tokens: Maximum number of tokens to generate
        temperature: Sampling temperature (higher = more creative, lower = more deterministic)
        verbose: Whether to print generation progress
        
    Returns:
        Generated response text
    """
    # Load model and tokenizer
    model, tokenizer = load(model_path)
    
    # Format prompt with chat template if available
    if tokenizer.chat_template is not None:
        messages = [{"role": "user", "content": prompt}]
        prompt = tokenizer.apply_chat_template(
            messages, add_generation_prompt=True
        )
    
    # Generate response
    response = generate(
        model, 
        tokenizer, 
        prompt=prompt, 
        max_tokens=max_tokens,
    )
    
    return response

if __name__ == "__main__":
    # Example usage
    # Current script directory: modules
    current_dir = Path(__file__).resolve().parent
    
    # Go back to project root directory
    project_root = current_dir.parent
    
    # Construct relative path for config file
    config_file = project_root / "config/prompts/combined_analysis.md"

    # Read file content
    with open(config_file, "r", encoding="utf-8") as f:
        prompt = f.read()
    max_tokens = 32768  # Output token limit
    
    # Measure inference time
    start_time = time.time()
    
    response = generate_response(prompt=prompt, max_tokens=max_tokens)
    # response = generate_response(prompt="Who are you?", max_tokens=max_tokens)

    end_time = time.time()
    inference_time = end_time - start_time
    
    print(f"\n\nInference completed in {inference_time:.2f} seconds ({inference_time/60:.2f} minutes)")
    print("\n" + "="*50 + " RESPONSE " + "="*50)
    print(response)
    print("="*111)
