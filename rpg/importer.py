"""
导入真题：把模考复盘、OCR 出来的 txt 一键整理进试炼塔题库（训练/题库/<板块>真题.md），不需要 AI 逐题核对。

三种来源：
- 模考：读 xingce-mokao-split 拆好的 FB模考试卷复盘/板块复盘/第N季/NN-板块.md（按 PDF 原文拆，题干、选项、答案、截图都准确）。
  截图复制到 训练/题库/图片/<板块>/，编号 粉笔36季-086，来源“粉笔第36季模考”。
- txt：练习册（题号 + ABCD 选项）或粉笔试卷的 OCR 文字。能干净拆开、认出板块的题直接入库；
  拆不干净的写进 训练/题库/_待修/<名称>.md，用户在 Obsidian 里改好后在网页上“重新导入”。
  粉笔试卷的 OCR 文字顺序会乱，没有对应的板块复盘时整份都进待修，建议先用 xingce-mokao-split 拆 PDF。
- 待修文件：改好（“### 检查”下清空）的题入库，其余留着。

知识点：按问法关键词猜（削弱、加强、前提假设……），猜不出写“待分类”；可以用 DeepSeek 补（classify，每次一批，只发题干）。
答案：读不到就写“（待补）”，这样的题试炼塔先不出；拿到答案表后用 fill_answers 批量补。
解析一律“（待补）”。

只追加题目、只改“待分类”的知识点和“（待补）”的答案，已有题目的其他内容和编号一概不动（试炼塔用编号记作答历史）。
拆题规则与 obsidian-to-xingce 仓库 skills/xingce-tiku/scripts/tiku.py 一致（那边是给 AI 精修用的命令行版本）。
"""
import json
import re
import shutil
from collections import Counter
from pathlib import Path

from . import ai, skeleton, vault

BOARDS = ["政治理论", "常识判断", "逻辑填空", "片段阅读", "数量关系", "图形推理", "定义判断",
          "类比推理", "论证逻辑", "形式逻辑", "一拖五", "资料分析"]
ALIAS = {"类比关系": "类比推理", "中心理解": "片段阅读", "语句排序": "片段阅读", "语句表达": "片段阅读"}
IMAGE_BOARDS = {"图形推理", "资料分析"}          # 题目文字里没有图，没图做不了
TODO = "（待补）"
UNSORTED = "待分类"
FIX_DIR = "_待修"

# 没有骨架时给 AI 的知识点范围（有骨架时用骨架的大项名，见 topic_options）
TOPICS = {
    "政治理论": "马克思主义哲学、政治经济学、毛泽东思想、中国特色社会主义理论、党史、时政",
    "常识判断": "法律、政治、经济、历史、地理、科技、文学文化、生活常识",
    "逻辑填空": "实词辨析、成语辨析、实词+成语",
    "片段阅读": "中心理解、细节判断、标题填入、语句填空、接语选择、语句排序",
    "数量关系": "工程、行程、经济利润、排列组合、概率、容斥、几何、和差倍比、周期、溶液、年龄、最值、数字推理",
    "图形推理": "位置规律、样式规律、属性规律、数量规律、特殊规律、空间重构、截面图、立体拼合、分类分组",
    "定义判断": "单定义、多定义",
    "类比推理": "语义关系、逻辑关系、语法关系、常识关系",
    "论证逻辑": "削弱、加强、前提假设、解释、评价、论证结构",
    "形式逻辑": "翻译推理、真假推理、分析推理、归纳推理",
    "一拖五": "分析推理组题",
    "资料分析": "基期量、现期量、增长量、增长率、比重、平均数、倍数、混合增长率、综合分析",
}

SECTION_RE = re.compile(r"^[一二三四五六七八九十]+\s*[\.．、]\s*(政治理论|常识判断|言语理解与表达|数量关系|判断推理|资料分析)")
ANS_RE = re.compile(r"正确答案[:：]\s*([A-D]?)\s*(?:你的答案[:：]\s*([A-D]?))?")
HEADER_TAIL_KW = ("本部分", "所给出的", "在这部分", "根据题目要求", "请根据", "要求你", "进行分析", "恰当的答案", "最恰当的")
ARGUMENT_KW = ("质疑", "削弱", "支持", "加强", "前提", "假设", "解释", "反驳", "反对", "评价", "漏洞", "结论")
FORMAL_KW = ("可以得出", "可以推出", "能够推出", "能推出", "一定为真", "一定为假", "不能确定", "必然为真",
             "必然为假", "可能为真", "哪项安排", "推出以下", "一定可以得出", "由此可以推出", "为真", "为假",
             "真话", "假话", "说对", "说错", "必然正确", "推论", "判断正确", "判断错误", "一定正确", "一定错误")
FIGURE_KW = ("填入问号处", "分为两类", "正方体", "多面体", "截面", "展开图", "视图", "立体图形", "拼合", "组合而成")
CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


class ImportError_(ValueError):
    pass


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fp:
        fp.write(text)


def _cn2int(s):
    if s.isdigit():
        return int(s)
    total, num = 0, 0
    for ch in s:
        if ch == "十":
            total += (num or 1) * 10
            num = 0
        else:
            num = CN_NUM.get(ch, 0)
    return total + num


def norm_stem(s, opts=None):
    """查重指纹：去掉来源括号、空白和标点后的【完整】题干 + 图片文件名 + 四个选项。
    不能只取开头几十个字、也不能丢掉图片：图形推理的题干都是同一句“从所给的四个选项中……”，
    资料分析同组几道题开头都是同一段材料，只看开头会把不同的题误当成重复。"""
    s = re.sub(r"^（[^）]{0,30}）", "", (s or "").strip())
    s = re.sub(r"!\[\[([^\]|]*)(?:\|[^\]]*)?\]\]", lambda m: " " + Path(m.group(1)).name + " ", s)
    if opts:
        s += "".join("%s%s" % (k, opts.get(k, "")) for k in "ABCD")
    return re.sub(r"[\s\W_]+", "", s)


def safe_name(s):
    return re.sub(r'[\\/:*?"<>|\s]+', "_", (s or "").strip())[:40]


# ---------------------------------------------------------------- 清洗与来源
def clean_lines(text):
    """去掉页码、广告、页眉页脚、在全文重复很多次的书眉"""
    lines = [ln.strip().replace("　", " ") for ln in (text or "").splitlines()]
    lines = [ln for ln in lines if ln]
    count = Counter(ln for ln in lines if len(ln) <= 40)
    out = []
    for ln in lines:
        if re.match(r"^≦\s*\d+\s*≧$", ln) or re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}(:\d{2})?$", ln):
            continue
        if re.match(r"^(\d{1,3}[\.．]\s*)+$", ln) or re.match(r"^\d{1,4}$", ln):
            continue
        if re.search(r"本试卷由粉笔用户|第\s*\d+\s*页\s*[，,]\s*共\s*\d+\s*页|扫描二维码|下载「粉笔」|听课刷题|就用粉笔"
                     r"|公考资料|V[:：]\s*\w{6,}|SIHAIGONGKAO|微信|关注公众号", ln):
            continue
        if count.get(ln, 0) >= 4 and not re.match(r"^[A-D][\.．。:：、]", ln) \
                and not re.search(r"填入问号处|正确答案|^[A-D]$", ln) and not SET_RE.match(ln):
            continue
        out.append(ln)
    return out


def detect_source(lines):
    """(来源, 编号前缀, 季数)：粉笔第N季模考 / 20XX年国考 / 20XX年XX省考；认不出返回空"""
    head = "\n".join(lines[:15])
    m = re.search(r"第([一二三四五六七八九十百\d]+)季", head)
    if m and ("模考" in head or "粉笔" in head):
        n = _cn2int(m.group(1))
        return "粉笔第%d季模考" % n, "粉笔%d季" % n, n
    m = re.search(r"(20\d{2})年.{0,12}?(国家公务员|国考)", head)
    if m:
        return "%s年国考" % m.group(1), "%s国考" % m.group(1), None
    m = re.search(r"(20\d{2})年.{0,6}?([一-鿿]{2,3}?)省.{0,10}?(公务员|省考)", head)
    if m:
        return "%s年%s省考" % (m.group(1), m.group(2)), "%s%s省考" % (m.group(1), m.group(2)), None
    return "", "", None


# ---------------------------------------------------------------- 选项与分类
OPT_FENBI = re.compile(r"(?:(?<=\s)|^)([A-D])[\.．]")
# 练习册 OCR：选项字母后的标点五花八门（A。B．C：D、），有时没有标点，C 常被识别成小写 c
OPT_BOOK = re.compile(r"(?:(?<=[\s。？?！!：:”）)])|^)([A-Dc])(?:\s*[\.．。:：、，,]|(?=[一-鿿“（(\d]))")


def split_options(text, scrambled):
    """(题干, {字母: 选项}, 问题)。选项常排两栏（A C 一行、B D 一行），粉笔 OCR 还会把 B D 挪到答案行后面，
    所以不按顺序找：题干 = 第一个 A 之前，B C D 各取 A 之后第一次出现的位置"""
    rx = OPT_FENBI if scrambled else OPT_BOOK
    marks = [(m.start(), m.end(), m.group(1).upper()) for m in rx.finditer(text)]
    first_a = next((mk for mk in marks if mk[2] == "A"), None)
    if not scrambled:
        # 练习册：题干里常有“A型血”“A领导”“特征A”，取【最后一个】后面还跟着 B、C、D 的 A 作为选项开头
        full = [mk for mk in marks if mk[2] == "A" and {"B", "C", "D"} <= {x[2] for x in marks if x[0] > mk[0]}]
        if full:
            first_a = full[-1]
    if not first_a:
        return text.strip(), {}, ["没找到选项"]
    chosen, seen = [first_a], {"A"}
    for mk in marks:
        if mk[0] > first_a[0] and mk[2] not in seen:
            seen.add(mk[2])
            chosen.append(mk)
    chosen.sort()
    stem = text[:chosen[0][0]].strip()
    opts = {}
    for i, (s, e, letter) in enumerate(chosen):
        end = chosen[i + 1][0] if i + 1 < len(chosen) else len(text)
        opts[letter] = re.sub(r"\s+", " ", text[e:end]).strip()
    problems = []
    missing = [x for x in "ABCD" if not opts.get(x)]
    if missing:
        problems.append("缺选项 " + "".join(missing))
    if any(len(v) > 160 for v in opts.values()):
        problems.append("有选项太长，可能吞进了下一题")
    if not scrambled and any(re.search(r"(?:^|\s)[A-D][\.．。:：、]\S", v) for v in opts.values()):
        problems.append("选项里还夹着另一组选项标记，可能拆错了")
    return stem, opts, problems


LOGIC_STRONG = re.compile(r"如果为真|若为真|削弱|加强|质疑|反驳|前提|假设|一定为真|一定为假|真话|假话|推理结构|论证方式")
# 言语问法要按完整短语认：“同意在本周末”里也有“意在”，“依次填入图形中”是逻辑题
VERBAL_FILL = re.compile(r"填入(?:文中|上文)?(?:画|划)横线|横线(?:处|部分)|依次填入.{0,4}最恰当")
VERBAL_READ = re.compile(r"这段文字|这段话|文段|上述文字|(?:意在|旨在|主要)(?:说明|强调|表明|告诉|指出|阐述|揭示|突出|介绍|讲|论述|讨论)|"
                         r"重新排列|语序正确|排序正确|标题|接下来最可能|下文最可能|语句填入|填入文中")
SEQ_ONLY = re.compile(r"^[\s①-⑨\d、，,]+$")


def verbal_board(stem, opts):
    """言语理解：逻辑填空（选词填空）还是片段阅读（主旨、意图、标题、排序、语句填入）；认不出返回空"""
    if "____" in stem and opts:   # PDF 导入时插回的填空横线：选项是词 → 逻辑填空，是整句 → 片段阅读（语句填空）
        return "逻辑填空" if all(len(re.sub(r"[\s\W_]+", "", v)) <= 12 for v in opts.values()) else "片段阅读"
    if VERBAL_FILL.search(stem):
        short = opts and all(len(re.sub(r"[\s\W_]+", "", v)) <= 12 for v in opts.values())
        return "逻辑填空" if "依次填入" in stem or short else "片段阅读"
    if VERBAL_READ.search(stem):
        return "片段阅读"
    return ""


def verbal_by_options(opts):
    """言语类练习册里问法认不出时：选项是一串序号（①③②④）→ 语句排序（片段阅读）；选项都是短词 → 逻辑填空；否则片段阅读"""
    vals = [v for v in opts.values() if v]
    if len(vals) < 4:
        return ""
    if all(SEQ_ONLY.match(v) for v in vals):
        return "片段阅读"
    if all(len(re.sub(r"[\s\W_]+", "", v)) <= 10 for v in vals):
        return "逻辑填空"
    return "片段阅读"


def guess_board(section, stem, opts):
    s = stem
    if section in ("政治理论", "常识判断", "数量关系", "资料分析"):
        return section
    if section == "言语理解与表达":
        if "重新排列" in s or "语序正确" in s or "排序" in s:
            return "片段阅读"
        short = opts and all(len(v) <= 12 for v in opts.values())
        return "逻辑填空" if "依次填入" in s or ("横线" in s and short) else "片段阅读"
    if not section and not LOGIC_STRONG.search(re.split(r"[。！？”]", s.rstrip())[-1]):   # 练习册不知道大题：问句不是明显的逻辑问法时，先按言语的问法认
        v = verbal_board(s, opts)
        if v:
            return v
    figure_opts = not opts or all(re.sub(r"[\s\W_]+", "", v).upper() in ("", "A", "B", "C", "D") for v in opts.values())
    # 有判断推理大题时题干关键词就够；练习册（不知道大题）还要求选项本身是图，免得“组合而成”之类的词误判
    if (any(k in s for k in FIGURE_KW) and (section or figure_opts)) or (opts and figure_opts):
        return "图形推理"
    if "定义" in s and re.search(r"(不)?(属于|符合)", s):
        return "定义判断"
    if len(s) <= 40 and not re.search(r"以下|下列|哪项|哪句", s) and (re.search(r"(对于|相当于)", s) or (opts and all(re.search(r"[:：]", v) for v in opts.values() if v))):
        return "类比推理"
    if any(k in re.sub(r"(如果|若|假如|假设)[^，,：:]{0,4}为真", "", s) for k in FORMAL_KW):  # “以下哪项如果为真”是论证题问法
        return "形式逻辑"
    if any(k in s for k in ARGUMENT_KW):
        return "论证逻辑"
    return ""


# ---------------------------------------------------------------- OCR 符号修复：①②③、ⅠⅡⅢ
CIRCLED = "①②③④⑤⑥⑦⑧⑨"
ROMAN = {"I": "Ⅰ", "II": "Ⅱ", "III": "Ⅲ", "IV": "Ⅳ", "V": "Ⅴ", "VI": "Ⅵ"}
# 只由序号和连接词组成的选项（“①③④”“仅Ⅰ和Ⅲ”“@②4”“I、II都推不出”）
_SEQ_OPT = re.compile(r"^[\s①-⑨Ⅰ-Ⅵ\dIVHl@Q?？、，,和与及或仅只有都是不能推出得只均]*$")
_ROMAN_RUN = re.compile(r"(?<![A-Za-z])(IV|VI|V|III|II|I)(?![A-Za-z])")


def fix_symbols(stem, opts):
    """OCR 常把 ① 认成 @ / Q / 1，④ 认成 4，Ⅰ Ⅱ Ⅲ 认成 I / II / III（甚至 H）。只在明确是序号的地方还原：
    - 题干里已有 ①② 序列时，紧接着序列、出现在句首 / 标点后的数字（或 @、Q）还原成下一个圈号；
    - 题干用 I / II / III 当陈述编号（后面跟标点或汉字）时还原成 Ⅰ Ⅱ Ⅲ；
    - 选项只由序号和“和 / 仅 / 都”等组成时，按题干用的是圈号还是罗马数字整体还原。
    返回 (题干, 选项, 问题)；还原后同一选项里序号重复（如 ②②）说明 OCR 丢了信息，交给待修核对"""
    problems = []
    uses_circled = bool(re.search("[①-⑨]", stem)) or any(re.search("[①-⑨]", v) for v in opts.values())
    uses_roman = bool(re.search("[Ⅰ-Ⅵ]", stem) or re.search(r"(?<![A-Za-z])I{1,3}(?:[\.．。:：、]|(?=[\u4e00-\u9fff]))", stem)) \
        or any(re.search(r"(?<![A-Za-z])I{1,3}(?![A-Za-z])", v) and _SEQ_OPT.match(v) for v in opts.values())
    if uses_circled:
        out, last, i = [], 0, 0
        while i < len(stem):
            ch = stem[i]
            if ch in CIRCLED:
                last = CIRCLED.index(ch) + 1
            elif last and i and (stem[i - 1] in " \t\n。；;，,：:）)" or stem[i - 1] in CIRCLED) \
                    and ((ch.isdigit() and int(ch) == last + 1) or (ch in "@Q" and last == 0)) \
                    and i + 1 < len(stem) and re.match(r"[\u4e00-\u9fffA-Z“（(]", stem[i + 1]):
                last += 1
                ch = CIRCLED[last - 1]
            out.append(ch)
            i += 1
        stem = "".join(out)
        stem = re.sub(r"(^|[\s。；;：:])[@Q](?=[\u4e00-\u9fff])", lambda m: m.group(1) + "①", stem)
    if uses_roman:
        stem = re.sub(r"(?<![A-Za-z])(IV|VI|V|III|II|I)(?=[\.．。:：、\s]|[\u4e00-\u9fff])", lambda m: ROMAN[m.group(1)], stem)
    new = {}
    for k, v in opts.items():
        if v and _SEQ_OPT.match(v) and len(v) <= 16:
            if uses_circled and not uses_roman:
                v = re.sub(r"[@Q]", "①", v)
                v = re.sub(r"[1-9]", lambda m: CIRCLED[int(m.group(0)) - 1], v)
            elif uses_roman:
                v = v.replace("H", "II").replace("l", "I")
                v = _ROMAN_RUN.sub(lambda m: ROMAN[m.group(1)], v)
            v = re.sub(r"\s*[,，]\s*", "、", v)   # 序号之间统一用顿号
            marks = re.findall("[①-⑨Ⅰ-Ⅵ]", v)
            if len(marks) != len(set(marks)) or re.search(r"[?？@Q]", v):
                problems.append("选项 %s 的序号可能被 OCR 认错（%s），请对照原书" % (k, v))
        new[k] = v
    return stem, new, problems


def board_by_options(opts):
    """问法里认不出板块时，按选项的样子判断逻辑题：
    选项很短，或长度相近又有共同的字（“栖霞镇 / 莲花镇 / 五溪镇”“甲和乙 / 乙和丙”“仅I / 仅II”）→ 形式逻辑；
    选项长、长短不一（一句一句的论据）→ 论证逻辑。只在逻辑类练习册里用（见 _collect）"""
    vals = [re.sub(r"[\s\W_]+", "", v) for v in opts.values()]
    if len(vals) < 4 or not all(vals):
        return ""
    lens = [len(v) for v in vals]
    common = set(vals[0]).intersection(*map(set, vals[1:]))
    if max(lens) <= 6 or (max(lens) - min(lens) <= 4 and max(lens) <= 20 and common):
        return "形式逻辑"
    return "论证逻辑"


def guess_topic(board, stem):
    tail = stem[-80:]
    if board == "论证逻辑":
        for kws, name in ((("削弱", "质疑", "反驳", "反对"), "削弱"), (("支持", "加强"), "加强"),
                          (("前提", "假设"), "前提假设"), (("解释",), "解释"), (("评价",), "评价")):
            if any(k in tail for k in kws):
                return name
    if board == "形式逻辑":
        if re.search(r"真话|假话|说对|说错|只有一[个句人].{0,4}(真|假|对|错)", stem):
            return "真假推理"
    return UNSORTED


# ---------------------------------------------------------------- 拆题
def parse_fenbi(lines):
    """粉笔试卷 OCR：每题以“正确答案：X 你的答案：Y”结尾；答案行后面可能挂着本题剩下的选项"""
    qs, buf, section = [], [], None
    for ln in lines:
        m = SECTION_RE.match(ln)
        if m:
            if buf and qs:
                qs[-1]["tail"] += buf
            buf, section = [], m.group(1)
            continue
        a = ANS_RE.search(ln)
        if a:
            before = ln[:a.start()].strip()
            if before:
                buf.append(before)
            if qs:
                while buf and re.match(r"^[A-D][\.．]", buf[0]):
                    qs[-1]["tail"].append(buf.pop(0))
            qs.append({"section": section, "lines": buf, "tail": [], "answer": a.group(1)})
            buf = []
            continue
        if section and any(k in ln for k in HEADER_TAIL_KW) and not buf:
            continue
        buf.append(ln)
    if buf and qs:
        qs[-1]["tail"] += buf
    out = []
    for i, q in enumerate(qs, 1):
        stem, opts, problems = split_options("\n".join(q["lines"] + q["tail"]), scrambled=True)
        problems.append("粉笔 OCR 文字顺序可能错乱，对照原卷核对")
        out.append({"num": i, "group": 0, "stem": stem, "options": opts, "answer": q["answer"],
                    "board": guess_board(q["section"], stem, opts), "problems": problems})
    return out


# 题号：后面有标点时接什么都行（“15：2008年…”“2.《道路交通安全法》…”）；没有标点时后面必须是汉字等（“18有些人…”）
START_RE = re.compile(r"(?:(?<=[\s。？?！!”）)])|^)([1-9]\d{0,2})(?:\s*[\.．。:：、，,]\s*(?=\S)|\s*(?=[\u4e00-\u9fff“\"（(《A-Z]))")


# 练习册每套开头的标记行：“练习题03”“05 练习题”“页07 练习题”“o1 练习题”（OCR 常把序号挪到前面或丢掉），
# 以及“拔高刷题十一”“专项练习三”这类中文数字的写法
SET_RE = re.compile(r"^[#＃\w页\s]{0,5}(?:练习题?|刷题|专项练习|模拟题?|套题|测试题?)\s*(?:\d{1,3}|[一二三四五六七八九十百零]{1,4})?\s*套?$")


def _starts(text):
    """一段文字里的题目起点：题号连续，四个选项出完才可能开始下一题；允许漏认一个题号"""
    cands = [(m.start(), m.end(), int(m.group(1))) for m in START_RE.finditer(text)]
    starts, last, skipped = [], 0, []

    def has_abcd(seg):
        return set("ABCD") <= {m.group(1).upper() for m in OPT_BOOK.finditer(seg)}

    for c in cands:
        n = c[2]
        if starts and not has_abcd(text[starts[-1][1]:c[0]]):
            if n == 1 and starts[-1][2] == 1:
                starts[-1] = c  # 两个“1”之间没有选项：前一个是目录里的数字
            continue
        if not starts:
            if n in (1, 2):  # 第 1 题题号没认出来时从 2 开始
                starts.append(c)
                last = n
        elif n == 1 or last < n <= last + 2:
            if n == last + 2:
                skipped.append(len(starts) - 1)
            starts.append(c)
            last = n
    return starts, skipped


def parse_book(lines, start_set=0):
    """练习册：有“练习题NN”标记就按标记分套（第几套 = 第几个有题的标记段，和答案表的“练习NN”对得上）；
    没有标记就按“题号回到 1”分套。每套里题号连续，选项按 A→B→C→D"""
    segs, cur, nums, mark = [], [], [], None
    for ln in lines:
        if SET_RE.match(ln) and len(ln) <= 12:
            segs.append(cur)
            nums.append(mark)
            cur = []
            d = re.findall(r"\d+|[一二三四五六七八九十百零]+(?=\s*套?$)", ln)
            mark = _cn2int(d[-1]) if d else None   # 标记里写的套号（“练习题16”“刷题十一”）；分上下册时下册从 16 开始
        else:
            cur.append(ln)
    segs.append(cur)
    nums.append(mark)
    texts = ["\n".join(x) for x in segs]
    by_marker = sum(bool(_starts(t)[0]) for t in texts) >= 2
    if not by_marker:
        texts, nums = ["\n".join(lines)], [None]
    out, group = [], 0
    for text, num in zip(texts, nums):
        starts, skipped = _starts(text)
        if not starts:
            continue  # 目录、封面
        if by_marker:
            # 用标记里的套号：第一套可以从任意号开始（下册），之后只接受紧跟着的号，OCR 认错 / 没认出就按上一套 +1
            ok = num is not None and 1 <= num <= 300 and (group < num <= group + 3 if group else True)
            if start_set:      # 用户指定了第一套是练习几：按顺序往后排，不看标记里的数字
                group = start_set if not group else group + 1
            else:
                group = num if ok else group + 1
        first = len(out)
        for i, (s, e, n) in enumerate(starts):
            if not by_marker and n == 1:
                group += 1
            end = starts[i + 1][0] if i + 1 < len(starts) else len(text)
            stem, opts, problems = split_options(text[e:end], scrambled=False)
            stem = re.sub(r"\s*\n\s*", "", stem)
            stem, opts, sym = fix_symbols(stem, opts)
            problems += sym
            out.append({"num": n, "group": max(group, 1), "stem": stem, "options": opts, "answer": "",
                        "board": guess_board("", stem, opts), "problems": problems})
        for i in skipped:
            q = out[first + i]
            q["problems"].append("下一题（第 %d 题）的题号没认出来，可能并在这道题的选项里" % (q["num"] + 1))
        if by_marker and starts[0][2] == 2:
            out[first]["problems"].append("这一套的第 1 题题号没认出来，可能并在别处，请核对")
    return out


def parse_review(season_dir):
    """读 xingce-mokao-split 生成的板块复盘（### 36. ❌ / 题干 / - **A.** 选项 / 正确答案：**B** / ## 材料（第a-b题））"""
    out = []
    for f in sorted(season_dir.glob("[0-9][0-9]-*.md")):
        name = re.sub(r"^\d\d-", "", f.stem)
        board = ALIAS.get(name, name)
        if board not in BOARDS:
            continue
        cur, mat, mats, in_note, mine = None, None, {}, False, []
        for ln in f.read_text(encoding="utf-8-sig", errors="ignore").split("\n"):
            mm = re.match(r"^## 材料（第(\d+)-(\d+)题）", ln)
            h = re.match(r"^### (\d+)\.", ln)
            if mm:
                mat, cur = (int(mm.group(1)), int(mm.group(2))), None
                mats[mat] = []
                continue
            if h:
                n = int(h.group(1))
                cur = {"num": n, "group": 0, "board": board, "lines": [], "options": {}, "answer": "",
                       "material": mat if mat and mat[0] <= n <= mat[1] else None, "problems": []}
                mine.append(cur)
                in_note = False
                continue
            if cur is None:
                if mat in mats and ln.strip() != "---":
                    mats[mat].append(ln)
                continue
            if ln.strip() == "---":
                cur = None
                continue
            if ln.startswith("> [!note]"):
                in_note = True
            if in_note:
                continue
            a = re.search(r"正确答案：\*\*([A-D]?)", ln)
            o = re.match(r"^\s*-\s*\*\*([A-D])[\.．]\*\*\s*(.*)$", ln)
            if a:
                cur["answer"] = a.group(1)
            elif o:
                cur["options"][o.group(1)] = o.group(2).strip()
            elif not ln.startswith(">"):
                cur["lines"].append(ln)
        for q in mine:
            # 材料是 Obsidian 折叠块（> [!abstract]- 材料文字… / > 正文）：去掉块头和行首的 >，只留正文
            mat = vault.clean_callout("\n".join(mats.get(q["material"], []))) if q["material"] else ""
            lines = ([x for x in mat.split("\n") if x.strip()] + [""] if mat else []) + q.pop("lines")
            q["stem"] = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
            # 选项就是图里的 A/B/C/D（图形推理常见）时，拆分脚本不写选项行：有截图就补成 A. A … D. D（选项看图）
            if "![[" in q["stem"] and not any(q["options"].values()):
                q["options"] = {k: k for k in "ABCD"}
            if set(q["options"]) != set("ABCD") or not all(q["options"].values()):
                q["problems"].append("复盘文件里选项不全")
        out += mine
    return sorted(out, key=lambda q: q["num"])


# ---------------------------------------------------------------- 题块（题库格式 / 待修格式）
HEAD_RE = re.compile(r"^##\s+题目\s+(.+?)\s*$", re.M)


def parse_blocks(text):
    masked = re.sub(r"^```[^\n]*\n.*?^```[^\n]*$", lambda m: " " * len(m.group(0)), text, flags=re.M | re.S)
    heads = list(HEAD_RE.finditer(masked))
    out = []
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        body = text[h.end():end]
        fields = {}
        parts = list(re.finditer(r"^###\s+(\S+)\s*$", body, re.M))
        for j, p in enumerate(parts):
            fields[p.group(1)] = body[p.end():parts[j + 1].start() if j + 1 < len(parts) else len(body)].strip()
        out.append({"id": h.group(1).strip(), "fields": fields, "start": h.start(), "end": end})
    return out


def parse_opts(s):
    # [ \t]* 而不是 \s*：空选项（“C. ”）不能把下一行的 D 项吞进来
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"^[ \t]*([A-D])[\.．、)）][ \t]*(.*)$", s or "", re.M)}


def bank_block(q):
    return ("## 题目 %s\n### 知识点\n%s\n### 题干\n%s\n### 选项\n%s\n### 答案\n%s\n### 解析\n%s\n\n"
            % (q["id"], q["topic"] or UNSORTED, q["stem"], "\n".join("%s. %s" % (k, q["options"][k]) for k in "ABCD"),
               q["answer"] if re.fullmatch(r"[A-D]", q["answer"] or "") else TODO, TODO))


def fix_block(q):
    """待修文件里的一道题：比题库多 板块 / 来源 / 检查 三节，改好后清空“检查”再在网页上重新导入"""
    return ("## 题目 %s\n### 板块\n%s\n### 知识点\n%s\n### 来源\n%s\n### 题干\n%s\n### 选项\n%s\n### 答案\n%s\n### 检查\n%s\n\n"
            % (q["id"], q["board"] or UNSORTED, q["topic"] or UNSORTED, q["source"], q["stem"],
               "\n".join("%s. %s" % (k, q["options"].get(k, "")) for k in "ABCD"), q["answer"] or TODO,
               "\n".join("⚠ " + p for p in q["problems"])))


def existing(bank):
    """所有题库已有的 编号 和 题干指纹（跨板块查重）"""
    ids, stems = {}, set()   # ids: 编号 → 题干指纹（判断“同编号是不是同一道题”用）
    for f in bank.glob("*真题.md"):
        for b in parse_blocks(f.read_text(encoding="utf-8-sig", errors="ignore")):
            k = norm_stem(b["fields"].get("题干", ""), parse_opts(b["fields"].get("选项")))
            ids[b["id"]] = k
            if len(k) >= 12:
                stems.add(k)
    return ids, stems


def same_question(a, b):
    """两个题干指纹是不是同一道题（允许 OCR 修复、来源括号等小改动）"""
    import difflib
    a, b = re.sub(r"[①-⑨Ⅰ-Ⅵ\dIVHl@Q]", "", a)[:120], re.sub(r"[①-⑨Ⅰ-Ⅵ\dIVHl@Q]", "", b)[:120]
    return not a or not b or difflib.SequenceMatcher(None, a, b).ratio() >= 0.6


def with_source(stem, source):
    """来源写在题干最前面；题干以图片开头时来源单独一行"""
    if not source or stem.startswith("（" + source):
        return stem
    return "（%s）%s%s" % (source, "\n" if stem.startswith("![[") else "", stem)


def place_images(paths, board, qid, stem, dry):
    """模考截图 ![[S36-Q066.png]] 复制到 训练/题库/图片/<板块>/<编号>.png（材料图 <前缀>-M111-115.png），改成库内路径。
    返回 (新题干, 缺的图)"""
    missing, seq = [], [0]
    img_dir = paths.train / "题库" / "图片" / board
    prefix = qid.rsplit("-", 1)[0]

    def repl(m):
        name = m.group(1).strip()
        if name.startswith("训练/"):
            if not (paths.vault / name).is_file():
                missing.append(name)
            return m.group(0)
        base = Path(name).name
        hit = next((p for p in (paths.vault / name, img_dir / base) if p.is_file()), None)
        if not hit and paths.seasons and paths.seasons.is_dir():
            hit = next(iter(paths.seasons.rglob(base)), None)
        mat = re.match(r"S\d+-(M\d+-\d+)", base)
        if mat:
            new = img_dir / ("%s-%s%s" % (prefix, mat.group(1), Path(base).suffix))
        else:
            seq[0] += 1
            new = img_dir / ("%s%s%s" % (qid, "" if seq[0] == 1 else "-%d" % seq[0], Path(base).suffix or ".png"))
        if not hit:
            missing.append(base)
            return m.group(0)
        if not dry and not new.exists():
            img_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(hit, new)
        return "![[%s]]" % new.relative_to(paths.vault).as_posix()

    stem = re.sub(r"!\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", repl, stem)
    if board in IMAGE_BOARDS and "![[" not in stem:
        missing.append("训练/题库/图片/%s/%s.png" % (board, qid))
    return stem, missing


# ---------------------------------------------------------------- 新模考 PDF：拆分（调用 xingce-mokao-split 的脚本）
PDF_DIR = ("FB模考试卷复盘", "模考试卷")
SEASON_RE = re.compile(r"第([一二三四五六七八九十百零\d]+)季")


def pdf_dir(paths):
    return paths.vault.joinpath(*PDF_DIR)


def split_script(paths):
    """xingce-mokao-split 的拆分脚本（安装脚本装在 copilot/skills 和 .opencode/skills）"""
    for root in ("copilot/skills", ".opencode/skills"):
        f = paths.vault / root / "xingce-mokao-split" / "scripts" / "split_mokao.py"
        if f.is_file():
            return f
    return None


def has_pymupdf():
    import importlib.util
    return bool(importlib.util.find_spec("pymupdf") or importlib.util.find_spec("fitz"))


def pdf_list(paths):
    """模考试卷文件夹里的 PDF，标出季数和是否已经拆过"""
    d, done = pdf_dir(paths), {n for n, sd in vault.seasons(paths) if any(sd.glob("[0-9][0-9]-*.md"))}
    out = []
    if d.is_dir():
        for f in sorted(d.glob("*.pdf"), key=lambda x: x.stat().st_mtime, reverse=True):
            m = SEASON_RE.search(f.stem)
            n = _cn2int(m.group(1)) if m else None
            out.append({"file": f.name, "season": n, "split": n in done})
    return out


def save_pdf(paths, body):
    """网页选的 PDF 存进 FB模考试卷复盘/模考试卷/；文件名里没有“第X季”时用填写的季数补上（拆分和导入都靠它认季）"""
    import base64
    name = Path(str(body.get("name") or "")).name
    if not name.lower().endswith(".pdf"):
        raise ImportError_("请选择 PDF 文件")
    if not SEASON_RE.search(name):
        n = int(body.get("season") or 0)
        if n <= 0:
            raise ImportError_("文件名里没有“第X季”，请填写这是第几季")
        name = "第%d季-%s" % (n, name)
    try:
        data = base64.b64decode(body.get("data") or "", validate=True)
    except Exception:
        raise ImportError_("文件读取失败，请重新选择")
    if not data.startswith(b"%PDF"):
        raise ImportError_("这不是 PDF 文件")
    d = pdf_dir(paths)
    d.mkdir(parents=True, exist_ok=True)
    with open(d / name, "wb") as fp:
        fp.write(data)
    return {"file": name}


def split_pdf(paths, body):
    """运行 split_mokao.py 拆分一份模考 PDF，然后把那一季导入试炼塔。已拆过的板块文件脚本会跳过，不覆盖复盘笔记"""
    import os
    import subprocess
    import sys
    name = Path(str(body.get("file") or "")).name
    f = pdf_dir(paths) / name
    if not name or not f.is_file():
        raise ImportError_("找不到这份 PDF")
    m = SEASON_RE.search(f.stem)
    if not m:
        raise ImportError_("文件名里没有“第X季”，改一下文件名再拆")
    script = split_script(paths)
    if not script:
        raise ImportError_("没找到 xingce-mokao-split（先运行 skill 安装脚本）")
    if not has_pymupdf():
        raise ImportError_("缺少 pymupdf：点下面的“安装拆分组件”，或在 PowerShell 运行 pip install pymupdf")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    from .paths import FROZEN
    # 打包成 exe 时 sys.executable 就是 exe 本身：让它带 --run-script 去跑拆分脚本（exe 里带着 pymupdf）
    cmd = [sys.executable, "--run-script", str(script), str(f)] if FROZEN else [sys.executable, str(script), str(f)]
    r = subprocess.run(cmd, capture_output=True, timeout=600, env=env,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    log = (r.stdout + r.stderr).decode("utf-8", errors="replace")
    if r.returncode != 0:
        raise ImportError_("拆分失败：\n" + log[-800:])
    season = _cn2int(m.group(1))
    if not any(d for n, d in vault.seasons(paths) if n == season):
        raise ImportError_("拆分完成但没找到第%d季的板块复盘：\n%s" % (season, log[-800:]))
    rep = commit(paths, {"kind": "season", "season": season})
    rep["season"] = season
    rep["split_log"] = "\n".join(ln for ln in log.splitlines() if re.search(r"共解析|题|⚠|跳过", ln))[-1200:]
    return rep


def install_pymupdf(paths, body):
    """用户在网页上点了“安装拆分组件”才运行：pip install pymupdf"""
    import subprocess
    import sys
    from .paths import FROZEN
    if FROZEN:      # exe 里已经带着 pymupdf
        return {"ok": has_pymupdf(), "log": "exe 版自带拆分组件，不用安装"}
    r = subprocess.run([sys.executable, "-m", "pip", "install", "pymupdf"], capture_output=True, timeout=600)
    log = (r.stdout + r.stderr).decode("utf-8", errors="replace")
    if r.returncode != 0:
        raise ImportError_("安装失败：\n" + log[-800:])
    import importlib
    importlib.invalidate_caches()
    return {"ok": has_pymupdf(), "log": log[-300:]}


# ---------------------------------------------------------------- 对外：状态 / 预览 / 导入
def status(paths):
    """导入页需要的信息：各季模考（题数、已导入数）、待修文件、待分类知识点数"""
    bank = paths.train / "题库"
    ids, _ = existing(bank) if bank.is_dir() else (set(), set())
    seasons = []
    for n, d in vault.seasons(paths):
        files = list(d.glob("[0-9][0-9]-*.md"))
        if not files:
            continue
        prefix = "粉笔%d季-" % n
        seasons.append({"season": n, "imported": sum(i.startswith(prefix) for i in ids)})
    fixes = []
    fd = bank / FIX_DIR
    if fd.is_dir():
        for f in sorted(fd.glob("*.md")):
            bs = parse_blocks(f.read_text(encoding="utf-8-sig", errors="ignore"))
            fixes.append({"file": f.name, "total": len(bs), "ready": sum(not b["fields"].get("检查", "").strip() for b in bs)})
    unsorted = sum(len(_unsorted_blocks(f)) for f in bank.glob("*真题.md")) if bank.is_dir() else 0
    return {"seasons": seasons[::-1], "fixes": fixes, "unsorted": unsorted, "ai": ai.available(), "boards": BOARDS,
            "pdfs": pdf_list(paths), "splitter": bool(split_script(paths)), "pymupdf": has_pymupdf(),
            "pdf_dir": "/".join(PDF_DIR) + "/"}


def _collect(paths, body):
    """按请求拆题，返回 (题目列表, 来源, 名称, 说明)"""
    kind = body.get("kind")
    note = ""
    if kind == "season":
        n = int(body.get("season") or 0)
        d = next((d for s, d in vault.seasons(paths) if s == n), None)
        if not d:
            raise ImportError_("找不到第 %s 季的板块复盘" % n)
        qs = parse_review(d)
        source, prefix, name = "粉笔第%d季模考" % n, "粉笔%d季" % n, "粉笔第%d季模考" % n
    elif kind in ("text", "pdf"):
        text = pdf_to_text(body.get("data") or "") if kind == "pdf" else body.get("text", "")
        lines = clean_lines(text)
        if not lines:
            raise ImportError_("文件是空的")
        source, prefix, season = detect_source(lines)
        if body.get("source") is not None and str(body.get("source")).strip() != "":
            source = str(body["source"]).strip()
            prefix = ""
        if body.get("no_source"):
            source = ""
        prefix = safe_name(body.get("prefix") or prefix or re.sub(r"[^\w一-鿿]", "", source)
                           or Path(body.get("name") or "导入").stem)
        name = source or prefix
        fenbi = sum("正确答案" in ln for ln in lines) >= 5
        review = next((d for s, d in vault.seasons(paths) if s == season), None) if season else None
        if fenbi and review and any(review.glob("[0-9][0-9]-*.md")):
            qs = parse_review(review)
            prefix = "粉笔%d季" % season
            note = "已有第%d季的板块复盘，直接用复盘文件（比 OCR 准，带截图）。" % season
        elif fenbi:
            qs = parse_fenbi(lines)
            note = "粉笔试卷的 OCR 文字顺序会乱，整份进待修。建议先用 xingce-mokao-split 拆这份 PDF，再在这里导入那一季。"
        else:
            qs = parse_book(lines, int(body.get("start_set") or 0))
        if not qs:
            raise ImportError_("一道题也没拆出来：确认是题目文字（OCR 结果），不是扫描图片")
        board = ALIAS.get(body.get("board") or "", body.get("board") or "")
        if board in BOARDS:
            for q in qs:
                q["board"] = board
        known = Counter(q["board"] for q in qs if q["board"])
        if not fenbi and known and (known["论证逻辑"] + known["形式逻辑"]) * 2 > sum(known.values()):
            for q in qs:   # 逻辑类练习册：问法认不出（或题干没 OCR 出问句）时按选项样子判断
                if not q["board"]:
                    q["board"] = board_by_options(q["options"])
        elif not fenbi and known and (known["逻辑填空"] + known["片段阅读"]) * 2 > sum(known.values()):
            for q in qs:   # 言语类练习册：同理，按选项样子判断逻辑填空 / 片段阅读
                if not q["board"]:
                    q["board"] = verbal_by_options(q["options"])
                # 言语书里被“支持 / 推出 / 结论”这类字带偏成逻辑的：没有明确逻辑问法就还是言语
                elif q["board"] in ("论证逻辑", "形式逻辑") and not LOGIC_STRONG.search(re.split(r"[。！？”]", q["stem"].rstrip())[-1]):
                    q["board"] = verbal_board(q["stem"], q["options"]) or "片段阅读"
    else:
        raise ImportError_("未知的导入方式")
    for q in qs:
        q["id"] = "%s-%03d" % (prefix, q["num"]) if not q.get("group") else "%s-%02d-%02d" % (prefix, q["group"], q["num"])
        q["source"] = source
        q["topic"] = guess_topic(q["board"], q["stem"])
        if not q["board"]:
            q["problems"].append("没认出板块")
        if len(q["stem"]) < 8 and q["board"] not in IMAGE_BOARDS | {"类比推理"}:
            q["problems"].append("题干太短，可能拆错了")
    return qs, source, name, note


def pdf_to_text(data_b64):
    """有文字层的 PDF（WPS / Word 导出、或 OCR 软件生成的“可搜索 PDF”）→ 一行一行的文字，交给 txt 同一套拆题流程。
    比先转 txt 多保住两样东西：
    - 填空的横线：PDF 里是画出来的细线，不是文字，转 txt 会丢；这里按坐标插回题干，写成 ____（横线下面本来有字的是“画线句”，不算空）；
    - 双空题选项之间的空隙：“遏止 恩威并施”，转 txt 会粘成“遏止恩威并施”。"""
    import base64
    try:
        import pymupdf as fitz
    except ImportError:
        try:
            import fitz
        except ImportError:
            raise ImportError_("读 PDF 需要 pymupdf 组件：在「① 模考」点“安装拆分组件”，或在 PowerShell 运行 pip install pymupdf")
    try:
        doc = fitz.open(stream=base64.b64decode(data_b64), filetype="pdf")
    except Exception:
        raise ImportError_("PDF 打不开，请确认文件没有损坏")
    out, chars_total = [], 0
    for page in doc:
        items = []   # (x0, y0, x1, y1, 文字)
        raw = page.get_text("rawdict")
        for b in raw.get("blocks", []):
            for ln in b.get("lines", []):
                cs = [c for s in ln.get("spans", []) for c in s.get("chars", [])]
                run, last = [], None
                for c in cs:
                    x0, y0, x1, y1 = c["bbox"]
                    w = max(1.0, x1 - x0)
                    if last is not None and (x0 - last[2] > w * 0.35 or c["c"].isspace()):
                        if run:
                            items.append(run)
                        run = []
                    if not c["c"].isspace():
                        run.append((x0, y0, x1, y1, c["c"]))
                    last = (x0, y0, x1, y1)
                if run:
                    items.append(run)
        words = [(r[0][0], min(c[1] for c in r), r[-1][2], max(c[3] for c in r), "".join(c[4] for c in r)) for r in items]
        chars_total += sum(len(w[4]) for w in words)
        # 填空横线：又细又不太长的水平线；横线正上方有字的是“画横线的句子”（下划线），不是空
        for dr in page.get_drawings():
            r = dr["rect"]
            if r.height > 1.5 or not 8 < r.width < 200:
                continue
            under = [w for w in words if abs(w[3] - r.y0) < 4 and min(w[2], r.x1) - max(w[0], r.x0) > r.width * 0.3]
            if not under:
                words.append((r.x0, r.y0 - 10, r.x1, r.y0, "____"))
        words.sort(key=lambda w: ((w[1] + w[3]) / 2, w[0]))
        rows = []
        for w in words:
            mid = (w[1] + w[3]) / 2
            for row in rows:
                if abs(row["mid"] - mid) < 6:
                    row["ws"].append(w)
                    break
            else:
                rows.append({"mid": mid, "ws": [w]})
        for row in sorted(rows, key=lambda r: r["mid"]):
            ws = sorted(row["ws"], key=lambda w: w[0])
            txt, prev = "", None
            for w in ws:
                if prev is not None and w[0] - prev[2] > 2 and "____" not in (w[4], prev[4]):
                    txt += " "
                txt += w[4]
                prev = w
            out.append(txt)
    if chars_total < 50:
        raise ImportError_("这份 PDF 没有文字层（是扫描图片）。先用 OCR 软件转成“可搜索 PDF”或 txt 再导入")
    return "\n".join(out)


def _route(paths, qs, dry):
    """分成 入库 / 待修 / 重复 三份；入库的题加来源、处理图片"""
    ids, stems = existing(paths.train / "题库")
    seen = set()
    ready, fix, dup = [], [], []
    clash = []
    for q in qs:
        stem = with_source(q["stem"], q["source"])
        key = norm_stem(stem, q["options"])
        if q["id"] in ids and not same_question(key, ids[q["id"]]):
            clash.append(q["id"])   # 编号一样但题目不同：前缀和另一本书撞了
            continue
        if q["board"] in BOARDS:
            stem, missing = place_images(paths, q["board"], q["id"], stem, dry)
            if missing:
                q["problems"].append("缺图：请把图存成 训练/题库/图片/%s/%s.png" % (q["board"], q["id"]))
        key = norm_stem(stem, q["options"])
        if q["id"] in ids or (len(key) >= 12 and key in stems):
            dup.append(q["id"])
            continue
        if q["id"] in seen:
            q["problems"].append("编号重复（拆题出错），请改成正确的编号")
        seen.add(q["id"])
        if q["problems"] or q["board"] not in BOARDS:
            fix.append(q)
            continue
        q["stem"] = stem
        ready.append(q)
        if len(key) >= 12:
            stems.add(key)
    if len(clash) >= 3 or (clash and len(clash) * 5 >= len(qs)):
        raise ImportError_("编号和已导入的另一批题撞了：%s 等 %d 道题编号相同但题目不同，什么都没有写入。\n"
                           "· 如果是另一本书：换一个前缀（比如在书名后加“言语”“逻辑”）；\n"
                           "· 如果是同一本书的下册、每套又从“练习题01”开始编：在“第一套是练习几”填下册第一套的号（如 16）。"
                           % ("、".join(clash[:3]), len(clash)))
    return ready, fix + [dict(q, problems=["编号和已有的另一道题相同，请改编号"]) for q in qs if q["id"] in clash], dup


def _summary(ready, fix, dup, note, name, source):
    if dup and not ready and not fix:
        note = (note + "\n" if note else "") + ("这一批 %d 道题全部已经在题库里。如果这其实是另一批题（比如下册），"
                                                "说明编号和已导入的题重复了：换个前缀，或填“第一套是练习几”。" % len(dup))
    return {"name": name, "source": source, "note": note, "ready": len(ready), "fix": len(fix), "dup": len(dup),
            "boards": Counter(q["board"] for q in ready).most_common(),
            "unsorted": sum(q["topic"] == UNSORTED for q in ready),
            "no_answer": sum(not q["answer"] for q in ready),
            "samples": [{"id": q["id"], "board": q["board"], "topic": q["topic"], "stem": q["stem"][:160],
                         "options": q["options"], "answer": q["answer"] or TODO} for q in ready[:3]],
            "problems": [{"id": q["id"], "problems": q["problems"]} for q in fix[:12]]}


def preview(paths, body):
    if body.get("kind") == "fix":
        return _fix_import(paths, body, dry=True)
    qs, source, name, note = _collect(paths, body)
    ready, fix, dup = _route(paths, qs, dry=True)
    return _summary(ready, fix, dup, note, name, source)


def commit(paths, body):
    if body.get("kind") == "fix":
        return _fix_import(paths, body, dry=False)
    qs, source, name, note = _collect(paths, body)
    if body.get("ai") and ai.available():
        _ai_label(paths, [q for q in qs if not q["board"] or q["topic"] == UNSORTED][:150])
    ready, fix, dup = _route(paths, qs, dry=False)
    _append(paths, ready)
    f = paths.train / "题库" / FIX_DIR / (safe_name(name) + ".md")
    if f.exists() and ready:  # 以前进了待修、这次能入库的题（比如修复后的图片选项题）：从待修文件里删掉
        _drop_ids(f, {q["id"] for q in ready})
    if f.exists():  # 同一份再导入一次：已经在待修文件里的题不重复追加
        there = {b["id"] for b in parse_blocks(f.read_text(encoding="utf-8-sig"))}
        fix = [q for q in fix if q["id"] not in there]
    if fix:
        old = f.read_text(encoding="utf-8") if f.exists() else (
            "# 待修：%s\n\n> 改好一道题（板块、题干、四个选项）就把它的“### 检查”下面清空，然后在网页「试炼塔 → 导入真题 → 待修」点重新导入。\n"
            "> 修不了的题直接删掉整块即可。答案不知道就留“（待补）”。\n\n" % name)
        _write(f, old.rstrip("\n") + "\n\n" + "".join(fix_block(q) for q in fix))
    r = _summary(ready, fix, dup, note, name, source)
    r["fix_file"] = "训练/题库/%s/%s.md" % (FIX_DIR, safe_name(name)) if f.exists() else ""
    return r


def _drop_ids(f, ids):
    text = f.read_text(encoding="utf-8-sig")
    blocks = parse_blocks(text)
    keep = [b for b in blocks if b["id"] not in ids]
    if len(keep) == len(blocks):
        return
    if not keep:
        f.unlink()
        return
    _write(f, text[:blocks[0]["start"]] + "".join(text[b["start"]:b["end"]] for b in keep))


def _append(paths, qs):
    by = {}
    for q in qs:
        by.setdefault(q["board"], []).append(bank_block(q))
    for board, items in by.items():
        f = paths.train / "题库" / (board + "真题.md")
        old = f.read_text(encoding="utf-8-sig") if f.exists() else "# %s真题\n" % board
        _write(f, old.rstrip("\n") + "\n\n" + "".join(items))


def _fix_import(paths, body, dry):
    """待修文件：“检查”已清空、板块和选项齐全的题入库，其余留在文件里"""
    name = Path(body.get("file") or "").name
    f = paths.train / "题库" / FIX_DIR / name
    if not name or not f.is_file():
        raise ImportError_("找不到待修文件")
    text = f.read_text(encoding="utf-8-sig")
    blocks = parse_blocks(text)
    qs, keep = [], []
    for b in blocks:
        fl = b["fields"]
        board = ALIAS.get(fl.get("板块", "").strip(), fl.get("板块", "").strip())
        opts = parse_opts(fl.get("选项"))
        ans = fl.get("答案", "").strip().upper()
        if fl.get("检查", "").strip() or board not in BOARDS or set(opts) != set("ABCD") or not all(opts.values()) \
                or not fl.get("题干", "").strip():
            keep.append(b)
            continue
        qs.append({"id": b["id"], "board": board, "topic": fl.get("知识点", "").strip() or UNSORTED,
                   "source": fl.get("来源", "").strip(), "stem": fl["题干"].strip(), "options": opts,
                   "answer": ans if re.fullmatch(r"[A-D]", ans) else "", "problems": [], "block": b})
    ready, fix, dup = _route(paths, qs, dry)
    keep += [q["block"] for q in fix]
    if not dry:
        _append(paths, ready)
        head = text[:blocks[0]["start"]] if blocks else text
        keep.sort(key=lambda b: b["start"])
        if keep:
            _write(f, head + "".join(text[b["start"]:b["end"]] for b in keep))
        else:
            f.unlink()
    r = _summary(ready, fix, dup, "", name, "")
    r["fix"] = len(keep)
    return r


# ---------------------------------------------------------------- 整理已有题库的格式
OPT_LINE = re.compile(r"^\s*([A-D])\s*[\.．、。:：)）]\s*(.*)$")


def normalize_bank(paths, body=None):
    """整理所有题库文件：选项统一写成“A. 内容”，并对题干、选项做 OCR 符号修复（①②③ / ⅠⅡⅢ）。
    只改 题干 / 选项 两节，编号、答案、解析、作答记录都不动。返回改了多少题、哪些题的序号仍需人工核对"""
    changed, flagged, files = 0, [], 0
    for f in sorted((paths.train / "题库").glob("*真题.md")):
        text = f.read_text(encoding="utf-8-sig")
        new_text, delta = text, 0
        for b in reversed(parse_blocks(text)):
            seg = text[b["start"]:b["end"]]
            fl = b["fields"]
            raw_opts = {}
            for ln in (fl.get("选项") or "").splitlines():
                m = OPT_LINE.match(ln)
                if m:
                    raw_opts[m.group(1)] = m.group(2).strip()
            if set(raw_opts) != set("ABCD"):
                continue
            stem0 = fl.get("题干", "")
            stem, opts, probs = fix_symbols(stem0, raw_opts)
            if probs:
                flagged.append(b["id"])
            opt_text = "\n".join("%s. %s" % (k, opts[k]) for k in "ABCD")
            new_seg = re.sub(r"(^###\s+选项\s*\n)(.*?)(?=^###|\Z)", lambda m: m.group(1) + opt_text + "\n",
                             seg, count=1, flags=re.M | re.S)
            if stem != stem0:
                new_seg = new_seg.replace(stem0, stem, 1)
            if new_seg != seg:
                new_text = new_text[:b["start"]] + new_seg + new_text[b["end"]:]
                delta += 1
        if delta:
            _write(f, new_text)
            files += 1
            changed += delta
    return {"changed": changed, "files": files, "flagged": flagged[:30], "flagged_total": len(flagged)}


# ---------------------------------------------------------------- 补答案
def parse_key(s):
    """“1-5 ABCDA”“1.A 2.B”或一串连续的 ABCD（从 1 开始） → {题号: 字母}"""
    key = {}
    for m in re.finditer(r"(\d+)\s*[-~—–至]\s*(\d+)\s*[:：.．]?\s*([A-Da-d\s]+)", s):
        a, b = int(m.group(1)), int(m.group(2))
        for i, x in enumerate(re.sub(r"\s", "", m.group(3)).upper()[:b - a + 1]):
            key[a + i] = x
    if key:
        return key
    for m in re.finditer(r"(\d+)\s*[\.．、:：]?\s*([A-Da-d])(?![A-Za-z])", s):
        key[int(m.group(1))] = m.group(2).upper()
    if key:
        return key
    return {i + 1: x for i, x in enumerate(re.sub(r"[^A-Da-d]", "", s).upper())}


def parse_table(s):
    """整本答案表：每行“练习01 ADDBA CDCAB DBBCC BBADD”（练习/第N套 + 一串字母） → {"01-01": "A", ...}"""
    key = {}
    for m in re.finditer(r"(?:练习题?|第)\s*0*(\d{1,3})\s*套?[^A-Da-d\n]*([A-Da-d][A-Da-d\s]*)", s):
        for i, x in enumerate(re.sub(r"\s", "", m.group(2)).upper()):
            key["%02d-%02d" % (int(m.group(1)), i + 1)] = x
    return key


def fill_answers(paths, body):
    """给编号 <前缀>-<题号> 的题补答案（只改“（待补）”的，已有答案的不动）。
    答案表里有“练习01 …”这样的行时，前缀填书的前缀（如 花生600题），一次补全本"""
    prefix = (body.get("prefix") or "").strip().rstrip("-")
    text = body.get("key") or ""
    table = parse_table(text)
    if table:
        key = {"%s-%s" % (prefix, k): v for k, v in table.items()}
    else:
        key = {"%s-%s" % (prefix, n): v for n, v in parse_key(text).items()}
    if not prefix or not key:
        raise ImportError_("请填编号前缀（如 四海逻辑600-03）和答案表（如 1-5 ABCDA，或整本：每行 练习01 ADDBA CDCAB …）")
    n = 0
    for f in sorted((paths.train / "题库").glob("*真题.md")):
        text = f.read_text(encoding="utf-8-sig")
        changed = False
        for b in reversed(parse_blocks(text)):
            m = re.match(r"^(.*-)0*(\d+)$", b["id"])
            k = b["id"] if b["id"] in key else (m and "%s%s" % (m.group(1), int(m.group(2))))
            if not k or k not in key:
                continue
            if re.fullmatch(r"[A-D]", b["fields"].get("答案", "").strip()):
                continue
            seg = text[b["start"]:b["end"]]
            new = re.sub(r"(^###\s+答案\s*\n)(.*?)(?=^###|\Z)", lambda mm: mm.group(1) + key[k] + "\n",
                         seg, count=1, flags=re.M | re.S)
            if new != seg:
                text = text[:b["start"]] + new + text[b["end"]:]
                n += 1
                changed = True
        if changed:
            _write(f, text)
    return {"filled": n, "key": len(key)}


def rename_prefix(paths, body, state):
    """改编号前缀：<旧>-xx → <新>-xx，只改勾选的板块（不勾就是全部）。题库文件、待修文件、存档里的作答记录一起改，
    做过的题历史不丢。新前缀已被别的题用过时拒绝"""
    old = (body.get("old") or "").strip().rstrip("-")
    new = (body.get("new") or "").strip().rstrip("-")
    boards = [b for b in (body.get("boards") or []) if b in BOARDS] or BOARDS
    if len(old) < 2 or len(new) < 2 or old == new or re.search(r"[\s/\\]", new):
        raise ImportError_("请填旧前缀和新前缀（不能相同、不能有空格）")
    bank = paths.train / "题库"
    ids, _ = existing(bank)
    if any(i.startswith(new + "-") for i in ids):
        raise ImportError_("新前缀“%s”已经有题在用了，换一个" % new)
    mapping, files = {}, 0
    for board in boards:
        f = bank / (board + "真题.md")
        if not f.is_file():
            continue
        text = f.read_text(encoding="utf-8-sig")
        n = re.sub(r"(?m)^(##\s+题目\s+)%s-" % re.escape(old), lambda m: m.group(1) + new + "-", text)
        if n != text:
            for b in parse_blocks(text):
                if b["id"].startswith(old + "-"):
                    mapping["%s::%s" % (board, b["id"])] = (board, new + b["id"][len(old):])
            n = n.replace("/%s-" % old, "/%s-" % new)       # 图片文件名跟着改（下面同步改文件）
            _write(f, n)
            files += 1
    img_root = bank / "图片"
    if img_root.is_dir():
        for p in sorted(img_root.rglob(old + "-*")):
            if p.parent.name in boards:
                p.rename(p.with_name(new + p.name[len(old):]))
    data = state.setdefault("bank", {"records": {}, "runs": {}, "groups": []})
    for k in list(data["records"]):   # 题库里已删、但做过的题：记录也一起改，保持一致
        board, _, qid = k.partition("::")
        if board in boards and qid.startswith(old + "-") and k not in mapping:
            mapping[k] = (board, new + qid[len(old):])
    moved = 0
    for k, (board, nid) in mapping.items():
        rec = data["records"].pop(k, None)
        if rec is not None:
            rec["question"] = dict(rec["question"], id=nid, key="%s::%s" % (board, nid))
            data["records"]["%s::%s" % (board, nid)] = rec
            moved += 1
    old_ids = {k.split("::", 1)[1]: v[1] for k, v in mapping.items()}
    for run in data.get("runs", {}).values():
        for q in run.get("questions", []):
            if q.get("board") in boards and q.get("id") in old_ids:
                q["key"] = "%s::%s" % (q["board"], old_ids[q["id"]])
                q["id"] = old_ids[q["id"]]
    for g in data.get("groups", []):
        if g.get("board") in boards:
            g["ids"] = [old_ids.get(i, i) for i in g.get("ids", [])]
    return {"renamed": len(mapping), "records": moved, "files": files}


# ---------------------------------------------------------------- 去重：同一道题（题干+选项一样）只留一份
def _dedupe_fp(stem, opts):
    s = re.sub(r"^（[^）]{2,60}）", "", stem.strip())                    # 题干前的来源括号不算
    imgs = re.findall(r"!\[\[[^\]]*?([^/\]]+)\]\]", s)
    s = re.sub(r"!\[\[[^\]]*\]\]", "", s)
    o = [re.sub(r"[\W_]+", "", opts.get(k, "")) for k in "ABCD"]
    s = re.sub(r"[\W_]+", "", s)
    if (len(s) < 12 and not imgs) or (all(len(x) <= 1 for x in o) and not imgs):
        return ""        # 太短、或图形题没有图：认不准，不去重
    return s + "|" + "|".join(imgs) + "|" + "|".join(o)


def _set_field(block, name, value):
    """改一道题里某个小节的内容；没有这个小节就插在“### 题干”前面"""
    m = re.search(r"^###\s+%s\s*\n(.*?)(?=^###\s|\Z)" % re.escape(name), block, re.M | re.S)
    if m:
        return block[:m.start(1)] + value + "\n" + block[m.end(1):]
    i = block.find("### 题干")
    return block[:i] + "### %s\n%s\n" % (name, value) + block[i:] if i >= 0 else block


def dedupe_bank(paths, body, state):
    """题库去重：题干和选项都一样的题只留一份。留哪份：做过的 > 有蒸馏解析的 > 有试卷出处的 > 解析长的。
    删掉的那份：试卷/题号并进留下的那份（按卷刷时这几张卷子都还能刷到），作答记录也挪过去，做过的不丢"""
    dry = bool(body.get("dry"))
    bank = paths.train / "题库"
    data = state.setdefault("bank", {"records": {}, "runs": {}, "groups": []})
    recs = data["records"]
    entries = []
    texts = {}
    for f in sorted(bank.glob("*真题*.md")):
        board = f.name.split("真题")[0]
        texts[f] = f.read_text(encoding="utf-8-sig")
        for b in parse_blocks(texts[f]):
            fl = b["fields"]
            fp = _dedupe_fp(fl.get("题干", ""), parse_opts(fl.get("选项", "")))
            if fp:
                entries.append((fp, f, board, b))
    groups = {}
    for e in entries:
        groups.setdefault(e[0], []).append(e)

    def score(e):
        _, f, board, b = e
        rec = recs.get("%s::%s" % (board, b["id"]))
        an = b["fields"].get("解析", "")
        return (bool(rec and rec.get("history")), "【推理链】" in an, bool(b["fields"].get("试卷")), len(an))
    ops = {}                 # 文件 → [(start, end, 新文本)]
    removed, moved, merged, examples = Counter(), 0, 0, []
    for g in groups.values():
        if len(g) < 2:
            continue
        g.sort(key=score, reverse=True)
        _, kf, kboard, kb = g[0]
        kkey = "%s::%s" % (kboard, kb["id"])
        papers = [x.strip() for x in kb["fields"].get("试卷", "").splitlines() if x.strip()]
        nums = kb["fields"].get("题号", "").split()
        nums += [""] * (len(papers) - len(nums))
        for _, f, board, b in g[1:]:
            for p, n in zip([x.strip() for x in b["fields"].get("试卷", "").splitlines() if x.strip()],
                            b["fields"].get("题号", "").split() + [""] * 99):
                if p not in papers:
                    papers.append(p)
                    nums.append(n)
            okey = "%s::%s" % (board, b["id"])
            rec = recs.get(okey)
            if rec and not dry:
                recs.pop(okey)
                if kkey in recs:     # 两份都做过：历史合在一起
                    k = recs[kkey]
                    k["history"] = sorted(k.get("history", []) + rec.get("history", []), key=lambda h: str(h.get("date", "")))
                    k["wrong"] = k.get("wrong") or rec.get("wrong")
                else:
                    recs[kkey] = dict(rec, question=dict(rec.get("question", {}), id=kb["id"], key=kkey, board=kboard))
                moved += 1
            ops.setdefault(f, []).append((b["start"], b["end"], ""))
            removed[board] += 1
        if len(examples) < 8:
            examples.append("%s ← %s" % (kb["id"], "、".join(x[3]["id"] for x in g[1:])))
        merged += 1
        if papers:
            block = texts[kf][kb["start"]:kb["end"]]
            nb = _set_field(block, "试卷", "\n".join(papers))
            if any(nums) and all(n.isdigit() for n in nums):
                nb = _set_field(nb, "题号", " ".join(nums))
            if nb != block:
                ops.setdefault(kf, []).append((kb["start"], kb["end"], nb))
    if not dry:
        for f, lst in ops.items():
            text = texts[f]
            for start, end, new in sorted(lst, reverse=True):
                text = text[:start] + new + text[end:]
            _write(f, text.rstrip("\n") + "\n")
    return {"groups": merged, "removed": sum(removed.values()), "boards": removed.most_common(), "records": moved,
            "files": len(ops), "examples": examples, "dry": dry}


def remove(paths, body, done_keys=()):
    """撤销一批导入：删除编号以 <前缀>- 开头、还没做过的题（题库和待修文件里都删）；做过的题保留（有作答记录）"""
    prefix = (body.get("prefix") or "").strip().rstrip("-")
    if len(prefix) < 2:
        raise ImportError_("请填要撤销的编号前缀（如 花生600题）")
    bank = paths.train / "题库"
    removed = kept = 0
    files = list(bank.glob("*真题.md")) + list((bank / FIX_DIR).glob("*.md"))
    for f in files:
        board = f.name[:-len("真题.md")] if f.name.endswith("真题.md") else ""
        text = f.read_text(encoding="utf-8-sig")
        blocks = parse_blocks(text)
        drop = []
        for b in blocks:
            if not b["id"].startswith(prefix + "-"):
                continue
            if board and "%s::%s" % (board, b["id"]) in done_keys:
                kept += 1
                continue
            drop.append(b)
        if not drop:
            continue
        for b in reversed(drop):
            text = text[:b["start"]] + text[b["end"]:]
        removed += len(drop)
        if f.parent.name == FIX_DIR and not parse_blocks(text):
            f.unlink()
        else:
            _write(f, text.rstrip("\n") + "\n")
    return {"removed": removed, "kept": kept}


# ---------------------------------------------------------------- AI 补分类（DeepSeek，只发题干开头）
def topic_options(paths, board):
    """有骨架就用骨架的大项名（试炼塔知识点和功法对上），没有就用默认分类"""
    sk = skeleton.load(paths, board) if paths.skeletons else None
    names = [it["name"] for it in sk["items"]] if sk and sk.get("items") else []
    return "、".join(names) if names else TOPICS.get(board, "")


def _ai_label(paths, qs):
    """给一批题定板块（没认出的）和知识点（待分类的）；每 25 题一次请求。失败的保持原样"""
    for i in range(0, len(qs), 25):
        batch = qs[i:i + 25]
        boards = sorted({q["board"] for q in batch if q["board"]})
        menu = "\n".join("- %s：%s" % (b, topic_options(paths, b)) for b in (boards or BOARDS))
        items = "\n".join("[%s] %s%s" % (q["id"], "" if q["board"] else "（板块未知）", re.sub(r"!\[\[[^\]]*\]\]|\s+", " ", q["stem"])[-220:])
                          for q in batch)
        msg = [{"role": "system", "content": "你是行测题目分类助手，只做分类，不解题。"},
               {"role": "user", "content": (
                   "给下面每道题标板块和知识点。板块只能是：%s。知识点从对应板块的候选里选最贴切的一个（候选没有合适的就写一个简短的通用名）。\n"
                   "候选：\n%s\n（板块未知的题也可以用其他板块的知识点。）\n\n题目（只给了题干结尾）：\n%s\n\n"
                   "只返回 JSON：{\"items\": [{\"id\": \"编号\", \"板块\": \"…\", \"知识点\": \"…\"}]}"
                   % ("、".join(BOARDS), menu if boards else "\n".join("- %s：%s" % (b, TOPICS[b]) for b in BOARDS), items))}]
        try:
            r = ai.chat_json(msg, temperature=0.1, max_tokens=2000, timeout=90)
        except ai.AIError:
            continue
        got = {str(x.get("id")): x for x in r.get("items", []) if isinstance(x, dict)}
        for q in batch:
            x = got.get(q["id"])
            if not x:
                continue
            b = ALIAS.get(str(x.get("板块", "")).strip(), str(x.get("板块", "")).strip())
            if not q["board"] and b in BOARDS:
                q["board"] = b
                q["problems"] = [p for p in q["problems"] if p != "没认出板块"]
            t = str(x.get("知识点", "")).strip()
            if q["topic"] == UNSORTED and t and len(t) <= 20 and "\n" not in t:
                q["topic"] = t


def _unsorted_blocks(f):
    return [b for b in parse_blocks(f.read_text(encoding="utf-8-sig", errors="ignore"))
            if b["fields"].get("知识点", "").strip() in ("", UNSORTED)]


def classify(paths, limit=100):
    """把题库里知识点是“待分类”的题交给 AI 补，每次最多 limit 题；只改知识点这一节"""
    if not ai.available():
        raise ImportError_("还没设置 AI（设置页填 DeepSeek 的 API key）")
    done = 0
    for f in sorted((paths.train / "题库").glob("*真题.md")):
        if done >= limit:
            break
        board = f.name[:-len("真题.md")]
        blocks = _unsorted_blocks(f)[:limit - done]
        if not blocks:
            continue
        qs = [{"id": b["id"], "board": board, "topic": UNSORTED, "stem": b["fields"].get("题干", ""), "problems": []}
              for b in blocks]
        _ai_label(paths, qs)
        topics = {q["id"]: q["topic"] for q in qs if q["topic"] != UNSORTED}
        text = f.read_text(encoding="utf-8-sig")
        for b in reversed(parse_blocks(text)):
            t = topics.get(b["id"])
            if not t or b["fields"].get("知识点", "").strip() not in ("", UNSORTED):
                continue
            seg = text[b["start"]:b["end"]]
            new = re.sub(r"(^###\s+知识点\s*\n)(.*?)(?=^###|\Z)", lambda m: m.group(1) + t + "\n",
                         seg, count=1, flags=re.M | re.S)
            text = text[:b["start"]] + new + text[b["end"]:]
        if topics:
            _write(f, text)
        done += len(blocks)
        if not topics:
            raise ImportError_("AI 没有返回可用的分类，稍后再试")
    left = sum(len(_unsorted_blocks(f)) for f in (paths.train / "题库").glob("*真题.md"))
    return {"done": done, "left": left}
