"""验证 weather_mood 模式的天气注入。
直接跑：让用户一眼看清「环境数据 → prompt 素材块 → LLM 真实输出」。
"""
import json
import sys
from datetime import datetime
from pathlib import Path

# 让 stdout 用 UTF-8（Windows 默认 GBK 会吞中文）
sys.stdout.reconfigure(encoding="utf-8")

# 让 backend.* 能 import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from services.environment import EnvironmentError, get_environment
from services.llm import _format_weather_block, generate_script


def time_of_day(now=None):
    h = (now or datetime.now()).hour
    if h < 6 or h >= 23: return "深夜"
    if h < 9: return "清晨"
    if h < 12: return "上午"
    if h < 14: return "中午"
    if h < 17: return "下午"
    if h < 19: return "傍晚"
    return "夜晚"


def season(now=None):
    m = (now or datetime.now()).month
    if m in (3, 4, 5): return "春"
    if m in (6, 7, 8): return "夏"
    if m in (9, 10, 11): return "秋"
    return "冬"


# 1. 拉环境
print("=" * 60)
print("① 后端拉到的环境数据")
print("=" * 60)
try:
    env = get_environment()
    env["time_of_day"] = time_of_day()
    env["season"] = season()
    print(json.dumps(env, ensure_ascii=False, indent=2, default=str))
except EnvironmentError as e:
    print(f"拉取失败：{e}")
    env = {"location": {}, "weather": None, "time_of_day": time_of_day(), "season": season()}

print()
print("=" * 60)
print("② 注入给 LLM 的事实素材块（直接看 prompt 长什么样）")
print("=" * 60)
print(_format_weather_block(env))

print()
print("=" * 60)
print("③ LLM 真实写出的旁白稿（目标 60 字 / weather_mood 模式）")
print("=" * 60)
try:
    script = generate_script(
        "weather_mood",
        "晴天",
        "周杰伦",
        target_chars=60,
        environment=env,
    )
    print(script)
    print()
    print(f"[字数：{len(script)}]")
except Exception as e:
    print(f"生成失败：{type(e).__name__}: {e}")

print()
print("=" * 60)
print("验证清单")
print("=" * 60)
loc = (env.get("location") or {}).get("city", "")
weather = (env.get("weather") or {}).get("text", "")
tod = env.get("time_of_day", "")
sea = env.get("season", "")
print(f"地点字段：{'✓' if loc else '✗'} {loc}")
print(f"天气字段：{'✓' if weather else '✗ (没拉到，请检查 qweather_api_key)'} {weather}")
print(f"时段字段：{'✓' if tod else '✗'} {tod}")
print(f"季节字段：{'✓' if sea else '✗'} {sea}")
print()
print("如果上面 4 项都 ✓，且第 ③ 段稿件读起来融入了对应意象，")
print("说明天气感悟旁白链路从拉数据 → 注入 prompt → LLM 输出，全部跑通。")
