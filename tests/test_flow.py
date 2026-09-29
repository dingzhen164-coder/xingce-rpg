"""
端到端测试：在临时文件夹里造一个迷你行测库，走一遍 面板 → 骨架定稿 → 默写 → 费曼 → 应用 → 掌握 → 复查 → 错题 → 突破。
AI 用假函数代替（不联网）。运行：

    python -m unittest discover -s tests -v

改了 engine / trainer 的规则后先跑这个，确认主流程没坏。
"""
import datetime as dt
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rpg import ai, api, engine, paths, trainer  # noqa: E402

SKELETON = """---
板块: 论证逻辑
状态: 草稿
来源skill: xue-rui-argument-logic
---
# 论证逻辑 · 骨架

## 1. 削弱题
- 【术语】否定论点：直接说论点不成立
- 【术语】拆桥：论据和论点说的不是一回事
- 【思路】先找论点和论据

## 2. 加强题
- 【术语】搭桥
- 【思路】补充论据和论点之间的联系
"""

BOARD_MD = """---
季数: 第36季
板块: 论证逻辑
---

# 第36季 · 论证逻辑

### 1. ✅

题干一

> [!check]- 答案
> 正确答案：**A**　我的答案：**A**　正确

> [!note] 复盘
>

---

### 2. ❌

![[S36-Q2.png]]
以下哪项最能削弱上述论证？

- **A.** 甲
- **B.** 乙

> [!check]- 答案
> 正确答案：**B**　我的答案：**A**　错误

> [!note] 复盘
> 【答案】B
> 【思路】否定论点。
> - 错因：

---
"""


def fake_chat(messages, json_mode=False, **kw):
    """假 AI：根据提示词里的关键字返回固定结果（全部判“通过”）"""
    text = messages[-1]["content"] if messages else ""
    sys_text = messages[0]["content"] if messages else ""
    if "知识骨架" in text:
        return SKELETON.split("# 论证逻辑 · 骨架", 1)[1]
    if "要点是否说到了" in text:
        n = text.count("\n") and len([l for l in text.split("需要判断的思路要点（按顺序）：")[1].split("\n\n")[0].splitlines() if l.strip()])
        return json.dumps({"答到": [True] * n, "错误说法": [], "点评": "不错"})
    if "费曼学习法" in sys_text:
        return json.dumps({"reply": "讲得清楚", "done": True,
                           "维度": {"是什么": True, "识别信号": True, "怎么用": True, "易错": True}, "通过": True})
    if "应用小题" in text and "判断学员" not in text:
        return json.dumps({"题目": "某论证……，以下哪项最能削弱？", "参考答案": "A", "参考思路": "否定论点"})
    if "判断学员对应用小题的作答" in text:
        return json.dumps({"通过": True, "点评": "对"})
    if "做错过的" in text:
        return json.dumps({"答案正确": True, "思路正确": True, "对应大项": "削弱题", "点评": "好", "正确思路": "否定论点"})
    return "好的"


class FlowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        v = self.tmp / "行测"
        (v / "copilot/skills/xue-rui-argument-logic").mkdir(parents=True)
        (v / "copilot/skills/xue-rui-argument-logic/SKILL.md").write_text("---\nname: x\n---\n# 论证\n", encoding="utf-8")
        sd = v / "FB模考试卷复盘/板块复盘/第36季"
        (sd / "attachments").mkdir(parents=True)
        (sd / "10-论证逻辑.md").write_text(BOARD_MD, encoding="utf-8")
        (sd / "attachments/S36-Q2.png").write_bytes(b"\x89PNG")
        self.vault = v
        # 隔离本机设置，不碰真实的 ~/.xingce-rpg
        self._settings = paths.SETTINGS_FILE, paths.SETTINGS_DIR
        paths.SETTINGS_DIR = self.tmp / "home"
        paths.SETTINGS_FILE = paths.SETTINGS_DIR / "settings.json"
        paths.save_settings({"vault": str(v), "api_key": "test"})
        self._chat = ai.chat
        ai.chat = fake_chat
        trainer.SESSIONS.clear()

    def tearDown(self):
        paths.SETTINGS_FILE, paths.SETTINGS_DIR = self._settings
        ai.chat = self._chat
        shutil.rmtree(self.tmp, ignore_errors=True)

    def state(self):
        return json.loads((self.vault / "训练/存档/存档.json").read_text(encoding="utf-8"))

    def run_task(self, task, answer="否定论点 拆桥 先找论点和论据 搭桥"):
        r = api.session_start({"task": task})
        while not r["finished"]:
            if r["input"]["mode"] == "text":
                r = api.session_reply({"session": r["session"], "text": answer})
            elif r["input"]["mode"] == "buttons":
                r = api.session_action({"session": r["session"], "action": r["input"]["buttons"][0]["id"]})
            else:
                break
        return r

    def test_full_flow(self):
        d = api.dashboard({})
        self.assertEqual(d["level"]["level"], 1)
        titles = [t["title"] for t in d["plan"]["tasks"]]
        self.assertIn("生成「论证逻辑」骨架", titles)
        self.assertTrue(any("错题" in t for t in titles))

        # 生成骨架 → 定稿
        r = api.session_start({"task": {"type": "skeleton", "board": "论证逻辑", "target": "论证逻辑", "title": "骨架"}})
        r = api.session_action({"session": r["session"], "action": "gen"})
        self.assertIn("草稿", (self.vault / "训练/骨架/论证逻辑.md").read_text(encoding="utf-8"))
        r = api.session_action({"session": r["session"], "action": "final"})
        self.assertTrue(r["finished"])
        sk = api.skeletons({})
        board = [b for b in sk["boards"] if b["board"] == "论证逻辑"][0]
        self.assertTrue(board["final"])
        self.assertEqual([i["name"] for i in board["items"]], ["削弱题", "加强题"])

        iid = "论证逻辑::削弱题"
        t = {"board": "论证逻辑", "target": iid, "title": "x"}
        # 默写：术语缺一个 → 不过
        r = self.run_task(dict(t, type="recite"), answer="否定论点，先找论点和论据")
        self.assertTrue(any("未通过" in m["text"] for m in r["messages"]))
        # 连续两次通过 → L1
        self.run_task(dict(t, type="recite"))
        self.run_task(dict(t, type="recite"))
        self.assertEqual(self.state()["items"][iid]["level"], 1)
        # 费曼 → L2
        self.run_task(dict(t, type="feynman"))
        self.assertEqual(self.state()["items"][iid]["level"], 2)
        # 应用两次 → 掌握
        self.run_task(dict(t, type="apply"))
        self.run_task(dict(t, type="apply"))
        st = self.state()["items"][iid]
        self.assertEqual(st["level"], 3)
        self.assertIsNotNone(st["next"])

        # 错题：判对，标记对应大项
        r = self.run_task({"type": "wrong", "board": "论证逻辑", "target": "36|论证逻辑|2", "title": "错题"})
        self.assertTrue(any(b["t"] == "img" for m in api.session_start(
            {"task": {"type": "wrong", "board": "论证逻辑", "target": "36|论证逻辑|2", "title": "错题"}})["messages"]
            for b in m.get("blocks", [])))
        self.assertEqual(self.state()["wrong"]["36|论证逻辑|2"]["status"], "done")
        self.assertGreater(self.state()["xp"], 200)

        # 另一个大项也掌握 → 第 1 批（其余板块没有 skill，被跳过）通关，XP 大奖；从“骨架”页发起的练习也会勾掉今日任务
        api.plan_regenerate({})
        t2 = {"board": "论证逻辑", "target": "论证逻辑::加强题", "title": "x"}
        for typ in ("recite", "recite", "feynman", "apply", "apply"):
            self.run_task(dict(t2, type=typ))
        s = self.state()
        self.assertIn(1, s["cleared"]["1"])
        self.assertTrue(any(e["type"] == "batch" for e in s["events"]))
        self.assertTrue(any(t["done"] for t in s["plan"]["tasks"] if t["target"] == "论证逻辑::加强题"))

    def test_no_ai_self_rating(self):
        paths.save_settings({"vault": str(self.vault)})  # 没有 key
        self.assertFalse(ai.available())
        (self.vault / "训练/骨架").mkdir(parents=True, exist_ok=True)
        (self.vault / "训练/骨架/论证逻辑.md").write_text(SKELETON.replace("状态: 草稿", "状态: 已定稿"), encoding="utf-8")
        r = api.session_start({"task": {"type": "recite", "board": "论证逻辑", "target": "论证逻辑::加强题", "title": "x"}})
        r = api.session_reply({"session": r["session"], "text": "搭桥 补充联系"})
        self.assertEqual(r["input"]["mode"], "buttons")
        r = api.session_action({"session": r["session"], "action": "self_ok"})
        self.assertTrue(r["finished"])
        self.assertEqual(self.state()["items"]["论证逻辑::加强题"]["l1"], 1)
        with self.assertRaises(trainer.TrainError):
            api.session_start({"task": {"type": "feynman", "board": "论证逻辑", "target": "论证逻辑::加强题", "title": "x"}})

    def test_tired_does_not_consume_task(self):
        (self.vault / "训练/骨架").mkdir(parents=True, exist_ok=True)
        (self.vault / "训练/骨架/论证逻辑.md").write_text(SKELETON.replace("状态: 草稿", "状态: 已定稿"), encoding="utf-8")
        r = api.session_start({"task": {"type": "recite", "board": "论证逻辑", "target": "论证逻辑::加强题", "title": "x"}})
        r2 = api.session_reply({"session": r["session"], "text": "好累啊不想学了"})
        self.assertFalse(r2["finished"])
        self.assertEqual(r2["input"]["mode"], "text")
        self.assertEqual(self.state()["xp"], 0)


class EngineTest(unittest.TestCase):
    def make(self, today, state=None):
        from rpg import config, store
        p = paths.Paths(None)
        return engine.Game(p, config.Rules(), config.Persona(), config.Lines(), state or store.new_state(today), today)

    def test_level_curve_reaches_max_on_target(self):
        g = self.make(dt.date(2026, 9, 29))
        costs, cum = g.level_table()
        self.assertEqual(len(cum), 31)
        self.assertAlmostEqual(cum[-1], 300 * (dt.date(2027, 12, 1) - dt.date(2026, 9, 29)).days, delta=50)
        self.assertLess(costs[0], costs[-1])

    def test_gate_blocks_level(self):
        g = self.make(dt.date(2026, 9, 29))
        _, cum = g.level_table()
        g.state["xp"] = cum[12]  # 够 Lv13
        info = g.level_info()
        self.assertEqual(info["level"], 10)
        self.assertEqual(info["gate"], 10)
        g.state["gates"].append(10)
        self.assertEqual(g.level_info()["level"], 13)

    def test_streak_halves_on_miss(self):
        t = dt.date(2026, 10, 10)
        g = self.make(t)
        g.state["created"] = "2026-10-01"
        for d in range(1, 9):  # 10/1–10/8 学了，10/9 没学
            g.state["seconds"][f"2026-10-0{d}"] = 3600
        run, bonus = g.streak()
        self.assertEqual(run, 0)
        self.assertAlmostEqual(bonus, 0.08)  # 8 天 → 断一天减半为 4 → 4×2%

    def test_ideal_line(self):
        g = self.make(dt.date(2026, 10, 9))
        g.state["created"] = "2026-09-29"
        self.assertEqual(g.ideal()["diff_days"], 10.0)
        g.state["leave"] = ["2026-10-01"]
        self.assertEqual(g.ideal()["diff_days"], 9.0)


if __name__ == "__main__":
    unittest.main()
