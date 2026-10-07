"""玉简（记忆卡片）：Markdown 存取、FSRS 排期、每日上限、撤销、简匣、导入、藏简阁、心跳计时。"""
import datetime as dt
import tempfile
import time
import unittest
from pathlib import Path

from rpg import api, cards, config, engine, paths, store


class CardsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self.tmp.name)
        (self.vault / "copilot/skills").mkdir(parents=True)
        self.p = paths.Paths(self.vault)
        self.p.ensure_train_dir()
        self.day = dt.date(2026, 10, 7)
        self.g = engine.Game(self.p, config.Rules(), config.Persona(), config.Lines(), store.new_state(self.day), self.day)
        cards._CACHE["key"] = None

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, front, back="答", deck="资料分析::速算", typ="问答", tags=""):
        return cards.add(self.g, {"deck": deck, "type": typ, "front": front, "back": back, "tags": tags})

    def test_markdown_round_trip_and_obsidian_edits(self):
        r = self.add("隔年增长率怎么算？", "r = r1 + r2 + r1×r2", tags="增长 公式")
        f = self.vault / "训练/卡片/资料分析.md"
        text = f.read_text(encoding="utf-8")
        self.assertIn("## 玉简 %s\n简匣: 资料分析::速算\n类型: 问答\n标签: 增长 公式\n### 正\n隔年增长率怎么算？" % r["id"], text)
        # 在 Obsidian 里手写一枚没编号的：读到时补上编号，写回文件
        f.write_text(text + "## 玉简\n简匣: 资料分析\n类型: 填空\n### 正\n比重差小于 {{c1::增长率差}}，{{c2::右边}}\n### 反\n\n", encoding="utf-8")
        notes, _ = cards.load(self.p)
        self.assertEqual(len(notes), 2)
        self.assertTrue(notes[1]["id"])
        self.assertIn("## 玉简 %s\n" % notes[1]["id"], f.read_text(encoding="utf-8"))
        self.assertEqual(cards.card_ords(notes[1]), ["c1", "c2"])
        # 改内容不丢进度
        key = "%s#1" % r["id"]
        cards.answer(self.g, key, 4)
        cards.update(self.g, {"id": r["id"], "back": "r1 + r2 + r1·r2"})
        self.assertEqual(self.g.state["cards"]["sched"][key]["st"], 2)
        # 换到别的顶层简匣 = 换文件
        cards.move(self.g, [r["id"]], "数量关系::工程")
        self.assertIn(r["id"], (self.vault / "训练/卡片/数量关系.md").read_text(encoding="utf-8"))
        self.assertNotIn(r["id"], f.read_text(encoding="utf-8"))

    def test_fsrs_learning_steps_and_intervals(self):
        r = self.add("问")
        key = "%s#1" % r["id"]
        now = time.time()
        iv = cards.intervals(self.g, key, "资料分析::速算", now)
        self.assertEqual((iv[1], iv[2], iv[3]), ("1分钟", "6分钟", "10分钟"))
        self.assertTrue(iv[4].endswith("天"))
        cards.answer(self.g, key, 3, now=now)                       # 通透 → 第二步 10 分钟
        s = self.g.state["cards"]["sched"][key]
        self.assertEqual((s["st"], s["step"]), (1, 1))
        cards.answer(self.g, key, 3, now=now + 700)                 # 再通透 → 毕业，进复习
        s = self.g.state["cards"]["sched"][key]
        self.assertEqual(s["st"], 2)
        self.assertGreaterEqual(s["ivl"], 1)
        # 复习卡：四个评分的间隔 晦涩 ≤ 通透 < 了然，再参进入重参
        s.update(due=self.g.state["cards"]["today"]["d"], last=(dt.date.fromisoformat(s["due"]) - dt.timedelta(days=4)).isoformat())
        iv = cards.intervals(self.g, key, "资料分析::速算", now)
        days = [float(iv[k][:-1]) for k in (2, 3, 4)]
        self.assertTrue(days[0] <= days[1] < days[2])
        self.assertEqual(iv[1], "10分钟")
        cards.answer(self.g, key, 1, now=now)
        s = self.g.state["cards"]["sched"][key]
        self.assertEqual((s["st"], s["lapses"]), (3, 1))

    def test_queue_limits_undo_and_siblings(self):
        for i in range(5):
            self.add("问%d" % i)
        rev = self.add("正", "反", typ="问答+反向")
        cards.deck_action(self.g, {"action": "options", "name": "资料分析", "options": {"new_per_day": 3}})
        order, counts, _ = cards.queue(self.g, "资料分析")
        self.assertEqual(counts["new"], 3)                          # 上层的每日新简数管着子匣
        first = order[0]
        xp = self.g.state["xp"]
        cards.answer(self.g, first, 4)
        self.assertEqual(self.g.state["xp"], xp + cards.XP[4])
        _, counts, _ = cards.queue(self.g, "资料分析")
        self.assertEqual(counts["new"], 2)
        self.assertEqual(cards.undo(self.g), first)
        _, counts, _ = cards.queue(self.g, "资料分析")
        self.assertEqual(counts["new"], 3)
        self.assertEqual(self.g.state["xp"], xp)
        self.assertNotIn(first, self.g.state["cards"]["sched"])
        # 反向玉简：正向温过后，反向今天不再出
        cards.deck_action(self.g, {"action": "options", "name": "资料分析", "options": {"new_per_day": 50}})
        cards.answer(self.g, rev["id"] + "#1", 4)
        order, _, _ = cards.queue(self.g, "资料分析")
        self.assertNotIn(rev["id"] + "#2", order)
        # 暂停的卡不出
        cards.suspend(self.g, [order[0]])
        self.assertNotIn(order[0], cards.queue(self.g, "资料分析")[0])

    def test_tree_rename_delete_and_search(self):
        self.add("甲", deck="资料分析::速算")
        self.add("乙", deck="资料分析::比重", tags="比重")
        tree = {d["name"]: d for d in cards.tree(self.g)}
        self.assertIn("政治理论", tree)                              # 默认 12 个板块
        self.assertEqual((tree["资料分析"]["new"], tree["资料分析::速算"]["new"], tree["资料分析::速算"]["depth"]), (2, 1, 1))
        cards.deck_action(self.g, {"action": "rename", "name": "资料分析::速算", "new": "资料分析::速算技巧"})
        self.assertEqual(cards.search(self.g, {"q": "甲"})["rows"][0]["deck"], "资料分析::速算技巧")
        self.assertEqual(cards.search(self.g, {"q": "比重"})["total"], 1)
        with self.assertRaises(cards.CardError):
            cards.deck_action(self.g, {"action": "delete", "name": "资料分析"})
        cards.deck_action(self.g, {"action": "delete", "name": "资料分析", "with_cards": True})
        self.assertEqual(cards.search(self.g, {})["total"], 0)
        with self.assertRaises(cards.CardError):
            self.add("{{c1}}不对", typ="填空")

    def test_import_anki_text_and_markdown_table(self):
        txt = "#separator:tab\n#html:true\n<b>增长量</b>公式？\t现期×r/(1+r)\t增长\n{{c1::基期}} = 现期/(1+r)\t\n坏行\n"
        r = cards.import_text(self.g, {"deck": "资料分析", "text": txt})
        self.assertEqual((r["added"], r["skipped"]), (2, 1))
        rows = cards.search(self.g, {"deck": "资料分析"})["rows"]
        self.assertEqual(cards.note_get(self.g, rows[0]["id"])["front"], "**增长量**公式？")   # Anki 的粗体转成 Markdown
        self.assertEqual(rows[0]["front"], "增长量公式？")                                       # 藏简阁列表里显示纯文字
        self.assertEqual(rows[1]["type"], "填空")
        table = "Question | Answer | Tags\n------- | -------- | --------\n什么是比重？ | 部分/整体 | 比重\n"
        self.assertEqual(cards.import_text(self.g, {"deck": "资料分析", "text": table.replace(" | ", "|")}) ["added"], 0)
        r = cards.import_text(self.g, {"deck": "资料分析", "text": "#separator:pipe\n" + table})
        self.assertEqual(r["added"], 1)

    def test_stats_and_info(self):
        r = self.add("问")
        key = r["id"] + "#1"
        cards.answer(self.g, key, 4, secs=12)
        st = cards.stats(self.g)
        self.assertEqual((st["total_reviews"], st["streak"], st["retention"]), (1, 1, 1.0))
        self.assertEqual(sum(st["forecast"]), 1)
        inf = cards.info(self.g, key)
        self.assertEqual(inf["history"][0]["rating"], "了然")
        self.assertEqual(inf["sched"]["state"], "复习")


class CardsApiTest(unittest.TestCase):
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

    def test_review_flow_and_heartbeat(self):
        api.cards_add({"deck": "言语", "type": "问答", "front": "“不刊之论”的刊？", "back": "删改"})
        r = api.cards_next({"deck": "言语"})
        self.assertEqual(r["card"]["front"], "“不刊之论”的刊？")
        self.assertEqual(r["intervals"]["1"] if "1" in r["intervals"] else r["intervals"][1], "1分钟")
        cards.LAST_ANSWER["t"] = 0
        self.assertFalse(api.heartbeat({"seconds": 30, "cards": True})["studying"])      # 没温简不算
        r = api.cards_answer({"deck": "言语", "key": r["card"]["key"], "rating": 4, "secs": 8})
        self.assertTrue(r["done"])
        hb = api.heartbeat({"seconds": 60, "cards": True})
        self.assertTrue(hb["studying"])
        self.assertEqual(hb["minutes"], 1)
        r = api.cards_undo({"deck": "言语"})
        self.assertEqual(r["card"]["front"], "“不刊之论”的刊？")
        d = api.dashboard({})
        self.assertTrue(any(t["type"] == "cards" for t in d["plan"]["tasks"]))


class CardGenTest(CardsApiTest):
    """🧙 师傅制卡（PDF / Markdown → AI 出卡草稿 → 刻入）和 AI 方案切换"""

    def _pdf(self):
        import pymupdf
        doc = pymupdf.open()
        for i, t in enumerate(["第一章 增长\n隔年增长率 = r1 + r2 + r1×r2，用于求隔一年的增长率。" * 3,
                               "第二章 比重\n现期比重 = 部分 / 整体。" * 3, ""]):
            p = doc.new_page()
            if t:
                p.insert_text((50, 72), t, fontname="china-s", fontsize=11)
        doc.set_toc([[1, "第一章 增长", 1], [1, "第二章 比重", 2], [1, "插图", 3]])
        return "data:application/pdf;base64," + __import__("base64").b64encode(doc.tobytes()).decode()

    def test_pdf_to_cards(self):
        from unittest.mock import patch
        from rpg import ai
        info = api.cardgen_load({"kind": "file", "name": "花生资料分析.pdf", "data": self._pdf()})
        self.assertEqual((info["kind"], info["pages"], [t["title"] for t in info["toc"]]), ("pdf", 3, ["第一章 增长", "第二章 比重", "插图"]))
        plan = api.cardgen_chunks({"src": info["src"], "sections": [0]})
        self.assertEqual([c["pages"] for c in plan["chunks"]], [[1]])
        plan = api.cardgen_chunks({"src": info["src"], "pages": [1, 3]})
        self.assertEqual(sum(len(c["pages"]) for c in plan["chunks"]), 3)
        reply = ('```json\n{"cards": [{"type": "问答", "front": "隔年增长率公式？", "back": "r1 + r2 + r1×r2", "tags": ["#增长"]},'
                 '{"type": "填空", "front": "现期比重 = {{c1::部分}} / 整体", "back": "", "tags": "比重"},'
                 '{"type": "问答", "front": "没有答案的卡", "back": ""}]}\n```')
        with patch.object(ai, "available", return_value=True), patch.object(ai, "vision_available", return_value=False), \
                patch.object(ai, "chat", return_value=reply) as chat:
            r = api.cardgen_gen({"src": info["src"], "chunk": plan["chunks"][0], "deck": "资料分析", "density": "精简", "types": "问答"})
        self.assertIn("隔年增长率", chat.call_args.args[0][1]["content"])
        self.assertIn("只出问答卡", chat.call_args.args[0][1]["content"])
        self.assertEqual(r["skipped"], [3])                                  # 第 3 页没字、没识图模型：跳过
        self.assertEqual([(c["type"], c["tags"]) for c in r["cards"]], [("问答", ["增长"]), ("填空", ["比重"])])
        self.assertTrue(r["cards"][0]["extra"].startswith("出自《花生资料分析》"))
        a = api.cards_add_many({"deck": "资料分析::速算", "cards": r["cards"] + [{"type": "填空", "front": "没挖空"}]})
        self.assertEqual((a["added"], a["skipped"]), (2, 1))
        self.assertEqual(api.cards_search({"deck": "资料分析"})["total"], 2)

    def test_markdown_sections(self):
        md = "---\ntags: x\n---\n# 增长\n## 隔年增长\n" + "隔年增长率内容。\n\n" * 5 + "## 混合增长\n混合增长率内容。\n# 比重\n比重内容。\n"
        info = api.cardgen_load({"kind": "paste", "name": "笔记", "text": md})
        self.assertEqual([t["title"] for t in info["toc"]], ["增长", "隔年增长", "混合增长", "比重"])
        plan = api.cardgen_chunks({"src": info["src"], "sections": [1]})
        self.assertEqual(len(plan["chunks"]), 1)
        self.assertIn("隔年增长率内容", plan["chunks"][0]["text"])
        self.assertNotIn("混合增长率内容", plan["chunks"][0]["text"])
        self.assertNotIn("tags: x", api.cardgen_chunks({"src": info["src"]})["chunks"][0]["text"])

    def test_ai_profiles_switch(self):
        api.settings_set({"api_key": "sk-deep", "base_url": "https://api.deepseek.com", "model": "deepseek-chat"})
        api.ai_profile({"action": "save", "name": "DeepSeek"})
        api.settings_set({"api_key": "sk-qwen", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus"})
        s = api.settings_get({})
        self.assertEqual(s["ai_active"], "")                                 # 改了设置：不再是 DeepSeek 那套
        api.ai_profile({"action": "save", "name": "千问"})
        s = api.ai_profile({"action": "use", "name": "DeepSeek"})
        self.assertEqual((s["model"], s["key_tail"], s["ai_active"]), ("deepseek-chat", "deep", "DeepSeek"))
        self.assertEqual([p["name"] for p in s["ai_profiles"]], ["DeepSeek", "千问"])
        self.assertNotIn("api_key", s["ai_profiles"][0])                      # key 不回给网页
        s = api.ai_profile({"action": "use", "name": "千问"})
        self.assertEqual(s["base_url"], "https://dashscope.aliyuncs.com/compatible-mode/v1")
        api.ai_profile({"action": "delete", "name": "千问"})
        self.assertEqual(api.settings_get({})["ai_active"], "")


class CardsMoreTest(CardsApiTest):
    """2.4.0：师傅讲讲只帮记忆并存进玉简、每日数量的总设置、灵脉图（思维导图）"""

    def test_explain_saved_and_prompt(self):
        from unittest.mock import patch
        from rpg import ai
        api.cards_add({"deck": "政治理论", "type": "问答", "front": "逻辑关系包括？", "back": "全同、全异、种属、交叉"})
        key = api.cards_next({"deck": ""})["card"]["key"]
        with patch.object(ai, "available", return_value=True), patch.object(ai, "chat", return_value="口诀：同异种交\n### 小标题") as chat:
            r = api.cards_explain({"key": key})
        system = chat.call_args.args[0][0]["content"]
        self.assertIn("不评判", system)
        self.assertNotIn("卡片内容如果有错", system)
        self.assertIn("#### ", r["saved"])
        self.assertIn("＃＃＃ 小标题", r["saved"])                       # 回复里的标题降级，不打乱玉简格式
        text = (self.vault / "训练/卡片/政治理论.md").read_text(encoding="utf-8")
        self.assertIn("### 师傅讲讲\n#### ", text)
        cards._CACHE["key"] = None
        self.assertIn("口诀：同异种交", api.cards_next({"deck": ""})["card"]["ai"])
        self.assertTrue(cards.reviewing())                                 # 在温简页面上就算在复习

    def test_global_daily_limits(self):
        for i in range(5):
            api.cards_add({"deck": "资料分析", "type": "问答", "front": "问%d" % i, "back": "答"})
        api.cards_deck({"action": "options", "name": "*", "options": {"new_per_day": 3}})
        self.assertEqual(api.cards_overview({})["defaults"]["new_per_day"], 3)
        self.assertEqual(api.cards_next({"deck": "资料分析"})["counts"]["new"], 3)
        api.cards_deck({"action": "options", "name": "资料分析", "options": {"new_per_day": 4}})   # 单个匣子另设的优先
        self.assertEqual(api.cards_next({"deck": "资料分析"})["counts"]["new"], 4)

    def test_mindmap(self):
        lst = api.mm_list({})
        self.assertEqual(lst["boards"][0], {"board": "政治理论", "maps": []})
        d = api.mm_get({"board": "资料分析", "name": "资料分析"})            # 第一次打开自动建一幅
        self.assertEqual(d["data"]["root"]["data"]["text"], "资料分析")
        root = {"data": {"text": "资料分析"}, "children": [{"data": {"text": "增长"}, "children": [{"data": {"text": "隔年增长"}}]}]}
        self.assertEqual(api.mm_save({"board": "资料分析", "name": "资料分析", "data": {"root": root, "layout": "mindMap"}})["nodes"], 3)
        r = api.mm_create({"board": "资料分析", "name": "资料分析"})
        self.assertEqual(r["name"], "资料分析（2）")                         # 重名加序号
        api.mm_rename({"board": "资料分析", "name": "资料分析（2）", "new": "速算"})
        self.assertEqual([m["name"] for m in api.mm_list({})["boards"][-1]["maps"]], ["资料分析", "速算"])
        e = api.mm_export({"board": "资料分析", "name": "资料分析", "ext": "md",
                           "data": "data:text/markdown;base64," + __import__("base64").b64encode("# 资料分析".encode()).decode()})
        self.assertEqual(e["path"], "训练/灵脉图/导出/资料分析.md")
        self.assertIn("&t=", e["url"])
        with self.assertRaises(api.ApiError):
            api.mm_export({"board": "资料分析", "name": "x", "ext": "exe", "data": "data:,1"})
        with self.assertRaises(api.ApiError):
            api.mm_get({"board": "../x", "name": "y"})
        api.mm_delete({"board": "资料分析", "name": "速算"})
        self.assertEqual(len(api.mm_list({})["boards"][-1]["maps"]), 1)
