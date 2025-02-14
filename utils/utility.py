import re

def extract_json(input_str):
    # Match JSON content wrapped in ```json or ``` (supports multiline)
    match = re.search(r'```(?:json)?\n({.*?})\n```', input_str, re.DOTALL)
    return match.group(1).strip() if match else input_str.strip()