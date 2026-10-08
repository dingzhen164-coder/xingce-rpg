"""🖼 修炼战报：把今天 / 近七天的修炼成果画成一张竖版海报（网页 web/poster.js 用 canvas 画），可以存图、分享。

- stats(g, span)：海报要用的数字。span = "day"（今天）或 "week"（含今天的近 7 天）。
  功行分钟（听课 / 做题 / 复习三才）、每天的分钟、达标天数、做题数和正确率（试炼塔 + 演武自练）、
  温简次数和记住率（玉简的复习记录）、得到的修为、用功最多的板块、境界 / 道行 / 连续打卡。
- save(paths, data_url, span, day)：网页画好的 PNG 存到 训练/战报/<日期>-今日|近七日.png（同名覆盖），
  电脑上用默认看图程序打开，平板上走 /notes-file 下载（notes.export_file 认这个文件夹）。
"""
import base64
import datetime as dt
import re


DIR = "战报"
SPANS = {"day": "今日", "week": "近七日"}


class PosterError(Exception):
    pass


def export_dir(paths):
    return paths.train / DIR


def _days(g, span):
    n = 7 if span == "week" else 1
    return [(g.today - dt.timedelta(days=k)).isoformat() for k in range(n - 1, -1, -1)]


def stats(g, span="day"):
    from . import question_bank
    if span not in SPANS:
        raise PosterError("范围只能是今日或近七日")
    days = _days(g, span)
    keep = set(days)
    goal = int(g.rules.num("每日目标分钟"))
    per_day = [int(g.minutes(d)) for d in days]
    split = g.time_split(keep)

    # 做题：试炼塔每次作答 + 演武自练记的题数
    q_total = q_ok = 0
    for rec in question_bank.state(g)["records"].values():
        for h in rec.get("history") or []:
            if h.get("date") in keep:
                q_total += 1
                q_ok += bool(h.get("ok"))
    for x in g.state.get("practice") or []:
        if x["d"] in keep and x.get("total"):
            q_total += int(x["total"])
            q_ok += int(x.get("correct") or 0)

    # 温简：玉简的复习记录。按日历日期算（和功行、做题一样），不用玉简自己“凌晨 4 点换日”的算法，免得半夜温的简对不上今天
    c_total = c_ok = 0
    for row in (g.state.get("cards") or {}).get("log") or []:
        try:
            ts, _, r, _, _ = row.split("|")
        except ValueError:
            continue
        if dt.date.fromtimestamp(float(ts)).isoformat() in keep:
            c_total += 1
            c_ok += int(r) > 1

    xp = sum(e.get("xp") or 0 for e in g.state["events"] if e.get("d") in keep)
    bt = g.board_time(keep)["boards"]
    top = sorted((b for b in bt if b["total"] > 0), key=lambda b: -b["total"])[:3]
    info = g.realm_info()
    run, _ = g.streak()
    return {
        "span": span, "label": SPANS[span], "days": days, "per_day": per_day,
        "minutes": sum(per_day), "goal": goal, "hit": sum(m >= goal for m in per_day),
        "split": {k: split[k] for k in ("lecture", "practice", "review")},
        "questions": {"total": q_total, "correct": q_ok, "acc": round(q_ok / q_total, 3) if q_total else None},
        "cards": {"total": c_total, "ok": c_ok, "rate": round(c_ok / c_total, 3) if c_total else None},
        "xp": int(round(xp)), "top": [{"board": b["board"], "minutes": b["total"]} for b in top],
        "realm": info["name"], "score": info["score"], "target": info["target"],
        "dao": g.dao_label(g.dao()), "streak": run,
    }


def save(paths, data_url, span="day", day=""):
    m = re.match(r"^data:image/png;base64,(.+)$", str(data_url or ""), re.S)
    if not m:
        raise PosterError("海报的图片数据不对")
    raw = base64.b64decode(m.group(1))
    if len(raw) > 20 * 1024 * 1024:
        raise PosterError("海报太大了")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(day or "")):
        day = dt.date.today().isoformat()
    d = export_dir(paths)
    d.mkdir(parents=True, exist_ok=True)
    f = d / ("%s-%s.png" % (day, SPANS.get(span, "今日")))
    tmp = f.with_suffix(".tmp")
    tmp.write_bytes(raw)
    tmp.replace(f)
    return {"path": f.relative_to(paths.vault).as_posix(), "name": f.name, "size": f.stat().st_size}
