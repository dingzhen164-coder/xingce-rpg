"""宗门大比：每周粉笔模考的成绩与走势。

- 每一季的对错来自 FB模考试卷复盘/板块复盘/第N季/NN-板块.md（✅ 对、❌ 错、⚪ 没做），自动统计各模块正确率；
- 粉笔成绩单上的数字（我的分数、大比平均分、最高分、已击败、排名 / 总人数、各模块用时、各模块得分）在大比页录入，
  存在存档 state["mocks"]["<季>"]；
- 各模块得分没录时估算：按答对题数折到总分（每道题同分；录了总分就按总分等比例分）；
- 导入一份模考试卷（拆分 PDF 或导入那一季）时，给演武 · 历练记记一笔 120 分钟（每季只记一次）。
"""
from . import vault

# 六大模块 ← 拆分出来的 13 个板块文件
MODULES = (
    ("政治理论", ("政治理论",)),
    ("常识判断", ("常识判断",)),
    ("言语理解", ("逻辑填空", "中心理解", "语句排序", "片段阅读")),
    ("数量关系", ("数量关系",)),
    ("判断推理", ("图形推理", "定义判断", "类比关系", "类比推理", "论证逻辑", "形式逻辑", "一拖五")),
    ("资料分析", ("资料分析",)),
)
MODULE_OF = {b: m for m, bs in MODULES for b in bs}
MODULE_NAMES = [m for m, _ in MODULES]
IMPORT_MINUTES = 120
FIELDS = ("score", "avg", "top", "beat", "rank", "people")


class MockError(Exception):
    pass


def _num(v, lo=None, hi=None, integer=False):
    if v in (None, ""):
        return None
    try:
        x = int(v) if integer else round(float(v), 2)
    except (TypeError, ValueError):
        raise MockError("「%s」不是数字" % v)
    if (lo is not None and x < lo) or (hi is not None and x > hi):
        raise MockError("数字 %s 超出范围" % v)
    return x


def season_counts(paths, season_dir):
    """{模块: {"boards": {板块: [对, 错, 没做, 总]}, "ok", "total"}}"""
    out = {m: {"boards": {}, "ok": 0, "total": 0} for m in MODULE_NAMES}
    for f in sorted(season_dir.glob("[0-9][0-9]-*.md")):
        board = f.stem[3:]
        m = MODULE_OF.get(board)
        if not m:
            continue
        qs = vault.parse_board_file(f)
        ok = sum(q["icon"] == "✅" for q in qs)
        bad = sum(q["icon"] == "❌" for q in qs)
        blank = sum(q["icon"] == "⚪" for q in qs)
        out[m]["boards"][board] = [ok, bad, blank, len(qs)]
        out[m]["ok"] += ok
        out[m]["total"] += len(qs)
    return out


def _boss_score(g, n):
    """修仙录里以前记的大比成绩（名字里有“第N季”或“N季”）"""
    for b in reversed(g.state.get("boss", [])):
        if b.get("kind", "大比") == "大比" and ("第%d季" % n in b["name"] or "%d季" % n in b["name"]):
            return b["score"]
    return None


def summary(g):
    data = g.state.setdefault("mocks", {})
    seasons = []
    for n, d in vault.seasons(g.paths):
        counts = season_counts(g.paths, d)
        total_q = sum(c["total"] for c in counts.values())
        if not total_q:
            continue
        rec = data.get(str(n), {})
        score = rec.get("score")
        if score is None:
            score = _boss_score(g, n)
        ok_all = sum(c["ok"] for c in counts.values())
        mods = []
        for m in MODULE_NAMES:
            c = counts[m]
            if not c["total"]:
                continue
            if score is not None and ok_all:
                est = score * c["ok"] / ok_all
            else:
                est = 100 * c["ok"] / total_q
            real = (rec.get("scores") or {}).get(m)
            mods.append({"name": m, "ok": c["ok"], "total": c["total"], "acc": c["ok"] / c["total"],
                         "score": real if real is not None else round(est, 1), "estimated": real is None,
                         "minutes": (rec.get("minutes") or {}).get(m),
                         "boards": [{"board": b, "ok": v[0], "wrong": v[1], "blank": v[2], "total": v[3]} for b, v in c["boards"].items()]})
        mins = [x["minutes"] for x in mods if x["minutes"] is not None]
        seasons.append({"season": n, "date": rec.get("date", ""), "score": score, "score_from_boss": rec.get("score") is None and score is not None,
                        **{k: rec.get(k) for k in FIELDS[1:]},
                        "ok": ok_all, "total": total_q, "acc": ok_all / total_q,
                        "minutes": sum(mins) if mins else None, "modules": mods,
                        "imported": str(n) in g.state.get("mock_practice", [])})
    scored = [s for s in seasons if s["score"] is not None]
    mean = lambda xs: round(sum(xs) / len(xs), 1) if xs else None
    overall = {
        "count": len(seasons), "scored": len(scored),
        "mean": mean([s["score"] for s in scored]),
        "best": max((s["score"] for s in scored), default=None),
        "latest": scored[-1]["score"] if scored else None,
        "mean_avg": mean([s["avg"] for s in seasons if s.get("avg") is not None]),
        "mean_beat": mean([s["beat"] for s in seasons if s.get("beat") is not None]),
        "latest_rank": next(({"rank": s["rank"], "people": s["people"], "season": s["season"]} for s in reversed(seasons) if s.get("rank")), None),
        "mean_acc": mean([s["acc"] * 100 for s in seasons]),
    }
    modules = []
    for m in MODULE_NAMES:
        xs = [x for s in seasons for x in s["modules"] if x["name"] == m]
        if not xs:
            continue
        mins = [x["minutes"] for x in xs if x["minutes"] is not None]
        modules.append({"name": m, "acc": sum(x["ok"] for x in xs) / sum(x["total"] for x in xs),
                        "score": mean([x["score"] for x in xs]), "minutes": mean(mins), "seasons": len(xs)})
    return {"seasons": seasons, "overall": overall, "modules": modules, "module_names": MODULE_NAMES}


def save(g, body):
    """录入 / 修改一季的成绩单。分数第一次录入时也记进宗门大比（修为、悟道、突破丹照旧）"""
    n = _num(body.get("season"), 1, 999, integer=True)
    if not n:
        raise MockError("先选是第几季")
    data = g.state.setdefault("mocks", {})
    rec = data.setdefault(str(n), {})
    had_score = rec.get("score") is not None or _boss_score(g, n) is not None
    rec["score"] = _num(body.get("score"), 0, 100)
    rec["avg"] = _num(body.get("avg"), 0, 100)
    rec["top"] = _num(body.get("top"), 0, 100)
    rec["beat"] = _num(body.get("beat"), 0, 100)
    rec["rank"] = _num(body.get("rank"), 1, None, integer=True)
    rec["people"] = _num(body.get("people"), 1, None, integer=True)
    if rec["rank"] and rec["people"] and rec["rank"] > rec["people"]:
        raise MockError("排名不能大于总人数")
    rec["date"] = str(body.get("date") or rec.get("date") or g.t)[:10]
    rec["minutes"] = {m: v for m in MODULE_NAMES
                      if (v := _num((body.get("minutes") or {}).get(m), 0, 300)) is not None}
    rec["scores"] = {m: v for m in MODULE_NAMES
                     if (v := _num((body.get("scores") or {}).get(m), 0, 100)) is not None}
    ev = []
    if rec["score"] is not None and not had_score:
        ev = g.add_boss("第%d季" % n, rec["score"])
    return ev


def on_import(g, season):
    """导入了一份模考试卷：演武 · 历练记记 120 分钟（每季一次），题数、对的题数按那一季的复盘算"""
    done = g.state.setdefault("mock_practice", [])
    if not season or str(season) in done:
        return []
    d = next((d for n, d in vault.seasons(g.paths) if n == season), None)
    counts = season_counts(g.paths, d) if d else {}
    total = sum(c["total"] for c in counts.values())
    ok = sum(c["ok"] for c in counts.values())
    done.append(str(season))
    return g.add_practice("模考", total, ok, IMPORT_MINUTES, "粉笔第%d季模考" % season, "导入模考试卷，自动记入 %d 分钟" % IMPORT_MINUTES)
