import cv2
from PIL import Image
import numpy as np
import os
from utils.log_config import setup_logger
from utils.utility import extract_json, clear_memory
import gc
import torch

logger = setup_logger(__name__)
def load_prompt(prompt_file_name):
    # Create a prompt for video analysis
    # Read the video understanding prompt from the config file
    prompt_file_path = os.path.join("config", "prompts", prompt_file_name)
    try:
        with open(prompt_file_path, "r", encoding="utf-8") as f:
            video_prompt = f.read()
        logger.debug("Successfully loaded video understanding prompt from file")
    except Exception as e:
        logger.error(f"Error loading video prompt file: {str(e)}")
        # Fallback prompt in case file can't be read
        video_prompt = "Analyze this video and describe what you see in detail."
    
    return video_prompt


def video_query(video_path, video_understand_model, video_understand_processor, meta_data, duration, transcript, ifresize=False, resize_height=896, resize_width=896):
    import base64
    import io
    
    # Gemma3 model was originally created to work with images of 896x896 pixels
    frames = downsample_video(video_path, max_frames=26, min_frames=4, resize_height=896, resize_width=896, ifresize=ifresize)
    logger.info(f"Downsampled video frames: {len(frames)}")
    prompt = load_prompt("video_undersanding_en.md")
    logger.info(f"prompt: {prompt}")


    messages = [
        {
            "role": "system",
            "content": [{"type": "text", "text": "You are a helpful assistant."}]
        },

        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt}]
        }
    ]
    
    # Process frames with base64 encoding
    for frame in frames:
        image, timestamp = frame
        messages[1]["content"].append({"type": "text", "text": f"Frame {timestamp}:"})
        
        # Convert PIL image to base64 string
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        
        # Add the base64 image to the message
        messages[1]["content"].append({"type": "image", "url": f"data:image/png;base64,{img_str}"})

    try:
        inputs = video_understand_processor.apply_chat_template(
            messages, add_generation_prompt=True, tokenize=True,
            return_dict=True, return_tensors="pt"
        ).to(video_understand_model.device)

        input_len = inputs["input_ids"].shape[-1]

        generation = video_understand_model.generate(**inputs, max_new_tokens=4096, do_sample=False)
        generation = generation[0][input_len:]

        decoded = video_understand_processor.decode(generation, skip_special_tokens=True)
        
        try:
            # Use the extract_json utility function to get the JSON content
            json_content = extract_json(decoded)
            
            # Check if json_content is a string (JSON string) or already a dictionary
            if isinstance(json_content, str):
                import json
                try:
                    # Parse the JSON string into a dictionary
                    json_dict = json.loads(json_content)
                    result = json_dict.get("description", decoded)
                except json.JSONDecodeError as e:
                    logger.error(f"Error parsing JSON from model response: {str(e)}")
                    # Create a dictionary with the raw text as description
                    result = decoded
            else:
                # If it's already a dictionary, just get the description
                result = json_content.get("description", decoded)
                
            logger.debug("Successfully processed model response")
        except Exception as e:
            logger.error(f"Error extracting description from model response: {str(e)}")
            # Return the raw decoded text as fallback
            result = decoded
    finally:
        # Clean up memory
        del frames
        del messages
        if 'inputs' in locals():
            del inputs
        if 'generation' in locals():
            del generation
        
    
    return result


def downsample_video(video_path, max_frames=30, min_frames=4, resize_height=896, resize_width=896, ifresize=False):
    vidcap = cv2.VideoCapture(video_path)
    if not vidcap.isOpened():
        print(f"Warning: Could not open video file: {video_path}")
        return []
    
    # Get video properties
    video_fps = vidcap.get(cv2.CAP_PROP_FPS)
    total_frames = int(vidcap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / video_fps if video_fps > 0 else 0
    
    # Always use fps=1.0 by default
    fps = 1.0
    
    # Calculate expected frames that will be extracted
    expected_frames = int(duration * fps)
    
    # For very short videos, increase fps to get at least 4 frames
    if expected_frames < min_frames and duration > 0:
        # Calculate new fps to get exactly min_frames
        fps = min_frames / duration
        expected_frames = min_frames
        print(f"Short video detected: increasing fps to {fps:.2f} to get minimum {min_frames} frames")
    
    
    # Store original expected frames before limiting
    original_expected_frames = expected_frames
    expected_frames = min(max_frames, expected_frames)
    
    # Recalculate fps if we're limiting frames
    if original_expected_frames > max_frames and duration > 0:
        # Adjust fps to evenly distribute frames across the entire video duration
        fps = expected_frames / duration
        print(f"Long video detected: adjusting fps to {fps:.2f} to limit to {expected_frames} frames across {duration:.2f} seconds")
    
    print(f"Extraction parameters: fps={fps:.2f}, expected to extract {expected_frames} frames")
    
    # Calculate the frame indices to extract
    interval = video_fps / fps
    frames = []
    
    for i in range(expected_frames):
        frame_idx = int(i * interval)
        if frame_idx >= total_frames:
            break
            
        vidcap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        success, image = vidcap.read()
        if success:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)  # Convert from BGR to RGB
            if ifresize:
                image = resize_image(image, resize_height, resize_width)
            pil_image = Image.fromarray(image)
            timestamp = round(frame_idx / video_fps, 2)
            frames.append((pil_image, timestamp))

    vidcap.release()
    
    # Clean up OpenCV resources
    del vidcap
    
    return frames


def resize_image(image, resize_height=896, resize_width=896):
    """
    Resize the image only if it exceeds the specified dimensions.
    
    Args:
        image: PIL Image object or NumPy array
        max_height: Maximum height for the image
        max_width: Maximum width for the image
        
    Returns:
        Resized image if needed, original image otherwise
    """
    # Check if image is a NumPy array (from OpenCV)
    if isinstance(image, np.ndarray):
        # For numpy arrays, shape is (height, width, channels)
        original_height, original_width = image.shape[:2]
        
        # Check if resizing is needed
        if original_width > resize_width or original_height > resize_height:
            # Calculate the new size maintaining the aspect ratio
            aspect_ratio = original_width / original_height
            if original_width > original_height:
                new_width = resize_width
                new_height = int(resize_width / aspect_ratio)
            else:
                new_height = resize_height
                new_width = int(resize_height * aspect_ratio)
            
            # Resize the image using OpenCV
            return cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_LANCZOS4)
        else:
            return image
    else:
        # Assume it's a PIL Image
        original_width, original_height = image.size
        
        # Check if resizing is needed
        if original_width > resize_width or original_height > resize_height:
            # Calculate the new size maintaining the aspect ratio
            aspect_ratio = original_width / original_height
            if original_width > original_height:
                new_width = resize_width
                new_height = int(resize_width / aspect_ratio)
            else:
                new_height = resize_height
                new_width = int(resize_height * aspect_ratio)
            
            # Resize the image using LANCZOS for high-quality downscaling
            return image.resize((new_width, new_height), Image.LANCZOS)
        else:
            return image