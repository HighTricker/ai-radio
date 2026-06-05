"""事实注入：历史上的今天 + 名言库（V3 #7）。

让「今日掌故」和「一句话」两个文案 mode 不再纯靠 LLM 记忆，
而是基于真实数据创作（避免编造年份/作者）。

数据源：
- 历史事件：维基百科 REST API（zh.wikipedia.org/api/rest_v1/feed/onthisday/all/MM/DD），
  按日缓存到 data/facts/history/MM-DD.json（历史不变，永久缓存）。
- 名言：本地 data/facts/quotations.md，一行一句，自由编辑。首次运行自动初始化精选库。
"""
from __future__ import annotations

import json
import logging
import random
from datetime import datetime
from pathlib import Path

import httpx

from services.config import AI_RADIO_DIR

logger = logging.getLogger(__name__)

FACTS_DIR = AI_RADIO_DIR / "data" / "facts"
HISTORY_DIR = FACTS_DIR / "history"
QUOTATIONS_PATH = FACTS_DIR / "quotations.md"

WIKI_ONTHISDAY = "https://zh.wikipedia.org/api/rest_v1/feed/onthisday/all/{month:02d}/{day:02d}"

# 单次喂给 LLM 的上限（太多会膨胀 prompt 成本，太少不够选）
MAX_EVENTS = 10
MAX_BIRTHS = 5
MAX_DEATHS = 3

# 首启时写入的名言精选（中外混合，主题偏深夜电台调性）
SEED_QUOTATIONS = """\
# 名言库

> 一行一句格式。空行和以 `#` `>` 开头的行被跳过。
> 用户可以随时编辑、追加、删除。

我们生来就是孤独。 —— 余华《活着》

世界上有两种人，一种用十年得到一切，一种用一生失去一切。 —— 张爱玲

人生若只如初见，何事秋风悲画扇。 —— 纳兰性德

时间从来不语，却回答了所有问题。 —— 余光中

向晚意不适，驱车登古原。夕阳无限好，只是近黄昏。 —— 李商隐

孤独是生命的礼物。 —— 加西亚·马尔克斯

我们的生命，是一串问题。 —— 卡夫卡

也许，每一个男子全都有过这样的两个女人，至少两个。 —— 张爱玲《红玫瑰与白玫瑰》

万物皆有裂痕，那是光照进来的地方。 —— 莱昂纳德·科恩

爱情像是一只蝴蝶，捉住了，就死了。 —— 冯唐

每个人都会孤独地长大，然后再孤独地老去。 —— 村上春树

风月不知人世改，照旧人世旧。 —— 张爱玲

世界上最远的距离，是用我冷漠的心，对爱我的人，掘了一条无法跨越的沟渠。 —— 泰戈尔

人生在世，不过是路过。 —— 老舍

无可奈何花落去，似曾相识燕归来。 —— 晏殊

知人者智，自知者明。胜人者有力，自胜者强。 —— 老子

愿你出走半生，归来仍是少年。 —— 苏轼

念念不忘，必有回响。 —— 李叔同

时间会把心爱的人变得不再心爱，把心爱的事变得不再心爱。 —— 三毛

寂寞会发慌，孤独则是饱满的。 —— 蒋勋

行到水穷处，坐看云起时。 —— 王维

愿有岁月可回首，且以深情共白头。 —— 沈从文

我有所念人，隔在远远乡。 —— 白居易

最远的旅行，是从自己的身体到自己的内心。 —— 切·格瓦拉

人是一根脆弱的芦苇，但是一根有思想的芦苇。 —— 帕斯卡

世界以痛吻我，要我报之以歌。 —— 泰戈尔

一个人至少拥有一个梦想，有一个理由去坚强。 —— 三毛

愿你的眼里，有阳光的清澈。 —— 仓央嘉措

凡是过往，皆为序章。 —— 莎士比亚《暴风雨》

不要温和地走进那个良夜。 —— 狄兰·托马斯
"""


class FactsError(Exception):
    """事实注入失败的统一异常（路由层会兜底为空 fact，让 LLM 走原 prompt）"""


def _ensure_quotations() -> Path:
    """首次访问时把 SEED_QUOTATIONS 写盘，用户后续可自由编辑。"""
    if QUOTATIONS_PATH.exists():
        return QUOTATIONS_PATH
    QUOTATIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUOTATIONS_PATH.write_text(SEED_QUOTATIONS, encoding="utf-8")
    logger.info(f"初始化名言库：{QUOTATIONS_PATH}（30 条精选）")
    return QUOTATIONS_PATH


def pick_quotation() -> str:
    """从 quotations.md 随机取一句。空文件返回空串（路由层降级）。"""
    path = _ensure_quotations()
    lines: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#") or s.startswith(">"):
            continue
        lines.append(s)
    if not lines:
        return ""
    return random.choice(lines)


def _wiki_cache_path(month: int, day: int) -> Path:
    return HISTORY_DIR / f"{month:02d}-{day:02d}.json"


def _condense_event(item: dict) -> str | None:
    """把 wiki 一条 event/birth/death 压缩成「年份：文本」形式。"""
    text = (item.get("text") or "").strip()
    year = item.get("year")
    if not text:
        return None
    return f"{year}年：{text}" if year else text


def fetch_history_events(month: int, day: int) -> dict:
    """调维基百科 REST API。失败抛 FactsError，由调用方决定降级策略。"""
    url = WIKI_ONTHISDAY.format(month=month, day=day)
    try:
        # trust_env=True（默认）让 httpx 读 v2rayN 设置的代理（如有）
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            # 维基 REST API 要求 UA 含产品名 + 联系方式；缺联系会被风控 403
            resp = client.get(
                url,
                headers={
                    "User-Agent": "ai-radio/0.3 (https://github.com/your-username/ai-radio)",
                    "Accept": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        raise FactsError(f"维基 API 失败：{type(e).__name__}: {e}")

    events_raw = (data.get("events") or [])[:MAX_EVENTS * 2]
    births_raw = (data.get("births") or [])[:MAX_BIRTHS * 2]
    deaths_raw = (data.get("deaths") or [])[:MAX_DEATHS * 2]

    events = [c for c in (_condense_event(it) for it in events_raw) if c][:MAX_EVENTS]
    births = [c for c in (_condense_event(it) for it in births_raw) if c][:MAX_BIRTHS]
    deaths = [c for c in (_condense_event(it) for it in deaths_raw) if c][:MAX_DEATHS]

    return {"events": events, "births": births, "deaths": deaths}


def get_today_events(today: datetime | None = None) -> dict:
    """读「历史上的今天」。命中本地缓存直接返回；否则拉 wiki 后写盘。

    历史不变，按 MM-DD 永久缓存（不带年份），下次同一天直接读。
    失败返回空 dict 让 LLM 走原 prompt 路径（明确指示"不确定就模糊化"）。
    """
    today = today or datetime.now()
    month, day = today.month, today.day
    cache_path = _wiki_cache_path(month, day)

    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"facts 缓存损坏 {cache_path}：{e}，重新拉取")

    try:
        data = fetch_history_events(month, day)
    except FactsError as e:
        logger.warning(f"历史事件拉取失败：{e}")
        return {}

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"facts 写盘 {cache_path.name}：events={len(data['events'])} births={len(data['births'])}")
    return data


def format_history_for_prompt(today: datetime | None = None) -> str:
    """组装成可直接喂给 LLM 的中文段落。空数据时返回空串。"""
    data = get_today_events(today)
    if not data:
        return ""
    parts: list[str] = []
    if data.get("events"):
        parts.append("【历史事件】\n" + "\n".join(f"- {e}" for e in data["events"]))
    if data.get("births"):
        parts.append("【出生】\n" + "\n".join(f"- {e}" for e in data["births"]))
    if data.get("deaths"):
        parts.append("【逝世】\n" + "\n".join(f"- {e}" for e in data["deaths"]))
    return "\n\n".join(parts)
