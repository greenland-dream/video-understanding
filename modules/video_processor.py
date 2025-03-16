import os, time, traceback
import re
from pathlib import Path
import logging
from utils.log_config import setup_logger
from utils.write_tags import embed_metadata_with_exiftool, write_description
from utils.ffmpeg_funs import extract_representative_frame
from modules.call_reasoner import route_providers
from utils.utility import extract_json
from modules.call_sensevoice import process_audio
from modules.key_frame_analyzer import analyze_key_frame
from modules.video_analyzer import analyze_video_content

logger = setup_logger(__name__)

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

def get_meta_data(video_path):
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

def process_single_video(video_path, db):
    """
    Process a single video file with all analysis steps
    
    Args:
        video_path: Path to the video file
        db: Database instance for checking and storing processing status
    
    Returns:
        bool: True if processing was successful, False otherwise
    """
    try:
        logger.info("------------------------------------------------------------------------------------------------")
        logger.info(f"\nProcessing video: {video_path}")
        base = os.path.splitext(video_path)[0]
        
        # Record processing start time
        process_start_time = time.time()
        
        # Set global processing timeout (15 minutes)
        max_total_processing_time = 900  # seconds
        
        # Initialize result variables
        transcript = ""
        duration = 0
        result_key_frame = {}
        result_video = {}
        meta_data = ""
        combined_result = None
        
        # 1. Process audio (extract and transcribe)
        logger.info("1. Processing audio...")
        time_start1 = time.time()
        try:
            transcript = process_audio(video_path)
            audio_time = time.time() - time_start1
            logger.info(f"Audio processing time: {audio_time:.2f} seconds")
            
        except Exception as e:
            logger.error(f"Error processing audio: {str(e)}")
            logger.error(traceback.format_exc())
            transcript = "Audio processing failed."
            # Even if audio processing fails, we continue with other steps
        
        # 2. Extract key frame
        logger.info("2. Extracting key frame...")
        time_start2 = time.time()
        temp_image = base + "_keyframe.jpg"
        key_frame_extracted = False
        try:
            key_frame_extracted, duration = extract_representative_frame(video_path, temp_image)
            logger.info(f"Key frame extraction time: {time.time() - time_start2:.2f} seconds")
        except Exception as e:
            logger.error(f"Error extracting key frame: {str(e)}")
            logger.error(traceback.format_exc())
            duration = 0  # Unable to get duration
        
        # 3. Analyze key frame
        # Check if key frame extraction was successful
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
            result_video = analyze_video_content(video_path)
            video_time = time.time() - time_start4
            logger.info(f"Video analysis time: {video_time:.2f} seconds")
            
        except Exception as e:
            logger.error(f"Error in video analysis: {str(e)}")
            logger.error(traceback.format_exc())
            result_video = {"answer": "Video analysis failed"}
        
        # 5. Get metadata
        time_start5 = time.time()
        try:
            meta_data = get_meta_data(video_path)
        except FileNotFoundError:
            logger.warning(f"No meta_data.txt found for {video_path}, using empty string")
            meta_data = "User did not provide meta_data"
        except Exception as e:
            logger.error(f"Error getting metadata: {str(e)}")
            logger.error(traceback.format_exc())
            meta_data = "User did not provide meta_data"
        logger.info(f"Metadata retrieval time: {time.time() - time_start5:.2f} seconds")

        # 6. Combine all analysis results   
        logger.info("7. Combining analysis results by calling reasoning model...")
        combined_result = route_providers(
            None,  # No specific provider, try by priority
            meta_data,
            duration,
            transcript,
            result_key_frame,
            result_video,
            "combine_video_image_results.md"
        )
        combined_result = extract_json(combined_result)
            
        
        # 8. Write metadata
        logger.info("8. Writing metadata...")
        isVoiceover, hierarchical_keywords = embed_metadata_with_exiftool(video_path, transcript, combined_result)
        logger.info(f"Hierarchical keywords: {hierarchical_keywords}")
    
        # 9. Write description file
        logger.info("9. Writing description file...")
        write_description(video_path, transcript, hierarchical_keywords, combined_result, isVoiceover, duration)
        
        
        try:
            # 10. Store to vector database
            logger.info("10. Storing to vector database...")
            time_start9 = time.time()
            try:
                db.add_to_vector_db(video_path, combined_result, transcript, meta_data)
            except Exception as e:
                logger.error(f"Error storing to vector database: {str(e)}")
                logger.error(traceback.format_exc())
            logger.info(f"Vector database storage time: {time.time() - time_start9:.2f} seconds")
        except Exception as e:
            logger.error(f"Fatal error storing to vector database: {str(e)}")
            logger.error(traceback.format_exc())
            # Continue processing even if vector database storage fails
        
        # 11. Mark as processed in the database
        logger.info("11. Marking as processed in database...")
        db.mark_video_processed(video_path, combined_result, transcript)
        
        # Record total processing time
        total_processing_time = time.time() - process_start_time
        logger.info(f"Total processing time: {total_processing_time:.2f} seconds")
        
        return True
        
    except Exception as e:
        logger.error(f"Error processing video {video_path}: {str(e)}")
        logger.error(traceback.format_exc())
        # Mark as failed in the database
        db.mark_video_processed(video_path, success=False)
        return False

def process_video_folder_recursive(folder_path, db):
    """
    Recursively collect all videos in folder_path and its subdirectories,
    then process each video. Videos are grouped by directory and sorted by number within each directory.
    
    Args:
        folder_path: Root folder to search for videos
        db: Database instance for tracking processed videos
    """
    # Step 1: Recursively collect all video files
    video_extensions = (".mp4", ".mov", ".avi", ".mkv")
    # Dictionary to store videos by directory
    videos_by_directory = {}
    
    logger.info(f"Scanning directory: {folder_path} for video files...")
    
    for root, dirs, files in os.walk(folder_path):
        video_files_in_dir = []
        for file in files:
            if file.lower().endswith(video_extensions):
                # Skip macOS metadata files (files starting with "._")
                if file.startswith("._"):
                    logger.info(f"Skipping macOS metadata file: {file}")
                    continue
                video_path = os.path.join(root, file)
                video_files_in_dir.append(video_path)
        
        # Only add directories that contain videos
        if video_files_in_dir:
            videos_by_directory[root] = video_files_in_dir
    
    if not videos_by_directory:
        logger.warning(f"No video files found in {folder_path} or its subdirectories.")
        return
    
    total_videos = sum(len(videos) for videos in videos_by_directory.values())
    logger.info(f"Found a total of {total_videos} videos in {len(videos_by_directory)} directories")
    
    # Process videos directory by directory
    processed_count = 0
    skipped_count = 0
    failed_count = 0
    
    # Sort directories by path for consistent processing order
    for directory in sorted(videos_by_directory.keys()):
        videos_in_dir = videos_by_directory[directory]
        # Sort videos within this directory by number
        sorted_videos = sorted(videos_in_dir, key=extract_number)
        
        logger.info(f"Processing directory: {directory} ({len(sorted_videos)} videos)")
        
        # Process each video in this directory
        for video_path in sorted_videos:
            # Check if this video has already been processed
            if db.is_video_processed(video_path):
                logger.info(f"Skipping already processed video: {video_path}")
                skipped_count += 1
                continue
            
            success = process_single_video(video_path, db)
            if success:
                processed_count += 1
            else:
                failed_count += 1
    
    # Summary
    logger.info("------------------------------------------------------------------------------------------------")
    logger.info(f"Processing summary for {folder_path}:")
    logger.info(f"Total videos found: {total_videos}")
    logger.info(f"Videos processed successfully: {processed_count}")
    logger.info(f"Videos skipped (already processed): {skipped_count}")
    logger.info(f"Videos failed: {failed_count}")
    logger.info("------------------------------------------------------------------------------------------------") 