"""
两种风格（东方修仙 / 西方玄幻）的全部“说法”。游戏规则只有一套，风格只决定名字、导师、台词库和界面文字。

- 当前风格存在存档的 state["theme"]（两台电脑同步），网页“设置”里切换；默认修仙。
- 网页从 /api/dashboard 的 theme.terms 取界面文字，后端用 T(g, "键") 取。
- 新增一个说法：两种风格的 TERMS 都要加同一个键。

境界（REALMS）按“预估分”划分，两种风格共用分数段，只是名字不同：
    50 凡人 | 51–59 炼气一～九层 | 60–64 筑基 | 65–69 金丹 | 70–74 元婴 | 75–79 化神 | 80–84 大乘 | 85+ 真仙
    五分一个大境界：初期 2 分、中期 2 分、后期 1 分（如筑基 60–61 初期、62–63 中期、64 后期）。
    进入 60/65/70/75/80/85 这些大境界需要渡劫（分数线在 规则.md 的“渡劫分数线”）。
"""

# (起始分, 结束分(不含), 类型)：mortal 凡人 / layers 每分一层 / stages 初中后 / single 不再细分
BANDS = [(50, 51, "mortal"), (51, 60, "layers"), (60, 65, "stages"), (65, 70, "stages"),
         (70, 75, "stages"), (75, 80, "stages"), (80, 85, "stages"), (85, 999, "single")]
CN_NUM = "一二三四五六七八九"

# 八个灵根品阶（index 0～7），四个大阶（index // 2）
BOARD_PILLS = {
    "修仙": {"政治理论": "学思践悟丹", "常识判断": "博闻强识丹", "逻辑填空": "咬文嚼字丹", "片段阅读": "一目十行丹",
             "数量关系": "速算凝元丹", "资料分析": "截位直除丹", "图形推理": "火眼金睛丹", "定义判断": "字斟句酌丹",
             "类比推理": "触类旁通丹", "论证逻辑": "明辨是非丹", "形式逻辑": "逆否归元丹", "一拖五": "排兵布阵丹"},
    "玄幻": {"政治理论": "信仰圣水", "常识判断": "博学者药剂", "逻辑填空": "词锋药剂", "片段阅读": "鹰眼药剂",
             "数量关系": "算术师药剂", "资料分析": "统计学家药剂", "图形推理": "真视药剂", "定义判断": "律法药剂",
             "类比推理": "共鸣药剂", "论证逻辑": "辩术药剂", "形式逻辑": "逆否秘药", "一拖五": "战术家药剂"},
}
ROOT_NAMES = {
    "修仙": {"政治理论": "政理灵根", "常识判断": "常识灵根", "逻辑填空": "填空灵根", "片段阅读": "阅读灵根",
             "数量关系": "数量灵根", "资料分析": "资料灵根", "图形推理": "图推灵根", "定义判断": "定义灵根",
             "类比推理": "类比灵根", "论证逻辑": "论证灵根", "形式逻辑": "推演灵根", "一拖五": "排布灵根"},
    "玄幻": {"政治理论": "信仰天赋", "常识判断": "博学天赋", "逻辑填空": "词锋天赋", "片段阅读": "阅读天赋",
             "数量关系": "算术天赋", "资料分析": "统计天赋", "图形推理": "真视天赋", "定义判断": "律法天赋",
             "类比推理": "共鸣天赋", "论证逻辑": "辩术天赋", "形式逻辑": "推演天赋", "一拖五": "战术天赋"},
}

THEMES = {
    "修仙": {
        "realms": ["凡人", "炼气期", "筑基期", "金丹期", "元婴期", "化神期", "大乘期", "真仙"],
        "layer": "{n}层",                       # 炼气三层
        "stages": ["初期", "中期", "后期"],
        "mortal_sub": "未入道",
        "gate_items": {60: "筑基丹", 65: "凝金丹", 70: "化婴丹", 75: "化神丹", 80: "渡厄丹", 85: "登仙丹"},
        "grades": ["黄阶下品", "黄阶上品", "玄阶下品", "玄阶上品", "地阶下品", "地阶上品", "天阶下品", "天阶上品"],
        "tiers": ["黄阶", "玄阶", "地阶", "天阶"],
        "pill_grades": ["下品", "中品", "上品"],
        "thunders": {"recite": "心法雷", "wrong": "心魔雷", "apply": "问道雷", "final": "紫霄神雷"},
        "tutor_face": "🌸",
        "world": ("世界观（东方修仙）：学员是踏上仙途的修士，目标是在“飞升大典”（国考）上飞升（上岸）。"
                  "行测各板块对应一条灵根，每个板块的知识骨架是“功法”，每一章是“一重”，【术语】是必须一字不差的“口诀”；"
                  "默写叫“背诵口诀”，费曼讲解叫“论道”，应用小题叫“试剑”，做错过的题是“心魔”（做对叫斩心魔，没斩掉会心魔复生），"
                  "复查叫“温养道基”（失败叫根基松动）；分数对应境界：凡人50、炼气51–59（一至九层）、筑基60、金丹65、元婴70、化神75、大乘80、真仙85；"
                  "突破大境界要“渡劫”（连续闯过几道天雷：心法雷背口诀、心魔雷重做错题、问道雷答应用题、最后一道紫霄神雷来自最弱灵根），"
                  "并且最近两次“宗门大比”（模考）都要达到该境界分数线；灵根品阶分天地玄黄各上下品；"
                  "加练叫炼丹服丹；专注修炼叫闭关；连续修炼叫“周天不息”；请假叫“告假玉简”；理想进度叫“天道进度”；"
                  "学习过久或连续失败会“走火入魔”，要调息。说话时自然地用这些说法，但判题内容必须严谨准确。"),
        "terms": {
                        'nav.bank': '🗼 试炼塔',
            'bank': '真题试炼',
            'bank_review': '伏魔再战',
            'bank_library': '真题玉简',
            'bank_remaining': '待闯关卡',
            'bank_wrong': '心魔残影',
            'bank_start': '入塔试炼',
            'bank_resume': '继续登塔',
            'bank_pause': '暂离试炼塔（保存进度）',
            'bank_next': '闯下一关',
            'bank_result': '查看试炼战报',
            'bank_history': '试炼战绩',
            'bank_rank.0': '磨砺道心',
            'bank_rank.1': '道基渐稳',
            'bank_rank.2': '剑心通明',
            'bank_rank.3': '破阵无伤',
            'bank_intro': '百层试炼塔，以真题验功法。每完成一批新玉简便登高一层，失手留下的心魔也要记得回头斩除。',
            'bank_good': '这一剑落得准。记住所用功法，别只记答案。',
            'bank_bad': '心魔已留下残影。先看清错因，待伏魔再战时把它斩去。',
            'bank_close': '本轮试炼已结。把失手的关卡练透，才算将功法化为本领。',
            'bank_empty': '玉简已练完，添入新真题后再来入阵。',
            'bank_no_wrong': '心魔残影已清，继续稳固道基。',
            'bank_unit': '关',
            'bank_record': '收录心魔残影',
            "brand": "☯ 行测修仙传", "nav.home": "🏯 洞府", "nav.train": "🧘 修炼", "nav.skeleton": "📜 藏经阁",
            "nav.wrong": "👹 心魔录", "nav.pill": "⚗ 丹房", "nav.log": "📖 修仙录", "nav.settings": "⚙ 设置",
            "minutes": "今日修炼", "lecture": "听道", "lecture_title": "听道 · 闻法记", "study": "修炼",
            "lecture_hint": "在别处听高人讲法（看网课）的时辰，也是修行。听完来此记一笔，与修炼合计每日功行。",
            "xp": "修为", "realm": "境界", "score": "道行（预估分）",
            "streak": "周天不息", "ideal": "天道进度", "lap": "大周天", "batch": "重秘境",
            "skeleton": "功法", "item": "重", "term": "口诀", "thought": "心得",
            "teach": "传授", "recite": "背诵口诀", "feynman": "论道", "example": "化法为境（举例）", "apply": "试剑", "wrong": "心魔", "kill": "斩心魔",
            "redo": "心魔复生", "review": "温养道基", "rust": "根基松动", "speedrun": "重温功法",
            "levels": "未入门,小成,大成,圆满", "tasks": "今日功课", "side": "支线", "boss": "宗门大比",
            "ascend": "飞升大典", "leave": "告假玉简", "practice": "演武", "practice_title": "演武 · 历练记", "selfstudy": "静修", "selfstudy_title": "静修 · 温养记", "tribulation": "渡劫", "bottleneck": "瓶颈",
            "root": "灵根", "pill": "丹药", "alchemy": "炼丹", "pill_room": "丹房", "retreat": "闭关", "retreat_end": "出关",
            "epiphany": "顿悟", "qi": "走火入魔", "dao": "道心", "weekly": "宗门周常", "bag": "储物袋", "heal": "疗伤",
            "demon_rank": "心魔榜", "tutor_room": "师尊的静室", "chat_btn": "向师尊请教", "breakthrough": "突破",
            "hero_empty_id": "无名散修",
        },
    },
    "玄幻": {
        "realms": ["平民", "见习学徒", "青铜骑士", "白银骑士", "黄金圣骑士", "秘银剑圣", "龙骑士", "神域·上岸者"],
        "layer": "{n}星",
        "stages": ["下位", "中位", "上位"],
        "mortal_sub": "未觉醒",
        "gate_items": {60: "青铜徽记", 65: "白银徽记", 70: "黄金徽记", 75: "秘银徽记", 80: "龙之徽记", 85: "神域徽记"},
        "grades": ["普通Ⅰ", "普通Ⅱ", "精良Ⅰ", "精良Ⅱ", "史诗Ⅰ", "史诗Ⅱ", "传说Ⅰ", "传说Ⅱ"],
        "tiers": ["普通", "精良", "史诗", "传说"],
        "pill_grades": ["劣质", "标准", "完美"],
        "thunders": {"recite": "咒文关", "wrong": "魔物关", "apply": "贤者之问", "final": "终焉之门"},
        "tutor_face": "🔮",
        "world": ("世界观（西方玄幻）：这里是“王立行测魔法学院”。学员是冒险者，目标是在“封神典礼”（国考）上封神（上岸）。"
                  "行测各板块对应一种元素天赋；每个板块的知识骨架是“咒文书”，每一章是一章咒文，【术语】是必须一字不差的“咒文真名”；"
                  "默写叫“咏唱咒文”，费曼讲解叫“传授奥义”，应用小题叫“实战演练”，做错过的题是“魔物”（没讨伐成功会卷土重来），"
                  "复查叫“驱散遗忘”（失败叫遗忘诅咒）；分数对应位阶：平民50、见习学徒51–59（一至九星）、青铜骑士60、白银骑士65、"
                  "黄金圣骑士70、秘银剑圣75、龙骑士80、神域·上岸者85；晋升大位阶要通过“晋升试炼”并在最近两次“竞技场”（模考）达线；"
                  "加练叫调配药剂；专注修炼叫冥想；连续打卡叫“圣火连燃”；请假叫“休憩卷轴”；理想进度叫“命运之线”；"
                  "学习过久或连续失败会“魔力过载”。说话时自然地用这些说法，但判题内容必须严谨准确。"),
        "terms": {
                        'nav.bank': '🗼 试炼塔',
            'bank': '真题试炼',
            'bank_review': '魔物再战',
            'bank_library': '真题卷轴',
            'bank_remaining': '待闯关卡',
            'bank_wrong': '魔物残影',
            'bank_start': '进入试炼',
            'bank_resume': '继续探索',
            'bank_pause': '返回营地（保存进度）',
            'bank_next': '挑战下一关',
            'bank_result': '查看冒险战报',
            'bank_history': '冒险战绩',
            'bank_rank.0': '磨砺意志',
            'bank_rank.1': '战技渐熟',
            'bank_rank.2': '奥义精通',
            'bank_rank.3': '完美通关',
            'bank_intro': '百层试炼塔，以真题验奥义。完成新卷轴便可继续登高，失手的魔物残影留待再次讨伐。',
            'bank_good': '这次施法很准确。记住判断的依据，下一关继续。',
            'bank_bad': '魔物留下了残影。先查清失手原因，再来完成讨伐。',
            'bank_close': '本轮冒险结束。把失手的关卡重新练透，才算掌握真正的奥义。',
            'bank_empty': '卷轴已练完，添入新真题后继续探索。',
            'bank_no_wrong': '魔物残影已清，继续精进战技。',
            'bank_unit': '关',
            'bank_record': '收录魔物残影',
            "brand": "⚔ 行测魔法学院", "nav.home": "🏕 营地", "nav.train": "⚔ 冒险", "nav.skeleton": "📕 咒文书",
            "nav.wrong": "👾 魔物图鉴", "nav.pill": "⚗ 炼金室", "nav.log": "📖 编年史", "nav.settings": "⚙ 设置",
            "minutes": "今日修炼", "lecture": "听讲", "lecture_title": "听讲 · 课堂笔记", "study": "修炼",
            "lecture_hint": "在别处旁听导师讲课（看网课）的时间也算修行。听完来此登记，与修炼合计每日学时。",
            "xp": "经验", "realm": "位阶", "score": "战力预估",
            "streak": "圣火连燃", "ideal": "命运之线", "lap": "轮征程", "batch": "层地下城",
            "skeleton": "咒文书", "item": "章", "term": "咒文真名", "thought": "思路",
            "teach": "导师讲解", "recite": "咏唱咒文", "feynman": "传授奥义", "example": "构筑幻境（举例）", "apply": "实战演练", "wrong": "魔物", "kill": "讨伐魔物",
            "redo": "卷土重来", "review": "驱散遗忘", "rust": "遗忘诅咒", "speedrun": "重温咒文",
            "levels": "未习得,能咏唱,能讲授,已精通", "tasks": "今日委托", "side": "支线任务", "boss": "竞技场",
            "ascend": "封神典礼", "leave": "休憩卷轴", "practice": "野外历练", "practice_title": "野外历练 · 实战日志", "selfstudy": "自习", "selfstudy_title": "自习 · 温故笔记", "tribulation": "晋升试炼", "bottleneck": "瓶颈",
            "root": "天赋", "pill": "药剂", "alchemy": "调配药剂", "pill_room": "炼金室", "retreat": "冥想", "retreat_end": "结束冥想",
            "epiphany": "灵感迸发", "qi": "魔力过载", "dao": "意志", "weekly": "公会周常", "bag": "背包", "heal": "治疗",
            "demon_rank": "弱点榜", "tutor_room": "学姐的研究室", "chat_btn": "找学姐聊聊", "breakthrough": "晋升",
            "hero_empty_id": "无名冒险者",
        },
    },
}

DEFAULT_THEME = "修仙"


def get(name):
    return THEMES.get(name) or THEMES[DEFAULT_THEME]


def band_of(score_int):
    for i, (lo, hi, kind) in enumerate(BANDS):
        if lo <= score_int < hi:
            return i, lo, hi, kind
    return (0,) + BANDS[0] if score_int < 50 else (len(BANDS) - 1,) + BANDS[-1]


def sub_stage(score_int):
    """返回 (大境界序号, 小境界名(不含大境界名), 小境界起始分, 小境界结束分(不含))，风格无关的部分"""
    i, lo, hi, kind = band_of(score_int)
    if kind == "mortal":
        return i, None, lo, hi
    if kind == "layers":
        return i, ("layer", score_int - lo + 1), score_int, score_int + 1
    if kind == "stages":
        off = score_int - lo
        k = 0 if off < 2 else (1 if off < 4 else 2)
        a = lo + (0, 2, 4)[k]
        b = lo + (2, 4, 5)[k]
        return i, ("stage", k), a, b
    return i, None, lo, hi


def realm_name(theme, score_int):
    """如 “炼气期三层” → 显示为 “炼气三层”；“筑基期中期” → “筑基中期”；凡人 → “凡人 · 未入道”"""
    t = get(theme)
    i, sub, _, _ = sub_stage(score_int)
    big = t["realms"][i]
    short = big[:-1] if big.endswith("期") else big
    if sub is None:
        return f"{big} · {t['mortal_sub']}" if i == 0 else big
    if sub[0] == "layer":
        return short + t["layer"].format(n=CN_NUM[sub[1] - 1])
    return short + t["stages"][sub[1]]


def realm_of_gate(theme, gate):
    return get(theme)["realms"][band_of(gate)[0]]

