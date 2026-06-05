"""验证主播 3 mode 改造：song_intro（纯歌曲介绍）/ song_intro_taste（结合听歌史）/ weather_mood。

直接调 generate_script（绕过取流），对比纯版 vs 结合版对同一首歌的写法差异。
跑法：ai-radio/.venv/Scripts/python.exe ai-radio/scripts/probe_modes.py
"""
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("HTTPS_PROXY", "http://127.0.0.1:10808")  # deepseek 走 VPN 代理
os.environ.setdefault("HTTP_PROXY", "http://127.0.0.1:10808")

from services.llm import generate_script, SUPPORTED_MODES  # noqa: E402
from services.playlist import PlaylistEntry  # noqa: E402

print("SUPPORTED_MODES:", SUPPORTED_MODES)
entry = PlaylistEntry("王牌冤家", "李荣浩")  # 2018 国庆单曲循环 44 遍，有画像钩子

for mode, desc in (("song_intro", "纯歌曲介绍（应不提听歌史）"),
                   ("song_intro_taste", "结合听歌史（应用上 2018/循环数）")):
    print(f"\n{'=' * 58}\n【{mode}】{desc}\n{'=' * 58}")
    try:
        print(generate_script(mode, "王牌冤家", "李荣浩", 60, entry=entry))
    except Exception as ex:
        print(f"[生成失败] {type(ex).__name__}: {ex}")
