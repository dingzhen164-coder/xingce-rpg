"""打包后的 exe / Mac App 自检（CI 用）：xingce-xiuxian.exe --run-script tests/smoke_frozen.py
确认 exe 里带齐了 pymupdf、segno、网页文件和程序模块。"""
import sys

import pymupdf  # noqa: F401
import segno  # noqa: F401
import webview  # noqa: F401

from rpg import api, lan, update, zhenti  # noqa: F401
from rpg.paths import DEFAULTS_DIR, FROZEN, WEB_DIR

assert FROZEN, "not frozen"
assert (WEB_DIR / "index.html").exists(), WEB_DIR
assert (WEB_DIR / "device.js").exists()
assert DEFAULTS_DIR.exists(), DEFAULTS_DIR
assert zhenti.FIX_FILE.exists(), zhenti.FIX_FILE
assert "<svg" in lan.qr_svg("http://192.168.1.2:8765/")
if sys.platform == "darwin":                   # Mac：苹果 Vision 能认出成绩截图里的中文和数字
    from rpg import report
    doc = pymupdf.open()
    page = doc.new_page(width=640, height=220)
    page.insert_text((30, 90), "得分 64.5  共30题答对25题", fontname="china-s", fontsize=30)
    out = report.ocr(page.get_pixmap(dpi=144).tobytes("png"))
    print(out)
    assert "64.5" in out and "得分" in out, out
print("SMOKE-OK", sys.version.split()[0])
