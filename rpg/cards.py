"""玉简（照 Anki 做的记忆卡片）：自己刻简（加卡片）、按 FSRS 排期温简（复习）、藏简阁（浏览）、灵识图（统计）。

- 玉简存在库里 训练/卡片/<顶层简匣>.md（Obsidian 里能看能改，坚果云同步），一枚玉简一节：

      ## 玉简 20261007-153012-001
      简匣: 资料分析::速算公式
      类型: 问答            （问答 / 问答+反向 / 填空）
      标签: 隔年增长 公式
      ### 正
      隔年增长率怎么算？
      ### 反
      r = r₁ + r₂ + r₁×r₂

  填空的“正”里写 {{c1::答案}} / {{c1::答案::提示}}，一个编号一张卡。xingce-card skill 写进来的也是这个格式。
  手写的 “## 玉简” 后面没有编号时，第一次读到就补上编号写回文件（编号是温习进度的钥匙，以后不要改）。
- 温习进度存在存档里 state["cards"]（随存档备份），改玉简内容不丢进度：
      sched: {卡: {st 0新/1学习/2复习/3重学, due 时间戳(学习中)或日期(复习), s 稳定度, d 难度, step, reps, lapses, last 日期, susp, leech}}
      decks: {简匣: 规矩}；today: {d, new: {简匣: 数}, rev: {简匣: 数}}；log: ["时间戳|卡|评分|秒数|间隔天"]；undo: [...]
  卡的编号 = 玉简编号#1 / #2（反向）/ #c1、#c2（填空）。
- 排期用 FSRS-5（Anki 23.10 起的默认算法，参数用官方默认值），四个评分：1 再参（重来）2 晦涩（困难）3 通透（良好）4 了然（简单）。
"""
import datetime as dt
import math
import re
import time
from pathlib import Path

LOG_KEEP = 40000
UNDO_KEEP = 10
DAY_ROLL_HOUR = 4                      # 和 Anki 一样，凌晨 4 点才算新的一天
TYPES = ("问答", "问答+反向", "填空")
DEFAULT_DECKS = ["政治理论", "常识判断", "逻辑填空", "片段阅读", "数量关系", "图形推理", "定义判断",
                 "类比推理", "论证逻辑", "形式逻辑", "一拖五", "资料分析"]
DEFAULT_OPTS = {"new_per_day": 20, "rev_per_day": 200, "learn_steps": [1, 10], "relearn_steps": [10],
                "retention": 0.9, "max_ivl": 36500, "leech": 8}
XP = {1: 1, 2: 2, 3: 3, 4: 3}
RATING_NAMES = {1: "再参", 2: "晦涩", 3: "通透", 4: "了然"}
CLOZE = re.compile(r"\{\{c(\d+)::(.*?)(?:::(.*?))?\}\}", re.S)
HEAD = re.compile(r"^## 玉简[ \t]*(\S*)[ \t]*$", re.M)


class CardError(Exception):
    pass


# ================================================================ FSRS-5
W = [0.40255, 1.18385, 3.173, 15.69105, 7.1949, 0.5345, 1.4604, 0.0046, 1.54575, 0.1192, 1.01925,
     1.9395, 0.11, 0.29605, 2.2698, 0.2315, 2.9898, 0.51655, 0.6621]
DECAY, FACTOR = -0.5, 19 / 81


def _clamp_d(d):
    return min(10.0, max(1.0, d))


def init_s(g):
    return max(W[g - 1], 0.1)


def init_d(g):
    return _clamp_d(W[4] - math.exp(W[5] * (g - 1)) + 1)


def next_d(d, g):
    d2 = d - W[6] * (g - 3) * (10 - d) / 9
    return _clamp_d(W[7] * init_d(4) + (1 - W[7]) * d2)


def retrievability(elapsed, s):
    return (1 + FACTOR * max(0.0, elapsed) / s) ** DECAY


def recall_s(d, s, r, g):
    hard = W[15] if g == 2 else 1.0
    easy = W[16] if g == 4 else 1.0
    return s * (math.exp(W[8]) * (11 - d) * s ** (-W[9]) * (math.exp(W[10] * (1 - r)) - 1) * hard * easy + 1)


def forget_s(d, s, r):
    f = W[11] * d ** (-W[12]) * ((s + 1) ** W[13] - 1) * math.exp(W[14] * (1 - r))
    return min(f, s / math.exp(W[17] * W[18]))


def short_s(s, g):
    return s * math.exp(W[17] * (g - 3 + W[18]))


def interval(s, retention, max_ivl):
    ivl = s / FACTOR * (retention ** (1 / DECAY) - 1)
    return int(min(max(1, round(ivl)), max_ivl))


# ================================================================ 时间
def logical_today(now=None):
    """凌晨 4 点前还算前一天"""
    t = dt.datetime.fromtimestamp(now if now is not None else time.time())
    return (t - dt.timedelta(hours=DAY_ROLL_HOUR)).date()


def _days_between(a, b):
    return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days


def fmt_ivl(seconds=None, days=None):
    if days is not None:
        if days < 31:
            return "%d天" % days
        if days < 365:
            return "%.1f月" % (days / 30.4) if days % 30 else "%d月" % (days // 30)
        return "%.1f年" % (days / 365)
    m = max(1, round(seconds / 60))
    return "%d分钟" % m if m < 60 else "%.1f小时" % (m / 60) if m < 1440 else "%d天" % round(m / 1440)


# ================================================================ 玉简文件
def folder(paths):
    return paths.train / "卡片"


def _safe_file(deck):
    top = deck.split("::", 1)[0].strip() or "未分匣"
    return re.sub(r'[\\/:*?"<>|#^\[\]]+', "_", top)[:40] + ".md"


def _new_id(taken):
    base = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    i = int(time.time() * 1000) % 1000
    while True:
        nid = "%s-%03d" % (base, i % 1000)
        if nid not in taken:
            taken.add(nid)
            return nid
        i += 1


def _section(body, name):
    m = re.search(r"^### %s[ \t]*\n(.*?)(?=^### |\Z)" % re.escape(name), body, re.M | re.S)
    return m.group(1).strip("\n").rstrip() if m else ""


def parse_file(text, fallback_deck=""):
    """返回 (文件头, [玉简])；玉简 {id, deck, type, tags, front, back, extra}"""
    heads = list(HEAD.finditer(text))
    header = text[: heads[0].start()] if heads else text
    notes = []
    for i, h in enumerate(heads):
        body = text[h.end(): heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        meta_part = body.split("\n### ", 1)[0]
        meta = {}
        for ln in meta_part.splitlines():
            m = re.match(r"^\s*([^:：\s]+)\s*[:：]\s*(.*)$", ln)
            if m:
                meta[m.group(1)] = m.group(2).strip()
        typ = meta.get("类型", "问答").replace(" ", "").replace("＋", "+")
        if typ in ("反向", "问答反向", "正反"):
            typ = "问答+反向"
        if typ not in TYPES:
            typ = "填空" if CLOZE.search(body) else "问答"
        notes.append({"id": h.group(1).strip(), "deck": meta.get("简匣", "") or fallback_deck, "type": typ,
                      "tags": [t for t in re.split(r"[\s,，、]+", meta.get("标签", "")) if t],
                      "front": _section(body, "正"), "back": _section(body, "反"), "extra": _section(body, "附注"),
                      "ai": _section(body, "师傅讲讲")})
    return header, notes


def note_md(n):
    out = "## 玉简 %s\n简匣: %s\n类型: %s\n" % (n["id"], n["deck"], n["type"])
    if n.get("tags"):
        out += "标签: %s\n" % " ".join(n["tags"])
    out += "### 正\n%s\n### 反\n%s\n" % (n["front"].strip(), n.get("back", "").strip())
    if n.get("extra", "").strip():
        out += "### 附注\n%s\n" % n["extra"].strip()
    if n.get("ai", "").strip():
        out += "### 师傅讲讲\n%s\n" % n["ai"].strip()
    return out + "\n"


def card_ords(n):
    if n["type"] == "填空":
        nums = sorted({int(x) for x in re.findall(r"\{\{c(\d+)::", n["front"])})
        return ["c%d" % k for k in nums] or ["c1"]
    return ["1", "2"] if n["type"] == "问答+反向" else ["1"]


_CACHE = {"key": None, "notes": None, "headers": None}


def load(paths):
    """读全部玉简：(notes 列表, {文件名: 文件头})；没有编号的补上编号写回"""
    d = folder(paths)
    d.mkdir(parents=True, exist_ok=True)
    files = sorted(d.glob("*.md"))
    key = tuple((f.name, f.stat().st_mtime_ns, f.stat().st_size) for f in files)
    if _CACHE["key"] == key:
        return _CACHE["notes"], _CACHE["headers"]
    notes, headers, fix = [], {}, set()
    for f in files:
        header, ns = parse_file(f.read_text(encoding="utf-8-sig"), f.stem)
        headers[f.name] = header
        for n in ns:
            n["file"] = f.name
            notes.append(n)
    taken, seen = set(), set()
    for n in notes:
        if n["id"] and n["id"] not in seen:
            seen.add(n["id"])
    taken |= seen
    seen = set()
    for n in notes:
        if not n["id"] or n["id"] in seen:          # 没编号 / 复制粘贴出来的重号：补一个新的
            n["id"] = _new_id(taken)
            fix.add(n["file"])
        seen.add(n["id"])
    if fix:
        _write_files(paths, notes, headers, fix)
        return load(paths)
    _CACHE.update(key=key, notes=notes, headers=headers)
    return notes, headers


def _write_files(paths, notes, headers, names):
    d = folder(paths)
    for name in names:
        mine = [n for n in notes if n["file"] == name]
        f = d / name
        if not mine and not (headers.get(name) or "").strip():
            if f.exists():
                f.unlink()
            continue
        head = headers.get(name) or "# %s · 玉简\n\n> 行测修仙传的玉简（记忆卡片）。可以在 Obsidian 里改正反面、标签；“## 玉简 编号”那一行别改。\n\n" % f.stem
        f.write_text(head.rstrip("\n") + "\n\n" + "".join(note_md(n) for n in mine), encoding="utf-8", newline="\n")
    _CACHE["key"] = None


def save_notes(paths, notes, headers, touched):
    _write_files(paths, notes, headers, touched)


# ================================================================ 存档里的进度
def data(g):
    c = g.state.setdefault("cards", {})
    c.setdefault("sched", {})
    c.setdefault("decks", {})
    c.setdefault("log", [])
    c.setdefault("undo", [])
    if not c.get("init"):
        for b in DEFAULT_DECKS:
            c["decks"].setdefault(b, {})
        c["init"] = True
    today = logical_today().isoformat()
    if (c.get("today") or {}).get("d") != today:
        c["today"] = {"d": today, "new": {}, "rev": {}, "secs": 0, "n": 0}
    return c


def deck_names(c, notes):
    names = set(c["decks"]) | {n["deck"] for n in notes if n["deck"]}
    full = set()
    for nm in names:
        parts = nm.split("::")
        for i in range(1, len(parts) + 1):
            full.add("::".join(parts[:i]))
    order = {b: i for i, b in enumerate(DEFAULT_DECKS)}
    return sorted(full, key=lambda x: [(order.get(p, 99), p) for p in x.split("::")])


def opts(c, deck):
    """简匣规矩：自己没设的沿用上层，都没有用默认"""
    out = dict(DEFAULT_OPTS)
    out.update({k: v for k, v in (c.get("defaults") or {}).items() if k in DEFAULT_OPTS})   # 修炼殿「⚙ 每日数量」：全部简匣的默认
    parts = deck.split("::")
    for i in range(1, len(parts) + 1):
        out.update({k: v for k, v in (c["decks"].get("::".join(parts[:i])) or {}).items() if k in DEFAULT_OPTS})
    return out


def _in(deck, parent):
    return not parent or deck == parent or deck.startswith(parent + "::")


def _ancestors(deck):
    parts = deck.split("::")
    return ["::".join(parts[:i]) for i in range(1, len(parts) + 1)]


def all_cards(notes):
    for n in notes:
        for o in card_ords(n):
            yield "%s#%s" % (n["id"], o), n, o


def _sched(c, key):
    return c["sched"].get(key) or {"st": 0}


def _left(c, deck, kind):
    """这个简匣今天还能出多少新简 / 复习（本匣和所有上层的上限取最小）"""
    left = 10 ** 9
    for a in _ancestors(deck):
        o = opts(c, a)
        lim = o["new_per_day"] if kind == "new" else o["rev_per_day"]
        left = min(left, lim - c["today"][kind].get(a, 0))
    return max(0, left)


def _siblings_today(c, today):
    """今天已经温过的玉简（同一枚玉简的另一张卡今天不再出，免得反向 / 填空互相提示）"""
    out = set()
    start = dt.datetime.combine(dt.date.fromisoformat(today), dt.time(DAY_ROLL_HOUR)).timestamp()
    for row in reversed(c["log"]):
        ts, key = row.split("|", 2)[:2]
        if float(ts) < start:
            break
        out.add(key.split("#")[0])
    return out


def queue(g, deck, now=None):
    """要温的卡（按 Anki：到期的学习中 → 复习和新简穿插；本匣和上层的每日上限都算），和三个计数"""
    now = now or time.time()
    c = data(g)
    notes, _ = load(g.paths)
    today = c["today"]["d"]
    learn, review, new, later = [], [], [], []
    seen = _siblings_today(c, today)
    new_left, rev_left = {}, {}
    for key, n, o in all_cards(notes):
        if not _in(n["deck"], deck):
            continue
        s = _sched(c, key)
        if s.get("susp"):
            continue
        if s["st"] in (1, 3):
            (learn if s["due"] <= now else later).append((s["due"], key))
        elif s["st"] == 2:
            if s["due"] <= today and n["id"] not in seen:
                review.append((s["due"], key, n["deck"]))
        elif n["id"] not in seen:
            new.append((key, n["deck"]))
    learn.sort()
    review.sort()
    rv, nw = [], []
    for due, key, dk in review:
        rv_left = rev_left.setdefault(dk, _left(c, dk, "rev"))
        if rv_left > 0 and (not deck or len(rv) < _left(c, deck, "rev")):
            rv.append(key)
            rev_left[dk] = rv_left - 1
    used_notes = set()
    for key, dk in new:
        nid = key.split("#")[0]
        if nid in used_notes:            # 同一枚玉简的几张新卡一天只出一张
            continue
        nl = new_left.setdefault(dk, _left(c, dk, "new"))
        if nl > 0 and (not deck or len(nw) < _left(c, deck, "new")):
            nw.append(key)
            used_notes.add(nid)
            new_left[dk] = nl - 1
    order = [k for _, k in learn]
    i = j = 0
    while i < len(rv) or j < len(nw):            # 每 4 张复习插 1 张新简
        for _ in range(4):
            if i < len(rv):
                order.append(rv[i])
                i += 1
        if j < len(nw):
            order.append(nw[j])
            j += 1
    if not order and later:                       # 都温完了，20 分钟内到期的学习卡提前出
        due, key = min(later)
        if due - now <= 20 * 60:
            order.append(key)
    counts = {"new": len(nw), "learn": len(learn), "review": len(rv)}
    return order, counts, later


# ================================================================ 评分
def _preview(c, s, deck, rating, now):
    """评分后的新状态（不改存档）"""
    o = opts(c, deck)
    s = dict(s)
    today = logical_today(now).isoformat()
    steps = o["learn_steps"] or []
    relearn = o["relearn_steps"] or []
    st = s.get("st", 0)

    def graduate(days):
        s.update(st=2, due=(dt.date.fromisoformat(today) + dt.timedelta(days=days)).isoformat(), ivl=days, step=0)

    def to_step(lst, k, extra=None):
        mins = extra if extra is not None else lst[k]
        s.update(st=1 if lst is steps else 3, step=k, due=now + mins * 60, ivl=0)

    if st == 0:
        s["s"], s["d"] = init_s(rating), init_d(rating)
        s["reps"], s["lapses"] = 0, 0
        if rating == 4 or not steps:
            graduate(interval(s["s"], o["retention"], o["max_ivl"]))
        elif rating == 1:
            to_step(steps, 0)
        elif rating == 2:
            to_step(steps, 0, (steps[0] + steps[1]) / 2 if len(steps) > 1 else steps[0] * 1.5)
        elif len(steps) > 1:
            to_step(steps, 1)
        else:
            graduate(interval(s["s"], o["retention"], o["max_ivl"]))
    elif st in (1, 3):
        lst = steps if st == 1 else relearn
        s["s"], s["d"] = short_s(s["s"], rating), next_d(s["d"], rating)
        k = min(s.get("step", 0), max(0, len(lst) - 1))
        if rating == 1:
            if lst:
                to_step(lst, 0)
                s["st"] = st
            else:
                graduate(1)
        elif rating == 2:
            if lst:
                to_step(lst, k, (lst[0] + lst[1]) / 2 if k == 0 and len(lst) > 1 else lst[k] * (1.5 if len(lst) == 1 else 1))
                s["st"] = st
            else:
                graduate(1)
        elif rating == 3 and k + 1 < len(lst):
            to_step(lst, k + 1)
            s["st"] = st
        else:
            ivl = interval(s["s"], o["retention"], o["max_ivl"])
            if rating == 4:
                ivl = max(ivl, 2 if st == 1 else 1)
            graduate(ivl)
    else:
        elapsed = _days_between(s.get("last") or today, today)
        r = retrievability(elapsed, s["s"])
        old_d = s["d"]
        s["d"] = next_d(old_d, rating)
        if rating == 1:
            s["s"] = forget_s(old_d, s["s"], r)
            s["lapses"] = s.get("lapses", 0) + 1
            if relearn:
                to_step(relearn, 0)
                s["st"] = 3
            else:
                graduate(interval(s["s"], o["retention"], o["max_ivl"]))
        else:
            ss = {g: recall_s(old_d, s["s"], r, g) for g in (2, 3, 4)}
            iv = {g: interval(ss[g], o["retention"], o["max_ivl"]) for g in (2, 3, 4)}
            iv[2] = min(iv[2], iv[3])
            iv[3] = max(iv[3], iv[2] + 1)
            iv[4] = max(iv[4], iv[3] + 1)
            s["s"] = ss[rating]
            graduate(min(iv[rating], o["max_ivl"]))
    s["reps"] = s.get("reps", 0) + 1
    s["last"] = today
    return s


def _label(s, now):
    if s["st"] == 2:
        return fmt_ivl(days=_days_between(logical_today(now).isoformat(), s["due"]))
    return fmt_ivl(seconds=s["due"] - now)


def intervals(g, key, deck, now=None):
    now = now or time.time()
    c = data(g)
    s = _sched(c, key)
    return {r: _label(_preview(c, s, deck, r, now), now) for r in (1, 2, 3, 4)}


def _find(notes, key):
    nid, _, o = key.partition("#")
    for n in notes:
        if n["id"] == nid and o in card_ords(n):
            return n, o
    raise CardError("这枚玉简不见了（可能在 Obsidian 里删了）")


def answer(g, key, rating, secs=0, now=None):
    now = now or time.time()
    if rating not in (1, 2, 3, 4):
        raise CardError("评分只能是 1~4")
    c = data(g)
    notes, _ = load(g.paths)
    n, _ = _find(notes, key)
    old = c["sched"].get(key)
    s = _sched(c, key)
    new = _preview(c, s, n["deck"], rating, now)
    kind = "new" if s["st"] == 0 else "rev" if s["st"] == 2 else ""
    c["undo"] = (c["undo"] + [{"key": key, "old": old, "kind": kind, "deck": n["deck"], "log": len(c["log"]),
                               "secs": int(secs), "xp": XP[rating]}])[-UNDO_KEEP:]
    if kind:
        for a in _ancestors(n["deck"]):
            c["today"][kind][a] = c["today"][kind].get(a, 0) + 1
    if rating == 1 and s["st"] == 2 and new.get("lapses", 0) >= opts(c, n["deck"])["leech"]:
        new["leech"] = True
    c["sched"][key] = new
    ivl = new.get("ivl", 0) if new["st"] == 2 else 0
    c["log"].append("%d|%s|%d|%d|%d" % (now, key, rating, min(int(secs), 600), ivl))
    if len(c["log"]) > LOG_KEEP:
        del c["log"][: len(c["log"]) - LOG_KEEP]
    c["today"]["secs"] += min(int(secs), 600)
    c["today"]["n"] += 1
    LAST_ANSWER["t"] = time.time()
    return award(g, XP[rating], n["deck"]) + ([{"kind": "info", "msg": "这枚玉简已经忘了 %d 次，标成「顽固」：换个角度重新理解一下，或者在藏简阁里改写它。" % new["lapses"]}]
                                               if new.get("leech") and not (old or {}).get("leech") else [])


def undo(g):
    c = data(g)
    if not c["undo"]:
        raise CardError("没有可以撤销的")
    u = c["undo"].pop()
    if u["old"] is None:
        c["sched"].pop(u["key"], None)
    else:
        c["sched"][u["key"]] = u["old"]
    if u["kind"]:
        for a in _ancestors(u["deck"]):
            c["today"][u["kind"]][a] = max(0, c["today"][u["kind"]].get(a, 0) - 1)
    del c["log"][u["log"]:]
    c["today"]["secs"] = max(0, c["today"]["secs"] - u["secs"])
    c["today"]["n"] = max(0, c["today"]["n"] - 1)
    award(g, -u["xp"], u["deck"])
    return u["key"]


LAST_ANSWER = {"t": 0}


def reviewing(window=600):
    """最近有没有在温简（心跳计时用：10 分钟内在温简页面上取过卡、答过卡、问过师傅）"""
    return time.time() - LAST_ANSWER["t"] <= window


def award(g, xp, deck):
    """温简的修为：每天一条“温简”记录累加（不是每张一条，修仙录不会被刷屏）；境界变化照常提示"""
    if not xp:
        return []
    before = g.realm_info()
    g.state["xp"] = max(0, g.state["xp"] + xp)
    ev = next((e for e in reversed(g.state["events"][-50:]) if e.get("type") == "cards" and e.get("d") == g.t), None)
    if ev is None:
        ev = {"t": dt.datetime.now().isoformat(timespec="seconds"), "d": g.t, "type": "cards", "board": "",
              "item": "", "ok": True, "xp": 0, "note": "温简"}
        g.state["events"].append(ev)
    ev["xp"] = max(0, ev["xp"] + xp)
    ev["note"] = "温简 %d 枚" % data(g)["today"]["n"]
    after = g.realm_info()
    out = []
    if (after["big"], after["sub"]) != (before["big"], before["sub"]) and after["score"] > before["score"]:
        out.append({"kind": "realm", "name": after["name"], "major": after["big"] != before["big"],
                    "score": after["score"], "big_name": after["big_name"], "next": after["next"],
                    "target": after["target"], "xp": g.state["xp"], "from": before["name"]})
    return out


# ================================================================ 给网页的
def tree(g):
    """简匣树：[{name, label, depth, new, learn, review, total, susp}]（数字含子匣）"""
    c = data(g)
    notes, _ = load(g.paths)
    names = deck_names(c, notes)
    out = []
    for nm in names:
        order, counts, _ = queue(g, nm)
        total = sum(1 for _, n, _ in all_cards(notes) if _in(n["deck"], nm))
        out.append({"name": nm, "label": nm.split("::")[-1], "depth": nm.count("::"), **counts, "total": total})
    return out


def overview(g):
    c = data(g)
    notes, _ = load(g.paths)
    return {"decks": tree(g), "today": {"n": c["today"]["n"], "secs": c["today"]["secs"]}, "defaults": opts(c, ""),
            "cards": sum(1 for _ in all_cards(notes)), "notes": len(notes), "can_undo": bool(c["undo"])}


def card_view(g, key):
    notes, _ = load(g.paths)
    n, o = _find(notes, key)
    from . import notes as notes_mod
    text = n["front"] + "\n" + n["back"] + "\n" + n.get("extra", "")
    imgs = notes_mod.resolve_images(g.paths, text, folder(g.paths)) if g.paths.vault else {}
    s = _sched(data(g), key)
    return {"key": key, "id": n["id"], "ord": o, "deck": n["deck"], "type": n["type"], "tags": n["tags"],
            "front": n["front"], "back": n["back"], "extra": n.get("extra", ""), "images": imgs,
            "state": s.get("st", 0), "leech": bool(s.get("leech")), "ai": n.get("ai", "")}


def next_card(g, deck):
    LAST_ANSWER["t"] = time.time()          # 在温简页面上就算在复习（心跳计时用）
    order, counts, later = queue(g, deck)
    out = {"counts": counts, "deck": deck}
    if not order:
        out["done"] = True
        if later:
            out["next_learn"] = fmt_ivl(seconds=min(d for d, _ in later) - time.time())
        return out
    key = order[0]
    out["card"] = card_view(g, key)
    out["intervals"] = intervals(g, key, out["card"]["deck"])
    return out


# ---------------------------------------------------------------- 刻简 / 改 / 删 / 暂停 / 移动
def _clean_deck(deck):
    parts = [re.sub(r"[#\n\r]", "", p).strip() for p in str(deck or "").split("::")]
    parts = [p for p in parts if p]
    if not parts:
        raise CardError("先选一个简匣")
    return "::".join(parts)[:120]


def _check(n):
    if not n["front"].strip():
        raise CardError("正面不能是空的")
    if n["type"] == "填空" and not CLOZE.search(n["front"]):
        raise CardError("填空玉简的正面要有 {{c1::要挖空的字}}")
    if n["type"] != "填空" and not n["back"].strip():
        raise CardError("反面不能是空的")


def add(g, body):
    notes, headers = load(g.paths)
    typ = body.get("type") if body.get("type") in TYPES else "问答"
    deck = _clean_deck(body.get("deck"))
    n = {"id": _new_id({x["id"] for x in notes}), "deck": deck, "type": typ,
         "tags": [t for t in re.split(r"[\s,，、]+", str(body.get("tags") or "")) if t][:20],
         "front": str(body.get("front") or "").strip(), "back": str(body.get("back") or "").strip(),
         "extra": str(body.get("extra") or "").strip()}
    _check(n)
    n["file"] = _safe_file(deck)
    notes.append(n)
    save_notes(g.paths, notes, headers, {n["file"]})
    data(g)["decks"].setdefault(deck.split("::")[0], {})
    return {"id": n["id"], "cards": len(card_ords(n))}


def add_many(g, deck, items):
    """一次刻入多枚（师傅制卡审完后）：[{type, front, back, tags, extra}]，格式不对的跳过"""
    deck = _clean_deck(deck)
    notes, headers = load(g.paths)
    taken = {x["id"] for x in notes}
    added, bad = 0, 0
    for it in items or []:
        typ = it.get("type") if it.get("type") in TYPES else "问答"
        tags = it.get("tags") or []
        if isinstance(tags, str):
            tags = re.split(r"[\s,，、]+", tags)
        n = {"id": _new_id(taken), "deck": _clean_deck(it.get("deck") or deck), "type": typ,
             "tags": [str(t) for t in tags if str(t).strip()][:20], "front": str(it.get("front") or "").strip(),
             "back": str(it.get("back") or "").strip(), "extra": str(it.get("extra") or "").strip()}
        try:
            _check(n)
        except CardError:
            bad += 1
            continue
        n["file"] = _safe_file(n["deck"])
        notes.append(n)
        added += 1
    save_notes(g.paths, notes, headers, {_safe_file(deck)} | {n["file"] for n in notes[-added:]} if added else set())
    data(g)["decks"].setdefault(deck, {})
    return {"added": added, "skipped": bad}


def update(g, body):
    notes, headers = load(g.paths)
    n = next((x for x in notes if x["id"] == body.get("id")), None)
    if not n:
        raise CardError("这枚玉简不见了")
    old_file = n["file"]
    new = dict(n)
    for k in ("front", "back", "extra"):
        if k in body:
            new[k] = str(body[k] or "").strip()
    if "type" in body and body["type"] in TYPES:
        new["type"] = body["type"]
    if "tags" in body:
        new["tags"] = [t for t in re.split(r"[\s,，、]+", str(body["tags"] or "")) if t][:20]
    if "deck" in body:
        new["deck"] = _clean_deck(body["deck"])
        new["file"] = _safe_file(new["deck"])
    _check(new)
    n.update(new)
    save_notes(g.paths, notes, headers, {old_file, n["file"]})
    return {"id": n["id"]}


def delete(g, ids):
    ids = set(ids or [])
    notes, headers = load(g.paths)
    touched = {n["file"] for n in notes if n["id"] in ids}
    keep = [n for n in notes if n["id"] not in ids]
    save_notes(g.paths, keep, headers, touched)
    c = data(g)
    for k in [k for k in c["sched"] if k.split("#")[0] in ids]:
        del c["sched"][k]
    return {"deleted": len(notes) - len(keep)}


def suspend(g, keys, on=True):
    c = data(g)
    notes, _ = load(g.paths)
    valid = {k for k, _, _ in all_cards(notes)}
    n = 0
    for k in keys or []:
        if k in valid:
            s = c["sched"].setdefault(k, {"st": 0})
            s["susp"] = bool(on)
            n += 1
    return {"n": n}


def forget(g, keys):
    """重置为新简（Anki 的“遗忘”）"""
    c = data(g)
    for k in keys or []:
        c["sched"].pop(k, None)
    return {"n": len(keys or [])}


def move(g, ids, deck):
    deck = _clean_deck(deck)
    notes, headers = load(g.paths)
    touched = set()
    for n in notes:
        if n["id"] in set(ids or []):
            touched |= {n["file"], _safe_file(deck)}
            n["deck"], n["file"] = deck, _safe_file(deck)
    save_notes(g.paths, notes, headers, touched)
    data(g)["decks"].setdefault(deck.split("::")[0], {})
    return {"n": len(touched) and sum(1 for n in notes if n["id"] in set(ids or []))}


# ---------------------------------------------------------------- 简匣
def _parse_opts(src):
    o = {}
    for k in ("new_per_day", "rev_per_day", "leech", "max_ivl"):
        if k in src and str(src[k]).strip() != "":
            o[k] = max(0, min(9999 if k != "max_ivl" else 36500, int(float(src[k]))))
    if "retention" in src and str(src["retention"]).strip() != "":
        o["retention"] = min(0.99, max(0.7, float(src["retention"])))
    for k in ("learn_steps", "relearn_steps"):
        if k in src:
            vals = [float(x) for x in re.split(r"[\s,，]+", str(src[k]).strip()) if x]
            o[k] = [v if v != int(v) else int(v) for v in vals if 0 < v <= 1440][:8]
    return o


def deck_action(g, body):
    c = data(g)
    act = body.get("action")
    if act == "create":
        name = _clean_deck(body.get("name"))
        c["decks"].setdefault(name, {})
        return {"name": name}
    if act in ("options", "get") and body.get("name") == "*":          # 全部简匣的默认规矩
        if act == "get":
            o = dict(DEFAULT_OPTS)
            o.update(c.get("defaults") or {})
            return {"name": "*", "options": o, "own": c.get("defaults") or {}}
        c["defaults"] = _parse_opts(body.get("options") or {})
        return {"name": "*", "options": opts(c, "")}
    if act == "options":
        name = _clean_deck(body.get("name"))
        c["decks"][name] = _parse_opts(body.get("options") or {})
        return {"name": name, "options": opts(c, name)}
    if act == "get":
        name = _clean_deck(body.get("name"))
        return {"name": name, "options": opts(c, name), "own": c["decks"].get(name, {})}
    notes, headers = load(g.paths)
    if act == "rename":
        old, new = _clean_deck(body.get("name")), _clean_deck(body.get("new"))
        touched = set()
        for n in notes:
            if _in(n["deck"], old):
                touched.add(n["file"])
                n["deck"] = new + n["deck"][len(old):]
                n["file"] = _safe_file(n["deck"])
                touched.add(n["file"])
        for k in [k for k in c["decks"] if _in(k, old)]:
            c["decks"][new + k[len(old):]] = c["decks"].pop(k)
        save_notes(g.paths, notes, headers, touched)
        return {"name": new}
    if act == "delete":
        name = _clean_deck(body.get("name"))
        ids = [n["id"] for n in notes if _in(n["deck"], name)]
        if ids and not body.get("with_cards"):
            raise CardError("这个简匣里还有 %d 枚玉简：先移走，或者确认连玉简一起删" % len(ids))
        delete(g, ids)
        for k in [k for k in c["decks"] if _in(k, name)]:
            del c["decks"][k]
        return {"deleted": len(ids)}
    raise CardError("不认识的操作")


# ---------------------------------------------------------------- 藏简阁
def _plain(s):
    s = re.sub(r"\*\*|==|~~|`", "", s or "")
    return re.sub(r"\s+", " ", CLOZE.sub(lambda m: m.group(2), re.sub(r"!\[\[[^\]]*\]\]|!\[[^\]]*\]\([^)]*\)", "［图］", s or ""))).strip()


def search(g, body):
    c = data(g)
    notes, _ = load(g.paths)
    q = str(body.get("q") or "").strip().lower()
    deck = body.get("deck") or ""
    flt = body.get("filter") or ""
    today = c["today"]["d"]
    rows = []
    for key, n, o in all_cards(notes):
        if deck and not _in(n["deck"], deck):
            continue
        if q and not any(q in x.lower() for x in (n["front"], n["back"], n.get("extra", ""), " ".join(n["tags"]), n["id"])):
            continue
        s = _sched(c, key)
        st = "暂停" if s.get("susp") else ["新简", "参悟中", "复习", "重参"][s.get("st", 0)]
        if flt == "new" and s.get("st", 0) != 0 or flt == "due" and not (s.get("st") == 2 and s["due"] <= today) \
                or flt == "susp" and not s.get("susp") or flt == "leech" and not s.get("leech"):
            continue
        rows.append({"key": key, "id": n["id"], "ord": o, "deck": n["deck"], "type": n["type"], "tags": n["tags"],
                     "front": _plain(n["front"])[:120], "back": _plain(n["back"])[:80], "state": st,
                     "due": s.get("due") if s.get("st") == 2 else "", "ivl": s.get("ivl", 0),
                     "reps": s.get("reps", 0), "lapses": s.get("lapses", 0), "leech": bool(s.get("leech"))})
    page, size = max(0, int(body.get("page") or 0)), 100
    return {"total": len(rows), "rows": rows[page * size:(page + 1) * size], "page": page, "size": size}


def note_get(g, nid):
    notes, _ = load(g.paths)
    n = next((x for x in notes if x["id"] == nid), None)
    if not n:
        raise CardError("这枚玉简不见了")
    return {k: n[k] for k in ("id", "deck", "type", "tags", "front", "back", "extra")}


def info(g, key):
    c = data(g)
    s = _sched(c, key)
    hist = []
    for row in c["log"]:
        ts, k, r, secs, ivl = row.split("|")
        if k == key:
            hist.append({"t": dt.datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M"), "rating": RATING_NAMES[int(r)],
                         "secs": int(secs), "ivl": int(ivl)})
    v = card_view(g, key)
    v["sched"] = {"state": ["新简", "参悟中", "复习", "重参"][s.get("st", 0)], "due": s.get("due") if s.get("st") == 2 else "",
                  "stability": round(s.get("s", 0), 1), "difficulty": round(s.get("d", 0), 1), "reps": s.get("reps", 0),
                  "lapses": s.get("lapses", 0), "susp": bool(s.get("susp"))}
    v["history"] = hist[-50:]
    return v


# ---------------------------------------------------------------- 灵识图
def stats(g, deck=""):
    c = data(g)
    notes, _ = load(g.paths)
    keys = {k for k, n, _ in all_cards(notes) if not deck or _in(n["deck"], deck)}
    today = dt.date.fromisoformat(c["today"]["d"])
    heat, ok, tot, by_rating = {}, 0, 0, {1: 0, 2: 0, 3: 0, 4: 0}
    month_ago = time.time() - 30 * 86400
    for row in c["log"]:
        ts, k, r, secs, _ = row.split("|")
        if k not in keys:
            continue
        d = logical_today(float(ts)).isoformat()
        h = heat.setdefault(d, [0, 0])
        h[0] += 1
        h[1] += int(secs)
        if float(ts) >= month_ago:
            by_rating[int(r)] += 1
            tot += 1
            ok += int(r) > 1
    forecast = [0] * 31
    states = {"新简": 0, "参悟中": 0, "复习": 0, "暂停": 0}
    mature = 0
    for k in keys:
        s = _sched(c, k)
        if s.get("susp"):
            states["暂停"] += 1
            continue
        states[["新简", "参悟中", "复习", "参悟中"][s.get("st", 0)]] += 1
        if s.get("st") == 2:
            dd = max(0, (dt.date.fromisoformat(s["due"]) - today).days)
            if dd <= 30:
                forecast[dd] += 1
            mature += s.get("ivl", 0) >= 21
    days = sorted(heat)
    streak, d = 0, today
    while d.isoformat() in heat:
        streak += 1
        d -= dt.timedelta(days=1)
    return {"heat": {k: heat[k] for k in days[-370:]}, "forecast": forecast, "states": states, "mature": mature,
            "retention": round(ok / tot, 3) if tot else None, "ratings": by_rating, "streak": streak,
            "total_reviews": sum(v[0] for v in heat.values()), "days": len(heat)}


# ---------------------------------------------------------------- 导入（Anki 导出的纯文本 / TSV）
def html_to_md(s):
    s = re.sub(r"(?i)<br\s*/?>|</div>|</p>", "\n", s or "")
    s = re.sub(r"(?i)<li[^>]*>", "\n- ", s)
    s = re.sub(r"(?i)</?(b|strong)>", "**", s)
    s = re.sub(r"(?i)</?(i|em)>", "*", s)
    s = re.sub(r'(?i)<img[^>]*src="([^"]+)"[^>]*>', r"![[\1]]", s)
    s = re.sub(r"<[^>]+>", "", s)
    import html as _html
    s = _html.unescape(s).replace("\xa0", " ")
    return re.sub(r"\n{3,}", "\n\n", "\n".join(x.rstrip() for x in s.splitlines())).strip()


def import_text(g, body):
    deck = _clean_deck(body.get("deck"))
    text = str(body.get("text") or "")
    sep = "\t"
    rows, skipped = [], 0
    tags_col = None
    for ln in text.splitlines():
        if ln.startswith("#"):
            m = re.match(r"#separator:(\S+)", ln)
            if m:
                sep = {"tab": "\t", "comma": ",", "semicolon": ";", "pipe": "|"}.get(m.group(1).lower(), m.group(1))
            m = re.match(r"#tags column:(\d+)", ln)
            if m:
                tags_col = int(m.group(1)) - 1
            continue
        if not ln.strip():
            continue
        parts = ln.split(sep)
        if sep == "|" and len(parts) >= 2 and set(parts[0].strip()) <= set("-"):
            continue                      # anki-expert 那种 Markdown 表格的分隔行
        if len(parts) < 2 and not CLOZE.search(ln):
            skipped += 1
            continue
        rows.append([p.strip().strip('"') for p in parts])
    if rows and sep == "|" and rows[0][0].lower() in ("question", "问题", "正面"):
        rows = rows[1:]
    notes, headers = load(g.paths)
    taken = {x["id"] for x in notes}
    added = []
    for r in rows:
        front = html_to_md(r[0])
        back = html_to_md(r[1]) if len(r) > 1 else ""
        tcol = tags_col if tags_col is not None else (2 if len(r) > 2 else None)
        tags = [t for t in re.split(r"\s+", r[tcol]) if t] if tcol is not None and tcol < len(r) else []
        typ = "填空" if CLOZE.search(front) else "问答"
        n = {"id": _new_id(taken), "deck": deck, "type": typ, "tags": tags[:20], "front": front, "back": back, "extra": ""}
        try:
            _check(n)
        except CardError:
            skipped += 1
            continue
        n["file"] = _safe_file(deck)
        added.append(n)
    if added:
        notes.extend(added)
        save_notes(g.paths, notes, headers, {_safe_file(deck)})
        data(g)["decks"].setdefault(deck.split("::")[0], {})
    return {"added": len(added), "skipped": skipped}


# ---------------------------------------------------------------- 图片（粘贴 / 手写）
def save_image(paths, data_url):
    import base64
    m = re.match(r"^data:image/(png|jpeg|jpg|gif|webp);base64,(.+)$", str(data_url or ""), re.S)
    if not m:
        raise CardError("图片格式不对")
    raw = base64.b64decode(m.group(2))
    if len(raw) > 8 * 1024 * 1024:
        raise CardError("图片太大（超过 8MB）")
    d = folder(paths) / "图片"
    d.mkdir(parents=True, exist_ok=True)
    name = "%s-%03d.%s" % (dt.datetime.now().strftime("%Y%m%d-%H%M%S"), int(time.time() * 1000) % 1000,
                           "jpg" if m.group(1) == "jpeg" else m.group(1))
    (d / name).write_bytes(raw)
    return {"path": "训练/卡片/图片/" + name, "md": "![[训练/卡片/图片/%s]]" % name}


# ---------------------------------------------------------------- 🙋 师傅讲讲：只帮着记，不评判卡片
EXPLAIN_SYSTEM = ("你是帮学员记忆卡片的师傅。卡片是学员自己整理的、要记住的内容，以卡片为准："
                  "不评判卡片对不对、不纠正、不说“你写错了”、不另外补充卡片以外的新知识点、不改写卡片的分类和结论。"
                  "你只做一件事：帮学员把这张卡记牢。\n"
                  "1. 先用一两句话把卡片内容理顺（不增删内容）；\n"
                  "2. 再给 1~2 种最合适的记忆办法：口诀（取首字 / 谐音 / 顺口溜）、联想画面、对比记忆、生活中的例子、记忆宫殿等；\n"
                  "3. 简短，Markdown 格式，不超过 250 字。学员追问时也只围绕怎么记住卡片内容回答。")


def explain_prompt(card, question, history):
    def plain(s):
        return CLOZE.sub(lambda m: m.group(2), s or "")
    ctx = ("要记住的卡片（简匣「%s」）：\n【正面】\n%s\n【反面】\n%s%s"
           % (card["deck"], plain(card["front"]), plain(card["back"]) or "（填空卡，要记的就是正面挖空的部分）",
              ("\n【附注】\n" + card["extra"]) if card.get("extra") else ""))
    msgs = [{"role": "system", "content": EXPLAIN_SYSTEM},
            {"role": "user", "content": ctx + "\n\n" + (question or "帮我记住这张卡。")}]
    for h in (history or [])[-6:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            msgs.insert(-1, {"role": h["role"], "content": str(h["content"])[:2000]})
    return msgs


def save_explain(g, key, question, reply):
    """师傅讲过的存进这枚玉简的“### 师傅讲讲”（Obsidian 里也能看），以后翻面时可以展开再看"""
    notes, headers = load(g.paths)
    n, _ = _find(notes, key)
    q = re.sub(r"\s+", " ", question or "帮我记住这张卡").strip()[:60]
    body = re.sub(r"^(#+)\s", lambda m: "＃" * len(m.group(1)) + " ", reply.strip(), flags=re.M)   # 回复里的标题别打乱玉简格式
    entry = "#### %s · %s\n%s" % (dt.datetime.now().strftime("%m-%d %H:%M"), q, body)
    n["ai"] = (n.get("ai", "").strip() + "\n\n" + entry).strip()
    save_notes(g.paths, notes, headers, {n["file"]})
    LAST_ANSWER["t"] = time.time()
    return n["ai"]
