import subprocess
import json, re
import os, glob, traceback
from pathlib import Path
from utils.log_config import setup_logger
from utils.write_tags import embed_metadata_with_exiftool, write_description
from utils.ffmpeg_funs import extract_representative_frame
from modules.call_reasoner import route_providers
from utils.utility import extract_json
from modules.audio_processing.audio_extractor import extract_audio
from modules.audio_processing.sensevoice_recognition import SenseVoiceTranscriber
from modules.call_sensevoice import process_audio
import yaml
from modules.call_jenus import analyze_frame
import os

os.environ["TOKENIZERS_PARALLELISM"] = "false"
logger = setup_logger(__name__)


def load_config():
    """
    load config file
    """
    config_path = Path(__file__).parent / "config" / "model_config.yaml"
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def _key_frame_understanding(image_path):
    """
    Call Janus API to analyze key frame
    """
    config = load_config()
    response = analyze_frame(
        image_path,
        prompt=config['janus']['prompt_file'],
        model_path=config['janus']['model']
    )
    logger.info("Response from Janus:")
    logger.info(f"{response}")
    return {"answer": response}

def _video_understanding(video_path):
    """
    Call OwL3 API to analyze video content
    """
    config = load_config()
    func2_dir = Path(__file__).parent / "modules"
    result = subprocess.run(
        [
            config['owl3']['python_path'],
            "-W", "ignore",
            "call_owl3.py",
            "--video", video_path,
            "--prompt", config['owl3']['prompt_file'],
            "--model", config['owl3']['model'],
            "--max_tokens", str(config['owl3']['max_tokens']),
            "--max_frames", str(config['owl3']['max_frames']),
            "--device", config['owl3']['device'],
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=func2_dir,
        text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"Function2 failed: {result.stderr}")
    
    json_str = result.stdout.strip().split('\n')[-1].strip()
    logger.info("Response from Owl3:")
    logger.info(f"{json_str}")
    
    return json.loads(json_str)

def extract_number(filepath: str) -> int:
    # Extract filename
    filename = Path(filepath).name
    # Extract number between '-' and '.mov'
    match = re.search(r'-\s*(\d+)\.mov$', filename, re.IGNORECASE)
    if match:
        return int(match.group(1))
    else:
        # If no number found, return infinity to sort to end
        return float('inf')

def _get_meta_data(video_path):
    """
    Get video metadata from meta_data.txt in the video directory
    """
    base_dir = os.path.dirname(video_path)
    meta_data_file = os.path.join(base_dir, "meta_data.txt")
    
    if not os.path.exists(meta_data_file):
        raise FileNotFoundError(f"Metadata file not found: {meta_data_file}")
    
    with open(meta_data_file, 'r', encoding='utf-8') as file:
        meta_data = file.read()
    
    return meta_data

def _process_video_folder(folder_path):
    """
    Process all videos in folder_path
    """
    video_extensions = ("*.mp4", "*.mov", "*.avi", "*.mkv")
    video_files = []
    for ext in video_extensions:
        video_files.extend(glob.glob(os.path.join(folder_path, ext)))
    
    if not video_files:
        logger.warning("No video files found.")
        return
    
    sorted_video_list = sorted(video_files, key=extract_number)

    for video_path in sorted_video_list:
        try:
            logger.info("------------------------------------------------------------------------------------------------")
            logger.info(f"\nProcessing video: {video_path}")
            base = os.path.splitext(video_path)[0]
            
            # 1. Process audio (extract and transcribe)
            logger.info("1. Processing audio...")
            transcript = process_audio(video_path)
            
            # 3. Extract key frame
            logger.info("3. Extracting key frame...")
            temp_image = base + "_keyframe.jpg"
            _, duration = extract_representative_frame(video_path, temp_image)

            # 4. Analyze key frame
            logger.info("4. Analyzing key frame...")
            result_key_frame = _key_frame_understanding(temp_image)
            os.remove(temp_image)  # Delete temp key frame image
            
            # 5. Analyze video
            logger.info("5. Analyzing video...")
            result_video = _video_understanding(video_path)
            
            # 6. Get metadata
            logger.info("6. Getting metadata...")
            meta_data = _get_meta_data(video_path)
            
            # 7. Combine all analysis results
            logger.info("7. Combining analysis results by calling reasoning model...")
            final_result = route_providers(
                None,  # No specific provider, try by priority
                meta_data,
                duration,
                transcript,
                result_key_frame,
                result_video,
                "combine_video_image_results.md"
            )
            final_result = extract_json(final_result)
            
            # 8. Write metadata
            logger.info("8. Writing metadata...")
            isVoiceover, hierarchical_keywords = embed_metadata_with_exiftool(video_path, transcript, final_result)
            logger.info(f"Hierarchical keywords: {hierarchical_keywords}")
            
            # 9. Write description file
            logger.info("9. Writing description file...")
            write_description(folder_path, video_path, transcript, hierarchical_keywords, final_result, isVoiceover, duration)
            
        except Exception as e:
            logger.error(f"Error processing video {video_path}: {str(e)}")
            logger.error(traceback.format_exc())
            continue

def main():
    # put your folder path here
    folder_paths = [
        "your_folder_path"
    ]
    
    for folder_path in folder_paths:
        logger.info(f"\n ========================================== Processing folder: {folder_path} ==========================================")
        _process_video_folder(folder_path)

if __name__ == "__main__":
    main()