"""一次性探测脚本：用 qqmusic-api-python 库拿《山丘》李宗盛的直链。

运行：python scripts/probe_qqmusic.py
"""
import asyncio
import json
import random
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 直接读 config.json 拿 cookie，避免重复填值
ROOT = Path(__file__).resolve().parent.parent
cfg = json.loads((ROOT / "data" / "config.json").read_text(encoding="utf-8"))
raw_cookie = (cfg.get("credentials", {}).get("qqmusic_cookie") or "").strip()

MUSICID = 0
MUSICKEY = ""
for part in raw_cookie.split(";"):
    kv = part.strip().split("=", 1)
    if len(kv) != 2:
        continue
    k, v = kv[0].strip().lower(), kv[1].strip()
    if k == "uin":
        MUSICID = int(v.lstrip("o") or "0")
    elif k == "qm_keyst":
        MUSICKEY = v

print(f"MUSICID={MUSICID}  MUSICKEY_LEN={len(MUSICKEY)}")

from qqmusic_api import Client, Credential
from qqmusic_api.modules.song import SongFileInfo


async def main():
    credential = Credential(musicid=MUSICID, musickey=MUSICKEY)
    async with Client(credential=credential) as client:
        print("\n=== get_cdn_dispatch ===")
        cdn_dispatch = await client.song.get_cdn_dispatch()
        print(f"sip count={len(cdn_dispatch.sip)}")
        print(f"sip[0]={cdn_dispatch.sip[0] if cdn_dispatch.sip else None}")
        cdn = random.choice(cdn_dispatch.sip) if cdn_dispatch.sip else ""

        print("\n=== 批量测年度歌单代表歌曲 ===")
        cases = [
            ("003ryaYw2nWz55", "山丘 李宗盛"),
            ("000XeLXA3X8CTH", "后来 刘若英"),
            ("0043nSjv1TtpMv", "漠河舞厅 柳爽"),
            ("001cdurD2fY83O", "月半小夜曲 李克勤"),
            ("001tea9d1wIUbz", "每当我看到花瓣飘落... 南辞"),
        ]
        mids = [c[0] for c in cases]
        resp = await client.song.get_song_urls([SongFileInfo(mid=m) for m in mids])
        for info, (mid, name) in zip(resp.data, cases):
            status = "✅" if info.result == 0 and info.purl else "❌"
            url_head = (cdn + info.purl)[:90] if info.purl else "(无)"
            print(f"  {status} {name:<30}  result={info.result}  url={url_head}...")


if __name__ == "__main__":
    asyncio.run(main())
