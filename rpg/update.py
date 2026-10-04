"""检查更新 / 一键更新（exe 版）。

- 每次改 rpg/version.py 的版本号推到 main，GitHub Actions 在 Windows 上打包出新的 exe，发到仓库的 Releases；
- 程序里点「检查更新」：问 GitHub 最新的 Release 是哪个版本，比当前新就给出下载；
- exe 版点「更新并重启」：把新 exe 下到旁边，写个小批处理——等这个程序退出、用新 exe 换掉旧的、再启动——然后自己退出；
- 源码版（python server.py）不自动替换，照旧用压缩包更新。
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

from .paths import FROZEN
from .version import REPO, VERSION

API = "https://api.github.com/repos/%s/releases/latest" % REPO


class UpdateError(Exception):
    pass


def _ver(s):
    return tuple(int(x) for x in re.findall(r"\d+", str(s or ""))[:4]) or (0,)


def check():
    req = urllib.request.Request(API, headers={"User-Agent": "xingce-rpg", "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            rel = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:       # 还没发布过 Release
            return {"current": VERSION, "latest": "", "newer": False, "frozen": FROZEN, "notes": "", "asset_url": "", "size": 0,
                    "page": "https://github.com/%s/releases" % REPO, "windows": os.name == "nt"}
        raise UpdateError("GitHub 回应 %s。也可以直接打开 https://github.com/%s/releases 下载" % (e.code, REPO))
    except Exception as e:
        raise UpdateError("连不上 GitHub（%s）。也可以直接打开 https://github.com/%s/releases 下载" % (e, REPO))
    tag = rel.get("tag_name") or ""
    asset = next((a for a in rel.get("assets", []) if a.get("name", "").lower().endswith(".exe")), None)
    return {"current": VERSION, "latest": tag.lstrip("v"), "newer": _ver(tag) > _ver(VERSION), "frozen": FROZEN,
            "notes": (rel.get("body") or "")[:2000], "page": rel.get("html_url") or "https://github.com/%s/releases" % REPO,
            "asset_url": asset.get("browser_download_url") if asset else "", "size": asset.get("size") if asset else 0,
            "windows": os.name == "nt"}


def apply():
    """下载新 exe，交给批处理换掉自己并重启。只在 Windows 上的 exe 版能用"""
    if not (FROZEN and os.name == "nt"):
        raise UpdateError("自动更新只在 Windows 的 exe 版能用；源码版请照旧下载压缩包更新")
    info = check()
    if not info["newer"]:
        raise UpdateError("已经是最新版（%s）" % VERSION)
    if not info["asset_url"]:
        raise UpdateError("新版本还在打包，过几分钟再试")
    exe = Path(sys.executable).resolve()
    new = exe.with_name(exe.stem + ".new.exe")
    req = urllib.request.Request(info["asset_url"], headers={"User-Agent": "xingce-rpg"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r, open(new, "wb") as f:
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
    except Exception as e:
        try:
            new.unlink()
        except OSError:
            pass
        raise UpdateError("下载新版本失败（%s）。可以打开 %s 手动下载，换掉旧的 exe" % (e, info["page"]))
    if info["size"] and new.stat().st_size != info["size"]:
        new.unlink()
        raise UpdateError("下载不完整，再试一次")
    bat = Path(tempfile.gettempdir()) / "xingce-rpg-update.bat"
    bat.write_text("\r\n".join([
        "@echo off", "chcp 65001 >nul",
        ":wait",
        'tasklist /FI "PID eq %d" | find "%d" >nul && (timeout /t 1 /nobreak >nul & goto wait)' % (os.getpid(), os.getpid()),
        'move /y "%s" "%s" >nul' % (new, exe),
        'start "" "%s"' % exe,
        'del "%~f0"', ""]), encoding="utf-8", newline="")
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(["cmd", "/c", str(bat)], creationflags=flags, close_fds=True)
    threading.Timer(1.5, lambda: os._exit(0)).start()      # 先把回应发给网页，再退出让批处理换文件
    return {"ok": True, "version": info["latest"]}
