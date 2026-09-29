#!/bin/bash
# 行测 RPG 启动（Mac）。双击运行；关掉终端窗口就退出。
cd "$(dirname "$0")" || exit 1
python3 server.py
