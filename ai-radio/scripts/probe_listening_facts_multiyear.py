"""验证 listening_facts 多年画像（V4.2）：跨年命中钩子 + 多年轨迹概览。

用轻量 stub 模拟 PlaylistEntry 接口（title / artists / artist / tags），聚焦验证
listening_facts 的多年加载与匹配逻辑，不依赖 playlist 构造细节。

跑法（项目根下）：
  ai-radio/.venv/Scripts/python.exe ai-radio/scripts/probe_listening_facts_multiyear.py
"""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from services import listening_facts  # noqa: E402


class FakeEntry:
    """复现 pick_for_entry 用到的 PlaylistEntry 接口。"""

    def __init__(self, title, artists, tags=None):
        self.title = title
        self.artists = artists
        self.tags = tags or []

    @property
    def artist(self):
        return self.artists[0] if self.artists else ""


def main() -> None:
    listening_facts.reset_cache()

    print("=" * 70)
    print("【多年加载自检】_load_multiyear() 各年 digest 概况")
    print("=" * 70)
    digests = listening_facts._load_multiyear()
    print(f"已加载年份：{sorted(digests)}")
    for year, dg in sorted(digests.items()):
        print(
            f"  {year}: 歌手={dg.top_artist_name} / 关键词={dg.yearly_keyword} / "
            f"top_songs={len(dg.top_songs)} / moments={len(dg.moments)} / "
            f"金句={len(dg.quotes)} / 时长={dg.total_hours}"
        )

    print("\n" + "=" * 70)
    print("【宏观画像】get_macro_background()")
    print("=" * 70)
    print(listening_facts.get_macro_background())

    print("\n" + "=" * 70)
    print("【跨年命中钩子】pick_for_entry()")
    print("=" * 70)
    cases = [
        ("王牌冤家", ["李荣浩"], []),                 # 2018 special_moment 国庆 44 遍
        ("王牌冤家 (Live)", ["李荣浩"], []),          # 2018 top_songs rank1 168 次
        ("Moon River", ["Audrey Hepburn"], []),       # 2020 top_songs rank1 147 次
        ("Chinese Tale", ["PDP"], []),                # 2021 special_moment 1/2 循环 29
        ("每当我看到花瓣飘落花蕊慢慢...", ["南辞"], []),  # 2022 special_moment 7/15 47 遍
        ("表态 (Live)", [], []),                      # 2019 top_songs rank1 186（无 artist）
        ("后来", ["刘若英"], ["yearly:2018", "yearly:2021"]),  # 仅 tags 钩子
        ("一首根本不存在的歌xyz", ["无名"], []),       # 兜底：应无钩子
    ]
    for title, artists, tags in cases:
        e = FakeEntry(title, artists, tags)
        out = listening_facts.pick_for_entry(e)
        print(f"\n--- 《{title}》/ {artists or '(无歌手)'} / tags={tags} ---")
        print(out if out else "(无钩子)")


if __name__ == "__main__":
    main()
