#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
行测 RPG · 启动入口。

    python server.py              # 启动并自动打开浏览器（Mac 用 python3）
    python server.py --port 9000  # 换端口
    python server.py --no-browser # 不自动打开浏览器

只用 Python 标准库，不需要 pip install 任何东西。关掉这个终端窗口 = 关掉程序。
"""
import argparse
import mimetypes
import socket
import sys
import threading
import webbrowser

sys.dont_write_bytecode = True  # 不生成 __pycache__（程序可能放在坚果云同步的库里）

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # Windows 终端中文不乱码
    except Exception:
        pass

# Windows 注册表可能把 .js 标成 text/plain，浏览器会拒绝执行，这里强制指定
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")

from http.server import ThreadingHTTPServer  # noqa: E402

from rpg.api import Handler  # noqa: E402
from rpg.paths import Paths, find_vault  # noqa: E402


def free_port(start):
    for p in range(start, start + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    return start


def main():
    ap = argparse.ArgumentParser(description="行测 RPG 训练网页")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()

    vault = find_vault()
    if vault:
        up = Paths(vault).ensure_train_dir()
        print(f"行测库：{vault}")
        for name in up:
            print(f"配置文件已升级到新版本：训练/{name}（旧文件备份为 训练/{name[:-3]}.旧版.md）")
        print(f"训练数据：{vault / '训练'}")
        try:   # 一次性：修掉旧版转换时串进逻辑填空等题干的材料（只动对得上指纹的题干）
            from rpg import api, zhenti
            r = zhenti.fix_material_leak(Paths(vault))
            if not r.get("done_before"):
                with api.open_game() as g:
                    n = zhenti.fix_material_state(g.state)
                if r["fixed"] or n:
                    print(f"已修复题干里串进的材料：题库 {r['fixed']} 题，作答记录 {n} 条")
        except Exception as e:      # 修不了不影响启动
            print(f"（修复材料串题时出错，已跳过：{e}）")
    else:
        print("还没找到行测库：打开网页后在“设置”里填写库的路径（含 copilot/skills 的那个文件夹）")

    port = free_port(a.port)
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"\n行测 RPG 已启动：{url}\n关掉这个窗口就会退出。")
    if not a.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
