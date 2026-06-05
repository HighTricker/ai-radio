"""歌曲下载缓存：把直链流式下载到本地，下次命中即用本地文件。

各平台直链有效期都不长（网易 20 分钟、QQ 2 小时），下载到本地后就没这个问题。
"""
import logging
from pathlib import Path

import httpx

AI_RADIO_DIR = Path(__file__).resolve().parent.parent.parent
SONG_CACHE_DIR = AI_RADIO_DIR / "data" / "cache" / "songs"
SONG_CACHE_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)

# 按 source 区分下载请求头：QQ 音乐 vkey 直链有 Referer 防盗链（403 if 没设）
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_HEADERS_BY_SOURCE: dict[str, dict[str, str]] = {
    "qqmusic": {
        "Referer": "https://y.qq.com/",
        "Origin": "https://y.qq.com",
        "User-Agent": _UA,
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Sec-Fetch-Dest": "audio",
        "Sec-Fetch-Mode": "no-cors",
        "Sec-Fetch-Site": "same-site",
        "Range": "bytes=0-",
    },
    # netease pyncm 内部 session 已带认证 cookie；直链不要 referer 也能下
    "netease": {},
}


def cache_path(source: str, source_id: str) -> Path:
    return SONG_CACHE_DIR / f"{source}_{source_id}.mp3"


def fetch_and_cache(source: str, source_id: str, audio_url: str) -> Path:
    """缓存命中即返回；未命中则流式下载到本地后返回。"""
    path = cache_path(source, source_id)
    if path.exists() and path.stat().st_size > 0:
        logger.debug(f"歌曲缓存命中：{path.name}")
        return path

    headers = _HEADERS_BY_SOURCE.get(source, {})
    logger.info(f"下载歌曲到缓存：{source}/{source_id}")
    with httpx.stream(
        "GET", audio_url, timeout=120.0, follow_redirects=True, headers=headers
    ) as resp:
        resp.raise_for_status()
        with path.open("wb") as f:
            for chunk in resp.iter_bytes(64 * 1024):
                f.write(chunk)

    if path.stat().st_size < 1024:
        path.unlink(missing_ok=True)
        raise RuntimeError(f"下载得到文件过小：{audio_url}")

    return path
