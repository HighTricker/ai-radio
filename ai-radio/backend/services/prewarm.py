"""预制 5 首待播队列。

启动时后台跑 5 首完整 episode（选歌 → 多源 → 缓存 → 稿件 → TTS），
落到内存。`/api/v1/episode` 接到请求先 try_pop 命中则秒返回。
pop 完后台 refill 补一首，永远维持 5 首"已就绪"。

设计取舍：
- 仅预制 当前 voice_id + 当前 mode 组合（切换则清空重做）；多组合预制
  成本爆炸（5 voice × 4 mode = 20），且切换是低频操作。
- 30 分钟 staleness：超时项丢弃重做。兼顾环境/天气信号变化 vs 预热收益。
- weather_mood 由 generator 自己拒绝（环境瞬变，预制会撒谎）。
- 失败兜底：任意一首生成失败 → 跳过本轮，让 episode 走 cold path（无 0
  等待但仍能播）。绝不让预热错误冒泡到用户请求。
"""
import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger(__name__)

QUEUE_SIZE = 5
STALENESS_SECONDS = 30 * 60  # 30 分钟


@dataclass
class PrewarmItem:
    payload: dict           # 完整 episode response（与 /api/v1/episode 同形态）
    voice_id: Optional[str]
    mode: str
    playlist_display: str   # PlaylistEntry.display，用于 cursor / dislike 检查
    created_at: float       # time.time()，用于 staleness 检查


# 由 main.py 在启动期注入的「生成单个 PrewarmItem」工厂函数签名：
#   (voice_id: Optional[str], mode: str, exclude_displays: list[str]) -> Optional[PrewarmItem]
# - exclude_displays: 当前队列已有的 display 列表，让 generator 避免选重复
# - 返回 None 表示「这一轮无法生成」（推荐器无候选 / 多源全挂 / TTS 失败）
GeneratorFn = Callable[[Optional[str], str, list[str]], Optional[PrewarmItem]]


class PrewarmQueue:
    def __init__(self):
        self._items: list[PrewarmItem] = []
        self._lock = threading.Lock()
        self._refill_lock = threading.Lock()  # 防止多个 refill 线程并发
        self._current_voice: Optional[str] = None
        self._current_mode: Optional[str] = None
        self._generator: Optional[GeneratorFn] = None

    def set_generator(self, fn: GeneratorFn) -> None:
        self._generator = fn

    def start(self, voice_id: Optional[str], mode: str) -> None:
        """启动 / 切换：清空旧队列，后台填到 QUEUE_SIZE 首。"""
        with self._lock:
            self._items.clear()
            self._current_voice = voice_id
            self._current_mode = mode
        self._trigger_refill()

    def try_pop(
        self,
        voice_id: Optional[str],
        mode: str,
        is_disliked: Callable[[str], bool],
    ) -> Optional[PrewarmItem]:
        """消费一个队列项。命中后异步触发 refill。

        命中条件：voice/mode 匹配 + 未过期 + dislike 未超阈值。
        不命中（配置变化 / 队列空 / 过期 / dislike）→ 返回 None；调用方走 cold path。
        """
        now = time.time()
        config_changed = False
        result: Optional[PrewarmItem] = None
        with self._lock:
            if voice_id != self._current_voice or mode != self._current_mode:
                # 配置变了 → 整体丢弃 + 用新配置重启
                config_changed = True
                self._items.clear()
                self._current_voice = voice_id
                self._current_mode = mode
            else:
                while self._items:
                    item = self._items.pop(0)
                    if now - item.created_at > STALENESS_SECONDS:
                        logger.info(f"prewarm 项过期丢弃：{item.playlist_display}")
                        continue
                    if is_disliked(item.playlist_display):
                        logger.info(f"prewarm 项 dislike 阈值丢弃：{item.playlist_display}")
                        continue
                    result = item
                    break
        # 锁外触发后台 refill（无论命中与否都补）
        self._trigger_refill()
        if config_changed:
            logger.info(f"prewarm 配置变更：voice={voice_id}, mode={mode}（队列清空重建）")
        return result

    # === 内部 ===

    def _snapshot_displays(self) -> list[str]:
        with self._lock:
            return [it.playlist_display for it in self._items]

    def _trigger_refill(self) -> None:
        threading.Thread(target=self._refill_loop, daemon=True).start()

    def _refill_loop(self) -> None:
        """同步阻塞地把队列填满。已有 refill 线程在跑则直接退出（不排队）。"""
        if not self._refill_lock.acquire(blocking=False):
            return
        try:
            while True:
                with self._lock:
                    if len(self._items) >= QUEUE_SIZE:
                        return
                    voice = self._current_voice
                    mode = self._current_mode
                if self._generator is None:
                    logger.warning("prewarm generator 未注入，跳过 refill")
                    return
                excluded = self._snapshot_displays()
                try:
                    item = self._generator(voice, mode, excluded)
                except Exception as e:
                    # generator 必须自己兜底；这里只是兜兜底
                    logger.warning(f"prewarm 生成异常：{type(e).__name__}: {e}")
                    time.sleep(2)
                    continue
                if item is None:
                    # generator 主动返回 None（无候选 / 多源全挂等）→ 暂停本轮
                    logger.info("prewarm 生成返回 None，暂停本轮 refill")
                    return
                with self._lock:
                    if voice != self._current_voice or mode != self._current_mode:
                        # 生成期间配置变了，丢弃该项
                        logger.info(f"prewarm 项作废（生成期间配置变更）：{item.playlist_display}")
                        continue
                    self._items.append(item)
                    logger.info(
                        f"prewarm 入队 [{len(self._items)}/{QUEUE_SIZE}]：{item.playlist_display}"
                    )
        finally:
            self._refill_lock.release()


# 模块级单例（main.py import 即用）
queue = PrewarmQueue()
