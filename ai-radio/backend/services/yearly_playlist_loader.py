"""年度歌单加载器（V4.0 STEP 2）。

数据源：`年度报告截图/YYYY/qq_music_*.md`，每文件含一个 ```yaml``` 块。
- 2018-2022 五年：年度歌单 / 音乐记忆（实体歌单，每首带 songmid）
- 2025 听歌报告：top_songs（无 songmid，跳过）+ monthly.top_artist（注入 tag）

跨年去重 + tag 合并：
- key = title.lower() | artists[0].lower()
- 相同条目 → 合并 tags（如 `[yearly:2018, yearly:2022]`）

2025 月度独占艺人处理（T4.2.7）：
- 该月 top_artist 若在 5 年榜单里有歌 → 给该艺人**首位**歌曲加 `monthly_top_2025:MM` tag
- 否则 → 写入 listening_facts 池，由 LLM 主播叙事时引用
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Iterable

import yaml

from .playlist import PlaylistEntry, _normalize_key

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
REPORT_DIR = PROJECT_ROOT / "年度报告截图"

# 哪些年的歌单要扫；2025 单独处理（听歌报告，不是歌单）
ANNUAL_PLAYLIST_YEARS = (2018, 2019, 2020, 2021, 2022)
LISTENING_REPORT_YEAR = 2025

_YAML_BLOCK_RE = re.compile(r"```yaml\s*\n(.*?)\n```", re.DOTALL)


def _extract_yaml(md_text: str) -> dict | None:
    """从 markdown 文件正文里抠出第一个 ```yaml``` 块。"""
    m = _YAML_BLOCK_RE.search(md_text)
    if not m:
        return None
    try:
        return yaml.safe_load(m.group(1))
    except yaml.YAMLError as e:
        logger.warning(f"YAML 解析失败：{e}")
        return None


def _has_valid_artists(artists: list) -> bool:
    """[?] 表示截图未识别出艺人，跳过这种条目。"""
    if not artists:
        return False
    cleaned = [a for a in artists if a and a not in ("[?]", "?", "(?)")]
    return bool(cleaned)


def _to_entry(raw: dict, year: int) -> PlaylistEntry | None:
    """把 YAML 一条 song 转成 PlaylistEntry。无效（缺 title / artists）返回 None。"""
    title = (raw.get("title") or "").strip()
    artists = raw.get("artists") or []
    if not title or not _has_valid_artists(artists):
        return None

    # 仅保留有 songmid 的（无 source 的没法播；2025 top_songs 走这条返回 None）
    sources = dict(raw.get("sources") or {})
    qq = sources.get("qqmusic") or {}
    if not qq.get("songmid"):
        return None

    tags = list(raw.get("tags") or [])
    # 兜底：若 YAML 自己没带年份 tag，补上
    if f"yearly:{year}" not in tags:
        tags.append(f"yearly:{year}")

    return PlaylistEntry(
        title=title,
        artists=[str(a).strip() for a in artists if a],
        album=(raw.get("album") or "").strip(),
        duration_ms=int(raw.get("duration_ms") or 0),
        language=(raw.get("language") or "").strip(),
        version_note=(raw.get("version_note") or "").strip(),
        sources=sources,
        tags=tags,
    )


def _load_one_year(year: int) -> list[PlaylistEntry]:
    """扫 年度报告截图/{year}/qq_music_*.md 里所有歌单文件。"""
    year_dir = REPORT_DIR / str(year)
    if not year_dir.exists():
        return []

    files: list[Path] = []
    for name_part in ("年度歌单", "音乐记忆"):
        files.extend(year_dir.glob(f"qq_music_*{name_part}*.md"))

    entries: list[PlaylistEntry] = []
    for f in files:
        try:
            data = _extract_yaml(f.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"读取 {f.name} 失败：{e}")
            continue
        if not data or not isinstance(data, dict):
            continue
        for raw in data.get("songs") or []:
            entry = _to_entry(raw, year)
            if entry is not None:
                entries.append(entry)
    logger.info(f"yearly_loader [{year}]：扫 {len(files)} 文件 → {len(entries)} 首")
    return entries


def _merge_into(by_key: dict[str, PlaylistEntry], incoming: PlaylistEntry) -> None:
    """跨年去重：命中 → 合并 tags / sources；未命中 → 新增。"""
    k = _normalize_key(incoming)
    if k not in by_key:
        by_key[k] = incoming
        return
    existing = by_key[k]
    seen = set(existing.tags)
    for t in incoming.tags:
        if t not in seen:
            existing.tags.append(t)
            seen.add(t)
    for src_key, src_val in (incoming.sources or {}).items():
        existing.sources.setdefault(src_key, src_val)


def _apply_2025_monthly_tags(by_key: dict[str, PlaylistEntry]) -> int:
    """读 2025 月度榜的 top_artist，给该艺人首位歌曲打 `monthly_top_2025:MM` tag。

    返回成功打上 tag 的歌曲数（用于日志）。
    """
    report = REPORT_DIR / str(LISTENING_REPORT_YEAR) / f"qq_music_{LISTENING_REPORT_YEAR}年度听歌报告.md"
    if not report.exists():
        return 0

    data = _extract_yaml(report.read_text(encoding="utf-8"))
    # 2025 报告里有多个 yaml 块，第一个是 meta；要找 monthly 字段所在的块
    # 用 finditer 重新扫所有 yaml 块
    all_blocks = _YAML_BLOCK_RE.findall(report.read_text(encoding="utf-8"))
    monthly: dict | None = None
    for blk in all_blocks:
        try:
            d = yaml.safe_load(blk)
        except yaml.YAMLError:
            continue
        if isinstance(d, dict) and isinstance(d.get("monthly"), dict):
            monthly = d["monthly"]
            break
    if not monthly:
        return 0

    tagged = 0
    for month_key, info in monthly.items():
        if not isinstance(info, dict):
            continue
        top_artist = (info.get("top_artist") or "").strip()
        if not top_artist:
            continue
        # 找该艺人在 5 年榜里第一首歌（首位 artist 匹配）
        target: PlaylistEntry | None = None
        for entry in by_key.values():
            if entry.artists and entry.artists[0].strip().lower() == top_artist.lower():
                target = entry
                break
        if target is None:
            continue
        tag = f"monthly_top_2025:{month_key}"
        if tag not in target.tags:
            target.tags.append(tag)
            tagged += 1
    return tagged


def load_yearly_entries() -> list[PlaylistEntry]:
    """主入口：合并 5 年实体歌单 + 注入 2025 月度独占艺人 tag。

    返回 list[PlaylistEntry]，已跨年去重；保留首次出现的字段值。
    """
    by_key: dict[str, PlaylistEntry] = {}

    for year in ANNUAL_PLAYLIST_YEARS:
        for entry in _load_one_year(year):
            _merge_into(by_key, entry)

    n_tagged = _apply_2025_monthly_tags(by_key)
    logger.info(
        f"yearly_loader：5 年合并去重 → {len(by_key)} 首；"
        f"2025 月度独占艺人 tag 命中 {n_tagged} 首"
    )
    return list(by_key.values())
