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
    """Lightweight audio file verification"""
    try:
        if not os.path.exists(audio_path):
            print(f"❌ Audio file does not exist: {audio_path}")
            return False
            
        file_size = os.path.getsize(audio_path)
        print(f"📊 Audio file size: {file_size} bytes")
        
        if file_size < 1000:  # Less than 1KB
            print(f"❌ Audio file too small: {file_size} bytes")
            return False
            
        # Check file headers for common audio formats
        with open(audio_path, 'rb') as f:
            header = f.read(12)
            
        # MP3 header check
        if header.startswith(b'ID3') or header[0:2] in [b'\xff\xfb', b'\xff\xf3', b'\xff\xf2']:
            print("✅ Valid MP3 audio file detected")
            return True
            
        # MP4/M4A header check  
        if b'ftyp' in header:
            print("✅ Valid MP4 audio file detected")
            return True
            
        # WAV header check
        if header.startswith(b'RIFF') and b'WAVE' in header:
            print("✅ Valid WAV audio file detected")
            return True
            
        print(f"⚠️ Unknown audio format, but proceeding (size: {file_size} bytes)")
        return True
        
    except Exception as e:
        print(f"❌ Error verifying audio file: {str(e)}")
        return False

def download_file(url, target_path):
    """Download file with enhanced headers for Dropbox compatibility"""
    try:
        print(f"Attempting to download: {url}")
        print(f"Target filename: {target_path}")
        
        # Check if it's a Dropbox temporary link
        is_dropbox_temp = 'dropboxusercontent.com' in url
        print(f"Dropbox temporary link detected: {is_dropbox_temp}")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
        response = requests.get(url, headers=headers, stream=True, allow_redirects=True, timeout=30)
        print(f"Response status: {response.status_code}")
        print(f"Response headers: {dict(response.headers)}")
        print(f"Final URL after redirects: {response.url}")
        print(f"Content-Type: {response.headers.get('Content-Type', 'unknown')}")
        
        response.raise_for_status()
        
        total_size = 0
        with open(target_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    total_size += len(chunk)
        
        print(f"Downloaded {total_size} bytes to {target_path}")
        print(f"Total streamed: {total_size} bytes")
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"Request error downloading {url}: {str(e)}")
        return False
    except Exception as e:
        print(f"Unexpected error downloading {url}: {str(e)}")
        return False

def parse_ffmpeg_output(stderr_output):
    """Parse FFmpeg stderr to confirm audio processing"""
    try:
        # Look for audio stream confirmation
        audio_indicators = [
            "Stream #1:0: Audio:",
            "-> #0:1 (",
            "aac (native)",
            "audio:"
        ]
        
        for indicator in audio_indicators:
            if indicator in stderr_output:
                return True
                
        return False
    except:
        return False

def combine_audio_video(audio_path, video_path, output_path):
    """Combine audio and video using FFmpeg with explicit stream mapping"""
    try:
        print("🔍 Verifying audio file...")
        if not verify_audio_file(audio_path):
            return False, "Invalid audio file"
            
        # Use explicit FFmpeg path and stream mapping
        ffmpeg_path = shutil.which('ffmpeg') or '/usr/bin/ffmpeg'
        
        # EXPLICIT STREAM MAPPING - force video from input 0, audio from input 1
        cmd = [
            ffmpeg_path,
            '-i', video_path,           # Input 0: video
            '-i', audio_path,           # Input 1: audio  
            '-map', '0:v:0',           # Map video stream from input 0
            '-map', '1:a:0',           # Map audio stream from input 1
            '-c:v', 'copy',            # Copy video codec (no re-encoding)
            '-c:a', 'aac',             # Convert audio to AAC
            '-b:a', '128k',            # Audio bitrate
            '-ar', '44100',            # Audio sample rate
            '-ac', '2',                # Stereo audio
            '-shortest',               # End when shortest stream ends
            '-avoid_negative_ts', 'make_zero',
            '-y',                      # Overwrite output
            output_path
        ]
        
        print(f"Running FFmpeg with explicit stream mapping: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        print(f"FFmpeg return code: {result.returncode}")
        print(f"FFmpeg stdout: {result.stdout}")
        print(f"FFmpeg stderr: {result.stderr}")
        
        if result.returncode == 0:
            if os.path.exists(output_path):
                output_size = os.path.getsize(output_path)
                print(f"FFmpeg success. Output file size: {output_size} bytes")
                
                # Verify audio was processed by checking FFmpeg output
                print("🔍 Verifying audio was processed by FFmpeg...")
                if parse_ffmpeg_output(result.stderr):
                    print("✅ FFmpeg confirmed audio processing")
                    return True, "Success"
                else:
                    print("⚠️ Could not confirm audio processing, but FFmpeg succeeded")
                    return True, "Success"
            else:
                return False, "Output file not created"
        else:
            return False, f"FFmpeg failed: {result.stderr}"
            
    except subprocess.TimeoutExpired:
        return False, "FFmpeg timeout"
    except Exception as e:
        return False, f"Error combining files: {str(e)}"

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    ffmpeg_available = check_ffmpeg()
    return jsonify({
        'status': 'healthy',
        'ffmpeg': 'available' if ffmpeg_available else 'not available'
    })

@app.route('/combine-url', methods=['POST'])
def combine_url():
    """Combine audio and video from URLs"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
            
        audio_url = data.get('audio_url')
        video_url = data.get('video_url')
        
        print("=== COMBINE-URL REQUEST ===")
        print(f"Audio URL: {audio_url}")
        print(f"Video URL: {video_url}")
        
        if not audio_url or not video_url:
            return jsonify({'error': 'Missing audio_url or video_url'}), 400
        
        # Generate unique ID for this job
        job_id = str(uuid.uuid4())
        
        # Create temporary file paths
        audio_temp = f'/tmp/audio_{job_id}.mp3'
        video_temp = f'/tmp/video_{job_id}.mp4'
        output_path = f'{OUTPUT_DIR}/combined_{job_id}.mp4'
        
        try:
            # Download audio
            print("=== DOWNLOADING AUDIO ===")
            if not download_file(audio_url, audio_temp):
                return jsonify({'error': 'Failed to download audio'}), 400
            
            # Download video  
            print("=== DOWNLOADING VIDEO ===")
            if not download_file(video_url, video_temp):
                return jsonify({'error': 'Failed to download video'}), 400
            
            # Combine files
            print("=== COMBINING FILES ===")
            audio_size = os.path.getsize(audio_temp)
            video_size = os.path.getsize(video_temp)
            print(f"Audio file size: {audio_size} bytes")
            print(f"Video file size: {video_size} bytes")
            
            success, message = combine_audio_video(audio_temp, video_temp, output_path)
            
            if success:
                return jsonify({
                    'success': True,
                    'job_id': job_id,
                    'download_url': f'/download/{job_id}',
                    'message': message
                })
            else:
                return jsonify({'error': message}), 500
                
        finally:
            # Clean up temporary files
            for temp_file in [audio_temp, video_temp]:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                except:
                    pass
                    
    except Exception as e:
        print(f"Error in combine_url: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/download/<job_id>', methods=['GET'])
def download(job_id):
    """Download the combined video"""
    try:
        output_path = f'{OUTPUT_DIR}/combined_{job_id}.mp4'
        
        if not os.path.exists(output_path):
            return jsonify({'error': 'File not found'}), 404
            
        return send_file(output_path, as_attachment=True, download_name=f'combined_{job_id}.mp4')
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download/<job_id>.mp4', methods=['GET'])
def download_direct(job_id):
    """Direct download link for the combined video"""
    return download(job_id)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
