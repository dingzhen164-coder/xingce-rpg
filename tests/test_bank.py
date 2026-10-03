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
        # 这些老用例测的是“写拆题过程”模式：现在要在功课里明确要求（reasoning）
        self.task = {'type': 'bank', 'board': '论证逻辑', 'title': '实战', 'target': '论证逻辑', 'id': 'bank:论证逻辑', 'reasoning': True}

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
        self.assertIn('已写进 训练/题库/类比推理真题.md', str(r))
        self.assertEqual(bank.tutor_notes(self.paths), {'03': '选C？坑都写脸上了。'})
        text = f.read_text(encoding='utf-8')
        block = text[text.index('## 题目 03'):]
        self.assertIn('秘密解析', block)
        self.assertIn('【师傅解惑】', block)
        self.assertLess(block.index('秘密解析'), block.index('选C？坑都写脸上了。'))
        self.assertEqual(text.count('【师傅解惑】'), 1)
        self.assertIn('再问师傅', str(r))
        # 再问一次：替换，不叠加
        with patch.object(trainer.ai, 'available', return_value=True), patch.object(trainer.ai, 'chat', return_value='第二次讲法'):
            trainer.action(self.g, sid, 'exam_explain:2')
        text = f.read_text(encoding='utf-8')
        self.assertEqual(text.count('【师傅解惑】'), 1)
        self.assertIn('第二次讲法', text)
        self.assertNotIn('坑都写脸上了', text)
        # 复盘时直接打字问师傅
        with patch.object(trainer.ai, 'available', return_value=True), patch.object(trainer.ai, 'chat', side_effect=fake_chat):
            r = trainer.reply(self.g, sid, '为什么不选B')
        self.assertIn('为什么不选B', str(r))
        self.assertIn('为什么不选B', sent['prompt'])
        self.assertEqual(r.get('scroll'), 'bottom')
        r = trainer.action(self.g, sid, 'exam_close')
        self.assertTrue(r['finished'])
        self.assertNotIn('类比推理', bank.state(self.g)['runs'])
        self.assertEqual(bank.summary(self.g)['groups'][0]['correct'], 2)

    def test_idiom_book_from_logic_fill(self):
        from rpg import idioms
        fill = ('\n## 题目 F1\n### 知识点\n逻辑填空-成语辨析\n### 题干\n这种理念____，乡村游____。\n### 选项\n'
                'A. 主张  如火如荼\nB. 强调  此起彼伏\nC. 遵循  崭露头角\nD. 蕴含  方兴未艾\n### 答案\nD\n### 解析\n'
                '第一空，搭配“农业文明”，A项“主张”的主语通常是人，排除；D项“蕴含”指包含，放入此处恰当，当选。\n'
                '第二空，A项“如火如荼”形容气势旺盛、热烈或激烈，D项“方兴未艾”形容形势或事物正在蓬勃发展，均能体现，保留。B项“此起彼伏”形容此处起来，彼处落下，排除。\n'
                '故正确答案为D。\n【文段出处】《某文》\n'
                '\n## 题目 F2\n### 知识点\n逻辑填空\n### 题干\n只有____才____。\n### 选项\nA. 只有 才\nB. 只要 就\nC. 无论 都\nD. 即使 也\n### 答案\nA\n### 解析\n关联词。\n')
        (self.paths.train / '题库/逻辑填空真题.md').write_text(fill, encoding='utf-8')
        self.assertEqual([idioms.letter(w) for w in ('蕴含', '方兴未艾', '长治久安', '龃龉')], ['Y', 'F', 'C', '#'])
        task = {'type': 'bank', 'board': '逻辑填空', 'title': '实战', 'target': '逻辑填空', 'id': 'bank:逻辑填空'}
        sid = trainer.start(self.g, task)['session']
        trainer.action(self.g, sid, 'exam_pick:0:D')
        r = trainer.action(self.g, sid, 'exam_pick:1:B')
        r = trainer.action(self.g, sid, 'exam_submit')
        self.assertIn('成语实词录新收 2 个：蕴含、方兴未艾', str(r['events']))      # 关联词不收
        book = idioms.listing(self.g)
        self.assertEqual([e['word'] for e in book['entries']], ['方兴未艾', '蕴含'])
        self.assertEqual(book['letters'], {'F': 1, 'Y': 1})
        e = next(x for x in book['entries'] if x['word'] == '方兴未艾')
        s = e['sources'][0]
        self.assertEqual(s['meaning'], '形容形势或事物正在蓬勃发展')
        self.assertEqual([(o['option'], o['word'], o['meaning']) for o in s['others']],
                         [('A', '如火如荼', '形容气势旺盛、热烈或激烈'), ('B', '此起彼伏', '形容此处起来，彼处落下'), ('C', '崭露头角', '')])
        self.assertTrue(s['compare'].startswith('第二空'))
        self.assertEqual((s['key'], s['blank'], s['answer'], s['source']), ('逻辑填空::F1', 2, 'D', '逻辑填空真题.md'))
        self.assertEqual(next(x for x in book['entries'] if x['word'] == '蕴含')['sources'][0]['meaning'], '指包含')
        text = (self.paths.train / '成语实词录.md').read_text(encoding='utf-8')
        self.assertIn('## F\n\n### 方兴未艾', text)
        self.assertIn('[[逻辑填空真题#题目 F1|F1]]', text)
        self.assertIn('如火如荼（A项）：形容气势旺盛、热烈或激烈', text)
        # 补收以前做过的：不重复
        r = idioms.backfill(self.g)
        self.assertEqual((r['new'], r['total']), ([], 2))
        self.assertEqual(len(idioms.data(self.g)['方兴未艾']['sources']), 1)
        # 师傅答疑：一句话辨析替换原辨析，解析没写的释义补上
        reply = {'辨析': '方兴未艾重“正在兴起”，如火如荼重“热烈”，此处写发展势头，选方兴未艾。', '释义': {'崭露头角': '比喻初显才能'}}
        with patch.object(trainer.ai, 'chat_json', return_value=reply) as m:
            idioms.ask_tutor(self.g, '方兴未艾')
        self.assertIn('方兴未艾', m.call_args[0][0][-1]['content'])
        s = idioms.data(self.g)['方兴未艾']['sources'][0]
        self.assertEqual((s['compare'], s['tutor']), (reply['辨析'], True))
        self.assertEqual(s['others'][2]['meaning'], '比喻初显才能')
        s['others'][1]['meaning'] = '（师傅补）旧版带标记'                          # 旧版存的：去掉标记
        self.assertTrue(idioms.clean_tags(self.g))
        self.assertEqual(s['others'][1]['meaning'], '旧版带标记')
        self.assertFalse(idioms.clean_tags(self.g))
        self.assertIn('辨析（🧙 师傅）', (self.paths.train / '成语实词录.md').read_text(encoding='utf-8'))
        idioms.backfill(self.g)                                                    # 再收一次不覆盖师傅的
        self.assertEqual(idioms.data(self.g)['方兴未艾']['sources'][0]['compare'], reply['辨析'])
        # 修改：释义自己写，改名
        idioms.edit(self.g, '蕴含', {'word': '蕴涵', 'sources': {'0': {'meaning': '包含（自己写的）'}}})
        book = idioms.data(self.g)
        self.assertNotIn('蕴含', book)
        self.assertEqual((book['蕴涵']['letter'], book['蕴涵']['sources'][0]['meaning']), ('Y', '包含（自己写的）'))
        idioms.backfill(self.g)                                                    # 旧名字不会被收回来
        self.assertNotIn('蕴含', idioms.data(self.g))
        # 删除：以后也不收回来
        idioms.delete(self.g, '方兴未艾')
        self.assertEqual(idioms.backfill(self.g)['new'], [])
        self.assertEqual(sorted(idioms.data(self.g)), ['蕴涵'])
        with self.assertRaises(ValueError):
            idioms.delete(self.g, '方兴未艾')

    def test_idiom_book_splits_joined_options(self):
        from rpg import idioms
        hist = ('\n## 题目 H1\n### 知识点\n逻辑填空\n### 题干\n____，____。\n### 选项\nA. 克服  纠正\nB. 破除  矫正\nC. 消除  修正\nD. 根除  改正\n### 答案\nA\n### 解析\n无\n'
                '\n## 题目 H2\n### 知识点\n逻辑填空\n### 题干\n____，____。\n### 选项\nA. 满足  挫伤\nB. 顺应  消磨\nC. 契合  抑制\nD. 迎合  影响\n### 答案\nA\n### 解析\n无\n')
        mock = ('\n## 题目 粉笔36季-047\n### 知识点\n逻辑填空\n### 题干\n才能____弊端，往往具有____。若未被及时____。\n### 选项\n'
                'A. 克服渐进性纠正\nB. 破除持续性矫正\nC. 消除阶段性修正\nD. 根除累积性改正\n### 答案\nA\n### 解析\n（待补）\n'
                '\n## 题目 粉笔36季-045\n### 知识点\n逻辑填空\n### 题干\n____，____，____。\n### 选项\n'
                'A. 满足屡禁不止挫伤\nB. 顺应层出不穷消磨\nC. 契合沉渣泛起抑制\nD. 迎合俯拾皆是影响\n### 答案\nA\n### 解析\n（待补）\n')
        (self.paths.train / '题库/逻辑填空真题.md').write_text(hist + mock, encoding='utf-8')
        qs = {q['id']: q for q in bank.read(self.paths, '逻辑填空')[0]}
        # 旧版收录：整串当一个词
        self.g.state['idioms'] = {'克服渐进性纠正': {'word': '克服渐进性纠正', 'letter': 'K', 'added': '2026-09-01', 'sources': [
            {'key': '逻辑填空::粉笔36季-047', 'board': '逻辑填空', 'date': '2026-09-01', 'blank': 1}]}}
        self.assertTrue(idioms.migrate(self.g))
        book = idioms.data(self.g)
        self.assertEqual(sorted(book), ['克服', '渐进性', '纠正'])
        self.assertEqual(book['渐进性']['sources'][0]['date'], '2026-09-01')        # 收录日期保留
        self.assertEqual([o['word'] for o in book['渐进性']['sources'][0]['others']], ['持续性', '阶段性', '累积性'])
        self.assertFalse(idioms.migrate(self.g))
        new = idioms.harvest(self.g, [qs['粉笔36季-045']])
        self.assertEqual(new, ['满足', '屡禁不止', '挫伤'])
        self.assertEqual([o['word'] for o in book['屡禁不止']['sources'][0]['others']], ['层出不穷', '沉渣泛起', '俯拾皆是'])

    def test_tutor_reads_whole_skill_and_hides_distilled(self):
        sk = self.paths.vault / 'copilot/skills/xingce-luojitiankong'
        (sk / 'references').mkdir(parents=True)
        (sk / 'scripts').mkdir()
        (sk / 'SKILL.md').write_text('---\nname: x\n---\n# 逻辑填空\n先读 `逻辑填空方法总纲`', encoding='utf-8')
        (sk / 'references/六种对应关系.md').write_text('解释对应、并列对应、转折对应、递进对应、因果对应、总分对应', encoding='utf-8')
        (sk / 'scripts/x.md').write_text('脚本说明不该读', encoding='utf-8')
        (self.paths.vault / '逻辑填空方法总纲.md').write_text('总纲：先找对应关系', encoding='utf-8')
        q = ('\n## 题目 L1\n### 知识点\n逻辑填空\n### 题干\n____了更多职业。\n### 选项\nA. 造就\nB. 创造\nC. 催生\nD. 产生\n'
             '### 答案\nC\n### 解析\n官方：C项“催生”指催促问世。\n【文段出处】人民网\n\n【推理链】\n第1步：蒸馏的推理\n\n【师傅解惑】（2026-10-03）\n旧的讲解\n')
        (self.paths.train / '题库/逻辑填空真题.md').write_text(q, encoding='utf-8')
        task = {'type': 'bank', 'board': '逻辑填空', 'title': '实战', 'target': '逻辑填空', 'id': 'bank:逻辑填空'}
        sid = trainer.start(self.g, task)['session']
        trainer.action(self.g, sid, 'exam_pick:0:B')
        trainer.action(self.g, sid, 'exam_submit')
        sent = {}
        def fake_chat(messages, **kw):
            sent['p'] = messages[-1]['content']
            return '讲解'
        with patch.object(trainer.ai, 'available', return_value=True), patch.object(trainer.ai, 'chat', side_effect=fake_chat):
            r = trainer.action(self.g, sid, 'exam_explain:0')
        p = sent['p']
        self.assertIn('六种对应关系', p.split('题目')[0])          # skill 的 references 也读到了，放在题目前面
        self.assertIn('总纲：先找对应关系', p)                     # skill 引用的库内资料
        self.assertNotIn('脚本说明不该读', p)
        self.assertIn('官方：C项“催生”指催促问世。', p)
        self.assertNotIn('蒸馏的推理', p)                           # 蒸馏小节、旧的师傅解惑不给师傅看
        self.assertNotIn('旧的讲解', p)
        self.assertIn('哪个方法', p)
        self.assertIn('依据 skill「xingce-luojitiankong」：SKILL.md、references/六种对应关系.md、逻辑填空方法总纲.md', str(r))

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

    def test_argument_board_defaults_to_normal_answering(self):
        self.file.write_text(''.join(question(x) for x in ('01', '02')), encoding='utf-8')
        task = dict(self.task)
        task.pop('reasoning')
        r = trainer.start(self.g, task)
        self.assertEqual([b['id'] for b in r['input']['buttons']][:4], ['exam_pick:0:A', 'exam_pick:0:B', 'exam_pick:0:C', 'exam_pick:0:D'])
        trainer.action(self.g, r['session'], 'bank_pause')
        # 以前按“写拆题过程”开的、还没答过的组：续闯时改成正常答题
        bank.state(self.g)['runs']['论证逻辑'].update(reasoning=True, exam=False)
        r = trainer.start(self.g, task)
        self.assertEqual(r['input']['mode'], 'buttons')
        self.assertIn('交卷', str(r['input']))

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
