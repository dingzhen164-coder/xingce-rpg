"""灵台手札：手写笔记本（像 Notability）+ 师傅编纂（手写 → Markdown）+ 调阅库里的 Markdown 笔记。

- 本子存在库里 训练/手札/手写/<id>.json（坚果云同步，平板上写的电脑上也有）：
  {"id", "title", "paper": "lines|grid|blank", "pages": [{"strokes": [{"t": "pen|hl|er", "c", "w", "p": [[x, y], …]}]}],
   "text": 打字补充, "compiled": 编纂出的 md（库内路径）, "updated"}
  坐标是“纸”上的逻辑坐标（一页宽 1000、高 1414，A4 比例），和屏幕大小无关。
- 师傅编纂：网页把每页画成白底 PNG 传上来 →
  配了识图模型（设置里的 vision_model）就直接让它认字 + 排版；没有就用系统自带 OCR（Windows / Mac）认字，再让 AI 排版。
  排好的 Markdown 存到 训练/手札/<标题>.md。
- 调阅：列出库里的 .md（不含 .obsidian、存档这类），读一篇时把 ![[图片]] 换成能在网页上显示的库内路径。
- 调阅 PDF：库里的 .pdf 也列出来。点开就是一本“PDF 批注本”（同样存在 训练/手札/手写/<id>.json，多了 "pdf": 库内路径、
  "paper": "pdf"，每页多一个 "h" = 这一页按宽 1000 算的高度）；每页的底图由 /notes-pdfpage?p=&n= 现渲染（pymupdf），
  上面照常用笔、荧光笔、橡皮勾画，自动保存。导出时把每页笔迹（透明 PNG）叠到原 PDF 上，原文字保持清晰。
"""
import base64
import datetime as dt
import json
import re
import time
from pathlib import Path

from . import ai, vault

PAGE_W, PAGE_H = 1000, 1414
PAPERS = ("lines", "grid", "blank")
PDF_MAX_PAGES = 600
SKIP_DIRS = {".obsidian", ".trash", ".git", "存档", "node_modules", ".stfolder"}


class NotesError(Exception):
    pass


def folder(paths):
    return paths.train / "手札"


def data_dir(paths):
    d = folder(paths) / "手写"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _file(paths, nid):
    if not re.fullmatch(r"[0-9a-z\-]{6,40}", str(nid or "")):
        raise NotesError("本子编号不对")
    return data_dir(paths) / ("%s.json" % nid)


def listing(paths):
    out = []
    for f in sorted(data_dir(paths).glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out.append({"id": d.get("id") or f.stem, "title": d.get("title") or f.stem, "updated": d.get("updated", ""),
                    "pages": len(d.get("pages") or []), "compiled": d.get("compiled", ""), "pdf": d.get("pdf", "")})
    return sorted(out, key=lambda x: x["updated"], reverse=True)


def get(paths, nid):
    f = _file(paths, nid)
    if not f.is_file():
        raise NotesError("这本手札不见了（可能在另一台电脑上删了）")
    d = json.loads(f.read_text(encoding="utf-8"))
    if d.get("pdf"):                       # 底图的版本号（PDF 换过就刷新缓存）
        p = pdf_file(paths, d["pdf"])
        d["pdf_v"] = int(p.stat().st_mtime) if p else 0
        d["pdf_missing"] = not p
    return d


def _clean_pages(pages):
    out = []
    for pg in (pages or [])[:200]:
        strokes = []
        for s in (pg or {}).get("strokes") or []:
            pts = [[round(float(x), 1), round(float(y), 1)] for x, y in (s.get("p") or [])[:4000]]
            if pts:
                strokes.append({"t": s.get("t") if s.get("t") in ("pen", "hl", "er") else "pen",
                                "c": str(s.get("c") or "#222222")[:9], "w": max(0.5, min(60.0, float(s.get("w") or 3))), "p": pts})
        out.append({"strokes": strokes})
    return out or [{"strokes": []}]


# 记笔记算复习时间：服务器记下每本手札最后一次真的写了东西（笔迹或打字有变化）的时刻，心跳只认最近写过的本子
WRITE_GRACE = 60          # 停笔超过 1 分钟就不再计时
LAST_WRITE = {}


def writing(nid, window=WRITE_GRACE + 35):
    """这本手札最近是否在写：最后一次有内容变化的保存在 window 秒内（网页每 30 秒上报一次，再加停笔的 1 分钟）"""
    return time.time() - LAST_WRITE.get(str(nid or ""), 0) <= window


def save(paths, body):
    nid = body.get("id") or (dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-%03d" % (int(time.time() * 1000) % 1000))
    f = _file(paths, nid)
    old = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}
    d = {"id": nid,
         "title": (str(body.get("title") or "").strip() or old.get("title") or dt.datetime.now().strftime("手札 %m-%d %H:%M"))[:60],
         "paper": body.get("paper") if body.get("paper") in PAPERS else old.get("paper", "lines"),
         "pages": _clean_pages(body["pages"]) if "pages" in body else old.get("pages") or [{"strokes": []}],
         "text": str(body["text"])[:20000] if "text" in body else old.get("text", ""),
         "compiled": old.get("compiled", ""),
         "updated": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    if old.get("pdf"):                     # PDF 批注本：页数、每页高度跟着 PDF 走，网页改不了
        d["pdf"], d["paper"] = old["pdf"], "pdf"
        olds = old.get("pages") or []
        pages = d["pages"][:len(olds)] + [{"strokes": []} for _ in range(len(olds) - len(d["pages"]))]
        for pg, o in zip(pages, olds):
            pg["h"] = o.get("h", PAGE_H)
        d["pages"] = pages
    if d["pages"] != old.get("pages") or d["text"] != old.get("text", ""):
        if old:                                   # 新建空本子不算写字
            LAST_WRITE[nid] = time.time()
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    tmp.replace(f)
    return {"id": nid, "title": d["title"], "updated": d["updated"]}


def delete(paths, nid):
    f = _file(paths, nid)
    if f.is_file():
        f.unlink()
    return {"ok": True}


# ---------------------------------------------------------------- 师傅编纂
def _png(data_url):
    m = re.match(r"^data:image/(png|jpeg|jpg);base64,(.+)$", str(data_url or ""), re.S)
    if not m:
        raise NotesError("页面图片格式不对")
    return base64.b64decode(m.group(2))


VISION_PROMPT = ("下面是学员手写的行测学习笔记（%d 页，按顺序）。请把手写内容认出来，整理成一份排版清楚的 Markdown 笔记：\n"
                 "1）忠实于原笔记的内容和结构，不要添加笔记里没有的知识；认不清的字用［?］标出；\n"
                 "2）用标题（## / ###）、列表、加粗、表格整理层次；画的框图、箭头关系用列表或表格表达；\n"
                 "3）开头一行 `# 标题`（按内容起一个简短的标题）；\n"
                 "4）只输出 Markdown 本身，不要解释。%s")


def _organize_prompt(title, ocr_pages, typed):
    pages = "\n\n".join("【第 %d 页 认出来的字】\n%s" % (i + 1, t.strip() or "（这页没认出字）") for i, t in enumerate(ocr_pages))
    return [{"role": "system", "content": "你是一位整理行测学习笔记的助手。只输出 Markdown，不要解释。"},
            {"role": "user", "content": (
                f"学员手写笔记「{title}」，先用 OCR 认了字（手写识别可能有错字、断行、顺序乱），另外还有学员打字补充的内容。\n"
                f"{pages}\n\n【打字补充】\n{typed.strip() or '（无）'}\n\n"
                "请整理成一份排版清楚的 Markdown 笔记：1）根据上下文和行测知识修正明显的 OCR 错字，拿不准的用［?］标出；"
                "2）忠实于笔记内容，不要添加笔记里没有的知识；3）用标题（## / ###）、列表、加粗、表格整理层次；"
                "4）开头一行 `# 标题`。只输出 Markdown 本身。")}]


def compile(paths, nid, images, typed=""):
    d = get(paths, nid)
    pngs = [_png(x) for x in (images or [])][:30]
    typed = str(typed if typed is not None else d.get("text", ""))
    if not pngs and not typed.strip():
        raise NotesError("这本手札还是空的：先写点什么再编纂")
    how = ""
    if pngs and ai.vision_available():
        content = [{"type": "text", "text": VISION_PROMPT % (len(pngs), ("\n学员另外打字补充：\n" + typed) if typed.strip() else "")}]
        content += [{"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(b).decode("ascii")}} for b in pngs]
        md = ai.chat([{"role": "user", "content": content}], vision=True, temperature=0.2, max_tokens=4000, timeout=240)
        how = "识图模型（%s）" % ai.settings()["vision_model"]
    else:
        texts = []
        if pngs:
            from . import report
            for b in pngs:
                try:
                    texts.append(report.ocr(b))
                except report.ReportError as e:
                    if not typed.strip():
                        raise NotesError("认不了手写：%s。可以在设置里填一个“识图模型”（能看图的 AI），"
                                         "认手写最准" % str(e).split("：")[0])
                    texts.append("")
        if ai.available():
            md = ai.chat(_organize_prompt(d["title"], texts, typed), temperature=0.2, max_tokens=4000, timeout=180)
            how = "系统 OCR 认字 + AI 排版" if pngs else "AI 排版（打字补充）"
        else:
            md = "# %s\n\n%s\n\n%s\n" % (d["title"], "\n\n".join(t.strip() for t in texts if t.strip()), typed.strip())
            how = "系统 OCR 认字（没有 AI，没排版）" if any(t.strip() for t in texts) else "打字补充（没有 AI，没排版）"
    md = re.sub(r"^```(?:markdown|md)?\s*\n(.*?)\n```\s*$", r"\1", md.strip(), flags=re.S).strip() + "\n"
    name = re.sub(r'[\\/:*?"<>|#^\[\]]+', " ", d["title"]).strip()[:50] or nid
    out = folder(paths) / (name + ".md")
    head = "> 灵台手札 · 师傅编纂（%s）· %s\n\n" % (how, dt.datetime.now().strftime("%Y-%m-%d %H:%M"))
    if md.startswith("# "):
        first, _, rest = md.partition("\n")
        text = first + "\n\n" + head + rest.lstrip("\n")
    else:
        text = "# %s\n\n%s%s" % (d["title"], head, md)
    out.write_text(text, encoding="utf-8", newline="\n")
    rel = out.relative_to(paths.vault).as_posix()
    d["compiled"] = rel
    f = _file(paths, nid)
    f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return {"path": rel, "markdown": text, "how": how}


# ---------------------------------------------------------------- 导出 PDF
EXPORT_DIR = ("手札", "导出")


def export_pdf(paths, nid, images):
    """网页把每页（纸 + 笔迹）画成图片传上来 → 拼成 A4 的 PDF，存到 训练/手札/导出/<标题>.pdf（同名覆盖）"""
    d = get(paths, nid)
    pics = [_png(x) for x in (images or [])][:200]
    if not pics:
        raise NotesError("这本手札还是空的，没有可以导出的页")
    try:
        import pymupdf as fitz
    except ImportError:
        try:
            import fitz
        except ImportError:
            raise NotesError("导出 PDF 需要 pymupdf 组件（exe / App 里自带；用 Python 运行的请在 PowerShell 运行 pip install pymupdf）")
    doc = fitz.open()
    w, h = fitz.paper_size("a4")
    for b in pics:
        page = doc.new_page(width=w, height=h)
        page.insert_image(page.rect, stream=b)
    doc.set_metadata({"title": d["title"], "creator": "行测修仙传 · 灵台手札"})
    out = paths.train.joinpath(*EXPORT_DIR)
    out.mkdir(parents=True, exist_ok=True)
    name = re.sub(r'[\\/:*?"<>|#^\[\]]+', " ", d["title"]).strip()[:50] or nid
    f = out / (name + ".pdf")
    tmp = f.with_suffix(".tmp")
    tmp.write_bytes(doc.tobytes(deflate=True, garbage=3))
    tmp.replace(f)
    return {"path": f.relative_to(paths.vault).as_posix(), "name": f.name, "pages": len(pics), "size": f.stat().st_size}


def export_file(paths, rel):
    """导出的文件的真实路径：只认 训练/手札/导出/ 里的 .pdf、训练/灵脉图/导出/ 里导出的思维导图、训练/战报/ 里的海报、训练/天机简报/原文/ 里的 PDF"""
    p = (paths.vault / str(rel or "")).resolve()
    if not p.is_file():
        return None
    if p.suffix.lower() == ".pdf" and paths.train.joinpath(*EXPORT_DIR).resolve() in p.parents:
        return p
    from . import mindmap
    if p.suffix.lower().lstrip(".") in mindmap.EXPORT_EXT and mindmap.export_dir(paths).resolve() in p.parents:
        return p
    from . import poster
    if p.suffix.lower() == ".png" and poster.export_dir(paths).resolve() in p.parents:
        return p
    from . import tianji
    if p.suffix.lower() == ".pdf" and (tianji.folder(paths) / "原文").resolve() in p.parents:
        return p
    return None


def open_local(p):
    """在电脑上用默认程序打开（只给本机用）"""
    import os
    import subprocess
    import sys
    if sys.platform.startswith("win"):
        os.startfile(str(p))  # noqa
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(p)])
    else:
        subprocess.Popen(["xdg-open", str(p)])


# ---------------------------------------------------------------- 调阅库里的 Markdown
# 调阅只看行测各板块的笔记：库根目录下名字带这些词的文件夹（不含 skill、copilot、训练、模考复盘这类）
BOARD_WORDS = ("常识", "政治", "言语", "逻辑填空", "中心理解", "片段阅读", "语句", "数量", "判断", "图形", "定义",
               "类比", "论证", "形式逻辑", "资料")
NOT_BOARD = ("skill", "copilot", "训练", "模考", "复盘", "book")


def is_board_dir(name):
    low = name.lower()
    return any(w in name for w in BOARD_WORDS) and not any(w in low for w in NOT_BOARD)


def md_tree(paths, limit=4000):
    """各板块文件夹里的 .md 和 .pdf：[{path, name, dir, top, kind: md|pdf}]（top = 板块文件夹），按文件夹、文件名排"""
    root = paths.vault
    out = []

    def walk(d, depth):
        if depth > 8 or len(out) >= limit:
            return
        try:
            items = sorted(d.iterdir(), key=lambda p: (p.is_file(), p.name))
        except OSError:
            return
        for p in items:
            if p.name.startswith(".") or p.name in SKIP_DIRS:
                continue
            if p.is_dir():
                if depth == 0 and not is_board_dir(p.name) or "skill" in p.name.lower():
                    continue
                walk(p, depth + 1)
            elif p.suffix.lower() in (".md", ".pdf") and depth > 0:
                rel = p.relative_to(root).as_posix()
                out.append({"path": rel, "name": p.stem, "dir": rel.rsplit("/", 1)[0], "top": rel.split("/", 1)[0],
                            "kind": p.suffix.lower()[1:]})
                if len(out) >= limit:
                    return
    walk(root, 0)
    return out


_IMG_INDEX = {"t": 0, "map": {}}


def _image_index(paths):
    if time.time() - _IMG_INDEX["t"] > 60:
        m = {}
        for p in paths.vault.rglob("*"):
            if p.suffix.lower() in vault.IMAGE_EXT and not any(part.startswith(".") for part in p.relative_to(paths.vault).parts):
                m.setdefault(p.name, p.relative_to(paths.vault).as_posix())
        _IMG_INDEX.update(t=time.time(), map=m)
    return _IMG_INDEX["map"]


def resolve_images(paths, text, base=None):
    """文字里的 ![[图]] / ![](图) → {写法: 库内路径}；先按相对 base 的路径找，再按文件名在全库找，找不到为空"""
    idx, images, root = _image_index(paths), {}, paths.vault.resolve()
    for m in re.finditer(r"!\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]|!\[[^\]]*\]\(([^)\s]+)\)", text or ""):
        name = (m.group(1) or m.group(2) or "").strip()
        if name in images:
            continue
        local = ""
        for cand in ([(base / name)] if base else []) + [paths.vault / name]:
            try:
                c = cand.resolve()
                if c.is_file():
                    local = c.relative_to(root).as_posix()
                    break
            except (ValueError, OSError):
                continue
        images[name] = local or idx.get(Path(name).name, "")
    return images


def read_md(paths, rel):
    p = (paths.vault / str(rel or "")).resolve()
    try:
        p.relative_to(paths.vault.resolve())
    except ValueError:
        raise NotesError("只能看库里的笔记")
    if p.suffix.lower() != ".md" or not p.is_file():
        raise NotesError("找不到这篇笔记")
    text = p.read_text(encoding="utf-8-sig", errors="replace")
    images = resolve_images(paths, text, p.parent)
    return {"path": Path(rel).as_posix(), "name": p.stem, "text": text, "images": images}


# ---------------------------------------------------------------- 调阅 PDF：批注本、每页底图、导出带批注的 PDF
def _fitz():
    try:
        import pymupdf as fitz
    except ImportError:
        try:
            import fitz
        except ImportError:
            raise NotesError("看 PDF 需要 pymupdf 组件（exe / App 里自带；用 Python 运行的请在 PowerShell 运行 pip install pymupdf）")
    return fitz


def pdf_file(paths, rel):
    """库里的一个 .pdf（不许跑出库、不进隐藏文件夹）"""
    try:
        p = (paths.vault / str(rel or "")).resolve()
        parts = p.relative_to(paths.vault.resolve()).parts
    except (ValueError, OSError):
        return None
    if p.suffix.lower() != ".pdf" or not p.is_file() or any(x.startswith(".") for x in parts):
        return None
    return p


def pdf_open(paths, rel, title=""):
    """打开库里的 PDF：已经有批注本就用它，没有就按 PDF 的页数、页面比例新建一本。返回 {id}"""
    p = pdf_file(paths, rel)
    if not p:
        raise NotesError("找不到这个 PDF")
    rel = p.relative_to(paths.vault.resolve()).as_posix()
    for b in listing(paths):
        if b.get("pdf") == rel:
            return {"id": b["id"]}
    fitz = _fitz()
    try:
        doc = fitz.open(str(p))
    except Exception as e:
        raise NotesError("打不开这个 PDF：%s" % e)
    if doc.page_count > PDF_MAX_PAGES:
        raise NotesError("这个 PDF 有 %d 页，太长了（最多 %d 页）" % (doc.page_count, PDF_MAX_PAGES))
    pages = []
    for pg in doc:
        r = pg.rect
        pages.append({"strokes": [], "h": round(PAGE_W * r.height / r.width, 1) if r.width else PAGE_H})
    nid = dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-%03d" % (int(time.time() * 1000) % 1000)
    d = {"id": nid, "title": (str(title or "").strip() or p.stem)[:60], "paper": "pdf", "pdf": rel, "pages": pages or [{"strokes": [], "h": PAGE_H}],
         "text": "", "compiled": "", "updated": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    f = _file(paths, nid)
    f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return {"id": nid}


_PAGE_CACHE = {}          # (路径, 修改时间, 页) → JPEG，留最近 60 页


def pdf_page(paths, rel, n, width=1400):
    """PDF 第 n 页（从 0 起）渲染成 JPEG（宽约 1400 像素）"""
    p = pdf_file(paths, rel)
    if not p:
        raise NotesError("找不到这个 PDF")
    key = (str(p), p.stat().st_mtime, int(n))
    if key in _PAGE_CACHE:
        return _PAGE_CACHE[key]
    fitz = _fitz()
    doc = fitz.open(str(p))
    if not 0 <= int(n) < doc.page_count:
        raise NotesError("没有这一页")
    page = doc[int(n)]
    zoom = width / page.rect.width if page.rect.width else 2
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    try:
        data = pix.tobytes("jpeg", jpg_quality=85)
    except TypeError:                      # 老版本 pymupdf 没有这个参数
        data = pix.tobytes("jpeg")
    if len(_PAGE_CACHE) >= 60:
        _PAGE_CACHE.pop(next(iter(_PAGE_CACHE)))
    _PAGE_CACHE[key] = data
    return data


def export_pdf_annot(paths, nid, overlays):
    """PDF 批注本导出：网页把每页的笔迹画成透明 PNG（没写的页传 null）→ 叠到原 PDF 对应页上，
    存到 训练/手札/导出/<标题>（批注）.pdf（同名覆盖）"""
    d = get(paths, nid)
    p = pdf_file(paths, d.get("pdf"))
    if not p:
        raise NotesError("原来的 PDF 不见了（可能挪走或改名了）")
    fitz = _fitz()
    doc = fitz.open(str(p))
    n = 0
    for i, ov in enumerate((overlays or [])[:doc.page_count]):
        if not ov:
            continue
        doc[i].insert_image(doc[i].rect, stream=_png(ov), overlay=True)
        n += 1
    if not n:
        raise NotesError("还没在这个 PDF 上写画，没有可以导出的批注")
    out = paths.train.joinpath(*EXPORT_DIR)
    out.mkdir(parents=True, exist_ok=True)
    name = re.sub(r'[\\/:*?"<>|#^\[\]]+', " ", d["title"]).strip()[:50] or nid
    f = out / (name + "（批注）.pdf")
    tmp = f.with_suffix(".tmp")
    tmp.write_bytes(doc.tobytes(deflate=True, garbage=3))
    tmp.replace(f)
    return {"path": f.relative_to(paths.vault).as_posix(), "name": f.name, "pages": doc.page_count, "marked": n, "size": f.stat().st_size}


def pdf_list(paths, limit=3000):
    """库里所有的 PDF（藏经阁「功法 · 教材」）：[{path, name, dir, top}]。
    不含隐藏文件夹、训练/ 里程序自己生成的（手札导出、战报、程序文件夹），训练/天机简报/原文/ 保留"""
    root = paths.vault
    out = []
    keep = ("训练", "天机简报", "原文")

    def blocked(parts):       # 训练/ 下只进 训练/天机简报/原文/
        return parts[0] == "训练" and tuple(parts[:3]) != keep[:min(3, len(parts))]

    def walk(d, depth):
        if depth > 10 or len(out) >= limit:
            return
        try:
            items = sorted(d.iterdir(), key=lambda p: (p.is_file(), p.name))
        except OSError:
            return
        for p in items:
            if p.name.startswith(".") or p.name in SKIP_DIRS:
                continue
            parts = p.relative_to(root).parts
            if p.is_dir():
                if not blocked(parts):
                    walk(p, depth + 1)
            elif p.suffix.lower() == ".pdf" and not (parts[0] == "训练" and tuple(parts[:3]) != keep):
                r = "/".join(parts)
                out.append({"path": r, "name": p.stem, "dir": "/".join(parts[:-1]), "top": parts[0] if len(parts) > 1 else ""})
                if len(out) >= limit:
                    return
    walk(root, 0)
    return out
