import os
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"  # Enable MPS fallback if needed
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import torch, argparse
from modelscope import AutoConfig, AutoModel, AutoTokenizer
from decord import VideoReader, cpu
from PIL import Image
from huggingface_hub import snapshot_download
import logging, json, sys
from pathlib import Path

env = os.environ.copy()
env["PYTHONWARNINGS"] = "ignore"

# Configure logging output to console, set log level and output format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=sys.stderr
)

logger = logging.getLogger(__name__)

def _download_and_load_model(model_id: str = "mPLUG/mPLUG-Owl3-2B-241014",
                             cache_dir: str = "./models",
                             device: str = "mps"):
    """
    Download and load model, tokenizer and processor
    """
    model_dir = snapshot_download(repo_id=model_id, cache_dir=cache_dir)
    
    config = AutoConfig.from_pretrained(model_dir, trust_remote_code=True)
    model = AutoModel.from_pretrained(model_dir, trust_remote_code=True)
    model = model.eval().to(device)
    
    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    processor = model.init_processor(tokenizer)
    
    return model, tokenizer, processor

def _encode_video(video_path: str, max_num_frames: int = 16) -> list:
    """
    Uniformly sample frames from video and return a list of sampled frames (in PIL.Image format)
    """
    def _uniform_sample(indices, n):
        gap = len(indices) / n
        idxs = [int(i * gap + gap / 2) for i in range(n)]
        return [indices[i] for i in idxs]
    
    vr = VideoReader(video_path, ctx=cpu(0))
    sample_fps = round(vr.get_avg_fps() / 1)  # Adjust sampling rate as needed
    frame_indices = list(range(0, len(vr), sample_fps))
    
    if len(frame_indices) > max_num_frames:
        frame_indices = _uniform_sample(frame_indices, max_num_frames)
    
    frames = vr.get_batch(frame_indices).asnumpy()
    frames = [Image.fromarray(frame.astype('uint8')) for frame in frames]
    return frames

def _analyze_video(video_path: str,
                  prompt: str = "video_understanding_zh.md",
                  model_id: str = "mPLUG/mPLUG-Owl3-2B-241014",
                  max_new_tokens: int = 512,
                  max_num_frames: int = 16,
                  cache_dir: str = "./models",
                  device: str = "mps") -> str:
    """
    Use mPLUG model to analyze video and generate labels.
    Analyze all sampled frames as a whole and return a comprehensive label result.
    """
    # Current script directory: modules
    current_dir = Path(__file__).resolve().parent
    
    # Go back to project root directory
    project_root = current_dir.parent
    
    # Construct relative path for config file
    config_file = project_root / "config/prompts" / prompt

    # Read file content
    with open(config_file, "r", encoding="utf-8") as f:
        question = f.read()

    # Check if video file exists
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file {video_path} does not exist.")
    
    # Load model, tokenizer and processor
    model, tokenizer, processor = _download_and_load_model(model_id=model_id,
                                                           cache_dir=cache_dir,
                                                           device=device)
    
    # Sample video frames and input all frames as a whole (generate one overall label per video)
    frames = _encode_video(video_path, max_num_frames=max_num_frames)
    # Note: Put all frames as one list (one input item per video)
    video_frames = [frames]
    
    # Construct conversation: user role message contains "<|video|>\n" + question, keep question unchanged
    messages = [
        {"role": "user", "content": f"<|video|>\n{question}"},
        {"role": "assistant", "content": ""}
    ]
    
    # Call processor for input preprocessing, pass videos parameter with frame list
    inputs = processor(messages, images=None, videos=video_frames)
    inputs = inputs.to(device)
    
    with torch.no_grad():
        inputs.update({
            'tokenizer': tokenizer,
            'max_new_tokens': max_new_tokens,
            'decode_text': True,
        })
        output = model.generate(**inputs)
    
    if isinstance(output, str):
        generated_text = output
    elif isinstance(output, (list, tuple)):
        generated_text = output[0] if len(output) > 0 else ""
    else:
        generated_text = tokenizer.batch_decode(output, skip_special_tokens=True)[0]
    
    return generated_text

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True, help="Path to the video")
    parser.add_argument("--prompt", default="video_understanding_zh.md", help="prompt file")
    parser.add_argument("--model", default="mPLUG/mPLUG-Owl3-2B-241014", help="model path")
    parser.add_argument("--max_tokens", type=int, default=512, help="max token length")
    parser.add_argument("--max_frames", type=int, default=16, help="max token length")
    parser.add_argument("--device", default="mps", help="device")

    args = parser.parse_args()
    
    logger.info(f"processing video in: {args.video}, with prompt: {args.prompt}, model: {args.model}, max_tokens: {args.max_tokens}, max_frames: {args.max_frames}")
    answer = _analyze_video(args.video, prompt=args.prompt, model_id=args.model, max_new_tokens=args.max_tokens, max_num_frames=args.max_frames, device=args.device)
    print(json.dumps({"answer": answer}))

if __name__ == "__main__":
    main()
