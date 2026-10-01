"""听道（其他平台看网课）：计入每日功行（目标、打卡、周常），只给少量修为，可补记、可删除；旧规则 120 分钟自动迁移为 300。"""
import datetime as dt
import tempfile
import unittest
from pathlib import Path

from rpg import config, engine, paths, store


class LectureTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        v = Path(self.tmp.name)
        (v / "copilot/skills").mkdir(parents=True)
        self.p = paths.Paths(v)
        self.p.ensure_train_dir()
        self.day = dt.date(2026, 10, 2)
        self.g = engine.Game(self.p, config.Rules(), config.Persona(), config.Lines(), store.new_state(self.day), self.day)

    def tearDown(self):
        self.tmp.cleanup()
        paths.NOTICES.clear()

    def test_lecture_counts_toward_daily_goal(self):
        g = self.g
        g.add_seconds(60 * 60)                         # 修炼 60 分钟
        xp = g.state["xp"]
        ev = g.add_lecture(240, "粉笔 判断推理")         # 听道 240 分钟 → 合计 300 达标
        self.assertEqual((g.study_minutes(g.t), g.lecture_minutes(g.t), g.minutes(g.t)), (60, 240, 300))
        self.assertEqual(g.state["xp"] - xp, 120)       # 0.5 修为 / 分钟，不吃加成
        self.assertTrue(any(e.get("scene") == "今日达标" for e in ev))
        m = g.dashboard()["minutes"]
        self.assertEqual((m["today"], m["goal"], m["study"], m["lecture"]), (300, 300, 60, 240))
        self.assertTrue(g.qualifies(self.day))
        g.add_lecture(30, day="2026-09-30")             # 补记前几天
        self.assertEqual(g.lecture_minutes("2026-09-30"), 30)
        with self.assertRaises(ValueError):
            g.add_lecture(30, day="2026-09-01")          # 太久以前不能补
        with self.assertRaises(ValueError):
            g.add_lecture(6000)                          # 手滑多打 0
        lid = g.state["lectures"][0]["id"]
        g.delete_lecture(lid)
        self.assertEqual((g.lecture_minutes(g.t), g.state["xp"]), (0, xp + 15))

    def test_old_default_rule_migrated_but_custom_kept(self):
        f = self.p.rules
        f.write_text(f.read_text(encoding="utf-8").replace("- 每日目标分钟: 300", "- 每日目标分钟: 120")
                     .replace("- 周常.修炼分钟: 1500", "- 周常.修炼分钟: 600"), encoding="utf-8")
        self.p.ensure_train_dir()
        r = config.Rules(f.read_text(encoding="utf-8"))
        self.assertEqual((r.num("每日目标分钟"), r.num("周常.修炼分钟")), (300, 1500))
        self.assertTrue(paths.NOTICES)
        f.write_text(f.read_text(encoding="utf-8").replace("- 每日目标分钟: 300", "- 每日目标分钟: 240"), encoding="utf-8")
        self.p.ensure_train_dir()
        self.assertEqual(config.Rules(f.read_text(encoding="utf-8")).num("每日目标分钟"), 240)   # 用户自己改的值不动


if __name__ == "__main__":
    unittest.main()
