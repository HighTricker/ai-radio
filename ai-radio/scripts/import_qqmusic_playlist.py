"""QQ 音乐歌单分享链接 → 样本 B 格式 md（含 YAML 结构化数据块）

抓取走 QQ 音乐公开 cgi（fcg_ucc_getcdinfo_byids_cp.fcg），无需登录。
输出 md 文件人类可读 + YAML 代码块机器可解析。

用法：
    # 单链接
    python scripts/import_qqmusic_playlist.py "https://y.qq.com/n/ryqq_v2/playlist/9705855688?..." --output "年度报告截图/2018/qq_music_xxx.md" --year 2018

    # 批量（每行 'YYYY:url'）
    python scripts/import_qqmusic_playlist.py --batch "年度报告截图/年度歌单链接.md" --out-base "年度报告截图"

输出文件名规则：qq_music_<dissname>.md（dissname 经 sanitize 去掉 Windows 禁字符）
"""
import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

CGI_URL = "https://c.y.qq.com/qzone/fcg-bin/fcg_ucc_getcdinfo_byids_cp.fcg"
HEADERS = {
    "Referer": "https://y.qq.com/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


# === URL / cgi ===

def parse_disstid(url: str) -> str:
    """从 QQ 音乐分享链接提取 disstid（playlist 数字 ID）。"""
    for pattern in (r"/playlist/(\d+)", r"[?&]id=(\d+)", r"[?&]disstid=(\d+)"):
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    raise ValueError(f"无法从 URL 提取 disstid: {url}")


def fetch_playlist(disstid: str) -> dict:
    """调 cgi 拿歌单 JSON，返回 cdlist[0]（包含 dissname / songlist 等）。"""
    params = {
        "type": 1, "disstid": disstid, "utf8": 1, "format": "json",
        "loginUin": 0, "hostUin": 0, "inCharset": "utf-8", "outCharset": "utf-8",
        "notice": 0, "platform": "yqq.json", "needNewCode": 0,
    }
    url = f"{CGI_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("code") != 0:
        raise RuntimeError(f"cgi 非零 code: {data.get('code')}")
    cdlist = data.get("cdlist") or []
    if not cdlist:
        raise RuntimeError("cdlist 为空")
    return cdlist[0]


# === 文件名 / 文本工具 ===

def sanitize_filename(name: str) -> str:
    """剥离 Windows 禁止字符 + 句点（避免文件名结尾点的麻烦）。"""
    s = re.sub(r'[<>:"/\\|?*]', "", name)
    s = s.replace(".", "")
    s = s.strip()
    return s or "playlist"


def detect_language(text: str) -> str | None:
    """粗判语言：中文 / 英语 / 俄语 / 哈萨克语 / 日语 / 韩语。仅用于 tags。"""
    if not text:
        return None
    if re.search(r"[一-鿿]", text):
        return "zh"
    if re.search(r"[ҒғҚқҢңҮүҰұӘәӨөІі]", text):
        return "kk"  # 哈萨克语特有 Cyrillic 扩展字符
    if re.search(r"[Ѐ-ӿ]", text):
        return "ru"
    if re.search(r"[぀-ヿ]", text):
        return "ja"
    if re.search(r"[가-힯]", text):
        return "ko"
    if re.search(r"[A-Za-z]", text):
        return "en"
    return None


_LANG_LABEL = {"en": "英语", "ru": "俄语", "kk": "哈萨克语", "ja": "日语", "ko": "韩语"}


def yaml_str(s: str) -> str:
    """字符串安全输出为 YAML 字面量：含特殊字符就 JSON 双引号转义。"""
    if not s:
        return '""'
    if any(c in s for c in ':#-[]{},&*!|>"\'%@`') or s != s.strip():
        return json.dumps(s, ensure_ascii=False)
    return s


# === 样本 B：单首歌 → YAML 条目 ===

def song_to_yaml_entry(song: dict, year: int | None) -> str:
    title = (song.get("songname") or "").strip()
    title_orig = (song.get("songorig") or "").strip()
    artists = [s["name"] for s in (song.get("singer") or []) if s.get("name")]
    album = (song.get("albumname") or "").strip()
    duration_ms = (song.get("interval") or 0) * 1000
    songmid = song.get("songmid", "")
    songid = song.get("songid", 0)
    album_mid = song.get("albummid", "")

    # 标题：优先用 songorig（原版名，去掉 (Explicit) 等版本标记）
    canonical_title = title_orig or title
    version_note = None
    if title_orig and title and title_orig != title:
        version_note = f"QQ 音乐显示名 \"{title}\""

    lang = detect_language(canonical_title) or detect_language(album)

    tags = []
    if year:
        tags.append(f"yearly:{year}")
        tags.append(f"qq_{year}")
    if lang and lang != "zh":
        tags.append(_LANG_LABEL.get(lang, lang))

    qq_parts = []
    if songmid:
        qq_parts.append(f'songmid: "{songmid}"')
    if songid:
        qq_parts.append(f"songid: {songid}")
    if album_mid:
        qq_parts.append(f'album_mid: "{album_mid}"')

    lines = [
        f"  - title: {yaml_str(canonical_title)}",
        f"    artists: [{', '.join(yaml_str(a) for a in artists)}]",
        f"    album: {yaml_str(album)}",
        f"    duration_ms: {duration_ms}",
        f"    isrc: null",
    ]
    if lang:
        lines.append(f"    language: {lang}")
    if version_note:
        lines.append(f"    version_note: {yaml_str(version_note)}")
    lines.extend([
        f"    sources:",
        f"      qqmusic: {{ {', '.join(qq_parts)} }}",
        f"      netease: {{ id: null }}",
    ])
    if tags:
        lines.append(f"    tags: [{', '.join(tags)}]")
    return "\n".join(lines)


def build_md(playlist: dict, year: int | None, source_url: str) -> str:
    dissname = playlist.get("dissname", "未知歌单")
    nick = playlist.get("nickname", "")
    uin = playlist.get("encrypt_uin", "")
    disstid = playlist.get("disstid", "")
    songnum = playlist.get("songnum", 0)
    today = datetime.now().strftime("%Y-%m-%d")
    songlist = playlist.get("songlist") or []

    yaml_entries = "\n".join(song_to_yaml_entry(s, year) for s in songlist)
    title_with_year = f"{dissname}{f' ({year})' if year else ''}"

    return (
        f"# {title_with_year}\n\n"
        f"> 来源：QQ 音乐\n"
        f"> 歌单 ID：{disstid}\n"
        f"> 创建者：{nick}（uin: {uin}）\n"
        f"> 共 {songnum} 首\n"
        f"> 抓取时间：{today}\n"
        f"> 抓取方式：QQ 音乐公开 cgi（fcg_ucc_getcdinfo_byids_cp.fcg）\n"
        f"> 原始链接：{source_url}\n\n"
        f"```yaml\n"
        f"songs:\n{yaml_entries}\n"
        f"```\n"
    )


# === 主流程 ===

def import_one(url: str, year: int | None, out_path: Path | None, out_base: Path | None) -> Path:
    disstid = parse_disstid(url)
    print(f"[{year or '?'}] disstid={disstid} 抓取中...")
    playlist = fetch_playlist(disstid)
    md = build_md(playlist, year, url)

    if out_path is None:
        if out_base is None:
            raise ValueError("必须指定 --output 或 --out-base")
        dissname = playlist.get("dissname", f"playlist_{disstid}")
        sanitized = sanitize_filename(dissname)
        out_path = out_base / str(year) / f"qq_music_{sanitized}.md"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    songnum = playlist.get("songnum", 0)
    dissname = playlist.get("dissname", "?")
    print(f"  ✅ {year or '?'} 《{dissname}》：{songnum} 首 → {out_path}")
    return out_path


def main() -> None:
    p = argparse.ArgumentParser(description="QQ 音乐歌单分享链接 → 样本 B 格式 md")
    p.add_argument("url", nargs="?", help="单链接模式：分享 URL")
    p.add_argument("--output", help="单链接模式：输出 md 路径")
    p.add_argument("--year", type=int, help="年份标签（用于 tags + 文件名子目录）")
    p.add_argument("--batch", help="批量模式：'YYYY:url' 文件路径")
    p.add_argument("--out-base", help="批量模式：输出目录基础（每年一个子目录）")
    args = p.parse_args()

    if args.batch:
        if not args.out_base:
            sys.exit("❌ --batch 必须配 --out-base")
        out_base = Path(args.out_base)
        success, failed = 0, 0
        for raw in Path(args.batch).read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r"^(\d{4})\s*[:：]\s*(https?://\S+)", line)
            if not m:
                print(f"  ⚠️  跳过无法识别行：{raw[:80]}")
                continue
            year = int(m.group(1))
            url = m.group(2)
            try:
                import_one(url, year, None, out_base)
                success += 1
            except Exception as e:
                print(f"  ❌ {year} 抓取失败：{type(e).__name__}: {e}")
                failed += 1
        print(f"\n批量完成：成功 {success}，失败 {failed}")
        sys.exit(0 if failed == 0 else 1)

    # 单链接模式
    if not args.url:
        sys.exit("❌ 缺 url 参数（或用 --batch）")
    out_path = Path(args.output) if args.output else None
    out_base = Path(args.out_base) if args.out_base else None
    if out_path is None and (out_base is None or args.year is None):
        sys.exit("❌ 必须 --output；或同时 --out-base + --year")
    import_one(args.url, args.year, out_path, out_base)


if __name__ == "__main__":
    main()
