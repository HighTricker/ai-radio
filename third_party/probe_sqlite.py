"""Read QQMusicApi sqlite credential store."""
import json
import sqlite3
import sys

DB = r"E:\AI电台项目\third_party\QQMusicApi\web\data\credentials.sqlite3"

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
print("TABLES:", cur.fetchall())

try:
    cur.execute("SELECT musicid, length(credential_json), updated_at, valid FROM credentials")
    rows = cur.fetchall()
    print(f"CREDENTIALS rows: {len(rows)}")
    for r in rows:
        print(f"  musicid={r[0]} cred_json_len={r[1]} updated_at={r[2]} valid={r[3]}")
    if rows:
        cur.execute("SELECT credential_json FROM credentials LIMIT 1")
        cred = json.loads(cur.fetchone()[0])
        print("FIELDS:", list(cred.keys()))
        print("musicid =", cred.get("musicid"))
        mk = str(cred.get("musickey", ""))
        print(f"musickey len = {len(mk)} (preview: {mk[:16]}...)" if mk else "musickey empty")
        # 输出完整 cred 给宝看
        print("\n=== FULL CREDENTIAL JSON (复制下面这段) ===")
        print(json.dumps(cred, ensure_ascii=False, indent=2))
except Exception as e:
    print("ERR:", e)
