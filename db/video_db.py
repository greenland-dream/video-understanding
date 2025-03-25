import json
import hashlib
import datetime
import chromadb
import torch
from chromadb.config import Settings
from chromadb.utils import embedding_functions
from sqlalchemy import create_engine, Column, String, Boolean, DateTime, Text, Float, Date, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from utils.ffmpeg_funs import get_video_orientation, get_video_duration
from langchain_community.embeddings import HuggingFaceEmbeddings

# Define the SQLAlchemy model
Base = declarative_base()

class ProcessedVideo(Base):
    __tablename__ = 'processed_videos'
    
    id = Column(String(64), primary_key=True)  # Using MD5 hash as unified ID
    file_path = Column(String(500), unique=True)
    file_hash = Column(String(64))
    processed_at = Column(DateTime, default=datetime.datetime.utcnow)
    success = Column(Boolean, default=True)
    
    # Analysis results
    analysis_json = Column(Text)  # Full analysis result JSON
    description = Column(Text)    # Video description
    transcript = Column(Text)     # Video transcript
    meta_data = Column(Text)      # Original meta_data content
    
    # Extracted metadata fields
    time_of_day = Column(String(100))  # Keep as string since it's descriptive text
    color = Column(String(100))        # Keep as string since it's descriptive text
    date = Column(DateTime)               # Changed from Date to DateTime for more flexibility
    scene = Column(String(100))        # Keep as string since it's descriptive text
    people = Column(String(500))       # Keep as string since it's a text list
    location = Column(String(500))     # Keep as string since it's descriptive text
    orientation = Column(String(50))   # Keep as string since it's an enum-like value
    duration = Column(Float)           # Change to Float for numeric duration in seconds
    camera_movement = Column(String(100))  # Camera movement type (static, panning, etc.)
    camera_angle = Column(String(100))     # Camera angle (eye level, aerial, etc.)
    camera_shot_type = Column(String(100))  # Camera shot type (close-up, medium shot, wide shot, etc.)
    star_rating = Column(Integer, default=0)  # Star rating from 0 to 5
    
    def __repr__(self):
        return f"<ProcessedVideo(id='{self.id}', file_path='{self.file_path}')>"

# Define custom embedding function class, compatible with ChromaDB interface requirements
class HuggingFaceEmbeddingFunction(embedding_functions.EmbeddingFunction):
    def __init__(self, model_name="BAAI/bge-large-zh-v1.5", device=None):
        # Check if MPS is available (Apple Silicon GPU acceleration)
        if device is None:
            device = "mps" if torch.backends.mps.is_available() else "cpu"
        
        self.embeddings = HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs={"device": device}
        )
    
    def __call__(self, input):
        # Ensure input is a list
        if not isinstance(input, list):
            input = [input]
        
        # Generate embeddings using HuggingFaceEmbeddings
        return [self.embeddings.embed_query(text) if text else [0.0] * 1024 for text in input]

class VideoDatabase:
    def __init__(self, db_path, chroma_path):
        # Setup SQL Database
        self.engine = create_engine(f'sqlite:///{db_path}')
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        
        # Create custom embedding function instance
        self.embedding_function = HuggingFaceEmbeddingFunction()
        
        # Setup Chroma Vector Database
        self.chroma_client = chromadb.PersistentClient(
            path=chroma_path,
            settings=Settings(allow_reset=True)
        )
        
        # Get or create collection with custom embeddings
        self.collection = self.chroma_client.get_or_create_collection(
            name="video_analysis",
            metadata={"hnsw:space": "cosine"},
            embedding_function=self.embedding_function
        )
    
    def close(self):
        """Close database connections and release resources"""
        try:
            # Close any SQLAlchemy resources
            self.engine.dispose()
            # Close Chroma client if it has a close method
            if hasattr(self.chroma_client, 'close'):
                self.chroma_client.close()
        except Exception as e:
            print(f"Error closing database connections: {str(e)}")
    
    def __del__(self):
        """Destructor to ensure resources are released"""
        try:
            self.close()
        except:
            pass
    
    def is_video_processed(self, file_path):
        """
        Check if a video has already been processed by checking both path and content hash
        """
        if not file_path or not isinstance(file_path, str):
            return False
            
        session = self.Session()
        try:
            result = session.query(ProcessedVideo).filter_by(file_path=file_path).first()
            if result is not None:
                return True
            
            # If not found by path, compute hash and check by content
            try:
                file_hash = self.compute_file_hash(file_path)
                result = session.query(ProcessedVideo).filter_by(file_hash=file_hash).first()
                return result is not None
            except (FileNotFoundError, PermissionError, IOError) as e:
                print(f"Error checking file hash for {file_path}: {str(e)}")
                return False
        finally:
            session.close()
    
    def compute_file_hash(self, file_path):
        """Compute a hash for the file to identify it even if renamed/moved"""
        if not file_path or not isinstance(file_path, str):
            raise ValueError("Invalid file path provided")
            
        hasher = hashlib.md5()
        try:
            with open(file_path, 'rb') as f:
                # Read just the first 1MB for speed, adjust as needed
                buf = f.read(1024 * 1024)
                hasher.update(buf)
            return hasher.hexdigest()
        except (FileNotFoundError, PermissionError, IOError) as e:
            raise e
    
    def mark_video_processed(self, file_path, analysis_result=None, transcript=None, success=True):
        """Mark a video as processed in the database with all metadata"""
        if not file_path or not isinstance(file_path, str):
            raise ValueError("Invalid file path provided")
            
        try:
            # Generate unified ID from file path
            unified_id = hashlib.md5(file_path.encode()).hexdigest()
            file_hash = self.compute_file_hash(file_path)
            
            # Parse analysis_result if it's a string
            if isinstance(analysis_result, str):
                try:
                    analysis_dict = json.loads(analysis_result)
                except json.JSONDecodeError:
                    analysis_dict = {"描述": analysis_result}
            else:
                analysis_dict = analysis_result or {}
            
            # Extract metadata fields
            metadata = {
                "time_of_day": analysis_dict.get("拍摄时间", ""),
                "color": analysis_dict.get("颜色", ""),
                "scene": analysis_dict.get("拍摄场景", ""),
                "people": analysis_dict.get("人物", ""),
                "camera_movement": analysis_dict.get("镜头移动", ""),
                "camera_angle": analysis_dict.get("拍摄角度", ""),
                "camera_shot_type": analysis_dict.get("镜头类型", "")
            }
            
            # Parse date string to DateTime object with enhanced format support
            date_str = analysis_dict.get("拍摄日期", "")
            parsed_date = None
            
            if date_str:
                # Define all possible date formats
                date_formats = [
                    # Full date formats
                    "%Y-%m-%d",
                    "%Y/%m/%d",
                    "%Y年%m月%d日",
                    "%Y年%m月%d号",
                    # Year-month only formats
                    "%Y年%m月",
                    "%Y-%m",
                    "%Y/%m",
                    # Year only format
                    "%Y年",
                    "%Y"
                ]
                
                for date_format in date_formats:
                    try:
                        if "月" in date_str and "日" not in date_str and "号" not in date_str:
                            # For year-month format, add default day
                            if date_format in ["%Y年%m月", "%Y-%m", "%Y/%m"]:
                                temp_date = datetime.datetime.strptime(date_str, date_format)
                                # Set to the first day of the month
                                parsed_date = temp_date.replace(day=1)
                                break
                        elif "年" in date_str and "月" not in date_str:
                            # For year only format, set to January 1st
                            if date_format in ["%Y年", "%Y"]:
                                temp_date = datetime.datetime.strptime(date_str, date_format)
                                # Set to January 1st
                                parsed_date = temp_date.replace(month=1, day=1)
                                break
                        else:
                            # For full date format
                            parsed_date = datetime.datetime.strptime(date_str, date_format)
                            break
                    except ValueError:
                        continue
            
            # Combine locations
            main_location = analysis_dict.get("拍摄主地点", "")
            sub_location = analysis_dict.get("拍摄次地点", "")
            location = f"{main_location}｜{sub_location}" if main_location and sub_location else (main_location or sub_location)
            
            # Get video properties
            orientation = get_video_orientation(file_path)
            orientation_map = {
                "horizontal": "横屏",
                "vertical": "竖屏", 
                "square": "方屏"
            }
            duration = get_video_duration(file_path)
            
            session = self.Session()
            try:
                video = ProcessedVideo(
                    id=unified_id,
                    file_path=file_path,
                    file_hash=file_hash,
                    success=success,
                    analysis_json=json.dumps(analysis_result) if analysis_result else None,
                    description=analysis_dict.get("描述", ""),
                    transcript=transcript,
                    meta_data=analysis_dict.get("meta_data", ""),
                    time_of_day=metadata["time_of_day"],
                    color=metadata["color"],
                    date=parsed_date,
                    scene=metadata["scene"],
                    people=metadata["people"],
                    location=location,
                    orientation=orientation_map.get(orientation, ""),
                    duration=float(duration) if duration else None,
                    camera_movement=metadata["camera_movement"],
                    camera_angle=metadata["camera_angle"],
                    camera_shot_type=metadata["camera_shot_type"],
                    star_rating=analysis_dict.get("star_rating", 0)
                )
                session.add(video)
                session.commit()
            finally:
                session.close()
        except Exception as e:
            print(f"Error marking video as processed: {str(e)}")
            raise
    
    def add_to_vector_db(self, file_path, analysis_result, transcript=None, meta_data=None):
        """
        Add analysis results to the vector database
        
        Args:
            file_path: Path to the video file
            analysis_result: Dictionary containing analysis results including description and metadata
            transcript: Optional transcript text
            meta_data: Optional metadata text
        """
        if not file_path or not isinstance(file_path, str):
            raise ValueError("Invalid file path provided")
            
        try:
            # Generate unified ID - same as SQL database
            unified_id = hashlib.md5(file_path.encode()).hexdigest()
            
            # Parse analysis_result if it's a string
            if isinstance(analysis_result, str):
                try:
                    analysis_dict = json.loads(analysis_result)
                except json.JSONDecodeError:
                    analysis_dict = {"描述": analysis_result}
            else:
                analysis_dict = analysis_result
            
            # Extract description for vector embedding
            description = meta_data or ""
            if "描述" in analysis_dict:
                description += " " + analysis_dict["描述"]
            
            # Create base metadata with all structured fields
            metadata = {
                "video_path": file_path,
                "processed_at": datetime.datetime.utcnow().isoformat(),
                "sql_id": unified_id  # Add reference to SQL database ID
            }
            
            # Map Chinese field names to English ones
            field_mapping = {
                "拍摄时间": "time_of_day",
                "颜色": "color",
                "拍摄日期": "date",
                "拍摄场景": "scene",
                "人物": "people",
                "镜头移动": "camera_movement",
                "拍摄角度": "camera_angle",
                "镜头类型": "camera_shot_type"
            }
            
            # Convert Chinese keys to English and add to metadata
            for zh_field, en_field in field_mapping.items():
                if zh_field in analysis_dict:
                    metadata[en_field] = analysis_dict[zh_field]
            
            # Combine main and sub locations into a single location field
            main_location = analysis_dict.get("拍摄主地点")
            sub_location = analysis_dict.get("拍摄次地点")
            
            if main_location and sub_location:
                metadata["location"] = f"{main_location}｜{sub_location}"
            elif main_location or sub_location:
                metadata["location"] = main_location or sub_location
            else:
                metadata["location"] = ""
            
            # Add video orientation
            orientation = get_video_orientation(file_path)
            orientation_map = {
                "horizontal": "横屏",
                "vertical": "竖屏", 
                "square": "方屏"
            }
            metadata["orientation"] = orientation_map[orientation]

            # Add video duration
            duration = get_video_duration(file_path)
            metadata["duration"] = f"{duration:.1f}"
            
            # 1. Add description document with all metadata
            self.collection.add(
                documents=[description],
                metadatas=[{**metadata, "document_type": "description"}],
                ids=[unified_id]
            )
            
            # 2. Add transcript document if available
            if transcript and transcript.strip():
                transcript_id = f"{unified_id}_transcript"
                self.collection.add(
                    documents=[transcript],
                    metadatas=[{**metadata, "document_type": "transcript"}],
                    ids=[transcript_id]
                )
            
            return True
            
        except Exception as e:
            print(f"Error adding video to vector DB: {str(e)}")
            raise 