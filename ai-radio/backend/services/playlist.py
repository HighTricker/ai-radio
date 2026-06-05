"""歌单数据模型 + 加载器。

V4.0 数据模型升级：PlaylistEntry 从 NamedTuple 改为 @dataclass，承载
sources（QQ songmid / 网易 id）+ tags（跨年标签）+ version_note 等元数据。

保留向后兼容：
- entry.artist 仍可用（返回 artists[0]，旧代码无需改）
- entry.display 仍可用（"歌名 - 艺人"）
- PlaylistEntry("title", "artist") 这种位置参数旧用法仍可用（__post_init__ 把 str 包成 list）

加载器 V4.0：
- 旧：仅读 taste.md（V1 手写 8 首）
- 新：taste.md ∪ yearly_playlist_loader（5 年 + 2025 报告）
- 受 settings.include_yearly_playlist 控制；默认 True
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

AI_RADIO_DIR = Path(__file__).resolve().parent.parent.parent
TASTE_PATH = AI_RADIO_DIR / "data" / "user" / "taste.md"


@dataclass
class PlaylistEntry:
    """歌单条目。

    title / artists 是核心；其他字段从年度报告 YAML 解析得到。
    旧代码用 PlaylistEntry(title, "李宗盛")，__post_init__ 把 str → [str] 自动兼容。
    """
    title: str
    artists: list[str] = field(default_factory=list)
    album: str = ""
    duration_ms: int = 0
    language: str = ""
    version_note: str = ""
    # {qqmusic: {songmid, songid, album_mid}, netease: {id}, spotify: {uri}, ...}
    sources: dict = field(default_factory=dict)
    # [yearly:2018, yearly:2022, qq_2022, 英语, top10_2025, ...]
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # 兼容旧 PlaylistEntry(title, "刘若英") 单 str 用法
        if isinstance(self.artists, str):
            self.artists = [self.artists] if self.artists.strip() else []
        # 防御：列表里夹了 None / 空串
        self.artists = [a for a in self.artists if a and a.strip()]

    @property
    def artist(self) -> str:
        """向后兼容：返回首位艺人字符串。"""
        return self.artists[0] if self.artists else ""

    @property
    def display(self) -> str:
        """向后兼容：'歌名 - 艺人' 拼接。"""
        return f"{self.title} - {self.artist}" if self.artists else self.title


def _parse_taste_md() -> list[PlaylistEntry]:
    """读 taste.md（V1 手写格式），返回 [(title, artist), ...]。"""
    if not TASTE_PATH.exists():
        return []

    entries: list[PlaylistEntry] = []
    for raw in TASTE_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(">"):
            continue
        line = re.sub(r"^[-*+]\s+", "", line)
        if not line:
            continue
        if " - " in line:
            title, artist = line.split(" - ", 1)
            entries.append(PlaylistEntry(title=title.strip(), artists=[artist.strip()]))
        else:
            entries.append(PlaylistEntry(title=line))
    return entries


def _should_include_yearly() -> bool:
    """从 settings.include_yearly_playlist 读开关，默认 True。"""
    try:
        from .config import load_config
        cfg = load_config()
        v = (cfg.get("settings", {}) or {}).get("include_yearly_playlist")
        return v if isinstance(v, bool) else True
    except Exception:
        return True


def _normalize_key(entry: PlaylistEntry) -> str:
    """跨源去重 key：歌名 + 首位艺人，小写。"""
    return f"{entry.title.strip().lower()}|{(entry.artist or '').strip().lower()}"


def _merge_tags(existing: PlaylistEntry, incoming: PlaylistEntry) -> None:
    """命中重复时把 incoming 的新 tag 合并进 existing（保序去重）。"""
    seen = set(existing.tags)
    for t in incoming.tags:
        if t not in seen:
            existing.tags.append(t)
            seen.add(t)
    # sources 也可能互补（taste.md 无 sources；yearly 有 qqmusic）
    for src_key, src_val in (incoming.sources or {}).items():
        existing.sources.setdefault(src_key, src_val)
    # 字段互补：当 existing 缺失 / 默认值时，用 incoming 填
    if not existing.album and incoming.album:
        existing.album = incoming.album
    if not existing.duration_ms and incoming.duration_ms:
        existing.duration_ms = incoming.duration_ms
    if not existing.language and incoming.language:
        existing.language = incoming.language
    if not existing.version_note and incoming.version_note:
        existing.version_note = incoming.version_note


def load_playlist() -> list[PlaylistEntry]:
    """V4.0：合并多源歌单。

    顺序：taste.md（手写）→ yearly_playlist_loader（5 年 + 2025 报告）
    跨源遇相同 (title, artist[0]) 合并 tags / sources / 元数据（taste 优先级最高，保留其 title 大小写）
    """
    base = _parse_taste_md()
    by_key: dict[str, PlaylistEntry] = {_normalize_key(e): e for e in base}

    if _should_include_yearly():
        try:
            from .yearly_playlist_loader import load_yearly_entries
            for e in load_yearly_entries():
                k = _normalize_key(e)
                if k in by_key:
                    _merge_tags(by_key[k], e)
                else:
                    by_key[k] = e
                    base.append(e)
        except Exception as ex:
            logger.warning(f"yearly_playlist_loader 加载失败，仅返回 taste.md：{ex}")

    return base
