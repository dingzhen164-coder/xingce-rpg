#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
行测修仙传 · 桌面版入口（打包成 exe 用的就是这个文件）。

    双击 行测修仙传.exe        → 在自己的窗口里打开（不开浏览器）；关掉窗口 = 退出程序
    python app.py              → 源码版也能这样开（需要 pip install pywebview；没装就用浏览器打开）

窗口是 pywebview（Windows 上用系统自带的 Edge WebView2）。打不开窗口时自动改用浏览器。
exe 还兼一个小用途：拆模考 PDF 时，程序用 `行测修仙传.exe --run-script 脚本.py 参数` 去跑拆分脚本（exe 里带着 pymupdf）。
"""
import os
import runpy
import sys
import threading
import traceback
import webbrowser
from pathlib import Path

sys.dont_write_bytecode = True


def run_script():
    """exe --run-script <脚本> [参数…]：像 python <脚本> 一样运行（拆分模考 PDF 用）"""
    i = sys.argv.index("--run-script")
    script = sys.argv[i + 1]
    sys.argv = [script] + sys.argv[i + 2:]
    # 窗口版 exe 没有 sys.stdout：接到父进程给的管道上（程序要读拆分脚本的输出），接不上就丢掉
    for name, fd in (("stdout", 1), ("stderr", 2)):
        if getattr(sys, name) is None:
            try:
                setattr(sys, name, open(fd, "w", encoding="utf-8", errors="replace", closefd=False))
            except OSError:
                setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    runpy.run_path(script, run_name="__main__")


def log_file():
    """窗口版没有终端：启动信息、报错写进 ~/.xingce-rpg/启动日志.txt，出问题时看这个"""
    d = Path.home() / ".xingce-rpg"
    d.mkdir(parents=True, exist_ok=True)
    return open(d / "启动日志.txt", "w", encoding="utf-8", buffering=1)


def main():
    if "--run-script" in sys.argv:
        return run_script()
    if getattr(sys, "frozen", False) and (sys.stdout is None or sys.stderr is None):
        sys.stdout = sys.stderr = log_file()        # --windowed 打包时没有控制台
    import server
    server.prepare()
    srv, url = server.start_server()
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    from rpg.version import VERSION
    print(f"行测修仙传 {VERSION} 已启动：{url}")
    try:
        import webview
    except Exception:
        webview = None
    if webview is None or "--browser" in sys.argv:
        webbrowser.open(url)
        print("（没有窗口组件，已用浏览器打开；关掉这个程序才会退出）")
        threading.Event().wait()
        return
    try:
        data = Path.home() / ".xingce-rpg" / "webview"     # 窗口里的本机设置（对话框大小、音乐……）存这里，重开还在
        data.mkdir(parents=True, exist_ok=True)
        webview.create_window("行测修仙传", url, width=1440, height=920, min_size=(900, 600), text_select=True)
        webview.start(private_mode=False, storage_path=str(data))
    except Exception:
        traceback.print_exc()
        webbrowser.open(url)        # 窗口开不了（比如缺 WebView2）：退回浏览器
        threading.Event().wait()
    os._exit(0)                     # 关掉窗口 = 退出（后台服务一起停）


if __name__ == "__main__":
    main()
