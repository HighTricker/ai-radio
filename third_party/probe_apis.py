"""Probe :8080 song/lyric APIs to learn response shapes."""
import io
import json
import sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import httpx

# Read credential from config
cfg = json.loads(open(r"E:\AI电台项目\ai-radio\data\config.json", encoding="utf-8").read())
cred = (cfg.get("credentials") or {}).get("qqmusic_credential") or {}
cookies = {"musicid": str(cred["musicid"]), "musickey": cred["musickey"]}
for k in ("openid", "refresh_token", "access_token", "unionid", "str_musicid", "refresh_key"):
    if cred.get(k):
        cookies[k] = str(cred[k])
if cred.get("expired_at"):
    cookies["expired_at"] = str(cred["expired_at"])

print(f"Cookies: musicid={cookies['musicid']}, musickey len={len(cookies['musickey'])}")
print(f"Other cookie keys: {[k for k in cookies if k not in ('musicid', 'musickey')]}\n")

MID = "000XeLXA3X8CTH"  # 后来 / 刘若英

print(f"=== GET /song/{MID}/url ===")
r = httpx.get(f"http://127.0.0.1:8080/song/{MID}/url", cookies=cookies, timeout=15.0, trust_env=False)
print(f"HTTP {r.status_code}")
print(json.dumps(r.json(), ensure_ascii=False, indent=2)[:2000])

print(f"\n=== GET /song/{MID}/lyric ===")
r = httpx.get(f"http://127.0.0.1:8080/song/{MID}/lyric", cookies=cookies, timeout=15.0, trust_env=False)
print(f"HTTP {r.status_code}")
body = r.json()
# 缩短 lyric 内容方便看 schema
if isinstance(body.get("data"), dict):
    for k, v in list(body["data"].items()):
        if isinstance(v, str) and len(v) > 100:
            body["data"][k] = f"[{len(v)} chars]: {v[:80]}..."
print(json.dumps(body, ensure_ascii=False, indent=2)[:1500])
