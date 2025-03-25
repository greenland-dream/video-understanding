from flask import Flask, render_template, request, jsonify, send_file, Response
import os
import sys
from pathlib import Path
import tempfile
import subprocess
import hashlib
import json
import mimetypes
import shutil
import platform
import datetime
import sqlite3

# Set environment variable to resolve tokenizers warning
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# Add the parent directory to Python path to import main.py and query.py
current_dir = Path(__file__).resolve().parent
parent_dir = current_dir.parent
sys.path.append(str(parent_dir))

from modules.video_query import VideoQuerySystem

app = Flask(__name__)

# Database path
DB_PATH = parent_dir / "db" / "data" / "video_processing.db"

# Create a directory for storing thumbnails
THUMBNAIL_DIR = current_dir / "static" / "thumbnails"
THUMBNAIL_DIR.mkdir(exist_ok=True, parents=True)

def run_process_videos(folder_path):
    """Run the main.py script to process videos"""
    try:
        # Create a subprocess to run main.py
        process = subprocess.Popen(
            [sys.executable, str(parent_dir / "main.py")],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # Read output in real-time
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                yield output.strip()
        
        # Get the return code
        return_code = process.poll()
        if return_code != 0:
            error = process.stderr.read()
            yield f"Error: {error}"
            
    except Exception as e:
        yield f"Error: {str(e)}"

def extract_thumbnail(video_path):
    """Extract a thumbnail from a video file using ffmpeg"""
    # Generate a unique filename based on the video path
    filename_hash = hashlib.md5(video_path.encode()).hexdigest()
    thumbnail_path = THUMBNAIL_DIR / f"{filename_hash}.jpg"
    
    # Check if thumbnail already exists
    if thumbnail_path.exists():
        return str(thumbnail_path.relative_to(current_dir / "static"))
    
    try:
        # Get video duration using ffprobe
        duration_cmd = [
            "ffprobe", 
            "-v", "error", 
            "-show_entries", "format=duration", 
            "-of", "default=noprint_wrappers=1:nokey=1", 
            video_path
        ]
        duration = float(subprocess.check_output(duration_cmd, text=True).strip())
        
        # Extract frame from the middle of the video
        middle_time = duration / 2
        extract_cmd = [
            "ffmpeg",
            "-ss", str(middle_time),
            "-i", video_path,
            "-vframes", "1",
            "-q:v", "2",
            str(thumbnail_path),
            "-y"
        ]
        subprocess.run(extract_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        return str(thumbnail_path.relative_to(current_dir / "static"))
    except Exception as e:
        print(f"Error extracting thumbnail: {e}")
        return None

def select_folder_macos():
    """Use osascript to open folder selection dialog on macOS"""
    try:
        # Use AppleScript to open folder selection dialog, directly activating the foreground application
        cmd = """osascript -e '
        tell application "System Events"
            set frontApp to name of first application process whose frontmost is true
        end tell
        tell application frontApp
            set folderPath to POSIX path of (choose folder with prompt "请选择文件夹:")
        end tell'"""
        result = subprocess.check_output(cmd, shell=True, text=True).strip()
        return result
    except subprocess.CalledProcessError:
        # User canceled the selection
        return None
    except Exception as e:
        print(f"Error selecting folder: {e}")
        return None

def select_folder():
    """Choose appropriate folder selection method based on operating system"""
    system = platform.system()
    
    if system == "Darwin":  # macOS
        return select_folder_macos()
    else:
        # Add implementations for other operating systems
        return None

# Get video library statistics
def get_video_stats():
    try:
        # Check if database file exists
        if not DB_PATH.exists():
            print(f"Database file does not exist: {DB_PATH}")
            return {"total": 0, "with_transcript": 0, "error": "Database file does not exist"}
        
        # Connect to database
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        
        # Get table names
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        print("Database tables:", tables)
        
        # Get total number of videos
        cursor.execute("SELECT COUNT(*) FROM processed_videos")
        total_videos = cursor.fetchone()[0]
        
        # Get number of videos with dialogue content
        cursor.execute("SELECT COUNT(*) FROM processed_videos WHERE transcript IS NOT NULL AND transcript != ''")
        videos_with_transcript = cursor.fetchone()[0]
        
        conn.close()
        
        print(f"Video statistics: Total={total_videos}, With dialogue={videos_with_transcript}")
        
        return {
            "total": total_videos,
            "with_transcript": videos_with_transcript
        }
    except Exception as e:
        print(f"Error getting video statistics: {e}")
        # Return more detailed error information
        return {"total": 0, "with_transcript": 0, "error": str(e)}

@app.route('/')
def index():
    # Get video library statistics
    video_stats = get_video_stats()
    return render_template('index.html', video_stats=video_stats)

@app.route('/browse_folder', methods=['GET'])
def browse_folder():
    """Open folder selection dialog and return the selected path"""
    folder_path = select_folder()
    if folder_path:
        return jsonify({'success': True, 'folder_path': folder_path})
    else:
        return jsonify({'success': False, 'message': '未选择文件夹'})

@app.route('/process_videos', methods=['POST'])
def process_videos():
    folder_path = request.json.get('folder_path')
    if not folder_path or not os.path.exists(folder_path):
        return jsonify({'error': 'Invalid folder path'}), 400
    
    return jsonify({
        'status': 'processing',
        'messages': list(run_process_videos(folder_path))
    })

@app.route('/search', methods=['POST'])
def search():
    query = request.json.get('query')
    
    if not query:
        return jsonify({'error': 'Query is required'}), 400
    
    try:
        # Initialize the query system
        query_system = VideoQuerySystem(
            db_path=str(parent_dir / "db/data/video_processing.db"),
            chroma_path=str(parent_dir / "db/data/chroma_db")
        )
        
        # Perform the search
        results = query_system.search_videos(query)
        
        # Format results for frontend
        formatted_results = []
        for result in results[:20]:  # Limit to 20 results
            # Extract thumbnail for the video
            thumbnail = extract_thumbnail(result['video_path'])
            
            # Generate a unique ID for the video
            video_id = hashlib.md5(result['video_path'].encode()).hexdigest()
            
            # Ensure transcript is retrieved
            transcript = result.get('transcript', '')
            if not transcript and result.get('video_path'):
                # If there's no transcript in the result, try to get it from the database
                transcript = query_system._get_transcript_for_video(result['video_path'])
                
            # Get star rating from database if available
            star_rating = 0
            try:
                # Connect to database
                conn = sqlite3.connect(str(DB_PATH))
                cursor = conn.cursor()
                
                # Query star_rating for this video
                cursor.execute("SELECT star_rating FROM processed_videos WHERE file_path = ?", 
                              (result['video_path'],))
                rating_result = cursor.fetchone()
                
                if rating_result and rating_result[0] is not None:
                    star_rating = rating_result[0]
                
                conn.close()
            except Exception as e:
                print(f"Error getting star rating: {e}")
            
            # Include star rating in metadata
            if 'metadata' in result:
                result['metadata']['star_rating'] = star_rating
            
            formatted_result = {
                'video_path': result['video_path'],
                'video_id': video_id,
                'description': result.get('description', result.get('document', '')),
                'transcript': transcript,
                'metadata': result.get('metadata', {}),
                'thumbnail': thumbnail,
                'scores': {
                    'description': result.get('description_score', 0),
                    'transcript': result.get('transcript_score', 0),
                    'combined': result.get('combined_score', 0)
                }
            }
            
            # Print debug information
            print(f"Search result for {video_id}: transcript length = {len(transcript)}")
            
            formatted_results.append(formatted_result)
        
        return jsonify({
            'status': 'success',
            'results': formatted_results
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        query_system.close()

@app.route('/check_file')
def check_file():
    file_path = request.args.get('path')
    
    if not file_path:
        return jsonify({'error': 'No file path provided'}), 400
    
    exists = os.path.exists(file_path)
    
    # Get file info if it exists
    file_info = {}
    if exists:
        file_info = {
            'size': os.path.getsize(file_path),
            'mime_type': mimetypes.guess_type(file_path)[0] or 'application/octet-stream',
            'filename': os.path.basename(file_path)
        }
    
    return jsonify({
        'exists': exists,
        'file_info': file_info,
        'video_id': hashlib.md5(file_path.encode()).hexdigest() if exists else None
    })

@app.route('/update_rating', methods=['POST'])
def update_rating():
    """Update the star rating for a video"""
    video_path = request.json.get('video_path')
    rating = request.json.get('rating')
    
    if not video_path:
        return jsonify({'success': False, 'error': 'No video path provided'}), 400
    
    try:
        # Validate rating
        rating = int(rating)
        if rating < 0 or rating > 5:
            return jsonify({'success': False, 'error': 'Rating must be between 0 and 5'}), 400
        
        # Connect to database
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        
        # Update the rating
        cursor.execute(
            "UPDATE processed_videos SET star_rating = ? WHERE file_path = ?",
            (rating, video_path)
        )
        conn.commit()
        
        # Check if any rows were affected
        if cursor.rowcount > 0:
            conn.close()
            return jsonify({'success': True})
        else:
            # If no rows were affected, the video may not be in the database yet
            # Get the file hash to identify the video
            unified_id = hashlib.md5(video_path.encode()).hexdigest()
            file_hash = ""
            
            if os.path.exists(video_path):
                # Compute file hash if needed
                with open(video_path, 'rb') as f:
                    file_hash = hashlib.md5(f.read()).hexdigest()
            
            # Try to insert a basic record with the rating
            try:
                cursor.execute(
                    "INSERT INTO processed_videos (id, file_path, file_hash, star_rating) VALUES (?, ?, ?, ?)",
                    (unified_id, video_path, file_hash, rating)
                )
                conn.commit()
                conn.close()
                return jsonify({'success': True})
            except:
                conn.close()
                return jsonify({'success': False, 'error': 'Could not update rating, video not found'}), 404
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/stream_video/<video_id>')
def stream_video(video_id):
    # Get the specific video path from the request
    video_path = request.args.get('path')
    
    # If path is provided directly and exists, use it
    if video_path and os.path.exists(video_path):
        # Get the file's MIME type
        mime_type = mimetypes.guess_type(video_path)[0] or 'application/octet-stream'
        return send_file(video_path, mimetype=mime_type)
    
    return jsonify({'error': 'Video not found'}), 404

@app.route('/export_videos', methods=['POST'])
def export_videos():
    """Export selected videos to specified folder"""
    data = request.json
    export_folder = data.get('export_folder')
    videos = data.get('videos', [])
    
    if not export_folder or not os.path.exists(export_folder):
        return jsonify({'error': '导出文件夹路径无效'}), 400
    
    if not videos:
        return jsonify({'error': '未选择任何视频'}), 400
    
    results = []
    descriptions = []
    
    for video in videos:
        video_path = video.get('video_path')
        description = video.get('description', '')
        
        if not video_path or not os.path.exists(video_path):
            results.append({
                'video_path': video_path,
                'success': False,
                'message': '视频文件不存在'
            })
            continue
        
        try:
            # Get filename
            filename = os.path.basename(video_path)
            # Target path
            target_path = os.path.join(export_folder, filename)
            
            # Copy file
            shutil.copy2(video_path, target_path)
            
            # Add to results
            results.append({
                'video_path': video_path,
                'success': True,
                'target_path': target_path,
                'message': '导出成功'
            })
            
            # Add to description list - only include filename and description
            video_info = f"文件名: {filename}\n"
            video_info += f"描述: {description}\n\n"
            descriptions.append(video_info)
            
        except Exception as e:
            results.append({
                'video_path': video_path,
                'success': False,
                'message': f'导出失败: {str(e)}'
            })
    
    # Write description file - append content if file already exists
    try:
        description_file_path = os.path.join(export_folder, "video_descriptions.txt")
        
        # Check if file already exists
        file_exists = os.path.exists(description_file_path)
        
        # Open file, append if exists, create if not
        with open(description_file_path, 'a' if file_exists else 'w', encoding='utf-8') as f:
            # If new file, add title
            if not file_exists:
                f.write("导出视频描述\n\n")
            
            # Write new descriptions
            f.writelines(descriptions)
    except Exception as e:
        return jsonify({
            'results': results,
            'description_file': {
                'success': False,
                'message': f'描述文件创建失败: {str(e)}'
            }
        })
    
    return jsonify({
        'results': results,
        'description_file': {
            'success': True,
            'path': description_file_path
        }
    })

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080, debug=True)  