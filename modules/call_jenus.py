# Usage: python call_jenus.py --folder /path/to/image/folder

import torch, argparse
from transformers import AutoModelForCausalLM
from janus.models import MultiModalityCausalLM, VLChatProcessor
from janus.utils.io import load_pil_images
import json, logging, sys
from pathlib import Path
# Configure logging output to console, set log level and output format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=sys.stderr
)

logger = logging.getLogger(__name__)


def analyze_frame(image, prompt = "key_frame_understanding_zh.md", model_path = "deepseek-ai/Janus-Pro-1B"):
    """
    Analyze images using deepseek junas and return descriptions and label information
    
    """
    # Current script directory: modules
    current_dir = Path(__file__).resolve().parent

    # Go back to project root directory: Video_understanding
    project_root = current_dir.parent

    # Construct relative path for config file
    config_file = project_root / "config/prompts" / prompt

    # Read file content
    with open(config_file, "r", encoding="utf-8") as f:
        question = f.read()

    vl_chat_processor: VLChatProcessor = VLChatProcessor.from_pretrained(
        model_path,
        use_fast=True
    )
    tokenizer = vl_chat_processor.tokenizer

    vl_gpt: MultiModalityCausalLM = AutoModelForCausalLM.from_pretrained(
        model_path, trust_remote_code=True
    )
    # vl_gpt = vl_gpt.to(torch.bfloat16).cuda().eval()
    vl_gpt = vl_gpt.to(torch.float16).to("mps").eval()

    conversation = [
        {
            "role": "<|User|>",
            "content": f"<image_placeholder>\n{question}",
            "images": [image],
        },
        {"role": "<|Assistant|>", "content": ""},
    ]

    # 4) Load images and create input dictionary
    pil_images = load_pil_images(conversation)
    prepare_inputs = vl_chat_processor(
        conversations=conversation, images=pil_images, force_batchify=True
    )

    # [Important] Convert to float16 and move to MPS here
    prepare_inputs = prepare_inputs.to(device=vl_gpt.device, dtype=torch.float16)

    # run image encoder to get the image embeddings
    inputs_embeds = vl_gpt.prepare_inputs_embeds(**prepare_inputs)

    # run the model to get the response
    outputs = vl_gpt.language_model.generate(
        inputs_embeds=inputs_embeds,
        attention_mask=prepare_inputs.attention_mask,
        pad_token_id=tokenizer.eos_token_id,
        bos_token_id=tokenizer.bos_token_id,
        eos_token_id=tokenizer.eos_token_id,
        max_new_tokens=512,
        do_sample=False,
        use_cache=True,
    )

    answer = tokenizer.decode(outputs[0].cpu().tolist(), skip_special_tokens=True)
    return answer

# def main():
#     parser = argparse.ArgumentParser()
#     parser.add_argument("--image", required=True, help="Path to the image")
#     parser.add_argument("--prompt", default="key_frame_understanding_zh.md", help="prompt file")
#     parser.add_argument("--model", default="deepseek-ai/Janus-Pro-1B", help="model path")

#     args = parser.parse_args()
    
#     logger.info(f"processing image in: {args.image}, with prompt: {args.prompt}, model: {args.model}")
#     answer = _analyze_frame(args.image, args.prompt, args.model)
#     print(json.dumps({"answer": answer}))


# if __name__ == "__main__":
#     main()

