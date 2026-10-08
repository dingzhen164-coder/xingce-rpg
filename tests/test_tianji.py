"""🔮 天机简报（rpg/tianji.py）：用 pymupdf 现画一份小黑月半时政版式的 PDF，测拆分、填空答案、进度、做成玉简"""
import base64
import tempfile
import unittest
from pathlib import Path

from rpg import api, cards, paths, tianji

try:
    import pymupdf as fitz
except ImportError:          # 老版本 pymupdf
    try:
        import fitz
    except ImportError:
        fitz = None

HEAD = ["抖音关注公考小黑老师", "Hey，上岸吧！"]


def make_pdf(path, pages):
    """pages：[[(缩进?, 文字)…]…]，缩进的行左边距大（开新段），顶格的行接上一段"""
    doc = fitz.open()
    for lines in pages:
        pg = doc.new_page(width=595, height=842)
        pg.insert_text((92, 70), HEAD[1], fontname="china-s", fontsize=9)
        y = 110
        for ind, t in lines:
            pg.insert_text((112 if ind else 90, y), t, fontname="china-s", fontsize=10.5)
            y += 20
        pg.insert_text((92, 800), HEAD[0], fontname="china-s", fontsize=9)
    doc.save(str(path))


MONTH = [
    [(1, "2026 年全国公职考试笔试"), (1, "小黑月半时政班"), (1, "2026 年9 月·下")],
    [(1, "2026 年9 月下收录2 条新闻，其中两星级重要新闻共计1 条，题目共计2 题。")],
    [(1, "九月（下）时政·课程讲义"), (1, "1.★★【综合】【平陆运河正式通航】"),
     (1, "2026 年9 月16 日，平陆运河正式通航。平陆运河是广西境内沟通珠江流域西江与北部湾"),
     (0, "的运河，是西部陆海新通道骨干工程。"),
     (1, "1.【小黑时政】（单选）平陆运河正式通航。下列说法正确的是："),
     (1, "A.连接长江"), (1, "B.沟通珠江流域西江与北部湾"), (1, "C.在云南"), (1, "D.通航能力最弱"),
     (1, "2.★【会议】【国务院常务会议】"), (1, "国务院召开全国安全生产视频会议，坚持人民至上、生命至上。"),
     (1, "2.【小黑时政】（单选）会议强调要坚持："), (1, "A.效率至上"), (1, "B.人民至上、生命至上"), (1, "C.速度至上"), (1, "D.利润至上")],
    [(1, "九月（下）时政·消化清单"), (1, "1.★★【综合】【平陆运河正式通航】"),
     (1, "平陆运河是广西境内沟通________流域西江与________的运河，是西部陆海新通道骨干工程。")],
    [(1, "九月（下）时政·小黑金卷"),
     (1, "1.【小黑时政】（单选）平陆运河正式通航。下列说法正确的是："),
     (1, "A.连接长江"), (1, "B.沟通珠江流域西江与北部湾"), (1, "C.在云南"), (1, "D.通航能力最弱"),
     (1, "2.【小黑时政】（单选）会议强调要坚持："), (1, "A.效率至上"), (1, "B.人民至上、生命至上"), (1, "C.速度至上"), (1, "D.利润至上")],
    [(1, "九月（下）时政·小黑金卷·答案与解析"), (1, "1.【答案】B。解析：平陆运河沟通珠江流域西江与北部湾。"),
     (0, "故本题答案为B。"), (1, "2.【答案】B。解析：坚持人民至上、生命至上。")],
]
TOPIC = [
    [(1, "小黑月半时政班"), (1, "2026 年“两会”及政府工作报告"), (1, "专题")],
    [(1, "2026 年“两会”及政府工作报告·小黑母题"), (1, "【2026 年政府工作报告】"),
     (1, "1.【小黑时政】（单选）2026 年3 月5 日，政府工作报告提出，今年发展主要预期目标是："),
     (1, "A.增长5%左右"), (1, "B.增长8%"), (1, "C.增长3%"), (1, "D.不设目标"),
     (1, "【原文速递】"), (1, "今年发展主要预期目标是：国内生产总值增长5%左右；城镇新增就业1200万人以上。")],
    [(1, "2026 年“两会”及政府工作报告·消化清单"), (1, "【2026 年政府工作报告】"),
     (1, "1.国内生产总值增长________左右；城镇新增就业________万人以上。")],
    [(1, "2026 年“两会”及政府工作报告·小黑母题·答案与解析"), (1, "【2026 年政府工作报告】"), (1, "1.【答案】A。解析：增长5%左右。")],
]


@unittest.skipIf(fitz is None, "没有 pymupdf")
class TianjiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self.tmp.name)
        (self.vault / "copilot/skills").mkdir(parents=True)
        self._settings = paths.SETTINGS_FILE, paths.SETTINGS_DIR
        paths.SETTINGS_DIR = self.vault / ".home"
        paths.SETTINGS_FILE = paths.SETTINGS_DIR / "settings.json"
        paths.save_settings({"vault": str(self.vault)})
        cards._CACHE["key"] = None
        self.month = self.vault / "m.pdf"
        self.topic = self.vault / "t.pdf"
        make_pdf(self.month, MONTH)
        make_pdf(self.topic, TOPIC)

    def tearDown(self):
        paths.SETTINGS_FILE, paths.SETTINGS_DIR = self._settings
        self.tmp.cleanup()

    def test_parse_month(self):
        d = tianji.parse_pdf(self.month)
        self.assertEqual((d["kind"], d["id"], d["title"]), ("month", "2026-09-下", "2026年9月·下"))
        self.assertIn("收录2条新闻", d["overview"])
        self.assertEqual([n["title"] for n in d["news"]], ["平陆运河正式通航", "国务院常务会议"])
        self.assertEqual(d["news"][0]["stars"], 2)
        self.assertIn("西部陆海新通道骨干工程", d["news"][0]["paras"][0])       # 顶格的行接上一段
        self.assertTrue(all("【小黑时政】" not in p for n in d["news"] for p in n["paras"]))   # 随堂题不混进正文
        self.assertEqual([q["answer"] for q in d["questions"]], ["B", "B"])
        self.assertEqual(d["news"][0]["qs"], [0])
        self.assertEqual(d["news"][1]["qs"], [1])
        self.assertIn("故本题答案为B", d["questions"][0]["analysis"])
        self.assertEqual([p["a"] for p in d["cloze"][0]["parts"] if "a" in p], ["珠江", "北部湾"])

    def test_parse_topic(self):
        d = tianji.parse_pdf(self.topic)
        self.assertEqual(d["kind"], "topic")
        self.assertEqual(d["title"], "2026年“两会”及政府工作报告")
        self.assertEqual(d["category"], "两会·政府报告")
        self.assertEqual(d["groups"], ["2026年政府工作报告"])
        self.assertEqual(d["questions"][0]["answer"], "A")
        self.assertIn("1200万人以上", d["news"][0]["paras"][0])
        self.assertEqual([p["a"] for p in d["cloze"][0]["parts"] if "a" in p], ["5%", "1200"])

    def test_import_progress_cards(self):
        data = "data:application/pdf;base64," + base64.b64encode(self.month.read_bytes()).decode()
        r = api.tj_import({"data": data})
        self.assertEqual((r["kind"], r["id"], r["found"], r["blanks"], r["questions"]), ("month", "2026-09-下", 2, 2, 2))
        self.assertTrue((self.vault / "训练/天机简报/月半时政/2026-09-下.json").is_file())
        self.assertTrue((self.vault / "训练/天机简报/原文/月半时政-2026-09-下.pdf").is_file())
        api.tj_import({"data": base64.b64encode(self.topic.read_bytes()).decode()})
        ls = api.tj_list({})
        self.assertEqual([x["id"] for x in ls["month"]], ["2026-09-下"])
        self.assertEqual(ls["topic"][0]["category"], "两会·政府报告")
        k = dict(kind="month", id="2026-09-下")
        api.tj_get(k)
        api.tj_mark(dict(k, read=0))
        api.tj_mark(dict(k, cloze="0-1", ok=1))
        api.tj_mark(dict(k, cloze="0-3", ok=0))
        r = api.tj_mark(dict(k, quiz=0, choice="B"))
        self.assertTrue(r["progress"]["quiz"]["0"]["ok"])
        self.assertTrue(r["events"])                       # 第一次答发修为
        self.assertFalse(api.tj_mark(dict(k, quiz=0, choice="A"))["events"])
        st = r["stat"]
        self.assertEqual((st["read"], st["seen"], st["forgot"], st["done"]), (1, 2, 1, 1))
        self.assertEqual(api.tj_cards(k)["added"], 1)
        self.assertEqual(api.tj_cards(k)["added"], 0)       # 不重复做
        md = (self.vault / "训练/卡片").glob("*.md")
        self.assertTrue(any("{{c1::北部湾}}" in f.read_text(encoding="utf-8") for f in md))
        hb = api.heartbeat({"seconds": 60, "tianji": "read"})
        self.assertTrue(hb["studying"])
        self.assertEqual(hb["minutes"], 1)
        api.tj_meta({"kind": "topic", "id": ls["topic"][0]["id"], "category": "经济"})
        self.assertEqual(api.tj_list({})["topic"][0]["category"], "经济")
        api.tj_delete(k)
        self.assertEqual(api.tj_list({})["month"], [])
        with self.assertRaises(api.ApiError):
            api.tj_import({"data": base64.b64encode(b"hello").decode()})


if __name__ == "__main__":
    unittest.main()
