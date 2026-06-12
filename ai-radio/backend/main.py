"""AI 电台 V2 后端

V2 第一波：从 taste.md 取歌单 → 网易云搜歌（pyncm）→ 缓存歌曲到本地 → 读手写稿件 → Fish Audio 合成 → 返回 url。
- 旧 V1 「本地 mp3 + 旁白文件」的能力保留作为兜底（搜不到的歌可以本地文件兜）
"""
# === VPN 直连规则：必须在 import pyncm/httpx 之前设置 ===
# 用户长期开 v2rayN TUN 模式，国内域名（网易云、Fish Audio 中国节点）走代理常被拦
# 加入 NO_PROXY 让这些域名直连，绕开 VPN
import os
_NO_PROXY = (
    "music.163.com,.music.163.com,music.126.net,.music.126.net,"
    # QQ 音乐：覆盖所有子域（cgi + 直链流媒体 + 封面 + tencent CDN）
    # 一个 .qq.com 通配比一个个写 host 更稳；.gtimg.cn 是腾讯静态资源 CDN
    ".qq.com,.gtimg.cn"
)
os.environ["NO_PROXY"] = (os.environ.get("NO_PROXY", "") + "," + _NO_PROXY).strip(",")
os.environ["no_proxy"] = os.environ["NO_PROXY"]  # 小写也设置，requests 两个都查

import json
import logging
import re
import sqlite3
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from adapters import netease, qqmusic
from adapters.base import Track
from services.config import CONFIG_PATH, get_voices, load_config
from services.environment import EnvironmentError, get_environment
from services.fish_audio import synthesize, TTS_CACHE_DIR
from services.llm import DEFAULT_MODE, SUPPORTED_MODES
from services.playlist import PlaylistEntry, load_playlist
from services.prewarm import PrewarmItem, queue as prewarm_queue
from services.recommender import RecommendError, recommend_next
from services.song_cache import SONG_CACHE_DIR, cache_path, fetch_and_cache

# 文案模式中文名（前端显示用）
MODE_LABELS: dict[str, str] = {
    "song_intro": "歌曲介绍",
    "song_intro_taste": "懂你的歌曲介绍",
    "weather_mood": "天气感悟",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# debug 端点开关：默认关；dev 想用 /api/v1/debug/* 时 `set RADIO_DEBUG=1` 再起服务。
RADIO_DEBUG = os.environ.get("RADIO_DEBUG", "").lower() in ("1", "true", "yes", "on")


@asynccontextmanager
async def lifespan(app):
    """V4.1：启动时触发后台预热 5 首待播队列，让用户首次点播 0 等待。

    预热使用 config 里的默认 voice_id + DEFAULT_MODE 组合；用户切换 voice/mode
    时 try_pop 会自动清空重启。lifespan 只调 prewarm_queue.start()（异步 daemon），
    不阻塞 uvicorn 启动。
    """
    try:
        # 一次性迁移：旧版本 config.json 里残留的 qqmusic_credential → :8080 sqlite
        _migrate_legacy_credential_to_sqlite()
    except Exception as e:
        logger.warning(f"credential 迁移失败：{type(e).__name__}: {e}")
    try:
        cfg = load_config()
        default_voice = (cfg.get("credentials") or {}).get("voice_id") or None
        prewarm_queue.start(default_voice, DEFAULT_MODE)
        logger.info(f"启动触发预热 (voice={default_voice}, mode={DEFAULT_MODE})")
    except Exception as e:
        logger.warning(f"启动预热触发失败：{type(e).__name__}: {e}")
    yield


app = FastAPI(title="AI Radio - V2", lifespan=lifespan)

# 显式白名单（呼应 VPN 访问规则）：后端自挂前端 :8000 + dev 端口；LAN 段用 regex 兜任意端口。
# 本项目无跨站 cookie 需求（QQ 凭据走 :8080 sqlite、网易 cookie 在后端配置），
# allow_credentials=False 即消除 "*" + credentials 的 CORS 规范冲突。
_ALLOWED_ORIGINS = [
    "http://localhost:8000", "http://127.0.0.1:8000",
    "http://localhost:4321", "http://127.0.0.1:4321",
    "http://localhost:5173", "http://127.0.0.1:5173",
]
_ALLOWED_ORIGIN_REGEX = r"http://(192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}):\d+"

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_origin_regex=_ALLOWED_ORIGIN_REGEX,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.middleware("http")
async def no_cache_html(request, call_next):
    """前端 index.html 永不缓存：避免老公修了前端但浏览器仍拿旧版。
    API JSON / mp3 / TTS 等响应不受影响（仅匹配 text/html）。
    """
    response = await call_next(request)
    if "text/html" in response.headers.get("content-type", ""):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# === 路径 ===
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = PROJECT_ROOT / "ai-radio" / "frontend"
SCRIPTS_DIR = PROJECT_ROOT / "ai-radio" / "data" / "notes" / "scripts"
LOCAL_SONGS_DIR = PROJECT_ROOT / "测试文件" / "歌曲"  # V1 兼容：本地 fallback
FEEDBACK_PATH = PROJECT_ROOT / "ai-radio" / "data" / "feedback.jsonl"

# 跨次调用的歌单游标
_cursor = {"i": 0}

# 推荐器用：最近播放历史（避免连续推同一首；模块级，重启清零）
_recent_history: deque[str] = deque(maxlen=5)

# 同一首歌累计 dislike ≥ 阈值时，cursor 自动跳过（按方向找下一首未被否决的）
DISLIKE_SKIP_THRESHOLD = 2


def _aggregate_feedback_by_entry() -> dict[str, dict[str, int]]:
    """聚合 feedback.jsonl → {'title - artist': {'like': n, 'dislike': n}}。

    用 display 作 key 是为了和 PlaylistEntry.display 直接对齐——cursor 选歌时
    没有 song_id（要先调网易云才有），但 display 在编排阶段就已知。
    """
    if not FEEDBACK_PATH.exists():
        return {}
    by_entry: dict[str, dict[str, int]] = {}
    with FEEDBACK_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            title = (rec.get("title") or "").strip()
            artist = (rec.get("artist") or "").strip()
            key = f"{title} - {artist}" if artist else title
            act = rec.get("action") or ""
            if not key or act not in ("like", "dislike"):
                continue
            stat = by_entry.setdefault(key, {"like": 0, "dislike": 0})
            stat[act] += 1
    return by_entry


def _resolve_target_idx(
    playlist: list[PlaylistEntry], start_idx: int, step: int
) -> tuple[int, list[str]]:
    """从 start_idx 按 step (+1 或 -1) 方向找第一首未被多次 dislike 的歌。

    返回 (target_idx, skipped_displays)。整圈全被 dislike 时兜底返回起点（避免死循环）。
    """
    n = len(playlist)
    if n == 0:
        return 0, []
    feedback = _aggregate_feedback_by_entry()
    skipped: list[str] = []
    candidate = start_idx % n
    for _ in range(n):
        entry = playlist[candidate]
        dislikes = feedback.get(entry.display, {}).get("dislike", 0)
        if dislikes < DISLIKE_SKIP_THRESHOLD:
            return candidate, skipped
        skipped.append(entry.display)
        candidate = (candidate + step) % n
    logger.warning(
        f"歌单内所有歌 dislike ≥ {DISLIKE_SKIP_THRESHOLD}，跳过逻辑失效，按起点 {start_idx} 播放"
    )
    return start_idx % n, skipped


def _time_of_day(now: datetime | None = None) -> str:
    """按小时分七段，与 recommender.py 内的时段语义保持一致。"""
    h = (now or datetime.now()).hour
    if h < 6 or h >= 23:
        return "深夜"
    if h < 9:
        return "清晨"
    if h < 12:
        return "上午"
    if h < 14:
        return "中午"
    if h < 17:
        return "下午"
    if h < 19:
        return "傍晚"
    return "夜晚"


def _season(now: datetime | None = None) -> str:
    """北半球四季：3-5 春 / 6-8 夏 / 9-11 秋 / 12-2 冬。LLM 自行从月份细化（如「春末」）。"""
    m = (now or datetime.now()).month
    if m in (3, 4, 5):
        return "春"
    if m in (6, 7, 8):
        return "夏"
    if m in (9, 10, 11):
        return "秋"
    return "冬"


def _enrich_environment(env: dict | None) -> dict | None:
    """给 get_environment 返回的字典补 time_of_day + season。env 为 None 时直接返回。"""
    if not env:
        return None
    now = datetime.now()
    env = dict(env)  # 浅拷贝避免改到缓存
    env["time_of_day"] = _time_of_day(now)
    env["season"] = _season(now)
    return env


def _find_intro_end_ms(lrc_text: str) -> float:
    """从 LRC 找前奏结束时间戳（=第一句真歌词），毫秒。跳过元信息行。"""
    if not lrc_text:
        return 0.0
    meta_re = re.compile(r"^(作词|作曲|编曲|出品|制作|演唱|混音|母带|和声|监制|录音)\s*[:：]")
    tag_re = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\](.*)")
    for line in lrc_text.split("\n"):
        m = tag_re.match(line.strip())
        if not m:
            continue
        ms = (int(m.group(1)) * 60 + float(m.group(2))) * 1000
        text = m.group(3).strip()
        if ms < 10000:
            continue
        if meta_re.match(text):
            continue
        return ms
    return 0.0


def _script_path(entry: PlaylistEntry, mode: str) -> Path:
    """song_intro 沿用 notes/scripts/{display}.md（兼容现有手写稿）。
    其他 mode 落到 notes/scripts/{mode}/{display}.md 子目录。
    """
    if mode == "song_intro":
        return SCRIPTS_DIR / f"{entry.display}.md"
    return SCRIPTS_DIR / mode / f"{entry.display}.md"


def _read_or_generate_script(
    entry: PlaylistEntry,
    lyric_str: str | None,
    mode: str,
    environment: dict | None = None,
) -> tuple[str, str | None]:
    """优先读本地手写稿；找不到则调 LLM 按 mode 生成 + 保存到 .md（下次复用）。

    weather_mood 模式下 environment 会作为 prompt 的事实素材注入。
    weather_mood 的稿件不落盘（环境是变化的，每次都得新写），其他 mode 落盘复用。

    返回 (script, fallback_reason)。fallback_reason 非 None 表示走了兜底文案，
    上层可据此把降级原因带到响应里告知前端。
    """
    candidate = _script_path(entry, mode)
    # weather_mood 强制每次新生成（环境变化太快，复用稿件会撒谎）
    if mode != "weather_mood" and candidate.exists():
        text = candidate.read_text(encoding="utf-8").strip()
        if text:
            return text, None

    intro_end_ms = _find_intro_end_ms(lyric_str or "")
    intro_sec = intro_end_ms / 1000.0
    target_sec = max(8.0, intro_sec - 1.0) if intro_sec > 0 else 12.0
    target_chars = int(target_sec * 4)  # 中文播报约 4 字/秒

    from services.llm import generate_script
    try:
        script = generate_script(
            mode, entry.title, entry.artist, target_chars,
            environment=environment, entry=entry,
        )
    except Exception as e:
        # LLM 失败兜底：极简稿不落盘（下次仍尝试 LLM），让节目能继续走完
        logger.warning(f"LLM 生成失败 [mode={mode}]，用兜底文案：{type(e).__name__}: {e}")
        artist_part = f"{entry.artist} 的作品，" if entry.artist else ""
        fallback = f"接下来这首，《{entry.title}》。{artist_part}请安静地听完它。"
        return fallback, f"llm_{type(e).__name__}"

    # weather_mood 不落盘（环境随时间变化，复用会撒谎）
    if mode == "weather_mood":
        logger.info(f"LLM 生成 weather_mood 稿件（不落盘）：{entry.display} ({len(script)} 字)")
        return script, None

    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text(script, encoding="utf-8")
    rel = candidate.relative_to(SCRIPTS_DIR)
    logger.info(f"LLM 生成稿件保存 [{mode}]：{rel} ({len(script)} 字)")
    return script, None


def _track_not_found(entry: PlaylistEntry, message: str, suggestion: str) -> JSONResponse:
    """统一的「这首歌走不下去了」返回：前端识别 type=track_not_found 后会自动切下一首。"""
    return JSONResponse(
        status_code=404,
        content={
            "type": "track_not_found",
            "message": message,
            "suggestion": suggestion,
            "track": {"title": entry.title, "artist": entry.artist},
        },
    )


# === 路由 ===
def _probe_qqmusic_api(timeout: float = 1.0) -> dict:
    """探 QQMusicApi :8080 是否在跑（QQ 直链 / 歌词 / 扫码登录的唯一来源）。
    短超时 + trust_env=False（不走 VPN 代理），失败不抛、不拖慢 health。"""
    try:
        r = httpx.get(f"{qqmusic.QQ_API_BASE}/", timeout=timeout, trust_env=False)
        return {"alive": True, "status": r.status_code}
    except Exception as e:
        return {"alive": False, "error": type(e).__name__}


@app.get("/api/v1/health")
def health():
    playlist = load_playlist()
    scripts = [s.stem for s in SCRIPTS_DIR.glob("*.md")] if SCRIPTS_DIR.exists() else []
    return {
        "ok": True,
        "playlist_count": len(playlist),
        "playlist": [e.display for e in playlist],
        "scripts_existing": scripts,
        "song_cache_dir": str(SONG_CACHE_DIR),
        "tts_cache_dir": str(TTS_CACHE_DIR),
        "cursor": _cursor["i"],
        "qqmusic_api": _probe_qqmusic_api(),
    }


@app.get("/api/v1/environment")
def get_environment_endpoint(lat: float | None = None, lon: float | None = None):
    """V3 #1 环境感知：返回当前地点 + 天气 + 时间。

    lat/lon 来自前端 navigator.geolocation；不传则后端走 IP 兜底定位。
    天气拉自和风 (QWeather)，未配 qweather_api_key 时静默降级为 weather=null。
    路由本身永远 200，前端按 weather 是否存在决定显不显示。
    """
    try:
        return get_environment(lat=lat, lon=lon)
    except EnvironmentError as e:
        # IP 定位都挂了 → 仍返回 200，让前端只显示时间
        logger.warning(f"环境感知失败：{e}")
        return {
            "location": {"city": "", "region": "", "source": "unavailable"},
            "weather": None,
            "time": datetime.now().isoformat(timespec="seconds"),
            "weather_configured": False,
            "error": str(e),
        }


@app.get("/api/v1/voices")
def get_voices_endpoint():
    """返回可选 voice 列表 [{id, name}, ...]"""
    return {"voices": get_voices()}


@app.get("/api/v1/modes")
def get_modes_endpoint():
    """返回可选文案模式 [{id, name}, ...]"""
    return {
        "modes": [{"id": m, "name": MODE_LABELS.get(m, m)} for m in SUPPORTED_MODES],
        "default": DEFAULT_MODE,
    }


@app.get("/api/v1/episode")
def get_episode(
    direction: str = "next",
    voice: str | None = None,
    mode: str = DEFAULT_MODE,
):
    """V2：选歌（next/prev）→ 网易云 → 缓存 → 按 mode 读/生成稿 → Fish 合成 → 返回 url。

    direction:
      - "next"（默认）：cursor 指向的下一首
      - "prev"：上一首（cursor 倒退 2 位再 +1 = 上一首）
    mode: 文案模式（song_intro / song_intro_taste / weather_mood）；未知 mode 自动回退到 DEFAULT_MODE
    """
    if mode not in SUPPORTED_MODES:
        logger.warning(f"未知文案模式 {mode}，回退到 {DEFAULT_MODE}")
        mode = DEFAULT_MODE
    playlist = load_playlist()
    if not playlist:
        raise HTTPException(404, "歌单为空：请编辑 data/user/taste.md 添加歌曲")

    n = len(playlist)
    recommend_reason: str | None = None

    if direction == "prev":
        # 上一首：cursor 倒退（用户主动操作，不走推荐器）
        start = (_cursor["i"] - 2) % n
        target_idx, skipped_by_feedback = _resolve_target_idx(playlist, start, -1)
        _cursor["i"] = (target_idx + 1) % n
        entry = playlist[target_idx]
    else:
        # V4.1 预热队列：next 方向先 try_pop 命中秒响应 + 后台 refill
        feedback = _aggregate_feedback_by_entry()

        def _is_disliked(display: str) -> bool:
            return feedback.get(display, {}).get("dislike", 0) >= DISLIKE_SKIP_THRESHOLD

        pre = prewarm_queue.try_pop(voice, mode, _is_disliked)
        if pre is not None:
            # 同步全局 _cursor + _recent_history（队列预热时未动这俩）
            _recent_history.append(pre.playlist_display)
            for i, e in enumerate(playlist):
                if e.display == pre.playlist_display:
                    _cursor["i"] = (i + 1) % n
                    break
            logger.info(
                f"预热命中秒响应：《{pre.payload.get('song_title')}》 "
                f"- {pre.payload.get('artist')}"
            )
            return pre.payload

        # 不命中：走原 cold path（推荐器选歌 → 多源 → ...）
        candidates = [
            e for e in playlist
            if feedback.get(e.display, {}).get("dislike", 0) < DISLIKE_SKIP_THRESHOLD
        ]
        skipped_by_feedback = []
        try:
            if not candidates:
                raise RecommendError("全部候选都被 dislike 阈值过滤")
            entry, recommend_reason = recommend_next(
                candidates, list(_recent_history), feedback, weather=None
            )
            # 同步 cursor 指向选中歌曲后一位（让 prev 仍能正确倒退）
            for i, e in enumerate(playlist):
                if e.display == entry.display:
                    _cursor["i"] = (i + 1) % n
                    break
        except RecommendError as rec_err:
            logger.warning(f"推荐器失败回退 cursor：{rec_err}")
            start = _cursor["i"] % n
            target_idx, skipped_by_feedback = _resolve_target_idx(playlist, start, 1)
            _cursor["i"] = (target_idx + 1) % n
            entry = playlist[target_idx]

    if skipped_by_feedback:
        logger.info(
            f"反馈驱动跳过 {skipped_by_feedback} → 选中 {entry.display}"
        )

    # 记录到最近播放历史，供下次推荐器避免重复推
    _recent_history.append(entry.display)

    # 检查歌词与脚本目录已就绪
    SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. V4.0 多源调度：优先 QQ（entry.sources.qqmusic.songmid 走直链），失败兜底网易
    track: Track | None = None
    dispatch_errors: list[str] = []

    qq_src = (entry.sources or {}).get("qqmusic") if hasattr(entry, "sources") else None
    if qq_src and qq_src.get("songmid"):
        try:
            track = qqmusic.get_track_by_songmid(
                qq_src["songmid"],
                title=entry.title,
                artists=entry.artists,
                album=entry.album,
                album_mid=qq_src.get("album_mid", ""),
                duration_ms=entry.duration_ms,
            )
        except Exception as e:
            logger.warning(f"QQ 调度失败《{entry.title}》：{type(e).__name__}: {e}")
            dispatch_errors.append(f"qq:{type(e).__name__}")
        if track is None:
            dispatch_errors.append("qq:no_track")
            logger.info(f"QQ 拿不到《{entry.title}》直链，回退网易兜底")

    if track is None:
        try:
            track = netease.get_track(entry.title, entry.artist)
        except Exception as e:
            logger.exception("网易云调用失败")
            return _track_not_found(
                entry,
                f"多源全部失败（《{entry.title}》/ {entry.artist}）：QQ={dispatch_errors} 网易={e}",
                "可能是 cookie 过期或网络抖动，自动切下一首…",
            )

    if track is None:
        return _track_not_found(
            entry,
            f"《{entry.title}》/ {entry.artist} 在 QQ + 网易都找不到 [QQ 错: {dispatch_errors}]",
            "可放本地 mp3 到 data/songs/，或自动切下一首…",
        )

    # 2. 缓存歌曲到本地（避开 20 分钟过期）
    try:
        fetch_and_cache(track.source, track.source_id, track.audio_url)
    except Exception as e:
        logger.exception("歌曲下载缓存失败")
        return _track_not_found(
            entry,
            f"《{entry.title}》/ {entry.artist} 下载失败：{e}",
            "直链可能已过期或网络断了，自动切下一首…",
        )

    # 3. 读旁白稿：优先本地手写稿；找不到则按 mode 调 DeepSeek LLM 自动生成 + 落盘
    #    weather_mood 模式：拉一次环境（命中缓存通常 < 5ms）作为 LLM 事实素材
    env_data: dict | None = None
    if mode == "weather_mood":
        try:
            env_data = _enrich_environment(get_environment())
        except EnvironmentError as e:
            logger.warning(f"weather_mood 环境感知失败，按降级写法继续：{e}")
            env_data = _enrich_environment({"location": {}, "weather": None})
    script, llm_fallback_reason = _read_or_generate_script(
        entry, track.lyric, mode, environment=env_data
    )

    # 4. Fish Audio 合成（用前端选定的 voice，或默认）
    # TTS 失败不让整集挂掉：tts_url=None，前端会跳过旁白只播歌
    tts_url: str | None = None
    tts_fallback_reason: str | None = None
    try:
        tts_path = synthesize(script, voice_id=voice)
        tts_url = f"/api/v1/tts/{tts_path.stem}"
    except Exception as e:
        logger.exception("Fish Audio 合成失败，跳过旁白只播歌")
        tts_fallback_reason = f"tts_{type(e).__name__}"

    degraded: list[dict] = []
    if llm_fallback_reason:
        degraded.append({"stage": "llm", "reason": llm_fallback_reason})
    if tts_fallback_reason:
        degraded.append({"stage": "tts", "reason": tts_fallback_reason})

    return {
        "tts_url": tts_url,
        "song_url": f"/api/v1/song/{track.source}/{track.source_id}",
        "song_id": f"{track.source}/{track.source_id}",
        "song_title": entry.title,
        "artist": entry.artist,
        "album": track.album,
        "cover_url": track.cover_url,
        "duration_ms": track.duration_ms,
        "lyric": track.lyric,
        "script": script,
        "mode": mode,
        "degraded": degraded,
        "skipped_by_feedback": skipped_by_feedback,
        "recommend_reason": recommend_reason,
    }


@app.get("/api/v1/tts/{hash_id}")
def serve_tts(hash_id: str):
    path = TTS_CACHE_DIR / f"{hash_id}.mp3"
    if not path.exists():
        raise HTTPException(404, f"TTS 缓存不存在：{hash_id}")
    return FileResponse(path, media_type="audio/mpeg")


@app.get("/api/v1/song/{source}/{source_id}")
def serve_song(source: str, source_id: str):
    path = cache_path(source, source_id)
    if not path.exists():
        raise HTTPException(404, f"歌曲缓存不存在：{source}/{source_id}")
    return FileResponse(path, media_type="audio/mpeg")


@app.get("/api/v1/debug/qqmusic")
def debug_qqmusic_track(
    songmid: str,
    title: str = "",
    artists: str = "",
    album: str = "",
    album_mid: str = "",
    duration_ms: int = 0,
):
    """V4.0 STEP 1 验收端点：按 songmid 端到端跑通 QQ 取直链 + 歌词 + 下载缓存。

    不走 PlaylistEntry / cursor / 推荐器，纯手工传参验证适配器单元能用。
    artists 用英文逗号分隔多个艺人。成功后浏览器访问返回的 song_url 应能直接播放。

    示例：/api/v1/debug/qqmusic?songmid=000XeLXA3X8CTH&title=后来&artists=刘若英
          &album=我等你&album_mid=0017zqT34WuQwa&duration_ms=341000
    """
    if not RADIO_DEBUG:
        raise HTTPException(404, "debug endpoint disabled")
    artist_list = [a.strip() for a in artists.split(",") if a.strip()]
    track = qqmusic.get_track_by_songmid(
        songmid,
        title=title or songmid,
        artists=artist_list,
        album=album,
        album_mid=album_mid,
        duration_ms=duration_ms,
    )
    if not track:
        raise HTTPException(
            404, f"QQ 音乐取不到 songmid={songmid}（可能 cookie 失效 / VIP / 无版权）"
        )
    try:
        fetch_and_cache(track.source, track.source_id, track.audio_url)
    except Exception as e:
        logger.exception("QQ 音乐下载缓存失败")
        raise HTTPException(502, f"取到直链但下载失败：{e}")
    return {
        "ok": True,
        "song_url": f"/api/v1/song/{track.source}/{track.source_id}",
        "track": track.to_dict(),
    }


# === 反馈：喜欢 / 不喜欢 ===
class FeedbackPayload(BaseModel):
    song_id: str
    title: str
    artist: str = ""
    action: str = Field(..., pattern="^(like|dislike)$")


@app.post("/api/v1/feedback")
def post_feedback(payload: FeedbackPayload):
    """追加写入 data/feedback.jsonl，一行一条 JSON。"""
    record = {
        "song_id": payload.song_id,
        "title": payload.title,
        "artist": payload.artist,
        "action": payload.action,
        "ts": datetime.now().isoformat(timespec="seconds"),
        "context": {},
    }
    FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with FEEDBACK_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    logger.info(f"feedback: {payload.action} ← {payload.title}")
    return {"ok": True, "record": record}


@app.get("/api/v1/feedback/stats")
def get_feedback_stats():
    """返回反馈统计：每首歌 like / dislike 计数。

    by_song   : 按 'netease/<sid>' song_id 聚合（含 title）
    by_entry  : 按 'title - artist' display 聚合，同 cursor 选歌的判定键，含 would_skip 标记
    """
    if not FEEDBACK_PATH.exists():
        return {
            "ok": True,
            "total": 0,
            "by_song": {},
            "by_entry": {},
            "dislike_skip_threshold": DISLIKE_SKIP_THRESHOLD,
        }
    by_song: dict[str, dict[str, int]] = {}
    total = 0
    with FEEDBACK_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            sid = rec.get("song_id", "")
            act = rec.get("action", "")
            if sid not in by_song:
                by_song[sid] = {"like": 0, "dislike": 0, "title": rec.get("title", "")}
            if act in ("like", "dislike"):
                by_song[sid][act] += 1
                total += 1

    by_entry_raw = _aggregate_feedback_by_entry()
    by_entry = {
        k: {**v, "would_skip": v.get("dislike", 0) >= DISLIKE_SKIP_THRESHOLD}
        for k, v in by_entry_raw.items()
    }
    return {
        "ok": True,
        "total": total,
        "by_song": by_song,
        "by_entry": by_entry,
        "dislike_skip_threshold": DISLIKE_SKIP_THRESHOLD,
    }


# === 配置管理（Config Page，PRD V2 验收对应） ===

# 字段分类：敏感字段需 mask 显示
_SENSITIVE_KEYS = {
    "fish_audio_api_key",
    "voice_id",
    "deepseek_api_key",
    "netease_music_u_cookie",
    "qweather_api_key",
}

# 占位符前缀：example 模板里未替换的字段以这些开头，应判为「未填」而非真值
_PLACEHOLDER_PREFIXES = ("请在此填入", "<")


def _is_real_value(v) -> bool:
    """非空且不是 example 占位符 → 视为用户真正填了值。"""
    if not isinstance(v, str):
        return False
    s = v.strip()
    return bool(s) and not s.startswith(_PLACEHOLDER_PREFIXES)
# 首启判定的必填字段：LLM key 按当前 provider 动态决定，netease cookie 恒定必填
_BASE_REQUIRED_KEYS = ["netease_music_u_cookie"]
# 可选凭据：含所有 LLM provider 的 key（每个都允许填，但不强制）
_OPTIONAL_KEYS = ["fish_audio_api_key", "voice_id", "qweather_api_key"]


def _current_required_keys() -> list[str]:
    """动态算 _REQUIRED_KEYS：当前 LLM provider 对应的 api_key_field 必填。"""
    from services.llm_providers import get_required_api_key_field
    try:
        return [get_required_api_key_field(), *_BASE_REQUIRED_KEYS]
    except Exception:
        return ["deepseek_api_key", *_BASE_REQUIRED_KEYS]


def _mask_value(v: str) -> str:
    """敏感字段 mask；保留长度信息让用户判断是否已填。"""
    if not isinstance(v, str) or not v:
        return ""
    return "●" * 8 + f" (已保存 {len(v)} 字符)"


@app.get("/api/v1/config")
def get_config_endpoint():
    """返回当前配置：敏感字段 mask，含必填/可选填充状态。"""
    cfg = load_config()
    creds = cfg.get("credentials", {}) or {}
    masked: dict = {}
    for k, v in creds.items():
        if k == "voice_options":
            masked[k] = v
            continue
        if k in _SENSITIVE_KEYS:
            masked[k] = _mask_value(v) if isinstance(v, str) else v
        else:
            masked[k] = v
    required_keys = _current_required_keys()
    required_filled = {k: _is_real_value(creds.get(k)) for k in required_keys}
    optional_filled = {k: _is_real_value(creds.get(k)) for k in _OPTIONAL_KEYS}
    return {
        "credentials": masked,
        "settings": cfg.get("settings", {}) or {},
        "required_filled": required_filled,
        "optional_filled": optional_filled,
        "all_required_ok": all(required_filled.values()),
    }


class ConfigUpdatePayload(BaseModel):
    credentials: dict | None = None
    settings: dict | None = None


@app.post("/api/v1/config")
def update_config_endpoint(payload: ConfigUpdatePayload):
    """部分更新 config.json：只覆盖提供且非空的字段，未提供 / 空字符串的字段保持不动。

    避免前端不带某字段时误清空已保存的值。
    """
    cfg = load_config()
    new_creds = payload.credentials or {}
    if new_creds:
        cfg.setdefault("credentials", {})
        for k, v in new_creds.items():
            if isinstance(v, str) and not v.strip():
                continue
            cfg["credentials"][k] = v
    new_settings = payload.settings or {}
    if new_settings:
        cfg.setdefault("settings", {})
        for k, v in new_settings.items():
            cfg["settings"][k] = v
    CONFIG_PATH.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # 热更新：netease cookie 变了就让已登录 session 失效，下次取歌自动重登（免重启）
    if new_creds.get("netease_music_u_cookie", "").strip():
        netease.reset_login()
        logger.info("netease cookie 已更新 → reset_login")
    logger.info(
        f"配置已更新：credentials={list(new_creds.keys())} settings={list(new_settings.keys())}"
    )
    return {"ok": True}


class LocationSearchPayload(BaseModel):
    name: str


@app.post("/api/v1/config/location/search")
def search_location_endpoint(payload: LocationSearchPayload):
    """V3.1：城市名 → 候选位置列表（前端在配置面板里手填位置时用）。

    VPN / LAN IP 环境浏览器 Geolocation 拒绝授权时的兜底入口。
    返回的某条候选写入 settings.location_override 后，environment 路由会优先用它。
    """
    name = payload.name.strip()
    if not name:
        return {"ok": False, "results": [], "message": "城市名不能为空"}
    from services.environment import _qweather_key, search_city
    api_key = _qweather_key()
    if not api_key:
        return {
            "ok": False, "results": [],
            "message": "未配置 qweather_api_key，无法搜索城市；请先在「天气 API」section 配 key",
        }
    try:
        results = search_city(name, api_key)
        return {"ok": True, "results": results}
    except EnvironmentError as e:
        logger.warning(f"城市搜索失败：{e}")
        return {"ok": False, "results": [], "message": str(e)}


class ConfigTestPayload(BaseModel):
    service: str = Field(..., pattern="^(llm|deepseek|fish_audio|netease|qqmusic|qweather)$")
    provider: str | None = None  # 仅 service=llm 时生效；缺省走当前 settings.llm_provider


@app.post("/api/v1/config/test")
def test_config_endpoint(payload: ConfigTestPayload):
    """连通性测试：调一次目标服务最小可用请求。

    LLM 测试：service 可填 llm（通用）或 deepseek（指定 provider）。
    传 provider 时强制用该 provider 临测（不改全局 settings.llm_provider）。
    """
    service = payload.service
    try:
        if service in ("llm", "deepseek"):
            from services.llm_providers import build_client_and_model, get_provider_config
            # service=deepseek → 锁定对应 provider；service=llm → 用 payload.provider 或当前
            provider = payload.provider
            if service == "deepseek":
                provider = service
            client, model = build_client_and_model(provider=provider)
            label = get_provider_config(provider)["label"]
            completion = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "你好，请只回一个字：好"}],
                max_completion_tokens=10,
            )
            text = (completion.choices[0].message.content or "").strip()
            return {"ok": True, "message": f"{label} ({model}) 连通正常（返回 {len(text)} 字）"}
        if service == "fish_audio":
            voices = get_voices()
            if not voices:
                return {"ok": False, "message": "未配置 voice_id / voice_options，无法测试"}
            tts_path = synthesize("配置测试，可以听到这段就说明合成成功。", voice_id=voices[0]["id"])
            size = tts_path.stat().st_size if tts_path.exists() else 0
            return {"ok": True, "message": f"Fish Audio 连通正常（合成 {size} 字节 mp3）"}
        if service == "netease":
            track = netease.get_track("晴天", "周杰伦")
            if track:
                artists = ", ".join(track.artists) if hasattr(track, "artists") else ""
                return {"ok": True, "message": f"网易云连通正常（搜到《{track.title}》/ {artists}）"}
            return {"ok": False, "message": "网易云能调通但没搜到，可能 cookie 失效"}
        if service == "qqmusic":
            # 用 2022 年度歌单《后来》刘若英固定 songmid 测一下能否取到直链
            sample_mid = "000XeLXA3X8CTH"
            url = qqmusic.get_audio_url(sample_mid)
            if not url:
                return {
                    "ok": False,
                    "message": "QQ 音乐 cgi 能调通但拿不到直链（可能 cookie 失效 / VIP 限制）",
                }
            lyric_len = len(qqmusic.get_lyric(sample_mid) or "")
            return {
                "ok": True,
                "message": f"QQ 音乐连通正常（《后来》刘若英直链 {len(url)} 字符，歌词 {lyric_len} 字）",
            }
        if service == "qweather":
            # 用北京坐标测一下能否拿到 now 数据
            from services.environment import _qweather_key, fetch_weather
            key = _qweather_key()
            if not key:
                return {"ok": False, "message": "未配置 qweather_api_key"}
            w = fetch_weather(39.9, 116.4, key)
            return {"ok": True, "message": f"和风天气连通正常（北京 {w.get('text')} {w.get('temp')}°C）"}
    except Exception as e:
        logger.exception(f"连通性测试 {service} 失败")
        return {"ok": False, "message": f"{type(e).__name__}: {str(e)[:200]}"}
    return {"ok": False, "message": f"未知 service: {service}"}


# === V4.1：预热队列 generator ===
# 抽出「选歌 + 多源 + 缓存 + 稿件 + TTS + payload 组装」做后台预生成。
# 不动 _cursor / _recent_history（episode 路由 pop 时再同步），但读 _recent_history
# 作为 recommender 的 recent_history 输入，避免和最近已播的撞车。
def _make_episode_for_prewarm(
    voice_id: str | None,
    mode: str,
    exclude_displays: list[str],
) -> PrewarmItem | None:
    """后台预热单首 episode：返回 PrewarmItem 或 None（无候选 / 失败）。

    exclude_displays: 当前队列已有项的 display；合并到 recent_history 喂给
    recommender，避免预热内部 5 首重复。
    """
    if mode == "weather_mood":
        # weather_mood 环境敏感（每次都得新写稿），预制等于撒谎
        return None

    playlist = load_playlist()
    if not playlist:
        return None

    feedback = _aggregate_feedback_by_entry()
    candidates = [
        e for e in playlist
        if feedback.get(e.display, {}).get("dislike", 0) < DISLIKE_SKIP_THRESHOLD
    ]
    if not candidates:
        return None

    effective_recent = list(_recent_history) + list(exclude_displays)

    try:
        entry, _reason = recommend_next(
            candidates, effective_recent, feedback, weather=None
        )
    except RecommendError as e:
        logger.info(f"预热：推荐器无候选：{e}")
        return None

    # 多源调度（QQ → netease）
    track: Track | None = None
    dispatch_errors: list[str] = []
    qq_src = (entry.sources or {}).get("qqmusic") if hasattr(entry, "sources") else None
    if qq_src and qq_src.get("songmid"):
        try:
            track = qqmusic.get_track_by_songmid(
                qq_src["songmid"],
                title=entry.title,
                artists=entry.artists,
                album=entry.album,
                album_mid=qq_src.get("album_mid", ""),
                duration_ms=entry.duration_ms,
            )
        except Exception as e:
            dispatch_errors.append(f"qq:{type(e).__name__}")
        if track is None:
            dispatch_errors.append("qq:no_track")

    if track is None:
        try:
            track = netease.get_track(entry.title, entry.artist)
        except Exception as e:
            logger.warning(
                f"预热多源全败《{entry.title}》：QQ={dispatch_errors} 网易={e}"
            )
            return None

    if track is None:
        return None

    # 歌曲下载缓存
    try:
        fetch_and_cache(track.source, track.source_id, track.audio_url)
    except Exception as e:
        logger.warning(f"预热下载失败《{entry.title}》：{e}")
        return None

    # 稿件
    try:
        script, llm_fallback_reason = _read_or_generate_script(
            entry, track.lyric, mode, environment=None
        )
    except Exception as e:
        logger.warning(f"预热稿件失败《{entry.title}》：{e}")
        return None

    # TTS（失败兜底：返回 payload 但 tts_url=None，让前端跳过旁白只播歌）
    tts_url: str | None = None
    tts_fallback_reason: str | None = None
    try:
        tts_path = synthesize(script, voice_id=voice_id)
        tts_url = f"/api/v1/tts/{tts_path.stem}"
    except Exception as e:
        logger.warning(f"预热 TTS 失败《{entry.title}》：{e}")
        tts_fallback_reason = f"tts_{type(e).__name__}"

    degraded: list[dict] = []
    if llm_fallback_reason:
        degraded.append({"stage": "llm", "reason": llm_fallback_reason})
    if tts_fallback_reason:
        degraded.append({"stage": "tts", "reason": tts_fallback_reason})

    payload = {
        "tts_url": tts_url,
        "song_url": f"/api/v1/song/{track.source}/{track.source_id}",
        "song_id": f"{track.source}/{track.source_id}",
        "song_title": entry.title,
        "artist": entry.artist,
        "album": track.album,
        "cover_url": track.cover_url,
        "duration_ms": track.duration_ms,
        "lyric": track.lyric,
        "script": script,
        "mode": mode,
        "degraded": degraded,
        "skipped_by_feedback": [],
        "recommend_reason": None,  # 预热路径不暴露推荐原因（避免误导用户）
    }
    return PrewarmItem(
        payload=payload,
        voice_id=voice_id,
        mode=mode,
        playlist_display=entry.display,
        created_at=time.time(),
    )


prewarm_queue.set_generator(_make_episode_for_prewarm)


# === V4.1+ QQ 音乐扫码登录代理 ===
# 真·一次扫码方案：扫码后 credential 直接落到 :8080 自己的 sqlite credential_store。
# :8080 启动期 startup_credential_health_check 自动 refresh 临过期凭证 → 用户扫一次能用到
# 腾讯彻底废账号为止（不再每 3 个月手动重扫）。
# 上游 QQMusicApi web 服务（L-1124/QQMusicApi）跑在 :8080，sqlite 在 third_party 项目下。

QQ_API_BASE = "http://127.0.0.1:8080"
QQ_API_SQLITE_PATH = (
    PROJECT_ROOT / "third_party" / "QQMusicApi" / "web" / "data" / "credentials.sqlite3"
)


def _store_credential_to_qqapi_sqlite(cred_dict: dict) -> int | None:
    """把扫码 status 接口返回的 credential dict 写入 :8080 sqlite credential_store。

    SDK 的 Credential 模型用 model_dump_json(by_alias=True) 序列化（camelCase），
    这是 :8080 自己 _upsert 用的格式。我们走同一条路保证读得回来。
    """
    try:
        from qqmusic_api import Credential  # noqa: 仅扫码登录路径用一次（不污染 adapter）
        cred_obj = Credential(**cred_dict)
        json_str = cred_obj.model_dump_json(by_alias=True)
    except Exception as e:
        logger.error(f"Credential 反序列化失败：{type(e).__name__}: {e}")
        return None
    try:
        conn = sqlite3.connect(str(QQ_API_SQLITE_PATH))
        conn.execute(
            """
            INSERT INTO credentials (musicid, credential_json, updated_at, valid)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(musicid) DO UPDATE SET
              credential_json = excluded.credential_json,
              updated_at = excluded.updated_at,
              valid = 1
            """,
            (cred_obj.musicid, json_str, int(time.time())),
        )
        conn.commit()
        conn.close()
        return cred_obj.musicid
    except Exception as e:
        logger.error(f"写入 :8080 sqlite 失败：{type(e).__name__}: {e}")
        return None


def _migrate_legacy_credential_to_sqlite() -> None:
    """一次性迁移：把 config.json.qqmusic_credential 旧字段写入 :8080 sqlite + 清掉字段。
    应该在 lifespan startup 调一次。后续扫码登录直接落 sqlite，不再走 config.json。"""
    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return
    creds = cfg.get("credentials") or {}
    legacy = creds.get("qqmusic_credential")
    if not isinstance(legacy, dict) or not legacy.get("musicid"):
        return
    musicid = _store_credential_to_qqapi_sqlite(legacy)
    if musicid:
        del creds["qqmusic_credential"]
        CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"★ 旧 credential 已从 config.json 迁移到 :8080 sqlite (musicid={musicid})")


@app.get("/api/v1/qq-login/me")
def qq_login_me():
    """返回 :8080 sqlite 当前有效 credential 状态。给配置面板「QQ 音乐登录」按钮回显用。"""
    try:
        if not QQ_API_SQLITE_PATH.exists():
            return {"logged_in": False, "musicid": None}
        conn = sqlite3.connect(str(QQ_API_SQLITE_PATH))
        rows = conn.execute(
            "SELECT musicid, updated_at FROM credentials WHERE valid = 1 ORDER BY updated_at DESC"
        ).fetchall()
        conn.close()
        if not rows:
            return {"logged_in": False, "musicid": None}
        return {"logged_in": True, "musicid": rows[0][0], "updated_at": rows[0][1]}
    except Exception as e:
        logger.warning(f"qq-login/me 查询失败：{type(e).__name__}: {e}")
        return {"logged_in": False, "musicid": None, "error": f"{type(e).__name__}: {e}"}


@app.get("/api/v1/qq-login/qrcode")
def qq_login_qrcode():
    """代理 QQMusicApi web 服务的 QR 二维码生成。返回 {data: {qr_type, identifier, img}}。"""
    try:
        r = httpx.get(f"{QQ_API_BASE}/login/qrcode/qq", timeout=15.0, trust_env=False)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        raise HTTPException(502, f"QQMusicApi web 服务（:8080）无响应：{type(e).__name__}: {e}")


@app.get("/api/v1/qq-login/status")
def qq_login_status(identifier: str):
    """代理 QR 登录状态查询；event=0 (DONE) 时把 credential 写入 :8080 sqlite credential_store。"""
    try:
        r = httpx.get(
            f"{QQ_API_BASE}/login/qrcode/qq/status",
            params={"identifier": identifier},
            timeout=15.0,
            trust_env=False,
        )
        r.raise_for_status()
        body = r.json()
    except Exception as e:
        raise HTTPException(502, f"QQMusicApi web 服务（:8080）无响应：{type(e).__name__}: {e}")

    data = body.get("data") or {}
    event = data.get("event")
    has_cred = bool(data.get("credential"))
    logger.info(f"[qq-login] event={event} done={data.get('done')} has_credential={has_cred}")

    if event == 0 and has_cred:
        musicid = _store_credential_to_qqapi_sqlite(data["credential"])
        if musicid:
            logger.info(f"★★★ QQ 扫码登录成功 → 凭证已落 :8080 sqlite (musicid={musicid})，自动续期生效")

    return body


# === 前端静态挂载（最后） ===
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
