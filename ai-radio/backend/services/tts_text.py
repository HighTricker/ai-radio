"""朗读文本归一化：把「显示用文本」净化成「TTS 用文本」。

显示层保持阿拉伯数字（`2020年` 好看）；朗读层把年份逐字转中文（`二零二零年`），
避免 Fish Audio 把 `2020` 念成「两千零二十」。本函数只在 `synthesize()` 合成前调用，
不影响前端显示的 `script`（payload["script"] 永远是原文）。

当前规则（v1）——仅处理 4 位数字年份：
  - 单个年份：`2020年` → `二零二零年`；`1969年7月20日` → `一九六九年7月20日`（月/日不动）
  - 数字与「年」之间的空格也放行：`2020 年` → `二零二零年`（大模型很常这么写）
  - 年份范围：`2018-2020年` → `二零一八到二零二零年`（符号连接号读作「到」）
  - 排除「年代」：`90年代`/`2000年代` 不动（那是「九十年代」，不能念「九零年代」）
  - 月/日/数量/金额/时间（`3首歌`、`第2首`、`19:30`）不动，TTS 默认就念对

这是一个「读稿净化」的口子，将来英文缩写、`%`、`℃`、URL、表情等念错都可在此扩展规则。
"""
import re

_DIGITS = {
    "0": "零", "1": "一", "2": "二", "3": "三", "4": "四",
    "5": "五", "6": "六", "7": "七", "8": "八", "9": "九",
}
_RANGE_SEP_SYMBOLS = "-~－—"  # 这些连接号朗读时统一转成「到」；「到 / 至」保留原字

# 数字与「年」之间可能有空格（大模型很常写 "2020 年"），放行水平空白：半角空格 / 制表 /
# 全角空格(U+3000) / 不换行空格(U+00A0)，但不含换行，避免跨行误匹配。
# 这是「缓存歌还念错」的真凶：旧正则要求数字与年紧挨着，带空格的年份全漏了。
_WS = r"[ \t　 ]*"

# 年份范围：4 位 + 连接号 + 4 位 +（空白）年（且后面不是「代」）。first 有 (?<!\d) 防吞更长数字尾部。
_YEAR_RANGE_RE = re.compile(
    r"(?<!\d)(\d{4})" + _WS + r"([-~－—到至])" + _WS + r"(\d{4})" + _WS + r"年(?!代)"
)
# 单个年份：4 位 +（空白）年（前不接数字、后不接「代」）
_YEAR_SINGLE_RE = re.compile(r"(?<!\d)(\d{4})" + _WS + r"年(?!代)")


def _digits_to_cn(s: str) -> str:
    """'2020' → '二零二零'（逐字）。"""
    return "".join(_DIGITS[c] for c in s)


def _repl_range(m: "re.Match") -> str:
    a, sep, b = m.group(1), m.group(2), m.group(3)
    conn = "到" if sep in _RANGE_SEP_SYMBOLS else sep
    return f"{_digits_to_cn(a)}{conn}{_digits_to_cn(b)}年"


def _repl_single(m: "re.Match") -> str:
    return f"{_digits_to_cn(m.group(1))}年"


def normalize_for_tts(text: str) -> str:
    """把待合成文本里的 4 位年份逐字化。显示文本请勿经过本函数。"""
    if not text:
        return text
    # 先处理范围（范围里的第一个年份不直接挨着「年」，单个规则覆盖不到）
    text = _YEAR_RANGE_RE.sub(_repl_range, text)
    # 再处理剩余的单个年份
    text = _YEAR_SINGLE_RE.sub(_repl_single, text)
    return text
