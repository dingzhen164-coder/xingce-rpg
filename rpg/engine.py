"""
游戏规则核心（纯计算 + 修改存档字典；不发网络请求）。数值都来自 规则.md（config.Rules），说法来自 themes.py。

一、修为 → 道行（预估分）→ 境界
    道行 = 起始分数 + (目标分数 − 起始分数) × 修为 / 理想修为，理想修为 = 每日理想经验 × (目标日 − 开始日期)。
    即“每天学满、一天不断，到目标日正好目标分数（80）”；之后按同样速度继续涨，最高到“最高分数”。
    境界按道行分段（themes.BANDS）：凡人 50 / 炼气 51–59 / 筑基 60 / 金丹 65 / 元婴 70 / 化神 75 / 大乘 80 / 真仙 85。
    渡劫：进入“渡劫分数线”（60、65…）上的大境界必须渡劫。修为到了但没渡劫 → 道行停在线下（瓶颈），多出的修为照样累计，
    渡劫成功后一次性涌入。条件见 tribulation_status()。
    宗门大比（模考）：最近两次成绩里较低的那个若高于当前道行，修为直接补到这个分数（add_boss 里的“大比悟道”）。

二、功法（骨架）掌握度：每一重（大项）0 未入门 →（背诵连续过 N 次）1 小成 →（论道过）2 大成 →（试剑连续过 N 次）3 圆满，
    之后按复查间隔温养道基；温养失败降回 0（根基松动）。批次 / 周目逻辑同前（一批 = 一重秘境，全部打通 = 一个大周天）。

三、灵根（roots）：每个板块一条。有功法的板块全部圆满即激活；没有功法的按最近两季正确率激活。
    品阶 0–7（黄下…天上）按最近几季该板块正确率实时计算，会跌落，但激活后不低于 0。
    加成：修为 +品阶×每阶加成；温养间隔 ×(1+品阶×复查间隔加成)。高境界渡劫要求一定数量、品阶的灵根。

四、其他：丹药（炼丹 = 选板块加练一炉，按成功率成丹，额外修为）、闭关（指定板块修为加成）、顿悟（随机额外修为）、
    走火入魔（连续修炼太久 / 连错太多 → 强制调息）、道心（近 N 天打卡占比，渡劫门槛）、宗门周常、储物袋（突破丹、护心丹）。

所有“结果”函数返回事件列表，网页据此弹出提示：
    {"kind": "xp", "v": 30, "msg": "…"} / {"kind": "realm", "name": "筑基初期", "major": True, "score": 60.0} /
    {"kind": "npc", "msg": "…", "scene": "渡劫成功"} / {"kind": "info", "msg": "…"}
"""
import datetime as dt
import math
import random
import time

from . import skeleton, themes, vault

DAILY_WRONG = "wrong:daily"   # 今日功课/心魔录共用的斩心魔任务
TRAIN_TYPES = ("recite", "review", "speedrun", "feynman", "example", "apply", "wrong")


def D(s):
    return dt.date.fromisoformat(s) if isinstance(s, str) else s


class Game:
    def __init__(self, paths, rules, persona, lines, state, today=None, rng=None):
        self.paths, self.rules, self.persona, self.lines, self.state = paths, rules, persona, lines, state
        self.today = today or dt.date.today()
        self.t = self.today.isoformat()
        self.rng = rng or random.Random()
        self._skel = {}
        self._acc = {}

    # ================================================================ 风格
    @property
    def theme(self):
        return self.state.get("theme") or themes.DEFAULT_THEME

    @property
    def th(self):
        return themes.get(self.theme)

    def T(self, key):
        return self.th["terms"][key]

    def level_names(self):
        return self.T("levels").split(",")

    def label(self, typ):
        return {"teach": self.T("teach"), "recite": self.T("recite"), "feynman": self.T("feynman"), "example": self.T("example"), "apply": self.T("apply"),
                "review": self.T("review"), "speedrun": self.T("speedrun"), "wrong": self.T("kill"),
                "skeleton": "编撰" + self.T("skeleton"), "tribulation": self.T("tribulation"),
                "heal": self.T("heal")}.get(typ, typ)

    # ================================================================ 板块 / 功法
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
        """板块可以修炼功法：有 skill，或者已经有功法（骨架）文件"""
        return board in self.boards and (self.has_skill(board) or self.skel(board) is not None)

    def final_items(self, board):
        s = self.skel(board)
        return s["items"] if s and s["final"] else []

    def find_item(self, iid):
        board = iid.split("::", 1)[0]
        for it in self.final_items(board):
            if it["id"] == iid:
                return it
        return None

    def all_items(self):
        return [it for b in self.boards for it in self.final_items(b)]

    def item(self, iid):
        st = self.state["items"].setdefault(iid, {
            "level": 0, "l1": 0, "l3": 0, "stage": -1, "next": None,
            "lap_check": False, "passed_once": False, "last": None, "rusty": False})
        # 老存档的圆满不重置；其余项目需要完成独立举例。
        st.setdefault("example_ok", st["level"] >= 3)
        return st

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

    def sources(self, board):
        return self.boards.get(board, {}).get("sources") or [board]

    def accuracy(self, board, last=None):
        last = last or int(self.rules.num("灵根取最近几季"))
        key = (board, last)
        if key not in self._acc:
            self._acc[key] = vault.accuracy(self.paths, self.sources(board), last=last)
        return self._acc[key]

    # ================================================================ 修为 → 道行 → 境界
    def ideal_total(self):
        """到目标日的理想修为（道行从起始分数涨到目标分数所需的修为）"""
        r = self.rules
        days = max(30, (r.date("目标日") - r.date("开始日期")).days)
        return r.num("每日理想经验") * days

    def xp_at(self, score):
        r = self.rules
        span = r.num("目标分数") - r.num("起始分数")
        return (score - r.num("起始分数")) / span * self.ideal_total()

    def raw_score(self, xp=None):
        r = self.rules
        xp = self.state["xp"] if xp is None else xp
        span = r.num("目标分数") - r.num("起始分数")
        return min(r.num("最高分数"), r.num("起始分数") + span * xp / self.ideal_total())

    def gates(self):
        return sorted(int(x) for x in self.rules.nums("渡劫分数线"))

    def pending_gate(self, xp=None):
        """修为已到、但还没渡劫的大境界分数线（瓶颈）；没有返回 None"""
        raw = self.raw_score(xp)
        for g in self.gates():
            if g not in self.state["gates"] and raw >= g:
                return g
        return None

    def realm_info(self, xp=None):
        xp = self.state["xp"] if xp is None else xp
        raw = self.raw_score(xp)
        gate = self.pending_gate(xp)
        eff = min(raw, gate - 0.01) if gate else raw
        s_int = int(math.floor(eff + 1e-9))
        big, sub, a, b = themes.sub_stage(s_int)
        b = min(b, self.rules.num("最高分数"))
        name = themes.realm_name(self.theme, s_int)
        if gate:
            into, need, frac = int(xp - self.xp_at(a)), int(self.xp_at(gate) - self.xp_at(a)), 1.0
        elif b > a:
            into, need = int(xp - self.xp_at(a)), int(self.xp_at(b) - self.xp_at(a))
            frac = max(0.0, min(1.0, into / need)) if need else 1.0
        else:
            into, need, frac = 0, 0, 1.0
        nxt = themes.realm_name(self.theme, b) if b > s_int and not gate else ""
        return {"score": round(eff, 1), "raw": round(raw, 2), "big": big, "sub": sub,
                "name": name, "big_name": self.th["realms"][big],
                "bottleneck": bool(gate), "gate": gate,
                "gate_realm": themes.realm_of_gate(self.theme, gate) if gate else "",
                "overflow": int(xp - self.xp_at(gate)) if gate else 0,
                "into": into, "need": need, "frac": frac, "next": nxt,
                "target": self.rules.num("目标分数"), "max_score": self.rules.num("最高分数")}

    # ================================================================ 时间 / 打卡 / 道心
    def study_minutes(self, day):
        """在本程序里真正修炼的分钟（网页心跳计时 + 历练录入）"""
        return self.state["seconds"].get(day if isinstance(day, str) else day.isoformat(), 0) / 60

    def lecture_minutes(self, day):
        """听道（在其他平台看网课）的分钟，首页手动记录"""
        ds = day if isinstance(day, str) else day.isoformat()
        return sum(x["minutes"] for x in self.state.setdefault("lectures", []) if x["d"] == ds)

    def minutes(self, day):
        """每日功行 = 修炼 + 听道；每日目标、打卡、道心、周常都按这个算"""
        return self.study_minutes(day) + self.lecture_minutes(day)

    def add_lecture(self, minutes, note="", day=None):
        """记一笔听道。day 可以是最近 7 天内（忘了记可以补）；给少量修为（经验.听道每分钟）"""
        minutes = int(minutes)
        cap = int(self.rules.num("听道单次上限") or 600)
        if not 1 <= minutes <= cap:
            raise ValueError("听道分钟要在 1–%d 之间" % cap)
        d = D(day) if day else self.today
        if not (self.today - dt.timedelta(days=7) <= d <= self.today):
            raise ValueError("只能补记最近 7 天的听道")
        ds = d.isoformat()
        goal = self.rules.num("每日目标分钟")
        before = self.minutes(ds)
        xp = int(round(minutes * self.rules.xp("听道每分钟")))
        ev = self._award(xp, "lecture", note="%s %d 分钟%s" % (self.T("lecture"), minutes, ("：" + note) if note else ""),
                         bonus=False) if xp else []
        self.state["lectures"].append({"id": "%s-%d" % (ds, int(time.time() * 1000) % 10 ** 9), "d": ds,
                                       "minutes": minutes, "note": str(note)[:40], "xp": xp})
        if ds == self.t and before < goal <= self.minutes(ds):
            ev.append(self._npc("今日达标"))
        return ev

    def delete_lecture(self, lid):
        """删掉记错的一笔（同时扣回那次给的修为）"""
        ls = self.state.setdefault("lectures", [])
        x = next((x for x in ls if x["id"] == lid), None)
        if not x:
            raise ValueError("找不到这条记录")
        ls.remove(x)
        self.state["xp"] = max(0, self.state["xp"] - x.get("xp", 0))
        self.state["events"].append({"t": dt.datetime.now().isoformat(timespec="seconds"), "d": self.t, "type": "lecture",
                                     "board": "", "item": "", "ok": True, "xp": -x.get("xp", 0),
                                     "note": "删除%s记录 %d 分钟" % (self.T("lecture"), x["minutes"])})
        return []

    def qualifies(self, day):
        ds = day.isoformat()
        return (ds in self.state["leave"] or ds in self.state["protected"]
                or self.minutes(ds) >= self.rules.num("保底分钟"))

    def streak(self):
        """返回 (连续打卡天数, 加成比例)。断一天累计天数减半（不清零）"""
        s = run = 0
        d = D(self.state["created"])
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
        d = self.today - dt.timedelta(days=1)
        n = 0
        start = D(self.state["created"])
        while d >= start and not self.qualifies(d):
            n += 1
            d -= dt.timedelta(days=1)
        return n if d >= start else 0

    def dao(self):
        """道心 0–100：最近 N 天（不含今天）打卡的比例；开始修炼之前的日子按“打卡”算（新入门道心圆满，缺一天降一截）"""
        n = int(self.rules.num("道心统计天数"))
        created = D(self.state["created"])
        ok = sum(1 for k in range(1, n + 1)
                 if (self.today - dt.timedelta(days=k)) < created or self.qualifies(self.today - dt.timedelta(days=k)))
        return round(100 * ok / n)

    def dao_label(self, v):
        return "稳固" if v >= 80 else "平稳" if v >= 60 else "动摇" if v >= 40 else "崩乱"

    # ================================================================ 天道进度 / 预测
    def ideal(self):
        r = self.rules
        daily = r.num("每日理想经验")
        days = 0
        d = r.date("开始日期")
        while d < self.today:
            if d.isoformat() not in self.state["leave"]:
                days += 1
            d += dt.timedelta(days=1)
        ideal_xp = daily * days
        # 天道进度只比“自己修出来的”修为：大比悟道补上的修为提升境界，但不算进度（免得一次模考考好就能躺几个月）
        effort = self.state["xp"] - self.insight_xp()
        diff_days = (ideal_xp - effort) / daily                       # >0 落后，<0 领先
        xp14 = sum(e["xp"] for e in self.state["events"]
                   if D(e["d"]) > self.today - dt.timedelta(days=14) and e["type"] != "insight")
        min14 = sum(self.study_minutes(self.today - dt.timedelta(days=k)) for k in range(14))   # 修为主要来自修炼，不含听道
        per_min = xp14 / min14 if min14 >= 30 and xp14 > 0 else daily / r.num("每日目标分钟")
        catch = None
        if diff_days > 0.5:
            extra_total = diff_days * daily / per_min
            catch = {"hours": round(extra_total / 60, 1), "per_day": int(math.ceil(extra_total / 14 / 5.0) * 5), "days": 14}
        span = min(14, (self.today - D(self.state["created"])).days + 1)
        rate = xp14 / max(1, span)
        remain = max(0, self.xp_at(r.num("目标分数")) - self.state["xp"])
        active_days = len({e["d"] for e in self.state["events"]})
        eta = (self.today + dt.timedelta(days=math.ceil(remain / rate))).isoformat() \
            if rate > 0 and active_days >= 3 else None
        return {"ideal_xp": int(ideal_xp), "diff_days": round(diff_days, 1), "catch": catch,
                "eta": eta, "target": r.date("目标日").isoformat(), "target_score": r.num("目标分数"),
                "daily_rate": round(rate)}

    def insight_xp(self):
        return sum(e["xp"] for e in self.state["events"] if e["type"] == "insight")

    def lap_forecast(self):
        p = self.lap_progress()
        hist = self.state["progress_hist"]
        past = span = None
        for k in range(7, 0, -1):
            v = hist.get((self.today - dt.timedelta(days=k)).isoformat())
            if v is not None:
                past, span = v, k
                break
        days_left = None
        if past is not None and p > past:
            days_left = math.ceil((1 - p) / ((p - past) / span))
        return {"progress": p, "days_left": days_left}

    # ================================================================ 灵根
    def root_boards(self):
        out = list(self.boards)
        out += [b for b in self.rules.side if b not in out]
        return out

    def root_name(self, board):
        return themes.ROOT_NAMES.get(self.theme, {}).get(board) or (board[:2] + self.T("root"))

    def root_grade(self, board):
        """按正确率算出的品阶（0–7），数据不足返回 0"""
        acc = self.accuracy(board)
        if not acc:
            return 0
        thr = self.rules.root_thresholds(board)
        g = 0
        for k, v in enumerate(thr):
            if acc["rate"] + 1e-9 >= v:
                g = k
        return g

    def root_can_activate(self, board):
        if self.available(board):
            # 全部圆满即觉醒；不看 lap_check（新一轮大周天开始时圆满的功法会被标记“待重温”，但灵根早已觉醒）
            items = self.final_items(board)
            return bool(items) and all(self.item(i["id"])["level"] >= 3 for i in items)
        acc = self.accuracy(board, last=2)
        thr = self.rules.root_thresholds(board)[0]
        return bool(acc and len(acc["per"]) >= 2 and all(o / t + 1e-9 >= thr for _, o, t in acc["per"]))

    def roots(self):
        """[{board, name, on, grade, grade_name, acc, bonus}]"""
        out = []
        for b in self.root_boards():
            st = self.state["roots"].get(b) or {}
            on = bool(st.get("on"))
            g = self.root_grade(b) if on else 0
            acc = self.accuracy(b)
            out.append({"board": b, "name": self.root_name(b), "on": on, "since": st.get("on"),
                        "grade": g, "grade_name": self.th["grades"][g] if on else "未觉醒",
                        "tier": g // 2, "acc": acc["rate"] if acc else None,
                        "route": "功法" if self.available(b) else "正确率",
                        "bonus": round(g * self.rules.num("灵根每阶加成"), 3) if on else 0})
        return out

    def root_bonus(self, board):
        st = self.state["roots"].get(board)
        if not board or not st or not st.get("on"):
            return 0.0
        return self.root_grade(board) * self.rules.num("灵根每阶加成")

    def _roots_housekeeping(self):
        ev = []
        for b in self.root_boards():
            st = self.state["roots"].setdefault(b, {"on": None, "grade": 0})
            if not st["on"] and self.root_can_activate(b):
                st["on"], st["grade"] = self.t, self.root_grade(b)
                ev.append({"kind": "info", "msg": f"{self.root_name(b)}觉醒！（{self.th['grades'][st['grade']]}）"})
                ev.append(self._npc("灵根激活"))
                continue
            if st["on"]:
                g = self.root_grade(b)
                if g != st.get("grade", 0):
                    up = g > st.get("grade", 0)
                    ev.append({"kind": "info", "msg": f"{self.root_name(b)}{'晋升' if up else '跌落'}为{self.th['grades'][g]}"})
                    ev.append(self._npc("灵根晋阶" if up else "灵根跌落"))
                    st["grade"] = g
        return ev

    def roots_meet(self, gate):
        """某渡劫线的灵根要求是否满足：(是否满足, 说明文字)"""
        req = self.rules.gate_roots(gate)
        rs = [r for r in self.roots() if r["on"]]
        parts, ok = [], True
        if "激活" in req:
            n = len(rs)
            ok &= n >= req["激活"]
            parts.append(f"已觉醒 {n}/{req['激活']}")
        for tier in range(4):
            if tier in req:
                n = sum(1 for r in rs if r["tier"] >= tier)
                ok &= n >= req[tier]
                parts.append(f"{self.th['tiers'][tier]}及以上 {n}/{req[tier]}")
        return ok, "，".join(parts) or "无要求"

    # ================================================================ 渡劫
    def contests(self, kind="大比"):
        return [b for b in self.state["boss"] if b.get("kind", "大比") == kind]

    def tribulation_status(self):
        g = self.pending_gate()
        if not g:
            return None
        r = self.rules
        last2 = [b["score"] for b in self.contests()[-2:]]
        roots_ok, roots_txt = self.roots_meet(g)
        dao = self.dao()
        tr = self.state["trib"]
        cool = tr.get("cooldown")
        heal_left = [h for h in tr.get("heal", []) if not h.get("done")]
        conds = [
            {"name": self.T("xp"), "ok": True, "text": f"已达 {g} 分线"},
            {"name": self.T("boss"), "ok": len(last2) == 2 and min(last2) >= g,
             "text": ("最近两次：" + "、".join(str(x) for x in last2)) if last2 else "还没有记录", "need": f"两次都 ≥ {g}"},
            {"name": self.T("root"), "ok": roots_ok, "text": roots_txt},
            {"name": self.T("dao"), "ok": dao >= r.num("渡劫道心"), "text": f"{dao}（需 ≥ {r.num('渡劫道心')}）"},
            {"name": "道基", "ok": (not cool or cool <= self.t) and not heal_left,
             "text": ("完好" if not cool or cool <= self.t else f"受损，{cool} 后可再渡劫")
             + (f"；还需{self.T('heal')} {len(heal_left)} 项" if heal_left else "")},
        ]
        idx = self.gates().index(g)
        counts = self.rules.nums("天劫雷数")
        n = int(counts[min(idx, len(counts) - 1)])
        return {"gate": g, "realm": themes.realm_of_gate(self.theme, g), "thunders": n,
                "ready": all(c["ok"] for c in conds), "conds": conds,
                "pill": self.th["gate_items"].get(g, "突破丹"),
                "pills": self.state["bag"].get(self.th["gate_items"].get(g, ""), 0)}

    def weakest_board(self, candidates):
        """正确率最低的板块（紫霄神雷 / 心魔榜用）"""
        scored = [(self.accuracy(b)["rate"] if self.accuracy(b) else 1.0, b) for b in candidates]
        return min(scored)[1] if scored else None

    def _pool_wrong(self, boards, prefer_redo=True):
        qs = []
        for b in boards:
            for q in vault.wrong_questions(self.paths, self.sources(b)):
                w = self.state["wrong"].get(q["key"]) or {}
                pri = 0 if w.get("status") == "redo" else (1 if w.get("status") != "done" else 2)
                qs.append((pri if prefer_redo else 0, b, q["key"]))
        return qs

    def build_gauntlet(self, kind, board=None, gate=None, ai_ok=True):
        """渡劫（kind="tribulation"）或炼丹（kind="alchemy"）的关卡列表：[{kind: recite|wrong|apply, target, board, label}]"""
        rng = self.rng
        if kind == "alchemy":
            items = [it for it in self.final_items(board)]
            known = [it for it in items if self.item(it["id"])["level"] >= 1] or items
            wrongs = sorted(self._pool_wrong([board]))
            n = int(self.rules.num("炼丹题数"))
            steps = []
            for k in range(n):
                use_wrong = (k % 2 == 1 and wrongs) or not known
                if use_wrong and wrongs:
                    _, b, key = wrongs.pop(0)
                    steps.append({"kind": "wrong", "target": key, "board": b})
                elif known:
                    it = rng.choice(known)
                    steps.append({"kind": "recite", "target": it["id"], "board": board})
            return steps
        # 渡劫
        st = self.tribulation_status()
        n = st["thunders"] if st else 3
        items = [it for it in self.all_items() if self.item(it["id"])["level"] >= 1]
        deep = [it for it in items if self.item(it["id"])["level"] >= 2] or items
        roots_on = [r["board"] for r in self.roots() if r["on"]] or list(self.boards)
        wrongs = sorted(self._pool_wrong(list(self.boards)))
        rng.shuffle(items)
        names = self.th["thunders"]
        steps, order = [], ["recite", "wrong", "apply"]
        for k in range(n - 1):
            want = order[k % 3]
            if want == "apply" and (not ai_ok or not deep):
                want = "recite"
            if want == "wrong" and not wrongs:
                want = "recite"
            if want == "recite" and not items:
                want = "wrong" if wrongs else None
            if want is None:
                break
            if want == "recite":
                it = items[k % len(items)]
                steps.append({"kind": "recite", "target": it["id"], "board": it["id"].split("::")[0], "label": names["recite"]})
            elif want == "wrong":
                _, b, key = wrongs.pop(0)
                steps.append({"kind": "wrong", "target": key, "board": b, "label": names["wrong"]})
            else:
                it = rng.choice(deep)
                steps.append({"kind": "apply", "target": it["id"], "board": it["id"].split("::")[0], "label": names["apply"]})
        # 紫霄神雷：最弱灵根的心魔
        wb = self.weakest_board(roots_on)
        final = [x for x in self._pool_wrong([wb]) if x[2] not in {s["target"] for s in steps}] if wb else []
        if final:
            _, b, key = sorted(final)[0]
            steps.append({"kind": "wrong", "target": key, "board": b, "label": names["final"]})
        elif items:
            it = rng.choice(items)
            steps.append({"kind": "recite", "target": it["id"], "board": it["id"].split("::")[0], "label": names["final"]})
        return steps

    def use_gate_pill(self, gate):
        name = self.th["gate_items"].get(gate)
        if name and self.state["bag"].get(name, 0) > 0:
            self.state["bag"][name] -= 1
            return name
        return None

    def on_tribulation(self, gate, ok, failed_step=None):
        tr = self.state["trib"]
        realm = themes.realm_of_gate(self.theme, gate)
        if ok:
            before = self.realm_info()
            if gate not in self.state["gates"]:
                self.state["gates"].append(gate)
            tr.update(cooldown=None, heal=[])
            ev = self._award(self.rules.xp("渡劫成功"), "tribulation", note=f"{self.T('tribulation')}成功，踏入{realm}", bonus=False)
            after = self.realm_info()
            if after["score"] > before["score"]:
                ev.append({"kind": "realm", "name": after["name"], "major": True, "score": after["score"]})
            ev.append(self._npc("渡劫成功"))
            return ev
        tr["cooldown"] = (self.today + dt.timedelta(days=int(self.rules.num("渡劫冷却天数")))).isoformat()
        tr["heal"] = [dict(failed_step, done=False)] if failed_step else []
        plan = self.state.get("plan")
        if plan and plan.get("date") == self.t:  # 疗伤马上出现在今日功课里
            have = {t["id"] for t in plan["tasks"]}
            plan["tasks"] = [t for t in self._heal_tasks() if t["id"] not in have] + plan["tasks"]
        self.state["events"].append({"t": dt.datetime.now().isoformat(timespec="seconds"), "d": self.t,
                                     "type": "tribulation", "board": "", "item": "", "ok": False, "xp": 0,
                                     "note": f"{realm}{self.T('tribulation')}失败，道基受损"})
        return [{"kind": "info", "msg": f"道基受损：{tr['cooldown']} 后才能再次{self.T('tribulation')}，先完成{self.T('heal')}"},
                self._npc("渡劫失败")]

    def _heal_progress(self, kind, target, ok):
        if not ok:
            return
        for h in self.state["trib"].get("heal", []):
            if h["kind"] == kind and h["target"] == target:
                h["done"] = True

    # ================================================================ 分批 / 周目
    def batch_boards(self, idx):
        return [b for b in self.rules.batches[idx] if self.available(b)]

    def cleared(self):
        return self.state["cleared"].setdefault(str(self.state["lap"]), [])

    def current_batch(self):
        for i in range(len(self.rules.batches)):
            if (i + 1) in self.cleared() or not self.batch_boards(i):
                continue
            return i
        return None

    def housekeeping(self):
        """检查通关、灵根、护心丹、周常、闭关到期，记录进度快照。每次读取面板和提交结果后调用。"""
        ev = self._roots_housekeeping()
        changed = True
        while changed:
            changed = False
            i = self.current_batch()
            if i is None:
                if any(self.batch_boards(k) for k in range(len(self.rules.batches))):
                    ev += self._lap_clear()
                break
            key = f"{self.state['lap']}-{i + 1}"
            self.state.setdefault("batch_start", {}).setdefault(key, self.t)
            if all(self.board_mastered(b) for b in self.batch_boards(i)):
                self.cleared().append(i + 1)
                ev += self._award(self.rules.xp("批次通关"), "batch", note=f"第{i + 1}{self.T('batch')}打通", bonus=False)
                ev.append(self._npc("批次通关"))
                changed = True
        ev += self._roots_housekeeping()
        ev += self._heart_pill()
        ev += self._weekly_claim()
        ev += self._retreat_check()
        self.state["progress_hist"][self.t] = round(self.lap_progress(), 4)
        return ev

    def _lap_clear(self):
        lap = self.state["lap"]
        ev = self._award(self.rules.xp("周目通关"), "lap", note=f"第{lap}个{self.T('lap')}圆满", bonus=False)
        ev.append(self._npc("周目通关"))
        self.state["lap"] = lap + 1
        for st in self.state["items"].values():
            if st["level"] >= 3:
                st["lap_check"] = True
        return ev

    # ================================================================ 修为
    def _award(self, base, typ, board="", item="", ok=True, note="", bonus=True):
        before = self.realm_info()
        mult = 1.0
        if bonus:
            mult += self.streak()[1] + self.root_bonus(board) + self._retreat_bonus(board)
        gain = int(round(base * mult))
        self.state["xp"] += gain
        self.state["events"].append({"t": dt.datetime.now().isoformat(timespec="seconds"), "d": self.t,
                                     "type": typ, "board": board, "item": item, "ok": ok,
                                     "xp": gain, "note": note})
        ev = [{"kind": "xp", "v": gain, "msg": note}] if gain else []
        if typ in TRAIN_TYPES:
            ev += self._qi_check(ok)
            if ok and typ in ("wrong", "feynman", "apply") and self.rng.random() < self.rules.num("顿悟概率"):
                extra = int(round(gain * self.rules.num("顿悟倍数")))
                if extra:
                    self.state["xp"] += extra
                    self.state["events"].append({"t": dt.datetime.now().isoformat(timespec="seconds"), "d": self.t,
                                                 "type": "epiphany", "board": board, "item": item, "ok": True,
                                                 "xp": extra, "note": f"{self.T('epiphany')}！"})
                    ev.append({"kind": "xp", "v": extra, "msg": f"{self.T('epiphany')}！"})
                    ev.append(self._npc("顿悟"))
        after = self.realm_info()
        if (after["big"], after["sub"]) != (before["big"], before["sub"]) and after["score"] > before["score"]:
            ev.append({"kind": "realm", "name": after["name"], "major": after["big"] != before["big"],
                       "score": after["score"]})
            if after["big"] == before["big"] or typ != "tribulation":
                ev.append(self._npc("小境界提升"))
        if after["bottleneck"] and not before["bottleneck"]:
            ev.append(self._npc("瓶颈"))
        return ev

    # ================================================================ 走火入魔 / 闭关
    def _rest(self, minutes, why):
        self.state["rest_until"] = time.time() + minutes * 60
        return [{"kind": "info", "msg": f"{self.T('qi')}预警：{why}，调息 {int(minutes)} 分钟后再修炼"}, self._npc("走火入魔")]

    def resting(self):
        """还需调息的分钟数（0 表示可以修炼）"""
        left = (self.state.get("rest_until") or 0) - time.time()
        return max(0, int(math.ceil(left / 60)))

    def _qi_check(self, ok):
        if ok:
            self.state["fail_streak"] = 0
            return []
        self.state["fail_streak"] = self.state.get("fail_streak", 0) + 1
        if self.state["fail_streak"] >= self.rules.num("走火入魔连错"):
            self.state["fail_streak"] = 0
            return self._rest(self.rules.num("走火调息分钟"), f"连续失败 {int(self.rules.num('走火入魔连错'))} 次")
        return []

    def _retreat_bonus(self, board):
        r = self.state.get("retreat")
        if r and board and r["board"] == board and time.time() < r["end"]:
            return self.rules.num("闭关加成")
        return 0.0

    def start_retreat(self, board, minutes):
        r = self.state.get("retreat")
        if r and time.time() < r["end"]:
            return False, f"正在{self.T('retreat')}中（{r['board']}）"
        now = time.time()
        self.state["retreat"] = {"board": board, "start": now, "end": now + minutes * 60, "minutes": minutes,
                                 "xp0": self.state["xp"], "d": self.t}
        return True, f"开始{self.T('retreat')}：{board} {minutes} 分钟，期间该板块{self.T('xp')} +{self.rules.num('闭关加成'):.0%}"

    def end_retreat(self):
        r = self.state.get("retreat")
        if not r:
            return []
        self.state["retreat"] = None
        mins = int(min(r["minutes"], (time.time() - r["start"]) / 60))
        gained = self.state["xp"] - r["xp0"]
        self.state["events"].append({"t": dt.datetime.now().isoformat(timespec="seconds"), "d": self.t,
                                     "type": "retreat", "board": r["board"], "item": "", "ok": True, "xp": 0,
                                     "note": f"{self.T('retreat_end')}：{r['board']} {mins} 分钟，{self.T('xp')} +{gained}"})
        e = self._npc("出关")
        e["extra"] = f"刚结束 {mins} 分钟的{self.T('retreat')}（{r['board']}），期间{self.T('xp')} +{gained}"
        return [{"kind": "info", "msg": f"{self.T('retreat_end')}：{r['board']} {mins} 分钟，{self.T('xp')} +{gained}"}, e]

    def _retreat_check(self):
        r = self.state.get("retreat")
        return self.end_retreat() if r and time.time() >= r["end"] else []

    # ================================================================ 护心丹 / 周常 / 储物袋
    def bag_add(self, name, n=1):
        self.state["bag"][name] = self.state["bag"].get(name, 0) + n

    def heart_pill_name(self):
        return "护心丹" if self.theme == "修仙" else "守护护符"

    def _heart_pill(self):
        ev = []
        y = self.today - dt.timedelta(days=1)
        yy = y - dt.timedelta(days=1)
        name = "护心丹"  # 存档里统一叫护心丹，显示时按风格换名
        if (y >= D(self.state["created"]) and yy >= D(self.state["created"]) and not self.qualifies(y)
                and self.qualifies(yy) and self.state["bag"].get(name, 0) > 0):
            self.state["bag"][name] -= 1
            self.state["protected"].append(y.isoformat())
            ev.append({"kind": "info", "msg": f"昨天断了修炼，自动服下{self.heart_pill_name()}，打卡不断"})
            ev.append(self._npc("护心丹"))
        run = self.streak()[0]
        n = int(self.rules.num("护心丹连续天数"))
        start = (self.today - dt.timedelta(days=max(0, run - 1))).isoformat()
        key = f"{start}:{run // n}"
        if run >= n and key not in self.state["hx_awards"]:
            self.state["hx_awards"].append(key)
            self.bag_add(name)
            ev.append({"kind": "info", "msg": f"连续修炼 {run} 天，获得一颗{self.heart_pill_name()}"})
        return ev

    def week_key(self):
        y, w, _ = self.today.isocalendar()
        return f"{y}-W{w:02d}"

    def weekly(self):
        """本周宗门周常：[{key, name, target, progress, done}]"""
        monday = self.today - dt.timedelta(days=self.today.weekday())
        days = {(monday + dt.timedelta(days=k)).isoformat() for k in range(7)}
        evs = [e for e in self.state["events"] if e["d"] in days and e.get("ok")]
        prog = {
            "斩心魔": sum(1 for e in evs if e["type"] == "wrong"),
            "背诵口诀": sum(1 for e in evs if e["type"] in ("recite", "review", "speedrun")),
            "论道": sum(1 for e in evs if e["type"] == "feynman"),
            "修炼分钟": int(sum(self.minutes(d) for d in days)),
            "宗门大比": sum(1 for b in self.contests() if b["d"] in days),
        }
        label = {"斩心魔": self.T("kill"), "背诵口诀": self.T("recite"), "论道": self.T("feynman"),
                 "修炼分钟": "功行分钟（修炼 + %s）" % self.T("lecture"), "宗门大比": self.T("boss")}
        out = []
        for k in ("斩心魔", "背诵口诀", "论道", "修炼分钟", "宗门大比"):
            tgt = int(self.rules.num("周常." + k))
            if tgt > 0:
                out.append({"key": k, "name": label[k], "target": tgt, "progress": min(prog[k], tgt),
                            "done": prog[k] >= tgt})
        return out

    def _weekly_claim(self):
        wk = self.week_key()
        claimed = self.state["weekly"].setdefault(wk, [])
        ev = []
        qs = self.weekly()
        for q in qs:
            if q["done"] and q["key"] not in claimed:
                claimed.append(q["key"])
                ev += self._award(self.rules.xp("周常"), "weekly", note=f"{self.T('weekly')}完成：{q['name']}", bonus=False)
        if qs and all(q["done"] for q in qs) and "all" not in claimed:
            claimed.append("all")
            self.bag_add("护心丹")
            ev.append({"kind": "info", "msg": f"本周{self.T('weekly')}全部完成，获得一颗{self.heart_pill_name()}"})
            ev.append(self._npc("周常完成"))
        return ev

    def bag_view(self):
        items = []
        for name, n in self.state["bag"].items():
            if n <= 0:
                continue
            shown = self.heart_pill_name() if name == "护心丹" else name
            desc = ("断修一天时自动服下，保住连续修炼" if name == "护心丹" else
                    f"{self.T('tribulation')}时抵挡一道失败的天雷")
            items.append({"name": shown, "count": n, "desc": desc})
        return items

    # ================================================================ 训练结果
    def on_recite(self, iid, ok, mode="recite"):
        """背诵口诀结果。mode: recite 修炼 / review 温养 / speedrun 新周天重温 / trial 渡劫炼丹（不改掌握度）"""
        st = self.item(iid)
        board, name = iid.split("::", 1)
        st["last"] = self.t
        self._heal_progress("recite", iid, ok)
        if mode == "trial":
            return self._award(self.rules.xp("默写通过" if ok else "默写未过"), "recite", board, iid, ok,
                               f"{self.T('recite')}{'成功' if ok else '失败'}「{name}」")
        ev = []
        if mode in ("review", "speedrun"):
            if ok:
                if mode == "speedrun":
                    st["lap_check"] = False
                else:
                    iv = self.rules.nums("复查间隔天数")
                    st["stage"] = min(st["stage"] + 1, len(iv) - 1)
                    stretch = 1 + self.root_grade(board) * self.rules.num("灵根复查间隔加成") if self.root_bonus(board) else 1
                    st["next"] = (self.today + dt.timedelta(days=int(round(iv[st["stage"]] * stretch)))).isoformat()
                ev += self._award(self.rules.xp("复查通过"), mode, board, iid, True, f"{self.label(mode)}成功「{name}」")
            else:
                st.update(level=0, l1=0, l3=0, stage=-1, next=None, lap_check=False, rusty=True, example_ok=False)
                ev += self._award(self.rules.xp("复查未过"), mode, board, iid, False,
                                  f"「{name}」{self.T('rust')}，降回{self.level_names()[0]}")
            return ev
        if ok:
            base = self.rules.xp("默写通过")
            note = f"{self.T('recite')}成功「{name}」"
            if not st["passed_once"]:
                st["passed_once"] = True
                base += self.rules.xp("首次通过加成")
                note += "（首次）"
            if st["level"] == 0:
                st["l1"] += 1
                if st["l1"] >= self.rules.num("默写连续通过次数"):
                    st["level"], st["rusty"] = 1, False
                    ev.append({"kind": "info", "msg": f"「{name}」{self.level_names()[1]}，下一步：{self.T('feynman')}"})
            ev = self._award(base, "recite", board, iid, True, note) + ev
            ev.append(self._npc("默写通过"))
        else:
            if st["level"] == 0:
                st["l1"] = 0
            ev += self._award(self.rules.xp("默写未过"), "recite", board, iid, False, f"{self.T('recite')}失败「{name}」")
            ev.append(self._npc("默写未过"))
        return ev

    def on_feynman(self, iid, ok):
        st = self.item(iid)
        board, name = iid.split("::", 1)
        st["last"] = self.t
        ev = self._award(self.rules.xp("费曼通过" if ok else "费曼未过"), "feynman", board, iid, ok,
                         f"{self.T('feynman')}{'通过' if ok else '未过'}「{name}」")
        if ok and st["level"] == 1:
            st["level"] = 2
            ev.append({"kind": "info", "msg": f"「{name}」{self.level_names()[2]}，下一步：{self.T('example')}"})
        ev.append(self._npc("费曼通过" if ok else "费曼未过"))
        return ev

    def on_example(self, iid, ok):
        st = self.item(iid)
        board, name = iid.split("::", 1)
        st["last"] = self.t
        if ok:
            st["example_ok"] = True
        return self._award(self.rules.xp("举例通过" if ok else "举例未过"), "example", board, iid, ok,
                           "%s%s「%s」" % (self.T("example"), "通过" if ok else "未过", name))

    def _l3_progress(self, iid, ok):
        st = self.item(iid)
        if st["level"] != 2 or not st.get("example_ok"):
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
        return self._award(self.rules.xp("大项掌握"), "master", board, iid, True,
                           f"「{name}」{self.level_names()[3]}", bonus=False)

    def on_apply(self, iid, ok, progress=True):
        board, name = iid.split("::", 1)
        self.item(iid)["last"] = self.t
        self._heal_progress("apply", iid, ok)
        ev = self._award(self.rules.xp("应用通过" if ok else "应用未过"), "apply", board, iid, ok,
                         f"{self.T('apply')}{'成功' if ok else '失败'}「{name}」")
        return ev + (self._l3_progress(iid, ok) if progress else [])

    def on_wrong(self, key, board, ok, iid=""):
        """心魔（错题）结果。iid：AI 判断这题对应的一重功法（可为空），斩掉计入该重的试剑进度"""
        w = self.state["wrong"].setdefault(key, {"status": "new", "streak": 0, "tries": 0, "due": None})
        redo = w["status"] == "redo"
        w["tries"] += 1
        w["last"] = self.t
        if iid:
            w["item"] = iid
        self._heal_progress("wrong", key, ok)
        n, src, num = key.split("|")
        label = f"第{n}季{src}第{num}题"
        gap = int(self.rules.num("回炉间隔天数"))
        if ok:
            w["streak"] = w["streak"] + 1 if redo else 1
            if not redo or w["streak"] >= self.rules.num("回炉连续判对"):
                w["status"] = "done"
            else:
                w["due"] = (self.today + dt.timedelta(days=gap)).isoformat()
            base = self.rules.xp("错题判对") + (self.rules.xp("回炉判对加成") if redo else 0)
            ev = self._award(base, "wrong", board, iid, True, f"{self.T('kill')} {label}" + (f"（{self.T('redo')}）" if redo else ""))
            ev.append(self._npc("错题判对"))
        else:
            w.update(status="redo", streak=0, due=(self.today + dt.timedelta(days=gap)).isoformat())
            ev = self._award(self.rules.xp("错题判错"), "wrong", board, iid, False,
                             f"{self.T('wrong')}未斩 {label}，{gap} 天后{self.T('redo')}")
            ev.append(self._npc("错题判错"))
        if iid and self.find_item(iid):
            ev += self._l3_progress(iid, ok)
        return ev

    def on_alchemy(self, board, n_ok, n_total, xp_gained):
        rate = n_ok / n_total if n_total else 0
        grade = 2 if rate >= 0.8 else (1 if rate >= 0.5 else 0)
        pct = self.rules.nums("丹药加成")
        bonus_pct = pct[min(grade, len(pct) - 1)]
        pname = themes.BOARD_PILLS.get(self.theme, {}).get(board, board + self.T("pill"))
        gname = self.th["pill_grades"][grade]
        self.state["pills"].append({"d": self.t, "board": board, "name": pname, "grade": gname, "rate": round(rate, 2)})
        ev = [{"kind": "info", "msg": f"{self.T('alchemy')}完成：{gname}{pname}（成功 {n_ok}/{n_total}）"}]
        ev += self._award(max(1, int(round(xp_gained * bonus_pct))), "pill", board,
                          note=f"服下{gname}{pname}（+{bonus_pct:.0%}）", bonus=False)
        e = self._npc("成丹")
        e["extra"] = f"刚炼成并服下{gname}{pname}（{board}，成功 {n_ok}/{n_total}）"
        ev.append(e)
        return ev

    def use_leave(self):
        month = self.t[:7]
        used = [d for d in self.state["leave"] if d.startswith(month)]
        if self.t in self.state["leave"]:
            return False, f"今天已经用过{self.T('leave')}了"
        if len(used) >= self.rules.num("每月请假卡"):
            return False, f"本月 {len(used)} 份{self.T('leave')}已用完"
        self.state["leave"].append(self.t)
        return True, self.say("请假")

    def add_boss(self, name, score, kind="大比"):
        """宗门大比（模考）/ 飞升大典（国考）成绩"""
        self.state["boss"].append({"d": self.t, "name": name, "score": score, "kind": kind})
        if kind == "飞升":
            return self._award(self.rules.xp("飞升"), "ascend", note=f"{self.T('ascend')}「{name}」{score} 分", bonus=False)
        ev = self._award(self.rules.xp("模考录分"), "boss", note=f"{self.T('boss')}「{name}」{score} 分", bonus=False)
        e = self._npc("宗门大比")
        e["extra"] = f"刚记录了{self.T('boss')}成绩：{name} {score} 分"
        ev.append(e)
        # 大比悟道：最近两次中较低的那个高于当前道行 → 修为直接补到这个分数
        last2 = [b["score"] for b in self.contests()[-2:]]
        if len(last2) == 2:
            m = min(min(last2), self.rules.num("最高分数"))
            if m > self.raw_score():
                gain = int(math.ceil(self.xp_at(m) - self.state["xp"]))
                if gain > 0:
                    ev += self._award(gain, "insight", note=f"{self.T('boss')}悟道：{self.T('xp')}暴涨至 {m} 分", bonus=False)
        # 突破丹：成绩达到下一道渡劫线，奖励对应的突破丹（最多存 3 颗）
        nxt = next((g for g in self.gates() if g not in self.state["gates"]), None)
        item = self.th["gate_items"].get(nxt) if nxt else None
        if item and score >= nxt and self.state["bag"].get(item, 0) < 3:
            self.bag_add(item)
            ev.append({"kind": "info", "msg": f"{self.T('boss')}成绩达到 {nxt} 分，获得一颗{item}（{self.T('tribulation')}时可抵挡一道天雷）"})
        return ev

    def add_practice(self, board, total, correct, minutes, source="", note=""):
        rec = {"d": self.t, "board": board, "total": total, "correct": correct, "minutes": minutes}
        if source:
            rec["source"] = source
        if note:
            rec["note"] = note
        self.state["practice"].append(rec)
        self.state["seconds"][self.t] = self.state["seconds"].get(self.t, 0) + minutes * 60
        self._practice_log(rec)
        head = f"{self.T('practice')} {board}" + (f"（{source}）" if source else "")
        if not total:
            return [{"kind": "info", "msg": f"{head}：日志已记下"}]
        return self._award(self.rules.xp("自练每题") * total, "practice", board, note=f"{head} {correct}/{total}")

    def _practice_log(self, rec):
        """自练日志写进库里：训练/红尘历练/年-月.md，一次一节，Obsidian 里能直接看"""
        if not self.paths.train:
            return
        folder = self.paths.train / "红尘历练"
        folder.mkdir(parents=True, exist_ok=True)
        f = folder / f"{self.t[:7]}.md"
        bits = [rec["board"]] + ([rec["source"]] if rec.get("source") else [])
        if rec["total"]:
            bits.append(f"{rec['correct']}/{rec['total']}（{rec['correct'] / rec['total']:.0%}）")
        if rec["minutes"]:
            bits.append(f"{rec['minutes']} 分钟")
        text = f"\n## {self.t} {dt.datetime.now().strftime('%H:%M')} · " + " · ".join(bits) + "\n"
        if rec.get("note"):
            text += "\n" + rec["note"].strip() + "\n"
        if not f.exists():
            text = f"# 红尘历练 · {self.t[:7]}\n\n纸质资料、其他 App 上的自练记录（修仙录里录入）。\n" + text
        with f.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(text)

    def practice_list(self, n=12):
        return self.state["practice"][-n:][::-1]

    def add_seconds(self, sec):
        """网页心跳：累加今天的修炼时间；跨过达标 / 超额线时导师说话；连续修炼太久触发走火入魔"""
        before = self.minutes(self.t)
        self.state["seconds"][self.t] = self.state["seconds"].get(self.t, 0) + sec
        after = self.minutes(self.t)
        goal = self.rules.num("每日目标分钟")
        ev = []
        if before < goal <= after:
            ev.append(self._npc("今日达标"))
        elif before < goal * 1.5 <= after:
            ev.append(self._npc("今日超额"))
        now = time.time()
        run = self.state.get("run") or {}
        if not run or now - run.get("last", 0) > 20 * 60:
            run = {"start": now, "last": now}
        run["last"] = now
        limit = self.rules.num("走火入魔分钟") * 60
        if now - run["start"] >= limit:
            rest = self.rules.num("走火调息分钟")
            ev += self._rest(rest, f"已连续修炼 {int(limit / 60)} 分钟")
            run = {"start": now + rest * 60, "last": now + rest * 60}
        self.state["run"] = run
        return ev + self._retreat_check()

    # ================================================================ 导师台词
    def _npc(self, scene):
        return {"kind": "npc", "msg": self.say(scene), "scene": scene}

    def say(self, scene):
        info = self.realm_info()
        ide = self.ideal() if scene.startswith("开场") else {"diff_days": 0}
        return self.lines.pick(
            scene, 称呼=self.persona["称呼"], 导师名=self.persona["导师名"], 境界=info["name"],
            分数=info["score"], 落后天数=max(0, round(ide["diff_days"])), 领先天数=max(0, round(-ide["diff_days"])),
            缺席天数=self.days_absent(), 连续天数=self.streak()[0], 今日分钟=int(self.minutes(self.t)),
            目标分钟=self.rules.num("每日目标分钟"))

    def tutor_context(self):
        """给 AI 导师看的“弟子现状”。导师开场、突破、聊天时都带上它，让她说话有依据。"""
        T = self.T
        info = self.realm_info()
        ide = self.ideal()
        run, bonus = self.streak()
        yday = (self.today - dt.timedelta(days=1)).isoformat()
        cur = self.current_batch()
        plan = (self.state.get("plan") or {}).get("tasks", [])
        fails = [e["note"] for e in self.state["events"][-40:] if not e.get("ok")][-5:]
        wins = [e["note"] for e in self.state["events"][-40:] if e.get("ok") and e["type"] in TRAIN_TYPES][-3:]
        redo = sum(1 for w in self.state["wrong"].values() if w["status"] == "redo")
        boss = self.contests()[-2:]
        roots = [r for r in self.roots() if r["on"]]
        weak = sorted([r for r in self.roots() if r["acc"] is not None], key=lambda r: r["acc"])[:3]
        trib = self.tribulation_status()
        lines = [
            f"弟子：{self.persona['称呼']}（{self.persona['ID']}），{T('realm')}「{info['name']}」，{T('score')} {info['score']} 分"
            f"（目标 {info['target']} 分），累计{T('xp')} {self.state['xp']}。",
            (f"正处于瓶颈：要{T('tribulation')}才能进入{info['gate_realm']}；条件："
             + "；".join(f"{c['name']}{'✓' if c['ok'] else '✗'}（{c['text']}）" for c in trib["conds"])) if trib else "",
            f"{T('ideal')}：{'落后' if ide['diff_days'] > 0 else '领先'} {abs(ide['diff_days'])} 天（目标日 {ide['target']}）。",
            f"{T('streak')} {run} 天，加成 {bonus:.0%}；{T('dao')} {self.dao()}；今天之前已缺席 {self.days_absent()} 天。",
            f"今天已修炼 {int(self.minutes(self.t))} 分钟（目标 {self.rules.num('每日目标分钟')}），昨天 {int(self.minutes(yday))} 分钟。",
            f"{T('tasks')}完成 {sum(1 for t in plan if t['done'])}/{len(plan)}。",
            f"第 {self.state['lap']} 个{T('lap')}、第 {(cur or 0) + 1} {T('batch')}："
            f"{'、'.join(self.batch_boards(cur)) if cur is not None else '全部打通'}。",
            (f"已觉醒{T('root')}：" + "、".join(f"{r['name']}（{r['grade_name']}）" for r in roots)) if roots else f"还没有觉醒任何{T('root')}。",
            ("正确率最低的板块：" + "、".join(f"{r['board']} {r['acc']:.0%}" for r in weak)) if weak else "",
            f"{T('redo')}的{T('wrong')} {redo} 只。",
            ("最近失败：" + "；".join(fails)) if fails else "",
            ("最近成功：" + "；".join(wins)) if wins else "",
            (f"最近{T('boss')}：" + "；".join(f"{b['name']} {b['score']} 分" for b in boss)) if boss else "",
            (f"正在{T('retreat')}：{self.state['retreat']['board']}" if self.state.get("retreat") else ""),
        ]
        return "\n".join(x for x in lines if x)

    def mood(self):
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

    # ================================================================ 今日功课
    def _task(self, typ, board, title, target, optional=False, extra=None):
        t = {"id": f"{typ}:{target}", "type": typ, "board": board, "title": title, "target": target,
             "minutes": self.rules.minutes({"review": "复查", "speedrun": "复查", "recite": "默写",
                                            "feynman": "费曼", "example": "举例", "apply": "应用", "wrong": "错题",
                                            "skeleton": "骨架", "tribulation": "渡劫"}.get(typ, typ)),
             "done": False, "ok": None, "optional": optional}
        if extra:
            t.update(extra)
        return t

    def plan(self, force=False):
        p = self.state.get("plan")
        if p and p.get("date") == self.t and not force:
            for index, task in enumerate(p["tasks"]):
                st = self.state["items"].get(task.get("target"), {})
                if task["type"] == "apply" and not task.get("done") and st.get("level") == 2 and not st.get("example_ok"):
                    p["tasks"][index] = self._task("example", task["board"], self.T("example") + " · " + task["board"], task["target"])
            self._merge_wrong(p["tasks"])
            self._add_bank_tasks(p["tasks"])
            return p
        tasks, used = [], set()
        cur = self.current_batch()
        cur_boards = self.batch_boards(cur) if cur is not None else []

        # 1) 渡劫（条件全部满足时）
        tr = self.tribulation_status()
        if tr and tr["ready"]:
            tasks.append(self._task("tribulation", "", f"{self.T('tribulation')}：冲击{tr['realm']}（{tr['thunders']} 道天雷）",
                                    str(tr["gate"])))
        # 1b) 疗伤
        for t in self._heal_tasks():
            tasks.append(t)
            used.add(t["target"])

        # 2) 功法：当前秘境里还没定稿的板块
        for b in cur_boards:
            s = self.skel(b)
            if not s or not s["final"]:
                title = f"审阅「{b}」{self.T('skeleton')}草稿并定稿" if s else f"编撰「{b}」{self.T('skeleton')}（生成骨架）"
                tasks.append(self._task("skeleton", b, title, b))

        # 3) 温养（到期）+ 重温（新周天）
        due = []
        for b in self.boards:
            for it in self.final_items(b):
                st = self.state["items"].get(it["id"])
                if not st or st["level"] < 3 or it["id"] in used:
                    continue
                if st.get("lap_check") and b in cur_boards:
                    due.append((0, "speedrun", b, it))
                elif not st.get("lap_check") and st.get("next") and st["next"] <= self.t:
                    due.append((1, "review", b, it))
        for _, typ, b, it in sorted(due, key=lambda x: x[0])[: int(self.rules.num("每日复查上限"))]:
            tasks.append(self._task(typ, b, f"{self.label(typ)} · {b}「{it['name']}」", it["id"]))
            used.add(it["id"])

        # 4) 心魔
        tasks += self._plan_wrong(cur, cur_boards, used)

        # 5) 新修：当前秘境里有定稿功法的板块，按“最久没练”轮换
        ready = [b for b in cur_boards if self.final_items(b)]
        last = {b: max([e["d"] for e in self.state["events"] if e.get("board") == b] or [""]) for b in ready}
        chosen = sorted(ready, key=lambda b: last[b])[: int(self.rules.num("每日新学板块数"))]
        per = math.ceil(self.rules.num("每日新学大项") / len(chosen)) if chosen else 0
        for b in chosen:
            n = 0
            for it in self.final_items(b):
                st = self.item(it["id"])
                if st["level"] >= 3 or it["id"] in used or n >= per:
                    continue
                typ = ["recite", "feynman", "apply"][st["level"]]
                if typ == "apply" and not st.get("example_ok"):
                    typ = "example"
                tasks.append(self._task(typ, b, f"{self.label(typ)} · {b}「{it['name']}」", it["id"]))
                n += 1
                used.add(it["id"])

        self._add_bank_tasks(tasks)
        self.state["plan"] = {"date": self.t, "tasks": tasks}
        return self.state["plan"]

    def _add_bank_tasks(self, tasks):
        from . import question_bank
        # 旧日计划立即兼容新入口；保留已经完成的任务，不重复生成实战。
        data = question_bank.state(self)
        candidates = list(dict.fromkeys(t['board'] for t in tasks
                          if t['type'] in ('recite', 'review', 'speedrun', 'feynman', 'example', 'apply')))
        for b in candidates:
            if any(t['id'] == 'bank:' + b for t in tasks):
                for t in tasks:
                    if t['id'] == 'bank:' + b:
                        t['title'] = '%s · %s' % (self.T('bank'), b)
                continue
            qs, errors = question_bank.read(self.paths, b)
            remaining = [q for q in qs if q['key'] not in data['records']]
            completed = any(x['date'] == self.t and b in (x['board'], *x.get('boards', ())) and x['mode'] == 'new'
                            for x in data['groups'])
            if (errors or not remaining) and b not in data['runs'] and not completed:
                continue
            n = min(question_bank.count(self), len(remaining))
            if b in data['runs']:
                n = len(data['runs'][b]['questions'])
            task = self._task('bank', b, '%s · %s（顺序 %s 关）' % (self.T('bank'), b, n), b)
            task['minutes'] = n * max(0, self.rules.num('分钟.实战每题'))
            task['done'] = completed
            task['ok'] = True if completed else None
            ix = max(i for i, t in enumerate(tasks) if t['board'] == b
                     and t['type'] in ('recite', 'review', 'speedrun', 'feynman', 'example', 'apply'))
            tasks.insert(ix + 1, task)

    def _heal_tasks(self):
        out = []
        for h in self.state["trib"].get("heal", []):
            if h.get("done"):
                continue
            typ = h["kind"] if h["kind"] in ("recite", "apply", "wrong") else "recite"
            name = h["target"].split("::", 1)[-1] if typ != "wrong" else h["target"].replace("|", " ")
            out.append(self._task(typ, h.get("board", ""), f"{self.T('heal')} · {self.label(typ)}「{name}」", h["target"]))
        return out

    def _plan_wrong(self, cur, cur_boards, used=()):
        r = self.rules
        last_n = int(r.num("错题只取最近几季"))
        order = list(cur_boards)
        if cur is not None:
            for i in range(cur):
                order += [b for b in self.batch_boards(i) if b not in order]
        redo, fresh_cur, fresh_old = [], [], []
        for b in order:
            for q in vault.wrong_questions(self.paths, self.sources(b), last_n):
                w = self.state["wrong"].get(q["key"])
                if w and w["status"] == "redo" and (w.get("due") or "") <= self.t:
                    redo.append((b, q))
                elif not w or w["status"] == "new":
                    (fresh_cur if b in cur_boards else fresh_old).append((b, q))
        lo, hi = int(r.num("每日错题下限")), int(r.num("每日错题上限"))
        key = f"{self.state['lap']}-{(cur or 0) + 1}"
        started = D(self.state.get("batch_start", {}).get(key, self.t))
        days_left = max(3, int(r.num("每批预计天数")) - (self.today - started).days)
        quota = max(lo, min(hi, len(redo) + math.ceil(len(fresh_cur) / days_left)))
        picked = [(b, q["key"]) for b, q in (redo + fresh_cur + fresh_old) if q["key"] not in used][:quota]
        if not picked:
            return []
        t = self._task("wrong", "", "", DAILY_WRONG.split(":", 1)[1],
                       extra={"quota": len(picked), "keys": [list(x) for x in picked], "hits": [], "redo": len(redo)})
        t["minutes"] *= len(picked)
        self._wrong_title(t)
        return [t]

    # 今日功课和心魔录共用的那一项“斩心魔”：一天一只任务，按只数计进度
    def _wrong_title(self, t):
        n, k = t["quota"], len(t["hits"])
        t["title"] = f"{self.T('kill')} · 今日 {min(k, n)}/{n} 只" + (f"（含{self.T('redo')} {t['redo']}）" if t.get("redo") else "")

    def daily_wrong(self):
        p = self.state.get("plan") or {}
        if p.get("date") != self.t:
            return None
        return next((t for t in p.get("tasks", []) if t["id"] == DAILY_WRONG), None)

    def next_wrong(self, board=""):
        """下一只该斩的心魔 (board, key)：先按今日功课排好的顺序，再到所有板块里挑（到期回炉 > 没交手 > 其余）"""
        t = self.daily_wrong()
        if t and not board:
            for b, key in t["keys"]:
                if key not in t["hits"]:
                    return b, key
        hits = set(t["hits"]) if t else set()
        allq = sorted(self._pool_wrong([board] if board else list(self.boards)))
        pool = [x for x in allq if x[2] not in hits] or allq       # 今天都斩过了：再从头来
        return (pool[0][1], pool[0][2]) if pool else None

    def wrong_hit(self, key, ok):
        """斩过一只（不论从哪进来的）：今日的斩心魔任务进度 +1，够数就算完成"""
        t = self.daily_wrong()
        if not t or key in t["hits"]:
            return
        t["hits"].append(key)
        t["ok"] = ok if t["ok"] is None else (t["ok"] and ok)
        if len(t["hits"]) >= t["quota"]:
            t["done"] = True
        self._wrong_title(t)

    def _merge_wrong(self, tasks):
        """旧计划里一只心魔一项：合成一项（已经斩过的算进度）"""
        heal = self.T("heal")
        old = [t for t in tasks if t["type"] == "wrong" and t["id"] != DAILY_WRONG and not t["title"].startswith(heal)]
        if not old:
            return
        ix = tasks.index(old[0])
        t = self._task("wrong", "", "", DAILY_WRONG.split(":", 1)[1],
                       extra={"quota": len(old), "keys": [[x["board"], x["target"]] for x in old],
                              "hits": [x["target"] for x in old if x["done"]], "redo": sum(self.T("redo") in x["title"] for x in old)})
        t["minutes"] = sum(x["minutes"] for x in old)
        t["done"] = all(x["done"] for x in old)
        self._wrong_title(t)
        tasks[ix:ix] = [t]
        for x in old:
            tasks.remove(x)

    def mark_done(self, task, ok):
        tid = task.get("id") or f"{task.get('type')}:{task.get('target')}"
        if tid == DAILY_WRONG:          # 按只数算，见 wrong_hit
            return
        for t in (self.state.get("plan") or {}).get("tasks", []):
            if t["id"] == tid and not t["done"]:
                t["done"], t["ok"] = True, ok
                return

    # ================================================================ 面板
    def dashboard(self):
        from . import question_bank
        info = self.realm_info()
        run, bonus = self.streak()
        cur = self.current_batch()
        roots = {r["board"]: r for r in self.roots()}
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
                    "acc": self.accuracy(b), "root": roots.get(b),
                })
        side = [{"board": k, "target": v, "acc": self.accuracy(k), "root": roots.get(k)} for k, v in self.rules.side.items()]
        demon = sorted([r for r in roots.values() if r["acc"] is not None], key=lambda r: r["acc"])
        scene = self.mood()
        dao = self.dao()
        retreat = self.state.get("retreat")
        return {
            "tower": question_bank.tower(self),
            "today": self.t, "theme": {"name": self.theme, "terms": self.th["terms"],
                                       "levels": self.level_names(), "face": self.th["tutor_face"]},
            "realm": info, "xp": self.state["xp"],
            "streak": {"days": run, "bonus": bonus}, "dao": {"value": dao, "label": self.dao_label(dao)},
            "ideal": self.ideal(), "lap": self.state["lap"],
            "batch": {"index": (cur + 1) if cur is not None else None,
                      "boards": self.batch_boards(cur) if cur is not None else [], "count": len(self.rules.batches)},
            "forecast": self.lap_forecast(),
            "tree": tree, "side": side, "roots": list(roots.values()), "demon": demon,
            "redo": sum(1 for w in self.state["wrong"].values() if w["status"] == "redo"),
            "trib": self.tribulation_status(), "bag": self.bag_view(), "weekly": self.weekly(),
            "retreat": ({"board": retreat["board"], "end": retreat["end"], "minutes": retreat["minutes"]}
                        if retreat and time.time() < retreat["end"] else None),
            "rest": self.resting(),
            "lectures": [x for x in self.state.setdefault("lectures", []) if x["d"] >= (self.today - dt.timedelta(days=6)).isoformat()][::-1],
            "minutes": {"today": int(self.minutes(self.t)), "goal": self.rules.num("每日目标分钟"),
                        "study": int(self.study_minutes(self.t)), "lecture": int(self.lecture_minutes(self.t)),
                        "floor": self.rules.num("保底分钟")},
            "leave": {"used": len([d for d in self.state["leave"] if d.startswith(self.t[:7])]),
                      "total": self.rules.num("每月请假卡"), "today": self.t in self.state["leave"]},
            "boss": self.contests()[-6:], "ascend": self.contests("飞升"),
            "pills": self.state["pills"][-5:][::-1],
            "pill_boards": [b for b in self.boards if self.final_items(b) or vault.wrong_questions(self.paths, self.sources(b))],
            "greeting": self.say(scene), "scene": scene,
            "recent": self.state["events"][-12:][::-1],
            "practice": self.practice_list(),
        }

