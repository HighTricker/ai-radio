"""推荐服务：从候选歌单里选下一首最适合现在播的歌。

PRD V2 验收对应："基于 taste + feedback + weather 调 LLM 输出候选歌名"

设计：
- 输入：已过 dislike 阈值的 candidates、最近播放历史、feedback 聚合、可选 weather
- 输出：选中的 PlaylistEntry + 一句话推荐理由（直接给用户看）
- 失败：抛 RecommendError，调用方应回退到 cursor 顺序

时段适配（小时数）：
  深夜 [0,6) / 清晨 [6,9) / 上午 [9,12) / 中午 [12,14) /
  下午 [14,18) / 傍晚 [18,22) / 夜晚 [22,24)
"""
import json
import logging
import re
from datetime import datetime
from typing import Iterable

from .llm_providers import build_client_and_model
from .playlist import PlaylistEntry

logger = logging.getLogger(__name__)


class RecommendError(Exception):
    """推荐失败 —— 调用方应回退到 cursor 顺序选歌。"""


def _time_segment(hour: int) -> str:
    if hour < 6:
        return "深夜"
    if hour < 9:
        return "清晨"
    if hour < 12:
        return "上午"
    if hour < 14:
        return "中午"
    if hour < 18:
        return "下午"
    if hour < 22:
        return "傍晚"
    return "夜晚"


_WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _build_prompt(
    available: list[PlaylistEntry],
    recent_played: list[str],
    feedback_by_entry: dict[str, dict[str, int]],
    weather: dict | None,
) -> tuple[str, str]:
    """构造 (system_prompt, user_msg)。"""
    now = datetime.now()
    weekday = _WEEKDAYS[now.weekday()]
    seg = _time_segment(now.hour)

    liked = [k for k, v in feedback_by_entry.items() if v.get("like", 0) > 0]
    dislike_partial = [
        k for k, v in feedback_by_entry.items()
        if 0 < v.get("dislike", 0) < 2  # 有 dislike 信号但未达跳过阈值
    ]

    candidates_text = "\n".join(f"{i + 1}. {e.display}" for i, e in enumerate(available))
    recent_text = "\n".join(f"- {s}" for s in recent_played[-5:]) if recent_played else "（暂无）"
    liked_text = "\n".join(f"- {s}" for s in liked) if liked else "（暂无）"
    dislike_partial_text = (
        "\n".join(f"- {s}" for s in dislike_partial) if dislike_partial else "（暂无）"
    )
    if weather:
        weather_text = f"{weather.get('condition', '未知')} {weather.get('temp', '')}"
    else:
        weather_text = "（无数据）"

    system_prompt = (
        "你是 AI 电台的智能选歌器。从候选歌单里选 1 首最适合**现在**播放的歌。\n\n"
        "选择原则（按重要性排序）：\n"
        "1. 严格避开'最近播过'列表里的歌\n"
        "2. 时段适配：清晨偏阳光振奋 / 上午偏中性轻快 / 中午下午偏氛围 / "
        "傍晚偏抒情 / 夜晚偏温柔 / 深夜偏安静治愈\n"
        "3. 周末（周六周日）整体更轻松；工作日工作时段稍专注\n"
        "4. 优先用户已 like 的歌（如果时段适配同时成立）\n"
        "5. 轻度避开'部分 dislike 但未达跳过阈值'的歌\n"
        "6. 天气适配（有数据时）：雨天偏温柔，晴天偏明亮\n\n"
        "输出**严格 JSON**（无 markdown 代码块包裹），格式：\n"
        '{"song": "歌名 - 歌手", "reason": "20 字内一句话推荐理由（直接给用户看）"}\n\n'
        "**song 字段必须完全等于候选列表里的某一行**（去掉前面的序号和点）。"
    )

    user_msg = (
        f"【候选歌单（共 {len(available)} 首）】\n{candidates_text}\n\n"
        f"【上下文】\n"
        f"- 当前时间：{now.strftime('%Y-%m-%d %H:%M')}（{weekday}{seg}）\n"
        f"- 最近播过（不要重复）：\n{recent_text}\n"
        f"- 你 like 的歌：\n{liked_text}\n"
        f"- 你部分 dislike 的歌（未达跳过阈值）：\n{dislike_partial_text}\n"
        f"- 天气：{weather_text}\n"
    )
    return system_prompt, user_msg


def _parse_response(text: str) -> dict:
    """解析 LLM 返回。优先 json.loads，失败则尝试抠出第一个 JSON 对象。"""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 兜底：抠第一个 { ... }
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise RecommendError(f"LLM 返回无 JSON：{text[:200]}")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise RecommendError(f"LLM 返回无效 JSON：{text[:200]}") from e


def _match_entry(chosen: str, available: list[PlaylistEntry]) -> PlaylistEntry | None:
    """先精确匹配 display；失败再忽略大小写+空格模糊匹配。"""
    for entry in available:
        if entry.display == chosen:
            return entry
    normalized = chosen.lower().replace(" ", "")
    for entry in available:
        if entry.display.lower().replace(" ", "") == normalized:
            return entry
    return None


def recommend_next(
    candidates: list[PlaylistEntry],
    recent_played: Iterable[str],
    feedback_by_entry: dict[str, dict[str, int]],
    weather: dict | None = None,
) -> tuple[PlaylistEntry, str]:
    """从 candidates 里推荐下一首播。

    candidates: 已经过 dislike ≥ 阈值过滤后的候选（调用方负责）
    recent_played: 最近播放历史的 display 字符串（最近的在末尾）
    feedback_by_entry: {'title - artist': {'like': n, 'dislike': n}}
    weather: V3 接入后填，目前 None
    """
    if not candidates:
        raise RecommendError("候选列表为空")

    # 优先排除最近播过的，但若全部最近播过则放开
    recent_set = set(recent_played)
    available = [e for e in candidates if e.display not in recent_set]
    if not available:
        available = candidates
        logger.info("所有候选都最近播过，放开 recent 约束")

    system_prompt, user_msg = _build_prompt(
        available, list(recent_played), feedback_by_entry, weather
    )

    client, model = build_client_and_model()

    logger.info(
        f"调用推荐器：{len(available)} 候选 / 最近 {len(recent_set)} 首 / "
        f"like {sum(1 for v in feedback_by_entry.values() if v.get('like', 0) > 0)} 首"
    )

    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.7,
            top_p=0.95,
            max_completion_tokens=200,
            response_format={"type": "json_object"},
        )
    except Exception as e:
        raise RecommendError(f"LLM 调用失败：{type(e).__name__}: {e}") from e

    text = (completion.choices[0].message.content or "").strip()
    if not text:
        raise RecommendError("LLM 返回空内容")

    data = _parse_response(text)
    chosen = (data.get("song") or "").strip()
    reason = (data.get("reason") or "").strip()
    if not chosen:
        raise RecommendError(f"LLM 返回缺 song 字段：{data}")

    entry = _match_entry(chosen, available)
    if entry is None:
        raise RecommendError(f"LLM 返回的歌不在候选里：'{chosen}'")

    logger.info(f"推荐选中 {entry.display}：{reason}")
    return entry, reason
