"""统一 Track 数据接口。所有音乐源适配器输出这个结构，前端只认它。"""
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Track:
    """跨平台统一歌曲对象。"""
    source: str                 # "netease" / "local" / ...
    source_id: str              # 平台原始 ID（local 用文件名）
    title: str
    artists: list[str]
    album: str = ""
    cover_url: str = ""
    duration_ms: int = 0
    audio_url: Optional[str] = None         # 直链；None 表示无法播放
    audio_url_expire_at: Optional[int] = None  # epoch 秒，过期需要重取
    lyric: Optional[str] = None             # LRC 字符串（前端解析时间戳）
    fee: str = "free"                       # free / vip / trial / nocopyright

    def to_dict(self) -> dict:
        return asdict(self)
