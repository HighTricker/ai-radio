"""网易云适配器（基于 pyncm）。

登录策略：
1. 优先用 config.json 里的 MUSIC_U cookie 登录（携带用户 VIP 权限，能拿完整曲）
2. 失败则回退匿名登录（128k 直链，VIP 歌只 30s 预览）
"""
import logging
import time
from typing import Callable, Optional, TypeVar

import requests.exceptions as reqexc
from pyncm import GetCurrentSession
from pyncm.apis.cloudsearch import GetSearchResult
from pyncm.apis.login import (
    GetCurrentLoginStatus,
    LoginViaAnonymousAccount,
    LoginViaCookie,
)
from pyncm.apis.track import GetTrackAudio, GetTrackLyrics

from services.config import load_config

from .base import Track

T = TypeVar("T")
_RETRYABLE = (reqexc.ConnectionError, reqexc.Timeout, reqexc.ChunkedEncodingError)


def _retry(fn: Callable[[], T], attempts: int = 3, delay: float = 1.5) -> T:
    """对网易云 API 调用做简单重试（应对 RemoteDisconnected 等瞬时断连）。"""
    last_err: Optional[Exception] = None
    cur_delay = delay
    for i in range(attempts):
        try:
            return fn()
        except _RETRYABLE as e:
            last_err = e
            if i == attempts - 1:
                raise
            logger.warning(
                f"网易云请求失败 [{i + 1}/{attempts}] {type(e).__name__}: {e} → {cur_delay:.1f}s 后重试"
            )
            time.sleep(cur_delay)
            cur_delay *= 1.5
    assert last_err is not None
    raise last_err

logger = logging.getLogger(__name__)

_logged_in = False


def _get_music_u_cookie() -> str:
    """从 config.json 读取 MUSIC_U cookie；空或占位则返回空。"""
    try:
        cfg = load_config()
        val = (cfg.get("credentials", {}).get("netease_music_u_cookie") or "").strip()
        if not val or val.startswith("请") or val.startswith("（") or val.startswith("#"):
            return ""
        return val
    except Exception:
        return ""


def _ensure_login() -> None:
    """惰性登录：优先 cookie，否则匿名。"""
    global _logged_in
    sess = GetCurrentSession()
    if _logged_in and sess.uid:
        return

    cookie = _get_music_u_cookie()
    if cookie:
        try:
            LoginViaCookie(MUSIC_U=cookie)
            # LoginViaCookie 内部会写入 session 的登录态；这里只读不写
            status = GetCurrentLoginStatus() or {}
            account = status.get("account") or {}
            profile = status.get("profile") or {}
            uid = account.get("id") or sess.uid
            if uid:
                nickname = profile.get("nickname", "")
                vip = account.get("vipType", 0)
                logger.info(
                    f"网易云 cookie 登录成功 uid={uid} nickname={nickname} vipType={vip}"
                )
                _logged_in = True
                return
            logger.warning("MUSIC_U cookie 登录返回空 uid，回退匿名")
        except Exception as e:
            logger.warning(f"MUSIC_U cookie 登录失败：{e}，回退匿名")

    LoginViaAnonymousAccount()
    sess = GetCurrentSession()
    logger.info(f"网易云匿名登录 uid={sess.uid}")
    _logged_in = True


def reset_login() -> None:
    """重置登录状态，让下次 _ensure_login 重新走流程（用于 cookie 更新后）。"""
    global _logged_in
    _logged_in = False


def _normalize(s: str) -> str:
    """简单归一化：去空格、转小写。"""
    return s.strip().lower().replace(" ", "")


def search_best_match(title: str, artist: str = "") -> Optional[dict]:
    """搜索一首歌，返回最佳匹配（dict 原始结构），找不到返回 None。

    匹配策略：
    1. 用 "歌名 歌手" 拼接搜索（精度更高）
    2. 优先选歌手名字归一化匹配的
    3. 同歌手中选时长最长的（避免选到 30 秒预览 / Live 简版）
    """
    _ensure_login()

    query = f"{title} {artist}".strip()
    res = _retry(lambda: GetSearchResult(query, limit=10))
    songs = res.get("result", {}).get("songs", []) or []
    if not songs:
        return None

    if artist:
        target = _normalize(artist)
        matched = [
            s for s in songs
            if any(_normalize(a.get("name", "")) == target for a in s.get("ar", []))
        ]
        if matched:
            songs = matched

    # 选时长最长的（通常=原版录音室版，非简版/Live）
    songs.sort(key=lambda s: s.get("dt", 0), reverse=True)
    return songs[0]


def get_track(title: str, artist: str = "") -> Optional[Track]:
    """组合：搜歌 + 取直链 + 取歌词 → 返回 Track 对象。"""
    _ensure_login()

    song = search_best_match(title, artist)
    if not song:
        return None

    sid = song["id"]

    # 直链
    audio_resp = _retry(lambda: GetTrackAudio([sid]))
    audio_data = (audio_resp.get("data") or [{}])[0]
    audio_url = audio_data.get("url")
    if not audio_url:
        # 拿不到直链（版权限制 / VIP / 下架）
        logger.warning(f"无直链：{title}-{artist} (id={sid}, code={audio_data.get('code')})")
        return None

    # 直链过期时间（pyncm 给的是相对秒数，转 epoch）
    expi_sec = audio_data.get("expi", 1200)
    expire_at = int(time.time()) + int(expi_sec)

    # 歌词
    try:
        lyric_resp = _retry(lambda: GetTrackLyrics(sid))
        lyric = lyric_resp.get("lrc", {}).get("lyric") or None
    except Exception as e:
        logger.warning(f"歌词获取失败：{e}")
        lyric = None

    # fee 字段
    fee_raw = song.get("fee", 0)
    fee_map = {0: "free", 1: "vip", 4: "vip", 8: "free"}  # 网易云 fee 编码（粗略）
    fee = fee_map.get(fee_raw, "free")

    return Track(
        source="netease",
        source_id=str(sid),
        title=song.get("name", title),
        artists=[a.get("name", "") for a in song.get("ar", [])],
        album=song.get("al", {}).get("name", ""),
        cover_url=song.get("al", {}).get("picUrl", ""),
        duration_ms=song.get("dt", 0),
        audio_url=audio_url,
        audio_url_expire_at=expire_at,
        lyric=lyric,
        fee=fee,
    )
