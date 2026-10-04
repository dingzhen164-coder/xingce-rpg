"""宗门大比·导入对错截图：粉笔模考报告里那张“答题卡”（绿圈 = 对，红圈 = 错，圈里是题号）。

粉笔模考下载的带答案试卷里“你的答案”是空的，拆出来全是 ⚪。这里读答题卡截图（可以好几张，滚动截的有重叠也行）：
1. 用 pymupdf 解图（拆试卷本来就要它，不另装东西），按颜色找出绿圈、红圈，聚成一行一行；
2. 不认数字：按这一季拆出来的题号排出“应有的答题卡”——每个模块另起一行、一行 11 个（行宽按截图里最长的一行），
   模块标题让上下两行隔得更开；拿截图里完整的那几行（贴着上下边被裁掉的行不要）去对：行里圈数一致、
   该有标题的地方间隔大，就对上了；
3. 几张图对上的位置合起来，得到每道题对 / 错。最后写回 板块复盘/第N季 的复盘文件（### 题号 的 ⚪ 换成 ✅ / ❌，
   答案栏、表格、frontmatter、总览一起改）。错题具体选了哪个不知道，我的答案写“？”。
"""
import base64
import re
from pathlib import Path

from . import vault

MODULE_ORDER = ("政治理论", "常识判断", "言语理解", "数量关系", "判断推理", "资料分析")


class MarksError(Exception):
    pass


def _color(r, g, b):
    """绿（对）/ 红（错）/ 其他。粉笔答题卡：绿 ≈ (40,190,150)，红 ≈ (240,85,80)"""
    if g > 140 and r < 130 and g - r > 50 and b > 90:
        return 1
    if r > 200 and g < 140 and b < 140 and r - g > 80:
        return 2
    return 0


def circles(data):
    """一张截图 → [(中心x, 中心y, 直径, 'ok'/'bad', 是否被上下边裁到)]"""
    try:
        import pymupdf
    except ImportError:
        try:
            import fitz as pymupdf
        except ImportError:
            raise MarksError("读截图要用 pymupdf 组件：在藏经阁「导入真题 → ① 模考」点“安装拆分组件”")
    try:
        pix = pymupdf.Pixmap(data)
    except Exception:
        raise MarksError("这张图打不开（只支持 png / jpg）")
    if pix.alpha or pix.n != 3:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    W, H, s = pix.width, pix.height, pix.samples
    step = 2 if max(W, H) > 1000 else 1
    w, h = (W + step - 1) // step, (H + step - 1) // step
    grid = bytearray(w * h)
    for yy in range(h):
        row = yy * step * W
        for xx in range(w):
            i = (row + xx * step) * 3
            grid[yy * w + xx] = _color(s[i], s[i + 1], s[i + 2])
    seen = bytearray(w * h)
    blobs = []
    for start in range(w * h):
        c = grid[start]
        if not c or seen[start]:
            continue
        stack, seen[start] = [start], 1
        n, x0, y0, x1, y1 = 0, w, h, 0, 0
        while stack:
            k = stack.pop()
            n += 1
            x, y = k % w, k // w
            x0, x1, y0, y1 = min(x0, x), max(x1, x), min(y0, y), max(y1, y)
            for nk in (k - 1, k + 1, k - w, k + w):
                if 0 <= nk < w * h and not seen[nk] and grid[nk] == c and abs(nk % w - x) <= 1:
                    seen[nk] = 1
                    stack.append(nk)
        bw, bh = x1 - x0 + 1, y1 - y0 + 1
        if n >= 30 and bw >= 8 and bh >= 4:
            blobs.append((x0, y0, bw, bh, n, c))
    if not blobs:
        return [], W, H
    # 圈的直径：取宽度的中位数；同色、宽度接近、填充率像圆圈（中间有白字）的才算
    ws = sorted(b[2] for b in blobs if b[2] >= 12)
    if not ws:
        return [], W, H
    d = ws[len(ws) // 2]
    out = []
    for x0, y0, bw, bh, n, c in blobs:
        if not (0.75 * d <= bw <= 1.3 * d):
            continue
        cut = y0 <= 1 or y0 + bh >= h - 1 or bh < 0.8 * d     # 被截图上下边裁掉一截
        if not cut and not (0.75 * d <= bh <= 1.3 * d):
            continue
        if n < 0.35 * bw * bh:
            continue
        out.append(((x0 + bw / 2) * step, (y0 + bh / 2) * step, d * step, 'ok' if c == 1 else 'bad', cut))
    return out, W, H


def rows_of(cs):
    """圈 → 行：[(行中心y, [按 x 排好的结果], 是否有被裁的)]"""
    if not cs:
        return []
    d = sorted(c[2] for c in cs)[len(cs) // 2]
    out = []
    for c in sorted(cs, key=lambda c: c[1]):
        if out and abs(c[1] - out[-1][0]) < 0.5 * d:
            out[-1][1].append(c)
        else:
            out.append([c[1], [c]])
    return [(y, [c[3] for c in sorted(r, key=lambda c: c[0])], any(c[4] for c in r), d) for y, r in out]


def layout(paths, season):
    """这一季应有的答题卡：[(模块, 第一题题号, 这一行几题, 是不是模块第一行)]，行宽按 per_row"""
    from . import mock
    d = next((d for n, d in vault.seasons(paths) if n == season), None)
    if not d:
        raise MarksError("还没有第%d季的板块复盘：先在藏经阁导入这一季的模考试卷" % season)
    nums = {}
    for f in d.glob("[0-9][0-9]-*.md"):
        m = mock.MODULE_OF.get(f.stem[3:])
        if m:
            for q in vault.parse_board_file(f):
                nums[q["num"]] = m
    if not nums:
        raise MarksError("第%d季的复盘里没有题目" % season)
    sections = []
    for n in sorted(nums):
        if sections and sections[-1][0] == nums[n] and sections[-1][2] == n - 1:
            sections[-1][2] = n
        else:
            sections.append([nums[n], n, n])
    return sections, sorted(nums)


def expected_rows(sections, per_row):
    rows = []
    for mod, a, b in sections:
        for k, start in enumerate(range(a, b + 1, per_row)):
            rows.append((mod, start, min(per_row, b - start + 1), k == 0))
    return rows


def scan(paths, season, images):
    """几张答题卡截图 → {题号: 'ok'/'bad'}，以及对上的情况"""
    if not images:
        raise MarksError("先选答题卡截图")
    sections, nums = layout(paths, season)
    per_image = []
    for k, data in enumerate(images):
        cs, W, H = circles(data)
        rows = rows_of(cs)
        per_image.append(rows)
    per_row = max((len(r[1]) for rows in per_image for r in rows), default=0)
    if not per_row:
        raise MarksError("截图里没找到绿 / 红圆圈：要截粉笔模考报告里的答题卡（题号圆圈那一页）")
    exp = expected_rows(sections, per_row)
    marks, report, last = {}, [], 0
    for k, rows in enumerate(per_image):
        full = [r for r in rows if not r[2]]
        if not full:
            report.append({"image": k + 1, "rows": 0, "matched": False, "why": "没有完整的一行"})
            continue
        d = full[0][3]
        gaps = [None] + [full[i][0] - full[i - 1][0] for i in range(1, len(full))]
        base = sorted(g for g in gaps[1:] if g) or [2 * d]
        normal = base[0]
        cands = []
        for o in range(0, len(exp) - len(full) + 1):
            ok, score = True, 0
            for i, r in enumerate(full):
                e = exp[o + i]
                if len(r[1]) != e[2]:
                    ok = False
                    break
                if gaps[i] is not None:
                    big = gaps[i] > normal * 1.3
                    score += 1 if big == e[3] else -3
            if ok:
                cands.append((score, o))
        if not cands:
            report.append({"image": k + 1, "rows": len(full), "matched": False,
                           "why": "圈的排法和这一季的题对不上（是不是选错了季，或者截的不是答题卡）"})
            continue
        best = max(c[0] for c in cands)
        good = [o for s_, o in cands if s_ == best]
        o = next((x for x in good if x >= last), good[0])     # 截图按从上到下的顺序选的：取不早于上一张的位置
        last = o
        for i, r in enumerate(full):
            mod, start, n, _ = exp[o + i]
            for j, v in enumerate(r[1]):
                marks[start + j] = v
        first, lastq = exp[o][1], exp[o + len(full) - 1][1] + exp[o + len(full) - 1][2] - 1
        report.append({"image": k + 1, "rows": len(full), "matched": True, "from": first, "to": lastq,
                       "ambiguous": len(good) > 1})
    missing = [n for n in nums if n not in marks]
    return {"season": season, "marks": {str(n): v for n, v in sorted(marks.items())}, "total": len(nums),
            "ok": sum(v == "ok" for v in marks.values()), "bad": sum(v == "bad" for v in marks.values()),
            "missing": missing, "images": report, "per_row": per_row,
            "sections": [{"name": m, "from": a, "to": b} for m, a, b in sections]}


def decode(images):
    out = []
    for x in images or []:
        try:
            out.append(base64.b64decode(str(x).split(",", 1)[-1], validate=False))
        except Exception:
            raise MarksError("截图读取失败，请重新选择")
    return out


# ---------------------------------------------------------------- 写回复盘文件
HEAD = re.compile(r"^### (\d+)\. (✅|❌|⚪)[ \t]*$", re.M)


def apply(paths, season, marks):
    """把 {题号: 'ok'/'bad'} 写进第 N 季的复盘文件。返回 {改了几题, 文件数}"""
    d = next((d for n, d in vault.seasons(paths) if n == season), None)
    if not d:
        raise MarksError("还没有第%d季的板块复盘" % season)
    marks = {int(k): v for k, v in marks.items() if v in ("ok", "bad")}
    changed, files, summary = 0, [], []
    for f in sorted(d.glob("[0-9][0-9]-*.md")):
        text = f.read_text(encoding="utf-8")
        new = text
        for n, v in marks.items():
            icon, word = ("✅", "正确") if v == "ok" else ("❌", "错误")
            m = re.search(r"^### %d\. (✅|❌|⚪)[ \t]*$" % n, new, re.M)
            if not m:
                continue
            old = m.group(1)
            if old == icon:
                continue
            changed += 1
            new = new[:m.start()] + "### %d. %s" % (n, icon) + new[m.end():]
            for bar in ("|", "\\|"):        # 表格里的链接把 | 写成 \|
                new = new.replace("[[#%d. %s%s%d]]" % (n, old, bar, n), "[[#%d. %s%s%d]]" % (n, icon, bar, n))
            # 表格那一行：| [[#36. ✅\|36]] | C | — | ⚪ 未作答 |
            new = re.sub(r"^(\|\s*\[\[#%d\. %s\\?\|%d\]\]\s*\|\s*([A-D?？]*)\s*\|)[^|\n]*\|[^|\n]*\|" % (n, icon, n),
                         lambda mm: "%s %s | %s %s |" % (mm.group(1), mm.group(2) if v == "ok" else "？", icon, word), new, flags=re.M)
            # 答案栏：> 正确答案：**C**　我的答案：**—**　未作答
            seg_start = new.find("### %d. %s" % (n, icon))
            seg_end = HEAD.search(new, seg_start + 5)
            seg_end = seg_end.start() if seg_end else len(new)
            seg = new[seg_start:seg_end]
            seg = re.sub(r"(正确答案：\*\*([A-D?？]*)\*\*　我的答案：)\*\*[^*]*\*\*　\S*",
                         lambda mm: "%s**%s**　%s" % (mm.group(1), mm.group(2) if v == "ok" else "？", word), seg, count=1)
            new = new[:seg_start] + seg + new[seg_end:]
        if new != text:
            heads = HEAD.findall(new)
            done = sum(i != "⚪" for _, i in heads)
            ok = sum(i == "✅" for _, i in heads)
            rate = "%.0f%%" % (100 * ok / done) if done else "—"
            new = re.sub(r"^作答: .*$", "作答: %d" % done, new, count=1, flags=re.M)
            new = re.sub(r"^正确: .*$", "正确: %d" % ok, new, count=1, flags=re.M)
            new = re.sub(r'^正确率: .*$', '正确率: "%s"' % rate, new, count=1, flags=re.M)
            f.write_text(new, encoding="utf-8", newline="\n")
            files.append(f.name)
        heads = HEAD.findall(new)
        summary.append((f.stem, len(heads), sum(i != "⚪" for _, i in heads), sum(i == "✅" for _, i in heads)))
    ov = next(iter(d.glob("00-*总览.md")), None)
    if ov and files:
        t = ov.read_text(encoding="utf-8")
        for stem, n, done, ok in summary:
            rate = "%.0f%%" % (100 * ok / done) if done else "—"
            t = re.sub(r"^\| \[\[%s\]\] \|.*$" % re.escape(stem), "| [[%s]] | %d | %d | %d | %s |" % (stem, n, done, ok, rate), t, flags=re.M)
        ov.write_text(t, encoding="utf-8", newline="\n")
    vault._cache.clear() if hasattr(vault, "_cache") else None
    return {"changed": changed, "files": files}
