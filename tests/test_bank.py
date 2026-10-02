"""真题实战回归：顺序、答案保密、续做、重复提交、错题统计与旧存档兼容。"""
import datetime as dt
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from rpg import config, engine, paths, question_bank as bank, store, trainer


def question(ident, answer='A'):
    return ('\n## 题目 %s\n### 知识点\n削弱\n### 题干\n题干 %s\n'
            '### 选项\nA. 甲\nB. 乙\nC. 丙\nD. 丁\n### 答案\n%s\n### 解析\n秘密解析\n') % (ident, ident, answer)


def bank_action(g, sid, act):
    if act.startswith("bank_answer:"):
        _, pos, letter = act.split(":")
        run = bank.state(g)["runs"]["论证逻辑"]
        if pos != str(run["pos"]):
            raise trainer.TrainError("题目切换")
        return trainer.reply(g, sid, "方向：削弱。论据与结论需要建立联系，A排除其他解释，B/C/D无关。\n【答案】" + letter)
    return trainer.action(g, sid, act)


class BankTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.paths = paths.Paths(Path(self.tmp.name))
        self.paths.ensure_train_dir()
        self.day = dt.date(2026, 9, 30)
        self.g = engine.Game(self.paths, config.Rules(), config.Persona(), config.Lines(),
                             store.new_state(self.day), self.day)
        self.file = self.paths.train / '题库/论证逻辑真题.md'
        self.task = {'type': 'bank', 'board': '论证逻辑', 'title': '实战', 'target': '论证逻辑', 'id': 'bank:论证逻辑'}

    def tearDown(self):
        self.tmp.cleanup()
        trainer.SESSIONS.clear()

    def test_templates_empty_preserved_and_invalid_rejected(self):
        self.assertEqual(len(list((self.paths.train/'题库').glob('*.md'))), 12)
        self.assertEqual(bank.read(self.paths, '论证逻辑'), ([], []))
        self.file.write_text(question('01') + question('01'), encoding='utf-8')
        self.paths.ensure_train_dir()
        self.assertEqual(self.file.read_text(encoding='utf-8'), question('01') + question('01'))
        with self.assertRaises(trainer.TrainError):
            trainer.start(self.g, self.task)

    def test_order_resume_no_answer_leak_and_duplicate_submission(self):
        self.file.write_text(''.join(question(x) for x in ['20', '01'] + [str(x) for x in range(30, 42)]), encoding='utf-8')
        r = trainer.start(self.g, self.task)
        self.assertIn('编号 20', str(r))
        self.assertNotIn('秘密解析', str(r))
        self.assertNotIn('正确答案', str(r))
        sid = r['session']
        self.assertTrue(trainer.is_studying(sid))
        bank_action(self.g, sid, 'bank_answer:0:B')
        xp = self.g.state['xp']
        with self.assertRaises(trainer.TrainError):
            bank_action(self.g, sid, 'bank_answer:0:B')
        self.assertEqual(self.g.state['xp'], xp)
        store.Store(self.paths).save(self.g.state, self.day)
        trainer.SESSIONS.clear()
        self.g.state = store.Store(self.paths).load(self.day)
        r = trainer.start(self.g, self.task)
        self.assertIn('秘密解析', str(r))
        sid = r['session']
        r = bank_action(self.g, sid, 'bank_next')
        self.assertIn('编号 01', str(r))
        for pos in range(1, 10):
            bank_action(self.g, sid, 'bank_answer:%s:A' % pos)
            r = bank_action(self.g, sid, 'bank_next')
        self.assertTrue(r['finished'])
        stats = bank.summary(self.g)['boards'][0]
        self.assertEqual((stats['first_total'], stats['first_correct'], stats['wrong']), (10, 9, 1))
        self.assertIn('正确率 90.0%', str(r))
        r = trainer.start(self.g, self.task)
        self.assertIn('编号 38', str(r))
        self.assertEqual(len(bank.state(self.g)['runs']['论证逻辑']['questions']), 4)

    def test_wrong_review_snapshot_stats_and_no_extra_xp(self):
        self.file.write_text(question('1'), encoding='utf-8')
        r = trainer.start(self.g, self.task)
        bank_action(self.g, r['session'], 'bank_answer:0:B')
        bank_action(self.g, r['session'], 'bank_next')
        self.file.write_text('', encoding='utf-8')  # 原题删掉仍可按错题快照复练
        self.task['type'] = 'bank_review'
        xp = self.g.state['xp']
        for _ in range(2):
            r = trainer.start(self.g, self.task)
            bank_action(self.g, r['session'], 'bank_answer:0:A')
            bank_action(self.g, r['session'], 'bank_next')
        s = bank.summary(self.g)['boards'][0]
        self.assertEqual((s['first_correct'], s['first_total'], s['review_correct'], s['review_total'], s['wrong']), (0, 1, 2, 2, 0))
        self.assertEqual(self.g.state['xp'], xp)

    def test_plan_after_skeleton_and_old_state(self):
        self.file.write_text(question('1'), encoding='utf-8')
        tasks = [self.g._task('recite','论证逻辑','复习','test1'),
                 self.g._task('apply','论证逻辑','应用','test2')]
        self.g.state['plan'] = {'date': self.g.t, 'tasks': tasks}
        self.g.state.pop('bank')
        result = self.g.plan()['tasks']
        self.assertEqual([t['type'] for t in result], ['recite','apply','bank'])
        self.assertEqual(len(self.g.plan()['tasks']), 3)
        self.assertEqual(self.g.rules.num('每日目标分钟'), 300)   # 修炼 + 听道合计

    def test_trial_reward_once_and_theme_feedback(self):
        self.file.write_text(question('1'), encoding='utf-8')
        r = trainer.start(self.g, self.task)
        self.assertEqual(r['battle']['total'], 1)
        self.assertNotIn('秘密解析', str(r['battle']))
        bank_action(self.g, r['session'], 'bank_answer:0:A')
        r = bank_action(self.g, r['session'], 'bank_next')
        self.assertIn('破阵无伤', str(r))
        self.assertEqual(sum(e['type'] == 'bank_clear' for e in self.g.state['events']), 1)
        with self.assertRaises(trainer.TrainError):
            bank_action(self.g, r['session'], 'bank_next')
        self.g.state['theme'] = '玄幻'
        self.assertEqual(self.g.T('nav.bank'), '🗼 试炼塔')
        self.assertEqual(self.g.T('bank_rank.3'), '完美通关')
        self.assertEqual(bank.rank(self.g, 9, 10), 2)
        self.assertEqual(bank.rank(self.g, 7, 10), 1)
        self.assertEqual(bank.rank(self.g, 6, 10), 0)

    def test_old_partial_run_keeps_answers_without_retroactive_reward(self):
        self.file.write_text(question('1') + question('2'), encoding='utf-8')
        r = trainer.start(self.g, self.task)
        bank_action(self.g, r['session'], 'bank_answer:0:A')
        run = bank.state(self.g)['runs']['论证逻辑']
        run['results'][0].pop('first')  # 模拟上一版保存的作答，没有新奖励标记
        bank_action(self.g, r['session'], 'bank_next')
        bank_action(self.g, r['session'], 'bank_answer:1:A')
        bank_action(self.g, r['session'], 'bank_next')
        ev = next(e for e in self.g.state['events'] if e['type'] == 'bank_clear')
        self.assertEqual(ev['xp'], 15)  # 只奖励本组一半的新记录
        self.assertEqual(len(bank.state(self.g)['records']), 2)

    def test_tower_boundaries_and_old_records(self):
        def fill(n):
            bank.state(self.g)['records'] = {str(i): {'history': [{'ok': False}]} for i in range(n)}
        for n, cleared, current, remain in [(0,0,1,50),(49,0,1,1),(50,1,2,50),
                                           (51,1,2,49),(4999,99,100,1),(5000,100,100,0),(5001,100,100,0)]:
            fill(n)
            t = bank.tower(self.g)
            self.assertEqual((t['cleared'],t['current'],t['remaining']), (cleared,current,remain))
            self.assertEqual(t['summit'], n >= 5000)
        self.g.rules = config.Rules('- 试炼塔层数: 3\n- 试炼塔总题数: 10')
        fill(9)
        self.assertEqual(bank.tower(self.g)['cleared'],2)
        fill(10)
        self.assertTrue(bank.tower(self.g)['summit'])

    def test_tower_wrong_answer_climbs_once_and_review_does_not(self):
        # 跨板块首次作答共享进度，旧历史无需新 first 标记。
        bank.state(self.g)['records'] = {'旧板块::%s' % i: {'history': [{'ok': True}], 'question': {'board': '片段阅读'}, 'wrong': False} for i in range(49)}
        self.file.write_text(question('50'), encoding='utf-8')
        r = trainer.start(self.g, self.task)
        r = bank_action(self.g,r['session'],'bank_answer:0:B')
        self.assertEqual(r['battle']['tower']['cleared'],1)
        self.assertTrue(any('登上试炼塔第 1 层' in e.get('msg','') for e in r['events']))
        bank_action(self.g,r['session'],'bank_next')
        self.task['type'] = 'bank_review'
        r = trainer.start(self.g,self.task)
        r = bank_action(self.g,r['session'],'bank_answer:0:A')
        self.assertEqual(r['battle']['tower']['completed'],50)
        self.assertFalse(any('登上试炼塔' in e.get('msg','') for e in r['events']))

    def test_appended_questions_continue_without_numeric_sort(self):
        self.file.write_text(question('999'), encoding='utf-8')
        r = trainer.start(self.g, self.task)
        bank_action(self.g,r['session'],'bank_answer:0:A')
        bank_action(self.g,r['session'],'bank_next')
        self.file.write_text(question('999') + question('001'), encoding='utf-8')
        r = trainer.start(self.g,self.task)
        self.assertIn('编号 001',str(r))
        self.assertEqual(len(bank.state(self.g)['runs']['论证逻辑']['questions']),1)

    def test_reasoning_answer_field_no_leak_and_method_separate(self):
        from rpg import ai
        self.file.write_text(question("1"), encoding="utf-8")
        skill = self.paths.skills / "xue-rui-argument-logic"
        skill.mkdir(parents=True, exist_ok=True)
        (skill / "SKILL.md").write_text("判断底层结构与每个选项的作用", encoding="utf-8")
        r = trainer.start(self.g, self.task)
        self.assertEqual(r["input"]["mode"], "text")
        self.assertNotIn("秘密解析", str(r))
        with self.assertRaises(trainer.TrainError):
            trainer.reply(self.g, r["session"], "A是支持，D是无关")
        with self.assertRaises(trainer.TrainError):
            trainer.reply(self.g, r["session"], "【答案】A")
        self.assertFalse(bank.state(self.g)["records"])
        judgement = {"通过": True, "维度": {"方向": True, "结论论据": True, "结构": True, "选项分析": False}, "点评": "只报术语", "正确思路": "应落到具体词句"}
        with patch.object(ai, "available", return_value=True), patch.object(ai, "chat_json", return_value=judgement):
            result = trainer.reply(self.g, r["session"], "方向、论据结论、结构说清了，选项没有落地。D也是无关。\n【答案】A")
        record = bank.state(self.g)["records"]["论证逻辑::1"]
        self.assertTrue(record["history"][0]["ok"])
        self.assertFalse(record["history"][0]["method_ok"])
        self.assertTrue(record["wrong"])
        self.assertIn("未通过", str(result))
        self.assertEqual(bank.summary(self.g)["boards"][0]["method_total"], 1)
        with self.assertRaises(trainer.TrainError):
            trainer.reply(self.g, r["session"], "重复作答\n【答案】B")
        self.assertEqual(len(record["history"]), 1)

    def test_reasoning_ai_failure_keeps_question_unsubmitted(self):
        from rpg import ai
        self.file.write_text(question("1"), encoding="utf-8")
        r = trainer.start(self.g, self.task)
        with patch.object(ai, "available", return_value=True), patch.object(ai, "chat_json", side_effect=ai.AIError("超时")):
            with self.assertRaises(ai.AIError):
                trainer.reply(self.g, r["session"], "论据、结论与四个选项分析\n【答案】A")
        self.assertFalse(bank.state(self.g)["records"])
        self.assertEqual(bank.state(self.g)["runs"]["论证逻辑"]["phase"], "answer")


    def test_whole_set_across_boards(self):
        # 言语书一套 20 题分在两个板块；整套试炼按题号顺序一次做完，不受每轮 10 关限制
        fill = self.paths.train / '题库/逻辑填空真题.md'
        read = self.paths.train / '题库/片段阅读真题.md'
        fill.write_text(''.join(question('懒猫-01-%02d' % n) for n in range(1, 21, 2)) + question('懒猫-02-01'), encoding='utf-8')
        read.write_text(''.join(question('懒猫-01-%02d' % n) for n in range(2, 21, 2)), encoding='utf-8')
        sets = bank.summary(self.g)['sets']
        self.assertEqual([(b['book'], b['next'], len(b['sets'])) for b in sets], [('懒猫', '懒猫-01', 2)])
        self.assertEqual(sets[0]['sets'][0]['total'], 20)
        task = {'type': 'bank', 'board': '套:懒猫-01', 'title': '整套', 'target': '套:懒猫-01'}
        r = trainer.start(self.g, task)
        self.assertIn('懒猫 第01套 · 第 1/20 题 · 编号 懒猫-01-01', str(r))
        sid = r['session']
        for pos in range(20):
            r = trainer.action(self.g, sid, 'exam_pick:%s:%s' % (pos, 'A' if pos else 'B'))
            if pos == 0:
                self.assertIn('编号 懒猫-01-02', str(r))          # 选完自动翻页，不判对错
                self.assertNotIn('秘密解析', str(r))
        r = trainer.action(self.g, sid, 'exam_submit')
        self.assertIn('正确率 95.0%（19/20）', str(r))
        self.assertEqual(len([e for e in r['events'] if e['kind'] == 'xp']), 1)   # 修为合成一条
        r = trainer.action(self.g, sid, 'exam_close')
        self.assertTrue(r['finished'])
        self.assertIn('19/20', str(r))
        d = bank.summary(self.g)
        self.assertEqual(d['groups'][0]['label'], '懒猫 第01套')
        self.assertEqual(d['groups'][0]['boards'], ['片段阅读', '逻辑填空'])
        self.assertEqual(d['sets'][0]['next'], '懒猫-02')
        self.assertEqual(d['sets'][0]['finished'], 1)
        with self.assertRaises(trainer.TrainError):
            trainer.start(self.g, task)

    def test_exam_submit_review_explain(self):
        f = self.paths.train / '题库/类比推理真题.md'
        f.write_text(''.join(question(x) for x in ('01', '02', '03')), encoding='utf-8')
        task = {'type': 'bank', 'board': '类比推理', 'title': '实战', 'target': '类比推理', 'id': 'bank:类比推理'}
        r = trainer.start(self.g, task)
        sid = r['session']
        self.assertTrue(r['replace'])
        self.assertIsNone(r['battle']['correct'])                     # 答题时不显示对了几道
        trainer.action(self.g, sid, 'exam_pick:0:B')
        r = trainer.action(self.g, sid, 'exam_submit')                 # 还有两道没选：不交卷，跳到第 2 题
        self.assertIn('2、3', str(r))
        self.assertIn('编号 02', str(r))
        self.assertEqual(bank.state(self.g)['records'], {})
        trainer.action(self.g, sid, 'exam_prev')
        trainer.action(self.g, sid, 'exam_pick:0:A')                   # 回去改答案
        trainer.action(self.g, sid, 'exam_pick:1:A')
        r = trainer.action(self.g, sid, 'exam_pick:2:C')
        self.assertIn('答题卡：1·A 2·A 3·C', str(r))
        r = trainer.action(self.g, sid, 'exam_submit')
        self.assertIn('正确率 66.7%（2/3）', str(r))
        table = r['messages'][0]['blocks'][0]
        self.assertEqual([row[6] for row in table['rows']], ['✓', '✓', '✗', '2/3'])
        self.assertIn('秘密解析', str(r))
        # 暂离后再进来还在复盘
        trainer.action(self.g, sid, 'bank_pause')
        r = trainer.start(self.g, task)
        sid = r['session']
        self.assertIn('复盘 第 1/3 题', str(r))
        r = trainer.action(self.g, sid, 'exam_rwrong')
        self.assertIn('复盘 第 3/3 题 · 编号 03 · ✗ 答错', str(r))
        with patch.object(trainer.ai, 'available', return_value=False):
            r = trainer.action(self.g, sid, 'exam_explain:2')
        self.assertIn('API key', str(r))
        self.assertIn('师傅解惑', str(r))                              # 没连 AI 不算讲过
        sent = {}
        def fake_chat(messages, **kw):
            sent['prompt'] = messages[-1]['content']
            return '选C？坑都写脸上了。'
        with patch.object(trainer.ai, 'available', return_value=True), patch.object(trainer.ai, 'chat', side_effect=fake_chat):
            r = trainer.action(self.g, sid, 'exam_explain:2')
        self.assertIn('坑都写脸上了', str(r))
        self.assertIn('学员选了：C（答错）', sent['prompt'])
        self.assertIn('已存入 训练/题库/师傅解惑.md', str(r))
        self.assertEqual(bank.tutor_notes(self.paths), {'03': '选C？坑都写脸上了。'})
        self.assertIn('再问师傅', str(r))
        r = trainer.action(self.g, sid, 'exam_close')
        self.assertTrue(r['finished'])
        self.assertNotIn('类比推理', bank.state(self.g)['runs'])
        self.assertEqual(bank.summary(self.g)['groups'][0]['correct'], 2)

    def test_exam_timing_table_and_log(self):
        f = self.paths.train / '题库/类比推理真题.md'
        f.write_text(''.join(question(x) for x in ('01', '02')), encoding='utf-8')
        task = {'type': 'bank', 'board': '类比推理', 'title': '实战', 'target': '类比推理', 'id': 'bank:类比推理'}
        now = [1000.0]
        with patch.object(trainer.time, 'time', side_effect=lambda: now[0]):
            r = trainer.start(self.g, task)
            sid = r['session']
            now[0] += 30
            r = trainer.action(self.g, sid, 'exam_pick:0:A')        # 第 1 题 30 秒
            self.assertEqual(r['battle']['timer'], {'total': 30, 'question': 0})
            now[0] += 45
            trainer.action(self.g, sid, 'bank_pause')                # 第 2 题看了 45 秒后暂离
            now[0] += 5000                                            # 暂离期间不计时
            r = trainer.start(self.g, task)
            sid = r['session']
            now[0] += 20
            trainer.action(self.g, sid, 'exam_prev')                 # 第 2 题再 20 秒，回第 1 题
            now[0] += 2000                                            # 走开太久：一次最多记 10 分钟
            trainer.action(self.g, sid, 'exam_pick:0:B')
            now[0] += 10
            trainer.action(self.g, sid, 'exam_pick:1:A')
            r = trainer.action(self.g, sid, 'exam_submit')
        rows = r['messages'][0]['blocks'][0]['rows']
        self.assertEqual([row[7] for row in rows], ['10:30', '1:15', '11:45'])
        self.assertIn('用时 11:45', r['messages'][0]['text'])
        self.assertEqual(bank.summary(self.g)['groups'][0]['seconds'], 705)
        log = (self.paths.train / '试炼记录' / (self.g.t + '.md')).read_text(encoding='utf-8')
        self.assertIn('| 1 | 01 | 类比推理 | 削弱 | B | A | ✗ | 10:30 |', log)
        r = trainer.action(self.g, sid, 'exam_close')
        self.assertEqual(r['messages'][0]['blocks'][0]['rows'][-1][7], '11:45')

    def test_point_run_and_dedupe(self):
        from rpg import importer
        f = self.paths.train / '题库/论证逻辑真题-2020.md'
        blk = lambda i, topic, stem, paper, num: ('\n## 题目 %s\n### 知识点\n%s\n### 试卷\n%s\n### 模块\n判断推理\n### 题号\n%s\n'
                                                '### 题干\n（2020年某省）%s\n### 选项\nA. 甲甲\nB. 乙乙\nC. 丙丙\nD. 丁丁\n### 答案\nA\n### 解析\n解析%s\n') % (i, topic, paper, num, stem, i)
        f.write_text(blk('真题-1', '削弱论证-他因', '研究发现喝咖啡的人更长寿所以咖啡延年', '甲卷', 3)
                     + blk('真题-2', '削弱论证-因果倒置', '城市里乌鸦越来越多说明垃圾变多了', '甲卷', 4)
                     + blk('真题-3', '加强论证-搭桥', '某地推行垃圾分类以后河流变清了', '甲卷', 5)
                     + blk('真题-9', '削弱论证-他因', '研究发现，喝咖啡的人更长寿，所以咖啡延年。', '乙卷', 7), encoding='utf-8')
        # 知识点试炼：只出“削弱论证”大类、没做过的
        task = {'type': 'bank', 'board': '点:论证逻辑:削弱论证', 'title': '点', 'target': ''}
        r = trainer.start(self.g, task)
        self.assertIn('论证逻辑 · 削弱论证 · 第 1/3 题', str(r))
        sid = r['session']
        for i in range(3):
            trainer.action(self.g, sid, 'exam_pick:%d:A' % i)
        r = trainer.action(self.g, sid, 'exam_submit')
        self.assertIn('正确率 100.0%（3/3）', str(r))
        trainer.action(self.g, sid, 'exam_close')
        with self.assertRaises(trainer.TrainError):
            trainer.start(self.g, task)                                   # 这一类做完了
        # 去重：1 和 9 题干选项一样（只差来源括号和标点）；两份都做过 → 记录合并到留下的那份，试卷并过去
        r = importer.dedupe_bank(self.paths, {'dry': True}, self.g.state)
        self.assertEqual((r['groups'], r['removed']), (1, 1))
        r = importer.dedupe_bank(self.paths, {}, self.g.state)
        self.assertEqual(r['records'], 1)
        qs = {q['id']: q for q in bank.read(self.paths, '论证逻辑')[0]}
        keep = '真题-1' if '真题-1' in qs else '真题-9'
        self.assertEqual(sorted(qs), sorted(['真题-2', '真题-3', keep]))
        self.assertEqual(sorted(qs[keep]['papers']), ['乙卷', '甲卷'])
        self.assertEqual(len(bank.state(self.g)['records']['论证逻辑::' + keep]['history']), 2)
        self.assertEqual(importer.dedupe_bank(self.paths, {}, self.g.state)['removed'], 0)

    def test_pending_answer_empty_analysis_and_images(self):
        f = self.paths.train / '题库/图形推理真题.md'
        img = self.paths.train / '题库/图片/图形推理/粉笔36季-077.png'
        self.assertTrue(img.parent.is_dir())                    # 图片文件夹自动建好
        img.write_bytes(b'png')
        f.write_text('\n## 题目 粉笔36季-077\n### 知识点\n位置规律\n### 题干\n（粉笔第36季模考）\n'
                     '![[训练/题库/图片/图形推理/粉笔36季-077.png]]\n从所给的四个选项中选择\n'
                     '### 选项\nA. A\nB. B\nC. C\nD. D\n### 答案\nC\n### 解析\n（待补）\n'
                     + question('四海-01-01', '（待补）') + question('四海-01-02', ''), encoding='utf-8')
        qs, errors = bank.read(self.paths, '图形推理')
        self.assertEqual(errors, [])
        self.assertEqual([q['id'] for q in qs], ['粉笔36季-077'])   # 答案待补的不出
        board = next(b for b in bank.summary(self.g)['boards'] if b['board'] == '图形推理')
        self.assertEqual((board['total'], board['pending']), (1, 2))
        task = {'type': 'bank', 'board': '图形推理', 'title': '实战', 'target': '图形推理', 'id': 'bank:图形推理'}
        r = trainer.start(self.g, task)
        blocks = [b for m in r['messages'] for b in m.get('blocks', [])]
        self.assertIn({'t': 'img', 'v': '训练/题库/图片/图形推理/粉笔36季-077.png'}, blocks)
        self.assertTrue(any('粉笔第36季模考' in b['v'] for b in blocks if b['t'] == 'text'))
        trainer.action(self.g, r['session'], 'exam_pick:0:C')
        r = trainer.action(self.g, r['session'], 'exam_submit')
        self.assertIn('这题没有解析', str(r))

if __name__ == '__main__':
    unittest.main()
