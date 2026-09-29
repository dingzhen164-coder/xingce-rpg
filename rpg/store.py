"""
存档：训练/存档/存档.json 的读写。

- 所有训练结果都保存在这一个 JSON 里（结构见 DESIGN.md「存档结构」和下面的 new_state）；
- 写入是原子的（先写临时文件再替换），程序中途被关掉也不会写坏；
- 每天第一次写入时备份一份到 存档/备份/，保留最近 14 份；
- 两台电脑通过坚果云同步同一个存档：“正在使用.json” 记录哪台电脑在用，
  另一台电脑 10 分钟内有心跳就在网页上提醒“不要两台同时开”；
- 坚果云产生冲突副本（文件名带“冲突”/conflict）时也在网页上提醒。
"""
import datetime as dt
import json
import os
import platform
import threading
import time
from pathlib import Path

LOCK = threading.RLock()  # 所有读改写存档的操作都要先拿这把锁
SCHEMA_VERSION = 1
DEVICE = platform.node() or "本机"


def new_state(today):
    return {
        "version": SCHEMA_VERSION,
        "created": today.isoformat(),
        "xp": 0,                 # 累计经验（已含连续打卡加成）
        "events": [],            # 每次得经验的记录：{t, d, type, board, item, ok, xp, note}
        "items": {},             # 骨架大项的掌握状态，键 "板块::大项"（结构见 engine.item_state）
        "wrong": {},             # 错题状态，键 "季|复盘板块|题号"
        "seconds": {},           # 每天学习秒数 {日期: 秒}（网页心跳累加，只算页面可见且有操作的时间）
        "leave": [],             # 用过请假卡的日期
        "plan": None,            # 今日任务 {date, tasks: [...]}
        "lap": 1,                # 当前周目
        "cleared": {},           # {周目: [已通关批次序号(从1开始)]}
        "gates": [],             # 已通过的突破等级
        "boss": [],              # 模考 / 国考真实分 {d, name, score}
        "practice": [],          # 自练记录 {d, board, total, correct, minutes}
        "progress_hist": {},     # 每天的周目进度快照 {日期: 0~1}，算“近7天速度”用
        "last_seen": None,       # 上次打开网页的日期（判断“回归”）
    }


class Store:
    def __init__(self, paths):
        self.paths = paths

    # ------------------------------------------------------------ 读写
    def load(self, today):
        f = self.paths.save_file
        if not f or not f.exists():
            return new_state(today)
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            # 存档坏了：不覆盖它，改名留证，从最近的备份恢复
            bad = f.with_name(f"存档-损坏-{int(time.time())}.json")
            os.replace(f, bad)
            return self._latest_backup() or new_state(today)
        base = new_state(today)
        base.update(data)  # 老存档缺的新字段用默认值补上
        return base

    def save(self, state, today):
        f = self.paths.save_file
        if not f:
            return
        f.parent.mkdir(parents=True, exist_ok=True)
        self._daily_backup(today)
        tmp = f.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as fp:
            json.dump(state, fp, ensure_ascii=False, indent=1)
        os.replace(tmp, f)

    def _backup_dir(self):
        return self.paths.save_dir / "备份"

    def _daily_backup(self, today):
        f = self.paths.save_file
        if not f.exists():
            return
        d = self._backup_dir()
        d.mkdir(exist_ok=True)
        dst = d / f"存档-{today.strftime('%Y%m%d')}.json"
        if not dst.exists():
            dst.write_bytes(f.read_bytes())
            for old in sorted(d.glob("存档-*.json"))[:-14]:
                old.unlink()

    def _latest_backup(self):
        d = self._backup_dir()
        for b in sorted(d.glob("存档-*.json"), reverse=True) if d.exists() else []:
            try:
                return json.loads(b.read_text(encoding="utf-8"))
            except Exception:
                continue
        return None

    # ------------------------------------------------------------ 多设备提醒
    def heartbeat(self):
        """写入“本机正在使用”；返回另一台电脑的名字（它 10 分钟内有心跳），没有返回 None"""
        if not self.paths.save_dir:
            return None
        lf = self.paths.save_dir / "正在使用.json"
        other = None
        try:
            cur = json.loads(lf.read_text(encoding="utf-8"))
            if cur.get("device") != DEVICE and time.time() - cur.get("ts", 0) < 600:
                other = cur.get("device")
        except Exception:
            pass
        if not other:
            try:
                lf.write_text(json.dumps({"device": DEVICE, "ts": time.time()}, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass
        return other

    def conflicts(self):
        """坚果云冲突副本的文件名列表"""
        d = self.paths.save_dir
        if not d or not d.exists():
            return []
        return [p.name for p in d.iterdir()
                if p.is_file() and ("冲突" in p.name or "conflict" in p.name.lower())]
