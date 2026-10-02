"""
端到端测试：在临时文件夹里造一个迷你行测库，走一遍 面板 → 功法定稿 → 背诵 → 论道 → 试剑 → 圆满 → 斩心魔 → 灵根觉醒
→ 宗门大比 → 渡劫 → 炼丹，外加境界、瓶颈、周常、护心丹、走火入魔、风格切换等规则的单元测试。
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

from rpg import ai, api, engine, paths, skeleton, trainer  # noqa: E402

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
    if "请以你的身份对学员说一段话" in text:
        return "哎呀，学姐的现场台词。"
    if "知识骨架" in text:
        return SKELETON.split("# 论证逻辑 · 骨架", 1)[1]
    if "要点是否说到了" in text:
        n = text.count("\n") and len([l for l in text.split("需要判断的思路要点（按顺序）：")[1].split("\n\n")[0].splitlines() if l.strip()])
        names = [l.split(". ", 1)[1] for l in text.split("需要判断的名称清单（按顺序）：")[1].split("\n\n")[0].splitlines() if ". " in l]
        answer = text.split("学员的默写：\n")[1].split("\n\n")[0]
        return json.dumps({"清单": [name in answer for name in names], "答到": [True] * n, "错误说法": [], "点评": "不错"})
    if "传授" in text and "弟子还没学过" in text:
        return "为师来讲：" + ("有例题" if "例题1：" in text else "无例题")
    if "陪学员复盘" in sys_text:
        return "师傅：先看问法。" + text[:12]
    if "费曼学习法" in sys_text:
        return json.dumps({"reply": "讲得清楚", "done": True,
                           "维度": {"是什么": True, "识别信号": True, "怎么用": True, "易错": True}, "通过": True})
    if "自行举例" in text:
        return json.dumps({"通过": True, "点评": "机制清楚", "修改建议": ""})
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
        r = api.session_start({"task": dict(task, fresh=True)})
        while not r["finished"]:
            if any(b["id"] == "discuss_end" for b in r["input"].get("buttons", [])):   # 题后复盘：结束
                r = api.session_action({"session": r["session"], "action": "discuss_end"})
            elif r["input"]["mode"] == "text":
                r = api.session_reply({"session": r["session"], "text": answer})
            elif r["input"]["mode"] == "buttons":
                r = api.session_action({"session": r["session"], "action": r["input"]["buttons"][0]["id"]})
            else:
                break
        return r

    def test_daily_wrong_is_one_shared_task(self):
        d = api.dashboard({})
        wrongs = [t for t in d["plan"]["tasks"] if t["type"] == "wrong"]
        self.assertEqual([t["id"] for t in wrongs], ["wrong:daily"])     # 今日功课只有一项斩心魔
        t = wrongs[0]
        self.assertIn("0/%d" % t["quota"], t["title"])
        # 心魔录和今日功课用同一个 task_id，进度互通
        r = api.session_start({"task_id": "wrong:daily"})
        r = api.session_reply({"session": r["session"], "text": "削弱 否定论点 选A"})
        self.assertIn("wrong_next", [b["id"] for b in r["input"]["buttons"]])
        t = [x for x in self.state()["plan"]["tasks"] if x["id"] == "wrong:daily"][0]
        self.assertEqual(len(t["hits"]), 1)
        self.assertEqual(t["done"], t["quota"] == 1)
        # 旧版计划（一只一项）进来自动合成一项
        st = self.state()
        st["plan"]["tasks"] = [x for x in st["plan"]["tasks"] if x["type"] != "wrong"] + [
            {"id": "wrong:36|论证逻辑|2", "type": "wrong", "board": "论证逻辑", "title": "斩心魔 · 第36季论证逻辑第2题",
             "target": "36|论证逻辑|2", "minutes": 5, "done": True, "ok": True, "optional": False},
            {"id": "wrong:36|论证逻辑|3", "type": "wrong", "board": "论证逻辑", "title": "斩心魔 · 第36季论证逻辑第3题",
             "target": "36|论证逻辑|3", "minutes": 5, "done": False, "ok": None, "optional": False}]
        (self.vault / "训练/存档/存档.json").write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
        d = api.dashboard({})
        wrongs = [t for t in d["plan"]["tasks"] if t["type"] == "wrong"]
        self.assertEqual(len(wrongs), 1)
        self.assertEqual((wrongs[0]["quota"], wrongs[0]["hits"], wrongs[0]["minutes"]), (2, ["36|论证逻辑|2"], 10))

    def test_full_flow(self):
        d = api.dashboard({})
        self.assertEqual(d["realm"]["name"], "凡人 · 未入道")
        titles = [t["title"] for t in d["plan"]["tasks"]]
        self.assertIn("编撰「论证逻辑」功法（生成骨架）", titles)
        self.assertTrue(any("斩心魔" in t for t in titles))

        # 生成功法 → 定稿
        r = api.session_start({"task": {"type": "skeleton", "board": "论证逻辑", "target": "论证逻辑", "title": "功法"}})
        r = api.session_action({"session": r["session"], "action": "gen"})
        self.assertIn("草稿", (self.vault / "训练/骨架/论证逻辑.md").read_text(encoding="utf-8"))
        r = api.session_action({"session": r["session"], "action": "final"})
        self.assertTrue(r["finished"])
        board = [b for b in api.skeletons({})["boards"] if b["board"] == "论证逻辑"][0]
        self.assertTrue(board["final"])
        self.assertEqual([i["name"] for i in board["items"]], ["削弱题", "加强题"])
        self.assertEqual(board["items"][0]["levelName"], "未入门")

        iid = "论证逻辑::削弱题"
        t = {"board": "论证逻辑", "target": iid, "title": "x"}
        r = self.run_task(dict(t, type="recite"), answer="否定论点，先找论点和论据")   # 缺口诀“拆桥”
        self.assertTrue(any("背诵口诀失败" in m["text"] for m in r["messages"]))
        # 传授：师傅先讲，再追问 / 再举一例，结束后不改掌握程度
        r = api.session_start({"task": dict(t, type="teach")})
        self.assertIn("为师来讲", str(r["messages"]))
        self.assertEqual([b["id"] for b in r["input"]["buttons"]], ["ask_more", "discuss_end"])
        r = api.session_action({"session": r["session"], "action": "ask_more"})
        self.assertIn("再举一个例子", str(r["messages"]))
        r = api.session_action({"session": r["session"], "action": "discuss_end"})
        self.assertTrue(r["finished"])
        self.assertEqual(self.state()["items"].get(iid, {}).get("level", 0), 0)
        # 修炼记录：这次传授写进 训练/修炼记录/论证逻辑/<大项>.md；下次再点，往期对话折叠在最上面
        logs = list((self.vault / "训练/修炼记录/论证逻辑").glob("*.md"))
        self.assertEqual(len(logs), 1)
        log = logs[0].read_text(encoding="utf-8")
        self.assertIn("· 传授 <!-- sid:", log)
        self.assertIn("· 背诵口诀 <!-- sid:", log)          # 前面那次背诵口诀也记了
        self.assertIn("为师来讲", log)
        self.assertIn("🧑 我", log)                     # “再举一例”这句也记下了
        # 再点“传授”：接着上次那次传授聊（上次的对话原样摆出来，师傅带着上次的上下文回答），写回同一段
        r = api.session_start({"task": dict(t, type="teach")})
        self.assertIn("接着", r["messages"][0]["text"])
        self.assertIn("为师来讲", str(r["messages"]))
        self.assertEqual([b["id"] for b in r["input"]["buttons"]], ["ask_more", "fresh", "discuss_end"])
        r = api.session_reply({"session": r["session"], "text": "削弱和质疑是一回事吗"})
        self.assertIn("师傅：先看问法", str(r["messages"]))
        api.session_action({"session": r["session"], "action": "discuss_end"})
        log = logs[0].read_text(encoding="utf-8")
        self.assertEqual(log.count("<!-- sid:"), 2)        # 没有新开一段
        self.assertIn("削弱和质疑是一回事吗", log)
        self.assertEqual(log.count("为师来讲"), 1)          # 上次的内容没被重复写
        self.assertNotIn("接着", log)
        # 重新开始：开一次新的传授，旧的折叠在上面
        r = api.session_start({"task": dict(t, type="teach")})
        r = api.session_action({"session": r["session"], "action": "fresh"})
        self.assertTrue(r.get("replace"))
        self.assertEqual(len([m for m in r["messages"] if (m.get("fold") or "").startswith("📜 往期修炼")]), 2)
        api.session_action({"session": r["session"], "action": "discuss_end"})
        self.assertEqual(logs[0].read_text(encoding="utf-8").count("<!-- sid:"), 3)
        self.run_task(dict(t, type="recite"))
        self.run_task(dict(t, type="recite"))
        self.assertEqual(self.state()["items"][iid]["level"], 1)
        self.run_task(dict(t, type="feynman"))
        self.assertEqual(self.state()["items"][iid]["level"], 2)
        self.run_task(dict(t, type="example"))
        self.run_task(dict(t, type="apply"))
        self.run_task(dict(t, type="apply"))
        self.assertEqual(self.state()["items"][iid]["level"], 3)

        r = api.session_start({"task": {"type": "wrong", "board": "论证逻辑", "target": "36|论证逻辑|2", "title": "心魔"}})
        self.assertTrue(any(b["t"] == "img" for m in r["messages"] for b in m.get("blocks", [])))
        self.run_task({"type": "wrong", "board": "论证逻辑", "target": "36|论证逻辑|2", "title": "心魔"})
        self.assertEqual(self.state()["wrong"]["36|论证逻辑|2"]["status"], "done")

        # 自选板块斩心魔（不指定哪题）→ 判完进入复盘，可以追问、请师傅解惑，点结束才收工
        r = api.session_start({"task": {"type": "wrong", "board": "论证逻辑", "target": "", "title": "心魔"}})
        r = api.session_reply({"session": r["session"], "text": "削弱 否定论点 选A"})
        self.assertFalse(r["finished"])
        self.assertEqual([b["id"] for b in r["input"]["buttons"]], ["ask_explain", "wrong_next", "discuss_end"])
        r = api.session_reply({"session": r["session"], "text": "为什么不选B"})
        self.assertIn("师傅：先看问法。为什么不选B", str(r["messages"]))
        r = api.session_action({"session": r["session"], "action": "ask_explain"})
        self.assertIn("请按 skill 的方法", str(r["messages"]))
        self.assertIn("已存入复盘解析", str(r["messages"]))
        r = api.session_action({"session": r["session"], "action": "ask_explain"})     # 再问一次：换掉，不重复
        files = [f for f in (self.vault / "FB模考试卷复盘").rglob("*.md") if "师傅解惑" in f.read_text(encoding="utf-8")]
        self.assertEqual(len(files), 1)
        text = files[0].read_text(encoding="utf-8")
        self.assertEqual(text.count("🧙 师傅解惑"), 1)
        self.assertIn("> 师傅：先看问法。请按 skill 的方法", text)
        r = api.session_action({"session": r["session"], "action": "discuss_end"})
        self.assertTrue(r["finished"])

        # 另一重也圆满 → 秘境打通、论证灵根觉醒；从藏经阁发起的练习也会勾掉今日功课
        api.plan_regenerate({})
        t2 = {"board": "论证逻辑", "target": "论证逻辑::加强题", "title": "x"}
        for typ in ("recite", "recite", "feynman", "example", "apply", "apply"):
            self.run_task(dict(t2, type=typ))
        s = self.state()
        self.assertIn(1, s["cleared"]["1"])
        self.assertTrue(s["roots"]["论证逻辑"]["on"])
        self.assertTrue(any(t["done"] for t in s["plan"]["tasks"] if t["target"] == "论证逻辑::加强题"))

        # 修为推到筑基线 → 瓶颈；两次大比 ≥ 60 → 可以渡劫
        with api.open_game() as g:
            g.state["xp"] = int(g.xp_at(61)) + 10
            info = g.realm_info()
        self.assertTrue(info["bottleneck"])
        self.assertEqual(info["name"], "炼气九层")
        self.assertFalse(api.dashboard({})["trib"]["ready"])
        api.boss({"name": "第37季", "score": 61})
        api.boss({"name": "第38季", "score": 63})
        d = api.dashboard({})
        self.assertTrue(d["trib"]["ready"], d["trib"])
        self.assertEqual(d["trib"]["pills"], 2)   # 每次大比达到 60 分奖励一颗筑基丹
        self.assertTrue(any(t["type"] == "tribulation" for t in d["plan"]["tasks"]) or api.plan_regenerate({}))
        r = self.run_task({"type": "tribulation", "board": "", "target": "60", "title": "渡劫"})
        self.assertIn(60, self.state()["gates"])
        self.assertTrue(any(e.get("kind") == "realm" and e.get("major") for e in r["events"]))
        self.assertTrue(api.dashboard({})["realm"]["name"].startswith("筑基"))

        # 炼丹：一炉论证逻辑，成丹后额外修为
        xp0 = self.state()["xp"]
        r = self.run_task({"type": "alchemy", "board": "论证逻辑", "target": "论证逻辑", "title": "炼丹"})
        self.assertTrue(any("明辨是非丹" in e.get("msg", "") for e in r["events"]))
        self.assertGreater(self.state()["xp"], xp0)
        self.assertEqual(self.state()["pills"][-1]["grade"], "上品")

    def test_tribulation_failure_needs_healing(self):
        (self.vault / "训练/骨架").mkdir(parents=True, exist_ok=True)
        (self.vault / "训练/骨架/论证逻辑.md").write_text(SKELETON.replace("状态: 草稿", "状态: 已定稿"), encoding="utf-8")
        with api.open_game() as g:
            for it in g.final_items("论证逻辑"):
                g.item(it["id"]).update(level=3, stage=0, next="2099-01-01")
            g.state["xp"] = int(g.xp_at(60.5))
            g.state["boss"] = [{"d": g.t, "name": "a", "score": 60, "kind": "大比"}, {"d": g.t, "name": "b", "score": 60, "kind": "大比"}]
            g.housekeeping()
        self.assertTrue(api.dashboard({})["trib"]["ready"])
        ai.chat = fake_chat
        r = self.run_task({"type": "tribulation", "board": "", "target": "60", "title": "渡劫"}, answer="不记得了")
        s = self.state()
        self.assertNotIn(60, s["gates"])
        self.assertTrue(s["trib"]["cooldown"])
        self.assertEqual(len(s["trib"]["heal"]), 1)
        d = api.dashboard({})
        self.assertFalse(d["trib"]["ready"])
        self.assertTrue(any(t["title"].startswith("疗伤") for t in d["plan"]["tasks"]))

    def test_ai_tutor_and_theme_switch(self):
        d = api.dashboard({})
        self.assertTrue(d["greet_pending"])
        self.assertEqual(api.tutor_greet({})["text"], "哎呀，学姐的现场台词。")
        d = api.dashboard({})
        self.assertFalse(d["greet_pending"])
        self.assertEqual(d["persona"]["tutor"], "劭神韵")
        self.assertEqual(d["theme"]["terms"]["skeleton"], "功法")
        with api.open_game() as g:                      # 里程碑台词被换成 AI 现场说的
            ev = api.tutor.enrich(g, g._award(int(g.xp_at(52)), "bonus", note="测试", bonus=False))
        self.assertTrue(any(e.get("kind") == "realm" for e in ev))
        self.assertIn("哎呀，学姐的现场台词。", [e.get("msg") for e in ev])
        api.theme_set({"theme": "玄幻"})
        d = api.dashboard({})
        self.assertEqual(d["persona"]["tutor"], "艾琳学姐")
        self.assertEqual(d["theme"]["terms"]["skeleton"], "咒文书")
        self.assertTrue(d["realm"]["name"].startswith("见习学徒"))
        self.assertTrue(d["greet_pending"])            # 换了导师要重新打招呼

    def test_no_ai_self_rating(self):
        paths.save_settings({"vault": str(self.vault)})  # 没有 key
        self.assertFalse(ai.available())
        (self.vault / "训练/骨架").mkdir(parents=True, exist_ok=True)
        (self.vault / "训练/骨架/论证逻辑.md").write_text(SKELETON.replace("状态: 草稿", "状态: 已定稿"), encoding="utf-8")
        r = api.session_start({"task": {"type": "recite", "board": "论证逻辑", "target": "论证逻辑::加强题", "title": "x", "fresh": True}})
        r = api.session_reply({"session": r["session"], "text": "搭桥 补充联系"})
        self.assertEqual(r["input"]["mode"], "buttons")
        r = api.session_action({"session": r["session"], "action": "self_ok"})
        self.assertTrue(r["finished"])
        self.assertEqual(self.state()["items"]["论证逻辑::加强题"]["l1"], 1)
        with self.assertRaises(trainer.TrainError):
            api.session_start({"task": {"type": "feynman", "board": "论证逻辑", "target": "论证逻辑::加强题", "title": "x", "fresh": True}})

    def test_tired_does_not_consume_task(self):
        (self.vault / "训练/骨架").mkdir(parents=True, exist_ok=True)
        (self.vault / "训练/骨架/论证逻辑.md").write_text(SKELETON.replace("状态: 草稿", "状态: 已定稿"), encoding="utf-8")
        r = api.session_start({"task": {"type": "recite", "board": "论证逻辑", "target": "论证逻辑::加强题", "title": "x", "fresh": True}})
        r2 = api.session_reply({"session": r["session"], "text": "好累啊不想学了"})
        self.assertFalse(r2["finished"])
        self.assertEqual(r2["input"]["mode"], "text")
        self.assertEqual(self.state()["xp"], 0)

    def test_time_counts_only_while_studying(self):
        (self.vault / "训练/骨架").mkdir(parents=True, exist_ok=True)
        (self.vault / "训练/骨架/论证逻辑.md").write_text(SKELETON.replace("状态: 草稿", "状态: 已定稿"), encoding="utf-8")
        self.assertEqual(api.heartbeat({"seconds": 30})["minutes"], 0)                   # 只是开着网页
        chat = api.session_start({"task": {"type": "chat", "board": "", "target": "", "title": "聊天"}})
        r = api.heartbeat({"seconds": 60, "session": chat["session"]})                     # 和导师闲聊
        self.assertFalse(r["studying"])
        self.assertEqual(r["minutes"], 0)
        s = api.session_start({"task": {"type": "recite", "board": "论证逻辑", "target": "论证逻辑::加强题", "title": "x", "fresh": True}})
        self.assertTrue(api.heartbeat({"seconds": 60, "session": s["session"]})["studying"])
        self.assertEqual(api.heartbeat({"seconds": 60, "session": s["session"]})["minutes"], 2)   # 做功课才计时
        api.session_reply({"session": s["session"], "text": "搭桥 补充论据和论点之间的联系"})
        self.assertEqual(api.heartbeat({"seconds": 60, "session": s["session"]})["minutes"], 3)   # 刚做完看解析也算
        self.assertFalse(api.heartbeat({"seconds": 60, "session": "不存在"})["studying"])

    def test_qi_deviation_after_repeated_failures(self):
        (self.vault / "训练/骨架").mkdir(parents=True, exist_ok=True)
        (self.vault / "训练/骨架/论证逻辑.md").write_text(SKELETON.replace("状态: 草稿", "状态: 已定稿"), encoding="utf-8")
        task = {"type": "recite", "board": "论证逻辑", "target": "论证逻辑::加强题", "title": "x"}
        for _ in range(5):
            self.run_task(task, answer="忘了")
        with self.assertRaises(trainer.TrainError):
            api.session_start({"task": dict(task, fresh=True)})
        self.assertGreater(api.dashboard({})["rest"], 0)

    def test_semantic_recall_synonyms_errors_and_malformed_result(self):
        bone = self.vault / "训练/骨架/论证逻辑.md"
        bone.parent.mkdir(parents=True, exist_ok=True)
        bone.write_text(SKELETON.replace("状态: 草稿", "状态: 已定稿"), encoding="utf-8")
        task = {"type": "recite", "board": "论证逻辑", "target": "论证逻辑::削弱题", "title": "x"}
        # 没有字面命中两个术语，但语义对应完整，AI按含义通过。
        ai.chat = lambda m, **kw: json.dumps({"清单": [True, True], "答到": [True, True, True], "错误说法": [], "点评": "含义正确"})
        r = self.run_task(task, "否认主张，以及破坏证据到主张的联系")
        self.assertTrue(any("成功" in m["text"] for m in r["messages"]))
        ai.chat = lambda m, **kw: json.dumps({"清单": [True, True], "答到": [True, True, True], "错误说法": ["把共现当因果"], "点评": "混淆"})
        self.run_task(task)
        self.assertEqual(self.state()["items"][task["target"]]["l1"], 0)
        ai.chat = lambda m, **kw: json.dumps({"清单": ["true"], "答到": [], "错误说法": []})
        r = api.session_start({"task": dict(task, fresh=True)})
        xp = self.state()["xp"]
        with self.assertRaises(trainer.TrainError):
            api.session_reply({"session": r["session"], "text": "讲解"})
        self.assertEqual(self.state()["xp"], xp)

    def test_example_gate_and_legacy_mastery(self):
        with api.open_game() as g:
            iid = "论证逻辑::测试举例"
            st = g.item(iid)
            st["level"] = 2
            g.on_apply(iid, True)
            self.assertEqual(st["l3"], 0)
            g.on_example(iid, False)
            self.assertFalse(st["example_ok"])
            g.on_example(iid, True)
            g.on_apply(iid, True)
            self.assertEqual(st["l3"], 1)
            g.state["items"]["旧圆满::方法"] = {"level": 3}
            self.assertTrue(g.item("旧圆满::方法")["example_ok"])

    def test_full_chapter_body_and_example_not_recall_point(self):
        from rpg import skeleton, vault
        folder = self.vault / "copilot/skills/xue-rui-argument-logic/chapters"
        folder.mkdir()
        (folder / "ch02.md").write_text("## 方法\n正文里的具体边界条件", encoding="utf-8")
        with api.open_game(save=False) as g:
            digest = vault.skill_digest(g.paths, "xue-rui-argument-logic")
        self.assertIn("正文里的具体边界条件", digest)
        it = skeleton.parse("## 方法\n- 【思路】解释机制\n- 【举例】自行编情境", "论证逻辑")["items"][0]
        self.assertEqual(it["thoughts"], ["解释机制"])
        self.assertEqual(it["examples"], ["自行编情境"])

    def test_unverified_draft_cannot_finalize(self):
        bone = self.vault / "训练/骨架/论证逻辑.md"
        bone.parent.mkdir(parents=True, exist_ok=True)
        bone.write_text("---\n状态: 草稿\n---\n## 方法\n> 待核对：补充章节定义\n- 【术语】建立联系", encoding="utf-8")
        r = api.session_start({"task": {"type": "skeleton", "board": "论证逻辑", "title": "审核"}})
        with self.assertRaises(trainer.TrainError):
            api.session_action({"session": r["session"], "action": "final"})
        self.assertIn("状态: 草稿", bone.read_text(encoding="utf-8"))

    def test_complete_argument_curriculum_can_finalize_and_preserves_hierarchy(self):
        from rpg import skeleton
        source = ROOT / "defaults/骨架/论证逻辑.md"
        body = source.read_text(encoding="utf-8")
        bone = self.vault / "训练/骨架/论证逻辑.md"
        bone.parent.mkdir(parents=True, exist_ok=True)
        bone.write_text(body, encoding="utf-8")
        parsed = skeleton.parse(body, "论证逻辑")
        units = {it["name"]: it for it in parsed["items"]}
        self.assertEqual(len(units["选项十三美 · 完整上位清单"]["terms"]), 13)
        self.assertEqual(len(units["选项十三丑 · 完整上位清单"]["terms"]), 13)
        mei = [it for name,it in units.items() if name.startswith("十三美·")]
        chou = [it for name,it in units.items() if name.startswith("十三丑·")]
        self.assertEqual((len(mei), len(chou)), (13,13))
        self.assertTrue(all(it["thoughts"] and it["examples"] for it in mei+chou))
        self.assertEqual(len(units["十三美·建立联系"]["terms"]),6)
        self.assertIn("直接建立联系", units["十三美·建立联系"]["terms"])
        self.assertIn("共同原因", units["十三美·固定秒杀结构"]["terms"])
        self.assertIn("前提型", units["选项十三美 · 完整上位清单"]["terms"])
        self.assertNotIn("> 待核对", body)
        r = api.session_start({"task": {"type": "skeleton", "board": "论证逻辑", "title": "审核完整骨架"}})
        r = api.session_action({"session": r["session"], "action": "final"})
        self.assertTrue(r["finished"])
        self.assertTrue(skeleton.load(paths.Paths(self.vault), "论证逻辑")["final"])


class MigrationTest(unittest.TestCase):
    def test_old_config_is_backed_up_and_replaced(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            v = tmp / "行测"
            (v / "copilot/skills").mkdir(parents=True)
            (v / "训练").mkdir()
            (v / "训练/角色设定.md").write_text("- 配置版本: 2\n- 导师名: 艾琳学姐\n", encoding="utf-8")  # 第二版的文件
            (v / "训练/规则.md").write_text((ROOT / "defaults/规则.md").read_text(encoding="utf-8"), encoding="utf-8")
            up = paths.Paths(v).ensure_train_dir()
            self.assertEqual(up, ["角色设定.md"])  # 台词库不存在 → 直接新建，不算升级
            self.assertIn("劭神韵", (v / "训练/角色设定.md").read_text(encoding="utf-8"))
            self.assertIn("艾琳学姐", (v / "训练/角色设定.旧版.md").read_text(encoding="utf-8"))
            self.assertTrue((v / "训练/台词库·玄幻.md").exists())
            self.assertEqual(paths.Paths(v).ensure_train_dir(), [])
        finally:
            paths.UPGRADED.clear()
            shutil.rmtree(tmp, ignore_errors=True)

    def test_shipped_tuxing_skeleton(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            v = tmp / "行测"
            (v / "copilot/skills").mkdir(parents=True)
            p = paths.Paths(v)
            p.ensure_train_dir()
            f = v / "训练/骨架/图形推理.md"
            self.assertTrue(f.exists())                              # 程序自带的图推 24 诀复制进来了（草稿）
            f.write_text(f.read_text(encoding="utf-8").replace("状态: 草稿", "状态: 已定稿"), encoding="utf-8")
            p.ensure_train_dir()
            self.assertIn("已定稿", f.read_text(encoding="utf-8"))   # 已有的不覆盖
            from rpg import config, store
            rules = config.Rules((v / "训练/规则.md").read_text(encoding="utf-8"))
            g = engine.Game(p, rules, config.Persona(), config.Lines(), store.new_state(dt.date(2026, 10, 1)))
            self.assertTrue(g.available("图形推理"))                  # 有功法文件就算正式板块，不需要 skill
            self.assertIn("图形推理", rules.batches[3])
            self.assertNotIn("图形推理", rules.side)
            it = g.final_items("图形推理")[0]
            hit, miss = skeleton.check_verses(it, "先看对称一笔画，数面数线数交点，图形抽象看曲直，直角平行部分数")
            self.assertEqual(miss, ["有灵魂的一根线"])                  # 口诀整句逐字比对
        finally:
            paths.UPGRADED.clear()
            shutil.rmtree(tmp, ignore_errors=True)

    def test_shipped_ziliao_skeleton(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            v = tmp / "行测"
            (v / "copilot/skills").mkdir(parents=True)
            sk = v / "训练/骨架"
            sk.mkdir(parents=True)
            (sk / "资料分析.md").write_text("---\n板块: 资料分析\n状态: 草稿\n来源skill: xingce-ziliao\n---\n## 旧\n- 【思路】x\n",
                                          encoding="utf-8")
            p = paths.Paths(v)
            p.ensure_train_dir()
            self.assertIn("xingce-ziliao", (sk / "资料分析.md").read_text(encoding="utf-8"))  # 已有的（skill 生成的）不覆盖
            side = sk / "资料分析.程序自带版.md"
            self.assertTrue(side.exists())                           # 程序自带版放在旁边供替换
            (sk / "资料分析.md").unlink()
            side.unlink()
            p.ensure_train_dir()
            f = sk / "资料分析.md"
            f.write_text(f.read_text(encoding="utf-8").replace("状态: 草稿", "状态: 已定稿"), encoding="utf-8")
            p.ensure_train_dir()
            self.assertFalse(side.exists())                          # 用户改过的程序自带版不会再生成旁边那份
            data = skeleton.load(p, "资料分析")
            names = [it["name"] for it in data["items"]]
            self.assertIn("基期量", names)
            self.assertIn("两期比重差（比重增量）", names)
            first = data["items"][0]
            self.assertEqual(first["verses"], ["圈时间、判题型、定主体"])
            it = next(i for i in data["items"] if i["name"] == "基期量")
            self.assertTrue(any("基期时间" in t for t in it["thoughts"]))        # 【识别】按大意判分
            self.assertFalse(any("真题例" in t for t in it["thoughts"]))        # 真题例只作参考，不判分
            self.assertIn("真题例", it["text"])
        finally:
            paths.UPGRADED.clear()
            shutil.rmtree(tmp, ignore_errors=True)

    def test_old_save_gates_are_reset(self):
        from rpg import store
        tmp = Path(tempfile.mkdtemp())
        try:
            v = tmp / "行测"
            (v / "copilot/skills").mkdir(parents=True)
            p = paths.Paths(v)
            p.ensure_train_dir()
            (v / "训练/存档/存档.json").write_text(json.dumps({"version": 1, "created": "2026-09-29", "xp": 500, "gates": [30]}),
                                                  encoding="utf-8")
            st = store.Store(p).load(dt.date(2026, 10, 1))
            self.assertEqual(st["gates"], [])
            self.assertEqual(st["xp"], 500)
            self.assertEqual(st["theme"], "修仙")
        finally:
            paths.UPGRADED.clear()
            shutil.rmtree(tmp, ignore_errors=True)


class EngineTest(unittest.TestCase):
    def make(self, today, state=None, theme="修仙"):
        import random
        from rpg import config, store
        p = paths.Paths(None)
        st = state or store.new_state(today)
        st["theme"] = theme
        return engine.Game(p, config.Rules(), config.Persona("", theme), config.Lines(), st, today, rng=random.Random(1))

    def test_realm_table(self):
        from rpg import themes
        names = {s: themes.realm_name("修仙", s) for s in (50, 51, 53, 59, 60, 61, 62, 63, 64, 65, 69, 70, 80, 84, 85, 92)}
        self.assertEqual(names[50], "凡人 · 未入道")
        self.assertEqual(names[51], "炼气一层")
        self.assertEqual(names[53], "炼气三层")
        self.assertEqual(names[59], "炼气九层")
        self.assertEqual([names[x] for x in (60, 61, 62, 63, 64)], ["筑基初期", "筑基初期", "筑基中期", "筑基中期", "筑基后期"])
        self.assertEqual([names[x] for x in (65, 69, 70)], ["金丹初期", "金丹后期", "元婴初期"])
        self.assertEqual([names[x] for x in (80, 84, 85, 92)], ["大乘初期", "大乘后期", "真仙", "真仙"])
        self.assertEqual(themes.realm_name("玄幻", 62), "青铜骑士中位")

    def test_score_follows_xp_and_target_date(self):
        g = self.make(dt.date(2026, 9, 29))
        total = 300 * (dt.date(2027, 12, 1) - dt.date(2026, 9, 29)).days
        g.state["xp"] = total
        g.state["gates"] = [60, 65, 70, 75, 80]
        self.assertAlmostEqual(g.realm_info()["score"], 80.0, places=1)   # 目标日的理想修为 = 80 分
        g.state["xp"] = total * 7 // 6
        self.assertEqual(g.realm_info()["name"], "大乘后期")               # 85 分线要渡劫 → 卡在 84.99
        self.assertTrue(g.realm_info()["bottleneck"])

    def test_bottleneck_and_calibration_by_contest(self):
        g = self.make(dt.date(2026, 10, 1))
        g.add_boss("第37季", 57)
        self.assertEqual(g.realm_info()["name"], "凡人 · 未入道")   # 只有一次，不校准
        g.add_boss("第38季", 58)
        self.assertEqual(g.realm_info()["name"], "炼气七层")        # min(57, 58) = 57 → 直接跨到炼气七层
        self.assertLessEqual(g.ideal()["diff_days"], 2)              # 大比悟道的修为不算天道进度
        g.add_boss("第39季", 66)
        g.add_boss("第40季", 64)
        info = g.realm_info()
        self.assertEqual(info["name"], "炼气九层")                  # 修为补到 64，但筑基要渡劫
        self.assertTrue(info["bottleneck"])
        st = g.tribulation_status()
        self.assertEqual(st["gate"], 60)
        self.assertTrue(st["conds"][1]["ok"])                       # 最近两次大比都 ≥ 60
        self.assertFalse(st["conds"][2]["ok"])                      # 还没觉醒灵根

    def test_root_grades(self):
        from rpg import config
        r = config.Rules()
        self.assertEqual(r.root_thresholds("论证逻辑"), [0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9])
        self.assertEqual(r.root_thresholds("常识判断")[-1], 0.8)
        self.assertEqual(r.gate_roots(75), {"激活": 7, 1: 4, 2: 1})

    def test_streak_halves_on_miss_and_heart_pill(self):
        t = dt.date(2026, 10, 10)
        g = self.make(t)
        g.state["created"] = "2026-10-01"
        for d in range(1, 9):  # 10/1–10/8 学了，10/9 没学
            g.state["seconds"][f"2026-10-0{d}"] = 3600
        run, bonus = g.streak()
        self.assertEqual(run, 0)
        self.assertAlmostEqual(bonus, 0.08)
        g.bag_add("护心丹")
        g.housekeeping()                                            # 10/9 自动服护心丹
        self.assertEqual(g.streak()[0], 9)
        self.assertEqual(g.state["bag"]["护心丹"], 0)

    def test_ideal_line_and_dao(self):
        g = self.make(dt.date(2026, 10, 9))
        g.state["created"] = "2026-09-29"
        self.assertEqual(g.ideal()["diff_days"], 10.0)
        g.state["leave"] = ["2026-10-01"]
        self.assertEqual(g.ideal()["diff_days"], 9.0)
        self.assertEqual(g.dao(), 36)                               # 近 14 天：开始前 4 天 + 告假 1 天 = 5/14

    def test_weekly_quests(self):
        g = self.make(dt.date(2026, 10, 7))
        for _ in range(20):
            g._award(15, "wrong", "论证逻辑", "", True, "斩", bonus=False)
        ev = g.housekeeping()
        self.assertTrue(any("周常完成：斩心魔" in e.get("msg", "") for e in ev))
        self.assertNotIn("all", g.state["weekly"][g.week_key()])


if __name__ == "__main__":
    unittest.main()

