"""
只读访问 Obsidian 行测库：模考板块复盘、解题 skill、截图。本模块从不写库里的任何文件。

板块复盘文件由 xingce-mokao-split 生成，格式（节选）：

    ### 102. ❌                         ← 题号 + 结果图标（✅ 对 / ❌ 错 / ⚪ 未作答）
    ![[S36-Q102.png]]                   ← 可能有截图
    题干……
    - **A.** 选项
    > [!check]- 答案
    > 正确答案：**B**　我的答案：**A**　错误
    > [!note] 复盘
    > 【答案】B ……                       ← 解析（xingce-jiexi-all 写入）或自己的笔记
    ---

资料分析 / 一拖五 这类有“## 材料（第a-b题）”的，材料正文挂在对应题目上。
解析规则和 obsidian-to-xingce 仓库里的 jiexi.py 保持一致。
"""
import re
from pathlib import Path

HEAD_RE = re.compile(r"^### (\d+)\. (\S+)")
ANS_RE = re.compile(r"正确答案：\*\*([^*]*)\*\*\s*我的答案：\*\*([^*]*)\*\*")
MAT_RE = re.compile(r"^## 材料（第(\d+)-(\d+)题）")
IMG_RE = re.compile(r"!\[\[([^\]|]+)(?:\|[^\]]*)?\]\]|!\[[^\]]*\]\(([^)]+)\)")
NOTE = "> [!note] 复盘"
CHECK = "> [!check]"
# 复盘栏里的空模板行（“- 错因：”这类），不算解析内容
PLACEHOLDER_RE = re.compile(r"^(?:[-*]\s*)?(?:\*\*)?[^：:>*]{1,12}[：:](?:\*\*)?\s*$")
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}

_cache = {}  # 路径 → (mtime, 解析结果)


# ---------------------------------------------------------------- skill
def skill_dir(paths, name):
    """skill 文件夹（按文件夹名找）；不存在返回 None"""
    if not paths.skills or not name:
        return None
    d = paths.skills / name
    return d if (d / "SKILL.md").is_file() else None


def skill_digest(paths, name, limit=None):
    """读取全篇学习资料；可选上限超出时拒绝，不悄悄截断分类或章节。"""
    d = skill_dir(paths, name)
    if not d:
        return ""
    files = [d / fn for fn in ("SKILL.md", "cheatsheet.md", "patterns.md", "glossary.md")]
    files += sorted((d / "chapters").glob("*.md"))
    parts = ["=== %s ===\n%s" % (f.relative_to(d), f.read_text(encoding="utf-8", errors="ignore"))
             for f in files if f.is_file()]
    if not any(f.is_file() for f in files[4:]):
        parts.append("资料提示：没有章节正文。只可依据现有内容，方法细节缺失时应标注待核对。")
    text = "\n\n".join(parts)
    if limit is not None and len(text) > limit:
        raise ValueError("skill 正文超过读取上限，请分板块整理资料；未生成残缺草稿")
    return text


# ---------------------------------------------------------------- 模考复盘
def seasons(paths):
    """[(季数, 目录)]，按季数从小到大"""
    if not paths.seasons or not paths.seasons.is_dir():
        return []
    out = []
    for d in paths.seasons.iterdir():
        m = re.fullmatch(r"第(\d+)季", d.name)
        if m and d.is_dir():
            out.append((int(m.group(1)), d))
    return sorted(out)


def board_file(season_dir, source):
    fs = sorted(season_dir.glob(f"[0-9][0-9]-{source}.md"))
    return fs[0] if fs else None


def _clean_analysis(lines):
    out = []
    for ln in lines:
        s = ln.strip()
        s = s[1:].strip() if s.startswith(">") else s
        if not s or PLACEHOLDER_RE.match(s):
            continue
        out.append(s)
    return "\n".join(out)


def parse_board_file(path):
    """返回题目列表（dict），带 mtime 缓存"""
    try:
        mt = path.stat().st_mtime
    except OSError:
        return []
    hit = _cache.get(path)
    if hit and hit[0] == mt:
        return hit[1]
    lines = path.read_text(encoding="utf-8", errors="ignore").split("\n")
    qs, mats, cur, mat, in_note = [], {}, None, None, False
    for ln in lines:
        h = HEAD_RE.match(ln)
        if h:
            cur = {"num": int(h.group(1)), "icon": h.group(2), "correct": "", "mine": "",
                   "body": [], "note": [], "material": None}
            if mat and mat[0] <= cur["num"] <= mat[1]:
                cur["material"] = mat
            qs.append(cur)
            in_note = False
            continue
        mm = MAT_RE.match(ln)
        if mm:
            mat = (int(mm.group(1)), int(mm.group(2)))
            mats[mat] = []
            cur = None
            continue
        if cur is None:
            if mat in mats and not ln.startswith("---"):
                mats[mat].append(ln)
            continue
        if ln.strip() == "---":
            cur = None
            continue
        if ln.startswith(NOTE):
            in_note = True
            continue
        if in_note:
            cur["note"].append(ln)
            continue
        a = ANS_RE.search(ln)
        if a:
            cur["correct"], cur["mine"] = a.group(1).strip("?"), a.group(2).strip("—")
        elif not ln.startswith(CHECK):
            cur["body"].append(ln)
    for q in qs:
        q["analysis"] = _clean_analysis(q.pop("note"))
        q["material_lines"] = mats.get(q["material"], []) if q["material"] else []
        q["body"] = "\n".join(q["body"]).strip()
    _cache[path] = (mt, qs)
    return qs


def questions(paths, source, last_n=0):
    """某个复盘板块在所有季里的题目，附上 season / source / key / dir"""
    ss = seasons(paths)
    if last_n:
        ss = ss[-last_n:]
    out = []
    for n, d in ss:
        f = board_file(d, source)
        if not f:
            continue
        for q in parse_board_file(f):
            q = dict(q, season=n, source=source, dir=str(d), key=f"{n}|{source}|{q['num']}")
            out.append(q)
    return out


def wrong_questions(paths, sources, last_n=0):
    """❌ / ⚪ 的题（错题池），新的季排在前面"""
    out = []
    for s in sources:
        out += [q for q in questions(paths, s, last_n) if q["icon"] in ("❌", "⚪")]
    return sorted(out, key=lambda q: (-q["season"], q["num"]))


def find_question(paths, key):
    n, source, num = key.split("|")
    for q in questions(paths, source):
        if q["season"] == int(n) and q["num"] == int(num):
            return q
    return None


def accuracy(paths, sources, last=3):
    """最近 last 季的实战正确率：{"rate", "trend": "↑/→/↓", "per": [(季, 对, 总)], "count"}"""
    per = []
    for n, d in seasons(paths):
        ok = tot = 0
        for s in sources:
            f = board_file(d, s)
            if not f:
                continue
            qs = parse_board_file(f)
            tot += len(qs)
            ok += sum(1 for q in qs if q["icon"] == "✅")
        if tot:
            per.append((n, ok, tot))
    if not per:
        return None
    recent = per[-last:]
    rate = sum(o for _, o, _ in recent) / sum(t for _, _, t in recent)
    trend = "→"
    if len(per) >= 2:
        last_r = per[-1][1] / per[-1][2]
        prev = per[-3:-1] if len(per) >= 3 else per[-2:-1]
        prev_r = sum(o for _, o, _ in prev) / sum(t for _, _, t in prev)
        trend = "↑" if last_r - prev_r > 0.05 else ("↓" if prev_r - last_r > 0.05 else "→")
    return {"rate": rate, "trend": trend, "per": per[-last:], "count": len(per)}


# ---------------------------------------------------------------- 截图
_img_index = {}


def find_image(paths, season_dir, name):
    """Obsidian 式查找：先找本季目录（含 attachments），再在整个模考复盘目录里按文件名找"""
    name = name.strip()
    sd = Path(season_dir)
    for c in (sd / name, sd / "attachments" / name):
        if c.is_file():
            return c
    root = paths.vault / "FB模考试卷复盘" if paths.vault else None
    if root and root.is_dir():
        if name not in _img_index:
            hits = [p for p in root.rglob(Path(name).name) if p.is_file()]
            _img_index[name] = hits[0] if hits else None
        return _img_index[name]
    return None


def render_blocks(paths, q):
    """把题目（材料 + 题干 + 选项）转成网页用的块列表：[{"t":"text","v":…} | {"t":"img","v":库内相对路径}]"""
    blocks = []
    text = "\n".join(q.get("material_lines") or [])
    if text.strip():
        text += "\n\n"
    text += q["body"]
    pos = 0
    for m in IMG_RE.finditer(text):
        if text[pos:m.start()].strip():
            blocks.append({"t": "text", "v": text[pos:m.start()].strip()})
        name = m.group(1) or m.group(2)
        p = find_image(paths, q["dir"], name)
        if p and paths.vault:
            try:
                blocks.append({"t": "img", "v": p.resolve().relative_to(paths.vault.resolve()).as_posix()})
            except ValueError:
                pass
        pos = m.end()
    if text[pos:].strip():
        blocks.append({"t": "text", "v": text[pos:].strip()})
    return blocks


def safe_vault_file(paths, rel):
    """网页请求库里的图片时用：只允许库内、图片后缀的文件，防止读到别的文件"""
    if not paths.vault or not rel:
        return None
    p = (paths.vault / rel).resolve()
    try:
        p.relative_to(paths.vault.resolve())
    except ValueError:
        return None
    return p if p.is_file() and p.suffix.lower() in IMAGE_EXT else None

