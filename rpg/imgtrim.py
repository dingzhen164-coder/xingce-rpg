"""资料分析等材料截图：裁掉四周的空白，网页上铺满材料框时字更大、更清楚（/vault-file?p=…&trim=1）。
用 pymupdf 读写图片（exe / Mac App 里带着；源码版没装就原图照给）。裁过的放在内存里，图片改了自动重裁。"""
from pathlib import Path

_CACHE = {}
LIGHT = 236          # 比这个亮的算空白（纸色、浅灰的底纹）
PAD = 8              # 裁完四周留一点边


def _pm():
    try:
        import pymupdf
        return pymupdf
    except ImportError:
        try:
            import fitz
            return fitz
        except ImportError:
            return None


def trim(path):
    """返回裁好的 PNG 字节；用不着裁（本来就没什么空白）、读不了，返回 None"""
    p = Path(path)
    try:
        key = (str(p), p.stat().st_mtime_ns)
    except OSError:
        return None
    if key in _CACHE:
        return _CACHE[key]
    out = None
    try:
        out = _trim(p)
    except Exception:
        out = None
    if len(_CACHE) > 200:
        _CACHE.clear()
    _CACHE[key] = out
    return out


def _trim(p):
    pm = _pm()
    if not pm:
        return None
    pix = pm.Pixmap(str(p))
    if pix.alpha:
        pix = pm.Pixmap(pix, 0)                       # 去掉透明通道
    if pix.colorspace and pix.colorspace.n not in (1, 3):
        pix = pm.Pixmap(pm.csRGB, pix)
    w, h, n, stride = pix.width, pix.height, pix.n, pix.stride
    if w < 40 or h < 40:
        return None
    data = pix.samples
    rows = [y for y in range(h) if min(data[y * stride: y * stride + w * n]) < LIGHT]
    if not rows:
        return None
    y0, y1 = rows[0], rows[-1] + 1
    band = data[y0 * stride: y1 * stride]
    cols = [x for x in range(w) if min(min(band[x * n + c::stride]) for c in range(n)) < LIGHT]
    if not cols:
        return None
    x0, x1 = cols[0], cols[-1] + 1
    x0, y0, x1, y1 = max(0, x0 - PAD), max(0, y0 - PAD), min(w, x1 + PAD), min(h, y1 + PAD)
    if (x1 - x0) * (y1 - y0) > 0.9 * w * h:          # 空白不多：不值得裁
        return None
    samples = b"".join(data[y * stride + x0 * n: y * stride + x1 * n] for y in range(y0, y1))
    out = pm.Pixmap(pix.colorspace, x1 - x0, y1 - y0, samples, False)
    return out.tobytes("png")
