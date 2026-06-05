"""Fish Audio TTS HTTP API 调用 + 本地缓存。

API 文档：https://docs.fish.audio/text-to-speech/text-to-speech
端点：POST https://api.fish.audio/v1/tts
鉴权：Authorization: Bearer <api_key>
"""
import hashlib
from pathlib import Path

import httpx

from .config import get_credential

AI_RADIO_DIR = Path(__file__).resolve().parent.parent.parent
TTS_CACHE_DIR = AI_RADIO_DIR / "data" / "cache" / "tts"
TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

FISH_API_URL = "https://api.fish.audio/v1/tts"


def _hash(text: str, voice_id: str) -> str:
    """同文本 + 同音色 = 同 hash → 缓存命中。"""
    h = hashlib.sha256()
    h.update(text.encode("utf-8"))
    h.update(b"|")
    h.update(voice_id.encode("utf-8"))
    return h.hexdigest()[:16]


def synthesize(text: str, voice_id: str | None = None) -> Path:
    """合成一段 TTS，返回 mp3 文件路径。命中缓存就直接返回。

    voice_id: 可选；不传则用 config.json 的默认 voice_id。
    """
    api_key = get_credential("fish_audio_api_key")
    if not voice_id:
        voice_id = get_credential("voice_id")

    cache_key = _hash(text, voice_id)
    cache_path = TTS_CACHE_DIR / f"{cache_key}.mp3"
    if cache_path.exists() and cache_path.stat().st_size > 0:
        return cache_path

    payload = {
        "text": text,
        "reference_id": voice_id,
        "format": "mp3",
        # 默认采样率、码率，Fish Audio 会按 voice 配置自适应
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=120.0) as client:
        resp = client.post(FISH_API_URL, json=payload, headers=headers)

    if resp.status_code != 200:
        raise RuntimeError(
            f"Fish Audio API {resp.status_code}: {resp.text[:500]}"
        )

    audio_bytes = resp.content
    if len(audio_bytes) < 1024:
        raise RuntimeError(
            f"Fish Audio 返回内容过小 ({len(audio_bytes)} bytes)，可能是错误响应：{audio_bytes[:200]!r}"
        )

    cache_path.write_bytes(audio_bytes)
    return cache_path
