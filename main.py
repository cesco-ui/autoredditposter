from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import moviepy.editor as mp
import textwrap
import uuid
import random
import requests
import os
import tempfile
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Dropbox video links mapped by mood
BACKGROUND_CLIPS = {
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

class RenderRequest(BaseModel):
    hook: str
    body: str
    mood: str
    narration_url: str

def download_file(url, out_path):
    try:
        logger.info(f"Downloading file from: {url}")
        # Add headers to mimic browser request
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        r = requests.get(url, timeout=60, headers=headers, stream=True)
        r.raise_for_status()
        
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        
        logger.info(f"Successfully downloaded to: {out_path}")
        return True
    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        return False

def upload_to_dropbox(file_path, dropbox_path, access_token):
    try:
        logger.info(f"Uploading file to Dropbox: {dropbox_path}")
        
        with open(file_path, 'rb') as f:
            file_data = f.read()
        
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/octet-stream',
            'Dropbox-API-Arg': f'{{"path": "{dropbox_path}", "mode": "overwrite"}}'
        }
        
        response = requests.post(
            'https://content.dropboxapi.com/2/files/upload',
            headers=headers,
            data=file_data,
            timeout=300  # 5 minute timeout for upload
        )
        
        if response.status_code == 200:
            logger.info("Successfully uploaded to Dropbox")
            return response.json()
        else:
            logger.error(f"Dropbox upload failed: {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Error uploading to Dropbox: {e}")
        return None

@app.post("/render")
def render_video(data: RenderRequest):
    session_id = str(uuid.uuid4())
    
    # Use temporary directory
    temp_dir = tempfile.mkdtemp()
    narration_path = os.path.join(temp_dir, f"{session_id}_voice.mp3")
    video_path = os.path.join(temp_dir, f"{session_id}_video.mp4")
    output_path = os.path.join(temp_dir, f"{session_id}_output.mp4")
    
    try:
        logger.info(f"Processing request for mood: {data.mood}")
        
        # Ensure narration URL uses direct download
        narration_url = data.narration_url
        if 'dropbox.com' in narration_url and '&dl=0' in narration_url:
            narration_url = narration_url.replace('&dl=0', '&dl=1')
        
        # Download narration
        if not download_file(narration_url, narration_path):
            raise HTTPException(status_code=400, detail="Failed to download narration audio")

        # Verify file was downloaded
        if not os.path.exists(narration_path) or os.path.getsize(narration_path) == 0:
            raise HTTPException(status_code=400, detail="Narration file is empty or missing")

        # Pick random background for mood
        if data.mood not in BACKGROUND_CLIPS:
            raise HTTPException(status_code=400, detail=f"Unknown mood: {data.mood}")
        
        background_url = random.choice(BACKGROUND_CLIPS[data.mood])
        if not download_file(background_url, video_path):
            raise HTTPException(status_code=400, detail="Failed to download background video")

        # Load media with error handling
        try:
            logger.info("Loading video and audio files...")
            video = mp.VideoFileClip(video_path).subclip(0, 60)  # Back to 60 seconds with paid plan
            narration = mp.AudioFileClip(narration_path)
            
            # Ensure audio duration doesn't exceed video duration
            if narration.duration > video.duration:
                narration = narration.subclip(0, video.duration)
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error loading media files: {str(e)}")

        # Hook overlay
        title_clips = []
        try:
            # Limit hook length but allow more with paid plan
            hook_text = data.hook[:150] + "..." if len(data.hook) > 150 else data.hook
            title = mp.TextClip(
                hook_text, 
                fontsize=72, 
                color="white", 
                font="Arial-Bold",
                size=(video.w * 0.95, None)
            )
            title = title.set_position(("center", 50)).set_duration(min(10, video.duration))
            title_clips.append(title)
        except Exception as e:
            logger.warning(f"Error creating title clip: {e}")

        # Captions
        caption_clips = []
        try:
            # Allow more text with paid plan
            body_text = data.body[:1000] + "..." if len(data.body) > 1000 else data.body
            lines = textwrap.wrap(body_text, width=70)
            lines = lines[:20]  # Allow more lines with paid plan
            
            if lines:
                duration_per_line = video.duration / len(lines)
                for i, line in enumerate(lines):
                    start_time = i * duration_per_line
                    if start_time >= video.duration - 1:
                        break
                    
                    caption = mp.TextClip(
                        line, 
                        fontsize=42, 
                        color="white", 
                        font="Arial",
                        size=(video.w * 0.9, None)
                    )
                    caption = caption.set_position(("center", "bottom")).set_start(start_time).set_duration(duration_per_line)
                    caption_clips.append(caption)
        except Exception as e:
            logger.warning(f"Error creating captions: {e}")

        # Compose final video
        try:
            logger.info("Composing final video...")
            clips = [video] + title_clips + caption_clips
            
            final = mp.CompositeVideoClip(clips)
            final = final.set_audio(narration)
            
            # Write video with better quality settings for paid plan
            final.write_videofile(
                output_path, 
                fps=24, 
                codec='libx264',
                audio_codec='aac',
                preset='medium',  # Better quality with paid plan
                temp_audiofile=os.path.join(temp_dir, 'temp-audio.m4a'),
                remove_temp=True,
                verbose=False,
                logger=None
            )
            
            # Clean up clips to free memory
            video.close()
            narration.close()
            final.close()
            for clip in title_clips + caption_clips:
                clip.close()
                
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error rendering video: {str(e)}")

        # Verify output file was created
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise HTTPException(status_code=500, detail="Video rendering failed - output file is empty")

        # Upload to Dropbox final_videos folder
        try:
            # Create a clean filename
            clean_hook = "".join(c for c in data.hook if c.isalnum() or c in (' ', '-', '_')).rstrip()
            clean_hook = clean_hook[:50]  # Limit length
            dropbox_filename = f"/final_videos/{clean_hook}_{session_id}.mp4"
            
            # Get Dropbox access token from environment variable
            DROPBOX_ACCESS_TOKEN = os.getenv('DROPBOX_ACCESS_TOKEN', 'YOUR_DROPBOX_ACCESS_TOKEN_HERE')
            
            upload_result = upload_to_dropbox(output_path, dropbox_filename, DROPBOX_ACCESS_TOKEN)
            
            if upload_result:
                logger.info("Video uploaded to Dropbox successfully")
                return {
                    "video_path": output_path, 
                    "dropbox_path": dropbox_filename,
                    "dropbox_file_id": upload_result.get('id'),
                    "message": "Video rendered and uploaded successfully"
                }
            else:
                logger.warning("Video rendered but Dropbox upload failed")
                return {
                    "video_path": output_path, 
                    "message": "Video rendered successfully, but upload to Dropbox failed"
                }
                
        except Exception as e:
            logger.warning(f"Error during Dropbox upload: {e}")
            return {
                "video_path": output_path, 
                "message": "Video rendered successfully, but upload to Dropbox failed"
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
    finally:
        # Clean up temporary files
        try:
            for file_path in [narration_path, video_path]:
                if os.path.exists(file_path):
                    os.remove(file_path)
        except Exception as e:
            logger.warning(f"Error cleaning up files: {e}")

@app.get("/")
def read_root():
    return {"message": "Reddit Story Video Renderer API"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}
