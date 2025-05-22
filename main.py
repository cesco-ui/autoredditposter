from fastapi import FastAPI, Request
from pydantic import BaseModel
import moviepy.editor as mp
import textwrap
import requests
import os
import uuid

app = FastAPI()

class RenderRequest(BaseModel):
    hook: str
    body: str
    background_clip: str  # file name e.g. "toxic_2.mp4"
    narration_url: str    # URL to download narration audio

@app.post("/render")
def render_story(data: RenderRequest):
    output_id = str(uuid.uuid4())
    video_path = f"/tmp/{output_id}.mp4"
    narration_path = f"/tmp/{output_id}.mp3"

    # Download narration
    r = requests.get(data.narration_url)
    with open(narration_path, "wb") as f:
        f.write(r.content)

    # Load video + audio
    video = mp.VideoFileClip(f"backgrounds/{data.background_clip}").subclip(0, 60)
    narration = mp.AudioFileClip(narration_path)

    # Text overlays
    txt_clip = mp.TextClip(data.hook, fontsize=80, color='white', font='Arial-Bold').set_position("top").set_duration(video.duration)
    
    # Generate timed caption clips
    lines = textwrap.wrap(data.body, width=70)
    caption_clips = []
    duration_per_line = video.duration / len(lines)
    for i, line in enumerate(lines):
        caption = mp.TextClip(line, fontsize=40, color='white', font='Arial').set_position(("center", "bottom"))
        caption_clips.append(caption.set_start(i * duration_per_line).set_duration(duration_per_line))

    final = mp.CompositeVideoClip([video, txt_clip] + caption_clips)
    final = final.set_audio(narration)

    final.write_videofile(video_path, fps=24)

    return {"video_path": video_path}
