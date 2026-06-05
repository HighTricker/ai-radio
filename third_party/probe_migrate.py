"""Migration probe: 把 config.json 里的 credential 写入 :8080 sqlite + 测不带 cookie 调 song API."""
import io
import json
import sqlite3
import sys
import time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 1. 读 config.json 里的 credential
cfg = json.loads(open(r"E:\AI电台项目\ai-radio\data\config.json", encoding="utf-8").read())
cred_dict = (cfg.get("credentials") or {}).get("qqmusic_credential")
if not cred_dict:
    print("[FAIL] config.json 里没 qqmusic_credential")
    sys.exit(1)
print(f"[OK] config.json credential: musicid={cred_dict['musicid']} keys={list(cred_dict.keys())}")

# 2. 用 SDK Credential 构造 + 序列化（snake_case → 标准 JSON via by_alias）
from qqmusic_api import Credential
try:
    cred_obj = Credential(**cred_dict)
    print(f"[OK] Credential 构造成功（snake_case 直接吃）: musicid={cred_obj.musicid}")
except Exception as e:
    print(f"[FAIL] Credential(**snake_case): {type(e).__name__}: {e}")
    # try with model_validate
    try:
        cred_obj = Credential.model_validate(cred_dict)
        print(f"[OK] model_validate 成功")
    except Exception as e2:
        print(f"[FAIL] model_validate: {type(e2).__name__}: {e2}")
        sys.exit(1)

json_str = cred_obj.model_dump_json(by_alias=True)
print(f"[OK] model_dump_json(by_alias=True) 长度 {len(json_str)}")
keys = list(json.loads(json_str).keys())
print(f"     字段名: {keys}")

# 3. INSERT 到 sqlite
db_path = r"E:\AI电台项目\third_party\QQMusicApi\web\data\credentials.sqlite3"
conn = sqlite3.connect(db_path)
conn.execute(
    """
    INSERT INTO credentials (musicid, credential_json, updated_at, valid)
    VALUES (?, ?, ?, 1)
    ON CONFLICT(musicid) DO UPDATE SET
      credential_json = excluded.credential_json,
      updated_at = excluded.updated_at,
      valid = 1
    """,
    (cred_obj.musicid, json_str, int(time.time())),
)
conn.commit()
conn.close()
print(f"[OK] 写入 sqlite 成功 musicid={cred_obj.musicid}")

# 4. 验证：不传 cookie 调 :8080 song/url API（应该 :8080 用默认凭据）
import httpx
print("\n--- 测试: 不传 cookie 调 :8080 /song/000XeLXA3X8CTH/url ---")
r = httpx.get(
    "http://127.0.0.1:8080/song/000XeLXA3X8CTH/url",
    cookies={},  # 显式空 cookie
    timeout=15.0,
    trust_env=False,
)
print(f"HTTP {r.status_code}")
body = r.json()
if body.get("code") == 0:
    info = body["data"]["midurlinfo"][0]
    print(f"[OK] result={info['result']} purl_len={len(info['purl'] or '')}")
    if info.get("purl"):
        print(">>> 全局默认凭据生效，:8080 自动用 sqlite 里的 cred 调腾讯成功")
    else:
        print("[WARN] purl 空，可能默认凭据没启用")
else:
    print(f"[FAIL] {body}")
