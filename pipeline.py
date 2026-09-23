"""
Video generation engine: ElevenLabs voice, fal.ai video, fal.ai lipsync.
Adapted from the reference script; the video model endpoint is isolated
in config/settings.py so it can be swapped without touching this module.
"""
import os

import fal_client
import requests
from dotenv import load_dotenv

load_dotenv()

from config.settings import (
    ART_STYLE_BLOCK,
    ELEVENLABS_MODEL_ID,
    LIPSYNC_ENDPOINT,
    VIDEO_MODEL_IMAGE_ENDPOINT,
    VIDEO_MODEL_RESOLUTION,
    VIDEO_MODEL_TEXT_ENDPOINT,
)

FAL_KEY = os.environ.get("FAL_KEY")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")
if FAL_KEY:
    os.environ.setdefault("FAL_KEY", FAL_KEY)


def build_video_prompt(visual_prompt: str, style: str | None = None) -> str:
    """Prepends the house PS2-style block, or a per-shot style override if given."""
    return f"{style or ART_STYLE_BLOCK} {visual_prompt}".strip()


def generate_voice(text: str, voice_id: str, out_path: str,
                    model_id: str = ELEVENLABS_MODEL_ID) -> str:
    """Text -> mp3 on disk via ElevenLabs. Returns out_path."""
    if not ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY not set, check your .env")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"}
    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    with open(out_path, "wb") as f:
        f.write(response.content)
    return out_path


def generate_video(prompt: str, image_url: str | None = None,
                    resolution: str = VIDEO_MODEL_RESOLUTION) -> str:
    """Visual-only clip via fal. Returns a fal-hosted video URL."""
    if not FAL_KEY:
        raise RuntimeError("FAL_KEY not set, check your .env")
    endpoint = VIDEO_MODEL_IMAGE_ENDPOINT if image_url else VIDEO_MODEL_TEXT_ENDPOINT
    arguments = {"prompt": prompt, "resolution": resolution}
    if image_url:
        arguments["image_url"] = image_url
    result = fal_client.subscribe(
        endpoint, arguments=arguments, with_logs=True,
        on_queue_update=lambda u: [print(l["message"]) for l in getattr(u, "logs", [])],
    )
    return result["video"]["url"]


def upload_local_file(path: str) -> str:
    """Local file -> public fal URL (fal inputs need URLs, not local paths)."""
    if not FAL_KEY:
        raise RuntimeError("FAL_KEY not set, check your .env")
    return fal_client.upload_file(path)


def lipsync(video_url: str, audio_url: str) -> str:
    """Retimes the mouth in video_url to match audio_url. Both must be URLs. Returns final video URL."""
    if not FAL_KEY:
        raise RuntimeError("FAL_KEY not set, check your .env")
    result = fal_client.subscribe(
        LIPSYNC_ENDPOINT,
        arguments={"video_url": video_url, "audio_url": audio_url},
        with_logs=True,
        on_queue_update=lambda u: [print(l["message"]) for l in getattr(u, "logs", [])],
    )
    return result["video"]["url"]


def download_to_file(url: str, out_path: str) -> str:
    """Fal-hosted result URL -> local file on disk, so accepted takes live locally."""
    response = requests.get(url)
    response.raise_for_status()
    with open(out_path, "wb") as f:
        f.write(response.content)
    return out_path
