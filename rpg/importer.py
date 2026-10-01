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


def norm_stem(s):
    """查重用：去掉来源括号、图片、空白和标点，取前 60 个字"""
    s = re.sub(r"^（[^）]{0,30}）", "", (s or "").strip())
    s = re.sub(r"!\[\[[^\]]*\]\]", "", s)
    s = re.sub(r"[\s\W_]+", "", s)
    return s[:60]


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
    return stem, opts, problems


def guess_board(section, stem, opts):
    s = stem
    if section in ("政治理论", "常识判断", "数量关系", "资料分析"):
        return section
    if section == "言语理解与表达":
        if "重新排列" in s or "语序正确" in s or "排序" in s:
            return "片段阅读"
        short = opts and all(len(v) <= 12 for v in opts.values())
        return "逻辑填空" if "依次填入" in s or ("横线" in s and short) else "片段阅读"
    if any(k in s for k in FIGURE_KW):
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


START_RE = re.compile(r"(?:(?<=[\s。？?！!”）)])|^)([1-9]\d{0,2})\s*[\.．。:：、，,]?\s*(?=[一-鿿“\"（(A-Z])")


# 练习册每套开头的标记行：“练习题03”“05 练习题”“页07 练习题”“o1 练习题”（OCR 常把序号挪到前面或丢掉）
SET_RE = re.compile(r"^[#＃\w页\s]{0,5}练习题?\s*\d{0,3}$")


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


def parse_book(lines):
    """练习册：有“练习题NN”标记就按标记分套（第几套 = 第几个有题的标记段，和答案表的“练习NN”对得上）；
    没有标记就按“题号回到 1”分套。每套里题号连续，选项按 A→B→C→D"""
    segs, cur = [], []
    for ln in lines:
        if SET_RE.match(ln) and len(ln) <= 12:
            segs.append(cur)
            cur = []
        else:
            cur.append(ln)
    segs.append(cur)
    texts = ["\n".join(x) for x in segs]
    by_marker = sum(bool(_starts(t)[0]) for t in texts) >= 2
    if not by_marker:
        texts = ["\n".join(lines)]
    out, group = [], 0
    for text in texts:
        starts, skipped = _starts(text)
        if not starts:
            continue  # 目录、封面
        if by_marker:
            group += 1
        first = len(out)
        for i, (s, e, n) in enumerate(starts):
            if not by_marker and n == 1:
                group += 1
            end = starts[i + 1][0] if i + 1 < len(starts) else len(text)
            stem, opts, problems = split_options(text[e:end], scrambled=False)
            stem = re.sub(r"\s*\n\s*", "", stem)
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
            lines = ([x for x in mats.get(q["material"], []) if x.strip()] + [""] if q["material"] else []) + q.pop("lines")
            q["stem"] = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
            if set(q["options"]) != set("ABCD") or not all(q["options"].values()):
                q["problems"].append("复盘文件里选项不全（可能是图片选项）")
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
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"^\s*([A-D])[\.．、)）]\s*(.*)$", s or "", re.M)}


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
    ids, stems = set(), set()
    for f in bank.glob("*真题.md"):
        for b in parse_blocks(f.read_text(encoding="utf-8-sig", errors="ignore")):
            ids.add(b["id"])
            k = norm_stem(b["fields"].get("题干", ""))
            if len(k) >= 12:
                stems.add(k)
    return ids, stems


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
    return {"seasons": seasons[::-1], "fixes": fixes, "unsorted": unsorted, "ai": ai.available(), "boards": BOARDS}


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
    elif kind == "text":
        lines = clean_lines(body.get("text", ""))
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
            qs = parse_book(lines)
        if not qs:
            raise ImportError_("一道题也没拆出来：确认是题目文字（OCR 结果），不是扫描图片")
        board = ALIAS.get(body.get("board") or "", body.get("board") or "")
        if board in BOARDS:
            for q in qs:
                q["board"] = board
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


def _route(paths, qs, dry):
    """分成 入库 / 待修 / 重复 三份；入库的题加来源、处理图片"""
    ids, stems = existing(paths.train / "题库")
    seen = set()
    ready, fix, dup = [], [], []
    for q in qs:
        stem = with_source(q["stem"], q["source"])
        if q["board"] in BOARDS:
            stem, missing = place_images(paths, q["board"], q["id"], stem, dry)
            if missing:
                q["problems"].append("缺图：请把图存成 训练/题库/图片/%s/%s.png" % (q["board"], q["id"]))
        key = norm_stem(stem)
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
    return ready, fix, dup


def _summary(ready, fix, dup, note, name, source):
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
