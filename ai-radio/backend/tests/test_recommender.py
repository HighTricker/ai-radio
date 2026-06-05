"""recommender 的 LLM 输出解析 / 候选匹配单测（标准库 unittest）。

LLM 返回格式天然不稳定，这两个兜底分支必须有回归网。
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # backend/

from services.recommender import _parse_response, _match_entry, RecommendError  # noqa: E402
from services.playlist import PlaylistEntry  # noqa: E402


class TestParseResponse(unittest.TestCase):
    def test_pure_json(self):
        d = _parse_response('{"song": "后来", "reason": "夜深了"}')
        self.assertEqual(d["song"], "后来")

    def test_json_code_block(self):
        d = _parse_response('```json\n{"song": "晴天"}\n```')
        self.assertEqual(d["song"], "晴天")

    def test_json_with_surrounding_text(self):
        d = _parse_response('好的，我推荐：{"song": "山丘", "reason": "x"} 希望你喜欢')
        self.assertEqual(d["song"], "山丘")

    def test_no_json_raises(self):
        with self.assertRaises(RecommendError):
            _parse_response("这里完全没有 JSON 对象")

    def test_invalid_json_raises(self):
        with self.assertRaises(RecommendError):
            _parse_response("{这看起来像但不是合法 JSON}")


class TestMatchEntry(unittest.TestCase):
    def setUp(self):
        self.avail = [
            PlaylistEntry("后来", "刘若英"),
            PlaylistEntry("Moon River", "Audrey Hepburn"),
        ]

    def test_exact_display(self):
        e = _match_entry("后来 - 刘若英", self.avail)
        self.assertEqual(e.title, "后来")

    def test_case_and_space_insensitive(self):
        # 大小写 + 去空格归一化匹配
        e = _match_entry("moonriver-audreyhepburn", self.avail)
        self.assertEqual(e.title, "Moon River")

    def test_no_match_returns_none(self):
        self.assertIsNone(_match_entry("不存在 - 无名", self.avail))


if __name__ == "__main__":
    unittest.main()
