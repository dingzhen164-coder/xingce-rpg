"""🖼 修炼战报（rpg/poster.py）：统计数字、存图、下载口令"""
import base64
import tempfile
import unittest
from pathlib import Path

from rpg import api, cards, notes, paths, poster

PNG = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\nfake").decode()


class PosterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self.tmp.name)
        (self.vault / "copilot/skills").mkdir(parents=True)
        self._settings = paths.SETTINGS_FILE, paths.SETTINGS_DIR
        paths.SETTINGS_DIR = self.vault / ".home"
        paths.SETTINGS_FILE = paths.SETTINGS_DIR / "settings.json"
        paths.save_settings({"vault": str(self.vault)})
        cards._CACHE["key"] = None

    def tearDown(self):
        paths.SETTINGS_FILE, paths.SETTINGS_DIR = self._settings
        self.tmp.cleanup()

    def test_stats_counts_today(self):
        api.cards_add({"deck": "言语", "type": "问答", "front": "刊", "back": "删改"})
        r = api.cards_next({"deck": "言语"})
        api.cards_answer({"deck": "言语", "key": r["card"]["key"], "rating": 3, "secs": 5})
        api.lecture_add({"minutes": 30, "note": "资料分析网课"})
        d = api.poster_stats({"span": "day"})
        self.assertEqual(d["cards"]["total"], 1)
        self.assertEqual(d["cards"]["rate"], 1.0)
        self.assertEqual(len(d["days"]), 1)
        self.assertEqual(d["split"]["lecture"], 30)
        self.assertGreaterEqual(d["minutes"], 30)
        self.assertEqual(d["top"][0]["board"], "资料分析")
        self.assertIn("realm", d)
        self.assertIn("call", d["persona"])
        w = api.poster_stats({"span": "week"})
        self.assertEqual(len(w["per_day"]), 7)
        self.assertEqual(w["cards"]["total"], 1)
        with self.assertRaises(api.ApiError):
            api.poster_stats({"span": "year"})

    def test_save_and_download_allowlist(self):
        r = api.poster_save({"data": PNG, "span": "week"})
        self.assertTrue(r["path"].startswith("训练/战报/") and r["path"].endswith("-近七日.png"))
        self.assertTrue((self.vault / r["path"]).is_file())
        self.assertIn("&t=", r["url"])
        p = paths.Paths(self.vault)
        self.assertIsNotNone(notes.export_file(p, r["path"]))
        (self.vault / "训练/战报/别的.txt").write_text("x", encoding="utf-8")
        self.assertIsNone(notes.export_file(p, "训练/战报/别的.txt"))
        with self.assertRaises(api.ApiError):
            api.poster_save({"data": "data:text/plain;base64,eA=="})


if __name__ == "__main__":
    unittest.main()
