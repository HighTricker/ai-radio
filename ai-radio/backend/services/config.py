"""配置文件读取（data/config.json）"""
import json
from pathlib import Path

# 项目根 = 三层之上：services -> backend -> ai-radio -> 项目根
AI_RADIO_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = AI_RADIO_DIR / "data" / "config.json"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"配置文件不存在：{CONFIG_PATH}。请按 PRD 创建并填入 API key。"
        )
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def get_credential(key: str) -> str:
    cfg = load_config()
    val = cfg.get("credentials", {}).get(key, "").strip()
    if not val or val.startswith("请在此填入"):
        raise ValueError(
            f"配置项「credentials.{key}」为空或仍是占位符，请在 {CONFIG_PATH} 中填入真实值。"
        )
    return val


def get_voices() -> list[dict]:
    """返回 voice_options 列表 [{id, name}, ...]。

    优先 credentials.voice_options 数组；否则 fallback 到 voice_id 单值。
    自动过滤掉空 id 或占位符项。
    """
    cfg = load_config()
    creds = cfg.get("credentials", {}) or {}
    options = creds.get("voice_options") or []
    valid = []
    if isinstance(options, list):
        for v in options:
            if not isinstance(v, dict):
                continue
            vid = (v.get("id") or "").strip()
            if not vid or vid.startswith("请"):
                continue
            valid.append({"id": vid, "name": v.get("name") or vid[:8]})
    if valid:
        return valid
    # fallback：兼容老配置只有 voice_id 单值
    fallback_id = (creds.get("voice_id") or "").strip()
    if fallback_id and not fallback_id.startswith("请"):
        return [{"id": fallback_id, "name": "默认主播"}]
    return []
