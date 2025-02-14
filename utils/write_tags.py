import os
import json
import subprocess, traceback
from utils.log_config import setup_logger
from utils.ffmpeg_funs import get_video_orientation, get_video_duration

logger = setup_logger(__name__)

def transform_tags(raw_tags):
    """
    Transform raw tags into a structured format
    
    Args:
        raw_tags: Raw tags in JSON string or dict format
        
    Returns:
        dict: Transformed tags
    """
    if isinstance(raw_tags, str):
        try:
            tags = json.loads(raw_tags)
        except json.JSONDecodeError as e:
            print("JSON解析错误:", e)
            return {}
    elif isinstance(raw_tags, dict):
        tags = raw_tags.copy()
    else:
        print("不支持的 tags 数据类型")
        return {}
    return tags
    # 特殊处理：将"详细描述"复制到 description 字段
    # if "详细描述" in tags:
    #     tags["description"] = tags["详细描述"]
    # else:
    #     tags["description"] = "无描述"
    # return tags

def embed_metadata_with_exiftool(input_video, transcript, raw_tags):
    """
    Use ExifTool to embed metadata into MOV file for Adobe Bridge
    
    Args:
        input_video: Path to input video file
        transcript: Transcription text
        raw_tags: Tags in JSON string or dict format
        
    Returns:
        tuple: (bool, str) - (has_voiceover, hierarchical_keywords_string)
    """
    isVoiceover = False
    try:
        tags = transform_tags(raw_tags)
        cmd = ["exiftool", "-overwrite_original"]
        
        # Get video duration
        duration = get_video_duration(input_video)
        
        # Write XMP-dc:Description field
        if "description" in tags:
            description_text = tags['description']
            # Add duration info
            description_text = f"Duration: {duration:.1f}s | " + description_text
            if "是否有旁白" in tags and tags["是否有旁白"] == "有旁白":
                isVoiceover = True
                description_text += f" | Voiceover: {transcript}"
            cmd.append(f'-XMP-dc:Description="{description_text}"')

        # Build hierarchical and flat keywords
        hierarchical_keywords = []
        flat_keywords = []

        if "拍摄时间" in tags:
            hierarchical_keywords.append(f"拍摄时间|{tags['拍摄时间']}")
            flat_keywords.append(tags["拍摄时间"])

        if "拍摄场景" in tags and "二级场景分类" in tags:
            hierarchical_keywords.append(f"{tags['拍摄场景']}|{tags['二级场景分类']}")
            flat_keywords.append(tags["二级场景分类"])

        if "颜色" in tags:
            hierarchical_keywords.append(f"颜色|{tags['颜色']}")
            flat_keywords.append(tags["颜色"])

        if "人物" in tags:
            hierarchical_keywords.append(f"人物|{tags['人物']}")
            flat_keywords.append(tags["人物"])

        if "拍摄主地点" in tags:
            hierarchical_keywords.append(f"拍摄主地点|{tags['拍摄主地点']}")
            flat_keywords.append(tags["拍摄主地点"])

        if "拍摄次地点" in tags:
            hierarchical_keywords.append(f"拍摄次地点|{tags['拍摄次地点']}")
            flat_keywords.append(tags["拍摄次地点"])

        if "拍摄日期" in tags:
            hierarchical_keywords.append(f"拍摄日期|{tags['拍摄日期']}")
            flat_keywords.append(tags["拍摄日期"])
        
        if "是否有旁白" in tags:
            hierarchical_keywords.append(f"是否有旁白|{tags['是否有旁白']}")
            flat_keywords.append(tags["是否有旁白"])            

        if "旁白总结" in tags:
            if tags['是否有旁白'] == "有旁白":
                hierarchical_keywords.append(f"Voiceover|{tags['旁白总结']}")
                flat_keywords.append(tags["旁白总结"])

        # Add orientation tags
        orientation = get_video_orientation(input_video)
        if orientation == "horizontal":
            hierarchical_keywords.append("Orientation|horizontal")
            flat_keywords.append("horizontal")
        elif orientation == "vertical":
            hierarchical_keywords.append("Orientation|vertical")
            flat_keywords.append("vertical")
        else:
            hierarchical_keywords.append("Orientation|square")
            flat_keywords.append("square")

        # Write Hierarchical Subject field
        if hierarchical_keywords:
            cmd.append(f"-HierarchicalSubject={hierarchical_keywords[0]}")
            for kw in hierarchical_keywords[1:]:
                cmd.append(f"-HierarchicalSubject+={kw}")
        
        # Write Subject field (flat keywords)
        if flat_keywords:
            cmd.append(f"-Subject={flat_keywords[0]}")
            for kw in flat_keywords[1:]:
                cmd.append(f"-Subject+={kw}")
        
        # Add input file path
        cmd.append(str(input_video))
        
        logger.info(f"Executing command: {' '.join(cmd)}")
        
        # Execute command
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.stderr:
            logger.error(f"Failed to write metadata, error:\n{result.stderr}")
        else:
            logger.info("Metadata written successfully")
            
        # Return voiceover status and hierarchical keywords string
        hierarchical_keywords_str = "; ".join(hierarchical_keywords)
        return isVoiceover, hierarchical_keywords_str

    except subprocess.CalledProcessError as e:
        traceback.print_exc()
        logger.error(f"ExifTool execution error: {e}")
        return isVoiceover, ""

def write_description(folder_path, video, transcript, hierarchical_keywords, raw_tags, isVoiceover, duration):
    """
    Write video descriptions to video_descriptions.txt in the folder
    
    Args:
        folder_path: Path to folder containing videos
        video: Path to video file
        transcript: Transcription text
        hierarchical_keywords: Hierarchical keywords string
        raw_tags: Tags in JSON string or dict format
        isVoiceover: Whether video has voiceover
        duration: Video duration in seconds
    """
    tags = transform_tags(raw_tags)
    description = tags.get("description", "")
    
    # Get video filename without path
    video_name = os.path.basename(video)
    description_file = os.path.join(folder_path, "video_descriptions.txt")
    
    if isVoiceover:
        line = (
            f"{video_name}: Duration {duration:.1f}s\n"
            f"Description: {description}\n"
            f"Keywords: {hierarchical_keywords}\n"
            f"Voiceover: {transcript}\n\n"
        )
    else:
        line = (
            f"{video_name}: Duration {duration:.1f}s\n"
            f"Description: {description}\n"
            f"Keywords: {hierarchical_keywords}\n\n"
        )

    # "a" mode will create file if not exists
    with open(description_file, "a", encoding="utf-8") as f:
        f.write(line)
    
    logger.info(f"Description written to {description_file}")

