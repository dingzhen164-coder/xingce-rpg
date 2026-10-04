"""外观与音乐：语录读取、只接受合法选择、音乐文件只能从 训练/外观/音乐/ 读。"""
import datetime as dt
import tempfile
import unittest
from pathlib import Path

from rpg import api, appearance, paths


class AppearanceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        v = Path(self.tmp.name)
        (v / "copilot/skills").mkdir(parents=True)
        self.p = paths.Paths(v)
        self.p.ensure_train_dir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_defaults_quotes_and_validation(self):
        self.assertTrue((self.p.train / "外观/背景").is_dir() and (self.p.train / "外观/音乐").is_dir())
        qs = appearance.quotes(self.p)
        self.assertEqual(qs[0], "山高万仞，只登一步")                     # 默认语录复制进库
        v = appearance.view(self.p, {}, dt.date(2026, 10, 1))
        self.assertIn(v["daily"], qs)
        self.assertEqual(v["current"]["track"], "")                      # 程序不自带音乐
        (self.p.train / "外观/背景/山.jpg").write_bytes(b"x")
        (self.p.train / "外观/音乐/琴.mp3").write_bytes(b"x")
        st = {}
        appearance.update(self.p, st, {"bg": "file:训练/外观/背景/山.jpg", "dim": 5, "quote": "fixed",
                                       "fixed": "道阻且长，行则将至", "track": "训练/外观/音乐/琴.mp3", "volume": -1})
        a = st["appearance"]
        self.assertEqual((a["bg"], a["dim"], a["quote"], a["track"], a["volume"]),
                         ("file:训练/外观/背景/山.jpg", 0.9, "fixed", "训练/外观/音乐/琴.mp3", 0.0))
        appearance.update(self.p, st, {"bg": "file:训练/规则.md", "track": "../../etc/passwd", "quote": "bad"})
        self.assertEqual((st["appearance"]["bg"], st["appearance"]["track"], st["appearance"]["quote"]),
                         ("file:训练/外观/背景/山.jpg", "训练/外观/音乐/琴.mp3", "fixed"))  # 非法值不改

    def test_no_builtin_backgrounds_shuffle_and_quote_size(self):
        self.assertEqual(appearance.view(self.p, {})["current"]["bg"], "none")          # 没有自己的图：不用背景
        st = {"appearance": {"bg": "builtin:水墨远山"}}                                  # 以前选的自带背景
        (self.p.train / "外观/背景/云.jpg").write_bytes(b"x")
        self.assertEqual(appearance.view(self.p, st)["current"]["bg"], "file:训练/外观/背景/云.jpg")
        appearance.update(self.p, st, {"bg": "builtin:云海仙山"})                       # 自带背景不再收
        self.assertNotEqual(st["appearance"]["bg"], "builtin:云海仙山")
        appearance.update(self.p, st, {"shuffle": True, "quote_size": 9})
        self.assertEqual((st["appearance"]["shuffle"], st["appearance"]["quote_size"]), (True, 2.0))
        appearance.update(self.p, st, {"quote_size": 0.1})
        self.assertEqual(st["appearance"]["quote_size"], 0.5)

    def test_music_file_only_from_music_folder(self):
        (self.p.train / "外观/音乐/琴.mp3").write_bytes(b"x")
        (self.p.train / "秘密.mp3").write_bytes(b"x")
        self.assertIsNotNone(api._music_file(self.p, "训练/外观/音乐/琴.mp3"))
        self.assertIsNone(api._music_file(self.p, "训练/秘密.mp3"))
        self.assertIsNone(api._music_file(self.p, "训练/外观/音乐/../../秘密.mp3"))


if __name__ == "__main__":
    unittest.main()
