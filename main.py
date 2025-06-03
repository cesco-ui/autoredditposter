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

def verify_audio_in_video(video_path):
    """Verify that the video file actually contains audio streams"""
    try:
        ffmpeg_commands = ['ffmpeg', '/usr/bin/ffmpeg', '/usr/local/bin/ffmpeg']
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
            print("FFmpeg not found for verification")
            return False
        
        # Check if video has audio streams
        cmd = [
            ffmpeg_path,
            '-i', video_path,
            '-af', 'volumedetect',
            '-f', 'null',
            '-'
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        # Check if audio stream exists and has volume
        stderr_output = result.stderr.lower()
        
        if 'stream #0:1: audio' in stderr_output or 'stream #0:0: audio' in stderr_output:
            print("✅ Audio stream detected in output video")
            
            # Check if audio has actual volume (not silent)
            if 'mean_volume:' in stderr_output and 'max_volume:' in stderr_output:
                print("✅ Audio has detectable volume")
                return True
            else:
                print("❌ Audio stream exists but appears to be silent")
                return False
        else:
            print("❌ No audio stream found in output video")
            return False
            
    except Exception as e:
        print(f"Error verifying audio: {e}")
        return False

def download_file(url, filename):
    """Download file from URL with enhanced headers for Dropbox compatibility"""
    try:
        # Enhanced browser-like headers specifically for Dropbox temporary links
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'DNT': '1'
        }
        
        print(f"Attempting to download: {url}")
        print(f"Target filename: {filename}")
        
        # Check if it's a Dropbox temporary link
        is_dropbox_temp = 'dropboxusercontent.com' in url
        print(f"Dropbox temporary link detected: {is_dropbox_temp}")
        
        response = requests.get(
            url, 
            headers=headers, 
            stream=True, 
            timeout=60,  # Increased timeout for audio files
            allow_redirects=True,
            verify=True  # Ensure SSL verification
        )
        
        print(f"Response status: {response.status_code}")
        print(f"Response headers: {dict(response.headers)}")
        print(f"Final URL after redirects: {response.url}")
        
        response.raise_for_status()
        
        # Check content type for audio files
        content_type = response.headers.get('content-type', '').lower()
        print(f"Content-Type: {content_type}")
        
        if 'audio' in filename and 'audio' not in content_type and 'octet-stream' not in content_type:
            print(f"Warning: Expected audio content but got {content_type}")
        
        # Write file in chunks
        total_size = 0
        with open(filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:  # Filter out keep-alive chunks
                    f.write(chunk)
                    total_size += len(chunk)
        
        file_size = os.path.getsize(filename)
        print(f"Downloaded {file_size} bytes to {filename}")
        print(f"Total streamed: {total_size} bytes")
        
        # Verify file size
        if file_size == 0:
            print("Error: Downloaded file is empty")
            return False
            
        # For audio files, do additional verification
        if 'audio' in filename:
            if file_size < 1000:  # Less than 1KB is suspicious for audio
                print(f"Warning: Audio file seems too small ({file_size} bytes)")
                return False
        
        return True
        
    except requests.exceptions.Timeout as e:
        print(f"Timeout error downloading {url}: {e}")
        return False
    except requests.exceptions.ConnectionError as e:
        print(f"Connection error downloading {url}: {e}")
        return False
    except requests.exceptions.HTTPError as e:
        print(f"HTTP error downloading {url}: {e}")
        return False
    except requests.exceptions.RequestException as e:
        print(f"Request error downloading {url}: {e}")
        return False
    except Exception as e:
        print(f"General error downloading {url}: {e}")
        return False

def combine_audio_video(audio_path, video_path, output_path):
    """Combine audio and video using FFmpeg with enhanced debugging"""
    try:
        # Verify input files exist and have content
        if not os.path.exists(audio_path):
            print(f"Audio file not found: {audio_path}")
            return False
            
        if not os.path.exists(video_path):
            print(f"Video file not found: {video_path}")
            return False
            
        audio_size = os.path.getsize(audio_path)
        video_size = os.path.getsize(video_path)
        
        print(f"Audio file size: {audio_size} bytes")
        print(f"Video file size: {video_size} bytes")
        
        if audio_size == 0:
            print("Error: Audio file is empty")
            return False
            
        if video_size == 0:
            print("Error: Video file is empty")
            return False
        
        # Find FFmpeg
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
        
        # Enhanced FFmpeg command with explicit mapping and audio processing
        cmd = [
            ffmpeg_path,
            '-i', video_path,           # Input 0: video
            '-i', audio_path,           # Input 1: audio
            '-map', '0:v:0',           # Map video stream from input 0
            '-map', '1:a:0',           # Map audio stream from input 1
            '-c:v', 'copy',            # Copy video without re-encoding
            '-c:a', 'aac',             # Encode audio as AAC
            '-b:a', '128k',            # Set audio bitrate
            '-ar', '44100',            # Set audio sample rate
            '-ac', '2',                # Set audio channels to stereo
            '-shortest',               # Stop when shortest stream ends
            '-avoid_negative_ts', 'make_zero',  # Fix timestamp issues
            '-y',                      # Overwrite output file
            output_path
        ]
        
        print(f"Running enhanced FFmpeg command: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        print(f"FFmpeg return code: {result.returncode}")
        print(f"FFmpeg stdout: {result.stdout}")
        print(f"FFmpeg stderr: {result.stderr}")
        
        if result.returncode == 0:
            output_size = os.path.getsize(output_path)
            print(f"FFmpeg success. Output file size: {output_size} bytes")
            
            # CRITICAL: Verify the output actually has audio
            if verify_audio_in_video(output_path):
                print("✅ Audio verification PASSED - proceeding")
                return True
            else:
                print("❌ Audio verification FAILED - stopping to prevent wasted credits")
                return False
        else:
            print(f"FFmpeg failed with return code: {result.returncode}")
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
        
        print(f"=== COMBINE REQUEST ===")
        print(f"Audio URL: {audio_url}")
        print(f"Video URL: {video_url}")
        
        # Generate unique filename
        job_id = str(uuid.uuid4())
        
        # File paths
        audio_path = f'/tmp/audio_{job_id}.mp3'
        video_path = f'/tmp/video_{job_id}.mp4'
        output_path = f'{OUTPUT_DIR}/combined_{job_id}.mp4'
        
        # Download files
        print(f"=== DOWNLOADING AUDIO ===")
        if not download_file(audio_url, audio_path):
            return jsonify({"error": "Failed to download audio"}), 400
            
        print(f"=== DOWNLOADING VIDEO ===")
        if not download_file(video_url, video_path):
            return jsonify({"error": "Failed to download video"}), 400
        
        # Combine with FFmpeg
        print(f"=== COMBINING FILES ===")
        if not combine_audio_video(audio_path, video_path, output_path):
            return jsonify({"error": "Failed to combine audio and video - no audio detected in output"}), 500
        
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
        
        print(f"=== COMBINE-URL REQUEST ===")
        print(f"Audio URL: {audio_url}")
        print(f"Video URL: {video_url}")
        
        # Generate unique filename
        job_id = str(uuid.uuid4())
        
        # File paths
        audio_path = f'/tmp/audio_{job_id}.mp3'
        video_path = f'/tmp/video_{job_id}.mp4'
        output_path = f'{OUTPUT_DIR}/combined_{job_id}.mp4'
        
        # Download files
        print(f"=== DOWNLOADING AUDIO ===")
        if not download_file(audio_url, audio_path):
            return jsonify({"error": "Failed to download audio"}), 400
            
        print(f"=== DOWNLOADING VIDEO ===")
        if not download_file(video_url, video_path):
            return jsonify({"error": "Failed to download video"}), 400
        
        # Combine with FFmpeg
        print(f"=== COMBINING FILES ===")
        if not combine_audio_video(audio_path, video_path, output_path):
            return jsonify({"error": "Failed to combine audio and video - no audio detected in output"}), 500
        
        # Clean up input files
        try:
            os.remove(audio_path)
            os.remove(video_path)
        except:
            pass
        
        # Return URL info instead of file - now with .mp4 extension for Creatomate
        download_url = f"{request.host_url}download/{job_id}.mp4"
        file_size = os.path.getsize(output_path)
        
        print(f"=== SUCCESS ===")
        print(f"Download URL: {download_url}")
        print(f"File size: {file_size}")
        print(f"✅ Audio verified - safe to send to Creatomate")
        
        return jsonify({
            "success": True,
            "download_url": download_url,
            "url": download_url,  # For easy access in n8n
            "job_id": job_id,
            "file_size": file_size,
            "audio_verified": True
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
