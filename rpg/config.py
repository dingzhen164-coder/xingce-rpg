"""
读取 训练/ 下的三个用户配置文件，给出带默认值的配置对象。

    规则.md      → Rules      （游戏规则：时间线、等级、分批、经验值……）
    角色设定.md  → Persona    （ID、称呼、头像、导师人设）
    台词库.md    → Lines      （导师在各场景下随机说的话）

每次请求都重新读取（文件很小），所以用户改完刷新网页就生效。
规则文件里缺的键一律用 DEFAULT_RULES 里的默认值，写错的值也回退到默认值，程序不会因此崩溃。
"""
import datetime as dt
import random
import re

from . import mdconf

# 默认规则：和 defaults/规则.md 保持一致。新增规则时两边都要加。
DEFAULT_RULES = {
    "开始日期": "2026-09-29",
    "满级目标日": "2027-12-01",
    "每日目标分钟": 120,
    "保底分钟": 15,
    "每月请假卡": 4,
    "起始分数": 50,
    "满级分数": 80,
    "每日理想经验": 300,
    "后期升级倍数": 3.0,
    "突破等级": "10, 20, 30",
    "突破题数": 8,
    "突破通过率": 0.9,
    "每批预计天数": 14,
    "每日新学大项": 4,
    "每日新学板块数": 2,
    "每日复查上限": 6,
    "默写连续通过次数": 2,
    "思路达标比例": 0.8,
    "费曼追问轮数": 2,
    "应用连续通过次数": 2,
    "复查间隔天数": "3, 7, 15, 30, 60",
    "每日错题下限": 4,
    "每日错题上限": 10,
    "回炉间隔天数": 2,
    "回炉连续判对": 2,
    "错题只取最近几季": 0,
    "经验.默写通过": 30,
    "经验.默写未过": 5,
    "经验.首次通过加成": 20,
    "经验.费曼通过": 50,
    "经验.费曼未过": 10,
    "经验.应用通过": 25,
    "经验.应用未过": 5,
    "经验.错题判对": 15,
    "经验.错题判错": 3,
    "经验.回炉判对加成": 10,
    "经验.复查通过": 15,
    "经验.复查未过": 3,
    "经验.大项掌握": 40,
    "经验.批次通关": 500,
    "经验.周目通关": 2000,
    "经验.突破成功": 300,
    "经验.自练每题": 2,
    "经验.模考录分": 100,
    "经验.模考进步每分": 20,
    "连续打卡每天加成": 0.02,
    "连续打卡加成上限": 0.2,
    "分钟.默写": 5,
    "分钟.费曼": 12,
    "分钟.应用": 6,
    "分钟.错题": 4,
    "分钟.复查": 3,
    "分钟.骨架": 15,
}

DEFAULT_BATCHES = [
    ["论证逻辑", "形式逻辑", "一拖五"],
    ["片段阅读", "逻辑填空", "政治理论"],
    ["资料分析", "数量关系"],
    ["定义判断", "类比推理"],
]

# 板块名 → (skill 文件夹名, [模考复盘里的板块名])
DEFAULT_BOARDS = {
    "论证逻辑": ("xue-rui-argument-logic", ["论证逻辑"]),
    "形式逻辑": ("xue-rui-formal-logic", ["形式逻辑"]),
    "一拖五": ("xue-rui-yituowu", ["一拖五"]),
    "片段阅读": ("center-comprehension-jiangwei", ["中心理解", "语句排序"]),
    "逻辑填空": ("xingce-luojitiankong", ["逻辑填空"]),
    "政治理论": ("political-theory-reasoning", ["政治理论"]),
    "资料分析": ("xingce-ziliao", ["资料分析"]),
    "数量关系": ("xingce-shuliang", ["数量关系"]),
    "定义判断": ("xingce-dingyi", ["定义判断"]),
    "类比推理": ("xingce-leibi", ["类比关系"]),
}
DEFAULT_SIDE = {"常识判断": 0.6, "图形推理": 0.7}


def _date(s, default):
    try:
        return dt.date.fromisoformat(str(s).strip())
    except Exception:
        return dt.date.fromisoformat(default)


class Rules:
    """规则。用 r.num("经验.默写通过") / r.date("满级目标日") / r.nums("复查间隔天数") 取值。"""

    def __init__(self, text=""):
        self.raw = mdconf.parse(text)

    def get(self, key):
        return self.raw.get(key, DEFAULT_RULES.get(key))

    def num(self, key):
        return mdconf.to_num(self.get(key), DEFAULT_RULES[key])

    def date(self, key):
        return _date(self.get(key), DEFAULT_RULES[key])

    def nums(self, key):
        vals = [mdconf.to_num(x, None) for x in mdconf.split_list(str(self.get(key)))]
        vals = [v for v in vals if v is not None]
        return vals or [mdconf.to_num(x, 0) for x in mdconf.split_list(DEFAULT_RULES[key])]

    def xp(self, name):
        """经验值：r.xp("默写通过")"""
        return self.num("经验." + name)

    def minutes(self, task_type):
        key = "分钟." + task_type
        return self.num(key) if key in DEFAULT_RULES else 5

    @property
    def batches(self):
        """[[板块, …], …]，按 “第N批” 的 N 排序；规则里一批都没写就用默认分批"""
        found = []
        for k, v in self.raw.items():
            m = re.fullmatch(r"第\s*(\d+)\s*批", k)
            if m and mdconf.split_list(v):
                found.append((int(m.group(1)), mdconf.split_list(v)))
        return [b for _, b in sorted(found)] or [list(b) for b in DEFAULT_BATCHES]

    @property
    def boards(self):
        """{板块: {"skill": 文件夹名, "sources": [复盘板块名]}}，保持规则里的顺序"""
        out = {}
        for k, v in self.raw.items():
            if k.startswith("板块."):
                name = k[3:].strip()
                skill, _, src = v.partition("|")
                out[name] = {"skill": skill.strip(), "sources": mdconf.split_list(src) or [name]}
        if not out:
            out = {k: {"skill": s, "sources": list(src)} for k, (s, src) in DEFAULT_BOARDS.items()}
        # 分批里出现、但没有定义的板块：skill 名留空（显示为待接入）
        for b in [x for batch in self.batches for x in batch]:
            out.setdefault(b, {"skill": "", "sources": [b]})
        return out

    @property
    def side(self):
        """副线 {复盘板块名: 目标正确率}"""
        out = {k[3:].strip(): mdconf.to_num(v, 0.7) for k, v in self.raw.items() if k.startswith("副线.")}
        return out or dict(DEFAULT_SIDE)


class Persona:
    DEFAULT = {
        "ID": "上岸者·001",
        "称呼": "小岸",
        "头像": "头像.png",
        "称号": "见习考生, 备考学徒, 刷题行者, 行测骑士, 上岸先锋, 上岸者",
        "导师名": "教官",
        "导师人设": "毒舌但靠谱的备考教官。说话简短、带点刺，偷懒会被俏皮地骂，超额完成会真心夸，真的累了会先共情再鼓励。",
        "吐槽尺度": "轻",
    }

    def __init__(self, text=""):
        raw = mdconf.parse(text)
        self.d = {k: (raw.get(k) or v) for k, v in self.DEFAULT.items()}

    def __getitem__(self, k):
        return self.d[k]

    def title(self, level, max_level):
        titles = mdconf.split_list(self.d["称号"]) or ["上岸者"]
        if level >= max_level or len(titles) == 1:
            return titles[-1]
        return titles[min((level - 1) // 5, len(titles) - 2)]


class Lines:
    """台词库：lines.pick("开场·落后", 称呼="小岸", 落后天数=3)"""

    def __init__(self, text=""):
        self.sec = mdconf.sections(text)

    def pick(self, scene, **vals):
        opts = self.sec.get(scene) or []
        if not opts:
            return ""
        s = random.choice(opts)
        for k, v in vals.items():
            s = s.replace("{" + k + "}", str(v))
        return re.sub(r"\{[^{}]{1,6}\}", "", s)  # 没提供的占位符直接去掉


def read_text(path):
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def load_all(paths):
    """返回 (Rules, Persona, Lines)；库没找到或文件缺失时用 defaults/ 里的默认文件"""
    from .paths import DEFAULTS_DIR

    def txt(p, name):
        return (read_text(p) if p else "") or read_text(DEFAULTS_DIR / name)

    return (Rules(txt(paths.rules, "规则.md")), Persona(txt(paths.persona, "角色设定.md")),
            Lines(txt(paths.lines, "台词库.md")))
