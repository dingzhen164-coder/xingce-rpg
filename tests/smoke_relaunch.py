"""CI 用：在打包好的 exe 里跑（exe --run-script tests/smoke_relaunch.py 新exe 目标exe），
走一遍“一键更新”的后半段：交给换文件脚本 → 自己退出（临时目录 _MEIxxxx 随之删掉）→ 脚本换文件并重开。
重开的新程序能起来（启动日志里有“已启动”）才算过。"""
import os
import sys

from rpg import update

new, exe = sys.argv[1], sys.argv[2]
update.launch_swap(os.getpid(), new, exe)
print("SWAP-LAUNCHED")
