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
%(doubt)s
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
                NOTE % dict(qid=qid, paper=paper, year='2021', point=point, img=img,
                            doubt='\n> [!warning] 疑点（待复核）\n> 解析少一句' if qid == '30' else ''), encoding='utf-8')
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
        q30 = next(x for x in bank.read(p, '形式逻辑')[0] if x['id'] == '真题-30')
        self.assertNotIn('疑点', q30['stem'])                       # 疑点是对解析的复核，不当材料
        self.assertIn('【疑点】\n疑点（待复核）\n解析少一句', q30['analysis'])
        self.assertNotIn('（无）', q30['stem'])
        books = bank.summary(g)['sets']
        self.assertEqual((books[0]['book'], books[0]['sets'][0]['total']), ('历年真题·判断推理', 5))
        # 卷子里的顺序：图形 → 逻辑（按题号） → 科学推理；题干里不出现知识点和解析
        r = trainer.start(g, {'type': 'bank', 'board': '套:' + books[0]['next'], 'title': '卷', 'target': ''})
        self.assertIn('编号 真题-20', str(r))
        self.assertNotIn('官方20', str(r))
        self.assertNotIn('数量规律', str(r))
        order = [x['id'] for x in bank.state(g)['runs']['套:' + books[0]['next']]['questions']]
        self.assertEqual(order, ['真题-20', '真题-10', '真题-11', '真题-30', '真题-40'])
        for i in range(5):
            r = trainer.action(g, r['session'], 'exam_pick:%d:B' % i)
        r = trainer.action(g, r['session'], 'exam_submit')
        self.assertIn('正确率 100.0%', str(r))
        self.assertIn('官方20', str(r))


RAW = """---
类型: "真题"
试卷: "%(paper)s"
年份: "2020"
模块: "言语理解与表达"
---

# 卷

## 第 %(n1)d 题　<sub>qid 501 · 逻辑填空</sub>

<p>他一直在        中前行。</p>
填入画横线部分最恰当的一项是：

- **A**. 逆境
- **B**. 竞争
- **C**. 矛盾　✅
- **D**. 挑战

**答案**：C

**官方解析**

解析501，公式<img src="../90-图片/公式图/f.png" />如此。

---

## 材料 1

<p>一段材料。</p>

### 第 %(n2)d 题　<sub>qid 502 · 片段阅读</sub>

这段文字意在说明：

- **A**. 甲　✅
- **B**. 乙
- **C**. 丙
- **D**. 丁

**答案**：A

**官方解析**

解析502

---

## 第 9 题　<sub>qid 503 · 片段阅读</sub>

多选题

- **A**. 甲　✅
- **B**. 乙　✅
- **C**. 丙
- **D**. 丁

**答案**：AB

**官方解析**

无
"""


class RawTest(unittest.TestCase):
    def test_raw_shared_questions_and_blanks(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / 'raw'
            (src / '03-言语理解与表达').mkdir(parents=True)
            (src / '90-图片/公式图').mkdir(parents=True)
            (src / '90-图片/公式图/f.png').write_bytes(b'png')
            for name, n1, n2 in (('2020年安徽省公务员录用考试《行测》试题（网友回忆版）', 1, 2),
                                 ('2020年山西省公务员录用考试《行测》试题（网友回忆版）', 7, 3)):
                (src / '03-言语理解与表达' / (name + '.md')).write_text(RAW % dict(paper=name, n1=n1, n2=n2), encoding='utf-8')
            out = Path(d) / 'vault'
            (out / 'copilot/skills').mkdir(parents=True)
            r = zhenti.convert_raw(src, out / '训练')
            self.assertEqual((r['total'], r['skipped']), (2, {'多选题': 2, '几张卷子共用': 2}))
            self.assertTrue((out / '训练/题库/图片/真题库/公式图/f.png').is_file())
            p = paths.Paths(out)
            q = bank.read(p, '逻辑填空')[0][0]
            self.assertIn('（2020年安徽省等2卷）他一直在____中前行。', q['stem'])
            self.assertIn('解析501，公式![[训练/题库/图片/真题库/公式图/f.png]]如此。', q['analysis'])
            self.assertEqual((q['nums'], len(q['papers'])), ([1, 7], 2))
            self.assertIn('一段材料。', bank.read(p, '片段阅读')[0][0]['stem'])
            g = engine.Game(p, config.Rules(), config.Persona(), config.Lines(),
                            store.new_state(dt.date(2026, 10, 1)), dt.date(2026, 10, 1))
            books = bank.summary(g)['sets']
            self.assertEqual([(b['book'], len(b['sets'])) for b in books], [('历年真题·言语理解与表达', 2)])
            # 山西卷里材料题是第 3 题、填空是第 7 题：按这张卷子的题号排
            name = next(x['name'] for x in books[0]['sets'] if '山西' in x['name'])
            self.assertEqual([x['id'] for x in bank._set_questions(g, name)[0]], ['真题-502', '真题-501'])
            # 行内公式图留在文字里，网页上按小图显示
            self.assertEqual([b['t'] for b in trainer._bank_blocks(g, '逻辑填空', q['analysis'])], ['text'])


    def test_material_only_covers_its_questions(self):
        def q(n, stem):
            return ('### 第 %d 题　<sub>qid %d · 片段阅读</sub>\n\n%s\n\n- **A**. 甲　✅\n- **B**. 乙\n- **C**. 丙\n- **D**. 丁\n\n'
                    '**答案**：A\n\n**官方解析**\n\n无\n\n---\n\n' % (n, 900 + n, stem))
        long_ = '“致天下之治者在人才。”在当今人才竞争日趋激烈的背景下，如何网罗天下英才为我所用？如何让专家人才地贡献才智、施展才华、创新创业？' * 2
        t = ('---\n试卷: "卷"\n年份: "2020"\n---\n\n## 材料 1\n\n①一段关于算法的材料。\n\n'
             + q(1, '这段文字意在说明：') + q(2, long_) + '## 材料 2\n\n第二段材料。\n\n'
             + ''.join(q(k, '根据材料，下列说法正确的是：') for k in range(3, 9)))
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'x.md'
            f.write_text(t, encoding='utf-8')
            got = {x['num']: x['stem'] for x in zhenti.parse_raw(f, '言语理解与表达')}
        self.assertIn('算法的材料', got[1])
        self.assertNotIn('算法的材料', got[2])            # 自带一大段、不提材料：独立题
        self.assertTrue(all('第二段材料' in got[k] for k in range(3, 8)))
        self.assertNotIn('第二段材料', got[8])           # 一段材料最多管 5 道

    def test_ziliao_papers_with_distilled_notes(self):
        """资料分析：整张卷子按题号成套，材料管它下面所有题（可多于 5 道），蒸馏笔记按 qid 补进解析、知识点用蒸馏的大类"""
        def q(n, stem, ans='A'):
            return ('### 第 %d 题　<sub>qid %d · 综合</sub>\n\n%s\n\n- **A**. 1　%s\n- **B**. 2\n- **C**. 3\n- **D**. 4\n\n'
                    '**答案**：%s\n\n**官方解析**\n\n官方%d\n\n---\n\n' % (n, 700 + n, stem, '✅' if ans == 'A' else '', ans, n))
        with tempfile.TemporaryDirectory() as d:
            raw, kg = Path(d) / 'raw', Path(d) / 'kg'
            (raw / '06-资料分析').mkdir(parents=True)
            (raw / '90-图片/题目图').mkdir(parents=True)
            (raw / '90-图片/题目图/t.png').write_bytes(b'png')
            paper = '2024年国家公务员录用考试《行测》题（副省级）'
            (raw / '06-资料分析' / (paper + '.md')).write_text(
                '---\n试卷: "%s"\n年份: "2024"\n模块: "资料分析"\n---\n\n## 材料 1\n\n<p>2023年某市产值100亿元。</p>'
                '<p><img src="../90-图片/题目图/t.png" /></p>\n\n' % paper
                + ''.join(q(k, '第%d问：<p>求</p><p>多少？</p>' % k) for k in range(1, 8)), encoding='utf-8')
            note = kg / '10-真题/资料分析/增长'
            note.mkdir(parents=True)
            (note / '701 增长量.md').write_text((NOTE % dict(qid='701', paper=paper, year='2024', point='增长 / 增长量计算', img='', doubt=''))
                                              .replace('# 标题\n', '# 标题\n\n材料：[[15-材料/资料分析/55 某市|55]]\n'), encoding='utf-8')
            (kg / '15-材料/资料分析').mkdir(parents=True)
            (kg / '15-材料/资料分析/55 某市.md').write_text('---\nmid: "55"\n---\n\n## 阅读陷阱\n- ⚠ 单位是亿元\n', encoding='utf-8')
            out = Path(d) / 'vault'
            (out / 'copilot/skills').mkdir(parents=True)
            r = zhenti.convert_ziliao(raw, kg, out / '训练')
            self.assertEqual((r['total'], r['distilled'], r['missing_count']), (7, 1, 0))
            p = paths.Paths(out)
            qs = {x['id']: x for x in bank.read(p, '资料分析')[0]}
            self.assertEqual(len(qs), 7)
            self.assertTrue(all('某市产值' in x['stem'] for x in qs.values()))      # 7 道都挂着材料
            mat, stem = trainer.split_stem('资料分析', qs['真题-707']['stem'])
            self.assertIn('题目图/t.png', mat)
            self.assertEqual(stem, '第7问：求\n多少？')                             # 问题自己不留空行，网页才拆得对
            a = qs['真题-701']
            self.assertEqual(a['topic'], '增长')
            for part in ('【官方解析】\n官方1', '【考点】\n增长量计算', '【推理链】', '【材料陷阱】\n⚠ 单位是亿元'):
                self.assertIn(part, a['analysis'])
            self.assertEqual(qs['真题-702']['topic'], '综合')
            g = engine.Game(p, config.Rules(), config.Persona(), config.Lines(),
                            store.new_state(dt.date(2026, 10, 1)), dt.date(2026, 10, 1))
            books = bank.sets(g)
            self.assertEqual([(b['book'], len(b['sets']), b['sets'][0]['total']) for b in books], [('历年真题·资料分析', 1, 7)])
            self.assertEqual([x['id'] for x in bank._set_questions(g, books[0]['sets'][0]['name'])[0]],
                             ['真题-%d' % (700 + k) for k in range(1, 8)])

    def test_chart_after_source_tag_is_a_block(self):
        """材料只有一张表：来源括号和图在同一行，图也要整张显示，不能当成行内公式小图"""
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            (out / 'copilot/skills').mkdir(parents=True)
            p = paths.Paths(out)
            p.ensure_train_dir()
            for rel in ('题目图/t.png', '公式图/f.png'):
                f = p.train / '题库/图片/真题库' / rel
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_bytes(b'png')
            g = engine.Game(p, config.Rules(), config.Persona(), config.Lines(),
                            store.new_state(dt.date(2026, 10, 1)), dt.date(2026, 10, 1))
            img = '![[训练/题库/图片/真题库/%s]]'
            got = trainer._bank_blocks(g, '资料分析', '（2026年云南省等3卷）' + img % '题目图/t.png')
            self.assertEqual([b['t'] for b in got], ['text', 'img'])
            got = trainer._bank_blocks(g, '资料分析', '同比增长' + img % '公式图/f.png' + '，较上年')
            self.assertEqual([b['t'] for b in got], ['text'])              # 公式图仍留在句子里

    def test_fix_leaked_material_in_old_bank(self):
        good = '“致天下之治者在人才。”如何让专家人才____地贡献才智？\n填入画横线部分最恰当的一项是'
        table = {'2453277': [len(good), zhenti._fp(good)], '1': [len(good), zhenti._fp(good)]}
        blk = lambda qid, stem: '## 题目 真题-%s\n### 知识点\n逻辑填空\n### 题干\n%s\n### 选项\nA. 甲\nB. 乙\nC. 丙\nD. 丁\n### 答案\nA\n### 解析\n原解析\n\n' % (qid, stem)
        src = '（2020年北京市公务员录用考试（乡镇卷）题（网友回忆版））'
        with tempfile.TemporaryDirectory() as d:
            p = paths.Paths(Path(d))
            (p.train / '题库').mkdir(parents=True)
            fx = Path(d) / 'fix.json'
            fx.write_text(__import__('json').dumps(table), encoding='utf-8')
            old, zhenti.FIX_FILE = zhenti.FIX_FILE, fx
            try:
                f = p.train / '题库' / '逻辑填空真题-2020.md'
                f.write_text('# 头\n\n' + blk('2453277', src + '①算法材料。\n②更多。\n\n' + good)
                             + blk('1', '我自己改过的' + good + '！'), encoding='utf-8')
                r = zhenti.fix_material_leak(p)
                self.assertEqual((r['fixed'], r['files']), (1, ['逻辑填空真题-2020.md']))
                text = f.read_text(encoding='utf-8')
                self.assertIn('### 题干\n' + src + good + '\n### 选项', text)
                self.assertNotIn('算法材料', text)
                self.assertIn('我自己改过的', text)          # 指纹对不上的不动
                self.assertTrue(zhenti.fix_material_leak(p).get('done_before'))
                state = {'bank': {'records': {'逻辑填空::真题-2453277': {'question': {'id': '真题-2453277', 'stem': src + '材料\n\n' + good}}},
                                  'runs': {}}}
                self.assertEqual(zhenti.fix_material_state(state), 1)
                self.assertEqual(state['bank']['records']['逻辑填空::真题-2453277']['question']['stem'], src + good)
            finally:
                zhenti.FIX_FILE = old


if __name__ == '__main__':
    unittest.main()


class MergeDistilledTest(unittest.TestCase):
    def test_merge_into_existing_bank(self):
        with tempfile.TemporaryDirectory() as d:
            train = Path(d) / '训练'
            (train / '题库').mkdir(parents=True)
            f = train / '题库/逻辑填空真题-2020.md'
            f.write_text('\n## 题目 真题-501\n### 知识点\n逻辑填空\n### 试卷\n卷\n### 题干\n他一直在____中前行。\n'
                         '### 选项\nA. 逆境\nB. 竞争\nC. 矛盾\nD. 挑战\n### 答案\nC\n### 解析\n官方解析501\n\n'
                         '## 题目 真题-502\n### 知识点\n逻辑填空\n### 题干\n别的题\n### 选项\nA. 甲\nB. 乙\nC. 丙\nD. 丁\n'
                         '### 答案\nA\n### 解析\n官方502\n', encoding='utf-8')
            notes = Path(d) / '蒸馏/10-真题/言语理解与表达/逻辑填空'
            notes.mkdir(parents=True)
            (Path(d) / '蒸馏/90-图片/公式图').mkdir(parents=True)
            (Path(d) / '蒸馏/90-图片/公式图/g.png').write_bytes(b'png')
            note = NOTE % dict(qid='501', paper='卷', year='2020', point='逻辑填空 / 实词辨析-语义侧重', img='', doubt='')
            note = note.replace('1. 第1步：推理501', '1. 第1步：推理501 <img src="../../../90-图片/公式图/g.png" />')
            (notes / '501 x.md').write_text(note, encoding='utf-8')
            r = zhenti.merge_distilled(train, Path(d) / '蒸馏/10-真题')
            self.assertEqual((r['notes'], r['merged'], r['topics'], r['files'], r['images_copied']),
                             (1, 1, 1, ['逻辑填空真题-2020.md'], 1))
            text = f.read_text(encoding='utf-8')
            self.assertIn('### 知识点\n实词辨析-语义侧重', text)
            self.assertIn('官方解析501\n\n【问法模型】\n问法501', text)
            self.assertIn('【推理链】\n第1步：推理501', text)
            self.assertIn('官方502\n', text)                                   # 没对上的题不动
            self.assertTrue((train / '题库/图片/真题库/公式图/g.png').is_file())
            self.assertEqual(zhenti.merge_distilled(train, Path(d) / '蒸馏')['files'], [])   # 再合并一次：不重复
            self.assertEqual(text.count('【推理链】'), f.read_text(encoding='utf-8').count('【推理链】'))
            with self.assertRaises(ValueError):
                zhenti.merge_distilled(train, Path(d) / '没有这个文件夹')


class TolerantNoteTest(unittest.TestCase):
    def test_variant_formats(self):
        with tempfile.TemporaryDirectory() as d:
            train = Path(d) / '训练'
            (train / '题库').mkdir(parents=True)
            blk = lambda i: ('\n## 题目 真题-%s\n### 知识点\n逻辑填空\n### 题干\n题%s____\n### 选项\nA. 甲\nB. 乙\nC. 丙\nD. 丁\n'
                             '### 答案\nA\n### 解析\n官方%s\n') % (i, i, i)
            (train / '题库/逻辑填空真题-2020.md').write_text(blk('1746638') + blk('17159') + blk('999'), encoding='utf-8')
            deep = Path(d) / 'vault-言语理解与表达/10-真题/言语理解与表达/逻辑填空/逻辑填空-成语辨析'
            deep.mkdir(parents=True)
            # 不带引号的 qid、别的小节名、考点写在正文里
            (deep / '1746638 逻辑填空-成语辨析.md').write_text(
                '---\nqid: 1746638\n考点: 逻辑填空 / 成语辨析-语义侧重\n---\n# 成语辨析\n\n'
                '**问法模型**：填入画横线部分最恰当 → 先找提示词\n\n## 解题思路\n1. 看前后文\n2. 比较侧重\n\n'
                '**秒杀技巧**：看感情色彩\n\n## 易错陷阱\n- 只看词义\n\n## 相关题\n- [[10-真题/x|x]]\n\n### 题干\n题\n', encoding='utf-8')
            # 没有 frontmatter，qid 只在文件名开头
            (deep / '17159 逻辑填空-成语辨析.md').write_text('# 标题\n考点：[[20-考点/逻辑填空/成语辨析|逻辑填空 / 成语辨析-搭配]]\n\n'
                                                         '## 推理链\n第1步：x\n\n## 母题抽象\n> 搭配优先\n', encoding='utf-8')
            (deep / '说明.md').write_text('# 只是说明\n', encoding='utf-8')
            r = zhenti.merge_distilled(train, Path(d) / 'vault-言语理解与表达')
            self.assertEqual((r['scanned'], r['notes'], r['merged'], r['topics'], r['skipped_no_qid']), (3, 2, 2, 2, 1))
            text = (train / '题库/逻辑填空真题-2020.md').read_text(encoding='utf-8')
            self.assertIn('### 知识点\n成语辨析-语义侧重', text)
            self.assertIn('官方1746638\n\n【问法模型】\n填入画横线部分最恰当 → 先找提示词\n\n【解题思路】\n看前后文\n比较侧重\n\n'
                          '【秒杀技巧】\n看感情色彩\n\n【易错陷阱】\n- 只看词义', text)
            self.assertNotIn('相关题', text)
            self.assertIn('### 知识点\n成语辨析-搭配', text)
            self.assertIn('【推理链】\n第1步：x\n\n【母题抽象】\n搭配优先', text)
            self.assertIn('官方999\n', text)


class CalloutNoteTest(unittest.TestCase):
    def test_answer_callout_format(self):
        """言语那批：蒸馏内容在 > [!success]- 点击查看答案与解析 折叠框里"""
        note = Path(__file__).with_name('fixtures') / '1746638 逻辑填空-成语辨析.md'
        with tempfile.TemporaryDirectory() as d:
            train = Path(d) / '训练'
            (train / '题库').mkdir(parents=True)
            (train / '题库/逻辑填空真题-2016.md').write_text(
                '\n## 题目 真题-1746638\n### 知识点\n逻辑填空\n### 题干\n题\n### 选项\nA. 一丝不苟\nB. 不遗余力\nC. 分毫不差\nD. 滴水不漏\n'
                '### 答案\nC\n### 解析\n官方解析原文\n【文段出处】《赢在执行》\n', encoding='utf-8')
            src = Path(d) / 'vault/10-真题/言语理解与表达/逻辑填空/逻辑填空-成语辨析'
            src.mkdir(parents=True)
            (src / note.name).write_text(note.read_text(encoding='utf-8'), encoding='utf-8')
            r = zhenti.merge_distilled(train, Path(d) / 'vault')
            self.assertEqual((r['notes'], r['merged'], r['skipped_no_parts']), (1, 1, 0))
            text = (train / '题库/逻辑填空真题-2016.md').read_text(encoding='utf-8')
            heads = [ln for ln in text.splitlines() if ln.startswith('【') and ln.endswith('】')]
            self.assertEqual(heads, ['【细化】', '【问法模型】', '【推理链】', '【最快解法】', '【易错点】',
                                     '【适用边界（什么时候不要用）】', '【易混考点辨析】', '【母题抽象】'])
            self.assertIn('官方解析原文\n【文段出处】《赢在执行》\n\n【细化】', text)
            for bad in ('正确答案', '相关题', '典型提问', '同类特征', '文段指出执行力'):
                self.assertNotIn(bad, text)
            self.assertIn('### 知识点\n逻辑填空-成语辨析', text)
            zhenti.merge_distilled(train, Path(d) / 'vault')                       # 再合并：不重复
            self.assertEqual((train / '题库/逻辑填空真题-2016.md').read_text(encoding='utf-8'), text)
