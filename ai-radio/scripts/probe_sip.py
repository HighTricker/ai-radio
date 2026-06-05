"""试 7 个 sip 节点哪个能下《山丘》。"""
import asyncio
import json
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
os.environ["NO_PROXY"] = ".qq.com,.gtimg.cn"

import httpx
from qqmusic_api import Client, Credential
from qqmusic_api.modules.song import SongFileInfo

cfg = json.loads(Path("E:/AI电台项目/ai-radio/data/config.json").read_text(encoding="utf-8"))
raw = cfg["credentials"]["qqmusic_cookie"]
uin = 0
key = ""
for p in raw.split(";"):
    kv = p.strip().split("=", 1)
    if len(kv) != 2:
        continue
    k, v = kv[0].strip().lower(), kv[1].strip()
    if k == "uin" and v.lstrip("o").isdigit():
        uin = int(v.lstrip("o"))
    elif k == "qm_keyst":
        key = v


async def go():
    cred = Credential(musicid=uin, musickey=key)
    async with Client(credential=cred) as c:
        cd = await c.song.get_cdn_dispatch()
        urls = await c.song.get_song_urls([SongFileInfo(mid="003ryaYw2nWz55")])
        info = urls.data[0]
        print(f"purl: {info.purl[:90]}")
        print(f"result: {info.result}")
        print(f"共 {len(cd.sip)} 个 sip 节点：")
        headers = {
            "Referer": "https://y.qq.com/",
            "Origin": "https://y.qq.com",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
        }
        for i, sip in enumerate(cd.sip):
            full = sip + info.purl
            try:
                r = httpx.head(full, timeout=10, follow_redirects=True, headers=headers)
                cl = r.headers.get("content-length", "?")
                print(f"  [{i}] {sip[:50]:<52} → HTTP {r.status_code}  content-length={cl}")
            except Exception as e:
                print(f"  [{i}] {sip[:50]:<52} → 异常 {type(e).__name__}: {str(e)[:60]}")


asyncio.run(go())
