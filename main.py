from flask import Flask, request, jsonify, send_file
import os
import subprocess
import requests
import tempfile
import uuid
import shutil

app = Flask(__name__)

# Create output directory
OUTPUT_DIR = '/tmp/videos'
os.makedirs(OUTPUT_DIR, exist_ok=True)

def check_ffmpeg():
    """Check if FFmpeg is available"""
    try:
        result = subprocess.run(['which', 'ffmpeg'], capture_output=True, text=True)
        return result.returncode == 0
    except:
        return False

def download_file(url, filename):
    """Download file from URL"""
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        
        with open(filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"Error downloading {url}: {e}")
        return False

def combine_audio_video(audio_path, video_path, output_path):
    """Combine audio and video using FFmpeg"""
    try:
        # Try different FFmpeg commands
        ffmpeg_commands = [
            'ffmpeg',
            '/usr/bin/ffmpeg',
            '/usr/local/bin/ffmpeg'
        ]
        
        ffmpeg_path = None
        for cmd in ffmpeg_commands:
            try:
                result = subprocess.run([cmd, '-version'], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    ffmpeg_path = cmd
                    break
            except:
                continue
        
        if not ffmpeg_path:
            print("FFmpeg not found")
            return False
        
        cmd = [
            ffmpeg_path,
            '-i', video_path,
            '-i', audio_path,
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-shortest',
            '-y',  # Overwrite output file
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            return True
        else:
            print(f"FFmpeg error: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print("FFmpeg timeout")
        return False
    except Exception as e:
        print(f"FFmpeg exception: {e}")
        return False

@app.route('/health', methods=['GET'])
def health():
    ffmpeg_available = check_ffmpeg()
    return jsonify({
        "status": "healthy", 
        "ffmpeg": "available" if ffmpeg_available else "not found"
    })

@app.route('/combine', methods=['POST'])
def combine_videos():
    try:
        if not check_ffmpeg():
            return jsonify({"error": "FFmpeg not available on this system"}), 500
        
        data = request.get_json()
        
        if not data or 'audio_url' not in data or 'video_url' not in data:
            return jsonify({"error": "Missing audio_url or video_url"}), 400
        
        audio_url = data['audio_url']
        video_url = data['video_url']
        
        # Generate unique filename
        job_id = str(uuid.uuid4())
        
        # File paths
        audio_path = f'/tmp/audio_{job_id}.mp3'
        video_path = f'/tmp/video_{job_id}.mp4'
        output_path = f'{OUTPUT_DIR}/combined_{job_id}.mp4'
        
        # Download files
        print(f"Downloading audio from: {audio_url}")
        if not download_file(audio_url, audio_path):
            return jsonify({"error": "Failed to download audio"}), 400
            
        print(f"Downloading video from: {video_url}")
        if not download_file(video_url, video_path):
            return jsonify({"error": "Failed to download video"}), 400
        
        # Combine with FFmpeg
        print(f"Combining audio and video...")
        if not combine_audio_video(audio_path, video_path, output_path):
            return jsonify({"error": "Failed to combine audio and video"}), 500
        
        # Clean up input files
        try:
            os.remove(audio_path)
            os.remove(video_path)
        except:
            pass
        
        # Return the combined video file
        return send_file(
            output_path,
            as_attachment=True,
            download_name=f'combined_{job_id}.mp4',
            mimetype='video/mp4'
        )
        
    except Exception as e:
        print(f"Error in combine_videos: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
