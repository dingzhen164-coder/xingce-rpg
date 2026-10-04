"""平板 App 的更新：电脑替平板去 GitHub 下最新的 APK（电脑能上 GitHub，平板不一定能），再从局域网传给平板。

- GET /api/app/latest      平板 App 问：最新版本是多少、装包准备好没有（电脑去 GitHub 看一眼，顺手把 APK 下到本机）
- GET /app/xingce-xiuxian.apk   平板来拿安装包（不用口令：安装包本来就是公开的）
- 另外开一个“只给安装包”的端口（主端口 +1 起找空的）：旧版 App 里点同一台电脑、不同端口的链接会交给系统浏览器下载，
  这样还没有“一键更新”功能的旧 App 也能点一下就下载安装
安装包存在 ~/.xingce-rpg/apk/xingce-xiuxian-<版本>.apk，只留最新一个。
"""
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import paths, update

NAME = "xingce-xiuxian.apk"
_LOCK = threading.Lock()


class ApkError(Exception):
    pass


def folder():
    return Path(paths.SETTINGS_DIR) / "apk"


def cached():
    """本机已经下好的最新安装包 (版本, 路径)；没有返回 (None, None)"""
    fs = sorted(folder().glob("xingce-xiuxian-*.apk"), key=lambda f: update._ver(f.stem.split("-")[-1]))
    return (fs[-1].stem.split("-")[-1], fs[-1]) if fs else (None, None)


def latest():
    """问 GitHub 最新版本，把 APK 下到本机。返回 {"latest", "ready", "error"}；连不上 GitHub 就用本机已有的"""
    try:
        info = update.check()
    except update.UpdateError as e:
        ver, f = cached()
        return {"latest": ver or "", "ready": bool(f), "error": str(e)}
    if not info.get("apk_url"):
        ver, f = cached()
        return {"latest": ver or info.get("latest", ""), "ready": bool(f), "error": "" if f else "这一版还没有平板 App 安装包"}
    try:
        ensure(info["latest"], info["apk_url"], info.get("apk_size") or 0)
    except ApkError as e:
        return {"latest": info["latest"], "ready": False, "error": str(e)}
    return {"latest": info["latest"], "ready": True, "error": ""}


def ensure(ver, url, size=0):
    """把这一版的 APK 下到本机（已经有就不下），删掉旧的。返回路径"""
    with _LOCK:
        d = folder()
        d.mkdir(parents=True, exist_ok=True)
        f = d / ("xingce-xiuxian-%s.apk" % ver)
        if f.is_file() and (not size or f.stat().st_size == size):
            return f
        tmp = f.with_suffix(".part")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "xingce-rpg"})
            with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as out:
                while True:
                    chunk = r.read(1 << 16)
                    if not chunk:
                        break
                    out.write(chunk)
        except Exception as e:
            tmp.unlink(missing_ok=True)
            raise ApkError("电脑下载平板 App 安装包失败（%s）：电脑能打开 GitHub 吗？" % e)
        if size and tmp.stat().st_size != size:
            tmp.unlink(missing_ok=True)
            raise ApkError("安装包下载不完整，再试一次")
        tmp.replace(f)
        for old in d.glob("xingce-xiuxian-*.apk"):
            if old != f:
                old.unlink(missing_ok=True)
        return f


def apk_bytes():
    """给平板的安装包：本机有就直接给；没有先去 GitHub 下"""
    ver, f = cached()
    if not f:
        info = latest()
        ver, f = cached()
        if not f:
            raise ApkError(info.get("error") or "还没有平板 App 安装包")
    return f.read_bytes()


class _ApkOnly(BaseHTTPRequestHandler):
    """另开端口上只给安装包"""
    def do_GET(self):
        if self.path.split("?")[0] != "/" + NAME:
            self.send_error(404)
            return
        try:
            data = apk_bytes()
        except ApkError as e:
            body = ("<meta charset=utf-8><p style='font-size:20px'>%s</p>" % e).encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.android.package-archive")
        self.send_header("Content-Disposition", 'attachment; filename="%s"' % NAME)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


def serve_apk_port(host, start_port):
    """开“只给安装包”的端口（从 start_port 往后找空的）。返回端口号，开不了返回 0"""
    for port in range(start_port, start_port + 20):
        try:
            srv = ThreadingHTTPServer((host, port), _ApkOnly)
        except OSError:
            continue
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return port
    return 0
