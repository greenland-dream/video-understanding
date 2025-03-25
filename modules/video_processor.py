import os, time, traceback
import re
from pathlib import Path
import logging
from utils.log_config import setup_logger
from utils.write_tags import embed_metadata_with_exiftool, write_description
from utils.ffmpeg_funs import get_video_duration
from modules.call_reasoner import route_providers
from utils.utility import extract_json, extract_number, clear_memory
from modules.audio_processor import process_audio
from modules.video_analyzer import video_query
import gc
import torch

logger = setup_logger(__name__)



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

def analyze_video_content_full(video_path, transcriber, video_understand_model, video_understand_processor):
    """
    Analyze video content and return the results
    
    Args:
        video_path: Path to the video file
        transcriber: Transcription model
        video_understand_model: Video understanding model
        video_understand_processor: Video understanding processor
    
    Returns:
        dict: Analysis results including transcript, duration, result_video, meta_data, combined_result, and if_error flag
    """
    try:
        logger.info("------------------------------------------------------------------------------------------------")
        logger.info(f"\nAnalyzing video content: {video_path}")
        
        # Initialize result variables
        transcript = ""
        meta_data = ""
        combined_result = None
        result_video = {}
        if_error = False
        duration = 0
        
        # Get video duration
        try:
            duration = get_video_duration(video_path)
            logger.info(f"Video duration: {duration:.2f} seconds")
        except Exception as e:
            logger.error(f"Error getting video duration: {str(e)}")
            logger.error(traceback.format_exc())
            if_error = True
            # Continue with other steps even if duration extraction fails
        
        # 1. Process audio (extract and transcribe)
        logger.info("1. Processing audio...")
        time_start1 = time.time()
        try:
            transcript = process_audio(video_path, transcriber)
            audio_time = time.time() - time_start1
            logger.info(f"Audio processing time: {audio_time:.2f} seconds")
            
        except Exception as e:
            logger.error(f"Error processing audio: {str(e)}")
            logger.error(traceback.format_exc())
            transcript = "Audio processing failed."
            if_error = True
            # Even if audio processing fails, we continue with other steps
        time_end1 = time.time()
        logger.info(f"Audio processing time: {time_end1 - time_start1:.2f} seconds")
        
        # Clear memory for audio processing
        clear_memory()

        # 2. Get metadata
        time_start5 = time.time()
        try:
            meta_data = get_meta_data(video_path)   
        except Exception as e:
            logger.error(f"Error getting metadata: {str(e)}")
            logger.error(traceback.format_exc())
            meta_data = "User did not provide meta_data"
            if_error = True
        logger.info(f"Metadata retrieval time: {time.time() - time_start5:.2f} seconds")


        # 3. Analyze video
        logger.info("3. Analyzing video...")
        time_start4 = time.time()
        try:
            # Calculate parameters for video analysis using the simple fixed fps=1 method
            result_video = video_query(video_path, video_understand_model, video_understand_processor, meta_data, duration, transcript, ifresize=False, resize_height=896, resize_width=896)
            logger.info(f"result_video: {result_video}")
        except Exception as e:
            logger.error(f"Error in video analysis: {str(e)}")
            logger.error(traceback.format_exc())
            if_error = True
            result_video = {}
        time_end4 = time.time()
        logger.info(f"3. Video analysis time: {time_end4 - time_start4:.2f} seconds")
   
        # Clear memory for video processing
        clear_memory()

        # 4. Combine all analysis results   
        time_start4 = time.time()
        logger.info("4. Combining analysis results by calling reasoning model...")
        try:
            combined_result = route_providers(
                None,  # No specific provider, try by priority
                meta_data,
                duration,
                transcript,
                result_video,
                "combine_video_image_results.md"
            )
            combined_result = extract_json(combined_result)
            logger.info(f"combined_result: {combined_result}")
        except Exception as e:
            logger.error(f"Error combining analysis results: {str(e)}")
            logger.error(traceback.format_exc())
            combined_result = {}
            if_error = True
        logger.info(f"Combining results time: {time.time() - time_start4:.2f} seconds")
        
        # Return the analysis results
        return {
            "transcript": transcript,
            "duration": duration,
            "result_video": result_video,
            "meta_data": meta_data,
            "combined_result": combined_result,
            "if_error": if_error
        }
        
    except Exception as e:
        logger.error(f"Error analyzing video {video_path}: {str(e)}")
        logger.error(traceback.format_exc())
        return {
            "transcript": "",
            "duration": 0,
            "result_video": {},
            "meta_data": "",
            "combined_result": None,
            "if_error": True
        }

def write_data_to_db(video_path, analysis_results, db):
    """
    Write analysis results to files and database
    
    Args:
        video_path: Path to the video file
        analysis_results: Results from analyze_video_content_full
        db: Database instance for storing processing status
    
    Returns:
        bool: True if writing was successful, False otherwise
    """
    try:
        logger.info(f"Writing data for video: {video_path}")
        
        # Extract analysis results
        transcript = analysis_results["transcript"]
        combined_result = analysis_results["combined_result"]
        meta_data = analysis_results["meta_data"]
        duration = analysis_results["duration"]
        if_error = analysis_results["if_error"]
        
        # Track if any step fails
        has_failure = if_error
        
        # 1. Write metadata
        logger.info("1. Writing metadata...")
        try:
            isVoiceover, hierarchical_keywords = embed_metadata_with_exiftool(video_path, transcript, combined_result)
            logger.info(f"Hierarchical keywords: {hierarchical_keywords}")
        except Exception as e:
            logger.error(f"Error writing metadata: {str(e)}")
            logger.error(traceback.format_exc())
            has_failure = True
            hierarchical_keywords = []
            isVoiceover = False
    
        # 2. Write description file
        logger.info("2. Writing description file...")
        try:
            write_description(video_path, transcript, hierarchical_keywords, combined_result, isVoiceover, duration)
        except Exception as e:
            logger.error(f"Error writing description: {str(e)}")
            logger.error(traceback.format_exc())
            has_failure = True
        
        # 3. Store to vector database
        logger.info("3. Storing to vector database...")
        time_start9 = time.time()
        try:
            db.add_to_vector_db(video_path, combined_result, transcript, meta_data)
            logger.info(f"Vector database storage time: {time.time() - time_start9:.2f} seconds")
        except Exception as e:
            logger.error(f"Error storing to vector database: {str(e)}")
            logger.error(traceback.format_exc())
            has_failure = True
        
        # 4. Mark as processed in the database
        logger.info("4. Marking as processed in database...")
        db.mark_video_processed(video_path, combined_result, transcript, success=not has_failure)
        
        
        logger.info(f"Memory cleanup performed after writing data")
        
        return not has_failure
        
    except Exception as e:
        logger.error(f"Error writing data for video {video_path}: {str(e)}")
        logger.error(traceback.format_exc())
        # Mark as failed in the database
        try:
            db.mark_video_processed(video_path, success=False)
        except Exception as db_error:
            logger.error(f"Error marking video as failed: {str(db_error)}")
            logger.error(traceback.format_exc())
        return False

def process_single_video(video_path, db, transcriber, video_understand_model, video_understand_processor):
    """
    Process a single video file with all analysis steps
    
    Args:
        video_path: Path to the video file
        db: Database instance for checking and storing processing status
        transcriber: Transcription model
        video_understand_model: Video understanding model
        video_understand_processor: Video understanding processor
    
    Returns:
        bool: True if processing was successful, False otherwise
    """
    try:
        # Record processing start time
        process_start_time = time.time()
        
        # Step 1: Analyze video content
        try:
            analysis_results = analyze_video_content_full(video_path, transcriber, video_understand_model, video_understand_processor)
        except Exception as e:
            logger.error(f"Fatal error in video analysis: {str(e)}")
            logger.error(traceback.format_exc())
            # If analysis completely fails, mark as failed and return
            try:
                db.mark_video_processed(video_path, success=False)
            except Exception as db_error:
                logger.error(f"Error marking video as failed: {str(db_error)}")
            return False
        
        # Check if analysis had errors
        if analysis_results["if_error"]:
            logger.warning("Analysis completed with errors. Continuing with data writing.")
        
        # Step 2: Write data to files and database
        try:
            success = write_data_to_db(video_path, analysis_results, db)
        except Exception as e:
            logger.error(f"Fatal error in writing data: {str(e)}")
            logger.error(traceback.format_exc())
            # If data writing completely fails, mark as failed and return
            try:
                db.mark_video_processed(video_path, success=False)
            except Exception as db_error:
                logger.error(f"Error marking video as failed: {str(db_error)}")
            return False
        
        # Record total processing time
        total_processing_time = time.time() - process_start_time
        logger.info(f"Total processing time: {total_processing_time:.2f} seconds")
        
        
        return success
        
    except Exception as e:
        logger.error(f"Error processing video {video_path}: {str(e)}")
        logger.error(traceback.format_exc())
        # Mark as failed in the database
        try:
            db.mark_video_processed(video_path, success=False)
        except Exception as db_error:
            logger.error(f"Error marking video as failed: {str(db_error)}")
        return False

def process_video_folder_recursive(folder_path, db, transcriber, video_processor_model, video_processor_processor):
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
            
            success = process_single_video(video_path, db, transcriber, video_processor_model, video_processor_processor)
            if success:
                processed_count += 1
            else:
                failed_count += 1
                
            # No need for another cleanup here as process_single_video already does this at the end
    
    # Summary
    logger.info("------------------------------------------------------------------------------------------------")
    logger.info(f"Processing summary for {folder_path}:")
    logger.info(f"Total videos found: {total_videos}")
    logger.info(f"Videos processed successfully: {processed_count}")
    logger.info(f"Videos skipped (already processed): {skipped_count}")
    logger.info(f"Videos failed: {failed_count}")
    logger.info("------------------------------------------------------------------------------------------------") 