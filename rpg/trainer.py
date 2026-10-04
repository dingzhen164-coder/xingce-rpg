"""
训练会话：网页上一次“点功课 → 对话 → 出结果”的流程。界面说法随风格变（g.T("键")，见 themes.py）。

会话类型（session["type"]）：
    recite    背诵口诀（默写）         review / speedrun  温养道基 / 重温功法（也是默写）
    feynman   论道（费曼，多轮追问）    apply     试剑（AI 出应用小题 → 学员答 → AI 判）
    wrong     斩心魔（错题判断）
    tribulation  渡劫：连续闯几道天雷（心法雷=背诵、心魔雷=错题、问道雷=应用题、紫霄神雷=最弱灵根的心魔），失败一道就结束
    alchemy      炼丹：选一个板块加练一炉（背诵 + 心魔），按成功率成丹，额外修为
    skeleton  生成 / 定稿功法（骨架）   chat      和导师聊天

每个函数返回给网页的统一结构（api.py 原样转成 JSON）：
    {"session": id, "type": 类型, "title": 标题,
     "messages": [{"who": "npc"|"sys"|"me", "text": 文字, "blocks": [题目块], "fold": 折叠标题}],
     "events":   engine 返回的事件（+修为 / 境界 / 导师台词）,
     "input":    {"mode": "text"|"buttons"|"none", "placeholder": 提示, "buttons": [{"id", "label"}]},
     "finished": 是否结束}

没填 API key 时：背诵 / 温养 / 心魔 退化为“自评模式”（学员对照清单与思路判断含义）；论道 / 试剑 / 生成功法必须有 AI；
渡劫里的问道雷没有 AI 时换成心法雷。会话只存在内存里，结果在出结果那一刻就写进存档。
"""
import re
import time
import uuid
from pathlib import Path

from . import question_bank, ai, idioms, prompts, skeleton, tutor, vault

SESSIONS = {}
FINISHED = {}   # 刚结束的会话 {id: (类型, 结束时间)}：结束后看解析的几分钟也算修炼时间
STUDY_TYPES = ("teach", "recite", "review", "speedrun", "feynman", "example", "apply", "wrong", "tribulation", "alchemy", "bank", "bank_review",
               "mock_review")
REVIEW_GRACE = 180  # 秒


PRACTICE_TYPES = ("bank", "bank_review", "wrong", "apply", "tribulation", "alchemy")   # 计入“做题”，其余修炼计入“复习”（大比复盘 mock_review 也算复习）


def study_kind(sid):
    s = SESSIONS.get(sid or "")
    typ = s["type"] if s else FINISHED.get(sid or "", ("", 0))[0]
    return "practice" if typ in PRACTICE_TYPES else "review"


LAST_BOARD = {}   # 会话 → 最近一次心跳时在练的模块（结束后看解析的几分钟也记到它）


def study_board(g, sid):
    """这个会话在练哪个模块（板块）：知识点试炼 点:板块:考点 → 板块；整套试炼按当前这道题的板块；不认识的返回空"""
    s = SESSIONS.get(sid or "")
    if not s:
        return LAST_BOARD.get(sid or "", "")
    b = s.get("board") or (s.get("task") or {}).get("board") or ""
    if b.startswith(question_bank.POINT_PREFIX):
        b = b[len(question_bank.POINT_PREFIX):].split(":", 1)[0]
    elif b.startswith(question_bank.SET_PREFIX):
        run = question_bank.state(g)["runs"].get(b) or {}
        qs = run.get("questions") or []
        b = qs[min(run.get("pos", 0), len(qs) - 1)]["board"] if qs else ""
    b = b if b in question_bank.boards(g) else ""
    if len(LAST_BOARD) > 300:
        LAST_BOARD.clear()
    LAST_BOARD[sid] = b
    return b


def is_studying(sid):
    """这个会话是否在“修炼”：正在进行的功课，或刚结束 3 分钟内（在看解析）。闲聊、编撰功法不算。"""
    s = SESSIONS.get(sid or "")
    if s:
        return s["type"] in STUDY_TYPES
    typ, t = FINISHED.get(sid or "", ("", 0))
    return typ in STUDY_TYPES and time.time() - t < REVIEW_GRACE
TIRED_WORDS = ("累", "不想学", "学不动", "好烦", "烦死", "崩溃", "坚持不下去", "想放弃", "太难了", "不想练")
RESULT_SCENES = {"默写通过", "默写未过", "费曼通过", "费曼未过", "错题判对", "错题判错"}


class TrainError(Exception):
    pass


# ---------------------------------------------------------------- 小工具
def _msg(who, text, blocks=None, fold=None):
    m = {"who": who, "text": text}
    if blocks:
        m["blocks"] = blocks
    if fold:
        m["fold"] = fold
    return m


def _resp(s, messages, events=None, input=None, finished=False):
    if finished:
        SESSIONS.pop(s["id"], None)
        FINISHED[s["id"]] = (s["type"], time.time())
    return {"session": s["id"], "type": s["type"], "title": s["title"], "messages": messages,
            "events": events or [], "input": input or {"mode": "none"}, "finished": finished}


def _text_input(ph):
    return {"mode": "text", "placeholder": ph}


def _buttons(*pairs):
    return {"mode": "buttons", "buttons": [{"id": i, "label": l} for i, l in pairs]}


def _remember(s, inp):
    s["last_input"] = inp
    return inp


def _need_ai(what):
    if not ai.available():
        raise TrainError(f"{what}需要 AI：请先在“设置”里填写 API key")


def _item(g, iid):
    it = g.find_item(iid)
    if not it:
        raise TrainError(f"{g.T('skeleton')}里找不到这一{g.T('item')}（可能改过标题或还没定稿），请回首页点“重新生成{g.T('tasks')}”")
    return it


def _drop_dup_npc(ev, comment):
    """AI 已经给了点评时，去掉台词库里的“结果类”台词，避免导师连说两句"""
    if not comment:
        return ev
    return [e for e in ev if not (e.get("kind") == "npc" and e.get("scene") in RESULT_SCENES)]


def _xp_of(ev):
    return sum(e["v"] for e in ev if e.get("kind") == "xp")


def is_tired(text):
    t = text.strip()
    return len(t) <= 20 and any(w in t for w in TIRED_WORDS)


def tired_response(g, s, text):
    """学员说累了：导师先安慰，会话保持原样，可以继续答题"""
    try:
        reply = ai.chat(prompts.tired_reply(g.persona, text, int(g.minutes(g.t)), g.rules.num("每日目标分钟")),
                        temperature=0.8, max_tokens=300) if ai.available() else g.say("累了")
    except ai.AIError:
        reply = g.say("累了")
    return _resp(s, [_msg("npc", reply),
                     _msg("sys", f"缓一缓再继续；想休息也可以去“{g.T('nav.log')[2:]}”用{g.T('leave')}，或者直接关掉——今天修炼够保底分钟，"
                                 f"{g.T('streak')}就不会断。")],
                 input=s.get("last_input") or _text_input(""))


ALL = {}        # 所有会话（含已结束的，最多留 200 个）：写修炼记录用


def new_session(typ, title, task, **data):
    s = {"id": uuid.uuid4().hex[:12], "type": typ, "title": title, "task": task, **data}
    SESSIONS[s["id"]] = s
    ALL[s["id"]] = s
    while len(ALL) > 200:
        ALL.pop(next(iter(ALL)))
    return s


def get(sid):
    s = SESSIONS.get(sid)
    if not s:
        raise TrainError("这次修炼已经结束或程序重启过，请从功课列表重新开始")
    return s


def _recite_prompt(g, board, it, head):
    return (f"{head}：{board}「{it['name']}」。凭记忆写出这一{g.T('item')}的全部内容——"
            + (f"{g.T('term')}（【口诀】）共 {len(it['verses'])} 句，必须一字不差；" if it.get("verses") else "")
            + (f"列全分类清单（共 {len(it['terms'])} 个），" if it["terms"] else "")
            + f"再用自己的话讲思路（共 {len(it['thoughts'])} 条）。允许同义表达与不同顺序，含义要对应，不能混淆上位分类和下位方法。")


def _wrong_intro(g, q, head):
    return _msg("sys", f"{head}第{q['season']}季 · {q['source']} · 第{q['num']}题（上次你选了 {q['mine'] or '未作答'}）",
                blocks=vault.render_blocks(g.paths, q))


# ---------------------------------------------------------------- 开始
# ---------------------------------------------------------------- 修炼记录：大项的每次对话存进 训练/修炼记录/<板块>/<大项>.md
LOG_DIR = "修炼记录"
LOG_TYPES = ("teach", "recite", "review", "speedrun", "feynman", "example", "apply")
_LOG_HEAD = re.compile(r"^## (.+?) <!-- sid:(\w+) -->[ \t]*$", re.M)


def _log_file(g, iid):
    board, _, name = iid.partition("::")
    safe = lambda x: re.sub(r'[\\/:*?"<>|]+', "_", x).strip() or "_"
    return g.paths.train / LOG_DIR / safe(board) / (safe(name) + ".md") if g.paths.train else None


def _msg_text(m):
    """记进修炼记录的文字：师傅和自己说的话全记；系统消息只记标题行（例题只留“例题 1（真题-xxx）”，题干去玉简里查）"""
    if m.get("who") == "sys":
        return (m.get("text") or "").strip()
    parts = [m.get("text") or ""] + [b["v"] for b in m.get("blocks", []) if b.get("t") == "text"]
    return "\n".join(p for p in parts if p.strip()).strip()


def _log(g, sid, user_text, r):
    """把这次对话（含刚说的话和这一轮的回复）写进这个大项的修炼记录；同一次会话反复覆盖自己那一段"""
    s = ALL.get(sid)
    if not s or s["type"] not in LOG_TYPES or not s.get("iid"):
        return
    log = s.setdefault("log", [])
    if user_text:
        log.append(("me", user_text))
    for m in r.get("messages", []):
        if m.get("history") or m.get("fold"):     # 往期记录、折叠的答案解析不重复记
            continue
        t = _msg_text(m)
        if t:
            log.append((m.get("who", "sys"), t))
    f = _log_file(g, s["iid"])
    if not f:
        return
    who = {"me": "🧑 我", "npc": "🌸 " + g.persona["导师名"]}
    body = "\n\n".join("**%s**：\n%s" % (who[w], t) if w in who else "> " + t.replace("\n", "\n> ") for w, t in log)
    sid = s.get("log_sid", sid)       # 接着上次聊的：写回上次那一段
    head = "## %s · %s <!-- sid:%s -->" % (s.setdefault("started", time.strftime("%Y-%m-%d %H:%M")), g.label(s["type"]), sid)
    try:
        old = f.read_text(encoding="utf-8") if f.is_file() else "# %s · 修炼记录\n\n> 每次传授、背诵口诀、论道、化法为境、试剑的对话都记在这里，新的在下面。\n" % s["iid"].replace("::", " · ")
        m = re.search(r"^## .+? <!-- sid:%s -->[ \t]*$" % sid, old, re.M)
        if m:
            nxt = _LOG_HEAD.search(old, m.end())
            old = old[:m.start()] + head + "\n\n" + body + "\n\n" + (old[nxt.start():] if nxt else "")
        else:
            old = old.rstrip("\n") + "\n\n" + head + "\n\n" + body + "\n"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(old.rstrip("\n") + "\n", encoding="utf-8", newline="\n")
    except OSError:
        pass


def _past_logs(g, iid, sid, n=5):
    """这个大项以前的修炼记录（最近 n 次，不含这一次），做成折叠消息放在对话最上面"""
    f = _log_file(g, iid)
    if not f or not f.is_file():
        return []
    text = f.read_text(encoding="utf-8")
    heads = list(_LOG_HEAD.finditer(text))
    out = []
    for i, h in enumerate(heads):
        if h.group(2) == sid:
            continue
        body = text[h.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)].strip()
        body = re.sub(r"^> ?", "", body, flags=re.M)
        out.append({"who": "sys", "text": body, "fold": "📜 往期修炼 · " + h.group(1), "history": True})
    return out[-n:]


def _parse_log(body):
    """修炼记录里的一段 → [(who, text)]；who 是 me / npc / sys（系统消息记成连续的 > 行）"""
    out, prev_blank = [], True
    for ln in body.splitlines():
        h = re.match(r"^\*\*(🧑 我|🌸 [^*]+)\*\*：\s*$", ln)
        if h:
            out.append(["me" if h.group(1).startswith("🧑") else "npc", ""])
        elif ln.startswith(">"):
            if not out or out[-1][0] != "sys" or prev_blank:
                out.append(["sys", ""])
            out[-1][1] += re.sub(r"^> ?", "", ln) + "\n"
        elif out:
            out[-1][1] += ln + "\n"
        prev_blank = not ln.strip()
    return [(w, t.strip()) for w, t in out if t.strip()]


def _last_log(g, iid, label):
    """这个大项上一次同类练习的记录：(sid, 时间, [(who, text)])；没有就 None"""
    f = _log_file(g, iid)
    if not f or not f.is_file():
        return None
    text = f.read_text(encoding="utf-8")
    heads = [h for h in _LOG_HEAD.finditer(text) if h.group(1).endswith("· " + label)]
    if not heads:
        return None
    h = heads[-1]
    nxt = _LOG_HEAD.search(text, h.end())
    entries = _parse_log(text[h.end():nxt.start() if nxt else len(text)])
    return (h.group(2), h.group(1).rsplit(" · ", 1)[0], entries) if entries else None


def _resume(g, task, last):
    """接着上次的对话：把上次的对话原样摆出来，进入可以接着问师傅的状态；也可以点“重新开始”"""
    old_sid, when, entries = last
    it = _item(g, task["target"])
    label = g.label(task["type"])
    s = new_session(task["type"], task.get("title") or label, task, iid=it["id"], board=task["board"],
                    resumed=label, log_sid=old_sid, started=when, log=list(entries))
    content = "\n".join(["【口诀】" + v for v in it.get("verses", [])] + ["【术语】" + t for t in it.get("terms", [])]
                        + ["【思路】" + t for t in it.get("thoughts", [])])
    history = [{"role": "user" if w == "me" else "assistant", "content": t} for w, t in entries if w in ("me", "npc")][-12:]
    s["discuss"] = {"kind": label, "title": it["name"], "board": task["board"], "history": history,
                    "question": "大项「%s」的内容：\n%s" % (it["name"], content), "mine": "（接着上次的%s聊）" % label, "reference": ""}
    msgs = [dict(_msg("sys", "📜 接着 %s 那次%s继续。想从头来就点「🆕 重新开始%s」。" % (when, label, label)), history=True)]
    msgs += [{"who": w, "text": t, "history": True} for w, t in entries]
    return _resp(s, msgs, input=_remember(s, _discuss_input(task["type"] == "teach", label)))


def start(g, task):
    if task.get("type") in LOG_TYPES and task.get("target") and not task.get("fresh"):
        try:
            last = _last_log(g, task["target"], g.label(task["type"]))
        except OSError:
            last = None
        if last:
            if g.resting():
                raise TrainError(f"{g.T('qi')}预警：还需调息 {g.resting()} 分钟。去喝口水、走两步，回来再修炼。")
            return _resume(g, task, last)
    r = _start(g, task)
    s = ALL.get(r.get("session"))
    if s and s["type"] in LOG_TYPES and s.get("iid"):
        _log(g, s["id"], "", r)
        past = _past_logs(g, s["iid"], s["id"])
        if past:
            r["messages"] = past + [_msg("sys", "↑ 以上是这一项以前的修炼记录（点开看），下面是这一次。")] + r["messages"]
    return r


def reply(g, sid, text):
    r = _reply(g, sid, text)
    _log(g, sid, (text or "").strip(), r)
    return r


def action(g, sid, act):
    r = _action(g, sid, act)
    _log(g, sid, "", r)
    return r


def _start(g, task):
    """task：今日功课里的一项（dict），或临时构造的 {"type","board","target","title","id"}"""
    typ = task["type"]
    if typ not in ("chat", "skeleton") and g.resting():
        raise TrainError(f"{g.T('qi')}预警：还需调息 {g.resting()} 分钟。去喝口水、走两步，回来再修炼。")
    if typ in ("bank", "bank_review"):
        return _start_bank(g, task)
    if typ == "mock_review":
        return _start_mreview(g, task)
    if typ == "teach":
        return _start_teach(g, task)
    if typ in ("recite", "review", "speedrun"):
        it = _item(g, task["target"])
        s = new_session(typ, task["title"], task, iid=it["id"], board=task["board"])
        return _resp(s, [_msg("npc", _recite_prompt(g, task["board"], it, g.label(typ)))],
                     input=_remember(s, _text_input("凭记忆写出全部内容，写完按 Ctrl+Enter 提交")))
    if typ == "feynman":
        _need_ai(g.T("feynman"))
        it = _item(g, task["target"])
        s = new_session(typ, task["title"], task, iid=it["id"], board=task["board"], history=[], asked=0)
        return _resp(s, [_msg("npc", f"{g.T('feynman')}。把「{it['name']}」讲给{g.persona['导师名']}听：它是什么、题目里怎么认出来、"
                                     "怎么用、容易错在哪。就当对方完全不懂。")],
                     input=_remember(s, _text_input("像给别人讲课一样讲出来")))
    if typ == "example":
        _need_ai(g.T("example"))
        it = _item(g, task["target"])
        s = new_session(typ, task["title"], task, iid=it["id"], board=task["board"])
        task_text = "；".join(it.get("examples", [])) or "自行编情境、论据、结论和选项，解释方法如何起作用；含多个类别时分别举例。"
        return _resp(s, [_msg("npc", "「%s」：%s 不要求照抄原文，要让例子体现具体机制。" % (it["name"], task_text))],
                     input=_remember(s, _text_input("自己的例子 → 方法 → 为什么成立 → 易混区别")))
    if typ == "apply":
        _need_ai(g.T("apply"))
        it = _item(g, task["target"])
        q = ai.chat_json(prompts.apply_question(g.persona, task["board"], it), temperature=0.7)
        s = new_session(typ, task["title"], task, iid=it["id"], board=task["board"], q=q)
        return _resp(s, [_msg("npc", f"{g.T('apply')}：\n\n{q.get('题目', '')}")],
                     input=_remember(s, _text_input("先说你认出的考点和思路，再给答案")))
    if typ == "wrong":
        origin = {k: task.get(k) for k in ("id", "type", "board", "target", "title")}
        if task.get("target") in ("", None, "daily"):
            # 斩心魔（今日功课/心魔录/修炼殿共用）：挑下一只最该斩的（今日排好的 > 到期回炉 > 没交手过 > 其余）
            nxt = g.next_wrong(task.get("board") or "")
            if not nxt:
                where = f"「{task['board']}」" if task.get("board") else ""
                raise TrainError(f"{where}还没有{g.T('wrong')}（模考板块复盘里做错的题）")
            task = dict(task, board=nxt[0], target=nxt[1])
            daily = g.daily_wrong()
            if daily:
                task["title"] = daily["title"] if origin["id"] == "wrong:daily" else task["title"]
        q = vault.find_question(g.paths, task["target"])
        if not q:
            raise TrainError("找不到这道题（复盘文件可能改名或删除了）")
        s = new_session(typ, task["title"], task, key=q["key"], board=task["board"], origin=origin)
        return _resp(s, [_wrong_intro(g, q, f"{g.T('wrong')}现身！"),
                         _msg("npc", f"用{g.T('skeleton')}里的方法{g.T('kill')}：这是什么题型 → 用什么方法 → 关键依据落在哪句话 → 选哪个。")],
                     input=_remember(s, _text_input("题型 → 方法 → 依据 → 答案")))
    if typ in ("tribulation", "alchemy"):
        return _start_gauntlet(g, task)
    if typ == "skeleton":
        return _start_skeleton(g, task)
    if typ == "chat":
        s = new_session("chat", task.get("title") or g.T("tutor_room"), task, history=[])
        return _resp(s, [_msg("npc", tutor.cached_greeting(g) or g.say(g.mood()) or "说吧，什么事？")],
                     input=_remember(s, _text_input("问方法、让导师帮你排计划、或者只是聊两句")))
    raise TrainError(f"未知的功课类型：{typ}")


# ---------------------------------------------------------------- 回复 / 按钮
def _reply(g, sid, text):
    s = get(sid)
    text = (text or "").strip()
    if not text:
        raise TrainError("内容是空的")
    if is_tired(text):
        return tired_response(g, s, text)
    if s.get("discuss"):
        return _discuss_reply(g, s, text)
    typ = s["type"]
    if typ == "mock_review":
        return _mreview_chat(g, s, text)
    if typ in ("recite", "review", "speedrun"):
        return _grade_recite(g, s, text)
    if typ in ("tribulation", "alchemy"):
        return _gauntlet_answer(g, s, text)
    if typ == "feynman":
        return _feynman(g, s, text)
    if typ == "example":
        return _example(g, s, text)
    if typ in ("bank", "bank_review"):
        return _bank_reply(g, s, text)
    if typ == "apply":
        return _apply(g, s, text)
    if typ == "wrong":
        return _wrong(g, s, text)
    if typ == "chat":
        return _chat(g, s, text)
    raise TrainError("这一步不需要输入文字，请点按钮")


def _action(g, sid, act):
    """按钮：自评（self_ok / self_no）、功法（gen / final）、跳过（skip）"""
    s = get(sid)
    if s["type"] in ("bank", "bank_review"):
        return _bank_action(g, s, act)
    if s["type"] == "mock_review":
        return _mreview_action(g, s, act)
    if s.get("discuss"):
        return _discuss_action(g, s, act)
    if act == "skip":
        if s["type"] == "tribulation":
            raise TrainError(f"{g.T('tribulation')}开始后不能跳过")
        return _resp(s, [_msg("sys", "已跳过，这项功课留在列表里。")], finished=True)
    if s["type"] == "skeleton":
        return _skeleton_action(g, s, act)
    if act in ("self_ok", "self_no") and s.get("pending"):
        ok = act == "self_ok"
        p = s.pop("pending")
        if s["type"] in ("tribulation", "alchemy"):
            return _gauntlet_step_done(g, s, ok and not p.get("miss") and p.get("answer_ok", True), [], "")
        if s["type"] == "wrong":
            return _wrong_finish(g, s, ok and p.get("answer_ok", True), "", [])
        it = _item(g, s["iid"])
        vmiss = [m for m in p.get("miss", []) if m.startswith("口诀：")]  # 口诀已由程序逐字比对，自评改不了
        return _recite_finish(g, s, it["terms"] if ok else [], vmiss + ([] if ok else it["terms"]), None, ok,
                              "自评结果（未由AI验证）")
    raise TrainError("未知操作")


# ---------------------------------------------------------------- 背诵口诀（默写）
def _judge_recite(g, board, it, text):
    """返回 (hit, miss, coverage 或 None(需要自评), 点评, 错误说法)。
    【术语】由 AI 按含义判断；【口诀】（it["verses"]）由程序逐字比对，漏一句就算没过（口诀要背原句）"""
    vhit, vmiss = skeleton.check_verses(it, text)
    vhit, vmiss = ["口诀：" + v for v in vhit], ["口诀：" + v for v in vmiss]
    if not ai.available():
        # 字面查找仅作对照建议，不能据此否定同义表达（口诀除外：口诀本来就要求原句）。
        return vhit, vmiss, None, "", []
    if not it["terms"] and not it["thoughts"]:
        return vhit, vmiss, 1.0, "", []
    r = ai.chat_json(prompts.recite_grade(g.persona, board, it, text, []))
    names = r.get("清单")
    marks = r.get("答到")
    if (not isinstance(names, list) or len(names) != len(it["terms"])
            or not isinstance(marks, list) or len(marks) != len(it["thoughts"])
            or any(type(x) is not bool for x in names + marks)
            or not isinstance(r.get("错误说法"), list)):
        raise TrainError("AI判分格式不完整，尚未记录结果，请重试")
    hit = [name for name, yes in zip(it["terms"], names) if yes] + vhit
    miss = [name for name, yes in zip(it["terms"], names) if not yes] + vmiss
    cov = sum(marks) / len(marks) if marks else 1.0
    return hit, miss, cov, r.get("点评", ""), r["错误说法"]



def _recite_summary(g, it, hit, miss, cov, wrong_says):
    lines = []
    vmiss = [m[3:] for m in miss if m.startswith("口诀：")]
    if it.get("verses"):
        n = len(it["verses"])
        lines.append(f"{g.T('term')}（逐字比对）{n - len(vmiss)}/{n}" + (f"，漏 / 错：{'、'.join(vmiss)}" if vmiss else "，全对 ✓"))
    if cov is None:
        return "\n".join(lines + ["未连接AI：请对照完整清单与思路自行核对含义，不作字面判分。"])
    tmiss = [m for m in miss if not m.startswith("口诀：")]
    if it["terms"]:
        lines.append(f"分类含义对应 {len(it['terms']) - len(tmiss)}/{len(it['terms'])}"
                     + (f"，漏 / 错：{'、'.join(tmiss)}" if tmiss else "，全对 ✓"))
    if cov is not None and it["thoughts"]:
        lines.append(f"思路要点覆盖 {cov:.0%}")
    if wrong_says:
        lines.append("说错的地方：" + "；".join(wrong_says))
    return "\n".join(lines)


def _self_rate_buttons():
    return _buttons(("self_ok", "清单完整、含义正确（自评）"), ("self_no", "有明显遗漏"))


def _grade_recite(g, s, text):
    it = _item(g, s["iid"])
    hit, miss, cov, comment, wrong_says = _judge_recite(g, s["board"], it, text)
    if cov is None:
        s["pending"] = {"hit": hit, "miss": miss}
        return _resp(s, [_msg("sys", _recite_summary(g, it, hit, miss, None, [])),
                         _msg("sys", it["text"], fold=f"{g.T('skeleton')}原文"),
                         _msg("npc", "没连 AI，请对照清单和思路自评：是否列全、含义对应且无错误？不会按字面匹配判失败。")], input=_self_rate_buttons())
    return _recite_finish(g, s, hit, miss, cov, None, comment, wrong_says)


def _recite_finish(g, s, hit, miss, cov, self_ok, comment, wrong_says=()):
    it = _item(g, s["iid"])
    verse_ok = not any(m.startswith("口诀：") for m in miss)
    ok = not wrong_says and verse_ok and (bool(self_ok) if cov is None else not miss and cov >= g.rules.num("思路达标比例"))
    ev = _drop_dup_npc(g.on_recite(s["iid"], ok, s["type"]), comment)
    g.mark_done(s["task"], ok)
    msgs = [_msg("sys", (f"✨ {g.label(s['type'])}成功\n" if ok else f"💥 {g.label(s['type'])}失败\n")
                 + _recite_summary(g, it, hit, miss, cov, list(wrong_says)))]
    if comment:
        msgs.append(_msg("npc", comment))
    msgs.append(_msg("sys", it["text"], fold=f"{g.T('skeleton')}原文"))
    return _resp(s, msgs, ev, finished=True)


# ---------------------------------------------------------------- 论道（费曼）
def _feynman(g, s, text):
    it = _item(g, s["iid"])
    s["history"].append({"role": "user", "content": text})
    left = max(0, int(g.rules.num("费曼追问轮数")) - s["asked"])
    r = ai.chat_json(prompts.feynman_turn(g.persona, s["board"], it, s["history"], left), temperature=0.5)
    reply_text = r.get("reply", "")
    s["history"].append({"role": "assistant", "content": reply_text})
    if not bool(r.get("done")) and left > 0:
        s["asked"] += 1
        return _resp(s, [_msg("npc", reply_text)], input=_remember(s, _text_input("回答追问")))
    dims = r.get("维度") or {}
    ok = r.get("通过") is True and all(dims.get(k) is True for k in ("是什么", "识别信号", "怎么用", "易错"))
    ev = _drop_dup_npc(g.on_feynman(s["iid"], ok), reply_text)
    g.mark_done(s["task"], ok)
    dim_line = "　".join(f"{'✅' if v else '❌'}{k}" for k, v in dims.items())
    return _resp(s, [_msg("npc", reply_text), _msg("sys", (f"✨ {g.T('feynman')}通过　" if ok else "💥 还没讲透　") + dim_line),
                     _msg("sys", it["text"], fold=f"{g.T('skeleton')}原文")], ev, finished=True)


def _example(g, s, text):
    it = _item(g, s["iid"])
    digest = vault.skill_digest(g.paths, g.boards[s["board"]].get("skill"))
    r = ai.chat_json(prompts.example_grade(g.persona, s["board"], it, text, digest))
    if type(r.get("通过")) is not bool:
        raise TrainError("举例判分格式不完整，尚未记录，请重试")
    ok = r["通过"]
    st = g.item(s["iid"])
    st["last_example"] = {"date": g.t, "text": text, "ok": ok, "feedback": r.get("点评", "")}
    ev = g.on_example(s["iid"], ok)
    g.mark_done(s["task"], ok)
    it = _item(g, s["iid"])
    return _to_discuss(g, s, [_msg("sys", "举例通过：下一步实战迁移。" if ok else "举例尚未通过，请按反馈修改。"),
                              _msg("npc", r.get("点评", "")), _msg("sys", r.get("修改建议", ""))], ev,
                       {"kind": "举例", "title": it["name"], "question": "为大项「%s」举一个自己的例子" % it["name"],
                        "mine": text, "reference": r.get("修改建议", "")})


# ---------------------------------------------------------------- 题后复盘：继续问师傅（按板块 skill 回答）
def _discuss_input(teach=False, resumed=None):
    if resumed:   # 接着上次的对话：随时可以重新开始这一项
        return {"mode": "text", "placeholder": "接着上次聊，直接说；Ctrl+Enter 发送",
                "buttons": ([{"id": "ask_more", "label": "🌀 再举一例"}] if teach else [])
                + [{"id": "fresh", "label": "🆕 重新开始" + resumed}, {"id": "discuss_end", "label": "先到这"}]}
    if teach:
        return {"mode": "text", "placeholder": "哪里没听懂？直接问师傅，Ctrl+Enter 发送",
                "buttons": [{"id": "ask_more", "label": "🌀 再举一例"}, {"id": "discuss_end", "label": "结束传授"}]}
    return {"mode": "text", "placeholder": "还有哪里不懂？直接问师傅（会参照这个板块的 skill），Ctrl+Enter 发送",
            "buttons": [{"id": "ask_explain", "label": "🧙 师傅解惑"}, {"id": "discuss_end", "label": "结束复盘"}]}


def _to_discuss(g, s, messages, events, ctx):
    """判完分不马上关门：进入复盘，可以点“师傅解惑”或继续追问；点“结束复盘”才算这次修炼结束"""
    s["discuss"] = dict(ctx, board=s.get("board", ""), history=[])
    extra = []
    if s["type"] == "wrong":
        daily = g.daily_wrong()
        if daily:
            extra.append(_msg("sys", f"今日{g.T('kill')}进度：{min(len(daily['hits']), daily['quota'])}/{daily['quota']}"
                              + ("（已完成，想多斩几只也行）" if daily["done"] else "")))
    return _resp(s, messages + extra + [_msg("sys", "可以继续复盘：点「🧙 师傅解惑」让师傅按功法讲透，或者直接打字追问。")],
                 events, input=_remember(s, _wrong_input(s)))


def _wrong_input(s):
    inp = _discuss_input()
    if s["type"] == "wrong" and (s.get("origin") or {}).get("target") in ("", None, "daily"):
        inp["buttons"].insert(1, {"id": "wrong_next", "label": "👹 下一只"})
    return inp


def _skill_name(g, board):
    return g.boards.get(board, {}).get("skill") or SIDE_SKILLS.get(board) or ""


def _skill_digest(g, board):
    skill = _skill_name(g, board)
    return vault.skill_for_tutor(g.paths, skill)[0] if skill else ""


def _discuss_ask(g, s, text):
    d = s["discuss"]
    if not ai.available():
        return [_msg("npc", (_say(g, "试炼·解惑没AI") or "为师今日闭关（没连上 AI）。") +
                     "\n（在“设置”里填 AI 的 API key 后，师傅就能按功法给你讲题、回答追问。）")]
    try:
        r = ai.chat(prompts.discuss(g.persona, d, _skill_digest(g, d["board"]), text), temperature=0.6, max_tokens=1500)
    except ai.AIError as e:
        raise TrainError("师傅没回话：%s" % e)
    d["history"] += [{"role": "user", "content": text}, {"role": "assistant", "content": r}]
    d["history"] = d["history"][-10:]
    return [_msg("npc", r)]


def _discuss_reply(g, s, text):
    inp = _wrong_input(s) if s["type"] == "wrong" else _discuss_input(s["type"] == "teach", s.get("resumed"))
    return _resp(s, _discuss_ask(g, s, text), input=_remember(s, inp))


def _discuss_action(g, s, act):
    if act == "ask_explain":
        n = len(s["discuss"]["history"])
        msgs = [_msg("me", "🧙 师傅，这题给我讲透。")] + _discuss_ask(g, s, "请按 skill 的方法把这道题完整讲一遍")
        if s["type"] == "wrong" and len(s["discuss"]["history"]) > n:   # 讲成了：存进这题的复盘笔记，下次“复盘解析”能看到
            where = vault.save_tutor_note(g.paths, s["key"], s["discuss"]["history"][-1]["content"], g.t)
            if where:
                msgs.append(_msg("sys", "📌 已存入复盘解析：%s 第 %s 题（再问一次会换成新的）" % (where, s["key"].split("|")[2])))
        return _resp(s, msgs, input=_remember(s, _wrong_input(s)))
    if act == "wrong_next" and s.get("origin"):
        SESSIONS.pop(s["id"], None)
        r = start(g, dict(s["origin"], target=""))
        r["replace"] = True
        return r
    if act == "ask_more":
        return _resp(s, [_msg("me", "🌀 师傅，再举一个例子。")] + _discuss_ask(
            g, s, "再给我出一道考这个大项的典型例题（四个选项），先让我看题，然后按步骤讲怎么用这个方法做出来"),
            input=_remember(s, _discuss_input(True, s.get("resumed"))))
    if act == "fresh":            # 重新开始这一项：开一次全新的
        SESSIONS.pop(s["id"], None)
        r = start(g, dict(s["task"], fresh=True))
        r["replace"] = True
        return r
    if act in ("discuss_end", "skip"):
        scene = "修炼·传授结束" if s["type"] == "teach" else "试炼·复盘结束"
        return _resp(s, [_msg("npc", _say(g, scene) or "今天就到这，去下一项。")], finished=True)
    raise TrainError("这一步请打字追问，或点「师傅解惑」/「结束复盘」")


# ---------------------------------------------------------------- 传授：师傅先把这一项讲清楚，再配真题例题
_GENERIC = re.compile(r"完整|清单|上位|总览|概述|十三[美丑]|选项|题型|方法|技巧|\d+")


def _teach_examples(g, board, it, n=2):
    """从这个板块的题库里挑和大项最贴近的真题：知识点/题干里命中大项名里的关键词越多越靠前"""
    # 名字里的词和真题考点的说法常不一样（“由果推因削弱” vs “削弱论证-因果倒置”），按两字片段比
    parts = [w for w in re.split(r"[·・\s/、（）()\-—：:]+", _GENERIC.sub(" ", it["name"])) if len(w) >= 2]
    parts += [t.split("：")[0].strip("【】 ") for t in it.get("terms", [])[:6] if 2 <= len(t.split("：")[0]) <= 8]
    grams = {w[i:i + 2] for w in parts for i in range(len(w) - 1)} - {"题目", "选项", "正确", "错误"}
    if not grams:
        return []
    scored = []
    for q in question_bank.read(g.paths, board)[0]:
        score = 3 * sum(w in q["topic"] for w in grams) + sum(w in q["stem"][:300] for w in grams)
        if score:
            scored.append((-score, len(q["stem"]), q["id"], q))
    return [x[3] for x in sorted(scored)[:n]]


def _plain(text):
    return vault.IMG_RE.sub("［图］", text or "")


def _start_teach(g, task):
    it = _item(g, task["target"])
    board = task["board"]
    s = new_session("teach", task["title"], task, iid=it["id"], board=board)
    examples = _teach_examples(g, board, it)
    content = "\n".join(["【口诀】" + v for v in it.get("verses", [])] + ["【术语】" + t for t in it.get("terms", [])]
                        + ["【思路】" + t for t in it.get("thoughts", [])] + ["【举例】" + t for t in it.get("examples", [])])
    if ai.available():
        try:
            lecture = ai.chat(prompts.teach(g.persona, board, it, content, _skill_digest(g, board),
                                            [dict(q, stem=_plain(q["stem"]), analysis=_plain(q["analysis"])[:600]) for q in examples]),
                              temperature=0.6, max_tokens=2200)
        except ai.AIError as e:
            raise TrainError("师傅没来上课：%s" % e)
    else:   # 没连 AI：把骨架里这一项原样摊开讲，例题照样给
        lecture = ("（没连 AI，为师先把功法原文摊给你看。）\n\n「%s」这一项要掌握：\n%s"
                   % (it["name"], content or "（骨架里这一项还没有内容）"))
    msgs = [_msg("npc", lecture)]
    for k, q in enumerate(examples, 1):
        msgs.append(_msg("sys", "📜 例题 %d（真题 · %s）" % (k, q["id"]),
                         _bank_blocks(g, board, q["stem"] + "\n\n" + "\n".join("%s. %s" % (o, v) for o, v in q["options"].items()))))
        msgs.append(_msg("sys", "答案：%s\n%s" % (q["answer"], _plain(q["analysis"]) or "（无解析）"), fold="例题 %d 答案与解析（先自己做再展开）" % k))
    if not examples:
        msgs.append(_msg("sys", "题库里没找到贴近这一项的真题，点「🌀 再举一例」让师傅现编一道。"))
    past = _past_logs(g, it["id"], s["id"], n=1)
    s["discuss"] = {"kind": "传授", "title": it["name"], "board": board, "history": [],
                    "previous": past[-1]["text"][-1500:] if past else "",
                    "question": "大项「%s」的内容：\n%s" % (it["name"], content),
                    "mine": "（弟子在听课）", "reference": "\n\n".join(_plain(q["stem"])[:300] + " 答案 " + q["answer"] for q in examples)}
    msgs.append(_msg("sys", "听完可以直接追问，或点「🌀 再举一例」。讲明白了再去背诵口诀、论道。"))
    return _resp(s, msgs, input=_remember(s, _discuss_input(True)))


# ---------------------------------------------------------------- 试剑（应用）
def _grade_apply(g, board, it, q, text):
    r = ai.chat_json(prompts.apply_grade(g.persona, board, it, q.get("题目", ""), q.get("参考答案", ""),
                                         q.get("参考思路", ""), text))
    return bool(r.get("通过")), r.get("点评", "")


def _apply(g, s, text):
    it = _item(g, s["iid"])
    q = s["q"]
    ok, comment = _grade_apply(g, s["board"], it, q, text)
    ev = g.on_apply(s["iid"], ok)
    g.mark_done(s["task"], ok)
    return _to_discuss(g, s, [_msg("sys", f"✨ {g.T('apply')}成功" if ok else f"💥 {g.T('apply')}失败"), _msg("npc", comment),
                              _msg("sys", f"参考答案：{q.get('参考答案', '')}\n参考思路：{q.get('参考思路', '')}", fold="参考答案")], ev,
                       {"kind": "试剑", "title": it["name"], "question": q.get("题目", ""), "answer": q.get("参考答案", ""),
                        "mine": text, "reference": q.get("参考思路", "")})


# ---------------------------------------------------------------- 斩心魔（错题）
def _answer_letter(text):
    m = re.findall(r"(?<![A-Za-z])([A-Ha-h])(?![A-Za-z])", text)
    return m[-1].upper() if m else ""


def _grade_wrong(g, key, board, text):
    """返回 (ok 或 None(自评), 对应大项 iid, 附加消息, AI 结果, answer_ok)"""
    q = vault.find_question(g.paths, key)
    if not q:
        raise TrainError("找不到这道题")
    names = [it["name"] for it in g.final_items(board)]
    if not ai.available():
        letter = _answer_letter(text)
        answer_ok = letter == q["correct"].upper() if letter else True
        return None, "", [_msg("sys", f"正确答案：{q['correct']}" + (f"（你答 {letter}）" if letter else "")),
                          _msg("sys", q["analysis"] or "（这题还没有解析）", fold="复盘解析"),
                          _msg("npc", "没连 AI，对照解析自己判断：思路和答案都对吗？")], None, answer_ok
    qtext = "\n".join(b["v"] for b in vault.render_blocks(g.paths, q) if b["t"] == "text")
    r = ai.chat_json(prompts.wrong_grade(g.persona, board, qtext, q["correct"], q["mine"], q["analysis"], names, text))
    ok = bool(r.get("答案正确")) and bool(r.get("思路正确"))
    iname = (r.get("对应大项") or "").strip()
    iid = skeleton.item_id(board, iname) if iname in names else ""
    extra = [_msg("npc", r.get("点评", "")),
             _msg("sys", f"正确答案：{q['correct']}\n正确思路：{r.get('正确思路', '')}", fold="正确思路"),
             _msg("sys", q["analysis"] or "（这题还没有解析）", fold="复盘解析")]
    return ok, iid, extra, r, True


def _wrong(g, s, text):
    s["answer_text"] = text
    ok, iid, extra, r, answer_ok = _grade_wrong(g, s["key"], s["board"], text)
    if ok is None:
        s["pending"] = {"answer_ok": answer_ok}
        return _resp(s, extra, input=_buttons(("self_ok", "思路和答案都对"), ("self_no", "不对")))
    return _wrong_finish(g, s, ok, iid, extra, r)


def _wrong_finish(g, s, ok, iid, extra, r=None):
    ev = _drop_dup_npc(g.on_wrong(s["key"], s["board"], ok, iid), r and r.get("点评"))
    g.mark_done(s["task"], ok)
    g.wrong_hit(s["key"], ok)
    head = f"⚔ {g.T('kill')}成功" if ok else f"💥 {g.T('wrong')}逃走了（{int(g.rules.num('回炉间隔天数'))} 天后{g.T('redo')}）"
    if r is not None:
        head += f"　答案{'✓' if r.get('答案正确') else '✗'}　思路{'✓' if r.get('思路正确') else '✗'}"
    if iid:
        head += f"　对应：{iid.split('::', 1)[1]}"
    q = vault.find_question(g.paths, s["key"]) or {}
    qtext = "\n".join(b["v"] for b in vault.render_blocks(g.paths, q) if b["t"] == "text") if q else ""
    return _to_discuss(g, s, [_msg("sys", head)] + extra, ev,
                       {"kind": "模考错题", "title": s.get("title", ""), "question": qtext, "answer": q.get("correct", ""),
                        "mine": s.get("answer_text", "") or "（自评）", "reference": q.get("analysis", "")})


# ---------------------------------------------------------------- 渡劫 / 炼丹（连续关卡）
def _start_gauntlet(g, task):
    typ = task["type"]
    if typ == "tribulation":
        st = g.tribulation_status()
        if not st or not st["ready"]:
            raise TrainError(f"现在还不能{g.T('tribulation')}：条件没有全部满足（看首页的{g.T('tribulation')}面板）")
        steps = g.build_gauntlet("tribulation", gate=st["gate"], ai_ok=ai.available())
        if not steps:
            raise TrainError(f"还没有可用的{g.T('skeleton')}或{g.T('wrong')}，天劫无从降下")
        s = new_session(typ, task.get("title") or f"{g.T('tribulation')}", task, steps=steps, i=0, n_ok=0, xp=0,
                        gate=st["gate"], board="")
        head = (f"⚡ {st['realm']}{g.T('tribulation')}！共 {len(steps)} 道天雷，必须一道不落地扛下来。"
                f"储物袋里的{st['pill']}：{st['pills']} 颗（失败时自动服下，可抵挡一道）。")
        return _gauntlet_next(g, s, [_msg("npc", head)])
    board = task["board"]
    steps = g.build_gauntlet("alchemy", board=board)
    if not steps:
        raise TrainError(f"「{board}」还没有可练的{g.T('skeleton')}和{g.T('wrong')}，炼不了这炉丹")
    s = new_session(typ, task.get("title") or f"{g.T('alchemy')} · {board}", task, steps=steps, i=0, n_ok=0, xp=0,
                    board=board)
    return _gauntlet_next(g, s, [_msg("npc", f"开炉！这一炉共 {len(steps)} 味药（{board}的口诀与心魔），成功越多，丹品越高。")])


def _step_head(g, s, step):
    k, n = s["i"] + 1, len(s["steps"])
    if s["type"] == "tribulation":
        return f"第 {k}/{n} 道 · {step.get('label', '')}"
    return f"第 {k}/{n} 味药"


def _gauntlet_next(g, s, msgs, events=None):
    events = events or []
    if s["i"] >= len(s["steps"]):
        return _gauntlet_finish(g, s, msgs, events, ok=True)
    step = s["steps"][s["i"]]
    head = _step_head(g, s, step)
    if step["kind"] == "recite":
        it = _item(g, step["target"])
        msgs.append(_msg("npc", f"{head}：" + _recite_prompt(g, step["board"], it, g.T("recite"))))
        return _resp(s, msgs, events, input=_remember(s, _text_input("凭记忆写出全部内容")))
    if step["kind"] == "wrong":
        q = vault.find_question(g.paths, step["target"])
        if not q:
            s["i"] += 1
            return _gauntlet_next(g, s, msgs + [_msg("sys", "（这道题找不到了，跳过）")], events)
        msgs += [_wrong_intro(g, q, f"{head}："), _msg("npc", "题型 → 方法 → 依据 → 答案。")]
        return _resp(s, msgs, events, input=_remember(s, _text_input("题型 → 方法 → 依据 → 答案")))
    it = _item(g, step["target"])
    q = ai.chat_json(prompts.apply_question(g.persona, step["board"], it), temperature=0.7)
    step["q"] = q
    msgs.append(_msg("npc", f"{head}（考点：{it['name']}）：\n\n{q.get('题目', '')}"))
    return _resp(s, msgs, events, input=_remember(s, _text_input("先说考点和思路，再给答案")))


def _gauntlet_answer(g, s, text):
    step = s["steps"][s["i"]]
    if step["kind"] == "recite":
        it = _item(g, step["target"])
        hit, miss, cov, comment, wrong_says = _judge_recite(g, step["board"], it, text)
        summary = _recite_summary(g, it, hit, miss, cov, [])
        if cov is None:
            s["pending"] = {"miss": miss}
            return _resp(s, [_msg("sys", summary), _msg("sys", it["text"], fold=f"{g.T('skeleton')}原文")],
                         input=_self_rate_buttons())
        ok = not miss and not wrong_says and cov >= g.rules.num("思路达标比例")
        return _gauntlet_step_done(g, s, ok, [_msg("sys", summary)] + ([_msg("npc", comment)] if comment else []), comment)
    if step["kind"] == "wrong":
        ok, iid, extra, r, answer_ok = _grade_wrong(g, step["target"], step["board"], text)
        if ok is None:
            s["pending"] = {"answer_ok": answer_ok}
            return _resp(s, extra, input=_buttons(("self_ok", "思路和答案都对"), ("self_no", "不对")))
        step["iid"] = iid
        return _gauntlet_step_done(g, s, ok, extra, r.get("点评"))
    it = _item(g, step["target"])
    ok, comment = _grade_apply(g, step["board"], it, step["q"], text)
    return _gauntlet_step_done(g, s, ok, [_msg("npc", comment)], comment)


def _gauntlet_step_done(g, s, ok, msgs, comment):
    step = s["steps"][s["i"]]
    trib = s["type"] == "tribulation"
    if step["kind"] == "recite":
        ev = g.on_recite(step["target"], ok, "trial" if trib else "recite")
    elif step["kind"] == "wrong":
        ev = g.on_wrong(step["target"], step["board"], ok, step.get("iid", ""))
    else:
        ev = g.on_apply(step["target"], ok, progress=not trib)
    ev = [e for e in ev if e.get("kind") != "npc" or e.get("scene") not in RESULT_SCENES]  # 连续关卡里不插结果台词
    s["xp"] += _xp_of(ev)
    msgs = [_msg("sys", "✅ 扛住了" if ok else "💥 没扛住")] + msgs
    if ok:
        s["n_ok"] += 1
    elif trib:
        pill = g.use_gate_pill(s["gate"])
        if pill:
            msgs.append(_msg("sys", f"🛡 服下{pill}，硬生生抵挡了这道天雷！"))
        else:
            return _gauntlet_finish(g, s, msgs, ev, ok=False, failed=step)
    s["i"] += 1
    return _gauntlet_next(g, s, msgs, ev)


def _gauntlet_finish(g, s, msgs, events, ok, failed=None):
    if s["type"] == "tribulation":
        fs = {k: failed[k] for k in ("kind", "target", "board")} if failed else None
        ev = g.on_tribulation(s["gate"], ok, fs)
        g.mark_done(s["task"], ok)
        msgs.append(_msg("sys", f"{'🌈 ' + g.T('tribulation') + '成功！' if ok else '⚡ ' + g.T('tribulation') + '失败'}"
                                f"（扛住 {s['n_ok']}/{len(s['steps'])} 道）"))
        return _resp(s, msgs, events + ev, finished=True)
    ev = g.on_alchemy(s["board"], s["n_ok"], len(s["steps"]), s["xp"])
    msgs.append(_msg("sys", f"🔥 丹成！成功 {s['n_ok']}/{len(s['steps'])}"))
    return _resp(s, msgs, events + ev, finished=True)


# ---------------------------------------------------------------- 功法（骨架）
def _start_skeleton(g, task):
    b = task["board"]
    s = new_session("skeleton", task["title"], task, board=b)
    sk = g.skel(b)
    rel = f"训练/骨架/{b}.md"
    S, I = g.T("skeleton"), g.T("item")
    if sk and sk["final"]:
        return _resp(s, [_msg("sys", f"「{b}」{S}已定稿（{len(sk['items'])} {I}）。")], finished=True)
    if sk:
        n_terms = sum(len(i["terms"]) + len(i.get("verses", [])) for i in sk["items"])
        return _resp(s, [_msg("npc", f"「{b}」的{S}草稿在 `{rel}`：{len(sk['items'])} {I}、{n_terms} 个{g.T('term')}（术语）。"
                                     "去 Obsidian 里审一遍：删掉不需要的、补上老师强调的、确认上位清单完整、下位方法归属正确、理解与举例要求清楚。改好了点“定稿”。")],
                     input=_buttons(("final", "已审改，定稿"), ("gen", "重新生成草稿"), ("skip", "稍后再说")))
    if not vault.skill_dir(g.paths, g.boards.get(b, {}).get("skill")):
        return _resp(s, [_msg("sys", f"找不到「{b}」的 skill 文件夹（{g.boards.get(b, {}).get('skill')}），"
                                     f"可以在 Obsidian 里手写 `{rel}`（格式见 DESIGN.md）。")], finished=True)
    return _resp(s, [_msg("npc", f"「{b}」还没有{S}。从解题 skill「{g.boards[b]['skill']}」里提炼一份草稿，你再审改。大约需要 30–60 秒。")],
                 input=_buttons(("gen", "生成草稿"), ("skip", "稍后再说")))


def _skeleton_action(g, s, act):
    b = s["board"]
    S, I = g.T("skeleton"), g.T("item")
    if act == "gen":
        _need_ai(f"生成{S}")
        # skill 常常只是“去读某文件 / 调某知识库”的规程，真正的知识在它引用的资料里，一起读；规则里可用“骨架素材.板块”补充
        extra = [x.strip() for x in re.split(r"[,，;；]", g.rules.get("骨架素材." + b) or "") if x.strip()]
        digest, used = vault.skill_material(g.paths, g.boards[b]["skill"], extra)
        md = ai.chat(prompts.skeleton_gen(b, digest), max_tokens=8000, timeout=240)
        md = re.sub(r"^```(?:markdown|md)?\s*\n|\n```\s*$", "", md.strip())
        src = "> 生成时读到的资料：" + ("、".join(used) if used else "无（只有 skill 本身）") + "\n\n"
        if not skeleton.save_draft(g.paths, b, g.boards[b]["skill"], src + md):
            raise TrainError(f"{S}已定稿，不会覆盖。要重做请先在文件里把状态改回“草稿”")
        g._skel.pop(b, None)
        sk = g.skel(b)
        n = len(sk["items"]) if sk else 0
        tip = "" if used else (f"\n\n⚠ 这个 skill 没引用任何库里的资料，骨架可能只有方法没有知识。可以在 `训练/规则.md` 加一行"
                               f"“- 骨架素材.{b}: 资料文件或文件夹路径”（多个用逗号隔开），再重新生成。")
        return _resp(s, [_msg("npc", f"草稿已写到 `训练/骨架/{b}.md`（{n} {I}）。读到的资料：{'、'.join(used) or '无'}。去 Obsidian 里审改，改好点“定稿”。{tip}")],
                     [{"kind": "info", "msg": f"已生成「{b}」{S}草稿"}],
                     input=_buttons(("final", "已审改，定稿"), ("gen", "重新生成草稿"), ("skip", "稍后再说")))
    if act == "final":
        g._skel.pop(b, None)
        sk = g.skel(b)
        if not sk or not sk["items"]:
            raise TrainError(f"{S}里没有解析到任何一{I}（每一{I}需要一个 `## 标题`）")
        pending = [i["name"] for i in sk["items"] if re.search(r"^>\s*待核对", i["text"], re.M)]
        if pending:
            raise TrainError("方法细节尚未补充，不能定稿：" + "、".join(pending))
        bad = [i["name"] for i in sk["items"] if not i["terms"] and not i["thoughts"] and not i.get("verses")]
        skeleton.set_final(g.paths, b, True)
        g._skel.pop(b, None)
        g.mark_done(s["task"], True)
        msg = f"「{b}」{S}已定稿：{len(sk['items'])} {I}。明天的{g.T('tasks')}会开始安排它；也可以回首页点“重新生成{g.T('tasks')}”马上开始。"
        if bad:
            msg += f"\n注意：这些{I}下面没有条目：{'、'.join(bad)}"
        return _resp(s, [_msg("sys", msg)], [{"kind": "info", "msg": f"{S}定稿"}], finished=True)
    raise TrainError("未知操作")


# ---------------------------------------------------------------- 聊天
def _chat(g, s, text):
    s["history"].append({"role": "user", "content": text})
    if not ai.available():
        return _resp(s, [_msg("npc", g.say(g.mood()) or "（没连 AI，只会说台词库里的话）")], input=_text_input(""))
    cur = g.current_batch()
    knowledge = "\n".join(f"{b}：" + "、".join(it["name"] for it in g.final_items(b))
                          for b in (g.batch_boards(cur) if cur is not None else []) if g.final_items(b))
    r = ai.chat(prompts.free_chat(g.persona, s["history"][-12:], g.tutor_context(), knowledge),
                temperature=0.8, max_tokens=500)
    s["history"].append({"role": "assistant", "content": r})
    return _resp(s, [_msg("npc", r)], input=_text_input(""))



# ---------------------------------------------------------------- 顺序真题实战（答案与解析只在提交后返回）
def _start_bank(g, task):
    try:
        run = question_bank.begin(g, task['board'], 'review' if task['type'] == 'bank_review' else 'new')
    except question_bank.BankError as e:
        raise TrainError(str(e))
    # 新入口也可以恢复同板块未完成的错题组，计时类型与实际模式一致。
    typ = 'bank_review' if run['mode'] == 'review' else 'bank'
    s = new_session(typ, '%s · %s' % (g.T(typ), question_bank.label(task['board'])), task, board=task['board'], token=run['token'])
    # 所有板块默认都是点选项、交卷判分；“写拆题过程逐题审方法”只在功课里明确要求时才用（task.reasoning）
    if run.get('reasoning') and not task.get('reasoning') and not run['results']:
        run['reasoning'] = False          # 以前按“写拆题过程”开的组、还没交过题：改成正常答题
        run['exam'] = True
    run.setdefault('reasoning', bool(task.get('reasoning')))
    run.setdefault('exam', not run['reasoning'] and not run['results'])
    r = _bank_show(g, s, run)
    r['messages'].insert(0, _msg('npc', g.T('bank_intro')))
    return r


def _bank_show(g, s, run, events=None):
    if run.get('exam'):
        return _exam_show(g, s, run, events)
    q = run['questions'][run['pos']]
    if run['phase'] == 'analysis':
        r = run['results'][-1]
        msg = '你的答案：%s · %s\n正确答案：%s\n知识点：%s\n\n解析：' % (
            r['answer'], '破关成功（正确）' if r['ok'] else '失手（错误），' + g.T('bank_record'), q['answer'], q['topic'])
        # 解析里可能有图（图形推理的讲解图），和题干一样转成网页块
        msgs = [_msg('sys', msg, _bank_blocks(g, q['board'], q['analysis'] or '（解析待补，之后可以用 skill 补写）'))]
        if r.get('reasoning'):
            msgs.append(_msg('sys', '你的拆题：\n' + r['reasoning'] + '\n方法审核：' + (
                '通过' if r.get('method_ok') is True else '未通过' if r.get('method_ok') is False else '未验证（未连接AI）')
                + '\n' + r.get('feedback', '')))
        return _bank_resp(g, s, run, msgs + [_msg('npc', g.T('bank_good' if r['ok'] else 'bank_bad'))], events,
                          _buttons(('bank_next', g.T('bank_result') if run['pos'] + 1 == len(run['questions']) else g.T('bank_next')),
                                   ('bank_pause', g.T('bank_pause'))))
    msg = '%s · 第 %s/%s 关 · 编号 %s' % (question_bank.label(run['board']), run['pos'] + 1, len(run['questions']), q['id'])
    blocks = _bank_blocks(g, q['board'], q['stem'] + '\n\n' + '\n'.join('%s. %s' % (k, v) for k, v in q['options'].items()))
    if run.get('reasoning'):
        msg += '\n\n独立拆题：问法方向 → 结论（主体/结果）→ 论据 → 底层结构 → A/B/C/D的作用与排除理由。最后单独写一行【答案】B（填你的选择）。提交后才显示标准答案。'
        return _bank_resp(g, s, run, [_msg('sys', msg, blocks)], events,
                          _remember(s, _text_input('写出拆题过程，最后一行【答案】A/B/C/D')))
    # 不在作答前展示知识点标签，避免直接提示题型；复盘时才显示。
    return _bank_resp(g, s, run, [_msg('sys', msg, blocks)], events,
                      _buttons(*[('bank_answer:%s:%s' % (run['pos'], k), k) for k in 'ABCD'],
                               ('bank_pause', g.T('bank_pause'))))


def _bank_blocks(g, board, text):
    """题干 + 选项 → 网页块；![[训练/题库/图片/…png]] 变成图片（库内路径，找不到时按文件名在 题库/图片/<板块>/ 里找）。
    单独一行的图是图片块；夹在句子里的（数量关系解析里的公式图）留在文字里，网页上按行内小图显示"""
    def resolve(name):
        if g.paths.vault:
            for c in (name, "训练/题库/" + name, "训练/题库/图片/%s/%s" % (board, Path(name).name)):
                if vault.safe_vault_file(g.paths, c):
                    return c
        return None

    blocks, buf, pos = [], "", 0

    def flush():
        nonlocal buf
        if buf.strip():
            blocks.append({"t": "text", "v": buf.strip()})
        buf = ""
    for m in vault.IMG_RE.finditer(text):
        name = (m.group(1) or m.group(2) or "").strip()
        rel = resolve(name)
        line_start = text.rfind("\n", 0, m.start()) + 1
        line_end = text.find("\n", m.end())
        line = text[line_start:m.start()] + text[m.end():len(text) if line_end < 0 else line_end]
        buf += text[pos:m.start()]
        pos = m.end()
        if line.strip() and rel:          # 行内小图（公式）
            buf += "![[%s]]" % rel
            continue
        flush()
        blocks.append({"t": "img", "v": rel} if rel else {"t": "text", "v": "（缺图：%s，请把图片放到 训练/题库/图片/%s/）" % (name, board)})
    buf += text[pos:]
    flush()
    return blocks


def _bank_action(g, s, act):
    run = question_bank.state(g)['runs'].get(s['board'])
    if not run or run['token'] != s['token']:
        raise TrainError('本组已经结束，请重新进入实战')
    if act in ('bank_pause', 'skip'):
        if run.get('exam') and run['phase'] != 'review':
            _tick(run)      # 暂离不计时
        return _resp(s, [_msg('sys', '试炼进度已保存，下次进入这个板块续闯。')], finished=True)
    if run.get('exam'):
        return _exam_action(g, s, run, act)
    if act.startswith('bank_answer:'):
        if run.get('reasoning'):
            raise TrainError('请写拆题过程及最后的【答案】再提交')
        parts = act.split(':')
        if len(parts) != 3 or parts[1] != str(run['pos']):
            raise TrainError('题目已经切换，请重新进入本组')
        try:
            ev = question_bank.record(g, run, parts[2])
        except question_bank.BankError as e:
            raise TrainError(str(e))
        return _bank_show(g, s, run, ev)
    if act == 'bank_next' and run['phase'] == 'analysis':
        if run['pos'] + 1 < len(run['questions']):
            run['pos'] += 1
            run['phase'] = 'answer'
            return _bank_show(g, s, run)
        group, events = _settle(g, s, run)
        text = '%s · %s完成：%s/%s 正确，正确率 %.1f%%。\n试炼品评：%s\n%s已保存，可到%s继续磨练。' % (
            question_bank.label(s['board']), g.T('bank_review' if group['mode'] == 'review' else 'bank'),
            group['correct'], group['total'], 100 * group['correct'] / group['total'],
            g.T('bank_rank.' + str(group['rank'])), g.T('bank_wrong'), g.T('bank_review'))
        return _resp(s, [_msg('sys', text), _msg('npc', g.T('bank_close'))], events, finished=True)
    raise TrainError('这一步请使用当前题目的按钮')


def _settle(g, s, run, keep=False):
    """一组做完：记成绩、发通关奖、勾掉今日功课。返回 (成绩, 事件)"""
    group = question_bank.finish(g, run, keep)
    # 错题复练不代替当日的新题实战；完成一组即完成任务，不要求全对。
    if group['mode'] == 'new':   # 整套试炼也算完成了套里各板块今天的实战功课
        for b in group['boards'] if question_bank.is_set(s['board']) else [s['board']]:
            g.mark_done({'id': 'bank:' + b}, True)
    events = []
    # 通关奖只对应本组首次作答的题目；旧组缺 first 标记不补发，复练不刷修为。
    if group['mode'] == 'new' and group['first_count']:
        base = g.rules.xp('实战通关') * group['first_count'] / group['total']
        main = max(group['boards'], key=lambda b: sum(q['board'] == b for q in run['questions']))
        events = g._award(base, 'bank_clear', main if question_bank.is_set(s['board']) else s['board'], ok=True,
                          note='%s · %s 通关' % (g.T('bank'), question_bank.label(s['board'])))
    # 逻辑填空：正确选项里的成语 / 实词收进藏经阁·成语实词录
    try:
        new = idioms.harvest(g, [q for q, _ in zip(run['questions'], run['results'])])
    except Exception:     # 收录出错不影响交卷
        new = []
    if new:
        events = list(events) + [{'kind': 'info', 'msg': '📗 成语实词录新收 %d 个：%s%s' % (
            len(new), '、'.join(new[:8]), ' 等' if len(new) > 8 else '')}]
    return group, events


# ---------------------------------------------------------------- 考试式：全部选完交卷 → 正确率 → 逐题复盘（可请师傅解惑）
SIDE_SKILLS = {'常识判断': 'xingce-changshi'}   # 副线板块没有骨架设置，按名字找 skill


IDLE_CAP = 600   # 一道题一次最多记 10 分钟：中途走开、关了网页没点暂离，不把几个小时算进去


def _tick(run):
    """把当前这道题从显示到现在的时间记到它头上（翻回来改答案的时间也算这道题）"""
    shown = run.get('shown')
    if shown:
        times = run.setdefault('times', {})
        times[str(shown[0])] = times.get(str(shown[0]), 0) + max(0, min(time.time() - shown[1], IDLE_CAP))
    run['shown'] = None


def _clock(sec):
    sec = int(round(sec or 0))
    return '%d:%02d' % (sec // 60, sec % 60) if sec < 3600 else '%d:%02d:%02d' % (sec // 3600, sec // 60 % 60, sec % 60)


def _result_table(g, run):
    """交卷后的成绩表：每道题的答案、对错、用时，最后一行合计；跨板块的再按板块汇总"""
    qs, res = run['questions'], run['results']
    rows = [[str(i + 1), q['id'], q['board'], q['topic'][:16], r['answer'], q['answer'], '✓' if r['ok'] else '✗',
             _clock(r.get('seconds'))] for i, (q, r) in enumerate(zip(qs, res))]
    total = sum(r.get('seconds', 0) for r in res)
    ok = sum(r['ok'] for r in res)
    rows.append(['合计', '', '', '', '', '', '%d/%d' % (ok, len(res)), _clock(total)])
    blocks = [{'t': 'table', 'head': ['题', '编号', '板块', '知识点', '我选', '答案', '对错', '用时'], 'rows': rows}]
    boards = list(dict.fromkeys(q['board'] for q in qs))
    if len(boards) > 1:
        brows = []
        for b in boards:
            idx = [i for i, q in enumerate(qs) if q['board'] == b]
            sec = sum(res[i].get('seconds', 0) for i in idx)
            brows.append([b, str(len(idx)), '%d/%d' % (sum(res[i]['ok'] for i in idx), len(idx)), _clock(sec), _clock(sec / len(idx))])
        blocks.append({'t': 'table', 'head': ['板块', '题数', '对', '用时', '平均每题'], 'rows': brows})
    return blocks, total


def _save_table(g, run, total):
    """成绩表另存一份到 训练/试炼记录/<日期>.md（追加），在 Obsidian 里也能翻"""
    if not g.paths.train:
        return
    qs, res, group = run['questions'], run['results'], run['settled']
    lines = ['', '## %s · %s · 正确率 %.1f%%（%d/%d）· 用时 %s' % (
        time.strftime('%H:%M'), question_bank.label(run['board']), 100 * group['correct'] / group['total'],
        group['correct'], group['total'], _clock(total)), '',
        '| 题 | 编号 | 板块 | 知识点 | 我选 | 答案 | 对错 | 用时 |', '|---|---|---|---|---|---|---|---|']
    for i, (q, r) in enumerate(zip(qs, res)):
        lines.append('| %d | %s | %s | %s | %s | %s | %s | %s |' % (
            i + 1, q['id'], q['board'], q['topic'][:16].replace('|', '/'), r['answer'], q['answer'],
            '✓' if r['ok'] else '✗', _clock(r.get('seconds'))))
    folder = g.paths.train / '试炼记录'
    try:
        folder.mkdir(parents=True, exist_ok=True)
        f = folder / ('%s.md' % g.t)
        head = '' if f.exists() else '# 试炼记录 · %s\n' % g.t
        with f.open('a', encoding='utf-8', newline='\n') as fh:
            fh.write(head + '\n'.join(lines) + '\n')
    except OSError:
        pass


def _say(g, scene, **vals):
    return g.lines.pick(scene, 称呼=g.persona['称呼'], 导师名=g.persona['导师名'], **vals)


def _exam_show(g, s, run, events=None, extra=None):
    qs = run['questions']
    if run['phase'] == 'review':
        return _review_show(g, s, run, events, extra)
    picks = run.setdefault('picks', {})
    pos = run['pos']
    q = qs[pos]
    run['shown'] = [pos, time.time()]
    left = [str(i + 1) for i in range(len(qs)) if str(i) not in picks]
    msg = '%s · 第 %s/%s 题 · 编号 %s' % (question_bank.label(run['board']), pos + 1, len(qs), q['id'])
    blocks = _bank_blocks(g, q['board'], q['stem'] + '\n\n' + '\n'.join('%s. %s' % (k, v) for k, v in q['options'].items()))
    sheet = '答题卡：' + ' '.join('%d%s' % (i + 1, '·' + picks[str(i)] if str(i) in picks else '·_') for i in range(len(qs)))
    mine = picks.get(str(pos))
    btns = [('exam_pick:%s:%s' % (pos, k), ('✓ ' if k == mine else '') + k) for k in 'ABCD']
    if pos > 0:
        btns.append(('exam_prev', '← 上一题'))
    if pos + 1 < len(qs):
        btns.append(('exam_next', '下一题 →'))
    btns.append(('exam_submit', '交卷' if not left else '交卷（还有 %d 题没选）' % len(left)))
    btns.append(('bank_pause', g.T('bank_pause')))
    msgs = [_msg('sys', msg, blocks), _msg('sys', sheet)] + (extra or [])
    r = _bank_resp(g, s, run, msgs, events, _buttons(*btns))
    r['replace'] = True
    return r


def _exam_action(g, s, run, act):
    qs, picks = run['questions'], run.setdefault('picks', {})
    if run['phase'] == 'review':
        return _review_action(g, s, run, act)
    _tick(run)
    if act.startswith('exam_pick:'):
        _, pos, k = act.split(':')
        if pos != str(run['pos']) or k not in 'ABCD':
            raise TrainError('题目已经切换，请重新进入本组')
        picks[pos] = k
        if run['pos'] + 1 < len(qs):      # 选完自动翻到下一题；最后一题停住等交卷
            run['pos'] += 1
        return _exam_show(g, s, run)
    if act == 'exam_prev':
        run['pos'] = max(0, run['pos'] - 1)
        return _exam_show(g, s, run)
    if act == 'exam_next':
        run['pos'] = min(len(qs) - 1, run['pos'] + 1)
        return _exam_show(g, s, run)
    if act == 'exam_submit':
        left = [i for i in range(len(qs)) if str(i) not in picks]
        if left:
            run['pos'] = left[0]
            return _exam_show(g, s, run, extra=[_msg('npc', _say(g, '试炼·没做完', 题号='、'.join(str(i + 1) for i in left))
                                                     or '还有第 %s 题没选，交什么卷？' % '、'.join(str(i + 1) for i in left))])
        events = []
        for i in range(len(qs)):
            run['pos'], run['phase'] = i, 'answer'
            try:
                events += question_bank.record(g, run, picks[str(i)])
            except question_bank.BankError as e:
                raise TrainError(str(e))
        for i, r in enumerate(run['results']):
            r['seconds'] = round(run.get('times', {}).get(str(i), 0))
        group, ev = _settle(g, s, run, keep=True)
        group['seconds'] = sum(r['seconds'] for r in run['results'])
        _save_table(g, run, group['seconds'])
        # 一题一条“+5 修为”会刷屏，合成一条
        xp = sum(e['v'] for e in events + ev if e.get('kind') == 'xp')
        events = ([{'kind': 'xp', 'v': xp, 'msg': '%s · %s 交卷' % (g.T('bank'), question_bank.label(s['board']))}] if xp else []) + \
            [e for e in events + ev if e.get('kind') != 'xp']
        run['phase'], run['rpos'] = 'review', 0
        return _review_show(g, s, run, events, head=True)
    raise TrainError('这一步请使用当前题目的按钮')


def _rank_scene(group):
    if group['correct'] == group['total']:
        return '试炼·全对'
    return {2: '试炼·上品', 1: '试炼·中品'}.get(group['rank'], '试炼·下品')


def _review_show(g, s, run, events=None, extra=None, head=False, scroll_bottom=False):
    qs, res, group = run['questions'], run['results'], run['settled']
    i = run.setdefault('rpos', 0)
    q, r = qs[i], res[i]
    msgs = []
    if head:
        rate = 100 * group['correct'] / group['total']
        table, total = _result_table(g, run)
        msgs.append(_msg('sys', '交卷！%s · 正确率 %.1f%%（%s/%s）· 用时 %s（平均每题 %s）\n试炼品评：%s\n\n下面逐题复盘，看不懂的点「师傅解惑」。' % (
            question_bank.label(run['board']), rate, group['correct'], group['total'], _clock(total), _clock(total / len(res)),
            g.T('bank_rank.' + str(group['rank']))), table))
        msgs.append(_msg('npc', _say(g, _rank_scene(group), 正确率='%.0f%%' % rate, 对题数=group['correct'],
                                     总题数=group['total'], 错题数=group['total'] - group['correct']) or g.T('bank_close')))
    msgs.append(_msg('sys', '复盘 第 %s/%s 题 · 编号 %s · %s · 用时 %s' % (i + 1, len(qs), q['id'], '✓ 答对' if r['ok'] else '✗ 答错', _clock(r.get('seconds'))),
                     _bank_blocks(g, q['board'], q['stem'] + '\n\n' + '\n'.join('%s. %s' % (k, v) for k, v in q['options'].items()))))
    msgs.append(_msg('sys', '你的答案：%s · 正确答案：%s\n知识点：%s\n\n解析：' % (r['answer'], q['answer'], q['topic']),
                     _bank_blocks(g, q['board'], q['analysis'] or '（这题没有解析，点「师傅解惑」让师傅讲）')))
    if not r['ok'] and not head:
        line = _say(g, '试炼·复盘错题', 你的答案=r['answer'], 正确答案=q['answer'])
        if line:
            msgs.append(_msg('npc', line))
    if str(i) in run.get('explain', {}):
        msgs.append(_msg('npc', run['explain'][str(i)]))
    elif question_bank.TUTOR_HEAD not in (q['analysis'] or '') and q['id'] in question_bank.tutor_notes(g.paths):   # 旧版存在单独文件里的
        msgs.append(_msg('sys', question_bank.tutor_notes(g.paths)[q['id']], fold='🧙 上次的师傅解惑'))
    for h in run.get('chat', {}).get(str(i), []):          # 这道题上追问师傅的对话
        msgs.append(_msg('me' if h['role'] == 'user' else 'npc', h['content']))
    msgs += extra or []
    wrong_after = [k for k in range(i + 1, len(qs)) if not res[k]['ok']]
    btns = [('exam_explain:%s' % i, '🧙 师傅解惑' if str(i) not in run.get('explain', {}) else '🧙 再问师傅')]
    if i > 0:
        btns.append(('exam_rprev', '← 上一题'))
    if i + 1 < len(qs):
        btns.append(('exam_rnext', '下一题 →'))
    if wrong_after:
        btns.append(('exam_rwrong', '下一道错题'))
    btns.append(('exam_close', '结束复盘'))
    btns.append(('bank_pause', '稍后再看'))
    inp = {'mode': 'text', 'placeholder': '对这道题还有疑问？直接问师傅（Ctrl+Enter 发送）；「🧙 师傅解惑」按功法 skill 把整题讲透',
           'buttons': [{'id': k, 'label': v} for k, v in btns]}
    rr = _bank_resp(g, s, run, msgs, events, _remember(s, inp))
    rr['replace'] = True
    if scroll_bottom:
        rr['scroll'] = 'bottom'
    return rr


def _review_action(g, s, run, act):
    qs, res = run['questions'], run['results']
    i = run.get('rpos', 0)
    if act == 'exam_rprev':
        run['rpos'] = max(0, i - 1)
    elif act == 'exam_rnext':
        run['rpos'] = min(len(qs) - 1, i + 1)
    elif act == 'exam_rwrong':
        run['rpos'] = next((k for k in range(i + 1, len(qs)) if not res[k]['ok']), i)
    elif act.startswith('exam_explain:'):
        if act.split(':')[1] != str(i):
            raise TrainError('题目已经切换，请重新点')
        if not ai.available():   # 没连 AI：说一句，不记成“讲过了”
            return _review_show(g, s, run, extra=[_msg('npc', (_say(g, '试炼·解惑没AI') or '为师今日闭关（没连上 AI）。先把解析读三遍。')
                                                       + '\n（在“设置”里填 AI 的 API key 后，师傅就能按功法给你讲题。）')])
        text, skill, used = _explain(g, qs[i], res[i])
        run.setdefault('explain', {})[str(i)] = text
        question_bank.save_tutor_note(g.paths, qs[i], text, g.t)        # 备份一份（历年题库重新转换时不丢）
        where = question_bank.save_tutor_to_bank(g.paths, qs[i], text, g.t)
        note = ('📌 已写进 训练/题库/%s 这道题的解析末尾（原解析保留；再问一次会换成新的）' % where if where
                else '📌 题库里没找到这道题（可能改过编号），讲解存在 训练/题库/师傅解惑.md')
        note += ('\n📜 依据 skill「%s」：%s' % (skill, '、'.join(used[:8]) + (' 等 %d 个文件' % len(used) if len(used) > 8 else ''))
                 if used else '\n⚠ 这个板块没找到 skill 资料（copilot/skills/%s），师傅只能按通用方法讲' % (skill or '未配置'))
        return _review_show(g, s, run, extra=[_msg('sys', note)], scroll_bottom=True)
    elif act == 'exam_close':
        group = run['settled']
        table, total = _result_table(g, run)
        question_bank.close(g, run)
        text = '%s 复盘结束：%s/%s 正确，用时 %s。成绩表也存进了 训练/试炼记录/%s.md。%s已保存，可到%s继续磨练。' % (
            question_bank.label(run['board']), group['correct'], group['total'], _clock(total), g.t, g.T('bank_wrong'), g.T('bank_review'))
        return _resp(s, [_msg('sys', text, table), _msg('npc', _say(g, '试炼·复盘结束') or g.T('bank_close'))], finished=True)
    else:
        raise TrainError('这一步请使用当前题目的按钮')
    return _review_show(g, s, run)


def _explain(g, q, r):
    """师傅解惑：按这道题所属板块的 skill 讲题。返回 (讲解, skill 名, 读到的 skill 文件)"""
    skill = _skill_name(g, q['board'])
    digest, used = vault.skill_for_tutor(g.paths, skill) if skill else ('', [])
    try:
        text = ai.chat(prompts.bank_explain(g.persona, q, r['answer'], digest, skill), temperature=0.5, max_tokens=1800)
    except ai.AIError as e:
        raise TrainError('师傅没回话：%s' % e)
    return text, skill, used


def _bank_resp(g, s, run, messages, events, inp):
    """给网页提供只含进度的战斗面板，绝不包含答案或解析快照。"""
    r = _resp(s, messages, events, input=inp)
    exam = run.get('exam') and run['phase'] != 'review'
    r['battle'] = {'board': run['board'], 'total': len(run['questions']),
                   'position': (run.get('rpos', 0) if run['phase'] == 'review' else run['pos']) + 1,
                   'answered': len(run.get('picks', {})) if exam else len(run['results']),
                   'correct': None if exam else sum(x['ok'] for x in run['results']),
                   'mode': run['mode'], 'phase': run['phase'], 'tower': question_bank.tower(g)}
    if exam:   # 计时：网页按这两个数接着走秒（时间以程序记录为准）
        times = run.get('times', {})
        r['battle']['timer'] = {'total': round(sum(times.values())), 'question': round(times.get(str(run['pos']), 0))}
    return r


def _review_chat(g, s, run, text):
    """复盘时追问：带着这道题、你的答案和解析问师傅（按板块 skill），对话留在这道题下面"""
    i = run.get("rpos", 0)
    q, r = run["questions"][i], run["results"][i]
    hist = run.setdefault("chat", {}).setdefault(str(i), [])
    if not ai.available():
        return _review_show(g, s, run, extra=[_msg("me", text), _msg("npc", (_say(g, "试炼·解惑没AI") or "为师今日闭关（没连上 AI）。")
                                                                    + "\n（在“设置”里填 AI 的 API key 后才能追问。）")], scroll_bottom=True)
    ctx = {"kind": "试炼复盘", "title": q["id"], "board": q["board"], "history": hist[-10:],
           "question": q["stem"] + "\n" + "\n".join("%s. %s" % kv for kv in q["options"].items()),
           "answer": q["answer"], "mine": r["answer"], "reference": q.get("analysis", "")[:3000]}
    try:
        reply = ai.chat(prompts.discuss(g.persona, ctx, _skill_digest(g, q["board"]), text), temperature=0.6, max_tokens=1500)
    except ai.AIError as e:
        raise TrainError("师傅没回话：%s" % e)
    hist += [{"role": "user", "content": text}, {"role": "assistant", "content": reply}]
    return _review_show(g, s, run, scroll_bottom=True)


def _bank_reply(g, s, text):
    run = question_bank.state(g)["runs"].get(s["board"])
    if run and run["token"] == s["token"] and run.get("exam") and run["phase"] == "review":
        return _review_chat(g, s, run, text)
    if not run or run["token"] != s["token"] or run["phase"] != "answer":
        raise TrainError("题目已提交或组已切换，请恢复当前进度")
    if not run.get("reasoning"):
        raise TrainError("请使用选项按钮")
    # 专用答案行，不能把选项分析里的最后一个字母误当最终答案。
    matches = re.findall(r"(?m)^\s*(?:【答案】|答案[:：])\s*([A-Da-d])\s*$", text)
    if len(matches) != 1:
        raise TrainError("请单独写且只写一行【答案】B，不能从拆题中的选项字母猜答案")
    reasoning = re.sub(r"(?m)^\s*(?:【答案】|答案[:：])\s*[A-Da-d]\s*$", "", text).strip()
    if not reasoning:
        raise TrainError("还没有拆题过程，请写出论据、结论、结构及选项分析")
    q = run["questions"][run["pos"]]
    method_ok, feedback = None, "未连接AI，请提交后对照解析自行核对方法；正确率只表示答案正确率。"
    if ai.available():
        digest = vault.skill_digest(g.paths, g.boards.get(s["board"], {}).get("skill"))
        r = ai.chat_json(prompts.bank_method_grade(g.persona, s["board"], q, text, digest))
        dims = r.get("维度")
        if type(r.get("通过")) is not bool or not isinstance(dims, dict) or any(
                type(dims.get(k)) is not bool for k in ("方向", "结论论据", "结构", "选项分析")):
            raise TrainError("AI方法审核格式不完整，尚未提交，请重试")
        method_ok = r["通过"] and all(dims[k] for k in ("方向", "结论论据", "结构", "选项分析")) and bool(digest)
        feedback = r.get("点评", "") + "\n正确思路：" + r.get("正确思路", "")
    try:
        ev = question_bank.record(g, run, matches[0].upper(), reasoning, method_ok, feedback)
    except question_bank.BankError as e:
        raise TrainError(str(e))
    return _bank_show(g, s, run, ev)


# ---------------------------------------------------------------- 大比复盘：一次模考按板块逐题复盘（界面同试炼交卷后的复盘；时间计入“复习”）
MOCK_TIME_BOARD = {"类比关系": "类比推理", "中心理解": "片段阅读", "语句排序": "语句表达", "形式逻辑": "论证逻辑"}
MOCK_ICON = {"✅": "✓ 答对", "❌": "✗ 答错", "⚪": "⚪ 没做"}


def mock_boards(g, season):
    """这一季模考拆出来的各板块（按文件顺序），只要有题的"""
    d = next((d for n, d in vault.seasons(g.paths) if n == season), None)
    if not d:
        return None, []
    return d, [f.stem[3:] for f in sorted(d.glob("[0-9][0-9]-*.md")) if vault.parse_board_file(f)]


def mock_reviewed(g, season):
    return g.state.setdefault("mocks", {}).setdefault(str(season), {}).setdefault("reviewed", {})


def _time_board(g, src):
    """复盘时间记到哪个修炼板块（首页“各模块学习时间”用）：同名的；拆试卷时的叫法换成修炼里的叫法；都没有就记总时间"""
    bs = question_bank.boards(g)
    for b in (src, MOCK_TIME_BOARD.get(src, "")):
        if b in bs:
            return b
    return ""


def _mreview_load(g, s, src):
    d, boards = mock_boards(g, s["season"])
    if not d or src not in boards:
        raise TrainError("第%s季没有「%s」的复盘" % (s["season"], src))
    qs = [dict(q, season=s["season"], source=src, dir=str(d), key="%s|%s|%s" % (s["season"], src, q["num"]))
          for q in vault.parse_board_file(vault.board_file(d, src))]
    picked = [q for q in qs if q["icon"] != "✅"] if s["only_wrong"] else qs
    s["all_correct"] = s["only_wrong"] and not picked
    s.update(source=src, board=_time_board(g, src), boards=boards, qs=picked or qs, rpos=0, explain={}, chat={},
             title="📜 大比复盘 · 第%s季 · %s" % (s["season"], src))


def _start_mreview(g, task):
    try:
        season = int(task.get("season"))
    except (TypeError, ValueError):
        raise TrainError("选一季模考再复盘")
    d, boards = mock_boards(g, season)
    if not boards:
        raise TrainError("第%s季还没有板块复盘：先到藏经阁 → 玉简 · 题库 → 导入真题，导入这一季的模考 PDF" % season)
    src = task.get("board") if task.get("board") in boards else boards[0]
    s = new_session("mock_review", "", task, season=season, only_wrong=bool(task.get("only_wrong")))
    _mreview_load(g, s, src)
    return _mreview_show(g, s, head=True)


def _mreview_counts(qs):
    return {k: sum(q["icon"] == k for q in qs) for k in ("✅", "❌", "⚪")}


def _mreview_show(g, s, events=None, extra=None, head=False, scroll_bottom=False):
    qs, i = s["qs"], s["rpos"]
    q = qs[i]
    done = mock_reviewed(g, s["season"]).setdefault(s["source"], [])
    if q["num"] not in done:
        done.append(q["num"])
    msgs = []
    if head:
        c = _mreview_counts(qs)
        ok, n = c["✅"], len(qs)
        rows = [[str(x["num"]), x["mine"] or "—", x["correct"] or "?", MOCK_ICON.get(x["icon"], x["icon"])] for x in qs]
        note = ("（这个板块全对，没有错题，下面复盘全部题目）" if s.get("all_correct")
                else "（只看错题和没做的）" if s["only_wrong"] else "")
        msgs.append(_msg("sys", "📜 第%s季大比复盘 · %s%s\n答对 %d/%d（%.0f%%）· 答错 %d · 没做 %d\n\n下面逐题复盘：看题 → 对答案 → 读解析，看不懂的点「师傅解惑」。" % (
            s["season"], s["source"], note, ok, n, 100 * ok / n, c["❌"], c["⚪"]),
            [{"t": "table", "head": ["题号", "我选", "答案", "结果"], "rows": rows}]))
        rate = ok / n
        scene = "试炼·全对" if ok == n else "试炼·上品" if rate >= 0.8 else "试炼·中品" if rate >= 0.6 else "试炼·下品"
        line = _say(g, scene, 正确率="%.0f%%" % (100 * rate), 对题数=ok, 总题数=n, 错题数=n - ok)
        if line:
            msgs.append(_msg("npc", line))
    msgs.append(_msg("sys", "复盘 第 %d/%d 题 · 第%s季第 %s 题 · %s · %s" % (
        i + 1, len(qs), s["season"], q["num"], s["source"], MOCK_ICON.get(q["icon"], q["icon"])), vault.render_blocks(g.paths, q)))
    msgs.append(_msg("sys", "你的答案：%s · 正确答案：%s\n\n复盘解析：" % (q["mine"] or "没做", q["correct"] or "?"),
                     vault.render_blocks(g.paths, {"body": q["analysis"] or "（这题还没写复盘解析，点「师傅解惑」让师傅讲；讲完自动写进这题的复盘笔记）",
                                                   "dir": q["dir"]})))
    if q["icon"] != "✅" and not head:
        line = _say(g, "试炼·复盘错题", 你的答案=q["mine"] or "没做", 正确答案=q["correct"])
        if line:
            msgs.append(_msg("npc", line))
    if str(i) in s["explain"]:
        msgs.append(_msg("npc", s["explain"][str(i)]))
    for h in s["chat"].get(str(i), []):
        msgs.append(_msg("me" if h["role"] == "user" else "npc", h["content"]))
    msgs += extra or []
    btns = [("mr_explain:%d" % i, "🧙 师傅解惑" if str(i) not in s["explain"] else "🧙 再问师傅")]
    if i > 0:
        btns.append(("mr_prev", "← 上一题"))
    if i + 1 < len(qs):
        btns.append(("mr_next", "下一题 →"))
    if any(x["icon"] != "✅" for x in qs[i + 1:]):
        btns.append(("mr_wrong", "下一道错题"))
    k = s["boards"].index(s["source"])
    if k + 1 < len(s["boards"]) and (i + 1 == len(qs) or head):
        btns.append(("mr_board:" + s["boards"][k + 1], "下一板块：%s →" % s["boards"][k + 1]))
    btns.append(("mr_close", "结束复盘"))
    inp = {"mode": "text", "placeholder": "对这道题还有疑问？直接问师傅（Ctrl+Enter 发送）；「🧙 师傅解惑」按功法 skill 把整题讲透",
           "buttons": [{"id": a, "label": b} for a, b in btns]}
    r = _resp(s, msgs, events, input=_remember(s, inp))
    c = _mreview_counts(qs)
    r["battle"] = {"label": "大比复盘 · 第%s季 · %s" % (s["season"], s["source"]), "total": len(qs), "position": i + 1,
                   "ok": c["✅"], "wrong": c["❌"], "blank": c["⚪"], "reviewed": len(done), "phase": "review"}
    r["replace"] = True
    if scroll_bottom:
        r["scroll"] = "bottom"
    return r


def _mreview_pq(s, q):
    """按试炼题的样子给师傅看：材料 + 题干（含选项）、答案、复盘解析"""
    stem = "\n".join(q.get("material_lines") or []) + ("\n\n" if q.get("material_lines") else "") + q["body"]
    return {"board": s["board"] or s["source"], "topic": s["source"], "stem": stem, "options": "（见题目）",
            "answer": q["correct"], "analysis": q["analysis"]}


def _mreview_action(g, s, act):
    qs, i = s["qs"], s["rpos"]
    if act == "mr_prev":
        s["rpos"] = max(0, i - 1)
    elif act == "mr_next":
        s["rpos"] = min(len(qs) - 1, i + 1)
    elif act == "mr_wrong":
        s["rpos"] = next((k for k in range(i + 1, len(qs)) if qs[k]["icon"] != "✅"), i)
    elif act.startswith("mr_board:"):
        _mreview_load(g, s, act.split(":", 1)[1])
        r = _mreview_show(g, s, head=True)
        r["title"] = s["title"]
        return r
    elif act.startswith("mr_explain:"):
        if act.split(":")[1] != str(i):
            raise TrainError("题目已经切换，请重新点")
        if not ai.available():
            return _mreview_show(g, s, extra=[_msg("npc", (_say(g, "试炼·解惑没AI") or "为师今日闭关（没连上 AI）。先把解析读三遍。")
                                                     + "\n（在“设置”里填 AI 的 API key 后，师傅就能按功法给你讲题。）")])
        q = qs[i]
        text, skill, used = _explain(g, _mreview_pq(s, q), {"answer": q["mine"] or "未作答"})
        s["explain"][str(i)] = text
        where = vault.save_tutor_note(g.paths, q["key"], text, g.t)
        note = ("📌 已写进这题的复盘笔记：%s 第 %s 题（再问一次会换成新的）" % (where, q["num"]) if where
                else "📌 没找到这道题的复盘文件，讲解没存下来")
        note += ("\n📜 依据 skill「%s」：%s" % (skill, "、".join(used[:8]) + (" 等 %d 个文件" % len(used) if len(used) > 8 else ""))
                 if used else "\n⚠ 这个板块没找到 skill 资料（%s），师傅只能按通用方法讲" % (skill or "未配置"))
        return _mreview_show(g, s, extra=[_msg("sys", note)], scroll_bottom=True)
    elif act in ("mr_close", "skip", "bank_pause"):
        c = _mreview_counts(qs)
        done = mock_reviewed(g, s["season"]).get(s["source"], [])
        text = "第%s季 · %s 复盘结束：这个板块复盘过 %d 题（这次看的 %d 题里答对 %d、答错 %d、没做 %d）。错题都在%s里，接着去%s。" % (
            s["season"], s["source"], len(done), len(qs), c["✅"], c["❌"], c["⚪"], g.T("nav.wrong")[2:], g.T("kill") + g.T("wrong"))
        return _resp(s, [_msg("sys", text), _msg("npc", _say(g, "试炼·复盘结束") or "复盘完了就去把错题斩干净。")], finished=True)
    else:
        raise TrainError("这一步请使用当前题目的按钮")
    return _mreview_show(g, s)


def _mreview_chat(g, s, text):
    i = s["rpos"]
    q = s["qs"][i]
    hist = s["chat"].setdefault(str(i), [])
    if not ai.available():
        return _mreview_show(g, s, extra=[_msg("me", text), _msg("npc", (_say(g, "试炼·解惑没AI") or "为师今日闭关（没连上 AI）。")
                                                                 + "\n（在“设置”里填 AI 的 API key 后才能追问。）")], scroll_bottom=True)
    pq = _mreview_pq(s, q)
    ctx = {"kind": "大比复盘", "title": "第%s季第%s题" % (s["season"], q["num"]), "board": pq["board"], "history": hist[-10:],
           "question": pq["stem"], "answer": q["correct"], "mine": q["mine"] or "没做", "reference": q["analysis"][:3000]}
    try:
        reply = ai.chat(prompts.discuss(g.persona, ctx, _skill_digest(g, pq["board"]), text), temperature=0.6, max_tokens=1500)
    except ai.AIError as e:
        raise TrainError("师傅没回话：%s" % e)
    hist += [{"role": "user", "content": text}, {"role": "assistant", "content": reply}]
    return _mreview_show(g, s, scroll_bottom=True)
