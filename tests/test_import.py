"""导入真题：模考复盘、练习册 txt、待修重新导入、补答案、AI 补知识点（用假 AI）。"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rpg import ai, importer, paths, question_bank as bank

REVIEW = """## 材料（第111-112题）
![[S36-M111-112.png]]
2023年，全国……
---
### 111. ✅
在校生人数约为多少万人？
- **A.** 100
- **B.** 200
- **C.** 300
- **D.** 400
> [!check]- 答案
> 正确答案：**B**　我的答案：**B**　正确

> [!note] 复盘
> 我的笔记
---
### 112. ❌
同比增长约？
- **A.** 1%
- **B.** 2%
- **C.** 3%
- **D.** 4%
> [!check]- 答案
> 正确答案：**A**　我的答案：**C**　错误

> [!note] 复盘
>
---
"""

BOOK = """目录
001 练习题01
四海公考 SIHAIGONGKAO
1.研究显示，某河流的鱼类数量下降是由于上游建坝。以下哪项如果为真，最能削弱上述结论：
A。下游污染严重 B.坝建成前鱼已减少
C．渔民捕捞增加 D。鱼类迁徙路线改变
2。所有的甲都是乙，有些丙不是乙，由此可以推出：
A。有些丙不是甲 B.所有乙都是甲 C．有些甲是丙 D。所有丙都是乙
3.一种说法认为天气越冷，感冒的人越多。研究人员统计发现两者无关。下面哪项最能支持研究人员：
A：冬季室内通风少 B.病毒传播与温度无关 C．感冒药冬季销量高
"""


class ImportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        v = Path(self.tmp.name)
        (v / "copilot/skills").mkdir(parents=True)
        d = v / "FB模考试卷复盘/板块复盘/第36季"
        (d / "attachments").mkdir(parents=True)
        (d / "attachments/S36-M111-112.png").write_bytes(b"png")
        (d / "13-资料分析.md").write_text(REVIEW, encoding="utf-8")
        self.p = paths.Paths(v)
        self.p.ensure_train_dir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_season_import_copies_images_and_dedupes(self):
        self.assertEqual(importer.status(self.p)["seasons"], [{"season": 36, "imported": 0}])
        r = importer.commit(self.p, {"kind": "season", "season": 36})
        self.assertEqual((r["ready"], r["fix"]), (2, 0))
        img = self.p.train / "题库/图片/资料分析/粉笔36季-M111-112.png"
        self.assertTrue(img.is_file())                                       # 材料截图复制进题库
        qs, errors = bank.read(self.p, "资料分析")
        self.assertEqual(errors, [])
        self.assertEqual([q["answer"] for q in qs], ["B", "A"])
        self.assertTrue(qs[0]["stem"].startswith("（粉笔第36季模考）\n![[训练/题库/图片/资料分析/粉笔36季-M111-112.png]]"))
        self.assertNotIn("我的笔记", qs[0]["stem"])                          # 复盘笔记不进题干
        self.assertEqual(qs[0]["analysis"], "")                              # 解析待补
        r = importer.commit(self.p, {"kind": "season", "season": 36})
        self.assertEqual((r["ready"], r["dup"]), (0, 2))                     # 再导入一次全部跳过

    def test_book_import_fix_file_and_answers(self):
        body = {"kind": "text", "text": BOOK, "prefix": "测试书", "no_source": True}
        pre = importer.preview(self.p, body)
        self.assertFalse((self.p.train / "题库/_待修").exists())             # 预览不写文件
        r = importer.commit(self.p, body)
        self.assertEqual((r["ready"], r["fix"]), (2, 1))                     # 第 3 题缺 D 选项 → 待修
        self.assertEqual(pre["ready"], 2)
        arg, = bank.read_all(self.p, "论证逻辑")[0]
        self.assertEqual((arg["id"], arg["topic"], arg["pending"]), ("测试书-01-01", "削弱", True))
        self.assertNotIn("目录", arg["stem"])
        self.assertEqual(bank.read_all(self.p, "形式逻辑")[0][0]["id"], "测试书-01-02")
        importer.commit(self.p, body)                                         # 再导入：待修文件不重复追加
        fix = self.p.train / "题库/_待修/测试书.md"
        self.assertEqual(fix.read_text(encoding="utf-8").count("## 题目 测试书-01-03"), 1)
        t = fix.read_text(encoding="utf-8")
        t = t.replace("D. \n", "D. 感冒与免疫力有关\n").replace("### 板块\n待分类", "### 板块\n论证逻辑")
        t = t[:t.rindex("### 检查")] + "### 检查\n\n"
        fix.write_text(t, encoding="utf-8")
        r = importer.commit(self.p, {"kind": "fix", "file": "测试书.md"})
        self.assertEqual(r["ready"], 1)
        self.assertFalse(fix.exists())                                        # 全部修好后待修文件删除
        r = importer.fill_answers(self.p, {"prefix": "测试书-01", "key": "1-3 BAB"})
        self.assertEqual(r["filled"], 3)
        self.assertEqual([q["answer"] for q in bank.read(self.p, "论证逻辑")[0]], ["B", "B"])
        self.assertEqual(bank.pending(self.p, "论证逻辑"), 0)

    def test_set_markers_answer_table_and_remove(self):
        q = lambda n: "%d.某研究认为甲导致乙（样本%s）。以下哪项如果为真，最能削弱上述结论：\nA。选项一 B.选项二\nC．选项三 D。选项四\n" % (n, "一二三"[n - 1])
        text = ("目录\n001 练习题01\n007 02 练习题\n"                       # 目录里的“练习题”不算一套
                "#01 练习题\n" + q(1) + q(2) +
                "页02 练习题\n" + q(2).replace("甲", "丙") + q(3).replace("甲", "丁"))   # 第 2 套第 1 题题号没认出
        r = importer.commit(self.p, {"kind": "text", "text": text, "prefix": "花生", "no_source": True})
        ids = [x["id"] for x in bank.read_all(self.p, "论证逻辑")[0]]
        self.assertEqual(ids, ["花生-01-01", "花生-01-02", "花生-02-03"])          # 按标记分套，套号不错位
        self.assertEqual(r["fix"], 1)                                             # 第 2 套从 2 开始 → 待修核对
        r = importer.fill_answers(self.p, {"prefix": "花生", "key": "练习01 AB\n练习02 CDB"})
        self.assertEqual(r["filled"], 3)
        self.assertEqual([x["answer"] for x in bank.read_all(self.p, "论证逻辑")[0]], ["A", "B", "B"])
        r = importer.remove(self.p, {"prefix": "花生"}, {"论证逻辑::花生-01-01"})
        self.assertEqual((r["removed"], r["kept"]), (3, 1))                       # 做过的保留，待修里的也删
        self.assertEqual([x["id"] for x in bank.read_all(self.p, "论证逻辑")[0]], ["花生-01-01"])
        self.assertFalse((self.p.train / "题库/_待修/花生.md").exists())

    def test_upload_pdf_split_and_import(self):
        import base64
        sd = self.p.vault / "copilot/skills/xingce-mokao-split/scripts"
        sd.mkdir(parents=True)
        (sd / "split_mokao.py").write_text(            # 假拆分脚本：按真脚本的输出位置写板块复盘
            "import re,sys\nfrom pathlib import Path\np=Path(sys.argv[1]);n=re.search(r'第(\\d+)季',p.stem).group(1)\n"
            "o=p.parent.parent/'板块复盘'/('第%s季'%n);o.mkdir(parents=True,exist_ok=True)\n"
            "(o/'02-常识判断.md').write_text('### 21. ✅\\n下列说法正确的是\\n- **A.** 甲\\n- **B.** 乙\\n- **C.** 丙\\n- **D.** 丁\\n"
            "> 正确答案：**D**　我的答案：**D**\\n---\\n',encoding='utf-8')\n", encoding="utf-8")
        data = base64.b64encode(b"%PDF-1.4 x").decode()
        with self.assertRaises(importer.ImportError_):
            importer.save_pdf(self.p, {"name": "模考.pdf", "data": data})              # 没有季数
        with self.assertRaises(importer.ImportError_):
            importer.save_pdf(self.p, {"name": "第37季.pdf", "data": base64.b64encode(b"hello").decode()})   # 不是 PDF
        f = importer.save_pdf(self.p, {"name": "../模考.pdf", "data": data, "season": 37})["file"]
        self.assertEqual(f, "第37季-模考.pdf")                                         # 不能写到别的目录
        self.assertEqual(importer.status(self.p)["pdfs"][0], {"file": f, "season": 37, "split": False})
        r = importer.split_pdf(self.p, {"file": f})
        self.assertEqual(r["ready"], 1)
        self.assertEqual(bank.read(self.p, "常识判断")[0][0]["id"], "粉笔37季-021")
        self.assertTrue(importer.status(self.p)["pdfs"][0]["split"])

    def test_figure_options_from_screenshot_and_fix_cleanup(self):
        d = self.p.seasons / "第36季"
        (d / "attachments/S36-Q077.png").write_bytes(b"png")
        (d / "07-图形推理.md").write_text("### 77. ❌\n\n![[S36-Q077.png]]\n\n从所给的四个选项中，选择最合适的一个填入问号处：\n\n"
                                       "> [!check]- 答案\n> 正确答案：**C**　我的答案：**A**　错误\n\n> [!note] 复盘\n>\n\n---\n", encoding="utf-8")
        fix = self.p.train / "题库/_待修/粉笔第36季模考.md"     # 旧版本导入时进了待修
        fix.parent.mkdir(parents=True, exist_ok=True)
        fix.write_text("# 待修\n\n## 题目 粉笔36季-077\n### 板块\n图形推理\n### 检查\n⚠ 复盘文件里选项不全\n\n", encoding="utf-8")
        r = importer.commit(self.p, {"kind": "season", "season": 36})
        self.assertEqual((r["ready"], r["fix"]), (3, 0))
        q = bank.read(self.p, "图形推理")[0][0]
        self.assertEqual((q["options"], q["answer"]), ({k: k for k in "ABCD"}, "C"))
        self.assertFalse(fix.exists())                                        # 入库后从待修里删掉

    def test_same_stem_figures_and_shared_material_not_deduped(self):
        d = self.p.seasons / "第36季"
        fig = "### %d. ✅\n\n![[S36-Q%03d.png]]\n\n从所给的四个选项中，选择最合适的一个填入问号处，使之呈现一定的规律性：\n\n> 正确答案：**A**\n---\n"
        for n in (77, 78, 79):
            (d / ("attachments/S36-Q%03d.png" % n)).write_bytes(b"png")
        (d / "07-图形推理.md").write_text("".join(fig % (n, n) for n in (77, 78, 79)), encoding="utf-8")
        mat = "2023年，全国规模以上工业企业实现营业收入133.4万亿元，比上年增长1.1%；发生营业成本113.6万亿元，增长1.2%；实现利润总额7.7万亿元，下降2.3%。"
        q = "### %d. ✅\n%s\n- **A.** 1\n- **B.** 2\n- **C.** 3\n- **D.** 4\n> 正确答案：**B**\n---\n"
        (d / "13-资料分析.md").write_text("## 材料（第111-112题）\n![[S36-M111-112.png]]\n" + mat + "\n---\n" + q % (111, "营业收入利润率约为？")
                                       + q % (112, "营业成本同比增量约为？"), encoding="utf-8")
        r = importer.commit(self.p, {"kind": "season", "season": 36})
        self.assertEqual((r["ready"], r["dup"]), (5, 0))                     # 同一句题干的图形题、同材料的资料题都不算重复
        self.assertEqual(len(bank.read(self.p, "图形推理")[0]), 3)
        r = importer.commit(self.p, {"kind": "season", "season": 36})
        self.assertEqual((r["ready"], r["dup"]), (0, 5))                     # 真重复仍然跳过

    def test_logic_book_board_by_options_and_digit_stems(self):
        self.assertEqual(importer.board_by_options({"A": "栖霞镇", "B": "莲花镇", "C": "五溪镇", "D": "花石镇"}), "形式逻辑")
        self.assertEqual(importer.board_by_options({"A": "甲", "B": "乙", "C": "丙", "D": "丁"}), "形式逻辑")
        self.assertEqual(importer.board_by_options({
            "A": "最新调查显示，智商相对较低的孩子大多数经常被家长打屁股", "B": "本身不听话且更容易惹祸的孩子更有可能受到父母的严厉惩罚",
            "C": "研究报告称全球大约80%的父母都有以打屁股管教孩子的经历", "D": "被打屁股而困惑的孩子只懂得按家长要求去做而不会独立思考"}), "论证逻辑")
        text = ("练习题01\n1.某研究认为甲导致乙。以下哪项如果为真，最能削弱上述结论：\nA。选项一 B.选项二 C．选项三 D。选项四\n"
                "2：2008年以来，某市房价上涨。\nA。甲选红石村 B.乙选青山村 C．丙选绿水村 D。丁选黄叶村\n")   # 第 2 题题干以数字开头、问句没 OCR 出来
        qs = importer._collect(self.p, {"kind": "text", "text": text, "prefix": "书", "no_source": True})[0]
        self.assertEqual([(q["id"], q["board"]) for q in qs], [("书-01-01", "论证逻辑"), ("书-01-02", "形式逻辑")])

    def test_ocr_symbols_restored_and_bank_normalized(self):
        stem, opts, probs = importer.fix_symbols(
            "可推出以下哪项结论： I：甲。Ⅱ：乙。 III。丙。", {"A": "仅I", "B": "I和H", "C": "II, III", "D": "I、I和II都推不出"})
        self.assertEqual(stem, "可推出以下哪项结论： Ⅰ：甲。Ⅱ：乙。 Ⅲ。丙。")
        self.assertEqual(opts, {"A": "仅Ⅰ", "B": "Ⅰ和Ⅱ", "C": "Ⅱ、Ⅲ", "D": "Ⅰ、Ⅰ和Ⅱ都推不出"})
        self.assertEqual(len(probs), 1)                                                   # Ⅰ、Ⅰ 重复 → 人工核对
        stem, opts, probs = importer.fix_symbols("③乙 4丁 由此可以推出：", {"A": "@②4", "B": "②34", "C": "1号和2号", "D": "③"})
        self.assertEqual((stem, opts), ("③乙 ④丁 由此可以推出：", {"A": "①②④", "B": "②③④", "C": "1号和2号", "D": "③"}))
        stem, opts, probs = importer.split_options("某研究对A型血的人进行调查。以下哪项最能削弱：A。甲 B.乙 C．丙 D。丁", False)
        self.assertEqual((stem[-7:], opts["A"]), ("哪项最能削弱：", "甲"))                 # 题干里的“A型”不当选项
        f = self.p.train / "题库/形式逻辑真题.md"
        f.write_text("\n## 题目 书-01-01\n### 知识点\n真假推理\n### 题干\n断言：I：甲。II：乙。\n### 选项\nA．仅I\nB、仅II\nC. I和II\nD：都不对\n"
                     "### 答案\nC\n### 解析\n（待补）\n", encoding="utf-8")
        r = importer.normalize_bank(self.p, {})
        self.assertEqual(r["changed"], 1)
        q = bank.read(self.p, "形式逻辑")[0][0]
        self.assertEqual((q["stem"], q["options"], q["answer"]), ("断言：Ⅰ：甲。Ⅱ：乙。", {"A": "仅Ⅰ", "B": "仅Ⅱ", "C": "Ⅰ和Ⅱ", "D": "都不对"}, "C"))
        self.assertIn("A. 仅Ⅰ\nB. 仅Ⅱ\nC. Ⅰ和Ⅱ\nD. 都不对", f.read_text(encoding="utf-8"))   # 选项标点统一

    def test_prefix_clash_rename_and_verbal_book(self):
        q = lambda n, kind: ("%d.某研究认为甲导致乙（样本%d）。以下哪项如果为真，最能削弱上述结论：\nA。选项一 B.选项二 C．选项三 D。选项四\n" % (n, n)
                             if kind == "逻辑" else "%d.科学研究需要____的态度（第%d题）。依次填入画横线部分最恰当的一项是：\nA．严谨 B．推敲 C．斟酌 D．周密\n" % (n, n))
        logic = "练习题01\n" + q(1, "逻辑") + q(2, "逻辑") + q(3, "逻辑")
        verbal = "练习题01\n" + q(1, "言语") + q(2, "言语") + q(3, "言语")
        importer.commit(self.p, {"kind": "text", "text": logic, "prefix": "花生", "no_source": True})
        with self.assertRaises(importer.ImportError_):     # 同前缀导另一本书：拒绝，不写入
            importer.commit(self.p, {"kind": "text", "text": verbal, "prefix": "花生", "no_source": True})
        self.assertEqual(bank.read_all(self.p, "逻辑填空")[0], [])
        state = {"bank": {"records": {"论证逻辑::花生-01-01": {"question": {"id": "花生-01-01", "board": "论证逻辑", "key": "论证逻辑::花生-01-01"},
                                                              "history": [{"ok": True}], "wrong": False, "streak": 1}},
                          "runs": {}, "groups": [{"board": "论证逻辑", "ids": ["花生-01-01"]}]}}
        r = importer.rename_prefix(self.p, {"old": "花生", "new": "花生逻辑", "boards": ["论证逻辑"]}, state)
        self.assertEqual((r["renamed"], r["records"]), (3, 1))
        self.assertEqual([x["id"] for x in bank.read_all(self.p, "论证逻辑")[0]][:1], ["花生逻辑-01-01"])
        self.assertIn("论证逻辑::花生逻辑-01-01", state["bank"]["records"])                 # 作答记录跟着改
        self.assertEqual(state["bank"]["groups"][0]["ids"], ["花生逻辑-01-01"])
        with self.assertRaises(importer.ImportError_):
            importer.rename_prefix(self.p, {"old": "x", "new": "花生逻辑"}, state)          # 新前缀已被占用
        r = importer.commit(self.p, {"kind": "text", "text": verbal, "prefix": "花生言语", "no_source": True})
        self.assertEqual([(x["id"], x["board"]) for x in bank.read_all(self.p, "逻辑填空")[0]],
                         [("花生言语-01-01", "逻辑填空"), ("花生言语-01-02", "逻辑填空"), ("花生言语-01-03", "逻辑填空")])

    def test_empty_option_line_does_not_swallow_next(self):
        self.assertEqual(importer.parse_opts("A. 甲\nB. 乙\nC. \nD. 丁"), {"A": "甲", "B": "乙", "C": "", "D": "丁"})

    def test_ai_classify_only_touches_unsorted_topics(self):
        importer.commit(self.p, {"kind": "season", "season": 36})
        self.assertEqual(importer.status(self.p)["unsorted"], 2)

        def fake(msgs, **kw):
            ids = [ln[1:ln.index("]")] for ln in msgs[-1]["content"].splitlines() if ln.startswith("[")]
            return {"items": [{"id": i, "板块": "资料分析", "知识点": "现期量"} for i in ids]}

        with patch.object(ai, "available", return_value=True), patch.object(ai, "chat_json", side_effect=fake) as m:
            r = importer.classify(self.p, 100)
        self.assertNotIn("A. 100", m.call_args[0][0][-1]["content"])           # 只发题干，不发选项答案
        self.assertEqual((r["done"], r["left"]), (2, 0))
        self.assertEqual({q["topic"] for q in bank.read(self.p, "资料分析")[0]}, {"现期量"})

    def test_text_pdf_keeps_blanks(self):
        try:
            import pymupdf
        except ImportError:
            self.skipTest("没装 pymupdf")
        import base64
        doc = pymupdf.open(); pg = doc.new_page()
        y = 60
        for ln in ["拔高刷题十一", "1．这项改革", "依次填入画横线部分最恰当的一项是：", "A．遏止  恩威并施", "B．遏制  宽严相济",
                   "C．阻止  软硬兼施", "D．制止  刚柔并济",
                   "拔高刷题十二", "1．这段文字意在说明：", "A．甲", "B．乙", "C．丙", "D．丁"]:
            pg.insert_text((50, y), ln, fontname="china-s", fontsize=11); y += 20
        pg.draw_line((112, 81), (170, 81), width=0.6)                     # 第 2 行“这项改革”后面画一道横线 = 空
        data = base64.b64encode(doc.tobytes()).decode()
        r = importer.commit(self.p, {"kind": "pdf", "data": data, "name": "言语.pdf", "no_source": True, "prefix": "言语刷题"})
        self.assertEqual(r["ready"], 2, r)
        q = bank.read_all(self.p, "逻辑填空")[0][0]
        self.assertEqual(q["id"], "言语刷题-11-01")
        self.assertIn("____", q["stem"])
        self.assertIn("遏止 恩威并施", q["options"]["A"])
        self.assertEqual(bank.read_all(self.p, "片段阅读")[0][0]["id"], "言语刷题-12-01")
        with self.assertRaises(importer.ImportError_):                     # 扫描件：没有文字层
            importer.preview(self.p, {"kind": "pdf", "data": base64.b64encode(_blank_pdf()).decode(), "name": "x.pdf"})


def _blank_pdf():
    import pymupdf
    d = pymupdf.open(); d.new_page()
    return d.tobytes()


if __name__ == "__main__":
    unittest.main()
