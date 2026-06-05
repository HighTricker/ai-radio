"""playlist_importer 解析器单测（标准库 unittest，零依赖）。

跑法（backend 目录下）：
  ../.venv/Scripts/python.exe -m unittest discover -s tests
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # backend/

from services.playlist_importer import _parse_entry, parse_playlist_text, _is_noise_line  # noqa: E402


class TestParseEntry(unittest.TestCase):
    def test_standard_dash(self):
        e = _parse_entry("后来 - 刘若英")
        self.assertEqual((e.title, e.artist), ("后来", "刘若英"))

    def test_fullwidth_dash(self):
        e = _parse_entry("富士山下 — 陈奕迅")
        self.assertEqual((e.title, e.artist), ("富士山下", "陈奕迅"))

    def test_rank_prefix_arabic(self):
        e = _parse_entry("1. 晴天 - 周杰伦")
        self.assertEqual((e.title, e.artist), ("晴天", "周杰伦"))

    def test_rank_prefix_circle(self):
        e = _parse_entry("① 七里香 - 周杰伦")
        self.assertEqual(e.title, "七里香")

    def test_rank_prefix_chinese(self):
        e = _parse_entry("一、山丘 - 李宗盛")
        self.assertEqual(e.title, "山丘")

    def test_rank_prefix_top(self):
        e = _parse_entry("TOP3 成都 - 赵雷")
        self.assertEqual((e.title, e.artist), ("成都", "赵雷"))

    def test_bracket_tag(self):
        e = _parse_entry("[VIP] 夜曲 - 周杰伦")
        self.assertEqual(e.title, "夜曲")

    def test_paren_artist(self):
        e = _parse_entry("漠河舞厅（柳爽）")
        self.assertEqual((e.title, e.artist), ("漠河舞厅", "柳爽"))

    def test_by_format(self):
        e = _parse_entry("Monsters by Katie Sky")
        self.assertEqual((e.title, e.artist), ("Monsters", "Katie Sky"))

    def test_by_with_album_suffix(self):
        e = _parse_entry("Skin by Rag'n'Bone Man (Recovery)")
        self.assertEqual((e.title, e.artist), ("Skin", "Rag'n'Bone Man"))

    def test_artist_with_album_suffix(self):
        # 歌手段再含 " - 专辑"，只取第一段
        e = _parse_entry("夜空中最亮的星 - 逃跑计划 - 世界")
        self.assertEqual((e.title, e.artist), ("夜空中最亮的星", "逃跑计划"))

    def test_title_only_no_space(self):
        e = _parse_entry("纯歌名无歌手")
        self.assertEqual((e.title, e.artist), ("纯歌名无歌手", ""))

    def test_noise_returns_none(self):
        self.assertIsNone(_parse_entry("# 我的年度歌单"))
        self.assertIsNone(_parse_entry("https://y.qq.com/x"))
        self.assertIsNone(_parse_entry("1234 万次播放"))
        self.assertIsNone(_parse_entry(""))


class TestIsNoiseLine(unittest.TestCase):
    def test_noise(self):
        for s in ("# 标题", "> 引用", "https://x.com", "1.2亿", "", "a"):
            self.assertTrue(_is_noise_line(s), f"应判为噪音：{s!r}")

    def test_not_noise(self):
        self.assertFalse(_is_noise_line("后来 - 刘若英"))


class TestParsePlaylistText(unittest.TestCase):
    def test_multiline_drops_noise(self):
        text = (
            "# 我的歌单\n"
            "后来 - 刘若英\n"
            "\n"
            "1. 晴天 - 周杰伦\n"
            "https://x.com\n"
            "富士山下 — 陈奕迅\n"
        )
        entries = parse_playlist_text(text)
        self.assertEqual([e.title for e in entries], ["后来", "晴天", "富士山下"])


if __name__ == "__main__":
    unittest.main()
