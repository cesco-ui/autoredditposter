from flask import Flask, request, jsonify, send_file, Response
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
        # Add browser-like headers
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        print(f"Attempting to download: {url}")
        
        response = requests.get(url, headers=headers, stream=True, timeout=30, allow_redirects=True)
        
        print(f"Response status: {response.status_code}")
        print(f"Response headers: {dict(response.headers)}")
        
        response.raise_for_status()
        
        with open(filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        file_size = os.path.getsize(filename)
        print(f"Downloaded {file_size} bytes to {filename}")
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"Request error downloading {url}: {e}")
        return False
    except Exception as e:
        print(f"General error downloading {url}: {e}")
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
    """Original endpoint - returns binary file"""
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

@app.route('/combine-url', methods=['POST'])
def combine_videos_url():
    """New endpoint - returns URL instead of binary file"""
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
        
        # Return URL info instead of file - now with .mp4 extension for Creatomate
        download_url = f"{request.host_url}download/{job_id}.mp4"
        file_size = os.path.getsize(output_path)
        
        return jsonify({
            "success": True,
            "download_url": download_url,
            "url": download_url,  # For easy access in n8n
            "job_id": job_id,
            "file_size": file_size
        })
        
    except Exception as e:
        print(f"Error in combine_videos_url: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/download/<job_id>', methods=['GET'])
def download_video(job_id):
    """Download endpoint for combined videos - backward compatibility"""
    output_path = f'{OUTPUT_DIR}/combined_{job_id}.mp4'
    
    if not os.path.exists(output_path):
        return jsonify({"error": "File not found"}), 404
    
    response = send_file(
        output_path,
        as_attachment=False,
        mimetype='video/mp4'
    )
    
    # Add headers for better video streaming
    response.headers['Accept-Ranges'] = 'bytes'
    response.headers['Content-Type'] = 'video/mp4'
    
    return response

@app.route('/download/<job_id>.mp4', methods=['GET'])
def download_video_mp4(job_id):
    """Download endpoint with .mp4 extension for Creatomate compatibility"""
    output_path = f'{OUTPUT_DIR}/combined_{job_id}.mp4'
    
    if not os.path.exists(output_path):
        return jsonify({"error": "File not found"}), 404
    
    response = send_file(
        output_path,
        as_attachment=False,
        mimetype='video/mp4'
    )
    
    # Add headers for better video streaming and Creatomate compatibility
    response.headers['Accept-Ranges'] = 'bytes'
    response.headers['Content-Type'] = 'video/mp4'
    response.headers['Cache-Control'] = 'public, max-age=3600'
    
    return response

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
