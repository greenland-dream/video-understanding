import re
from pathlib import Path
import gc
import torch
import json

def extract_json(input_str):
    # Match JSON content wrapped in ```json or ``` (supports multiline)
    match = re.search(r'```(?:json)?\n({.*?})\n```', input_str, re.DOTALL)
    json_str = match.group(1).strip() if match else input_str.strip()
    
    # Try to parse the JSON string
    try:
        json_obj = json.loads(json_str)
        return json_obj
    except json.JSONDecodeError as e:
        # If parsing fails, try to fix common issues in the JSON
        # 1. Handle common escape issues
        json_str = json_str.replace('\\"', '"').replace('\\n', '\n')
        
        # 2. Fix missing commas between key-value pairs
        json_str = re.sub(r'(\w+")(\s*:\s*"[^"]*")(\s+)("?\w+"\s*:)', r'\1\2,\3\4', json_str)
        
        # 3. Remove trailing commas which are not valid in JSON
        json_str = re.sub(r',(\s*})', r'\1', json_str)
        json_str = re.sub(r',(\s*])', r'\1', json_str)
        
        # Try parsing again after fixes
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # If still failing, return a simple dict with the raw content
            return {"description": input_str.strip()}


def extract_number(filepath: str) -> int:
    """
    Extract number from filename for sorting
    """
    # Extract filename
    filename = Path(filepath).name
    # Extract number between '-' and '.mov'
    match = re.search(r'-\s*(\d+)\.mov$', filename, re.IGNORECASE)
    if match:
        return int(match.group(1))
    else:
        # If no number found, return infinity to sort to end
        return float('inf')

def clear_memory():
    """
    Clear Python garbage collector and MPS memory (for Apple Silicon).
    Call this function when you need to free up memory, especially before and after
    memory-intensive operations.
    """
    gc.collect()
    if hasattr(torch, 'mps'):
        torch.mps.empty_cache()