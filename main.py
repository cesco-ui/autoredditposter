from fastapi import FastAPI
from pydantic import BaseModel
import moviepy.editor as mp
import textwrap
import uuid
import random
import requests
import os

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
    r = requests.get(url)
    with open(out_path, "wb") as f:
        f.write(r.content)

@app.post("/render")
def render_video(data: RenderRequest):
    session_id = str(uuid.uuid4())
    narration_path = f"/tmp/{session_id}_voice.mp3"
    video_path = f"/tmp/{session_id}_video.mp4"
    output_path = f"/tmp/{session_id}_output.mp4"

    # Download narration
    download_file(data.narration_url, narration_path)

    # Pick random background for mood
    if data.mood not in BACKGROUND_CLIPS:
        return {"error": f"Unknown mood: {data.mood}"}
    background_url = random.choice(BACKGROUND_CLIPS[data.mood])
    download_file(background_url, video_path)

    # Load media
    video = mp.VideoFileClip(video_path).subclip(0, 60)
    narration = mp.AudioFileClip(narration_path)

    # Hook overlay
    title = mp.TextClip(data.hook, fontsize=72, color="white", font="Arial-Bold", size=(video.w * 0.95, None))
    title = title.set_position(("center", 50)).set_duration(video.duration)

    # Captions
    lines = textwrap.wrap(data.body, width=70)
    duration_per_line = video.duration / len(lines)
    caption_clips = []
    for i, line in enumerate(lines):
        caption = mp.TextClip(line, fontsize=42, color="white", font="Arial", size=(video.w * 0.9, None))
        caption = caption.set_position(("center", "bottom")).set_start(i * duration_per_line).set_duration(duration_per_line)
        caption_clips.append(caption)

    # Compose final
    final = mp.CompositeVideoClip([video, title] + caption_clips)
    final = final.set_audio(narration)
    final.write_videofile(output_path, fps=24)

    return {"video_path": output_path}
