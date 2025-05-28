from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
import tempfile
import os
import uuid
import random
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip, AudioFileClip, ImageClip
import logging
from typing import Optional
import subprocess
import shutil
import asyncio
import concurrent.futures
from datetime import datetime

# Fix for Pillow compatibility issue with MoviePy
try:
    from PIL import Image
    if not hasattr(Image, 'ANTIALIAS'):
        Image.ANTIALIAS = Image.LANCZOS
except ImportError:
    pass

def expand_reddit_acronyms(text: str) -> str:
    """Expand common Reddit acronyms for better text-to-speech"""
    expansions = {
        'AITA': 'Am I the A Hole',
        'AITAH': 'Am I the A Hole',
        'NTA': 'Not the A Hole',
        'YTA': 'You are the A Hole',
        'ESH': 'Everyone Sucks Here',
        'NAH': 'No A Holes Here',
        'INFO': 'I need more information',
        'WIBTA': 'Would I be the A Hole',
        'WIBTAH': 'Would I be the A Hole',
        'SO': 'significant other',
        'BF': 'boyfriend',
        'GF': 'girlfriend',
        'DH': 'dear husband',
        'DW': 'dear wife',
        'MIL': 'mother in law',
        'FIL': 'father in law',
        'SIL': 'sister in law',
        'BIL': 'brother in law',
        'DIL': 'daughter in law',
        'SAHM': 'stay at home mom',
        'SAHD': 'stay at home dad'
    }
    
    # Replace acronyms (case insensitive, whole words only)
    import re
    for acronym, expansion in expansions.items():
        # Use word boundaries to avoid partial matches
        pattern = r'\b' + re.escape(acronym) + r'\b'
        text = re.sub(pattern, expansion, text, flags=re.IGNORECASE)
    
    return text

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

class RenderRequest(BaseModel):
    hook: str
    body: str
    mood: str
    narration_url: str

class BatchRenderRequest(BaseModel):
    videos: list[RenderRequest]
    max_concurrent: int = 3  # Limit concurrent processing to avoid resource exhaustion

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
    
    # Method 1: Ultra-conservative settings for maximum compatibility
    try:
        logger.info("Attempting video write with ultra-conservative settings...")
        video_clip.write_videofile(
            output_path,
            codec='libx264',
            audio_codec='aac',
            bitrate="800k",  # Even lower bitrate
            fps=24,
            preset='ultrafast',
            threads=1,  # Single thread
            audio_bitrate="128k",  # Lower audio bitrate
            temp_audiofile=os.path.join(temp_dir, f"{video_id}_temp_audio.m4a"),
            remove_temp=True,
            verbose=False,
            logger=None,
            ffmpeg_params=['-movflags', '+faststart']  # Optimize for streaming
        )
        logger.info("Video written successfully with ultra-conservative settings")
        return True
        
    except Exception as e:
        logger.warning(f"Ultra-conservative method failed: {str(e)}")
    
    # Method 2: Minimal settings fallback
    try:
        logger.info("Attempting video write with minimal settings...")
        video_clip.write_videofile(
            output_path,
            codec='libx264',
            fps=24,
            preset='veryfast',
            threads=1,
            verbose=False,
            logger=None,
            temp_audiofile=os.path.join(temp_dir, f"{video_id}_temp_audio_2.m4a"),
            remove_temp=True
        )
        logger.info("Video written successfully with minimal settings")
        return True
        
    except Exception as e:
        logger.warning(f"Minimal settings method failed: {str(e)}")
    
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
    render_start_time = datetime.now()
    
    try:
        logger.info(f"=== RENDER START ===")
        logger.info(f"Hook: {data.hook[:100]}...")
        logger.info(f"Mood: {data.mood}")
        logger.info(f"Audio URL: {data.narration_url}")
        
        # Create temporary directory
        temp_dir = tempfile.mkdtemp()
        logger.info(f"Created temp directory: {temp_dir}")
        
        # Generate unique filename
        video_id = str(uuid.uuid4())
        output_filename = f"{video_id}_output.mp4"
        output_path = os.path.join(temp_dir, output_filename)
        
        # Expand Reddit acronyms for better text-to-speech
        expanded_hook = expand_reddit_acronyms(data.hook)
        expanded_body = expand_reddit_acronyms(data.body)
        logger.info(f"Expanded acronyms in text for better narration")
        
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
        
        # Adaptive target dimensions based on available resources
        try:
            # Try high quality first
            target_width = 720
            target_height = 1280
            
            # Check video file size to determine if we should reduce resolution
            video_file_size = os.path.getsize(background_path)
            if video_file_size > 50 * 1024 * 1024:  # If video > 50MB, use lower resolution
                target_width = 540
                target_height = 960
                logger.info("Large video detected, using reduced resolution for better performance")
                
        except Exception as e:
            # Fallback to safe resolution
            target_width = 540
            target_height = 960
            logger.warning(f"Resolution detection failed, using safe resolution: {e}")
        
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
        
        # Add title at the top with improved bubbly styling
        try:
            # Use original hook for display (preserves acronyms visually)
            title_text = data.hook[:80] + "..." if len(data.hook) > 80 else data.hook
            
            # Create main title text
            title_main = TextClip(
                title_text,
                fontsize=42,  # Larger, bubbly size
                color='white',
                font='Arial-Bold',
                stroke_color='black',
                stroke_width=4,  # Thick outline for bubbly effect
                method='caption',
                size=(target_width-60, None),  # Allow text wrapping
                align='center'
            )
            
            # Add drop shadow for bubbly depth effect
            try:
                title_shadow = TextClip(
                    title_text,
                    fontsize=42,
                    color='rgba(0,0,0,0.6)',  # Semi-transparent black shadow
                    font='Arial-Bold',
                    method='caption',
                    size=(target_width-60, None),
                    align='center'
                )
                
                # Composite title with shadow for bubbly effect
                shadow_offset = 4
                bubbly_title = CompositeVideoClip([
                    title_shadow.set_position(('center', 80 + shadow_offset)),
                    title_main.set_position(('center', 80))
                ]).set_duration(min(10, audio_duration))  # Show title longer
                
                clips.append(bubbly_title)
                logger.info("Added bubbly title with shadow effect")
                
            except Exception as shadow_error:
                # Fallback to simple title if shadow fails
                logger.warning(f"Title shadow failed, using simple title: {shadow_error}")
                title_clip = title_main.set_position(('center', 80)).set_duration(min(10, audio_duration))
                clips.append(title_clip)
            
        except Exception as e:
            logger.warning(f"Skipping title due to error: {str(e)}")
        
        # Add improved subtitles with perfect audio sync and bubbly styling
        try:
            logger.info("Starting subtitle generation...")
            body_text = expanded_body[:1000] + "..." if len(expanded_body) > 1000 else expanded_body
            
            # Smarter subtitle chunking that considers punctuation and speech patterns
            import re
            
            # First, split by sentences or major punctuation
            sentences = re.split(r'[.!?]+', body_text)
            
            chunks = []
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                    
                words = sentence.split()
                if len(words) <= 3:
                    # Short sentence, use as single chunk
                    chunks.append(sentence)
                else:
                    # Split longer sentences into 2-3 word chunks
                    chunk_size = 2
                    for i in range(0, len(words), chunk_size):
                        chunk = ' '.join(words[i:i + chunk_size])
                        chunks.append(chunk)
            
            # Limit total chunks for performance
            chunks = chunks[:25]  # Reduced for better performance
            
            logger.info(f"Created {len(chunks)} subtitle chunks")
            
            # Perfect timing calculation for audio sync
            # Dynamic subtitle start delay based on audio duration
            subtitle_start_delay = min(2.0, audio_duration * 0.05)  # 5% of audio or 2s max
            subtitle_end_buffer = 1.0  # Leave buffer at end
            subtitle_duration = max(audio_duration - subtitle_start_delay - subtitle_end_buffer, 5)
            
            # Better chunk duration calculation - account for natural speech patterns
            base_chunk_duration = subtitle_duration / len(chunks) if chunks else audio_duration
            # Add slight overlap for smoother reading experience
            chunk_duration = max(base_chunk_duration, 1.5)  # Minimum 1.5s per chunk for readability
            
            # Position subtitles in lower-middle area for readability
            subtitle_y_position = int(target_height * 0.65)  # 65% down from top
            
            logger.info(f"Subtitle timing: delay={subtitle_start_delay}s, duration={subtitle_duration}s, chunk_duration={chunk_duration}s")
            
            subtitle_clips_added = 0
            for i, chunk in enumerate(chunks):
                try:
                    # Perfect timing sync
                    start_time = subtitle_start_delay + (i * chunk_duration)
                    
                    logger.info(f"Processing subtitle {i+1}/{len(chunks)}: '{chunk}'")
                    
                    # Create bubbly, easy-to-read subtitle text with error handling
                    try:
                        subtitle_main = TextClip(
                            chunk,
                            fontsize=56,  # Even larger for mobile readability
                            color='white',
                            font='Arial-Bold',
                            stroke_color='black',
                            stroke_width=6,  # Very thick outline for bubbly effect
                            method='caption',
                            size=(target_width-40, None),
                            align='center'
                        )
                        
                        # Validate the subtitle was created properly
                        if subtitle_main is None or subtitle_main.duration <= 0:
                            raise Exception("TextClip creation returned invalid clip")
                            
                    except Exception as font_error:
                        logger.warning(f"Font rendering failed for chunk {i+1}, trying simpler approach: {font_error}")
                        # Fallback to simpler text clip
                        try:
                            subtitle_main = TextClip(
                                chunk,
                                fontsize=48,
                                color='white',
                                font='Arial',
                                method='caption',
                                size=(target_width-60, None),
                                align='center'
                            )
                            
                            # Validate fallback clip
                            if subtitle_main is None or subtitle_main.duration <= 0:
                                raise Exception("Fallback TextClip also failed")
                                
                        except Exception as fallback_error:
                            logger.error(f"Even fallback font rendering failed: {fallback_error}")
                            continue  # Skip this subtitle chunk entirely
                    
                    logger.info(f"Created main subtitle text for chunk {i+1}")
                    
                    # Position and time the subtitle
                    subtitle_final = subtitle_main.set_position(
                        ('center', subtitle_y_position)
                    ).set_start(start_time).set_duration(chunk_duration * 1.2)  # Slightly reduced overlap
                    
                    clips.append(subtitle_final)
                    subtitle_clips_added += 1
                    logger.info(f"Added subtitle {i+1} successfully")
                    
                except Exception as chunk_error:
                    logger.error(f"Failed to create subtitle chunk {i+1}: {str(chunk_error)}")
                    # Try simpler fallback for this chunk
                    try:
                        simple_chunk = TextClip(
                            chunk,
                            fontsize=40,
                            color='white'
                        ).set_position(('center', subtitle_y_position)).set_start(
                            subtitle_start_delay + (i * chunk_duration)
                        ).set_duration(chunk_duration)
                        clips.append(simple_chunk)
                        subtitle_clips_added += 1
                        logger.info(f"Added simple fallback subtitle {i+1}")
                    except:
                        logger.error(f"Even simple fallback failed for chunk {i+1}, skipping")
                        continue
            
            logger.info(f"Successfully added {subtitle_clips_added} subtitle clips")
                
        except Exception as e:
            logger.error(f"Major subtitle generation error: {str(e)}")
            
            # Fallback to simple subtitles with bubbly styling
            try:
                logger.info("Attempting fallback subtitle generation...")
                body_text = expanded_body[:600] + "..." if len(expanded_body) > 600 else expanded_body
                simple_subtitle = TextClip(
                    body_text,
                    fontsize=50,
                    color='white',
                    font='Arial-Bold',
                    stroke_color='black',
                    stroke_width=5,
                    method='caption',
                    size=(target_width-60, None),
                    align='center'
                ).set_position(('center', int(target_height * 0.65))).set_start(2.0).set_duration(audio_duration - 3)
                clips.append(simple_subtitle)
                logger.info("Added fallback subtitle successfully")
            except Exception as e2:
                logger.error(f"Even simple subtitles failed: {str(e2)}")
        
        # Compose video
        logger.info("Composing final video...")
        
        # Validate all clips before composition
        valid_clips = []
        for i, clip in enumerate(clips):
            try:
                if clip is not None and hasattr(clip, 'duration') and clip.duration > 0:
                    # Test if clip can generate a frame
                    test_frame = clip.get_frame(0)
                    if test_frame is not None:
                        valid_clips.append(clip)
                        logger.info(f"Clip {i} validated successfully")
                    else:
                        logger.warning(f"Clip {i} returns None frame, skipping")
                else:
                    logger.warning(f"Clip {i} is invalid or has no duration, skipping")
            except Exception as e:
                logger.warning(f"Clip {i} validation failed: {str(e)}, skipping")
        
        if not valid_clips:
            raise HTTPException(status_code=500, detail="No valid clips to compose video")
        
        logger.info(f"Using {len(valid_clips)} valid clips out of {len(clips)} total clips")
        
        final_video = CompositeVideoClip(valid_clips)
        final_video = final_video.set_fps(24)
        final_video = final_video.set_audio(audio_clip.subclip(0, audio_duration))
        
        # Immediate cleanup of individual clips to free memory before encoding
        try:
            for clip in clips:
                if hasattr(clip, 'close'):
                    clip.close()
            audio_clip.close()
            logger.info("Individual clips cleaned up before encoding")
        except Exception as e:
            logger.warning(f"Error during early clip cleanup: {str(e)}")
        
        # Force garbage collection to free memory
        import gc
        gc.collect()
        
        # Write video using robust method
        logger.info(f"Writing video to {output_path}")
        write_success = write_video_robust(final_video, output_path, temp_dir, video_id)
        
        # Close final video clip immediately after writing
        try:
            final_video.close()
            logger.info("Final video clip closed")
        except Exception as e:
            logger.warning(f"Error closing final video clip: {str(e)}")
        
        # Force another garbage collection after encoding
        gc.collect()
        
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
        
        # Calculate render statistics
        render_end_time = datetime.now()
        total_render_time = (render_end_time - render_start_time).total_seconds()
        
        logger.info(f"=== RENDER COMPLETE ===")
        logger.info(f"Total render time: {total_render_time:.2f} seconds")
        logger.info(f"Output file size: {os.path.getsize(output_path) / (1024*1024):.2f} MB")
        logger.info(f"Upload success: {upload_success}")
        
        return {
            "video_path": output_path,
            "dropbox_path": dropbox_path if upload_success else None,
            "message": message,
            "render_time_seconds": total_render_time,
            "file_size_mb": round(os.path.getsize(output_path) / (1024*1024), 2)
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

def render_single_video_safe(video_data: RenderRequest) -> dict:
    """Wrapper function for safe single video rendering in batch processing"""
    try:
        # Call the main render function but return dict instead of HTTP response
        result = render_video(video_data)
        return {
            "success": True,
            "video_data": video_data.dict(),
            "result": result,
            "error": None
        }
    except Exception as e:
        logger.error(f"Error rendering video for hook '{video_data.hook[:50]}...': {str(e)}")
        return {
            "success": False,
            "video_data": video_data.dict(),
            "result": None,
            "error": str(e)
        }

@app.post("/render-batch")
async def render_batch_videos(batch_data: BatchRenderRequest):
    """Render multiple videos concurrently"""
    start_time = datetime.now()
    logger.info(f"Starting batch render of {len(batch_data.videos)} videos")
    
    # Limit concurrent processing to avoid overwhelming the server
    max_workers = min(batch_data.max_concurrent, len(batch_data.videos), 3)
    
    results = []
    successful_renders = 0
    failed_renders = 0
    
    # Process videos in batches using ThreadPoolExecutor
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all video rendering tasks
        future_to_video = {
            executor.submit(render_single_video_safe, video): video 
            for video in batch_data.videos
        }
        
        # Collect results as they complete
        for future in concurrent.futures.as_completed(future_to_video):
            result = future.result()
            results.append(result)
            
            if result["success"]:
                successful_renders += 1
                logger.info(f"✅ Video {successful_renders}/{len(batch_data.videos)} completed successfully")
            else:
                failed_renders += 1
                logger.error(f"❌ Video failed: {result['error']}")
    
    end_time = datetime.now()
    total_time = (end_time - start_time).total_seconds()
    
    # Prepare batch summary
    summary = {
        "batch_id": str(uuid.uuid4()),
        "total_videos": len(batch_data.videos),
        "successful_renders": successful_renders,
        "failed_renders": failed_renders,
        "processing_time_seconds": total_time,
        "average_time_per_video": total_time / len(batch_data.videos) if batch_data.videos else 0,
        "results": results
    }
    
    logger.info(f"Batch processing completed: {successful_renders}/{len(batch_data.videos)} successful in {total_time:.1f}s")
    
    return summary

@app.get("/")
def read_root():
    return {"message": "Reddit Story Video Renderer API"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 
