"""灵台手札：本子存取、师傅编纂（识图 / OCR+AI / 只有 OCR）、调阅库里的 Markdown。"""
import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rpg import ai, notes, paths, report

PNG = "data:image/png;base64," + base64.b64encode(b"\x89PNG fake").decode("ascii")
STROKE = {"t": "pen", "c": "#222", "w": 3, "p": [[10, 10], [20, 30.123]]}


class NotesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.paths = paths.Paths(Path(self.tmp.name))
        self.paths.ensure_train_dir()
        notes._IMG_INDEX["t"] = 0

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_list_get_delete(self):
        r = notes.save(self.paths, {"title": "言语 · 主旨题", "paper": "grid", "pages": [{"strokes": [STROKE]}, {"strokes": []}]})
        nid = r["id"]
        self.assertTrue((self.paths.train / "手札/手写" / (nid + ".json")).is_file())
        d = notes.get(self.paths, nid)
        self.assertEqual(d["paper"], "grid")
        self.assertEqual(d["pages"][0]["strokes"][0]["p"][1], [20.0, 30.1])
        # 只改打字补充：笔画、纸不丢
        notes.save(self.paths, {"id": nid, "text": "补充一句"})
        d = notes.get(self.paths, nid)
        self.assertEqual((d["text"], d["paper"], len(d["pages"])), ("补充一句", "grid", 2))
        self.assertEqual([b["id"] for b in notes.listing(self.paths)], [nid])
        with self.assertRaises(notes.NotesError):
            notes.get(self.paths, "../../etc")
        notes.delete(self.paths, nid)
        self.assertEqual(notes.listing(self.paths), [])

    def test_compile_with_vision_model(self):
        nid = notes.save(self.paths, {"title": "片段阅读", "pages": [{"strokes": [STROKE]}]})["id"]
        reply = "```markdown\n# 主旨题\n\n## 转折\n- **但是** 后面是重点\n```"
        with patch.object(ai, "vision_available", return_value=True), \
                patch.object(ai, "settings", return_value={"vision_model": "vl-test"}), \
                patch.object(ai, "chat", return_value=reply) as chat:
            r = notes.compile(self.paths, nid, [PNG], "")
        self.assertTrue(chat.call_args.kwargs["vision"])
        content = chat.call_args.args[0][0]["content"]
        self.assertEqual(content[1]["type"], "image_url")
        self.assertEqual(r["path"], "训练/手札/片段阅读.md")
        text = (self.paths.vault / r["path"]).read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# 主旨题\n\n> 灵台手札 · 师傅编纂（识图模型（vl-test））"))
        self.assertIn("- **但是** 后面是重点", text)
        self.assertNotIn("```", text)
        self.assertEqual(notes.get(self.paths, nid)["compiled"], r["path"])

    def test_compile_ocr_then_ai_and_ocr_only(self):
        nid = notes.save(self.paths, {"title": "数量", "pages": [{"strokes": [STROKE]}]})["id"]
        with patch.object(ai, "vision_available", return_value=False), patch.object(ai, "available", return_value=True), \
                patch.object(report, "ocr", return_value="工程问题 赋值总量"), \
                patch.object(ai, "chat", return_value="# 工程问题\n\n- 赋值总量") as chat:
            r = notes.compile(self.paths, nid, [PNG], "效率比")
        prompt = chat.call_args.args[0][1]["content"]
        self.assertIn("工程问题 赋值总量", prompt)
        self.assertIn("效率比", prompt)
        self.assertIn("系统 OCR 认字 + AI 排版", r["markdown"])
        with patch.object(ai, "vision_available", return_value=False), patch.object(ai, "available", return_value=False), \
                patch.object(report, "ocr", return_value="工程问题"):
            r = notes.compile(self.paths, nid, [PNG], "")
        self.assertIn("没有 AI", r["markdown"])
        self.assertIn("工程问题", r["markdown"])
        # 认不了字也没打字：说清楚怎么办
        with patch.object(ai, "vision_available", return_value=False), \
                patch.object(report, "ocr", side_effect=report.ReportError("这台电脑没有 OCR：…")):
            with self.assertRaisesRegex(notes.NotesError, "识图模型"):
                notes.compile(self.paths, nid, [PNG], "")
        with self.assertRaises(notes.NotesError):
            notes.compile(self.paths, nid, [], "")

    def test_md_tree_and_read(self):
        v = self.paths.vault
        (v / "言语").mkdir()
        (v / "言语/主旨.md").write_text("# 主旨\n![[图1.png]]\n![](附件/图2.png)\n[[判断]]", encoding="utf-8")
        (v / "附件").mkdir()
        (v / "附件/图1.png").write_bytes(b"x")
        (v / "附件/图2.png").write_bytes(b"x")
        (v / ".obsidian").mkdir()
        (v / ".obsidian/workspace.md").write_text("x", encoding="utf-8")
        (v / "存档").mkdir(exist_ok=True)
        (v / "存档/旧.md").write_text("x", encoding="utf-8")
        for d in ("蒸馏skill", "copilot", "言语/skill", "资料分析/速算"):
            (v / d).mkdir(parents=True, exist_ok=True)
            (v / d / "x.md").write_text("x", encoding="utf-8")
        (v / "根目录.md").write_text("x", encoding="utf-8")
        tree = notes.md_tree(self.paths)
        files = [f["path"] for f in tree]
        self.assertEqual(sorted(files), ["言语/主旨.md", "资料分析/速算/x.md"])   # 只有板块文件夹，不含 skill / copilot / 训练 / 根目录
        self.assertEqual({f["top"] for f in tree}, {"言语", "资料分析"})
        self.assertFalse(any(f.startswith((".obsidian", "存档")) for f in files))
        r = notes.read_md(self.paths, "言语/主旨.md")
        self.assertEqual(r["images"], {"图1.png": "附件/图1.png", "附件/图2.png": "附件/图2.png"})
        for bad in ("../x.md", "附件/图1.png", "言语/没有.md"):
            with self.assertRaises(notes.NotesError):
                notes.read_md(self.paths, bad)


    def test_export_pdf(self):
        import base64
        import pymupdf
        nid = notes.save(self.paths, {"title": "类比推理", "pages": [{"strokes": [STROKE]}]})["id"]
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 100, 141), False)
        pix.clear_with(255)
        jpg = "data:image/jpeg;base64," + base64.b64encode(pix.tobytes("jpeg")).decode()
        r = notes.export_pdf(self.paths, nid, [jpg, jpg])
        self.assertEqual((r["path"], r["pages"]), ("训练/手札/导出/类比推理.pdf", 2))
        doc = pymupdf.open(str(self.paths.vault / r["path"]))
        self.assertEqual((doc.page_count, round(doc[0].rect.width)), (2, 595))      # A4
        self.assertEqual(notes.export_file(self.paths, r["path"]), (self.paths.vault / r["path"]).resolve())
        self.assertIsNone(notes.export_file(self.paths, "训练/存档/存档.json"))      # 只给导出目录里的 PDF
        self.assertIsNone(notes.export_file(self.paths, "训练/手札/导出/../../存档/x.pdf"))
        with self.assertRaises(notes.NotesError):
            notes.export_pdf(self.paths, nid, [])


if __name__ == "__main__":
    unittest.main()
