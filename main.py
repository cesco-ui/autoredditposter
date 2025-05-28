from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
import tempfile
import os
import uuid
import random
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
import logging
from typing import Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

class VideoRequest(BaseModel):
    hook: str
    body: str
    mood: str
    audio_url: str

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
        response = requests.get(url, stream=True, timeout=30)
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
        
        # Log headers for debugging (without the token)
        debug_headers = headers.copy()
        debug_headers['Authorization'] = 'Bearer [REDACTED]'
        logger.info(f"Upload headers: {debug_headers}")
        
        with open(file_path, 'rb') as f:
            response = requests.post(
                'https://content.dropboxapi.com/2/files/upload',
                headers=headers,
                data=f,
                timeout=300  # Increased timeout for large files
            )
        
        logger.info(f"Dropbox API response status: {response.status_code}")
        
        if response.status_code == 200:
            response_data = response.json()
            logger.info(f"Successfully uploaded to Dropbox: {dropbox_path}")
            logger.info(f"Dropbox response: {response_data}")
            return True
        else:
            logger.error(f"Dropbox upload failed: {response.status_code}")
            logger.error(f"Response headers: {response.headers}")
            logger.error(f"Response text: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        logger.error("Dropbox upload timed out")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error during Dropbox upload: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error uploading to Dropbox: {str(e)}")
        return False

def create_subtitle_clips(text: str, duration: float, video_size: tuple) -> list:
    """Create scrolling subtitle clips"""
    try:
        # Split text into chunks for better readability
        words = text.split()
        chunks = []
        chunk_size = 15  # words per chunk
        
        for i in range(0, len(words), chunk_size):
            chunk = ' '.join(words[i:i + chunk_size])
            chunks.append(chunk)
        
        subtitle_clips = []
        chunk_duration = duration / len(chunks) if chunks else duration
        
        for i, chunk in enumerate(chunks):
            start_time = i * chunk_duration
            
            subtitle = TextClip(
                chunk,
                fontsize=24,
                color='white',
                font='Arial-Bold',
                stroke_color='black',
                stroke_width=2,
                method='caption',
                size=(video_size[0] - 40, None)
            ).set_position(('center', 'bottom')).set_start(start_time).set_duration(chunk_duration)
            
            subtitle_clips.append(subtitle)
        
        return subtitle_clips
        
    except Exception as e:
        logger.error(f"Error creating subtitle clips: {str(e)}")
        return []

@app.post("/render-video")
async def render_video(request: VideoRequest):
    temp_dir = None
    try:
        # Create temporary directory
        temp_dir = tempfile.mkdtemp()
        logger.info(f"Created temp directory: {temp_dir}")
        
        # Generate unique filename
        video_id = str(uuid.uuid4())
        output_filename = f"{video_id}_output.mp4"
        output_path = os.path.join(temp_dir, output_filename)
        
        # Download audio file
        audio_path = download_file(request.audio_url, temp_dir, f"{video_id}_audio.mp3")
        
        # Get background video URL based on mood
        background_url = random.choice(MOOD_BACKGROUNDS.get(request.mood.lower(), MOOD_BACKGROUNDS["reflective"]))
        background_path = download_file(background_url, temp_dir, f"{video_id}_background.mp4")
        
        # Load video and audio
        logger.info("Loading video and audio files")
        background_video = VideoFileClip(background_path)
        audio_clip = VideoFileClip(audio_path).audio
        
        # Get audio duration and limit to 60 seconds
        audio_duration = min(audio_clip.duration, 60)
        
        # Trim background video to match audio duration
        if background_video.duration < audio_duration:
            # Loop the background video if it's shorter than audio
            background_video = background_video.loop(duration=audio_duration)
        else:
            background_video = background_video.subclip(0, audio_duration)
        
        # Create title overlay
        title_clip = TextClip(
            request.hook,
            fontsize=32,
            color='white',
            font='Arial-Bold',
            stroke_color='black',
            stroke_width=3,
            method='caption',
            size=(background_video.w - 40, None)
        ).set_position(('center', 'top')).set_duration(min(5, audio_duration))
        
        # Create subtitle clips
        subtitle_clips = create_subtitle_clips(request.body, audio_duration, (background_video.w, background_video.h))
        
        # Compose final video
        logger.info("Composing final video")
        final_clips = [background_video, title_clip] + subtitle_clips
        final_video = CompositeVideoClip(final_clips)
        final_video = final_video.set_audio(audio_clip.subclip(0, audio_duration))
        
        # Write video file
        logger.info(f"Writing video to {output_path}")
        final_video.write_videofile(
            output_path,
            codec='libx264',
            audio_codec='aac',
            temp_audiofile=os.path.join(temp_dir, f"{video_id}_temp_audio.m4a"),
            remove_temp=True,
            fps=24,
            preset='medium'
        )
        
        # Close clips to free memory
        background_video.close()
        audio_clip.close()
        final_video.close()
        
        # Upload to Dropbox
        dropbox_path = f"/final_videos/{output_filename}"
        upload_success = upload_to_dropbox(output_path, dropbox_path)
        
        if upload_success:
            message = "Video rendered and uploaded to Dropbox successfully"
        else:
            message = "Video rendered successfully, but upload to Dropbox failed"
        
        return {
            "video_path": output_path,
            "message": message
        }
        
    except Exception as e:
        logger.error(f"Error in render_video: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Video rendering failed: {str(e)}")
    
    finally:
        # Cleanup temporary files
        if temp_dir and os.path.exists(temp_dir):
            try:
                import shutil
                shutil.rmtree(temp_dir)
                logger.info(f"Cleaned up temp directory: {temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to cleanup temp directory: {str(e)}")

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 
