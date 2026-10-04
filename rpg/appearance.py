"""
外观与音乐：背景、语录、BGM。

- 背景：用户放进 训练/外观/背景/ 的图片（程序不自带背景；以前选的自带背景换成第一张自己的图，没有就不用背景）。
- 语录：训练/语录.md，一行一句（“- ”开头），用户自己改；显示方式：每次随机 / 每日一句 / 固定一句 / 不显示。
- 语录大小：quote_size，字号倍数 0.5 ~ 2。
- BGM：默认关闭，顶栏 ♪ 按钮打开，顺序循环或随机播放（shuffle）训练/外观/音乐/ 里的音频（程序不自带音乐）。
选择存在存档 state["appearance"] 里（两台电脑同步）；图片、音乐、语录都在库里，坚果云同步。
"""
import datetime as dt
import re

from .vault import IMAGE_EXT

AUDIO_EXT = {".mp3", ".ogg", ".m4a", ".aac", ".wav", ".flac", ".opus"}
BG_DIR = ("外观", "背景")
MUSIC_DIR = ("外观", "音乐")
DEFAULTS = {"bg": "", "dim": 0.35, "quote": "daily", "fixed": "", "track": "", "volume": 0.35, "shuffle": False, "quote_size": 1.0}
QUOTE_MODES = ("random", "daily", "fixed", "off")


def folder(paths, parts):
    d = paths.train
    for x in parts:
        d = d / x
    return d


def _files(paths, parts, exts):
    d = folder(paths, parts)
    if not d.is_dir():
        return []
    return [p.relative_to(paths.vault).as_posix() for p in sorted(d.iterdir())
            if p.is_file() and p.suffix.lower() in exts and not p.name.startswith(".")]


def quotes(paths):
    f = paths.train / "语录.md" if paths.train else None
    if not f or not f.is_file():
        return []
    out = []
    for ln in f.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
        m = re.match(r"^\s*[-*]\s+(.+?)\s*$", ln)
        if m and m.group(1):
            out.append(m.group(1))
    return out


def current(state):
    a = dict(DEFAULTS)
    a.update({k: v for k, v in (state.get("appearance") or {}).items() if k in DEFAULTS})
    return a


def view(paths, state, today=None):
    qs = quotes(paths)
    today = today or dt.date.today()
    cur, music = current(state), _files(paths, MUSIC_DIR, AUDIO_EXT)
    if cur["track"] not in music:          # 没选过 / 选的那首删了：从第一首开始
        cur["track"] = music[0] if music else ""
    bgs = _files(paths, BG_DIR, IMAGE_EXT)
    if cur["bg"] != "none" and not (cur["bg"].startswith("file:") and cur["bg"][5:] in bgs):
        cur["bg"] = "file:" + bgs[0] if bgs else "none"    # 没选过 / 以前选的自带背景 / 图片删了：第一张自己的图
    return {"current": cur, "backgrounds": bgs,
            "music": music, "quotes": qs,
            "daily": qs[today.toordinal() % len(qs)] if qs else "",
            "folders": {"bg": "训练/外观/背景/", "music": "训练/外观/音乐/", "quotes": "训练/语录.md"}}


def update(paths, state, body):
    """只接受已知的字段和合法的值；图片 / 音乐必须是库里外观文件夹里实际存在的文件"""
    a = current(state)
    bg = body.get("bg")
    if bg is not None:
        if bg == "none" or (str(bg).startswith("file:") and str(bg)[5:] in _files(paths, BG_DIR, IMAGE_EXT)):
            a["bg"] = bg
    if body.get("dim") is not None:
        a["dim"] = max(0.0, min(0.9, float(body["dim"])))
    if body.get("quote") in QUOTE_MODES:
        a["quote"] = body["quote"]
    if body.get("fixed") is not None:
        a["fixed"] = str(body["fixed"])[:60]
    tr = body.get("track")
    if tr is not None and tr in _files(paths, MUSIC_DIR, AUDIO_EXT):
        a["track"] = tr
    if body.get("shuffle") is not None:
        a["shuffle"] = bool(body["shuffle"])
    if body.get("quote_size") is not None:
        a["quote_size"] = round(max(0.5, min(2.0, float(body["quote_size"]))), 2)
    if body.get("volume") is not None:
        a["volume"] = max(0.0, min(1.0, float(body["volume"])))
    state["appearance"] = a
    return a
