"""师傅解惑存进复盘笔记：接在自己的笔记后面、再问一次就替换、没有笔记的题新开一段；“复盘解析”能读到。"""
import tempfile
import unittest
from pathlib import Path

from rpg import paths, vault

BOARD = """# 第36季 · 论证逻辑

### 1. ❌
题干一
- **A.** 甲
- **B.** 乙
> [!check]- 答案
> 正确答案：**B**　我的答案：**A**　错误

> [!note] 复盘
> 我自己的笔记
---
### 2. ⚪
题干二
- **A.** 甲
- **B.** 乙
> [!check]- 答案
> 正确答案：**A**　我的答案：**—**　未作答
---
"""


class TutorNoteTest(unittest.TestCase):
    def test_save_replace_and_new_note(self):
        with tempfile.TemporaryDirectory() as d:
            p = paths.Paths(Path(d))
            (Path(d) / 'copilot/skills').mkdir(parents=True)
            p.ensure_train_dir()
            season = p.seasons / '第36季'
            season.mkdir(parents=True)
            f = season / '04-论证逻辑.md'
            f.write_text(BOARD, encoding='utf-8')
            where = vault.save_tutor_note(p, '36|论证逻辑|1', '第一行讲解\n\n第二行', '2026-10-01')
            self.assertTrue(where.endswith('04-论证逻辑.md'))
            q = vault.find_question(p, '36|论证逻辑|1')
            self.assertIn('我自己的笔记', q['analysis'])
            self.assertIn('第一行讲解\n第二行', q['analysis'])
            vault.save_tutor_note(p, '36|论证逻辑|1', '新的讲解', '2026-10-02')
            text = f.read_text(encoding='utf-8')
            self.assertEqual(text.count('🧙 师傅解惑'), 1)
            self.assertNotIn('第一行讲解', text)
            self.assertIn('我自己的笔记', text)
            vault.save_tutor_note(p, '36|论证逻辑|2', '第二题讲解', '2026-10-02')
            q2 = vault.find_question(p, '36|论证逻辑|2')
            self.assertIn('第二题讲解', q2['analysis'])
            self.assertEqual(q2['correct'], 'A')
            self.assertEqual(len(vault.wrong_questions(p, ['论证逻辑'])), 2)   # 题目结构没被破坏


if __name__ == '__main__':
    unittest.main()
