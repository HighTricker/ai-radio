"""End-to-end test: new HTTP-only adapter fetching real song URL + lyric."""
import io
import sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\AI电台项目\ai-radio\backend")

from adapters.qqmusic import get_track_by_songmid

print("--- fetching 《后来》/刘若英 via :8080 HTTP ---")
t = get_track_by_songmid(
    "000XeLXA3X8CTH",
    title="后来",
    artists=["刘若英"],
    album="我等你",
    album_mid="0017zqT34WuQwa",
    duration_ms=341000,
)
if t and t.audio_url:
    print(f"[OK] SUCCESS!")
    print(f"  source: {t.source}")
    print(f"  audio_url len: {len(t.audio_url)}")
    print(f"  audio_url prefix: {t.audio_url[:80]}...")
    print(f"  cover: {(t.cover_url or '(empty)')[:60]}")
    print(f"  lyric: {len(t.lyric or '')} chars")
    if t.lyric:
        # 看歌词前两行确认是 LRC 不是密文
        lines = t.lyric.split("\n")[:2]
        for ln in lines:
            print(f"    {ln}")
else:
    print("[FAIL] track is None")
