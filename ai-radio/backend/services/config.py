"""配置文件读取（data/config.json）"""
import copy
import json
from pathlib import Path

# 项目根 = 三层之上：services -> backend -> ai-radio -> 项目根
AI_RADIO_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = AI_RADIO_DIR / "data" / "config.json"

# 进程内缓存 + 文件 mtime 失效：一次 episode 请求会重复读 config 十几次，缓存掉重复读盘；
# 配置面板写盘后 mtime 变 → 下次自动重载（无需重启，与 update_config 的「改完即生效」协同）。
_CONFIG_CACHE: dict | None = None
_CONFIG_MTIME: float | None = None


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"配置文件不存在：{CONFIG_PATH}。请按 PRD 创建并填入 API key。"
        )
    global _CONFIG_CACHE, _CONFIG_MTIME
    mtime = CONFIG_PATH.stat().st_mtime
    if _CONFIG_CACHE is None or _CONFIG_MTIME != mtime:
        _CONFIG_CACHE = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        _CONFIG_MTIME = mtime
    # 返回深拷贝：update_config 会就地 mutate 返回的 dict，绝不能污染缓存
    return copy.deepcopy(_CONFIG_CACHE)


def reset_config_cache() -> None:
    """测试 / 手动失效缓存用。"""
    global _CONFIG_CACHE, _CONFIG_MTIME
    _CONFIG_CACHE = None
    _CONFIG_MTIME = None


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
