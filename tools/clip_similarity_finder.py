#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Clip Similarity Finder

This script:
1. Takes a video file as input
2. Performs scene detection to split it into clips
3. Analyzes each clip to generate descriptions
4. Finds similar videos in the database for each clip
5. Saves the results to a target directory structure

Usage:
    python tools/clip_similarity_finder.py --video_path <path_to_video> --output_dir <output_directory> [--threshold 27] [--min_duration 0.6]
"""

import os
import sys
import argparse
import shutil
from pathlib import Path
import numpy as np
import logging
from typing import List, Dict, Tuple, Any
import tempfile
import json
import threading
import queue
import concurrent.futures
from threading import Lock

# Add parent directory to path to allow imports when running from tools directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Scene detection imports
from scenedetect import SceneManager, open_video
from scenedetect.detectors import ContentDetector
from scenedetect import frame_timecode

# Video processing imports
from decord import VideoReader, cpu
from PIL import Image

# Database imports
from db import VideoDatabase
from modules.video_query import VideoQuerySystem
from utils.log_config import setup_logger

# Set up logging
logger = setup_logger(__name__)

def detect_scenes(video_path: str, threshold: float = 27, min_scene_duration: float = 0.6) -> List[Tuple]:
    """
    Detect scenes in a video using the ContentDetector
    
    Args:
        video_path: Path to the video file
        threshold: ContentDetector threshold (higher = fewer scenes)
        min_scene_duration: Minimum scene duration in seconds
        
    Returns:
        List of (start_timecode, end_timecode) tuples
    """
    logger.info(f"Detecting scenes in {video_path} with threshold={threshold}, min_duration={min_scene_duration}")
    
    # Open video
    video_stream = open_video(video_path)
    
    # Create scene manager and add detector
    scene_manager = SceneManager()
    scene_manager.add_detector(ContentDetector(threshold=threshold))
    
    # Detect scenes
    scene_manager.detect_scenes(video=video_stream)
    raw_scenes = scene_manager.get_scene_list()
    
    # Filter scenes by duration
    scenes = []
    for start, end in raw_scenes:
        duration = end.get_seconds() - start.get_seconds()
        if duration >= min_scene_duration:
            scenes.append((start, end))
    
    logger.info(f"Detected {len(scenes)} scenes")
    for i, (start, end) in enumerate(scenes):
        duration = end.get_seconds() - start.get_seconds()
        logger.info(f"Scene {i+1}: {start.get_timecode()} → {end.get_timecode()} (duration: {duration:.2f}s)")
    
    return scenes

def extract_clip(video_path: str, start_timecode, end_timecode, output_path: str) -> bool:
    """
    Extract a clip from a video using ffmpeg
    
    Args:
        video_path: Path to the source video
        start_timecode: Start timecode
        end_timecode: End timecode
        output_path: Path to save the extracted clip
        
    Returns:
        True if successful, False otherwise
    """
    import subprocess
    
    start_time = start_timecode.get_timecode()
    duration = end_timecode.get_seconds() - start_timecode.get_seconds()
    
    try:
        # Use a different approach to avoid black frames:
        # 1. Put -ss before -i for faster seeking
        # 2. Use -accurate_seek for more precise seeking
        # 3. Avoid using copy codecs which can cause keyframe issues
        cmd = [
            "ffmpeg",
            "-ss", start_time,
            "-i", video_path,
            "-t", str(duration),
            "-avoid_negative_ts", "1",
            "-preset", "ultrafast",  # For faster encoding
            "-crf", "23",  # Reasonable quality
            output_path,
            "-y"  # Overwrite if exists
        ]
        
        logger.info(f"Extracting clip with command: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logger.debug(f"FFmpeg stderr: {result.stderr.decode('utf-8', errors='ignore')}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Error extracting clip: {e}")
        logger.error(f"FFmpeg stderr: {e.stderr.decode('utf-8', errors='ignore') if e.stderr else 'No error output'}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error extracting clip: {e}")
        return False

def get_middle_frame(video_path: str, start_timecode, end_timecode) -> Image.Image:
    """
    Get the middle frame of a video clip
    
    Args:
        video_path: Path to the video file
        start_timecode: Start timecode
        end_timecode: End timecode
        
    Returns:
        PIL Image of the middle frame
    """
    vr = VideoReader(video_path, ctx=cpu(0))
    fps = vr.get_avg_fps()
    
    start_sec = start_timecode.get_seconds()
    end_sec = end_timecode.get_seconds()
    
    # Calculate middle time (seconds)
    mid_sec = (start_sec + end_sec) / 2
    
    # Calculate frame number based on fps
    mid_frame = int(mid_sec * fps)
    
    # Ensure frame number doesn't exceed video length
    if mid_frame >= len(vr):
        mid_frame = len(vr) - 1
    
    frame = vr[mid_frame].asnumpy()
    return Image.fromarray(frame)

def analyze_clip(clip_path: str, db: VideoDatabase) -> Dict[str, Any]:
    """
    Analyze a video clip to generate a comprehensive description
    
    This function performs multiple analyses similar to process_single_video:
    1. Process audio (extract and transcribe)
    2. Extract and analyze key frame
    3. Analyze video content (motion, etc.)
    4. Combine all results using a reasoning model
    
    Args:
        clip_path: Path to the video clip
        db: VideoDatabase instance (used only for its configuration)
        
    Returns:
        Dictionary with combined analysis results
    """
    import time
    import traceback
    from modules.call_sensevoice import process_audio
    from modules.key_frame_analyzer import analyze_key_frame
    from modules.video_analyzer import analyze_video_content
    from modules.call_reasoner import route_providers
    from utils.utility import extract_json
    from utils.ffmpeg_funs import extract_representative_frame
    
    logger.info(f"Performing comprehensive analysis of clip: {clip_path}")
    base = os.path.splitext(clip_path)[0]
    
    # Initialize result variables
    transcript = ""
    duration = 0
    result_key_frame = {}
    result_video = {}
    combined_result = None
    
    # 1. Process audio (extract and transcribe)
    logger.info("1. Processing audio...")
    time_start1 = time.time()
    try:
        transcript = process_audio(clip_path)
        audio_time = time.time() - time_start1
        logger.info(f"Audio processing time: {audio_time:.2f} seconds")
    except Exception as e:
        logger.error(f"Error processing audio: {str(e)}")
        logger.error(traceback.format_exc())
        transcript = "Audio processing failed."
    
    # 2. Extract key frame
    logger.info("2. Extracting key frame...")
    time_start2 = time.time()
    temp_image = base + "_keyframe.jpg"
    key_frame_extracted = False
    try:
        key_frame_extracted, duration = extract_representative_frame(clip_path, temp_image)
        logger.info(f"Key frame extraction time: {time.time() - time_start2:.2f} seconds")
    except Exception as e:
        logger.error(f"Error extracting key frame: {str(e)}")
        logger.error(traceback.format_exc())
        duration = 0  # Unable to get duration
    
    # 3. Analyze key frame
    if not key_frame_extracted or not os.path.exists(temp_image) or os.path.getsize(temp_image) == 0:
        logger.warning("Key frame extraction failed or produced an empty image")
        result_key_frame = {"answer": "Failed to analyze key frame"}
    else:
        logger.info("3. Analyzing key frame...")
        time_start3 = time.time()
        try:
            result_key_frame = analyze_key_frame(temp_image)
            key_frame_time = time.time() - time_start3
            logger.info(f"Key frame analysis time: {key_frame_time:.2f} seconds")
        except Exception as e:
            logger.error(f"Error analyzing key frame: {str(e)}")
            logger.error(traceback.format_exc())
            result_key_frame = {"answer": "Failed to analyze key frame"}
    
    # Delete temporary image regardless of success or failure
    if os.path.exists(temp_image):
        os.remove(temp_image)
    
    # 4. Analyze video
    logger.info("4. Analyzing video...")
    time_start4 = time.time()
    try:
        result_video = analyze_video_content(clip_path)
        video_time = time.time() - time_start4
        logger.info(f"Video analysis time: {video_time:.2f} seconds")
    except Exception as e:
        logger.error(f"Error in video analysis: {str(e)}")
        logger.error(traceback.format_exc())
        result_video = {"answer": "Video analysis failed"}
    
    # 5. Combine all analysis results
    logger.info("5. Combining analysis results...")
    try:
        # Use empty string for meta_data
        meta_data = ""
        # 使用项目根目录路径
        project_root = Path(__file__).resolve().parent.parent
        prompt_path = "combine_video_image_results.md"
        
        combined_result = route_providers(
            None,  # No specific provider, try by priority
            meta_data,
            duration,
            transcript,
            result_key_frame,
            result_video,
            prompt_path
        )
        combined_result = extract_json(combined_result)
    except Exception as e:
        logger.error(f"Error combining analysis results: {str(e)}")
        logger.error(traceback.format_exc())
        # Create a simple combined result if the combination fails
        combined_result = {
            "answer": "Failed to combine analysis results. Individual analyses available.",
            "key_frame_analysis": result_key_frame.get("answer", "No key frame analysis"),
            "video_analysis": result_video.get("answer", "No video analysis"),
            "transcript": transcript[:500] + "..." if len(transcript) > 500 else transcript
        }
    
    return combined_result

def find_similar_videos(description: str, min_duration: float, query_system: VideoQuerySystem, limit: int = 5, background: str = "") -> List[Dict[str, Any]]:
    """
    Find videos similar to the description with duration >= min_duration
    
    Args:
        description: Video description to search for
        min_duration: Minimum duration in seconds
        query_system: VideoQuerySystem instance
        limit: Maximum number of results to return (default: 5, can be higher for filtering)
        background: Background information to consider when searching (optional)
        
    Returns:
        List of similar videos
    """
    logger.info(f"Finding videos similar to: {description[:50]}... (limit: {limit})")
    
    # If background is provided, enhance the description with it
    if background:
        enhanced_description = f"{background}. {description}"
        logger.info(f"Enhanced description with background: {enhanced_description[:50]}...")
    else:
        enhanced_description = description
    
    # Search for similar videos - request more results to allow for filtering
    search_limit = max(limit * 3, 30)  # Request at least 30 results to have enough for filtering
    results = query_system.search_videos(enhanced_description)
    
    # Filter by duration
    filtered_results = []
    for result in results:
        # Get duration from metadata if available
        duration = None
        if 'metadata' in result and 'duration' in result['metadata']:
            try:
                duration = float(result['metadata']['duration'])
            except (ValueError, TypeError):
                pass
        
        # If duration is available and meets minimum requirement, add to filtered results
        if duration is not None and duration >= min_duration:
            filtered_results.append(result)
            
            # Break if we have enough results
            if len(filtered_results) >= search_limit:
                break
    
    logger.info(f"Found {len(filtered_results)} videos with duration >= {min_duration}s")
    return filtered_results[:limit]

def verify_clip(clip_path: str) -> bool:
    """
    Verify that a clip was extracted correctly and contains valid video data
    
    Args:
        clip_path: Path to the clip file
        
    Returns:
        True if the clip is valid, False otherwise
    """
    import subprocess
    
    if not os.path.exists(clip_path) or os.path.getsize(clip_path) == 0:
        logger.error(f"Clip file does not exist or is empty: {clip_path}")
        return False
    
    try:
        # Use ffprobe to check if the video is valid
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_type",
            "-of", "json",
            clip_path
        ]
        
        result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output = json.loads(result.stdout)
        
        # Check if there's a valid video stream
        if "streams" in output and len(output["streams"]) > 0:
            return True
        else:
            logger.error(f"No valid video stream found in clip: {clip_path}")
            return False
    except subprocess.CalledProcessError as e:
        logger.error(f"Error verifying clip: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error verifying clip: {e}")
        return False

def similarity_search_worker(clip_info, query_system, output_lock, used_similar_videos):
    """
    Worker function for similarity search to be run in a separate thread
    
    Args:
        clip_info: Dictionary containing clip information
        query_system: VideoQuerySystem instance
        output_lock: Lock for thread-safe file operations
        used_similar_videos: Set to track used similar videos
    """
    import traceback
    
    clip_index = clip_info["index"]
    clip_path = clip_info["path"]
    clip_dir = clip_info["dir"]
    description = clip_info["description"]
    duration = clip_info["duration"]
    analysis_result = clip_info["analysis"]
    background = clip_info.get("background", "")
    
    logger.info(f"Thread starting similarity search for clip {clip_index}")
    
    try:
        # Find similar videos
        all_similar_videos = find_similar_videos(description, duration, query_system, limit=20, background=background)  # Get more results to filter
        
        # Filter out already used videos
        filtered_similar_videos = []
        with output_lock:  # Lock to safely access the shared set
            for video in all_similar_videos:
                video_path = video.get("video_path", "Unknown")
                # Skip if this video has already been used in another clip
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
            logger.warning(f"Could only find {len(filtered_similar_videos)} unique similar videos for clip {clip_index}")
        
        # Use lock for file operations to avoid conflicts
        with output_lock:
            # Save similar videos
            for j, video in enumerate(filtered_similar_videos, 1):
                video_info = {
                    "video_path": video.get("video_path", "Unknown"),
                    "similarity_score": video.get("combined_score", video.get("description_score", 0)),
                    "description": video.get("description", video.get("document", "No description")),
                    "metadata": video.get("metadata", {})
                }
                
                # Write video_info to description.txt
                with open(os.path.join(clip_dir, "description.txt"), "a", encoding="utf-8") as f:
                    f.write(f"\n\nSimilar Video {j}:\n")
                    f.write(f"Path: {video_info['video_path']}\n")
                    f.write(f"Similarity Score: {video_info['similarity_score']}\n")
                    f.write(f"Description: {video_info['description']}\n")
                
                # Save the full video_info as JSON for reference
                with open(os.path.join(clip_dir, f"similar_{j}.json"), "w", encoding="utf-8") as f:
                    json.dump(video_info, f, ensure_ascii=False, indent=2)
                
                # Copy the similar video to the clip directory with a new name
                similar_video_path = video_info["video_path"]
                if similar_video_path != "Unknown" and os.path.exists(similar_video_path):
                    try:
                        # Create a subdirectory for similar videos to avoid confusion with original clips
                        similar_videos_dir = os.path.join(clip_dir, "similar_videos")
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
        
        logger.info(f"Thread completed similarity search for clip {clip_index}")
    except Exception as e:
        logger.error(f"Error in similarity search thread for clip {clip_index}: {str(e)}")
        logger.error(traceback.format_exc())

def process_video(video_path: str, output_dir: str, threshold: float = 27, min_duration: float = 0.6, max_threads: int = 10, background: str = "") -> None:
    """
    Main function to process a video
    
    Args:
        video_path: Path to the video file
        output_dir: Output directory
        threshold: Scene detection threshold
        min_duration: Minimum scene duration in seconds
        max_threads: Maximum number of threads for similarity search
        background: Background information to consider when searching (optional)
    """
    # Ensure we have the absolute path to the original video
    original_video_path = os.path.abspath(video_path)
    logger.info(f"Processing video: {original_video_path}")
    logger.info(f"Output directory: {output_dir}")
    logger.info(f"Using up to {max_threads} threads for similarity search")
    if background:
        logger.info(f"Background information: {background[:50]}..." if len(background) > 50 else f"Background information: {background}")
    
    # Save background information if provided
    if background:
        os.makedirs(output_dir, exist_ok=True)
        with open(os.path.join(output_dir, "background_info.txt"), "w", encoding="utf-8") as f:
            f.write(background)
    
    # Verify that the input video exists and is a valid video file
    if not os.path.exists(original_video_path):
        logger.error(f"Input video file does not exist: {original_video_path}")
        return
    
    # Check if the input path contains "similar_" which would indicate a potential issue
    if "similar_" in original_video_path:
        logger.warning(f"Input video path contains 'similar_', which may indicate a potential issue: {original_video_path}")
        user_input = input("The input video path contains 'similar_'. Continue anyway? (y/n): ")
        if user_input.lower() != 'y':
            logger.info("Operation cancelled by user")
            return
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
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
            # Detect scenes
            scenes = detect_scenes(original_video_path, threshold, min_duration)
            
            if not scenes:
                logger.warning("No scenes detected in the video")
                return
            
            # List to store futures for similarity search tasks
            similarity_futures = []
            
            # Process each scene
            for i, (start, end) in enumerate(scenes, 1):
                # Calculate duration
                duration = end.get_seconds() - start.get_seconds()
                
                # Create clip directory
                clip_dir = os.path.join(output_dir, f"clip{i}_folder")
                os.makedirs(clip_dir, exist_ok=True)
                
                # Extract clip directly to output folder
                clip_path = os.path.join(clip_dir, f"origin_scene_{i}.mp4")
                
                # Always extract from the original input video - use the absolute path
                extraction_success = extract_clip(original_video_path, start, end, clip_path)
                
                # If extraction failed, skip this clip
                if not extraction_success:
                    logger.error(f"Failed to extract clip {i}, skipping")
                    continue
                
                # Analyze clip (this part remains sequential)
                logger.info(f"Starting analysis for clip {i}")
                analysis_result = analyze_clip(clip_path, db)
                
                # Get description from analysis result
                try:
                    # Try to parse the analysis result as JSON if it's a string
                    if isinstance(analysis_result, str):
                        analysis_json = json.loads(analysis_result)
                    else:
                        analysis_json = analysis_result
                    
                    # Extract the description field - try different possible field names
                    description = analysis_json.get("answer", 
                                  analysis_json.get("description", 
                                  analysis_json.get("content", "No description available")))
                    
                    # If description is still not found, use a fallback approach
                    if description == "No description available" and isinstance(analysis_json, dict):
                        # Look for any field that might contain a description
                        for key in ["video_description", "scene_description", "summary", "text"]:
                            if key in analysis_json and analysis_json[key]:
                                description = analysis_json[key]
                                break
                except Exception as e:
                    logger.warning(f"Failed to extract description from analysis result: {str(e)}")
                    description = "No description available"
                
                # Save description and full analysis (use lock for thread safety)
                with output_lock:
                    with open(os.path.join(clip_dir, "description.txt"), "w", encoding="utf-8") as f:
                        f.write(description)
                    
                    # Save the full analysis result as JSON for reference
                    with open(os.path.join(clip_dir, "full_analysis.json"), "w", encoding="utf-8") as f:
                        json.dump(analysis_result, f, ensure_ascii=False, indent=2)
                
                # Prepare clip info for the similarity search thread
                clip_info = {
                    "index": i,
                    "path": clip_path,
                    "dir": clip_dir,
                    "description": description,
                    "duration": duration,
                    "analysis": analysis_result,
                    "background": background
                }
                
                # Submit similarity search task to thread pool
                logger.info(f"Submitting similarity search task for clip {i} to thread pool")
                future = executor.submit(similarity_search_worker, clip_info, query_system, output_lock, used_similar_videos)
                similarity_futures.append(future)
                
                logger.info(f"Completed analysis for clip {i}, similarity search running in background")
            
            # Wait for all similarity search tasks to complete
            logger.info(f"Waiting for {len(similarity_futures)} similarity search tasks to complete")
            concurrent.futures.wait(similarity_futures)
            logger.info("All similarity search tasks completed")
            
            # Check for exceptions in the futures
            for i, future in enumerate(similarity_futures):
                try:
                    # This will re-raise any exception that occurred in the thread
                    future.result()
                except Exception as e:
                    logger.error(f"Exception in similarity search task {i+1}: {str(e)}")
        
        finally:
            # Close database connections
            db.close()
            query_system.close()

def main():
    """Parse command line arguments and run the script"""
    parser = argparse.ArgumentParser(description="Find similar videos for each clip in a video")
    parser.add_argument("--video_path", required=True, help="Path to the input video file")
    parser.add_argument("--output_dir", required=True, help="Directory to save results")
    parser.add_argument("--threshold", type=float, default=27, help="Scene detection threshold (default: 27)")
    parser.add_argument("--min_duration", type=float, default=0.6, help="Minimum scene duration in seconds (default: 0.6)")
    parser.add_argument("--max_threads", type=int, default=10, help="Maximum number of threads for similarity search (default: 10)")
    parser.add_argument("--background", help="Background information to consider when searching for similar videos")
    
    args = parser.parse_args()
    
    # Check if video file exists
    if not os.path.exists(args.video_path):
        print(f"Error: Video file not found: {args.video_path}")
        sys.exit(1)
    
    # Check if the input path contains "similar_" which would indicate a potential issue
    if "similar_" in args.video_path:
        print(f"Warning: Input video path contains 'similar_', which may indicate a potential issue: {args.video_path}")
        user_input = input("The input video path contains 'similar_'. Continue anyway? (y/n): ")
        if user_input.lower() != 'y':
            print("Operation cancelled by user")
            sys.exit(0)
    
    # Process video
    process_video(args.video_path, args.output_dir, args.threshold, args.min_duration, args.max_threads, args.background)

if __name__ == "__main__":
    main() 