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


if __name__ == "__main__":
    unittest.main()
