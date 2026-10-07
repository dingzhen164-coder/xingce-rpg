"""🧙 师傅制卡：把 PDF / Markdown / 粘贴的文字交给 AI，按“一张卡只考一个点”的规则出玉简草稿，学员审过再刻入。

流程（网页 web/cards.js 的“师傅制卡”）：
1. load：上传 PDF / .md / .txt（存到 ~/.xingce-rpg/制卡/），或选库里的一篇笔记、或粘贴文字 → 返回页数、目录（PDF 书签）、分段；
2. chunks：按选的章节 / 页码把正文切成每段约 3000 字的小块（PDF 一段 = 连续几页）；
3. gen：一块一块交给 AI 出卡（网页逐块调用，显示进度，可以中途停），返回 [{type, front, back, tags}]；
   扫描版 PDF 那页没有文字时：配了识图模型就把这页画成图片交给识图模型，没配就跳过并说明。
出卡规则参照 anki-expert（github.com/gong1414/anki-card-skill，MIT），加了行测的要求。
"""
import base64
import hashlib
import json
import re
import time
from pathlib import Path

from . import ai, notes, paths as paths_mod

CHUNK_CHARS = 3000
MAX_PAGES = 120          # 一次最多处理多少页（太多就分几次做）


class GenError(Exception):
    pass


def _dir():
    d = paths_mod.SETTINGS_DIR / "制卡"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _fitz():
    try:
        import pymupdf as fitz
    except ImportError:
        try:
            import fitz
        except ImportError:
            raise GenError("读 PDF 需要 pymupdf 组件（exe / App 里自带；用 Python 运行的请在 PowerShell 运行 pip install pymupdf）")
    return fitz


# ---------------------------------------------------------------- 读入
def _save(name, raw):
    sid = hashlib.sha1(raw).hexdigest()[:16]
    ext = Path(name).suffix.lower() or ".txt"
    f = _dir() / (sid + ext)
    if not f.exists():
        f.write_bytes(raw)
    (_dir() / (sid + ".name")).write_text(name, encoding="utf-8")
    for old in sorted(_dir().glob("*"), key=lambda p: p.stat().st_mtime)[:-40]:     # 只留最近 20 份左右
        old.unlink(missing_ok=True)
    return sid, f


def _src_file(sid):
    if not re.fullmatch(r"[0-9a-f]{16}", str(sid or "")):
        raise GenError("资料编号不对，请重新选择文件")
    hits = [f for f in _dir().glob(sid + ".*") if f.suffix != ".name"]
    if not hits:
        raise GenError("找不到刚才的资料（可能被清理了），请重新选择文件")
    name_f = _dir() / (sid + ".name")
    return hits[0], name_f.read_text(encoding="utf-8") if name_f.exists() else hits[0].name


def _md_sections(text):
    """Markdown / 纯文字按标题分段：[{title, level, start(段落序号)}]，没有标题就按字数切"""
    lines = text.splitlines()
    secs = []
    for i, ln in enumerate(lines):
        m = re.match(r"^(#{1,4})\s+(.+)$", ln)
        if m:
            secs.append({"title": m.group(2).strip(), "level": len(m.group(1)), "line": i})
    return secs


def load(paths, body):
    """返回 {src, name, kind: pdf|text, pages, toc:[{title, level, page}], chars}"""
    kind = body.get("kind")
    if kind == "vault":
        r = notes.read_md(paths, body.get("path"))
        raw = r["text"].encode("utf-8")
        sid, _ = _save(r["name"] + ".md", raw)
        return _describe(sid)
    if kind == "paste":
        text = str(body.get("text") or "").strip()
        if len(text) < 20:
            raise GenError("粘贴的文字太少了")
        sid, _ = _save((str(body.get("name") or "粘贴的文字").strip() or "粘贴的文字")[:40] + ".txt", text.encode("utf-8"))
        return _describe(sid)
    m = re.match(r"^data:[^;]*;base64,(.+)$", str(body.get("data") or ""), re.S)
    raw = base64.b64decode(m.group(1) if m else (body.get("data") or ""))
    if not raw:
        raise GenError("文件是空的")
    if len(raw) > 200 * 1024 * 1024:
        raise GenError("文件太大（超过 200MB）")
    name = str(body.get("name") or "资料")
    if raw[:4] == b"%PDF" and not name.lower().endswith(".pdf"):
        name += ".pdf"
    sid, _ = _save(name, raw)
    return _describe(sid)


def _describe(sid):
    f, name = _src_file(sid)
    if f.suffix == ".pdf":
        fitz = _fitz()
        try:
            doc = fitz.open(str(f))
        except Exception:
            raise GenError("PDF 打不开，请确认文件没有损坏")
        toc = [{"title": t, "level": lv, "page": p} for lv, t, p in doc.get_toc() if lv <= 3 and p >= 1]
        sample = "".join(doc[i].get_text("text") for i in range(min(doc.page_count, 5)))
        return {"src": sid, "name": name, "kind": "pdf", "pages": doc.page_count, "toc": toc,
                "scanned": len(sample.strip()) < 50 * min(doc.page_count, 5)}
    text = f.read_text(encoding="utf-8", errors="replace")
    secs = _md_sections(text)
    return {"src": sid, "name": name, "kind": "text", "pages": 0, "chars": len(text),
            "toc": [{"title": s["title"], "level": s["level"], "page": i + 1} for i, s in enumerate(secs)]}


def vault_files(paths):
    """能拿来制卡的库内笔记：各板块文件夹（同调阅）+ 灵台手札编纂出的 训练/手札/*.md"""
    files = notes.md_tree(paths)
    d = paths.train / "手札"
    if d.is_dir():
        for f in sorted(d.glob("*.md")):
            rel = f.relative_to(paths.vault).as_posix()
            files.append({"path": rel, "name": f.stem, "dir": "训练/手札", "top": "手札"})
    return {"files": files}


# ---------------------------------------------------------------- 切块
def _clean(t):
    t = re.sub(r"[ \t　]+", " ", t or "")
    t = re.sub(r"\n\s*\n+", "\n\n", t)
    return t.strip()


def chunks(paths, body):
    """按选的范围切块。PDF：pages=[起, 止]（从 1 数）或 sections=[目录序号…]；文字：sections=[标题序号…]，不选就整篇。
    返回 {chunks: [{label, pages:[…]} 或 {label, text}], skipped}"""
    sid = body.get("src")
    info = _describe(sid)
    f, name = _src_file(sid)
    out = []
    if info["kind"] == "pdf":
        doc = _fitz().open(str(f))
        pages = set()
        toc = info["toc"]
        for i in body.get("sections") or []:
            if 0 <= int(i) < len(toc):
                start = toc[int(i)]["page"]
                lv = toc[int(i)]["level"]
                nxt = next((t["page"] for t in toc[int(i) + 1:] if t["level"] <= lv), doc.page_count + 1)
                pages |= set(range(start, max(start + 1, nxt)))
        if body.get("pages"):
            a, b = [int(x) for x in body["pages"]][:2]
            a, b = max(1, min(a, b)), min(doc.page_count, max(a, b))
            pages |= set(range(a, b + 1))
        if not pages:
            raise GenError("先选章节，或者填页码范围")
        pages = sorted(pages)
        if len(pages) > MAX_PAGES:
            raise GenError("一次选了 %d 页，太多了：一次最多 %d 页，分几次做" % (len(pages), MAX_PAGES))
        cur, size = [], 0
        for p in pages:
            n = len(doc[p - 1].get_text("text").strip())
            if cur and (size + n > CHUNK_CHARS or p != cur[-1] + 1):
                out.append(cur)
                cur, size = [], 0
            cur.append(p)
            size += n
        if cur:
            out.append(cur)
        return {"name": name, "chunks": [{"label": "第 %d 页" % c[0] if len(c) == 1 else "第 %d–%d 页" % (c[0], c[-1]), "pages": c} for c in out]}
    text = f.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.S)          # frontmatter 不要
    lines = text.splitlines()
    secs = _md_sections(text)
    want = sorted({int(i) for i in body.get("sections") or [] if 0 <= int(i) < len(secs)})
    parts = []
    if want:
        for i in want:
            lv = secs[i]["level"]
            end = next((s["line"] for s in secs[i + 1:] if s["level"] <= lv), len(lines))
            parts.append((secs[i]["title"], "\n".join(lines[secs[i]["line"]:end])))
    else:
        parts.append((name, text))
    for title, body_text in parts:
        paras = re.split(r"\n\s*\n", body_text)
        buf, k = "", 0
        for para in paras:
            if buf and len(buf) + len(para) > CHUNK_CHARS:
                k += 1
                out.append({"label": "%s（%d）" % (title, k), "text": buf})
                buf = ""
            buf += para + "\n\n"
        if buf.strip():
            out.append({"label": title if not k else "%s（%d）" % (title, k + 1), "text": buf})
    return {"name": name, "chunks": out}


# ---------------------------------------------------------------- 出卡
RULES = """你是行测（公务员考试《行政职业能力测验》）备考的记忆卡片专家，把学员给的资料做成高质量的 Anki 式卡片（叫“玉简”）。
规则：
1. 最小信息原则：一张卡只考一个知识点，问题清楚具体，答案简洁；但不能漏掉关键信息。
2. 问题要能自然引出答案：问“用途 / 条件 / 区别 / 步骤 / 公式”，不要只问名字。答案有几条，就在问题末尾用括号写出条数，如“（3 条）”，答案用 Markdown 列表。
3. 找隐含知识点：资料里分散在几处的内容，补出“总结卡”“对比卡”（如两种方法的区别）。
4. 适合填空的（关键词、数字、公式里的一项、口诀）出填空卡：正面写完整句子，把要记的部分写成 {{c1::答案}}，同一句可以有 {{c2::…}}；填空卡的 back 可以留空或写一句补充。
5. 行测要求：
   - 公式 / 方法卡：正面写“什么情况下用 / 题目怎么问”，背面写公式或步骤 + 一个最简单的例子；
   - 实词、成语：正面给词或给一个语境，背面写意思、侧重点、搭配、易混词；
   - 常识、政治理论：正面问具体事实（时间、人物、内容、意义），不要出大而空的问题；
   - 例题、真题本身不要整题抄成卡，只提炼其中的方法、陷阱、结论。
6. 忠实于资料：只出资料里有的内容，资料说得不严谨的可以改严谨；不确定的宁可不出。
7. 格式：Markdown（**加粗** 关键词，列表，换行）；不要 HTML。每张卡给 1~3 个中文标签（知识点名，不要带 # 号）。
8. 页眉、页脚、广告、目录、版权页、练习题题号这类没有知识的内容跳过。
只输出 JSON：{"cards": [{"type": "问答" 或 "填空", "front": "…", "back": "…", "tags": ["…"]}]}"""

DENSITY = {"精简": "只出最核心的知识点，这一段大约 3~6 张。", "标准": "覆盖这一段的主要知识点，大约 6~12 张。",
           "详细": "尽量覆盖每个知识点（包括细节和隐含知识点），大约 10~20 张。"}


def _parse_cards(text):
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    m = re.search(r"\{.*\}", t, re.S)
    try:
        data = json.loads(m.group(0) if m else t)
    except ValueError:
        m = re.search(r"\[.*\]", t, re.S)
        if not m:
            raise GenError("AI 没按格式回复，换一段再试，或者换个模型")
        data = {"cards": json.loads(m.group(0))}
    out = []
    for c in data.get("cards") or []:
        front = str(c.get("front") or "").strip()
        back = str(c.get("back") or "").strip()
        typ = "填空" if re.search(r"\{\{c\d+::", front) else "问答"
        if not front or (typ == "问答" and not back):
            continue
        tags = c.get("tags") or []
        if isinstance(tags, str):
            tags = re.split(r"[\s,，、]+", tags)
        out.append({"type": typ, "front": front, "back": back,
                    "tags": [re.sub(r"[#\s]+", "", str(x))[:20] for x in tags if str(x).strip()][:4]})
    return out


def _chat(msgs, vision=False):
    try:
        return ai.chat(msgs, json_mode=True, temperature=0.3, max_tokens=4000, timeout=240, vision=vision)
    except ai.AIError as e:
        if "response_format" in str(e) or "json" in str(e).lower() and "400" in str(e):   # 有的接口不支持 JSON 模式
            return ai.chat(msgs, temperature=0.3, max_tokens=4000, timeout=240, vision=vision)
        raise


def gen(paths, body):
    """出一块的卡：{src, chunk: {pages | text, label}, density, types, note, deck} → {cards, skipped}"""
    if not ai.available():
        raise GenError("还没填 AI 的 API key：设置里填好才能请师傅制卡")
    f, name = _src_file(body.get("src"))
    ch = body.get("chunk") or {}
    density = DENSITY.get(body.get("density"), DENSITY["标准"])
    types = body.get("types") or "问答和填空都可以"
    if types == "问答":
        types = "只出问答卡，不要填空卡"
    elif types == "填空":
        types = "只出填空卡"
    want = ("\n\n学员对这批卡的要求：%s" % str(body["note"]).strip()) if str(body.get("note") or "").strip() else ""
    head = "资料：《%s》%s，放进简匣「%s」。\n%s\n卡片类型：%s。%s" % (re.sub(r"\.\w+$", "", name), ch.get("label", ""), body.get("deck") or "", density, types, want)
    skipped = []
    if ch.get("pages"):
        fitz = _fitz()
        doc = fitz.open(str(f))
        text, images = [], []
        for p in ch["pages"]:
            if not 1 <= int(p) <= doc.page_count:
                continue
            page = doc[int(p) - 1]
            t = page.get_text("text").strip()
            if len(t) >= 40:
                text.append("【第 %d 页】\n%s" % (p, _clean(t)))
            elif ai.vision_available():
                pix = page.get_pixmap(dpi=110)
                images.append((p, base64.b64encode(pix.tobytes("png")).decode("ascii")))
            else:
                skipped.append(p)
        cards = []
        if text:
            cards += _parse_cards(_chat([{"role": "system", "content": RULES},
                                         {"role": "user", "content": head + "\n\n" + "\n\n".join(text)}]))
        if images:
            content = [{"type": "text", "text": RULES + "\n\n" + head + "\n\n下面是这几页的图片（扫描页），先认出文字再出卡。"}]
            content += [{"type": "image_url", "image_url": {"url": "data:image/png;base64," + b}} for _, b in images[:6]]
            cards += _parse_cards(_chat([{"role": "user", "content": content}], vision=True))
        src_note = "出自《%s》%s" % (re.sub(r"\.\w+$", "", name), ch.get("label", ""))
    else:
        txt = _clean(re.sub(r"!\[\[[^\]]*\]\]|!\[[^\]]*\]\([^)]*\)", "", ch.get("text") or ""))
        if len(txt) < 20:
            return {"cards": [], "skipped": []}
        cards = _parse_cards(_chat([{"role": "system", "content": RULES}, {"role": "user", "content": head + "\n\n" + txt[:CHUNK_CHARS * 2]}]))
        src_note = "出自《%s》%s" % (re.sub(r"\.\w+$", "", name), "·" + ch["label"] if ch.get("label") and ch["label"] != name else "")
    for c in cards:
        c["extra"] = src_note
    return {"cards": cards, "skipped": skipped}
