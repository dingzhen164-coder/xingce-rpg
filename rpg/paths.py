"""
路径：找 Obsidian 行测库（vault）、训练文件夹、本机设置。

约定（和 obsidian-to-xingce 项目一致）：
    <库>/copilot/skills/<skill名>/SKILL.md          板块解题 skill（只读）
    <库>/FB模考试卷复盘/板块复盘/第N季/NN-板块.md     模考板块复盘（只读）
    <库>/训练/                                       本程序的数据（规则、骨架、存档……），坚果云同步
    ~/.xingce-rpg/settings.json                      本机设置（API key、库路径），不同步、不进仓库

找库的顺序：环境变量 XINGCE_VAULT → 本机设置里的 vault → 从程序所在目录往上找。
"""
import json
import os
import re
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent          # 程序根目录（server.py 所在）
WEB_DIR = APP_DIR / "web"
DEFAULTS_DIR = APP_DIR / "defaults"                       # 首次运行时复制到 训练/ 的默认配置
SETTINGS_DIR = Path.home() / ".xingce-rpg"
SETTINGS_FILE = SETTINGS_DIR / "settings.json"

SKILLS_REL = Path("copilot") / "skills"
SEASONS_REL = Path("FB模考试卷复盘") / "板块复盘"
TRAIN_REL = Path("训练")


def load_settings():
    """本机设置：{"api_key", "base_url", "model", "vault"}，文件不存在就返回空字典"""
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_settings(data):
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, SETTINGS_FILE)


def looks_like_vault(p: Path) -> bool:
    return (p / SKILLS_REL).is_dir() or (p / SEASONS_REL).is_dir()


def find_vault():
    """返回库根目录（Path）；找不到返回 None，网页会提示用户在“设置”里填写"""
    env = os.environ.get("XINGCE_VAULT")
    if env and looks_like_vault(Path(env).expanduser()):
        return Path(env).expanduser().resolve()
    s = load_settings().get("vault")
    if s and looks_like_vault(Path(s).expanduser()):
        return Path(s).expanduser().resolve()
    # 推荐把程序放在 <库>/训练/程序/ 里，这样往上两级就是库
    for p in [APP_DIR, *APP_DIR.parents]:
        if looks_like_vault(p):
            return p
    return None


class Paths:
    """一个库对应的全部路径。vault 为 None 时各属性也为 None。"""

    def __init__(self, vault):
        self.vault = vault
        self.skills = vault / SKILLS_REL if vault else None
        self.seasons = vault / SEASONS_REL if vault else None
        self.train = vault / TRAIN_REL if vault else None
        self.skeletons = self.train / "骨架" if vault else None
        self.save_dir = self.train / "存档" if vault else None
        self.save_file = self.save_dir / "存档.json" if vault else None
        self.rules = self.train / "规则.md" if vault else None
        self.persona = self.train / "角色设定.md" if vault else None
        self.lines = self.train / "台词库.md" if vault else None

    def ensure_train_dir(self):
        """建 训练/ 文件夹，把缺失的默认配置复制进去。
        已有的配置文件不覆盖；只有它的“配置版本”低于程序里这个文件的版本（config.FILE_VERSIONS，程序升级改了结构）时，
        才把旧文件改名为 “xxx.旧版.md” 备份，再换成新的默认文件。返回被升级的文件名列表。"""
        from .config import FILE_VERSIONS
        from .mdconf import parse, to_num
        if not self.vault:
            return []
        for d in (self.train, self.skeletons, self.save_dir):
            d.mkdir(parents=True, exist_ok=True)
        upgraded = []
        for name in ("规则.md", "角色设定.md", "台词库.md", "台词库·玄幻.md"):
            dst = self.train / name
            src = DEFAULTS_DIR / name
            if dst.exists():
                ver = to_num(parse(dst.read_text(encoding="utf-8", errors="ignore")).get("配置版本", 1), 1)
                if ver >= FILE_VERSIONS.get(name, 1):
                    continue
                bak = dst.with_name(dst.stem + ".旧版.md")
                if bak.exists():
                    bak.unlink()
                os.replace(dst, bak)
                upgraded.append(name)
            with open(dst, "w", encoding="utf-8", newline="\n") as fp:
                fp.write(src.read_text(encoding="utf-8"))
        # 程序自带的功法（图形推理.md = 图推 24 诀；资料分析.md = 题型识别 + 公式速算）：库里还没有时复制一份草稿，已有的绝不覆盖。
        # （defaults/骨架/ 里的其他文件如 论证逻辑.md 由 scripts/update-local.ps1 按需替换，这里不自动复制。）
        for name in AUTO_SKELETONS:
            src = DEFAULTS_DIR / "骨架" / name
            dst = self.skeletons / name
            if not src.exists():
                continue
            text = src.read_text(encoding="utf-8")
            if dst.exists():
                # 库里已有同名功法：不覆盖。若它是别处来的（比如之前按 skill 生成的草稿，“来源skill”不同），
                # 旁边放一份“xxx.程序自带版.md”供对照/替换；是程序自带那份（用户改过也一样）就什么都不做。
                src_of = lambda t: (re.search(r"^来源skill[:：]\s*(.*)$", t, re.M) or [None, ""])[1].strip()
                if src_of(dst.read_text(encoding="utf-8", errors="ignore")) == src_of(text):
                    continue
                dst = self.skeletons / (Path(name).stem + ".程序自带版.md")
                if dst.exists():
                    continue
            with open(dst, "w", encoding="utf-8", newline="\n") as fp:
                fp.write(text)
        if upgraded:
            UPGRADED.extend(upgraded)
        from .question_bank import ensure_templates
        ensure_templates(self)
        return upgraded


UPGRADED = []  # 本次运行中被升级的配置文件（网页上提示一次）
AUTO_SKELETONS = ("图形推理.md", "资料分析.md")

