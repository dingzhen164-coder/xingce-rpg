"""藏经阁·玉简：目录、搜题、看题。"""
import datetime as dt
import tempfile
import unittest
from pathlib import Path

from rpg import config, engine, library, paths, store, question_bank as bank


def q(ident, topic, stem, answer='A'):
    return ('\n## 题目 %s\n### 知识点\n%s\n### 题干\n（2023年国考）%s\n### 选项\nA. 甲\nB. 乙\nC. 丙\nD. 丁\n'
            '### 答案\n%s\n### 解析\n解析%s\n') % (ident, topic, stem, answer, ident)


class LibraryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.paths = paths.Paths(Path(self.tmp.name))
        self.paths.ensure_train_dir()
        self.g = engine.Game(self.paths, config.Rules(), config.Persona(), config.Lines(),
                             store.new_state(dt.date(2026, 10, 1)), dt.date(2026, 10, 1))
        (self.paths.train / '题库/论证逻辑真题-历年.md').write_text(
            q('真题-1', '削弱论证-因果倒置', '研究发现独角兽企业增长很快') + q('真题-2', '削弱论证-他因', '城市乌鸦变多')
            + q('真题-3', '加强论证-搭桥', '独角兽公司估值') + q('真题-4', '加强论证', '待补的题', '（待补）'), encoding='utf-8')

    def tearDown(self):
        self.tmp.cleanup()

    def test_catalog_search_detail(self):
        bank.state(self.g)['records']['论证逻辑::真题-2'] = {'question': {}, 'history': [{'date': '2026-10-01', 'answer': 'B', 'ok': False, 'seconds': 70}], 'wrong': True}
        c = library.catalog(self.g)
        b = next(x for x in c['boards'] if x['board'] == '论证逻辑')
        self.assertEqual((b['total'], b['wrong'], b['pending'], b['new']), (4, 1, 1, 2))
        self.assertEqual({t['name']: t['count'] for t in b['topics']}, {'削弱论证': 2, '加强论证': 2})   # 目录按大类
        r = library.search(self.g, {'q': '独角兽'})
        self.assertEqual([x['id'] for x in r['rows']], ['真题-1', '真题-3'])
        self.assertEqual(r['rows'][0]['text'], '研究发现独角兽企业增长很快')                                # 去掉来源括号
        self.assertEqual(library.search(self.g, {'q': '独角兽 估值'})['total'], 1)                          # 空格分开都要有
        self.assertEqual(library.search(self.g, {'board': '论证逻辑', 'topic': '削弱论证'})['total'], 2)
        self.assertEqual([x['id'] for x in library.search(self.g, {'status': 'wrong'})['rows']], ['真题-2'])
        d = library.detail(self.g, '论证逻辑::真题-2')
        self.assertEqual((d['answer'], d['history'][0]['seconds']), ('A', 70))
        self.assertIn('解析真题-2', str(d['analysis']))
        with self.assertRaises(bank.BankError):
            library.detail(self.g, '论证逻辑::没有')


if __name__ == '__main__':
    unittest.main()
