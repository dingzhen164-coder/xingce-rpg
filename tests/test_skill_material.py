"""生成骨架的素材：读 skill 引用的库内资料（文件、文件夹、检索 skill 的资料），不读脚本和其他 skill 的操作说明。"""
import tempfile
import unittest
from pathlib import Path

from rpg import paths, prompts, vault


class SkillMaterialTest(unittest.TestCase):
    def test_reads_referenced_material(self):
        with tempfile.TemporaryDirectory() as t:
            v = Path(t)
            d = v / "copilot/skills/political-theory-reasoning"
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text("必须先读取 `政治理论/00-三层级做题总框架.md`；调用 `kb-search`（知识库 `01-治理母逻辑`）；"
                                        "运行 `python \"<jiexi>\" next`；别读 `jiexi.py`", encoding="utf-8")
            (v / "政治理论").mkdir()
            (v / "政治理论/00-三层级做题总框架.md").write_text("第一层：定性", encoding="utf-8")
            kb = v / "copilot/skills/kb-search"
            (kb / "data").mkdir(parents=True)
            (kb / "SKILL.md").write_text("检索规程：最多 3 条", encoding="utf-8")
            (kb / "data/人民至上.md").write_text("人民至上要点", encoding="utf-8")
            (v / "资料/01-治理母逻辑").mkdir(parents=True)
            (v / "资料/01-治理母逻辑/共同富裕.md").write_text("共同富裕要点", encoding="utf-8")
            (v / "额外.md").write_text("规则里指定的资料", encoding="utf-8")
            text, used = vault.skill_material(paths.Paths(v), "political-theory-reasoning", ["额外.md"])
            self.assertEqual(set(used), {"政治理论/00-三层级做题总框架.md", "copilot/skills/kb-search/data/人民至上.md",
                                         "资料/01-治理母逻辑/共同富裕.md", "额外.md"})
            self.assertIn("第一层：定性", text)
            self.assertNotIn("检索规程", text)                      # 检索 skill 的操作说明不读
            msg = prompts.skeleton_gen("政治理论", text)[1]["content"]
            self.assertIn("操作规程", msg)                          # 提示词要求排除操作规程


if __name__ == "__main__":
    unittest.main()
