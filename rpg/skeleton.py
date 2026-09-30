"""
骨架文件：训练/骨架/<板块>.md —— 每个板块要能“一个不漏说出来”的知识清单，是默写和判分的唯一标准。

格式（AI 生成草稿，用户在 Obsidian 里审改，改完把“状态”改成“已定稿”或在网页上点“定稿”）：

    ---
    板块: 论证逻辑
    状态: 草稿                 ← 草稿 / 已定稿；只有已定稿的骨架才会进入训练
    来源skill: xue-rui-argument-logic
    ---
    # 论证逻辑 · 骨架

    ## 削弱题                  ← 一个 “## ” 标题 = 一个“大项”（训练和进度的最小单位）
    - 【术语】否定论点：……      ← 【术语】：完整名称清单，允许同义表述（AI 按含义判断）
    - 【术语】拆桥
    - 【思路】先找论点论据……    ← 【思路】或不带标记的条目：说出大意即可（AI 判断覆盖率）
    - 【口诀】先看对称一笔画     ← 【口诀】：整句一字不差（程序逐字比对，忽略标点；不走 AI 含义判断）；适合图推 24 诀这类口诀
    - 【特征】【翻译】……        ← 其他【xx】标记都按【思路】处理（说出大意即可）
    - ……⚠ 待核对：……          ← “⚠”之后是给用户看的提示，不参与判分

大项的 id 是 “板块::标题”（去掉开头的编号），改标题会被当成新大项，旧进度留在存档里不删。
"""
import re

TERM_TAG = "【术语】"
VERSE_TAG = "【口诀】"
THOUGHT_TAG = "【思路】"
NOTE_MARK = "⚠"
FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)
PUNCT_RE = re.compile(r"[\s　，,。.、；;：:！!？?“”\"'‘’（）()《》<>【】\[\]\-—_·/\\|]+")


def norm(s):
    """比对术语用：去掉空白和标点"""
    return PUNCT_RE.sub("", s or "")


def item_id(board, name):
    return f"{board}::{name}"


def path(paths, board):
    return paths.skeletons / f"{board}.md" if paths.skeletons else None


def _term_of(line):
    t = line.split(TERM_TAG, 1)[1]
    t = re.split(r"[：:（(，,；;—]", t, 1)[0]
    return t.strip().strip("*`").strip()


def parse(text, board):
    fm = FM_RE.match(text)
    meta = {}
    if fm:
        for ln in fm.group(1).splitlines():
            if ":" in ln or "：" in ln:
                k, v = re.split(r"[:：]", ln, 1)
                meta[k.strip()] = v.strip()
        text = text[fm.end():]
    items, cur = [], None
    for ln in text.splitlines():
        h = re.match(r"^##\s+(.+?)\s*$", ln)
        if h:
            name = re.sub(r"^(?:\d+[.、．)]|[一二三四五六七八九十]+[、.．])\s*", "", h.group(1)).strip()
            cur = {"name": name, "id": item_id(board, name), "terms": [], "verses": [], "thoughts": [],
                   "examples": [], "lines": []}
            items.append(cur)
            continue
        if cur is None or re.match(r"^#\s", ln):
            continue
        if ln.strip():
            cur["lines"].append(ln.rstrip())
        m = re.match(r"^\s*[-*]\s+(.+)$", ln)
        if not m:
            continue
        body = m.group(1)
        if "【举例】" in body:
            cur["examples"].append(body.replace("【举例】", "").strip())
        elif VERSE_TAG in body:
            # 【口诀】整句都要一字不差：单独存在 verses 里，由程序逐字比对（【术语】改为 AI 按含义判断，口诀不适用）
            v = body.split(VERSE_TAG, 1)[1].split(NOTE_MARK, 1)[0].strip().rstrip("。")
            if v:
                cur["verses"].append(v)
        elif TERM_TAG in body:
            t = _term_of(body)
            if t:
                cur["terms"].append(t)
            rest = body.split(TERM_TAG, 1)[1]
            # “【术语】拆桥：论据和论点说的不是一回事” 冒号后的解释也算一个思路要点
            if re.search(r"[：:]", rest):
                expl = re.split(r"[：:]", rest, 1)[1].strip()
                if expl:
                    cur["thoughts"].append(expl)
        else:
            # 【思路】【特征】【翻译】或不带标记的条目：说出大意即可；“⚠”后面是给用户的核对提示，不算要背的内容
            t = body.split(NOTE_MARK, 1)[0].replace(THOUGHT_TAG, "").strip()
            if t:
                cur["thoughts"].append(t)
    for it in items:
        it["text"] = "\n".join(it.pop("lines"))
    return {"board": board, "status": meta.get("状态", "草稿"), "skill": meta.get("来源skill", ""),
            "items": items}


def load(paths, board):
    """读骨架；文件不存在返回 None"""
    p = path(paths, board)
    if not p or not p.is_file():
        return None
    data = parse(p.read_text(encoding="utf-8", errors="ignore"), board)
    data["final"] = data["status"] == "已定稿"
    return data


def save_draft(paths, board, skill, body):
    """写入 AI 生成的草稿。已有“已定稿”的骨架不覆盖（返回 False）；已有草稿会先备份成 .bak.md"""
    p = path(paths, board)
    p.parent.mkdir(parents=True, exist_ok=True)
    old = load(paths, board)
    if old and old["final"]:
        return False
    if p.exists():
        p.with_name(f"{board}.bak.md").write_bytes(p.read_bytes())
    body = re.sub(r"^```(?:markdown|md)?\s*\n|\n```\s*$", "", body.strip())
    body = FM_RE.sub("", body, 1).strip()  # AI 若自己写了 frontmatter，去掉，用下面统一的
    text = (f"---\n板块: {board}\n状态: 草稿\n来源skill: {skill}\n---\n"
            f"# {board} · 骨架\n\n"
            f"> 审改说明：一个 `## 标题` = 一个大项；`【术语】` 是完整分类清单，允许同义表达；`【思路】` 用自己的话讲清；`【举例】` 自行编例子验证理解。\n"
            f"> 改完把上面的“状态: 草稿”改成“状态: 已定稿”（或在网页上点“定稿”），才会进入训练。\n\n"
            + re.sub(r"^#\s.*\n+", "", body) + "\n")
    with open(p, "w", encoding="utf-8", newline="\n") as fp:
        fp.write(text)
    return True


def set_final(paths, board, final=True):
    p = path(paths, board)
    if not p or not p.is_file():
        return False
    t = p.read_text(encoding="utf-8")
    new = "已定稿" if final else "草稿"
    if re.search(r"^状态[:：].*$", t, re.M):
        t = re.sub(r"^状态[:：].*$", f"状态: {new}", t, count=1, flags=re.M)
    else:
        t = f"---\n板块: {board}\n状态: {new}\n---\n" + t
    with open(p, "w", encoding="utf-8", newline="\n") as fp:
        fp.write(t)
    return True


def check_verses(item, answer):
    """逐字比对【口诀】：返回 (命中列表, 遗漏列表)。忽略空白和标点，其余必须一字不差"""
    a = norm(answer)
    hit = [v for v in item.get("verses", []) if norm(v) and norm(v) in a]
    miss = [v for v in item.get("verses", []) if v not in hit]
    return hit, miss


def check_terms(item, answer):
    """逐字比对术语：返回 (命中列表, 遗漏列表)"""
    a = norm(answer)
    hit = [t for t in item["terms"] if norm(t) and norm(t) in a]
    miss = [t for t in item["terms"] if t not in hit]
    return hit, miss

