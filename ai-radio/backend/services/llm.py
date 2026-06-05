"""LLM 主播稿生成（OpenAI 兼容协议，可在 MiMo / DeepSeek 等 provider 间切换）

provider 选择由 settings.llm_provider 决定，模型名由 settings.llm_model 决定
（缺省走 PROVIDERS 配置里的 default_model）；详见 services/llm_providers.py。

支持 3 个文案 mode：song_intro（纯歌曲介绍）/ song_intro_taste（结合听歌史的歌曲介绍）/ weather_mood（天气感悟）
每个 mode 对应 prompts/{mode}.md 一个 string.Template 模板。
接受 target_chars 参数实现 DJ 时间对齐（旁白长度 ≈ 前奏长度）
"""
import logging
from datetime import datetime
from pathlib import Path
from string import Template

from .llm_providers import build_client_and_model, get_provider_config

logger = logging.getLogger(__name__)

AI_RADIO_DIR = Path(__file__).resolve().parent.parent.parent
PROMPTS_DIR = AI_RADIO_DIR / "prompts"

SUPPORTED_MODES = ("song_intro", "song_intro_taste", "weather_mood")
DEFAULT_MODE = "song_intro_taste"


def _format_weather_block(env: dict | None) -> str:
    """构造 weather_mood 的事实素材块。

    - 有 weather + 地点 → 全字段
    - 只有 location/time/season（未配 qweather 或 API 失败）→ 略去天气
    - 都缺 → 提示模糊化叙述
    """
    if not env:
        return "【提示】此刻的环境素材暂不可知，请用「这是一个无主的时刻」式的开放写法兜底，不要编造天气或地点。"

    location = env.get("location") or {}
    weather = env.get("weather") or None
    city = (location.get("city") or "").strip()
    region = (location.get("region") or "").strip()
    time_of_day = (env.get("time_of_day") or "").strip()
    season = (env.get("season") or "").strip()

    lines: list[str] = []
    if city or region:
        loc_str = city or region
        if city and region and region != city:
            loc_str = f"{city} · {region}"
        lines.append(f"- 地点：{loc_str}")
    if time_of_day:
        lines.append(f"- 此刻时段：{time_of_day}")
    if season:
        lines.append(f"- 季节：{season}")
    if weather:
        text = (weather.get("text") or "").strip()
        temp = str(weather.get("temp") or "").strip()
        if text:
            line = f"- 天气：{text}"
            if temp:
                line += f"（{temp}°C）"
            lines.append(line)

    if not lines:
        return "【提示】环境素材本次为空，请用模糊的时空感写法，不要编造具体地点 / 天气。"

    return "【此刻的环境素材，请化用入旁白，不要照搬原文】\n" + "\n".join(lines)


def _load_prompt_template(mode: str) -> Template:
    path = PROMPTS_DIR / f"{mode}.md"
    if not path.exists():
        raise FileNotFoundError(f"文案模式 {mode} 缺失模板文件：{path}")
    return Template(path.read_text(encoding="utf-8"))


def generate_script(
    mode: str,
    song_title: str,
    artist: str,
    target_chars: int = 80,
    environment: dict | None = None,
    entry=None,
) -> str:
    """根据 mode + 歌名 + 歌手 + 目标字数，生成主播旁白稿。

    target_chars: 期望字数，由 DJ 时间对齐计算（前奏长度 - 1）* 4 字/秒
    mode: SUPPORTED_MODES 之一
    environment: weather_mood 模式专用，含 location/weather/time_of_day/season 的环境素材
    entry: V4.0 STEP 2 新增，song_intro 模式下会调 listening_facts 注入听歌史钩子
           （type 是 PlaylistEntry，不在签名里标 type 避免循环 import）
    """
    if mode not in SUPPORTED_MODES:
        raise ValueError(f"未知文案模式：{mode}，可选 {SUPPORTED_MODES}")

    client, model = build_client_and_model()
    provider_label = get_provider_config()["label"]

    min_chars = max(20, target_chars - 15)
    max_chars = target_chars + 10
    today = datetime.now().strftime("%Y 年 %m 月 %d 日")

    # 按 mode 注入真实事实，避免 LLM 编造。
    # song_intro（纯歌曲介绍）不注入任何素材；其余两档各自注入。
    fact_block = ""
    if mode == "weather_mood":
        fact_block = _format_weather_block(environment)
    elif mode == "song_intro_taste" and entry is not None:
        # 结合听歌史：注入用户听歌画像（宏观画像 + 当首歌相关事实）
        from services.listening_facts import get_macro_background, pick_for_entry
        macro = get_macro_background()
        specific = pick_for_entry(entry)
        parts = [p for p in (macro, specific) if p]
        fact_block = "\n\n".join(parts)

    template = _load_prompt_template(mode)
    system_prompt = template.safe_substitute(
        song_title=song_title,
        artist=artist or "（未署名）",
        min_chars=min_chars,
        max_chars=max_chars,
        today=today,
        fact_block=fact_block,
    )
    user_msg = (
        f"歌名：{song_title}\n"
        f"歌手：{artist}\n"
        f"文案模式：{mode}\n"
        f"目标字数：{target_chars}（{min_chars}-{max_chars}）"
    )

    logger.info(
        f"调用 {provider_label} {model} 生成稿件 [mode={mode}]：{song_title}-{artist} (~{target_chars} 字)"
    )

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.85,
        top_p=0.95,
        max_completion_tokens=600,
    )

    text = (completion.choices[0].message.content or "").strip()
    if not text:
        raise RuntimeError("LLM 返回空内容")
    return text
