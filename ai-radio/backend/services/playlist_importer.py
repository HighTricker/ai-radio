"""年度歌单导入器：把 QQ 音乐 / 网易云 / Spotify 等年度榜单合并到 taste.md

设计目标：
- 解析多种粗糙输入格式（用户复制粘贴的真实数据，往往带排名/emoji/特殊分隔）
- 与现有 taste.md 去重合并（不重复添加已有歌）
- 按来源标签分组（在 taste.md 加 `## 来源` markdown 二级标题，playlist.py 已跳过 # 行所以兼容）

支持的输入行格式：
- 标准：`歌名 - 歌手`
- 括号：`歌名（歌手）` / `歌名(歌手)`
- 带排名：`1. 歌名 - 歌手` / `01 歌名 - 歌手` / `①  歌名 - 歌手` / `一、歌名 - 歌手`
- 带 emoji / 方括号标签：`🎵 [VIP] 歌名 - 歌手`
- 网易云常见：`歌名 by 歌手` / `歌名 by 歌手 (专辑)`
- 兜底：`歌名 歌手`（最后一个空格切，启发式，可能误判）
"""
import re
from typing import Iterable

from .playlist import PlaylistEntry, TASTE_PATH, _normalize_key, load_playlist


# === 行清洗：去掉常见前缀噪音 ===

# 排名前缀：阿拉伯数字 + 标点；中文数字 + 顿号/句号；圆圈数字
_RANK_PREFIX_RE = re.compile(
    r"^\s*(?:"
    r"\d+[\.\。、:：]\s*"          # 1. / 1、 / 1:
    r"|\d+\s+(?=\S)"              # 1 后跟空格（要求后面有内容）
    r"|[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]\s*"
    r"|[一二三四五六七八九十]+\s*[、.．]\s*"
    r"|TOP\s*\d+\s*[\.\。、:：\-]?\s*"
    r")"
)

# 方括号包裹的小标签：[VIP] [TOP1] 【新】
_BRACKETS_PREFIX_RE = re.compile(r"^\s*[\[【][^\]】]{1,8}[\]】]\s*")

# 前置 emoji（保守只剥前面）
_EMOJI_PREFIX_RE = re.compile(
    r"^\s*[\U0001F300-\U0001FAFF☀-➿←-⇿✀-➿]+\s*"
)

# "歌名（歌手）" / "歌名(歌手)" — 注意末尾匹配，避免与歌名内括号冲突
_PAREN_TAIL_RE = re.compile(r"^(.+?)\s*[（(]\s*(.+?)\s*[)）]\s*$")

# 网易云风格 "歌名 by 歌手" / "歌名 by 歌手 (xxx)"
_BY_RE = re.compile(r"^(.+?)\s+by\s+(.+?)(?:\s*[（(].+?[)）])?\s*$", re.IGNORECASE)


def _clean_prefix(line: str) -> str:
    """重复剥离常见前缀直到稳定。"""
    s = line.strip()
    for _ in range(6):
        before = s
        s = _BRACKETS_PREFIX_RE.sub("", s)
        s = _EMOJI_PREFIX_RE.sub("", s)
        s = _RANK_PREFIX_RE.sub("", s)
        if s == before:
            break
    return s.strip()


def _is_noise_line(line: str) -> bool:
    """整行明显不是歌曲：标题、引用、纯数字（播放量）、太短、URL。"""
    s = line.strip()
    if not s:
        return True
    if s.startswith(("#", ">", "//", "—", "─", "===", "---")):
        return True
    if re.fullmatch(r"[\d,.\s亿万千百播放次听]+", s):  # 纯播放量（含小数，如 1.2亿）
        return True
    if s.startswith(("http://", "https://", "www.")):
        return True
    if len(s) < 2:
        return True
    return False


def _parse_entry(raw: str) -> PlaylistEntry | None:
    """从一行文本提取 (title, artist)。无法识别返回 None。"""
    if _is_noise_line(raw):
        return None
    line = _clean_prefix(raw)
    if not line or _is_noise_line(line):
        return None

    # 1) 优先 " - "（含全角破折号变体）
    for sep in (" - ", " — ", " – ", "—", "–"):
        if sep in line:
            parts = line.split(sep, 1)
            title = parts[0].strip()
            artist = parts[1].strip() if len(parts) > 1 else ""
            # 歌手段可能再含 " - 专辑"，只取第一段
            if " - " in artist:
                artist = artist.split(" - ", 1)[0].strip()
            if title:
                return PlaylistEntry(title, artist)

    # 2) "歌名 by 歌手"
    m = _BY_RE.match(line)
    if m:
        return PlaylistEntry(m.group(1).strip(), m.group(2).strip())

    # 3) "歌名（歌手）"
    m = _PAREN_TAIL_RE.match(line)
    if m:
        return PlaylistEntry(m.group(1).strip(), m.group(2).strip())

    # 4) 兜底：最后一个空格切（中文歌名/歌手内可能有空格，不一定准）
    #    至少 2 段且每段都非空才接受，否则当作纯歌名
    parts = line.rsplit(maxsplit=1)
    if len(parts) == 2 and all(p.strip() for p in parts):
        return PlaylistEntry(parts[0].strip(), parts[1].strip())

    # 5) 完全没歌手信息
    return PlaylistEntry(line, "")


def parse_playlist_text(raw_text: str) -> list[PlaylistEntry]:
    """把多行文本解析为 PlaylistEntry 列表。无法识别的行直接丢弃。"""
    entries: list[PlaylistEntry] = []
    for raw in raw_text.splitlines():
        entry = _parse_entry(raw)
        if entry is not None:
            entries.append(entry)
    return entries


# === 合并到 taste.md ===

def _dedup(entries: Iterable[PlaylistEntry]) -> list[PlaylistEntry]:
    """同一批输入内部也去重（按出现顺序保留首次）。"""
    seen: set[str] = set()
    out: list[PlaylistEntry] = []
    for e in entries:
        k = _normalize_key(e)
        if k in seen:
            continue
        seen.add(k)
        out.append(e)
    return out


def merge_into_taste(
    new_entries: list[PlaylistEntry],
    source_label: str,
    *,
    dry_run: bool = False,
) -> tuple[list[PlaylistEntry], int]:
    """把 new_entries 合并到 taste.md，按 source_label 加 ## 分组。

    去重：与现有 taste.md（含所有分组）逐条比对，已存在的跳过。批内重复也只保留首次。
    返回 (added_entries, skipped_count)。dry_run=True 时不写文件。
    """
    new_entries = _dedup(new_entries)
    existing_keys = {_normalize_key(e) for e in load_playlist()}
    added: list[PlaylistEntry] = []
    skipped = 0
    for e in new_entries:
        if _normalize_key(e) in existing_keys:
            skipped += 1
            continue
        added.append(e)
        existing_keys.add(_normalize_key(e))

    if dry_run or not added:
        return added, skipped

    section = f"\n## {source_label}\n\n"
    section += "\n".join(e.display for e in added) + "\n"

    # 用 'a' 追加；taste.md 末尾未必有换行，前面已带 \n，安全
    with TASTE_PATH.open("a", encoding="utf-8") as f:
        f.write(section)
    return added, skipped
