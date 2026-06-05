"""听歌报告 → AI 主播叙事素材池。

V4.0 T4.2.3：2025 听歌报告 → 宏观画像 + 当首歌钩子。
V4.2（2026-06-05）扩展：纳入 2018-2022 历年听歌报告，支持「跨年陪伴钩子」+
  「多年听歌轨迹概览」，强化「懂你」核心卖点。

  各年 QQ 音乐年度报告玩法不同（2018 性格标签 / 2019 口味标签 / 2020 行星 /
  2021 星球 / 2022 宇宙列车 / 2025 MBTI+四季），多模态提取忠实记录了差异，
  故 YAML schema 高度异构（top_artist 时单时复、top_songs 字段名 plays↔play_count /
  artist(str)↔artists(list) / title↔song）。本模块用「容错归一化（_normalize_year）」
  把异构结构收敛成统一 digest，并辅以各报告现成的「## 主播叙事金句池」。

数据源：年度报告截图/{2018..2022,2025}/qq_music_{year}年度听歌报告.md
- 每个文件含多个 ```yaml``` 块 + 一节「## 主播叙事金句池」markdown 列表

对外接口（签名不变，向后兼容 llm.py 注入点）：
- get_macro_background() → 每首歌通用的"用户画像"（2025 详版 + 2018-2022 轨迹概览）
- pick_for_entry(entry) → 当前歌相关事实（2025 七规则 + 2018-2022 跨年命中钩子）
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
REPORTS_ROOT = PROJECT_ROOT / "年度报告截图"
REPORT_PATH = REPORTS_ROOT / "2025" / "qq_music_2025年度听歌报告.md"  # 2025 详版

# 历年报告（故事性 schema 各不相同，走容错归一化）。文件名统一为
# qq_music_{year}年度听歌报告.md
HISTORICAL_YEARS = (2018, 2019, 2020, 2021, 2022)

_YAML_BLOCK_RE = re.compile(r"```yaml\s*\n(.*?)\n```", re.DOTALL)
# 「## 主播叙事金句池」一节（到下一个 ## 或文末）
_QUOTE_SECTION_RE = re.compile(r"##\s*主播叙事金句池\s*\n(.*?)(?:\n##\s|\Z)", re.DOTALL)
_QUOTE_LINE_RE = re.compile(r'^\s*-\s*"?(.+?)"?\s*$')

# 进程内缓存
_FACTS_CACHE: dict[str, Any] | None = None            # 2025 详版（合并 yaml）
_MULTIYEAR_CACHE: "dict[int, YearDigest] | None" = None  # 2018-2022 归一化


def _parse_report() -> dict[str, Any]:
    """读 2025 md 把所有 yaml 块合并到一个 dict。"""
    if not REPORT_PATH.exists():
        logger.warning(f"2025 听歌报告不存在：{REPORT_PATH}")
        return {}

    text = REPORT_PATH.read_text(encoding="utf-8")
    merged: dict[str, Any] = {}
    for block in _YAML_BLOCK_RE.findall(text):
        try:
            data = yaml.safe_load(block)
        except yaml.YAMLError as e:
            logger.warning(f"YAML 块解析失败：{e}")
            continue
        if isinstance(data, dict):
            merged.update(data)
    return merged


def _load() -> dict[str, Any]:
    """惰性加载 2025 详版 + 进程内缓存。"""
    global _FACTS_CACHE
    if _FACTS_CACHE is None:
        _FACTS_CACHE = _parse_report()
        if _FACTS_CACHE:
            logger.info(
                f"listening_facts 已加载 2025：年度主题={_FACTS_CACHE.get('meta', {}).get('theme')}"
                f" / top_artists={len(_FACTS_CACHE.get('top_artists') or [])}"
                f" / monthly={len(_FACTS_CACHE.get('monthly') or {})}"
            )
    return _FACTS_CACHE or {}


def reset_cache() -> None:
    """测试 / 报告更新时手动清缓存（含 2025 详版与多年归一化）。"""
    global _FACTS_CACHE, _MULTIYEAR_CACHE
    _FACTS_CACHE = None
    _MULTIYEAR_CACHE = None


# ============================================================
# 公共 API · 第 2 层：宏观画像（每首歌都一样）
# ============================================================

def get_macro_background() -> str:
    """每次调用都一样的"用户画像"段落，注入 system prompt。

    = 2025 详版画像 + 2018-2022 多年听歌轨迹概览。两段各自可空，
    任一有内容即返回；都空时返回空串（LLM 走通用人设，不强行编造）。
    """
    parts = []
    p2025 = _macro_2025()
    if p2025:
        parts.append(p2025)
    arc = _multiyear_arc()
    if arc:
        parts.append(arc)
    return "\n\n".join(parts)


def _macro_2025() -> str:
    """2025 年度报告 → 宏观画像段落（原 get_macro_background 主体，逻辑不变）。"""
    facts = _load()
    meta = facts.get("meta") or {}
    if not meta:
        return ""

    composer = facts.get("yearly_composer") or {}
    lyricist = facts.get("yearly_lyricist") or {}
    keywords = facts.get("keywords") or []
    kw_str = "、".join(f"「{k.get('word')}」({k.get('occurrences')}次)" for k in keywords[:3] if k.get('word'))

    lines = [
        "【用户的听歌画像（QQ 音乐 2025 年度报告，整体背景，与当前这首歌未必直接相关）】",
        "（提示：以下是听众本人的年度统计，不要把它当作当前播放歌曲的创作信息。",
        "  如果下面的「关于这首歌」段落没单独列出，就别强行把这些归到当前歌手身上。）",
    ]
    if meta.get("user"):
        lines.append(f"- 用户：{meta['user']}（QQ 音乐 LV.{meta.get('listening_level', '?')}）")
    if meta.get("theme"):
        lines.append(f"- 2025 年度主题：「{meta['theme']}」")
    if meta.get("mbti"):
        lines.append(f"- 性格标签：{meta['mbti']}（QQ 音乐按听歌行为推断）")
    if meta.get("total_hours") and meta.get("total_songs"):
        lines.append(
            f"- 2025 共听 {meta['total_hours']:.0f} 小时 / {meta['total_songs']} 首"
            f"（超过 {meta.get('percentile', '?')}% 用户）"
        )
    if composer.get("name") and lyricist.get("name"):
        if composer["name"] == lyricist["name"]:
            tags = []
            if composer.get("tag"):
                tags.append(composer['tag'])
            if lyricist.get("tag") and lyricist["tag"] != composer.get("tag"):
                tags.append(lyricist['tag'])
            tag_str = f"（{'、'.join(tags)}）" if tags else ""
            lines.append(f"- 年度作词作曲都是 {composer['name']}{tag_str}")
        else:
            lines.append(f"- 年度作曲：{composer['name']}；年度作词：{lyricist['name']}")
    if kw_str:
        lines.append(f"- 全年最常听到的词：{kw_str}")

    return "\n".join(lines)


# ============================================================
# 公共 API · 第 3 层：当前歌的相关事实
# ============================================================

def _norm(s: str | None) -> str:
    return (s or "").strip().lower()


def _find_top_song(title: str, artist: str, facts: dict) -> dict | None:
    """title + artist 双匹配；artist 留空时仅按 title 匹配（兜底）。

    防止《山丘 - 金玟岐》TOP 8 被张冠李戴给《山丘 - 李宗盛》。
    """
    title_n = _norm(title)
    artist_n = _norm(artist)
    for s in facts.get("top_songs") or []:
        if _norm(s.get("title")) != title_n:
            continue
        if not artist_n:
            return s
        # top_songs 的 artists 是 list；任意 artist 命中即视为同一首
        song_artists = [_norm(a) for a in (s.get("artists") or [])]
        if artist_n in song_artists:
            return s
    return None


def _find_top_artist_rank(artist: str, facts: dict) -> tuple[int, dict] | None:
    artist_n = _norm(artist)
    for s in facts.get("top_artists") or []:
        if _norm(s.get("name")) == artist_n:
            return (int(s.get("rank") or 0), s)
    return None


def _find_special_moment(title: str, artist: str, facts: dict) -> dict | None:
    title_n = _norm(title)
    artist_n = _norm(artist)
    for m in facts.get("special_moments") or []:
        if _norm(m.get("song")) == title_n and (
            not artist_n or _norm(m.get("artist")) == artist_n
        ):
            return m
    return None


def _find_season_song(title: str, facts: dict) -> tuple[str, dict] | None:
    title_n = _norm(title)
    for season_key, info in (facts.get("seasons") or {}).items():
        if isinstance(info, dict) and _norm(info.get("song")) == title_n:
            return (season_key, info)
    return None


_SEASON_CN = {"spring": "春", "summer": "夏", "autumn": "秋", "winter": "冬"}


def pick_for_entry(entry) -> str:
    """规则化挑选与当前 entry 相关的事实，返回可直接拼进 prompt 的文本块。

    entry: PlaylistEntry（需有 title / artists / tags）
    返回：人话陈述，每条一行。空串 = 当前歌在听歌史里"没有戏剧性钩子"，LLM 自行发挥。

    组成：2018-2022 跨年命中钩子（放最前，跨年陪伴最有故事性）+ 2025 七条规则。
    总条数封顶，跨年钩子优先保留。
    """
    facts = _load()

    bullets: list[str] = []

    # 1. 跨年陪伴（来自 entry.tags 的 yearly:YYYY）
    years = sorted({int(t.split(":")[1]) for t in entry.tags if t.startswith("yearly:") and t.split(":")[1].isdigit()})
    if len(years) >= 2:
        bullets.append(f"- 这首歌出现在你的 {'、'.join(str(y) for y in years)} 年度歌单里——陪了你 {len(years)} 年。")
    elif len(years) == 1:
        bullets.append(f"- 这首歌是你 {years[0]} 年度歌单里的歌。")

    if facts:
        # 2. 月度独占艺人（来自 entry.tags 的 monthly_top_2025:MM）
        months = sorted({t.split(":")[1] for t in entry.tags if t.startswith("monthly_top_2025:")})
        if months:
            if len(months) >= 2:
                bullets.append(
                    f"- {entry.artist} 在 2025 年 {'、'.join(m + '月' for m in months)} 都是你单月最常听的歌手"
                    + ("——连霸 4 个月。" if len(months) >= 4 else "。")
                )
            else:
                bullets.append(f"- {entry.artist} 是你 2025 年 {months[0]} 月最常听的歌手。")

        # 3. 年度 top_artist 排名
        artist = entry.artist
        if artist:
            ta = _find_top_artist_rank(artist, facts)
            if ta:
                rank, info = ta
                mins = info.get("listening_minutes")
                note = info.get("note")
                line = f"- {artist} 是你 2025 年度第 {rank} 名歌手"
                if mins:
                    hours = mins / 60
                    line += f"（共听 {hours:.0f} 小时）"
                if note:
                    line += f"——{note}"
                line += "。"
                bullets.append(line)

        # 4. 年度作词作曲（同一艺人可能同时身兼两职）
        composer = facts.get("yearly_composer") or {}
        lyricist = facts.get("yearly_lyricist") or {}
        if artist and _norm(composer.get("name")) == _norm(artist):
            roles = []
            if composer.get("name"):
                roles.append("作曲")
            if lyricist.get("name") and _norm(lyricist.get("name")) == _norm(artist):
                roles.append("作词")
            if roles:
                tag_str = ""
                if composer.get("tag") and lyricist.get("tag") and lyricist["tag"] != composer["tag"]:
                    tag_str = f"——你的「{composer['tag']}」，也是你的「{lyricist['tag']}」"
                elif composer.get("tag"):
                    tag_str = f"——QQ 音乐叫他「{composer['tag']}」"
                bullets.append(f"- {artist} 包揽了你 2025 年度{'+'.join(roles)}{tag_str}。")

        # 5. 命中 top_songs（年度 TOP 10）
        if entry.title:
            top_song = _find_top_song(entry.title, artist, facts)
            if top_song:
                rank = top_song.get("rank")
                plays = top_song.get("play_count")
                mins = top_song.get("listening_minutes")
                line = f"- 这首歌是你 2025 年度歌单 TOP {rank}"
                if plays:
                    line += f"，循环了 {plays} 次"
                if mins:
                    line += f"（{mins} 分钟）"
                line += "。"
                bullets.append(line)

        # 6. 命中 special_moments（特别时刻）
        if entry.title:
            sm = _find_special_moment(entry.title, artist, facts)
            if sm:
                date = sm.get("date", "")
                time = sm.get("time")
                stype = sm.get("type", "")
                plays = sm.get("play_count")
                base = f"- {date}"
                if time:
                    base += f" {time}"
                base += f" 那天，你把这首歌"
                if "单曲循环" in stype and plays:
                    base += f"单曲循环了 {plays} 遍——它是你 2025 年的单曲循环冠军。"
                elif "深夜" in stype:
                    base += f"翻出来听——你 2025 年最深夜的一次。"
                else:
                    base += f"翻出来听——{stype}。"
                bullets.append(base)

        # 7. 命中 seasons（四季歌单）
        if entry.title:
            ss = _find_season_song(entry.title, facts)
            if ss:
                season_key, info = ss
                season_cn = _SEASON_CN.get(season_key, season_key)
                bullets.append(f"- 这首歌是 QQ 音乐为你挑的 2025 {season_cn}季歌单代表曲。")

    # 8. 跨年命中钩子（2018-2022 历年报告 top_songs / special_moments）
    history = _match_song_history(entry.title, entry.artist)

    # 跨年钩子放最前（更稀有、更有陪伴感），再接 2025 钩子；总数封顶
    all_bullets = history + bullets
    if not all_bullets:
        return ""
    MAX_BULLETS = 5
    all_bullets = all_bullets[:MAX_BULLETS]

    return "【关于这首歌，你的听歌史里有这些线索（请自然化用，不要照搬数字）】\n" + "\n".join(all_bullets)


# ============================================================
# 多年历史报告（2018-2022）· 容错归一化 + 跨年匹配
# ============================================================

@dataclass
class YearDigest:
    """单年报告归一化后的统一结构（屏蔽各年 schema 差异）。"""
    year: int
    total_songs: int | None = None
    total_hours: float | None = None
    yearly_keyword: str | None = None
    top_artist_name: str | None = None
    top_artist_note: str | None = None          # 浓缩：次数/分钟/描述/年度文案
    top_songs: list[dict] = field(default_factory=list)  # 归一 [{title, artist, plays}]
    moments: list[dict] = field(default_factory=list)    # special_moments 原样（字段容错读）
    cross_year: dict | None = None              # cross_year_comparison（2021/2022 有）
    quotes: list[str] = field(default_factory=list)      # 主播叙事金句池


def _extract_quotes(text: str) -> list[str]:
    """从 md 抽「## 主播叙事金句池」节里的列表项（去引号）。"""
    m = _QUOTE_SECTION_RE.search(text)
    if not m:
        return []
    quotes: list[str] = []
    for line in m.group(1).splitlines():
        lm = _QUOTE_LINE_RE.match(line)
        if lm:
            q = lm.group(1).strip().strip('"').strip()
            if q:
                quotes.append(q)
    return quotes


def _norm_songs(raw: Any) -> list[dict]:
    """归一各年异构的歌曲条目：title↔song、artist(str)↔artists(list)、plays↔play_count。"""
    out: list[dict] = []
    for s in raw or []:
        if not isinstance(s, dict):
            continue
        title = s.get("title") or s.get("song")
        if not title:
            continue
        artist = s.get("artist")
        if not artist:
            arts = s.get("artists")
            if isinstance(arts, list) and arts:
                artist = arts[0]
        plays = s.get("plays") or s.get("play_count")
        out.append({"title": str(title), "artist": str(artist or ""), "plays": plays})
    return out


def _normalize_year(year: int, facts: dict, quotes: list[str]) -> YearDigest:
    """把单年异构 facts 收敛成 YearDigest。所有字段都容错，缺失即 None/空。"""
    meta = facts.get("meta") or {}
    theme = facts.get("theme") or {}

    total_songs = meta.get("total_songs") or meta.get("total_plays")
    total_hours = meta.get("total_hours")
    if total_hours is None and meta.get("total_minutes"):
        try:
            total_hours = round(float(meta["total_minutes"]) / 60, 1)
        except (TypeError, ValueError):
            total_hours = None

    # 年度歌手：top_artist(单数 dict) 优先，否则 top_artists(列表)[0]
    top_artist_name: str | None = None
    top_artist_note: str | None = None
    ta = facts.get("top_artist")
    if isinstance(ta, dict) and ta.get("name"):
        top_artist_name = str(ta["name"])
        bits: list[str] = []
        if ta.get("play_count"):
            bits.append(f"{ta['play_count']} 次")
        if ta.get("listening_minutes"):
            try:
                bits.append(f"{float(ta['listening_minutes']) / 60:.0f} 小时")
            except (TypeError, ValueError):
                pass
        if ta.get("description"):
            bits.append(str(ta["description"]))
        if ta.get("yearly_quote"):
            bits.append(str(ta["yearly_quote"]))
        top_artist_note = "·".join(bits) if bits else None
    else:
        tas = facts.get("top_artists")
        if isinstance(tas, list) and tas and isinstance(tas[0], dict):
            top_artist_name = tas[0].get("name")
            mins = tas[0].get("listening_minutes")
            if mins:
                try:
                    top_artist_note = f"{float(mins) / 60:.0f} 小时"
                except (TypeError, ValueError):
                    pass

    # 个人高频歌：顶层 top_songs（2018/2019/2020）；没有就退挚爱歌手的 top_songs（2021）
    songs = _norm_songs(facts.get("top_songs"))
    if not songs and isinstance(ta, dict):
        songs = _norm_songs(ta.get("top_songs"))

    cy = facts.get("cross_year_comparison")
    return YearDigest(
        year=year,
        total_songs=total_songs,
        total_hours=total_hours,
        yearly_keyword=theme.get("yearly_keyword"),
        top_artist_name=top_artist_name,
        top_artist_note=top_artist_note,
        top_songs=songs,
        moments=[m for m in (facts.get("special_moments") or []) if isinstance(m, dict)],
        cross_year=cy if isinstance(cy, dict) else None,
        quotes=quotes,
    )


def _load_multiyear() -> "dict[int, YearDigest]":
    """惰性加载 2018-2022 各年报告 → 归一化 digest + 进程内缓存。"""
    global _MULTIYEAR_CACHE
    if _MULTIYEAR_CACHE is not None:
        return _MULTIYEAR_CACHE

    digests: dict[int, YearDigest] = {}
    for year in HISTORICAL_YEARS:
        path = REPORTS_ROOT / str(year) / f"qq_music_{year}年度听歌报告.md"
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            logger.warning(f"读取 {year} 听歌报告失败：{e}")
            continue
        merged: dict[str, Any] = {}
        for block in _YAML_BLOCK_RE.findall(text):
            try:
                data = yaml.safe_load(block)
            except yaml.YAMLError as e:
                logger.warning(f"{year} YAML 块解析失败：{e}")
                continue
            if isinstance(data, dict):
                merged.update(data)
        quotes = _extract_quotes(text)
        if merged or quotes:
            digests[year] = _normalize_year(year, merged, quotes)

    _MULTIYEAR_CACHE = digests
    if digests:
        logger.info(f"listening_facts 多年报告已加载：{sorted(digests)}")
    return digests


def _moment_hook(year: int, m: dict) -> str:
    """把某年的一条 special_moment 渲染成带年份的钩子句。"""
    song = m.get("song")
    mtype = str(m.get("type") or "")
    date = m.get("date")
    time = m.get("time")
    plays = m.get("plays")
    note = m.get("note")

    if date:
        when = str(date)
        if time:
            when += f" {time}"
        head = f"- {when}，"
    else:
        head = f"- {year} 年，"

    if plays and ("循环" in mtype or "狂听" in mtype or "冠军" in mtype):
        body = f"你把《{song}》单曲循环了 {plays} 遍"
    elif "最早" in mtype or "元气" in mtype:
        body = f"你那年最早起的一天在听《{song}》"
    elif "最晚" in mtype or "最迟" in mtype or "EMO" in mtype:
        body = f"你那年最迟的一夜在听《{song}》"
    elif "第一首" in mtype or "年初" in mtype:
        body = f"你那年的第一首歌是《{song}》"
    elif "邂逅" in mtype:
        body = f"你邂逅了《{song}》"
    else:
        body = f"你听了《{song}》"
        if mtype:
            body += f"（{mtype}）"

    tail = f"——{note}" if note else ""
    return f"{head}{body}{tail}。"


def _match_song_history(title: str, artist: str) -> list[str]:
    """在 2018-2022 历年报告里找当前歌的命中，返回带年份、已自然化的钩子列表。

    匹配口径与 2025 一致：title 必须相等（_norm）；artist 两边都有值时才要求一致，
    任一为空则只按 title 命中（防同名误配的同时保留召回）。同年 top_songs 与
    special_moments 各取一次，避免同年重复刷屏。
    """
    title_n = _norm(title)
    artist_n = _norm(artist)
    if not title_n:
        return []

    hooks: list[str] = []
    for year, dg in sorted(_load_multiyear().items()):
        # a) 年度高频 / 年度 TOP 歌
        for s in dg.top_songs:
            if _norm(s["title"]) != title_n:
                continue
            if artist_n and s["artist"] and _norm(s["artist"]) != artist_n:
                continue
            plays = s.get("plays")
            line = f"- 这首歌在你 {year} 年的高频榜里"
            line += f"，那年循环了 {plays} 次。" if plays else "。"
            hooks.append(line)
            break
        # b) 特别时刻
        for m in dg.moments:
            if _norm(m.get("song")) != title_n:
                continue
            ma = m.get("artist")
            if artist_n and ma and _norm(ma) != artist_n:
                continue
            hooks.append(_moment_hook(year, m))
            break

    return hooks


def _multiyear_arc() -> str:
    """2018-2022 多年听歌轨迹概览（宏观背景，每年一行）。"""
    digests = _load_multiyear()
    if not digests:
        return ""

    lines = [
        "【你的多年听歌轨迹（QQ 音乐 2018-2022 年度报告概览，宏观背景，与当前这首歌未必直接相关）】",
    ]
    for year, dg in sorted(digests.items()):
        bits: list[str] = []
        if dg.top_artist_name:
            bits.append(f"年度歌手 {dg.top_artist_name}")
        if dg.yearly_keyword:
            bits.append(f"关键词「{dg.yearly_keyword}」")
        if dg.total_hours:
            bits.append(f"听了 {dg.total_hours:.0f} 小时")
        cy = dg.cross_year or {}
        carry = cy.get("carryover_artist")
        bi = cy.get("bi_directional_artist")
        if isinstance(bi, dict):
            carry = bi.get("name") or carry
        if carry:
            bits.append(f"延续 {carry}")
        if cy.get("fading_artist"):
            bits.append(f"淡出 {cy['fading_artist']}")
        if bits:
            lines.append(f"- {year}：" + " · ".join(str(b) for b in bits))

    return "\n".join(lines) if len(lines) > 1 else ""
