"""LLM provider 抽象层：基于 OpenAI 兼容协议封装 DeepSeek 写稿服务。

为什么保留抽象层：
- 用户在前端可以输 apikey
- 未来加 OpenAI / Qwen / GLM 等只需往 PROVIDERS 加一条
- llm.py 和 recommender.py 不再重复 base_url / default_model 常量
"""
from openai import OpenAI

from .config import get_credential, load_config

# provider_id → 配置；新增 provider 直接在这里加一行
PROVIDERS: dict[str, dict] = {
    "deepseek": {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "api_key_field": "deepseek_api_key",
        "default_model": "deepseek-chat",
    },
}

DEFAULT_PROVIDER = "deepseek"


def get_current_provider() -> str:
    """从 config.settings.llm_provider 读当前 provider；未配置或无效值 → 兜底 deepseek。"""
    cfg = load_config()
    p = (cfg.get("settings", {}) or {}).get("llm_provider")
    if isinstance(p, str) and p in PROVIDERS:
        return p
    return DEFAULT_PROVIDER


def get_provider_config(provider: str | None = None) -> dict:
    """返回 provider 配置 dict。provider 缺省 → 当前。"""
    pid = provider or get_current_provider()
    if pid not in PROVIDERS:
        raise ValueError(f"未知 LLM provider: {pid}（可选 {list(PROVIDERS)}）")
    return PROVIDERS[pid]


def get_required_api_key_field() -> str:
    """返回当前 provider 对应的 apikey 字段名，给 _REQUIRED_KEYS 动态校验用。"""
    return get_provider_config()["api_key_field"]


def build_client_and_model(provider: str | None = None) -> tuple[OpenAI, str]:
    """构造 OpenAI 兼容 client + 解析最终模型名。

    模型名优先级：settings.llm_model（用户填的）> provider default_model
    用户填了非空字符串就用，否则走该 provider 的默认。
    """
    p = get_provider_config(provider)
    api_key = get_credential(p["api_key_field"])
    client = OpenAI(api_key=api_key, base_url=p["base_url"])

    cfg = load_config()
    user_model = (cfg.get("settings", {}) or {}).get("llm_model")
    model = user_model.strip() if isinstance(user_model, str) and user_model.strip() else p["default_model"]
    return client, model
