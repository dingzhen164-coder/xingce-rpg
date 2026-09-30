"""
游戏规则核心（纯计算 + 修改存档字典，不做任何网络请求和文件读写以外的事）。

主要概念（详见 DESIGN.md）：
- 大项 item：骨架里的一个 “## 标题”。掌握度 level：0 未学 → 1 默写过(L1) → 2 讲清楚(L2) → 3 已掌握(L3)。
    L1：默写连续通过 N 次；L2：费曼讲解通过 1 次；L3：应用连续通过 N 次（错题判断命中该大项也算）。
    已掌握后按“复查间隔天数”复查；复查不过降回 0（生锈）。
- 经验 xp → 等级 level（Lv1～Lv满级等级，默认 100）。升级所需经验线性递增，
  总经验 = 每日理想经验 × (满级目标日 − 开始日期) 天，即“每天学满、一天不断”恰好在目标日满级。
  预估分按“已获经验 / 总经验”在 起始分数～满级分数 之间线性换算，和等级数无关。
- 晋升试炼（代码里叫 gate / 突破）：要到达“突破等级”（默认 30/60/90）必须先通过试炼，经验再多也停在前一级。
- 界面用西方玄幻的说法：骨架 = 咒文书，默写 = 咏唱，费曼 = 传授奥义，应用 = 实战演练，错题 = 魔物，
  复查 = 驱散遗忘，批 = 地下城的一层，周目 = 一轮征程。显示用的文字集中在下面的 LABEL / LEVEL_NAMES。
- 连续打卡：当天学习 ≥ 保底分钟（或用了请假卡）算打卡。加成 = 累计天数 × 每天加成（有上限）；
  断一天累计天数减半，不清零。
- 理想线：开始日期到昨天（不含请假日）× 每日理想经验；和实际经验的差 ÷ 每日理想经验 = 落后/领先天数。
- 分批与周目：规则里的“第N批”按顺序学，一批的所有大项都已掌握才进入下一批；全部批次通关 = 一个周目。
  新周目里已掌握的大项要先“速通”（默写一次）确认没忘。
- 每日任务 plan：突破试炼 → 骨架 → 复查/速通 → 错题（回炉优先，新错题按剩余天数分摊）→ 新学 → 追赶（可选）。

所有“结果”函数（on_recite / on_feynman / …）都返回事件列表，网页据此弹出 +经验、升级、导师台词：
    {"kind": "xp", "v": 30, "msg": "默写通过"} / {"kind": "level", "v": 12, "score": 61} /
    {"kind": "npc", "msg": "……"} / {"kind": "info", "msg": "……"}
"""
import datetime as dt
import math

from . import skeleton, vault

LEVEL_NAMES = ["未习得", "能咏唱", "能讲授", "已精通"]
# 任务类型 → 界面上的名字（西方玄幻风格）
LABEL = {"recite": "咏唱咒文", "feynman": "传授奥义", "apply": "实战演练", "review": "驱散遗忘",
         "speedrun": "重温咒文", "wrong": "讨伐魔物", "skeleton": "编纂咒文书", "trial": "晋升试炼"}


def D(s):
    return dt.date.fromisoformat(s) if isinstance(s, str) else s


class Game:
    def __init__(self, paths, rules, persona, lines, state, today=None):
        self.paths, self.rules, self.persona, self.lines, self.state = paths, rules, persona, lines, state
        self.today = today or dt.date.today()
        self.t = self.today.isoformat()
        self._skel = {}

    # ================================================================ 板块 / 骨架
    @property
    def boards(self):
        return self.rules.boards

    def skel(self, board):
        if board not in self._skel:
            self._skel[board] = skeleton.load(self.paths, board) if self.paths.vault else None
        return self._skel[board]

    def has_skill(self, board):
        return vault.skill_dir(self.paths, self.boards.get(board, {}).get("skill")) is not None

    def available(self, board):
        """板块可以参加训练：有 skill，或者已经有骨架文件"""
        return self.has_skill(board) or self.skel(board) is not None

    def final_items(self, board):
        s = self.skel(board)
        return s["items"] if s and s["final"] else []

    def find_item(self, iid):
        board = iid.split("::", 1)[0]
        for it in self.final_items(board):
            if it["id"] == iid:
                return it
        return None

    def item(self, iid):
        return self.state["items"].setdefault(iid, {
            "level": 0, "l1": 0, "l3": 0, "stage": -1, "next": None,
            "lap_check": False, "passed_once": False, "last": None, "rusty": False})

    def item_progress(self, iid):
        st = self.state["items"].get(iid)
        if not st:
            return 0.0
        if st["level"] >= 3 and st.get("lap_check"):
            return 2 / 3
        return st["level"] / 3

    def board_progress(self, board):
        items = self.final_items(board)
        if not items:
            return 0.0
        return sum(self.item_progress(i["id"]) for i in items) / len(items)

    def board_mastered(self, board):
        items = self.final_items(board)
        return bool(items) and all(
            self.item(i["id"])["level"] >= 3 and not self.item(i["id"])["lap_check"] for i in items)

    def lap_progress(self):
        bs = [b for batch in self.rules.batches for b in batch if self.available(b)]
        return sum(self.board_progress(b) for b in bs) / len(bs) if bs else 0.0

    # ================================================================ 等级
    def level_table(self):
        r = self.rules
        n = max(1, int(r.num("满级等级")) - 1)                     # 升级次数（Lv1 → Lv满级）
        days = max(30, (r.date("满级目标日") - r.date("开始日期")).days)
        total = r.num("每日理想经验") * days
        mult = max(1.0, float(r.num("后期升级倍数")))
        c1 = 2 * total / (n * (1 + mult))
        costs = [round(c1 * (1 + (mult - 1) * k / max(1, n - 1))) for k in range(n)]
        cum = [0]
        for c in costs:
            cum.append(cum[-1] + c)
        return costs, cum                                          # cum[L-1] = 到达 Lv L 的累计经验

    def level_info(self, xp=None):
        """等级、称号、预估分。
        晋升试炼：要到达“突破等级”g，必须先通过试炼，否则经验再多也停在 g-1（gate = g）。
        预估分和等级脱钩：起始分数 +（满级分数 − 起始分数）× 有效经验 / 满级总经验（被试炼卡住时有效经验封顶）。"""
        xp = self.state["xp"] if xp is None else xp
        costs, cum = self.level_table()
        max_lv = len(cum)
        lv = max(L for L in range(1, max_lv + 1) if cum[L - 1] <= xp)
        gate = None
        for g in sorted(int(x) for x in self.rules.nums("突破等级")):
            if g not in self.state["gates"] and lv >= g > 1:
                lv, gate = g - 1, g
                break
        if lv >= max_lv:
            need, into = 0, 0
        else:
            into = xp - cum[lv - 1]
            need = costs[lv - 1]
        eff = min(xp, cum[gate - 1]) if gate else xp
        lo, hi = self.rules.num("起始分数"), self.rules.num("满级分数")
        score = lo + (hi - lo) * min(1.0, eff / cum[-1])
        return {"level": lv, "max_level": max_lv, "score": round(score, 1),
                "into": int(into), "need": int(need), "frac": min(1.0, into / need) if need else 1.0,
                "gate": gate, "title": self.persona.title(lv, max_lv),
                "gate_title": self.persona.title(gate, max_lv) if gate else "",
                "total": int(cum[-1]), "max_score": hi}

    def pending_gate(self):
        """当前卡住的突破等级（经验已够但没过试炼），没有返回 None"""
        return self.level_info()["gate"]

    # ================================================================ 时间 / 打卡
    def minutes(self, day):
        return self.state["seconds"].get(day if isinstance(day, str) else day.isoformat(), 0) / 60

    def qualifies(self, day):
        ds = day.isoformat()
        return ds in self.state["leave"] or self.minutes(ds) >= self.rules.num("保底分钟")

    def streak(self):
        """返回 (连续打卡天数, 加成比例)"""
        start = D(self.state["created"])
        s = run = 0
        d = start
        while d < self.today:
            if self.qualifies(d):
                s += 1
                run += 1
            else:
                s //= 2
                run = 0
            d += dt.timedelta(days=1)
        if self.qualifies(self.today):
            s += 1
            run += 1
        bonus = min(self.rules.num("连续打卡加成上限"), s * self.rules.num("连续打卡每天加成"))
        return run, round(bonus, 3)

    def days_absent(self):
        """今天之前连续几天没打卡（从最近一次打卡算）；从没学过返回 0"""
        d = self.today - dt.timedelta(days=1)
        n = 0
        start = D(self.state["created"])
        while d >= start and not self.qualifies(d):
            n += 1
            d -= dt.timedelta(days=1)
        return n if d >= start else 0

    # ================================================================ 理想线 / 预测
    def ideal(self):
        r = self.rules
        daily = r.num("每日理想经验")
        start = r.date("开始日期")
        days = 0
        d = start
        while d < self.today:
            if d.isoformat() not in self.state["leave"]:
                days += 1
            d += dt.timedelta(days=1)
        ideal_xp = daily * days
        diff_days = (ideal_xp - self.state["xp"]) / daily             # >0 落后，<0 领先
        # 个人效率（近 14 天 经验/分钟），算追赶需要多学多久
        xp14 = sum(e["xp"] for e in self.state["events"]
                   if D(e["d"]) > self.today - dt.timedelta(days=14))
        min14 = sum(self.minutes(self.today - dt.timedelta(days=k)) for k in range(14))
        per_min = xp14 / min14 if min14 >= 30 and xp14 > 0 else daily / r.num("每日目标分钟")
        catch = None
        if diff_days > 0.5:
            extra_total = diff_days * daily / per_min                  # 追平需要多学的总分钟
            per_day = int(math.ceil(extra_total / 14 / 5.0) * 5)       # 两周内追平，每天多学（取 5 的倍数）
            catch = {"hours": round(extra_total / 60, 1), "per_day": per_day, "days": 14}
        # 预计满级：按近 14 天日均经验
        span = min(14, (self.today - D(self.state["created"])).days + 1)
        rate = xp14 / max(1, span)
        info = self.level_info()
        remain = max(0, info["total"] - self.state["xp"])
        active_days = len({e["d"] for e in self.state["events"]})
        eta = (self.today + dt.timedelta(days=math.ceil(remain / rate))).isoformat() \
            if rate > 0 and active_days >= 3 else None  # 学满 3 天才预测，免得第一天就吓人
        return {"ideal_xp": int(ideal_xp), "diff_days": round(diff_days, 1), "catch": catch,
                "eta": eta, "target": r.date("满级目标日").isoformat(), "daily_rate": round(rate)}

    def lap_forecast(self):
        """本周目进度与按近 7 天速度的剩余天数"""
        p = self.lap_progress()
        hist = self.state["progress_hist"]
        past = None
        for k in range(7, 0, -1):
            v = hist.get((self.today - dt.timedelta(days=k)).isoformat())
            if v is not None:
                past, span = v, k
                break
        days_left = None
        if past is not None and p > past:
            pace = (p - past) / span
            days_left = math.ceil((1 - p) / pace)
        return {"progress": p, "days_left": days_left}

    # ================================================================ 分批 / 周目
    def batch_boards(self, idx):
        return [b for b in self.rules.batches[idx] if self.available(b)]

    def cleared(self):
        return self.state["cleared"].setdefault(str(self.state["lap"]), [])

    def current_batch(self):
        """当前批次序号（从 0 开始）；本周目全部通关返回 None"""
        for i in range(len(self.rules.batches)):
            if (i + 1) in self.cleared() or not self.batch_boards(i):
                continue
            return i
        return None

    def housekeeping(self):
        """检查批次 / 周目通关，记录今日进度快照。每次读取面板和提交结果后调用。"""
        ev = []
        changed = True
        while changed:
            changed = False
            i = self.current_batch()
            if i is None:
                if any(self.batch_boards(k) for k in range(len(self.rules.batches))):
                    ev += self._lap_clear()
                    changed = False
                break
            key = f"{self.state['lap']}-{i + 1}"
            self.state.setdefault("batch_start", {}).setdefault(key, self.t)
            if all(self.board_mastered(b) for b in self.batch_boards(i)):
                self.cleared().append(i + 1)
                ev += self._award(self.rules.xp("批次通关"), "batch", note=f"第{i + 1}层地下城打通", bonus=False)
                ev.append(self._npc("批次通关"))
                changed = True
        self.state["progress_hist"][self.t] = round(self.lap_progress(), 4)
        return ev

    def _lap_clear(self):
        lap = self.state["lap"]
        ev = self._award(self.rules.xp("周目通关"), "lap", note=f"第{lap}轮征程通关", bonus=False)
        ev.append(self._npc("周目通关"))
        self.state["lap"] = lap + 1
        for st in self.state["items"].values():
            if st["level"] >= 3:
                st["lap_check"] = True
        return ev

    # ================================================================ 经验
    def _award(self, base, typ, board="", item="", ok=True, note="", bonus=True):
        before = self.level_info()
        mult = 1 + (self.streak()[1] if bonus else 0)
        gain = int(round(base * mult))
        self.state["xp"] += gain
        self.state["events"].append({"t": dt.datetime.now().isoformat(timespec="seconds"), "d": self.t,
                                     "type": typ, "board": board, "item": item, "ok": ok,
                                     "xp": gain, "note": note})
        ev = [{"kind": "xp", "v": gain, "msg": note}] if gain else []
        after = self.level_info()
        if after["level"] > before["level"]:
            ev.append({"kind": "level", "v": after["level"], "score": after["score"], "title": after["title"],
                       "promoted": after["title"] != before["title"]})
            ev.append(self._npc("升级"))
        if after["gate"] and not before["gate"]:
            ev.append(self._npc("突破待挑战"))
        return ev

    # ================================================================ 训练结果
    def on_recite(self, iid, ok, mode="recite"):
        """默写结果。mode: recite 学习 / review 复查 / speedrun 新周目速通"""
        st = self.item(iid)
        board = iid.split("::")[0]
        name = iid.split("::", 1)[1]
        st["last"] = self.t
        ev = []
        if mode in ("review", "speedrun"):
            if ok:
                if mode == "speedrun":
                    st["lap_check"] = False
                else:
                    iv = self.rules.nums("复查间隔天数")
                    st["stage"] = min(st["stage"] + 1, len(iv) - 1)
                    st["next"] = (self.today + dt.timedelta(days=int(iv[st["stage"]]))).isoformat()
                ev += self._award(self.rules.xp("复查通过"), mode, board, iid, True, f"{'重温' if mode == 'speedrun' else '驱散遗忘'}成功「{name}」")
            else:
                st.update(level=0, l1=0, l3=0, stage=-1, next=None, lap_check=False, rusty=True)
                ev += self._award(self.rules.xp("复查未过"), mode, board, iid, False, f"「{name}」被遗忘诅咒侵蚀，降回未习得")
            return ev
        if ok:
            base = self.rules.xp("默写通过")
            note = f"咏唱成功「{name}」"
            if not st["passed_once"]:
                st["passed_once"] = True
                base += self.rules.xp("首次通过加成")
                note += "（首次）"
            if st["level"] == 0:
                st["l1"] += 1
                if st["l1"] >= self.rules.num("默写连续通过次数"):
                    st["level"], st["rusty"] = 1, False
                    ev.append({"kind": "info", "msg": f"「{name}」已能咏唱，下一步：传授奥义（讲给学姐听）"})
            ev = self._award(base, "recite", board, iid, True, note) + ev
            ev.append(self._npc("默写通过"))
        else:
            if st["level"] == 0:
                st["l1"] = 0
            ev += self._award(self.rules.xp("默写未过"), "recite", board, iid, False, f"咏唱失败「{name}」")
            ev.append(self._npc("默写未过"))
        return ev

    def on_feynman(self, iid, ok):
        st = self.item(iid)
        board, name = iid.split("::", 1)
        st["last"] = self.t
        ev = self._award(self.rules.xp("费曼通过" if ok else "费曼未过"), "feynman", board, iid, ok,
                         f"费曼{'通过' if ok else '未过'}「{name}」")
        if ok and st["level"] == 1:  # 还没过 L1 的大项讲得再好也不升级：先默写
            st["level"] = 2
            ev.append({"kind": "info", "msg": f"「{name}」已能讲授，下一步：实战演练"})
        ev.append(self._npc("费曼通过" if ok else "费曼未过"))
        return ev

    def _l3_progress(self, iid, ok):
        st = self.item(iid)
        if st["level"] != 2:
            return []
        if not ok:
            st["l3"] = 0
            return []
        st["l3"] += 1
        if st["l3"] >= self.rules.num("应用连续通过次数"):
            return self._master(iid)
        return []

    def _master(self, iid):
        st = self.item(iid)
        iv = self.rules.nums("复查间隔天数")
        st.update(level=3, stage=0, next=(self.today + dt.timedelta(days=int(iv[0]))).isoformat(), rusty=False)
        board, name = iid.split("::", 1)
        return self._award(self.rules.xp("大项掌握"), "master", board, iid, True, f"已掌握「{name}」", bonus=False)

    def on_apply(self, iid, ok):
        board, name = iid.split("::", 1)
        self.item(iid)["last"] = self.t
        ev = self._award(self.rules.xp("应用通过" if ok else "应用未过"), "apply", board, iid, ok,
                         f"应用{'通过' if ok else '未过'}「{name}」")
        return ev + self._l3_progress(iid, ok)

    def on_wrong(self, key, board, ok, iid=""):
        """错题判断结果。iid：AI 判断这题对应的大项（可为空），判对计入该大项的 L3"""
        w = self.state["wrong"].setdefault(key, {"status": "new", "streak": 0, "tries": 0, "due": None})
        redo = w["status"] == "redo"
        w["tries"] += 1
        w["last"] = self.t
        if iid:
            w["item"] = iid
        n, src, num = key.split("|")
        label = f"第{n}季{src}第{num}题"
        if ok:
            w["streak"] = w["streak"] + 1 if redo else 1
            if not redo or w["streak"] >= self.rules.num("回炉连续判对"):
                w["status"] = "done"
            else:
                w["due"] = (self.today + dt.timedelta(days=int(self.rules.num("回炉间隔天数")))).isoformat()
            base = self.rules.xp("错题判对") + (self.rules.xp("回炉判对加成") if redo else 0)
            ev = self._award(base, "wrong", board, iid, True, f"讨伐成功 {label}" + ("（卷土重来的魔物）" if redo else ""))
            ev.append(self._npc("错题判对"))
        else:
            w.update(status="redo", streak=0,
                     due=(self.today + dt.timedelta(days=int(self.rules.num("回炉间隔天数")))).isoformat())
            ev = self._award(self.rules.xp("错题判错"), "wrong", board, iid, False, f"魔物逃走 {label}，两天后卷土重来")
            ev.append(self._npc("错题判错"))
        if iid and self.find_item(iid):
            ev += self._l3_progress(iid, ok)
        return ev

    def on_trial(self, gate, passed_ids, total):
        rate = len(passed_ids) / total if total else 0
        if rate >= self.rules.num("突破通过率"):
            if gate not in self.state["gates"]:
                self.state["gates"].append(gate)
            ev = self._award(self.rules.xp("突破成功"), "trial", note=f"晋升试炼通过，解锁 Lv.{gate}（{rate:.0%}）", bonus=False)
            ev.append(self._npc("突破成功"))
            return ev
        return [{"kind": "info", "msg": f"晋升试炼通过率 {rate:.0%}，未达到 {self.rules.num('突破通过率'):.0%}，整顿好再来挑战"}]

    def use_leave(self):
        month = self.t[:7]
        used = [d for d in self.state["leave"] if d.startswith(month)]
        if self.t in self.state["leave"]:
            return False, "今天已经请过假了"
        if len(used) >= self.rules.num("每月请假卡"):
            return False, f"本月 {len(used)} 张请假卡已用完"
        self.state["leave"].append(self.t)
        return True, self.say("请假")

    def add_boss(self, name, score):
        prev = [b["score"] for b in self.state["boss"]]
        self.state["boss"].append({"d": self.t, "name": name, "score": score})
        base = self.rules.xp("模考录分")
        if prev and score > prev[-1]:
            base += int((score - prev[-1]) * self.rules.xp("模考进步每分"))
        return self._award(base, "boss", note=f"Boss 战「{name}」{score} 分", bonus=False)

    def add_practice(self, board, total, correct, minutes):
        self.state["practice"].append({"d": self.t, "board": board, "total": total,
                                       "correct": correct, "minutes": minutes})
        self.state["seconds"][self.t] = self.state["seconds"].get(self.t, 0) + minutes * 60
        return self._award(self.rules.xp("自练每题") * total, "practice", board,
                           note=f"野外历练 {board} {correct}/{total}")

    def add_seconds(self, sec):
        """网页心跳：累加今天的学习时间；跨过达标 / 超额线时返回导师台词"""
        before = self.minutes(self.t)
        self.state["seconds"][self.t] = self.state["seconds"].get(self.t, 0) + sec
        after = self.minutes(self.t)
        goal = self.rules.num("每日目标分钟")
        if before < goal <= after:
            return [self._npc("今日达标")]
        if before < goal * 1.5 <= after:
            return [self._npc("今日超额")]
        return []

    # ================================================================ 导师台词
    def _npc(self, scene):
        """导师台词事件。scene 用来让 trainer 在 AI 已经点评过时去掉重复的“结果类”台词"""
        return {"kind": "npc", "msg": self.say(scene), "scene": scene}

    def say(self, scene):
        info = self.level_info()
        ide = self.ideal() if scene.startswith("开场") else {"diff_days": 0}
        return self.lines.pick(
            scene, 称呼=self.persona["称呼"], 导师名=self.persona["导师名"], 等级=info["level"],
            称号=info["title"], 分数=info["score"], 落后天数=max(0, round(ide["diff_days"])), 领先天数=max(0, round(-ide["diff_days"])),
            缺席天数=self.days_absent(), 连续天数=self.streak()[0], 今日分钟=int(self.minutes(self.t)),
            目标分钟=self.rules.num("每日目标分钟"))

    def tutor_context(self):
        """给 AI 导师看的“学员现状”，一段中文文字。导师开场、升级、聊天时都带上它，让她说话有依据。"""
        info = self.level_info()
        ide = self.ideal()
        run, bonus = self.streak()
        yday = (self.today - dt.timedelta(days=1)).isoformat()
        cur = self.current_batch()
        plan = (self.state.get("plan") or {}).get("tasks", [])
        fails = [e["note"] for e in self.state["events"][-40:] if not e.get("ok")][-5:]
        wins = [e["note"] for e in self.state["events"][-40:] if e.get("ok") and e["type"] != "boss"][-3:]
        rusty = [k.split("::", 1)[1] for k, v in self.state["items"].items() if v.get("rusty") and v["level"] == 0][:5]
        redo = sum(1 for w in self.state["wrong"].values() if w["status"] == "redo")
        boss = self.state["boss"][-2:]
        lines = [
            f"学员：{self.persona['称呼']}（ID {self.persona['ID']}），Lv.{info['level']}/{info['max_level']}「{info['title']}」，"
            f"预估 {info['score']} 分（目标 {info['max_score']} 分），累计经验 {self.state['xp']}。",
            (f"卡在晋升试炼前：要升到 Lv.{info['gate']} 必须先通过试炼。" if info["gate"] else ""),
            f"命运之线：{'落后' if ide['diff_days'] > 0 else '领先'} {abs(ide['diff_days'])} 天（满级目标日 {ide['target']}）。",
            f"圣火连燃（连续打卡）{run} 天，经验加成 {bonus:.0%}；今天之前已缺席 {self.days_absent()} 天。",
            f"今天已学 {int(self.minutes(self.t))} 分钟（目标 {self.rules.num('每日目标分钟')}），昨天学了 {int(self.minutes(yday))} 分钟。",
            f"今日委托完成 {sum(1 for t in plan if t['done'])}/{len(plan)}。",
            f"当前在第 {self.state['lap']} 轮征程、第 {(cur or 0) + 1} 层地下城："
            f"{'、'.join(self.batch_boards(cur)) if cur is not None else '全部打通'}。",
            f"卷土重来（回炉）的魔物 {redo} 只。",
            ("最近失败：" + "；".join(fails)) if fails else "",
            ("最近成功：" + "；".join(wins)) if wins else "",
            ("被遗忘诅咒侵蚀（复查失败）的大项：" + "、".join(rusty)) if rusty else "",
            ("最近 Boss 战：" + "；".join(f"{b['name']} {b['score']} 分" for b in boss)) if boss else "",
        ]
        return "\n".join(x for x in lines if x)

    def mood(self):
        """开场场景名"""
        if not self.state["events"]:
            return "开场·新手"
        if self.days_absent() >= 3:
            return "开场·回归"
        d = self.ideal()["diff_days"]
        if d >= 2:
            return "开场·落后"
        if d <= -2:
            return "开场·领先"
        return "开场·正常"

    # ================================================================ 每日任务
    def _task(self, typ, board, title, target, optional=False, extra=None):
        t = {"id": f"{typ}:{target}", "type": typ, "board": board, "title": title, "target": target,
             "minutes": self.rules.minutes({"review": "复查", "speedrun": "复查", "recite": "默写",
                                            "feynman": "费曼", "apply": "应用", "wrong": "错题",
                                            "skeleton": "骨架", "trial": "默写"}.get(typ, typ)),
             "done": False, "ok": None, "optional": optional}
        if extra:
            t.update(extra)
        return t

    def plan(self, force=False):
        p = self.state.get("plan")
        if p and p.get("date") == self.t and not force:
            return p
        tasks, used = [], set()
        cur = self.current_batch()
        cur_boards = self.batch_boards(cur) if cur is not None else []

        # 1) 突破试炼
        g = self.pending_gate()
        if g:
            tasks.append(self._task("trial", "", f"晋升试炼 · 晋升 Lv.{g}「{self.persona.title(g, self.level_info()['max_level'])}」", str(g)))

        # 2) 骨架：当前批次里还没定稿的板块
        for b in cur_boards:
            s = self.skel(b)
            if not s or not s["final"]:
                title = f"审阅「{b}」咒文书草稿并定稿" if s else f"编纂「{b}」咒文书（生成骨架）"
                tasks.append(self._task("skeleton", b, title, b))

        # 3) 复查（所有板块的到期大项）+ 速通（当前批次里新周目待确认的大项）
        due = []
        for b in self.boards:
            for it in self.final_items(b):
                st = self.state["items"].get(it["id"])
                if not st or st["level"] < 3:
                    continue
                if st.get("lap_check") and b in cur_boards:
                    due.append((0, "speedrun", b, it))
                elif not st.get("lap_check") and st.get("next") and st["next"] <= self.t:
                    due.append((1, "review", b, it))
        for _, typ, b, it in sorted(due, key=lambda x: x[0])[: int(self.rules.num("每日复查上限"))]:
            tasks.append(self._task(typ, b, f"{LABEL[typ]} · {b}「{it['name']}」", it["id"]))
            used.add(it["id"])

        # 4) 错题
        tasks += self._plan_wrong(cur, cur_boards)

        # 5) 新学：当前批次里有定稿骨架的板块，按“最久没练”轮换
        ready = [b for b in cur_boards if self.final_items(b)]
        last = {b: max([e["d"] for e in self.state["events"] if e.get("board") == b] or [""]) for b in ready}
        chosen = sorted(ready, key=lambda b: last[b])[: int(self.rules.num("每日新学板块数"))]
        per = math.ceil(self.rules.num("每日新学大项") / len(chosen)) if chosen else 0
        spare = []
        for b in chosen:
            n = 0
            for it in self.final_items(b):
                st = self.item(it["id"])
                if st["level"] >= 3 or it["id"] in used:
                    continue
                typ = ["recite", "feynman", "apply"][st["level"]]
                label = LABEL[typ]
                t = self._task(typ, b, f"{label} · {b}「{it['name']}」", it["id"])
                if n < per:
                    tasks.append(t)
                    n += 1
                else:
                    spare.append(t)
                used.add(it["id"])

        # 6) 追赶任务（落后理想线时出现，可选）
        if self.ideal()["diff_days"] >= 1:
            for t in spare[:2]:
                t["optional"] = True
                t["title"] = "【追赶】" + t["title"]
                tasks.append(t)

        self.state["plan"] = {"date": self.t, "tasks": tasks}
        return self.state["plan"]

    def _plan_wrong(self, cur, cur_boards):
        r = self.rules
        last_n = int(r.num("错题只取最近几季"))
        order = list(cur_boards)
        if cur is not None:  # 之前批次的板块排在后面
            for i in range(cur):
                order += [b for b in self.batch_boards(i) if b not in order]
        redo, fresh_cur, fresh_old = [], [], []
        for b in order:
            for q in vault.wrong_questions(self.paths, self.boards[b]["sources"], last_n):
                w = self.state["wrong"].get(q["key"])
                if w and w["status"] == "redo" and (w.get("due") or "") <= self.t:
                    redo.append((b, q))
                elif not w or w["status"] == "new":
                    (fresh_cur if b in cur_boards else fresh_old).append((b, q))
        lo, hi = int(r.num("每日错题下限")), int(r.num("每日错题上限"))
        key = f"{self.state['lap']}-{(cur or 0) + 1}"
        started = D(self.state.get("batch_start", {}).get(key, self.t))
        days_left = max(3, int(r.num("每批预计天数")) - (self.today - started).days)
        quota = len(redo) + math.ceil(len(fresh_cur) / days_left)
        quota = max(lo, min(hi, quota))
        picked = (redo + fresh_cur + fresh_old)[:quota]
        out = []
        for b, q in picked:
            again = any(q is x[1] for x in redo)
            out.append(self._task("wrong", b, f"讨伐魔物 · 第{q['season']}季{q['source']}第{q['num']}题"
                                  + ("（回炉）" if again else ""), q["key"]))
        return out

    def mark_done(self, task, ok):
        """把今日任务里对应的一项标记为完成。task 是任务 dict；从“骨架”页临时发起的练习没有 id，
        按 “类型:目标” 匹配今日任务里的同一项"""
        tid = task.get("id") or f"{task.get('type')}:{task.get('target')}"
        p = self.state.get("plan") or {}
        for t in p.get("tasks", []):
            if t["id"] == tid and not t["done"]:
                t["done"], t["ok"] = True, ok
                return

    # ================================================================ 面板
    def dashboard(self):
        info = self.level_info()
        run, bonus = self.streak()
        ide = self.ideal()
        cur = self.current_batch()
        tree = []
        for i, batch in enumerate(self.rules.batches):
            for b in batch:
                s = self.skel(b)
                items = self.final_items(b)
                tree.append({
                    "board": b, "batch": i + 1,
                    "state": ("locked" if not self.available(b) else
                              "mastered" if self.board_mastered(b) else
                              "current" if i == cur else
                              "cleared" if (i + 1) in self.cleared() else "later"),
                    "skeleton": "final" if s and s["final"] else ("draft" if s else "none"),
                    "progress": round(self.board_progress(b), 3),
                    "items": len(items),
                    "mastered": sum(1 for it in items if self.item_progress(it["id"]) >= 1),
                    "acc": vault.accuracy(self.paths, self.boards.get(b, {}).get("sources", [b])),
                })
        side = [{"board": k, "target": v, "acc": vault.accuracy(self.paths, [k])} for k, v in self.rules.side.items()]
        redo = sum(1 for w in self.state["wrong"].values() if w["status"] == "redo")
        today_min = int(self.minutes(self.t))
        scene = self.mood()
        return {
            "today": self.t,
            "level": info, "xp": self.state["xp"],
            "streak": {"days": run, "bonus": bonus},
            "ideal": ide, "lap": self.state["lap"],
            "batch": {"index": (cur + 1) if cur is not None else None,
                      "boards": self.batch_boards(cur) if cur is not None else [],
                      "count": len(self.rules.batches)},
            "forecast": self.lap_forecast(),
            "tree": tree, "side": side, "redo": redo,
            "minutes": {"today": today_min, "goal": self.rules.num("每日目标分钟"),
                        "floor": self.rules.num("保底分钟")},
            "leave": {"used": len([d for d in self.state["leave"] if d.startswith(self.t[:7])]),
                      "total": self.rules.num("每月请假卡"), "today": self.t in self.state["leave"]},
            "boss": self.state["boss"][-5:],
            "greeting": self.say(scene), "scene": scene,
            "recent": self.state["events"][-12:][::-1],
        }
