"""🌿 灵脉图：每个板块的思维导图（编辑器用 simple-mind-map，github.com/wanglin2/mind-map，MIT，放在 web/vendor/mindmap/）。

- 存在库里 训练/灵脉图/<板块>/<名字>.json（simple-mind-map 的完整数据：root 节点树 + layout / theme / view），坚果云同步；
  一个板块可以有好几幅，第一次打开自动建一幅“<板块>”。
- 导入：.xmind / Markdown / .json（.smm）在网页上转成节点树再存；导出：xmind / png / Markdown / json 存到 训练/灵脉图/导出/。
"""
import base64
import datetime as dt
import json
import re
from pathlib import Path

BOARDS = ["政治理论", "常识判断", "逻辑填空", "片段阅读", "数量关系", "图形推理", "定义判断",
          "类比推理", "论证逻辑", "形式逻辑", "一拖五", "资料分析"]
EXPORT_EXT = {"xmind", "png", "md", "json", "svg", "pdf"}


class MapError(Exception):
    pass


def folder(paths):
    return paths.train / "灵脉图"


def _safe(name, what="名字"):
    name = re.sub(r'[\\/:*?"<>|#^\[\]\n\r\t]+', " ", str(name or "")).strip()[:40]
    if not name or name.startswith("."):
        raise MapError("%s不能是空的" % what)
    return name


def _file(paths, board, name):
    return folder(paths) / _safe(board, "板块") / (_safe(name) + ".json")


def _count(node):
    return 1 + sum(_count(c) for c in (node or {}).get("children") or [])


def blank(title):
    return {"root": {"data": {"text": title}, "children": []}, "layout": "logicalStructure"}


def listing(paths):
    """[{board, maps: [{name, nodes, updated}]}]：默认 12 个板块在前，自己建的其它板块（文件夹）在后"""
    d = folder(paths)
    boards = list(BOARDS)
    if d.is_dir():
        boards += sorted(p.name for p in d.iterdir() if p.is_dir() and p.name not in BOARDS and p.name != "导出")
    out = []
    for b in boards:
        maps = []
        for f in sorted((d / b).glob("*.json")) if (d / b).is_dir() else []:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                n = _count(data.get("root"))
            except (OSError, ValueError):
                n = 0
            maps.append({"name": f.stem, "nodes": n, "updated": dt.datetime.fromtimestamp(f.stat().st_mtime).strftime("%m-%d %H:%M")})
        out.append({"board": b, "maps": maps})
    return {"boards": out}


def get(paths, board, name):
    f = _file(paths, board, name)
    if not f.is_file():
        if name == board:                 # 第一次打开这个板块：建一幅空的
            return save(paths, board, name, blank(board))
        raise MapError("这幅灵脉图不见了（可能在另一台电脑上删了）")
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except ValueError:
        raise MapError("这幅灵脉图的文件坏了：%s" % f.name)
    return {"board": board, "name": f.stem, "data": data}


def save(paths, board, name, data):
    if not isinstance(data, dict) or not isinstance(data.get("root"), dict):
        raise MapError("数据不对：没有根节点")
    f = _file(paths, board, name)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(f)
    return {"board": board, "name": f.stem, "data": data, "nodes": _count(data["root"])}


def create(paths, board, name, data=None):
    f = _file(paths, board, name)
    base, k = f.stem, 2
    while f.exists():                       # 重名就加个“（2）”
        f = f.with_name("%s（%d）.json" % (base, k))
        k += 1
    return save(paths, board, f.stem, data or blank(f.stem))


def rename(paths, board, name, new):
    f, g = _file(paths, board, name), _file(paths, board, new)
    if not f.is_file():
        raise MapError("这幅灵脉图不见了")
    if g.exists() and g != f:
        raise MapError("已经有一幅叫「%s」的了" % g.stem)
    f.replace(g)
    return {"board": board, "name": g.stem}


def delete(paths, board, name):
    f = _file(paths, board, name)
    if f.is_file():
        f.unlink()
    return {"ok": True}


def export(paths, board, name, ext, data_url):
    """网页导出的结果（dataURL）存到 训练/灵脉图/导出/<名字>.<扩展名>"""
    ext = str(ext or "").lower()
    if ext not in EXPORT_EXT:
        raise MapError("不支持导出成 %s" % ext)
    m = re.match(r"^data:[^;,]*(?:;[^,]*)?;base64,(.+)$", str(data_url or ""), re.S)
    if m:
        raw = base64.b64decode(m.group(1))
    elif str(data_url or "").startswith("data:"):
        from urllib.parse import unquote
        raw = unquote(str(data_url).split(",", 1)[1]).encode("utf-8")
    else:
        raise MapError("导出的数据不对")
    d = export_dir(paths)
    d.mkdir(parents=True, exist_ok=True)
    f = d / ("%s.%s" % (_safe(name), ext))
    f.write_bytes(raw)
    return {"path": f.relative_to(paths.vault).as_posix(), "name": f.name, "size": f.stat().st_size}


def export_dir(paths):
    return folder(paths) / "导出"
