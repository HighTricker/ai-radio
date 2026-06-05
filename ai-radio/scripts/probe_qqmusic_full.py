"""完整链路测试：复用项目 adapter，验证 get_track_by_songmid 能拿到可播放 mp3 + 歌词。

跑：python scripts/probe_qqmusic_full.py
"""
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

import urllib.request

from adapters.qqmusic import get_track_by_songmid

CASES = [
    ("003ryaYw2nWz55", "山丘", ["李宗盛"], "山丘", "001uIPMD3SDIVy"),
    ("000XeLXA3X8CTH", "后来", ["刘若英"], "我等你到三十五岁", ""),
    ("0043nSjv1TtpMv", "漠河舞厅", ["柳爽"], "漠河舞厅", ""),
]


def _head_check(url: str) -> tuple[int, int]:
    """对直链发 GET，读前 32KB，返回 (status, bytes_read)。"""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://y.qq.com/",
            "Range": "bytes=0-32767",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = r.read()
            return (r.status, len(data))
    except Exception as e:
        return (-1, 0)


for songmid, title, artists, album, album_mid in CASES:
    print(f"\n========== {title} - {'/'.join(artists)} ==========")
    t0 = time.time()
    track = get_track_by_songmid(
        songmid,
        title=title,
        artists=artists,
        album=album,
        album_mid=album_mid,
    )
    dt = time.time() - t0
    if track is None:
        print(f"  ❌ get_track_by_songmid 返回 None  ({dt:.2f}s)")
        continue

    print(f"  ✅ 拿到 Track ({dt:.2f}s)")
    print(f"     source_id   = {track.source_id}")
    print(f"     audio_url   = {track.audio_url[:100]}...")
    print(f"     cover_url   = {track.cover_url}")
    print(f"     lyric       = {('有 (' + str(len(track.lyric)) + ' chars)') if track.lyric else '无'}")
    print(f"     expire_at   = {track.audio_url_expire_at}  (剩 {(track.audio_url_expire_at - int(time.time()))//60} 分钟)")

    # 实际探测直链
    status, nbytes = _head_check(track.audio_url)
    if status in (200, 206):
        print(f"     下载验证    = ✅ HTTP {status}, 读到 {nbytes} bytes")
    else:
        print(f"     下载验证    = ❌ HTTP {status}（防盗链 / vkey 失效）")

    # 歌词前两行预览
    if track.lyric:
        lines = [l for l in track.lyric.split("\n") if l.strip()][:3]
        print("     歌词预览:")
        for l in lines:
            print(f"       {l}")
