"""真题实战回归：顺序、答案保密、续做、重复提交、错题统计与旧存档兼容。"""
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from rpg import config, engine, paths, question_bank as bank, store, trainer


def question(ident, answer='A'):
    return ('\n## 题目 %s\n### 知识点\n削弱\n### 题干\n题干 %s\n'
            '### 选项\nA. 甲\nB. 乙\nC. 丙\nD. 丁\n### 答案\n%s\n### 解析\n秘密解析\n') % (ident, ident, answer)


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
        trainer.action(self.g, sid, 'bank_answer:0:B')
        xp = self.g.state['xp']
        with self.assertRaises(trainer.TrainError):
            trainer.action(self.g, sid, 'bank_answer:0:B')
        self.assertEqual(self.g.state['xp'], xp)
        store.Store(self.paths).save(self.g.state, self.day)
        trainer.SESSIONS.clear()
        self.g.state = store.Store(self.paths).load(self.day)
        r = trainer.start(self.g, self.task)
        self.assertIn('秘密解析', str(r))
        sid = r['session']
        r = trainer.action(self.g, sid, 'bank_next')
        self.assertIn('编号 01', str(r))
        for pos in range(1, 10):
            trainer.action(self.g, sid, 'bank_answer:%s:A' % pos)
            r = trainer.action(self.g, sid, 'bank_next')
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
        trainer.action(self.g, r['session'], 'bank_answer:0:B')
        trainer.action(self.g, r['session'], 'bank_next')
        self.file.write_text('', encoding='utf-8')  # 原题删掉仍可按错题快照复练
        self.task['type'] = 'bank_review'
        xp = self.g.state['xp']
        for _ in range(2):
            r = trainer.start(self.g, self.task)
            trainer.action(self.g, r['session'], 'bank_answer:0:A')
            trainer.action(self.g, r['session'], 'bank_next')
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
        self.assertEqual(self.g.rules.num('每日目标分钟'), 120)

    def test_trial_reward_once_and_theme_feedback(self):
        self.file.write_text(question('1'), encoding='utf-8')
        r = trainer.start(self.g, self.task)
        self.assertEqual(r['battle']['total'], 1)
        self.assertNotIn('秘密解析', str(r['battle']))
        trainer.action(self.g, r['session'], 'bank_answer:0:A')
        r = trainer.action(self.g, r['session'], 'bank_next')
        self.assertIn('破阵无伤', str(r))
        self.assertEqual(sum(e['type'] == 'bank_clear' for e in self.g.state['events']), 1)
        with self.assertRaises(trainer.TrainError):
            trainer.action(self.g, r['session'], 'bank_next')
        self.g.state['theme'] = '玄幻'
        self.assertEqual(self.g.T('nav.bank'), '🗼 试炼塔')
        self.assertEqual(self.g.T('bank_rank.3'), '完美通关')
        self.assertEqual(bank.rank(self.g, 9, 10), 2)
        self.assertEqual(bank.rank(self.g, 7, 10), 1)
        self.assertEqual(bank.rank(self.g, 6, 10), 0)

    def test_old_partial_run_keeps_answers_without_retroactive_reward(self):
        self.file.write_text(question('1') + question('2'), encoding='utf-8')
        r = trainer.start(self.g, self.task)
        trainer.action(self.g, r['session'], 'bank_answer:0:A')
        run = bank.state(self.g)['runs']['论证逻辑']
        run['results'][0].pop('first')  # 模拟上一版保存的作答，没有新奖励标记
        trainer.action(self.g, r['session'], 'bank_next')
        trainer.action(self.g, r['session'], 'bank_answer:1:A')
        trainer.action(self.g, r['session'], 'bank_next')
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
        r = trainer.action(self.g,r['session'],'bank_answer:0:B')
        self.assertEqual(r['battle']['tower']['cleared'],1)
        self.assertTrue(any('登上试炼塔第 1 层' in e.get('msg','') for e in r['events']))
        trainer.action(self.g,r['session'],'bank_next')
        self.task['type'] = 'bank_review'
        r = trainer.start(self.g,self.task)
        r = trainer.action(self.g,r['session'],'bank_answer:0:A')
        self.assertEqual(r['battle']['tower']['completed'],50)
        self.assertFalse(any('登上试炼塔' in e.get('msg','') for e in r['events']))

    def test_appended_questions_continue_without_numeric_sort(self):
        self.file.write_text(question('999'), encoding='utf-8')
        r = trainer.start(self.g, self.task)
        trainer.action(self.g,r['session'],'bank_answer:0:A')
        trainer.action(self.g,r['session'],'bank_next')
        self.file.write_text(question('999') + question('001'), encoding='utf-8')
        r = trainer.start(self.g,self.task)
        self.assertIn('编号 001',str(r))
        self.assertEqual(len(bank.state(self.g)['runs']['论证逻辑']['questions']),1)


if __name__ == '__main__':
    unittest.main()
