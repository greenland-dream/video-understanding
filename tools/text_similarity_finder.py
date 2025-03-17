#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Text Similarity Finder

This script:
1. Takes text input (lyrics, instructions, etc.)
2. Expands instructions into full text if needed
3. Splits text into segments and generates video descriptions for each
4. Finds similar videos for each description (using multi-threading)
5. Saves the results to a target directory structure

Usage:
    python tools/text_similarity_finder.py --text "Your text or instructions here" --output_dir /path/to/output [--max_threads 10]
    python tools/text_similarity_finder.py --text_file /path/to/text_file.txt --output_dir /path/to/output [--max_threads 10]
"""

import os
import sys
import argparse
import shutil
import time
from pathlib import Path
import logging
from typing import List, Dict, Any, Tuple
import json
import threading
import concurrent.futures
from threading import Lock

# Add parent directory to path to allow imports when running from tools directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Import for API calls and local model
from modules.call_parse_api import call_parse_api
from modules.call_qwenQwQ import generate_response
from modules.call_reasoner import route_providers

# Database imports
from db import VideoDatabase
from modules.video_query import VideoQuerySystem
from utils.log_config import setup_logger

# Set up logging
logger = setup_logger(__name__)

def expand_instruction_to_text(instruction: str, target_duration: int = 25, background: str = "") -> str:
    """
    Expand an instruction into a full text script suitable for video narration
    
    Args:
        instruction: The instruction to expand
        target_duration: Target duration in seconds (default: 25)
        background: Background information to consider (optional)
        
    Returns:
        Expanded text script
    """
    logger.info(f"Expanding instruction to text (target duration: {target_duration}s)")
    
    # Load the prompt template
    current_dir = Path(__file__).resolve().parent
    project_root = current_dir.parent
    prompt_path = project_root / "config/prompts/expand_instruction.md"
    
    if not prompt_path.exists():
        logger.warning(f"Prompt file not found: {prompt_path}")
        # Fallback to hardcoded prompt
        prompt_template = """你是一位专业的视频脚本撰写专家。
请将以下指令转换为自然、对话式的视频脚本。
脚本应该在正常语速下大约需要 {target_duration} 秒来朗读。
参考：大约 150-170 个字是 1 分钟的语速，所以请尽量控制在 {word_count} 个字左右。
请使文本生动、清晰，适合视频配音。
不要包含任何时间戳、说话人名称或格式说明。
只需提供纯叙述文本。

指令: {instruction}

脚本:"""
    else:
        with open(prompt_path, "r", encoding="utf-8") as f:
            prompt_template = f.read()
    
    # Format the prompt
    word_count = int(target_duration * 2.8)  # Approximate Chinese character count for the duration
    formatted_prompt = prompt_template.format(
        target_duration=target_duration,
        word_count=word_count,
        instruction=instruction
    )
    
    # Create a temporary prompt file for the API call
    temp_prompt_file = f"expand_instruction_temp_{int(time.time())}.md"
    temp_prompt_path = project_root / "config/prompts" / temp_prompt_file
    
    # Ensure the directory exists
    os.makedirs(os.path.dirname(temp_prompt_path), exist_ok=True)
    
    try:
        # Write the prompt to a temporary file
        with open(temp_prompt_path, "w", encoding="utf-8") as f:
            f.write(formatted_prompt)
        
        # Try to use the remote API first
        try:
            expanded_text = route_providers(
                provider=None,  # Try all providers by priority
                meta_data="",
                duration="",
                transcript="",
                key_frame_analyzing_results="",
                video_analyzing_results="",
                prompt=temp_prompt_file
            )
            logger.info("Successfully used remote API for instruction expansion")
        except Exception as e:
            logger.warning(f"Remote API call failed for instruction expansion: {str(e)}")
            logger.info("Falling back to local model for instruction expansion")
            
            # Fallback to local model
            expanded_text = generate_response(
                prompt=formatted_prompt,
                max_tokens=1024,
                temperature=0.7,
                verbose=True
            )
    
    finally:
        # Clean up the temporary file
        if temp_prompt_path.exists():
            os.remove(temp_prompt_path)
    
    logger.info(f"Expanded text (length: {len(expanded_text)} chars, ~{len(expanded_text.split())} words)")
    return expanded_text

def split_text_into_segments(text: str, background: str = "") -> List[Dict[str, str]]:
    """
    Split text into meaningful segments using LLM and generate video descriptions for each segment.
    
    Args:
        text: Text to split
        background: Background information to consider (optional)
        
    Returns:
        List of dictionaries containing segment text and corresponding video description
    """
    logger.info(f"Splitting text into meaningful segments and generating descriptions")
    
    # Load the prompt template
    current_dir = Path(__file__).resolve().parent
    project_root = current_dir.parent
    prompt_path = project_root / "config/prompts/split_text.md"
    
    if not prompt_path.exists():
        logger.error(f"Prompt file not found: {prompt_path}")
        raise FileNotFoundError(f"Required prompt file not found: {prompt_path}")
    
    with open(prompt_path, "r", encoding="utf-8") as f:
        prompt_template = f.read()
    
    # Format the prompt
    formatted_prompt = prompt_template.format(
        background=background if background else "无特定背景要求",
        text=text
    )
    
    # Create a temporary prompt file for the API call
    temp_prompt_file = f"split_text_temp_{int(time.time())}.md"
    temp_prompt_path = project_root / "config/prompts" / temp_prompt_file
    
    # Ensure the directory exists
    os.makedirs(os.path.dirname(temp_prompt_path), exist_ok=True)
    
    try:
        # Write the prompt to a temporary file
        with open(temp_prompt_path, "w", encoding="utf-8") as f:
            f.write(formatted_prompt)
        
        # Try to use the remote API first
        try:
            response_content = route_providers(
                provider=None,  # Try all providers by priority
                meta_data="",
                duration="",
                transcript="",
                key_frame_analyzing_results="",
                video_analyzing_results="",
                prompt=temp_prompt_file
            )
            logger.info("Successfully used remote API for text segmentation")
        except Exception as e:
            logger.warning(f"Remote API call failed for text segmentation: {str(e)}")
            logger.info("Falling back to local model for text segmentation")
            
            # Fallback to local model
            response_content = generate_response(
                prompt=formatted_prompt,
                max_tokens=4096,
                temperature=0.7,
                verbose=True
            )
    
    finally:
        # Clean up the temporary file
        if temp_prompt_path.exists():
            os.remove(temp_prompt_path)
    
    # Extract JSON from response
    try:
        # Find JSON array in the response
        import re
        json_match = re.search(r'\[\s*\{.*\}\s*\]', response_content, re.DOTALL)
        if json_match:
            response_content = json_match.group(0)
        
        segments_with_descriptions = json.loads(response_content)
        logger.info(f"Successfully split text into {len(segments_with_descriptions)} segments with descriptions")
        
        # Validate the structure
        for item in segments_with_descriptions:
            if "segment" not in item or "description" not in item:
                logger.warning("Invalid segment structure detected, missing required fields")
                raise ValueError("Invalid segment structure")
        
        return segments_with_descriptions
    except Exception as e:
        logger.error(f"Error parsing LLM response: {str(e)}")
        logger.error(f"Raw response: {response_content}")
        
        # Fallback: Try to extract segments manually
        logger.info("Attempting fallback segmentation")
        
        # Simple fallback: split by sentences and generate descriptions separately
        from nltk.tokenize import sent_tokenize
        try:
            import nltk
            nltk.download('punkt', quiet=True)
            sentences = sent_tokenize(text)
            
            # Group sentences into reasonable segments (e.g., 1-3 sentences per segment)
            fallback_segments = []
            current_segment = ""
            
            for sentence in sentences:
                if len(current_segment) > 0 and len(current_segment) + len(sentence) > 200:
                    fallback_segments.append(current_segment)
                    current_segment = sentence
                else:
                    if current_segment:
                        current_segment += " " + sentence
                    else:
                        current_segment = sentence
            
            if current_segment:
                fallback_segments.append(current_segment)
            
            # Generate descriptions for each segment
            segments_with_descriptions = []
            for segment in fallback_segments:
                description = generate_video_description(segment, background)
                segments_with_descriptions.append({
                    "segment": segment,
                    "description": description
                })
            
            logger.info(f"Fallback segmentation created {len(segments_with_descriptions)} segments")
            return segments_with_descriptions
            
        except Exception as fallback_error:
            logger.error(f"Fallback segmentation failed: {str(fallback_error)}")
            # Last resort: return the whole text as one segment
            description = generate_video_description(text, background)
            return [{
                "segment": text,
                "description": description
            }]

def generate_video_description(text_segment: str, background: str = "") -> str:
    """
    Generate a video description from a text segment
    
    Args:
        text_segment: Text segment to generate description for
        background: Background information to consider (optional)
        
    Returns:
        Video description
    """
    logger.info(f"Generating video description for segment: {text_segment[:50]}...")
    
    # Load the prompt template
    current_dir = Path(__file__).resolve().parent
    project_root = current_dir.parent
    prompt_path = project_root / "config/prompts/generate_description.md"
    
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    
    with open(prompt_path, "r", encoding="utf-8") as f:
        prompt_template = f.read()
    
    # Format the prompt
    formatted_prompt = prompt_template.format(
        background=background if background else "无特定背景要求",
        text_segment=text_segment
    )
    
    # Create a temporary prompt file for the API call
    temp_prompt_file = f"description_temp_{int(time.time())}.md"
    temp_prompt_path = project_root / "config/prompts" / temp_prompt_file
    
    # Ensure the directory exists
    os.makedirs(os.path.dirname(temp_prompt_path), exist_ok=True)
    
    try:
        # Write the prompt to a temporary file
        with open(temp_prompt_path, "w", encoding="utf-8") as f:
            f.write(formatted_prompt)
        
        # Try to use the remote API first
        try:
            description = route_providers(
                provider=None,  # Try all providers by priority
                meta_data="",
                duration="",
                transcript="",
                key_frame_analyzing_results="",
                video_analyzing_results="",
                prompt=temp_prompt_file
            )
            logger.info("Successfully used remote API for video description generation")
        except Exception as e:
            logger.warning(f"Remote API call failed for video description generation: {str(e)}")
            logger.info("Falling back to local model for video description generation")
            
            # Fallback to local model
            description = generate_response(
                prompt=formatted_prompt,
                max_tokens=1024,
                temperature=0.7,
                verbose=True
            )
    
    finally:
        # Clean up the temporary file
        if temp_prompt_path.exists():
            os.remove(temp_prompt_path)
    
    logger.info(f"Generated description (length: {len(description)} chars)")
    return description

def find_similar_videos(description: str, query_system: VideoQuerySystem, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Find videos similar to the description
    
    Args:
        description: Video description to search for
        query_system: VideoQuerySystem instance
        limit: Maximum number of results to return (default: 5, can be higher for filtering)
        
    Returns:
        List of similar videos
    """
    logger.info(f"Finding videos similar to: {description[:50]}... (limit: {limit})")
    
    # Search for similar videos - request more results to allow for filtering
    search_limit = max(limit * 3, 30)  # Request at least 30 results to have enough for filtering
    results = query_system.search_videos(description)
    
    logger.info(f"Found {len(results)} videos matching the description")
    return results[:limit]

def similarity_search_worker(segment_info, query_system, output_lock, used_similar_videos):
    """
    Worker function for finding similar videos for a text segment
    
    Args:
        segment_info: Dictionary containing segment information
        query_system: VideoQuerySystem instance
        output_lock: Lock for thread-safe file operations
        used_similar_videos: Set to track used similar videos
    """
    import traceback
    
    segment_index = segment_info["index"]
    segment_text = segment_info["text"]
    segment_description = segment_info["description"]
    segment_dir = segment_info["dir"]
    
    logger.info(f"Thread starting similarity search for segment {segment_index}")
    
    try:
        # Find similar videos based on the pre-generated description
        all_similar_videos = find_similar_videos(segment_description, query_system, limit=20)  # Get more results to filter
        
        # Filter out already used videos
        filtered_similar_videos = []
        with output_lock:  # Lock to safely access the shared set
            for video in all_similar_videos:
                video_path = video.get("video_path", "Unknown")
                # Skip if this video has already been used in another segment
                if video_path in used_similar_videos:
                    logger.info(f"Skipping duplicate similar video: {video_path}")
                    continue
                
                # Add to filtered list and mark as used
                filtered_similar_videos.append(video)
                used_similar_videos.add(video_path)
                
                # Stop once we have 5 unique videos
                if len(filtered_similar_videos) >= 5:
                    break
        
        # If we couldn't find 5 unique videos, log a warning
        if len(filtered_similar_videos) < 5:
            logger.warning(f"Could only find {len(filtered_similar_videos)} unique similar videos for segment {segment_index}")
        
        # Use lock for file operations to avoid conflicts
        with output_lock:
            # Save segment text and description
            with open(os.path.join(segment_dir, "segment_text.txt"), "w", encoding="utf-8") as f:
                f.write(segment_text)
            
            with open(os.path.join(segment_dir, "description.txt"), "w", encoding="utf-8") as f:
                f.write(segment_description)
                
                # Add similar videos information
                for j, video in enumerate(filtered_similar_videos, 1):
                    f.write(f"\n\nSimilar Video {j}:\n")
                    f.write(f"Path: {video.get('video_path', 'Unknown')}\n")
                    f.write(f"Similarity Score: {video.get('combined_score', video.get('description_score', 0))}\n")
                    f.write(f"Description: {video.get('description', video.get('document', 'No description'))}\n")
            
            # Save similar videos
            for j, video in enumerate(filtered_similar_videos, 1):
                video_info = {
                    "video_path": video.get("video_path", "Unknown"),
                    "similarity_score": video.get("combined_score", video.get("description_score", 0)),
                    "description": video.get("description", video.get("document", "No description")),
                    "metadata": video.get("metadata", {})
                }
                
                # Save the full video_info as JSON for reference
                with open(os.path.join(segment_dir, f"similar_{j}.json"), "w", encoding="utf-8") as f:
                    json.dump(video_info, f, ensure_ascii=False, indent=2)
                
                # Copy the similar video to the segment directory with a new name
                similar_video_path = video_info["video_path"]
                if similar_video_path != "Unknown" and os.path.exists(similar_video_path):
                    try:
                        # Create a subdirectory for similar videos
                        similar_videos_dir = os.path.join(segment_dir, "similar_videos")
                        os.makedirs(similar_videos_dir, exist_ok=True)
                        
                        # Generate a unique filename for the similar video
                        similar_video_filename = f"similar_{j}.mp4"
                        target_path = os.path.join(similar_videos_dir, similar_video_filename)
                        
                        # Copy the similar video
                        logger.info(f"Copying similar video from {similar_video_path} to {target_path}")
                        shutil.copy2(similar_video_path, target_path)
                        logger.info(f"Successfully copied similar video {j}")
                    except Exception as e:
                        logger.error(f"Failed to copy similar video {j}: {str(e)}")
                        logger.error(traceback.format_exc())
        
        logger.info(f"Thread completed similarity search for segment {segment_index}")
    except Exception as e:
        logger.error(f"Error in similarity search thread for segment {segment_index}: {str(e)}")
        logger.error(traceback.format_exc())

def process_text(text: str, output_dir: str, max_threads: int = 10, background: str = "") -> None:
    """
    Main function to process text and find similar videos
    
    Args:
        text: Text to process
        output_dir: Output directory
        max_threads: Maximum number of threads for parallel processing
        background: Background information to consider when generating descriptions
    """
    logger.info(f"Processing text (length: {len(text)} chars)")
    logger.info(f"Output directory: {output_dir}")
    logger.info(f"Using up to {max_threads} threads for parallel processing")
    logger.info(f"Background information: {background[:50]}..." if len(background) > 50 else f"Background information: {background}")
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Save the original text and background
    with open(os.path.join(output_dir, "original_text.txt"), "w", encoding="utf-8") as f:
        f.write(text)
    
    if background:
        with open(os.path.join(output_dir, "background_info.txt"), "w", encoding="utf-8") as f:
            f.write(background)
    
    # Split text into segments and get descriptions
    segments_with_descriptions = split_text_into_segments(text, background)
    
    # Save all segments to a single file for reference
    with open(os.path.join(output_dir, "all_segments.txt"), "w", encoding="utf-8") as f:
        f.write(f"背景信息：{background}\n\n" if background else "")
        for i, segment_info in enumerate(segments_with_descriptions, 1):
            f.write(f"片段 {i}:\n")
            f.write(f"文本: {segment_info['segment']}\n")
            f.write(f"描述: {segment_info['description']}\n\n")
    
    # Initialize database and query system
    project_root = Path(__file__).resolve().parent.parent
    db_dir = os.path.join(project_root, "db", "data")
    db = VideoDatabase(
        db_path=os.path.join(db_dir, "video_processing.db"),
        chroma_path=os.path.join(db_dir, "chroma_db")
    )
    
    query_system = VideoQuerySystem(
        db_path=os.path.join(db_dir, "video_processing.db"),
        chroma_path=os.path.join(db_dir, "chroma_db")
    )
    
    # Create a lock for thread-safe file operations
    output_lock = Lock()
    
    # Create a shared set to track used similar videos (for preventing duplicates)
    used_similar_videos = set()
    
    # Create a thread pool executor
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_threads) as executor:
        try:
            # List to store futures for segment processing tasks
            segment_futures = []
            
            # Process each segment
            for i, segment_info in enumerate(segments_with_descriptions, 1):
                # Create segment directory
                segment_dir = os.path.join(output_dir, f"segment{i}_folder")
                os.makedirs(segment_dir, exist_ok=True)
                
                # Prepare segment info for the worker thread
                worker_segment_info = {
                    "index": i,
                    "text": segment_info["segment"],
                    "description": segment_info["description"],
                    "dir": segment_dir
                }
                
                # Submit segment processing task to thread pool
                logger.info(f"Submitting segment {i} processing task to thread pool")
                future = executor.submit(similarity_search_worker, worker_segment_info, query_system, output_lock, used_similar_videos)
                segment_futures.append(future)
            
            # Wait for all segment processing tasks to complete
            logger.info(f"Waiting for {len(segment_futures)} segment processing tasks to complete")
            concurrent.futures.wait(segment_futures)
            logger.info("All segment processing tasks completed")
            
            # Check for exceptions in the futures
            for i, future in enumerate(segment_futures):
                try:
                    # This will re-raise any exception that occurred in the thread
                    future.result()
                except Exception as e:
                    logger.error(f"Exception in segment processing task {i+1}: {str(e)}")
        
        finally:
            # Close database connections
            db.close()
            query_system.close()
    
    logger.info(f"Text processing complete. Results saved to: {output_dir}")

def main():
    """Parse command line arguments and run the script"""
    parser = argparse.ArgumentParser(description="Find similar videos based on text input")
    parser.add_argument("--text", help="Text input (lyrics, instructions, etc.)")
    parser.add_argument("--text_file", required=True, help="Path to a text file containing input")
    parser.add_argument("--output_dir", required=True, help="Directory to save results")
    parser.add_argument("--max_threads", type=int, default=10, help="Maximum number of threads for parallel processing (default: 10)")
    parser.add_argument("--is_instruction", action="store_true", help="Treat input as an instruction to be expanded")
    parser.add_argument("--target_duration", type=int, default=25, help="Target duration in seconds for expanded instructions (default: 25)")
    parser.add_argument("--background", help="Background information to consider when generating descriptions")
    
    args = parser.parse_args()
    
    # Check if either text or text_file is provided
    if not args.text and not args.text_file:
        print("Error: Either --text or --text_file must be provided")
        sys.exit(1)
    
    # Get text from file if provided
    if args.text_file:
        if not os.path.exists(args.text_file):
            print(f"Error: Text file not found: {args.text_file}")
            sys.exit(1)
        
        with open(args.text_file, "r", encoding="utf-8") as f:
            text = f.read().strip()
    else:
        text = args.text
    
    # Get background information
    background = args.background or ""
    
    # Expand text if it's an instruction
    if args.is_instruction:
        print(f"Expanding instruction to text (target duration: {args.target_duration}s)")
        text = expand_instruction_to_text(text, target_duration=args.target_duration, background=background)
        print(f"Expanded text (length: {len(text)} chars, ~{len(text.split())} words)")
    
    # Process text
    process_text(
        text, 
        args.output_dir, 
        args.max_threads,
        background
    )
    
    print(f"Processing complete. Results saved to: {args.output_dir}")

if __name__ == "__main__":
    main() 