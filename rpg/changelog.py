"""版本更新记录：读 rpg/data/changelog.md（“## 版本 · 日期”一节，下面“- ”一条），给设置页显示。"""
import re
from pathlib import Path

FILE = Path(__file__).parent / "data" / "changelog.md"


def entries(path=FILE):
    out = []
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return out
    for ln in text.splitlines():
        m = re.match(r"^##\s+v?([\d.]+)\s*(?:[·•\-—]\s*(\S.*))?$", ln.strip())
        if m:
            out.append({"version": m.group(1), "date": (m.group(2) or "").strip(), "items": []})
        elif out and re.match(r"^\s*[-*]\s+", ln):
            out[-1]["items"].append(re.sub(r"^\s*[-*]\s+", "", ln).strip())
    return out
