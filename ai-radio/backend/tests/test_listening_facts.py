"""listening_facts 多年画像归一化 / 跨年匹配单测（标准库 unittest）。

各年报告 schema 高度异构，归一化与防张冠李戴匹配是核心正确性。
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # backend/

from services import listening_facts  # noqa: E402
from services.listening_facts import _normalize_year, _norm_songs, YearDigest  # noqa: E402


class TestNormSongs(unittest.TestCase):
    def test_title_song_alias_and_plays(self):
        out = _norm_songs([{"title": "A", "plays": 5}, {"song": "B", "play_count": 3}])
        self.assertEqual((out[0]["title"], out[0]["plays"]), ("A", 5))
        self.assertEqual((out[1]["title"], out[1]["plays"]), ("B", 3))

    def test_artist_str_vs_list(self):
        out = _norm_songs([
            {"title": "A", "artist": "歌手1"},
            {"title": "B", "artists": ["歌手2", "feat"]},
        ])
        self.assertEqual(out[0]["artist"], "歌手1")
        self.assertEqual(out[1]["artist"], "歌手2")  # 列表取首位

    def test_drop_entry_without_title(self):
        out = _norm_songs([{"plays": 5}, {"title": "ok"}])
        self.assertEqual([s["title"] for s in out], ["ok"])


class TestNormalizeYear(unittest.TestCase):
    def test_top_artist_singular_2018_style(self):
        facts = {
            "meta": {"year": 2018, "total_songs": 100, "total_hours": 50},
            "theme": {"yearly_keyword": "我们"},
            "top_artist": {"name": "陈粒", "play_count": 612},
        }
        dg = _normalize_year(2018, facts, [])
        self.assertEqual(dg.top_artist_name, "陈粒")
        self.assertEqual(dg.yearly_keyword, "我们")
        self.assertEqual(dg.total_songs, 100)

    def test_top_artists_plural_and_minutes_2019_style(self):
        facts = {
            "meta": {"year": 2019, "total_plays": 200, "total_minutes": 6000},
            "top_artists": [{"name": "李荣浩", "listening_minutes": 1971}],
        }
        dg = _normalize_year(2019, facts, [])
        self.assertEqual(dg.top_artist_name, "李荣浩")
        self.assertEqual(dg.total_songs, 200)        # total_plays 别名
        self.assertEqual(dg.total_hours, 100.0)      # total_minutes/60

    def test_top_songs_fallback_to_artist_2021_style(self):
        facts = {
            "meta": {"year": 2021},
            "top_artist": {"name": "X", "top_songs": [{"song": "妙龄童", "plays": 117}]},
        }
        dg = _normalize_year(2021, facts, [])
        self.assertEqual([s["title"] for s in dg.top_songs], ["妙龄童"])


class TestMatchSongHistory(unittest.TestCase):
    def setUp(self):
        self._orig = listening_facts._load_multiyear
        d2018 = YearDigest(
            year=2018,
            top_songs=[{"title": "王牌冤家 (Live)", "artist": "李荣浩", "plays": 168}],
            moments=[{
                "song": "王牌冤家", "type": "单日单曲循环冠军",
                "date": "2018-10-01", "plays": 44, "note": "国庆当天",
            }],
        )
        listening_facts._load_multiyear = lambda: {2018: d2018}

    def tearDown(self):
        listening_facts._load_multiyear = self._orig

    def test_top_songs_hit(self):
        hooks = listening_facts._match_song_history("王牌冤家 (Live)", "李荣浩")
        self.assertTrue(any("168" in h for h in hooks), hooks)

    def test_special_moment_hit(self):
        hooks = listening_facts._match_song_history("王牌冤家", "李荣浩")
        self.assertTrue(any("44" in h for h in hooks), hooks)

    def test_artist_mismatch_no_false_match(self):
        # 同名不同歌手：artist 两边都有值且不一致 → 不应误配
        hooks = listening_facts._match_song_history("王牌冤家 (Live)", "别的歌手")
        self.assertEqual(hooks, [])

    def test_unknown_song_no_hooks(self):
        self.assertEqual(listening_facts._match_song_history("根本不存在的歌xyz", "x"), [])


if __name__ == "__main__":
    unittest.main()
