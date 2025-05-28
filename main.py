from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
import tempfile
import os
import uuid
import random
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip, AudioFileClip
import logging
from typing import Optional
import subprocess
import shutil

# Fix for Pillow compatibility issue with MoviePy
try:
    from PIL import Image
    if not hasattr(Image, 'ANTIALIAS'):
        Image.ANTIALIAS = Image.LANCZOS
except ImportError:
    pass

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

class RenderRequest(BaseModel):
    hook: str
    body: str
    mood: str
    narration_url: str

# Dropbox configuration
DROPBOX_ACCESS_TOKEN = os.getenv('DROPBOX_ACCESS_TOKEN')

# Mood to background video mapping
MOOD_BACKGROUNDS = {
    "toxic": [
        "https://www.dropbox.com/scl/fi/1d5wkyfmkjfqc2c82u81v/toxic_1.mp4?rlkey=wbfhd7g0sit71kg154ta0wdvf&st=6p0a8roq&dl=1",
        "https://www.dropbox.com/scl/fi/wwriv8a5odi656g2y05gv/toxic_2.mp4?rlkey=kvts8z7uiykaj4vra5m569zy0&st=mah3nq4r&dl=1",
        "https://www.dropbox.com/scl/fi/njmkpxu54gveq1ba6zth2/toxic_3.mp4?rlkey=ushbykoj6h4vd4esjhyu1nm6v&st=9880mq71&dl=1",
        "https://www.dropbox.com/scl/fi/w4gn4yk9ebdqscto4lsyb/toxic_4.mp4?rlkey=ba0far7qnzdzg5q4jojvgxaxb&st=tle45c7a&dl=1"
    ],
    "reflective": [
        "https://www.dropbox.com/scl/fi/62t2lcv7uy1b8ud4k759b/reflective_1.mp4?rlkey=f3gnq1rrdgb84weuh277gpocb&st=8nq0c89g&dl=1",
        "https://www.dropbox.com/scl/fi/w2dg6wu60eo1uzlq2hud9/reflective_2.mp4?rlkey=7aksj0dizcppq9n9mdsh7cx0b&st=r0pqvq4b&dl=1",
        "https://www.dropbox.com/scl/fi/updtympqwasrqjuyaztjj/reflective_3.mp4?rlkey=rzrv3dya4q9rcb9fzm0djt6el&st=rh02abtj&dl=1",
        "https://www.dropbox.com/scl/fi/5lbv91b55s6b4gyfwx2cw/reflective_4.mp4?rlkey=c4pdcjk0dukftymby02gf2lit&st=4p5mijgz&dl=1"
    ],
    "emotional": [
        "https://www.dropbox.com/scl/fi/f1d788uchszdgegb4rdno/emotional_1.mp4?rlkey=x1bxhb4lkdpykd8k1eh4ef7kz&st=500l0spj&dl=1",
        "https://www.dropbox.com/scl/fi/qx9f0s4k1s3ho3xmdln8g/emotional_2.mp4?rlkey=0mj0ky3d220vl8ktgr67c18t6&st=fyd4qpmf&dl=1",
        "https://www.dropbox.com/scl/fi/7i9iv1a7o7l64s356jw58/emotional_3.mp4?rlkey=nuucpgcf73wwsxfwn0uhxvpjf&st=qit4rdvo&dl=1",
        "https://www.dropbox.com/scl/fi/ey5rztxydsc8u4tn32vzb/emotional_4.mp4?rlkey=j42uh4syq22usnffc1tsykjko&st=csm7qdmq&dl=1"
    ],
    "dramatic": [
        "https://www.dropbox.com/scl/fi/ot5f23dg5it8lrkcr0zpw/dramatic_1.mp4?rlkey=4twzcl6a6ro9881yjah35hwrs&st=vav2ndez&dl=1",
        "https://www.dropbox.com/scl/fi/w6bnjmx5qy3rmdv9tsq60/dramatic_2.mp4?rlkey=z1zea0ubguy1t7w9wkbify2gz&st=6srstjau&dl=1",
        "https://www.dropbox.com/scl/fi/25hql0yxs5xug5t4mipde/dramatic_3.mp4?rlkey=1xseyzeosb23byxyygxcz19r8&st=8wbl19bm&dl=1",
        "https://www.dropbox.com/scl/fi/tlv5gas2gqa4ql8j99xx4/dramatic_4.mp4?rlkey=7efikosn98a5laggm2zoc2cfe&st=am9n6nqe&dl=1"
    ]
}

def download_file(url: str, temp_dir: str, filename: str) -> str:
    """Download a file from URL to temporary directory"""
    try:
        # Add headers to mimic browser request
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, stream=True, timeout=60, headers=headers)
        response.raise_for_status()
        
        file_path = os.path.join(temp_dir, filename)
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        logger.info(f"Downloaded {filename} successfully")
        return file_path
    except Exception as e:
        logger.error(f"Error downloading {filename}: {str(e)}")
        raise

def upload_to_dropbox(file_path: str, dropbox_path: str) -> bool:
    """Upload file to Dropbox"""
    try:
        if not DROPBOX_ACCESS_TOKEN:
            logger.error("Dropbox access token not found in environment variables")
            return False
        
        # Check if file exists and get its size
        if not os.path.exists(file_path):
            logger.error(f"File does not exist: {file_path}")
            return False
            
        file_size = os.path.getsize(file_path)
        logger.info(f"Uploading file: {file_path} (size: {file_size} bytes) to {dropbox_path}")
        
        headers = {
            'Authorization': f'Bearer {DROPBOX_ACCESS_TOKEN}',
            'Dropbox-API-Arg': f'{{"path": "{dropbox_path}", "mode": "add", "autorename": true}}',
            'Content-Type': 'application/octet-stream'
        }
        
        with open(file_path, 'rb') as f:
            response = requests.post(
                'https://content.dropboxapi.com/2/files/upload',
                headers=headers,
                data=f,
                timeout=300
            )
        
        if response.status_code == 200:
            response_data = response.json()
            logger.info(f"Successfully uploaded to Dropbox: {dropbox_path}")
            return True
        else:
            logger.error(f"Dropbox upload failed: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Error uploading to Dropbox: {str(e)}")
        return False

def write_video_robust(video_clip, output_path: str, temp_dir: str, video_id: str) -> bool:
    """Write video with multiple fallback methods"""
    
    # Method 1: Try with conservative settings first
    try:
        logger.info("Attempting video write with conservative settings...")
        video_clip.write_videofile(
            output_path,
            codec='libx264',
            audio_codec='aac',
            bitrate="1000k",  # Lower bitrate
            fps=24,
            preset='ultrafast',  # Fastest encoding
            threads=1,  # Single thread to reduce resource usage
            temp_audiofile=os.path.join(temp_dir, f"{video_id}_temp_audio.m4a"),
            remove_temp=True,
            verbose=False,
            logger=None
        )
        logger.info("Video written successfully with conservative settings")
        return True
        
    except Exception as e:
        logger.warning(f"Conservative method failed: {str(e)}")
    
    # Method 2: Try without audio encoding
    try:
        logger.info("Attempting video write without separate audio encoding...")
        video_clip.write_videofile(
            output_path,
            codec='libx264',
            fps=24,
            preset='ultrafast',
            threads=1,
            verbose=False,
            logger=None
        )
        logger.info("Video written successfully without separate audio encoding")
        return True
        
    except Exception as e:
        logger.warning(f"No separate audio method failed: {str(e)}")
    
    # Method 3: Use direct FFMPEG command as fallback
    try:
        logger.info("Attempting direct FFMPEG encoding...")
        
        # Write video without audio first
        temp_video_path = os.path.join(temp_dir, f"{video_id}_temp_video.mp4")
        video_clip.without_audio().write_videofile(
            temp_video_path,
            codec='libx264',
            fps=24,
            preset='ultrafast',
            threads=1,
            verbose=False,
            logger=None
        )
        
        # Write audio separately
        temp_audio_path = os.path.join(temp_dir, f"{video_id}_temp_audio.wav")
        video_clip.audio.write_audiofile(temp_audio_path, verbose=False, logger=None)
        
        # Combine using FFMPEG command
        cmd = [
            'ffmpeg', '-y',  # -y to overwrite
            '-i', temp_video_path,
            '-i', temp_audio_path,
            '-c:v', 'copy',  # Copy video stream
            '-c:a', 'aac',   # Encode audio to AAC
            '-shortest',     # End when shortest stream ends
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            logger.info("Video written successfully using direct FFMPEG")
            return True
        else:
            logger.error(f"FFMPEG command failed: {result.stderr}")
            
    except Exception as e:
        logger.warning(f"Direct FFMPEG method failed: {str(e)}")
    
    return False

@app.post("/render")
def render_video(data: RenderRequest):
    temp_dir = None
    try:
        # Create temporary directory
        temp_dir = tempfile.mkdtemp()
        logger.info(f"Created temp directory: {temp_dir}")
        
        # Generate unique filename
        video_id = str(uuid.uuid4())
        output_filename = f"{video_id}_output.mp4"
        output_path = os.path.join(temp_dir, output_filename)
        
        # Ensure narration URL uses direct download
        narration_url = data.narration_url
        if 'dropbox.com' in narration_url and '&dl=0' in narration_url:
            narration_url = narration_url.replace('&dl=0', '&dl=1')
        
        # Download audio file
        audio_path = download_file(narration_url, temp_dir, f"{video_id}_audio.mp3")
        
        # Verify audio file was downloaded
        if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
            raise HTTPException(status_code=400, detail="Audio file is empty or missing")
        
        # Get background video URL based on mood
        if data.mood.lower() not in MOOD_BACKGROUNDS:
            raise HTTPException(status_code=400, detail=f"Unknown mood: {data.mood}")
        
        background_url = random.choice(MOOD_BACKGROUNDS[data.mood.lower()])
        background_path = download_file(background_url, temp_dir, f"{video_id}_background.mp4")
        
        # Verify background video was downloaded
        if not os.path.exists(background_path) or os.path.getsize(background_path) == 0:
            raise HTTPException(status_code=400, detail="Background video is empty or missing")
        
        # Load audio and video
        logger.info("Loading audio and video files...")
        
        # Load background video with 9:16 aspect ratio optimization
        background_video = VideoFileClip(background_path)
        
        # Target dimensions for 9:16 aspect ratio
        target_width = 720
        target_height = 1280
        
        # Check if video is already close to 9:16 aspect ratio
        current_ratio = background_video.w / background_video.h
        target_ratio = 9/16
        ratio_tolerance = 0.01  # Allow small variations
        
        if abs(current_ratio - target_ratio) <= ratio_tolerance:
            # Video is already 9:16, just resize to target dimensions if needed
            if background_video.w != target_width or background_video.h != target_height:
                background_video = background_video.resize((target_width, target_height))
                logger.info(f"Video was already 9:16, resized to {target_width}x{target_height}")
            else:
                logger.info(f"Video is already perfect 9:16 at {background_video.w}x{background_video.h}")
        else:
            # Video needs aspect ratio correction
            logger.info(f"Converting video from {background_video.w}x{background_video.h} (ratio: {current_ratio:.3f}) to 9:16")
            
            # Calculate scaling to fill the target dimensions
            scale_w = target_width / background_video.w
            scale_h = target_height / background_video.h
            scale = max(scale_w, scale_h)  # Scale to fill
            
            # Resize video
            background_video = background_video.resize(scale)
            
            # Crop to exact 9:16 ratio
            background_video = background_video.crop(
                x_center=background_video.w/2,
                y_center=background_video.h/2,
                width=target_width,
                height=target_height
            )
            logger.info(f"Video converted to 9:16 aspect ratio: {background_video.w}x{background_video.h}")
        
        # Ensure FPS is set
        if not hasattr(background_video, 'fps') or background_video.fps is None:
            background_video = background_video.set_fps(24)
        
        # Limit duration to reduce processing time
        max_duration = min(45, background_video.duration)  # Reduced to 45s max
        background_video = background_video.subclip(0, max_duration)
        
        # Load audio
        audio_clip = AudioFileClip(audio_path)
        audio_duration = min(audio_clip.duration, background_video.duration)
        
        logger.info(f"Using duration: {audio_duration}s, video size: {background_video.w}x{background_video.h}")
        
        # Trim video to match audio
        if background_video.duration > audio_duration:
            background_video = background_video.subclip(0, audio_duration)
        
        # Create simplified overlays to reduce complexity
        clips = [background_video]
        
        # Add title at the top with better formatting
        try:
            title_text = data.hook[:80] + "..." if len(data.hook) > 80 else data.hook
            title_clip = TextClip(
                title_text,
                fontsize=36,  # Larger font for mobile
                color='white',
                font='Arial-Bold',
                stroke_color='black',
                stroke_width=3,
                method='caption',
                size=(target_width-40, None),  # Allow text wrapping
                align='center'
            ).set_position(('center', 80)).set_duration(min(8, audio_duration))
            clips.append(title_clip)
            
        except Exception as e:
            logger.warning(f"Skipping title due to error: {str(e)}")
        
        # Add improved subtitles in the lower third (Crayo.ai style)
        try:
            body_text = data.body[:800] + "..." if len(data.body) > 800 else data.body
            words = body_text.split()
            
            # Create subtitle chunks (3-5 words per line for Crayo.ai style)
            chunk_size = 4  # Even smaller chunks for TikTok style
            chunks = [' '.join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)]
            chunks = chunks[:20]  # Allow more chunks for longer stories
            
            chunk_duration = audio_duration / len(chunks) if chunks else audio_duration
            
            # Position subtitles in the lower third of the screen (Crayo.ai style)
            subtitle_y_position = int(target_height * 0.7)  # 70% down from top (lower third)
            
            for i, chunk in enumerate(chunks):
                start_time = i * chunk_duration
                
                # Create clean text without background (Crayo.ai style)
                subtitle_text = TextClip(
                    chunk,
                    fontsize=38,  # Larger, bold text
                    color='white',
                    font='Arial-Bold',
                    stroke_color='black',
                    stroke_width=3,  # Thick outline for readability
                    method='caption',
                    size=(target_width-80, None),  # More margin from edges
                    align='center'
                )
                
                # Position in lower third with some variation to avoid overlap
                y_offset = (i % 3) * 15  # Slight vertical variation for consecutive subtitles
                final_y_position = subtitle_y_position + y_offset
                
                # Make sure we don't go off screen
                if final_y_position + 60 > target_height:
                    final_y_position = subtitle_y_position
                
                subtitle_final = subtitle_text.set_position(
                    ('center', final_y_position)
                ).set_start(start_time).set_duration(chunk_duration)
                
                clips.append(subtitle_final)
                
        except Exception as e:
            logger.warning(f"Skipping subtitles due to error: {str(e)}")
            
            # Fallback to simple subtitles without background
            try:
                body_text = data.body[:400] + "..." if len(data.body) > 400 else data.body
                simple_subtitle = TextClip(
                    body_text,
                    fontsize=32,
                    color='white',
                    font='Arial-Bold',
                    stroke_color='black',
                    stroke_width=3,
                    method='caption',
                    size=(target_width-60, None),
                    align='center'
                ).set_position(('center', int(target_height * 0.7))).set_duration(audio_duration)
                clips.append(simple_subtitle)
            except Exception as e2:
                logger.warning(f"Even simple subtitles failed: {str(e2)}")
        
        # Compose video
        logger.info("Composing final video...")
        final_video = CompositeVideoClip(clips)
        final_video = final_video.set_fps(24)
        final_video = final_video.set_audio(audio_clip.subclip(0, audio_duration))
        
        # Write video using robust method
        logger.info(f"Writing video to {output_path}")
        write_success = write_video_robust(final_video, output_path, temp_dir, video_id)
        
        # Close clips to free memory
        try:
            for clip in clips:
                clip.close()
            final_video.close()
            audio_clip.close()
        except Exception as e:
            logger.warning(f"Error closing clips: {str(e)}")
        
        if not write_success:
            raise HTTPException(status_code=500, detail="Failed to write video with all methods")
        
        # Verify output file was created
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise HTTPException(status_code=500, detail="Video rendering failed - output file is empty")
        
        logger.info(f"Video successfully created: {os.path.getsize(output_path)} bytes")
        
        # Upload to Dropbox
        clean_hook = "".join(c for c in data.hook if c.isalnum() or c in (' ', '-', '_')).rstrip()
        clean_hook = clean_hook[:50]
        dropbox_path = f"/final_videos/{clean_hook}_{video_id}.mp4"
        upload_success = upload_to_dropbox(output_path, dropbox_path)
        
        if upload_success:
            message = "Video rendered and uploaded to Dropbox successfully"
        else:
            message = "Video rendered successfully, but upload to Dropbox failed"
        
        return {
            "video_path": output_path,
            "dropbox_path": dropbox_path if upload_success else None,
            "message": message
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in render_video: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Video rendering failed: {str(e)}")
    
    finally:
        # Cleanup temporary files
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                logger.info(f"Cleaned up temp directory: {temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to cleanup temp directory: {str(e)}")

@app.get("/")
def read_root():
    return {"message": "Reddit Story Video Renderer API"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 
