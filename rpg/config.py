"""
读取 训练/ 下的三个用户配置文件，给出带默认值的配置对象。

    规则.md                    → Rules      （游戏规则：时间线、境界、渡劫、灵根、丹药、分批、修为值……）
    角色设定.md                → Persona    （ID、头像；每种风格的称呼、导师名 / 头像 / 人设）
    台词库.md / 台词库·玄幻.md → Lines      （导师在各场景下随机说的话，修仙 / 玄幻各一份）

每次请求都重新读取（文件很小），所以用户改完刷新网页就生效。
规则文件里缺的键一律用 DEFAULT_RULES 里的默认值，写错的值也回退到默认值，程序不会因此崩溃。
"""
import datetime as dt
import random
import re

from . import mdconf

# 默认规则：和 defaults/规则.md 保持一致。新增规则时两边都要加。
DEFAULT_RULES = {
    # 真题实战：每组 10 或 15 题，纳入每日目标时间
    "试炼塔层数": 100,
    "试炼塔总题数": 5000,
    "实战每组题数": 10,
    "试炼上品正确率": 0.9,
    "试炼中品正确率": 0.7,
    "经验.实战通关": 30,
    "分钟.实战每题": 2,
    "经验.实战答对": 5,
    "经验.实战答错": 1,
    "经验.举例通过": 25,
    "经验.举例未过": 5,
    "分钟.举例": 6,
    # 时间线
    "开始日期": "2026-09-29",
    "目标日": "2027-12-01",
    "每日目标分钟": 300,    # 修炼 + 听道（网课）合计
    "保底分钟": 15,
    "每月请假卡": 4,
    # 分数与境界（修为 → 预估分 → 境界）
    "起始分数": 50,
    "目标分数": 80,
    "最高分数": 100,
    "每日理想经验": 300,
    # 渡劫
    "渡劫分数线": "60, 65, 70, 75, 80, 85",
    "天劫雷数": "3, 5, 7, 9, 9, 9",
    "渡劫冷却天数": 3,
    "渡劫道心": 60,
    "渡劫灵根.60": "激活1",
    "渡劫灵根.65": "激活3",
    "渡劫灵根.70": "激活5 玄阶2",
    "渡劫灵根.75": "激活7 玄阶4 地阶1",
    "渡劫灵根.80": "激活9 玄阶6 地阶3",
    "渡劫灵根.85": "激活10 地阶5 天阶2",
    # 灵根
    "灵根正确率": "55, 60, 65, 70, 75, 80, 85, 90",
    "灵根正确率.常识判断": "45, 50, 55, 60, 65, 70, 75, 80",
    "灵根取最近几季": 3,
    "灵根每阶加成": 0.05,
    "灵根复查间隔加成": 0.1,
    # 丹药 / 闭关 / 顿悟 / 走火入魔 / 道心
    "炼丹题数": 5,
    "丹药加成": "0.1, 0.2, 0.3",
    "闭关加成": 0.2,
    "顿悟概率": 0.08,
    "顿悟倍数": 1.0,
    "走火入魔分钟": 180,
    "走火入魔连错": 5,
    "走火调息分钟": 10,
    "道心统计天数": 14,
    "护心丹连续天数": 30,
    # 宗门周常（每周一刷新）
    "周常.斩心魔": 20,
    "周常.背诵口诀": 15,
    "周常.论道": 3,
    "周常.修炼分钟": 1500,
    "周常.宗门大比": 1,
    # 导师
    "导师AI": "开",
    # 分批与日常
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
    # 修为（经验）
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
    "经验.渡劫成功": 500,
    "经验.自练每题": 2,
    "经验.听道每分钟": 0.5,   # 听道（网课）每分钟的修为；主要靠修炼拿修为，听道只给少量
    "听道单次上限": 600,
    "经验.模考录分": 100,
    "经验.周常": 150,
    "经验.飞升": 3000,
    "连续打卡每天加成": 0.02,
    "连续打卡加成上限": 0.2,
    "分钟.默写": 5,
    "分钟.费曼": 12,
    "分钟.应用": 6,
    "分钟.错题": 4,
    "分钟.复查": 3,
    "分钟.骨架": 15,
    "分钟.疗伤": 5,
    "分钟.渡劫": 20,
}

# 用户配置文件的版本号。defaults/ 里的文件改了结构（不只是改数值）时 +1，
# 程序启动时会把旧版本的用户文件备份成 “xxx.旧版.md” 并换成新默认文件（见 paths.ensure_train_dir）。
CONFIG_VERSION = 4
# 每个配置文件各自的版本：只升级真正改了结构的文件，其余文件不动（用户改过的内容保留）
FILE_VERSIONS = {"规则.md": 4, "角色设定.md": 3, "台词库.md": 3, "台词库·玄幻.md": 3}
TIER_WORDS = {"黄阶": 0, "玄阶": 1, "地阶": 2, "天阶": 3}

DEFAULT_BATCHES = [
    ["论证逻辑", "形式逻辑", "一拖五"],
    ["片段阅读", "逻辑填空", "政治理论"],
    ["资料分析", "数量关系"],
    ["定义判断", "类比推理", "图形推理"],
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
    "图形推理": ("xingce-tuxing", ["图形推理"]),
}
DEFAULT_SIDE = {"常识判断": 0.6}


def _date(s, default):
    try:
        return dt.date.fromisoformat(str(s).strip())
    except Exception:
        return dt.date.fromisoformat(default)


class Rules:
    """规则。用 r.num("经验.默写通过") / r.date("目标日") / r.nums("复查间隔天数") 取值。"""

    def __init__(self, text=""):
        self.raw = mdconf.parse(text)

    def get(self, key):
        return self.raw.get(key, DEFAULT_RULES.get(key))

    def has(self, key):
        return key in self.raw or key in DEFAULT_RULES

    def num(self, key):
        return mdconf.to_num(self.get(key), DEFAULT_RULES[key])

    def date(self, key):
        return _date(self.get(key), DEFAULT_RULES[key])

    def nums(self, key):
        vals = [mdconf.to_num(x, None) for x in mdconf.split_list(str(self.get(key)))]
        vals = [v for v in vals if v is not None]
        return vals or [mdconf.to_num(x, 0) for x in mdconf.split_list(DEFAULT_RULES[key])]

    def on(self, key):
        """开关类规则：“开 / 是 / true / 1” 为真"""
        return str(self.get(key)).strip().lower() in ("开", "是", "true", "1", "on", "yes")

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

    def gate_roots(self, gate):
        """某道渡劫线的灵根要求：{"激活": n, 0: 黄阶及以上个数, 1: 玄阶…, 2: 地阶…, 3: 天阶…}"""
        out = {}
        for m in re.finditer(r"(激活|黄阶|玄阶|地阶|天阶)\s*(\d+)", str(self.get(f"渡劫灵根.{gate}") or "")):
            key = "激活" if m.group(1) == "激活" else TIER_WORDS[m.group(1)]
            out[key] = int(m.group(2))
        return out

    def root_thresholds(self, board):
        """灵根八个品阶的正确率门槛（0~1）"""
        key = f"灵根正确率.{board}"
        raw = self.raw.get(key) or DEFAULT_RULES.get(key) or self.get("灵根正确率")
        vals = [mdconf.to_num(x, None) for x in mdconf.split_list(str(raw))]
        vals = [v / 100 if v and v > 1 else v for v in vals if v is not None]
        return (vals + [1.01] * 8)[:8]

    @property
    def side(self):
        """副线 {复盘板块名: 目标正确率}"""
        out = {k[3:].strip(): mdconf.to_num(v, 0.7) for k, v in self.raw.items() if k.startswith("副线.")}
        return out or dict(DEFAULT_SIDE)


class Persona:
    """角色设定。两种风格各有一套导师和称呼：角色设定.md 里写成 “修仙.导师名: …” “玄幻.导师名: …”；
    不带前缀的键（ID、头像）两种风格共用。用 p["导师名"] 取当前风格的值。"""
    COMMON = {"ID": "", "头像": "头像.png"}
    THEMED = {
        "修仙": {"称呼": "徒儿", "导师名": "劭神韵", "导师头像": "师尊.png", "吐槽尺度": "中",
                 "导师人设": ("仙门长老，你的师尊，修为深不可测的傲娇女仙。嘴上嫌弃、句句带刺，总说“为师才不是担心你”，"
                            "其实一直暗中关注你的修炼；你偷懒时她冷着脸训你“朽木不可雕也”，你表现好时别过脸说“哼，勉强算你有几分悟性”，"
                            "你真的累了或遇到难处时，她会嘴硬心软地替你护法、认真开解你。")},
        "玄幻": {"称呼": "小岸", "导师名": "艾琳学姐", "导师头像": "导师.png", "吐槽尺度": "中",
                 "导师人设": ("王立行测魔法学院的首席大魔导师，你的学姐。表面温柔、总是笑眯眯，实际腹黑毒舌："
                            "你偷懒时她笑着补刀、阴阳怪气地“关心”你；你超额完成时嘴上说“哼，还算像样”，其实比谁都骄傲；"
                            "你真的累了、遇到困难时，她会收起毒舌，认真温柔地安慰你。")},
    }

    def __init__(self, text="", theme="修仙"):
        from . import themes
        raw = mdconf.parse(text)
        self.theme = theme if theme in self.THEMED else "修仙"
        self.d = {k: (raw.get(k) or v) for k, v in self.COMMON.items()}
        for k, v in self.THEMED[self.theme].items():
            self.d[k] = raw.get(f"{self.theme}.{k}") or v
        if not self.d["ID"]:
            self.d["ID"] = themes.get(self.theme)["terms"]["hero_empty_id"]

    def __getitem__(self, k):
        return self.d[k]


class Lines:
    """台词库：lines.pick("开场·落后", 称呼="小岸", 落后天数=3)"""

    def __init__(self, text="", fallback=""):
        # 自己的台词库里没有的场景（程序新加的），用默认台词库里的
        self.sec = mdconf.sections(fallback)
        self.sec.update({k: v for k, v in mdconf.sections(text).items() if v})

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


LINES_FILE = {"修仙": "台词库.md", "玄幻": "台词库·玄幻.md"}


def load_all(paths, theme="修仙"):
    """返回 (Rules, Persona, Lines)；库没找到或文件缺失时用 defaults/ 里的默认文件。
    theme 决定用哪套导师设定和哪个台词库（修仙：台词库.md；玄幻：台词库·玄幻.md）"""
    from .paths import DEFAULTS_DIR

    def txt(p, name):
        return (read_text(p) if p else "") or read_text(DEFAULTS_DIR / name)

    lines_name = LINES_FILE.get(theme, "台词库.md")
    return (Rules(txt(paths.rules, "规则.md")), Persona(txt(paths.persona, "角色设定.md"), theme),
            Lines(txt(paths.train / lines_name if paths.train else None, lines_name), read_text(DEFAULTS_DIR / lines_name)))

