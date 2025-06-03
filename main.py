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

def verify_audio_file(audio_path):
    """Lightweight audio file verification - no FFmpeg processing"""
    try:
        if not os.path.exists(audio_path):
            print("❌ Audio file doesn't exist")
            return False
            
        file_size = os.path.getsize(audio_path)
        print(f"📊 Audio file size: {file_size} bytes")
        
        # Basic size check
        if file_size < 1000:  # Less than 1KB
            print("❌ Audio file too small")
            return False
            
        # Quick header check for common audio formats
        with open(audio_path, 'rb') as f:
            header = f.read(12)
            
        # Check for MP3 header
        if header.startswith(b'ID3') or header[0:2] == b'\xff\xfb' or header[0:2] == b'\xff\xfa':
            print("✅ Valid MP3 audio file detected")
            return True
            
        # Check for other audio formats
        if b'ftyp' in header:  # MP4/M4A
            print("✅ Valid MP4/M4A audio file detected")
            return True
            
        if header.startswith(b'RIFF') and b'WAVE' in header:  # WAV
            print("✅ Valid WAV audio file detected")
            return True
            
        # If we can't identify format but file size is reasonable, proceed
        if file_size > 10000:  # 10KB+
            print("⚠️ Unknown audio format but reasonable size - proceeding")
            return True
            
        print("❌ Audio file format not recognized")
        return False
        
    except Exception as e:
        print(f"❌ Error verifying audio file: {e}")
        return False

def parse_ffmpeg_output(stderr_output):
    """Parse FFmpeg stderr to verify audio was processed successfully"""
    try:
        stderr_lower = stderr_output.lower()
        
        # Check if FFmpeg detected audio input
        has_audio_input = (
            'audio:' in stderr_lower or 
            'stream #1:0: audio' in stderr_lower or
            'mp3' in stderr_lower or
            'aac' in stderr_lower
        )
        
        # Check if FFmpeg processed audio output
        has_audio_output = (
            'audio:' in stderr_lower and 'kb' in stderr_lower
        )
        
        # Look for audio encoder confirmation
        audio_encoded = (
            'aac' in stderr_lower and 
            ('hz' in stderr_lower or 'khz' in stderr_lower)
        )
        
        if has_audio_input and (has_audio_output or audio_encoded):
            print("✅ FFmpeg confirmed audio processing")
            return True
        else:
            print("❌ FFmpeg output suggests no audio was processed")
            print(f"Audio input detected: {has_audio_input}")
            print(f"Audio output detected: {has_audio_output}")
            print(f"Audio encoding detected: {audio_encoded}")
            return False
            
    except Exception as e:
        print(f"⚠️ Error parsing FFmpeg output: {e}")
        return True  # Default to success if we can't parse

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
    """Combine audio and video using FFmpeg with EXPLICIT STREAM MAPPING"""
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
        
        # LIGHTWEIGHT AUDIO VERIFICATION - before FFmpeg
        print("🔍 Verifying audio file...")
        if not verify_audio_file(audio_path):
            print("❌ Audio file verification failed - stopping to prevent Creatomate waste")
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
        
        # EXPLICIT STREAM MAPPING - CRITICAL FOR AUDIO REPLACEMENT
        cmd = [
            ffmpeg_path,
            '-i', video_path,           # Input 0: video
            '-i', audio_path,           # Input 1: audio
            '-map', '0:v:0',           # Map video stream from input 0
            '-map', '1:a:0',           # Map audio stream from input 1 (YOUR audio!)
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
        
        print(f"Running FFmpeg with explicit stream mapping: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        print(f"FFmpeg return code: {result.returncode}")
        print(f"FFmpeg stdout: {result.stdout}")
        print(f"FFmpeg stderr: {result.stderr}")
        
        if result.returncode == 0:
            output_size = os.path.getsize(output_path)
            print(f"FFmpeg success. Output file size: {output_size} bytes")
            
            # SMART VERIFICATION - parse FFmpeg output (no extra processing)
            print("🔍 Verifying audio was processed by FFmpeg...")
            if not parse_ffmpeg_output(result.stderr):
                print("❌ FFmpeg output suggests audio processing failed - stopping")
                return False
            
            # Basic output file size sanity check
            if output_size < video_size * 0.8:  # Output should be at least 80% of video size
                print(f"❌ Output file unexpectedly small: {output_size} vs input video {video_size}")
                return False
                
            print("✅ All verifications passed - safe to send to Creatomate")
            return True
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
        "ffmpeg": "available" if ffmpeg_available else "not found",
        "audio_verification": "enabled"
    })

@app.route('/combine-url', methods=['POST'])
def combine_videos_url():
    """Main endpoint for combining audio and video with smart verification"""
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
        
        # Combine with FFmpeg - with smart verification
        print(f"=== COMBINING FILES ===")
        if not combine_audio_video(audio_path, video_path, output_path):
            return jsonify({"error": "Failed to combine audio and video - audio verification failed"}), 500
        
        # Clean up input files
        try:
            os.remove(audio_path)
            os.remove(video_path)
        except:
            pass
        
        # Return URL info instead of file
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
