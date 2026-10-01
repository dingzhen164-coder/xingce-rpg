"""历年真题库转换 + 按卷子整套试炼。"""
import datetime as dt
import tempfile
import unittest
from pathlib import Path

from rpg import config, engine, paths, question_bank as bank, store, trainer, zhenti

NOTE = '''---
类型: "真题"
qid: "%(qid)s"
试卷: "%(paper)s"
地区: "江苏"
年份: "%(year)s"
考点: "%(point)s"
---

# 标题

**问法模型**：问法%(qid)s

## 推理链
1. 第1步：推理%(qid)s

**最快解法**：⚡ 快%(qid)s

## 易错点
- ⚠ 易错%(qid)s

## 母题抽象
> 🧩 母题%(qid)s

**同类特征**：不要

## 相关题
- 不要

---

### 题干
<p>题干%(qid)s</p>%(img)s

### 选项
- A. 甲
- B. 乙　✅
- C. 丙
- D. 丁

### 官方解析
官方%(qid)s

### 给定材料
（无）
'''


class ZhentiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name) / 'repo' / '10-真题' / '判断推理'
        paper = '2021年江苏省公务员录用考试《行测》题（B类）（网友回忆版）'
        for kind, qid, point, img in [
                ('逻辑判断', '30', '逻辑判断 / 翻译推理-假设法代入', ''),
                ('逻辑判断', '10', '逻辑判断 / 削弱论证-因果倒置', ''),
                ('逻辑判断', '11', '逻辑判断 / 平行结构-论证方式', ''),
                ('图形推理', '20', '图形推理 / 数量规律', '<p><img width="1" src="../../../90-图片/题目图/x.png" /></p>'),
                ('科学推理', '40', '科学推理 / 力学', '')]:
            (root / kind).mkdir(parents=True, exist_ok=True)
            (root / kind / ('%s 题.md' % qid)).write_text(
                NOTE % dict(qid=qid, paper=paper, year='2021', point=point, img=img), encoding='utf-8')
        self.out = Path(self.tmp.name) / 'vault'
        (self.out / 'copilot/skills').mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()
        trainer.SESSIONS.clear()

    def test_convert_and_paper_set(self):
        r = zhenti.convert(Path(self.tmp.name) / 'repo', self.out / '训练')
        self.assertEqual(r['boards'], {'形式逻辑': 2, '论证逻辑': 1, '图形推理': 1, '常识判断': 1})
        self.assertEqual(r['images'], 1)
        text = (self.out / '训练/题库/图形推理真题-历年.md').read_text(encoding='utf-8')
        self.assertIn('（2021年江苏省B类）题干20', text)
        self.assertIn('![[训练/题库/图片/真题库/题目图/x.png]]', text)
        self.assertIn('题目图\\x.png', (self.out / '训练/题库/图片/真题库/图片清单.txt').read_text(encoding='utf-8-sig'))
        p = paths.Paths(self.out)
        p.ensure_train_dir()
        g = engine.Game(p, config.Rules(), config.Persona(), config.Lines(), store.new_state(dt.date(2026, 10, 1)), dt.date(2026, 10, 1))
        q = bank.read(p, '论证逻辑')[0][0]
        self.assertEqual((q['id'], q['answer'], q['paper'][:7]), ('真题-10', 'B', '2021年江苏'))
        for k in ('【官方解析】\n官方10', '【推理链】\n第1步', '【最快解法】\n⚡ 快10', '【易错点】', '【母题抽象】\n🧩 母题10'):
            self.assertIn(k, q['analysis'])
        self.assertNotIn('同类特征', q['analysis'])
        books = bank.summary(g)['sets']
        self.assertEqual((books[0]['book'], books[0]['sets'][0]['total']), ('历年真题', 5))
        # 卷子里的顺序：图形 → 逻辑（按题号） → 科学推理；题干里不出现知识点和解析
        r = trainer.start(g, {'type': 'bank', 'board': '套:' + books[0]['next'], 'title': '卷', 'target': ''})
        self.assertIn('编号 真题-20', str(r))
        self.assertNotIn('官方20', str(r))
        self.assertNotIn('数量规律', str(r))
        order = [x['id'] for x in bank.state(g)['runs']['套:' + books[0]['next']]['questions']]
        self.assertEqual(order, ['真题-20', '真题-10', '真题-11', '真题-30', '真题-40'])
        r = trainer.action(g, r['session'], 'bank_answer:0:B')
        self.assertIn('官方20', str(r))


if __name__ == '__main__':
    unittest.main()
