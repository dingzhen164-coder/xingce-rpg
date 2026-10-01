"""
外观与音乐：背景、语录、BGM。

- 背景：程序自带几张（网页用代码画，见 web/app.js 的 BUILTIN_BG），或用户放进 训练/外观/背景/ 的图片。
- 语录：训练/语录.md，一行一句（“- ”开头），用户自己改；显示方式：每次随机 / 每日一句 / 固定一句 / 不显示。
- BGM：默认关闭，顶栏 ♪ 按钮打开。训练/外观/音乐/ 里有音频就按顺序循环播放，没有就用网页现场合成的古琴风氛围音。
选择存在存档 state["appearance"] 里（两台电脑同步）；图片、音乐、语录都在库里，坚果云同步。
"""
import datetime as dt
import re

from .vault import IMAGE_EXT

AUDIO_EXT = {".mp3", ".ogg", ".m4a", ".aac", ".wav", ".flac", ".opus"}
BG_DIR = ("外观", "背景")
MUSIC_DIR = ("外观", "音乐")
DEFAULTS = {"bg": "builtin:水墨远山", "dim": 0.35, "quote": "daily", "fixed": "", "track": "builtin", "volume": 0.35}
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
    return {"current": current(state), "backgrounds": _files(paths, BG_DIR, IMAGE_EXT),
            "music": _files(paths, MUSIC_DIR, AUDIO_EXT), "quotes": qs,
            "daily": qs[today.toordinal() % len(qs)] if qs else "",
            "folders": {"bg": "训练/外观/背景/", "music": "训练/外观/音乐/", "quotes": "训练/语录.md"}}


def update(paths, state, body):
    """只接受已知的字段和合法的值；图片 / 音乐必须是库里外观文件夹里实际存在的文件"""
    a = current(state)
    bg = body.get("bg")
    if bg is not None:
        if bg == "none" or re.fullmatch(r"builtin:[\w一-鿿]{1,12}", str(bg)) \
                or (str(bg).startswith("file:") and str(bg)[5:] in _files(paths, BG_DIR, IMAGE_EXT)):
            a["bg"] = bg
    if body.get("dim") is not None:
        a["dim"] = max(0.0, min(0.9, float(body["dim"])))
    if body.get("quote") in QUOTE_MODES:
        a["quote"] = body["quote"]
    if body.get("fixed") is not None:
        a["fixed"] = str(body["fixed"])[:60]
    tr = body.get("track")
    if tr is not None and (tr == "builtin" or tr in _files(paths, MUSIC_DIR, AUDIO_EXT)):
        a["track"] = tr
    if body.get("volume") is not None:
        a["volume"] = max(0.0, min(1.0, float(body["volume"])))
    state["appearance"] = a
    return a
