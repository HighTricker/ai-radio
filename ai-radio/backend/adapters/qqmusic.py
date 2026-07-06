"""QQ 音乐适配器：纯 HTTP 调用 QQMusicApi web 服务（http://127.0.0.1:8080）。

V4.1+ 真·一次扫码方案：
- credential 由 :8080 自己的 sqlite credential_store 全权管理
- :8080 启动期 startup_credential_health_check 自动 refresh 临过期凭证
- adapter 调 :8080 song API 时不传 cookie，:8080 自动用 sqlite 默认凭据
- 用户扫一次码 → 用到腾讯彻底废账号为止（不再每 3 个月手动重扫）

main.py 调用方接口 (get_track_by_songmid / get_audio_url / get_lyric) 完全不变。

例外（唯一 SDK 残留，仅函数内 import 一次）：歌词响应是加密文本，web 服务无解密
参数，本地用 SDK 的 qrc_decrypt 函数解密（纯本地 RC4 操作，无网络/cookie 依赖）。
"""
import logging
import time
from typing import Optional

import httpx

from .base import Track

logger = logging.getLogger(__name__)

QQ_API_BASE = "http://127.0.0.1:8080"
_HTTP_TIMEOUT = 10.0
_COVER_URL_FMT = "https://y.gtimg.cn/music/photo_new/T002R300x300M000{album_mid}.jpg"


def _rank_cdn(host: str) -> int:
    """CDN 节点优选：sjy*.stream > 其他 .stream > aqqmusic.tc（防盗链严格）。"""
    if "sjy" in host and ".stream." in host:
        return 0
    if ".stream." in host:
        return 1
    return 2


def _http_get(path: str, params: dict | None = None) -> Optional[dict]:
    """同步 GET :8080；返回 body.data 或 None（网络错 / 4xx / code != 0）。

    不传 cookie：让 :8080 用 sqlite 里的全局默认凭据（credential.enabled = true 配的）。
    """
    try:
        r = httpx.get(
            f"{QQ_API_BASE}{path}",
            params=params,
            timeout=_HTTP_TIMEOUT,
            trust_env=False,
        )
    except Exception as e:
        logger.warning(f"QQMusicApi {path} 网络错误：{type(e).__name__}: {e}")
        return None
    if r.status_code != 200:
        logger.warning(f"QQMusicApi {path} HTTP {r.status_code}: {r.text[:200]}")
        return None
    body = r.json()
    if body.get("code") != 0:
        logger.warning(f"QQMusicApi {path} code={body.get('code')} msg={body.get('msg')}")
        return None
    return body.get("data")


def _pick_cdn_host() -> Optional[str]:
    """从 web 服务拿 CDN 节点列表，按 _rank_cdn 选最优。"""
    data = _http_get("/song/get_cdn_dispatch")
    if not data:
        return None
    sip = data.get("sip") or []
    if not sip:
        return None
    return sorted(sip, key=_rank_cdn)[0]


def get_audio_url(songmid: str) -> Optional[str]:
    """按 songmid 拿完整 mp3 直链（拼好 CDN host）。失败返回 None。"""
    cdn = _pick_cdn_host()
    if not cdn:
        return None
    data = _http_get(f"/song/{songmid}/url")
    if not data:
        return None
    midurlinfo = data.get("midurlinfo") or []
    if not midurlinfo:
        return None
    info = midurlinfo[0]
    if info.get("result") != 0 or not info.get("purl"):
        # VIP / 数字专辑 / 区域限制 / cookie 失效 → vkey 拿不到
        logger.warning(
            f"QQ vkey 空 songmid={songmid} result={info.get('result')} "
            f"filename={info.get('filename')}"
        )
        return None
    return cdn + info["purl"]


def get_lyric(songmid: str) -> Optional[str]:
    """按 songmid 拿 LRC 歌词。

    Web 服务返回 {lyric: <加密文本>, crypt: 1}；唯一一处仍用 SDK：调
    `Lyric.decrypt()` 做本地解密（纯 RC4 离线操作，无 cookie/网络依赖）。
    """
    data = _http_get(f"/song/{songmid}/lyric")
    if not data or not data.get("lyric"):
        return None
    raw = data["lyric"]
    if not data.get("crypt"):
        return raw.strip() or None
    try:
        from qqmusic_api.algorithms import qrc_decrypt
        plain = qrc_decrypt(raw)
        return plain.strip() or None
    except Exception as e:
        logger.warning(f"QQ 歌词解密失败 songmid={songmid}: {type(e).__name__}: {e}")
        return None


def get_track_by_songmid(
    songmid: str,
    *,
    title: str = "",
    artists: Optional[list[str]] = None,
    album: str = "",
    album_mid: str = "",
    duration_ms: int = 0,
) -> Optional[Track]:
    """主入口：按 songmid 组装 Track。失败返回 None（上层走 netease 兜底）。"""
    audio_url = get_audio_url(songmid)
    if not audio_url:
        return None
    lyric = get_lyric(songmid)
    cover_url = _COVER_URL_FMT.format(album_mid=album_mid) if album_mid else ""
    return Track(
        source="qqmusic",
        source_id=songmid,
        title=title or "(unknown)",
        artists=artists or [],
        album=album,
        cover_url=cover_url,
        duration_ms=duration_ms,
        audio_url=audio_url,
        audio_url_expire_at=int(time.time()) + 90 * 60,  # 保守 1.5h（vkey 实际 2h）
        lyric=lyric,
        fee="free",
    )
