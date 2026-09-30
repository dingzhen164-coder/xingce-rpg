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

没填 API key 时：背诵 / 温养 / 心魔 退化为“自评模式”（程序比对口诀 + 学员自己判断思路）；论道 / 试剑 / 生成功法必须有 AI；
渡劫里的问道雷没有 AI 时换成心法雷。会话只存在内存里，结果在出结果那一刻就写进存档。
"""
import re
import uuid

from . import ai, prompts, skeleton, tutor, vault

SESSIONS = {}
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


def new_session(typ, title, task, **data):
    s = {"id": uuid.uuid4().hex[:12], "type": typ, "title": title, "task": task, **data}
    SESSIONS[s["id"]] = s
    return s


def get(sid):
    s = SESSIONS.get(sid)
    if not s:
        raise TrainError("这次修炼已经结束或程序重启过，请从功课列表重新开始")
    return s


def _recite_prompt(g, board, it, head):
    return (f"{head}：{board}「{it['name']}」。凭记忆写出这一{g.T('item')}的全部内容——"
            f"【术语】是{g.T('term')}，必须一字不差（共 {len(it['terms'])} 个）；【思路】说出大意即可（共 {len(it['thoughts'])} 条）。")


def _wrong_intro(g, q, head):
    return _msg("sys", f"{head}第{q['season']}季 · {q['source']} · 第{q['num']}题（上次你选了 {q['mine'] or '未作答'}）",
                blocks=vault.render_blocks(g.paths, q))


# ---------------------------------------------------------------- 开始
def start(g, task):
    """task：今日功课里的一项（dict），或临时构造的 {"type","board","target","title","id"}"""
    typ = task["type"]
    if typ not in ("chat", "skeleton") and g.resting():
        raise TrainError(f"{g.T('qi')}预警：还需调息 {g.resting()} 分钟。去喝口水、走两步，回来再修炼。")
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
    if typ == "apply":
        _need_ai(g.T("apply"))
        it = _item(g, task["target"])
        q = ai.chat_json(prompts.apply_question(g.persona, task["board"], it), temperature=0.7)
        s = new_session(typ, task["title"], task, iid=it["id"], board=task["board"], q=q)
        return _resp(s, [_msg("npc", f"{g.T('apply')}（考点：{it['name']}）：\n\n{q.get('题目', '')}")],
                     input=_remember(s, _text_input("先说你认出的考点和思路，再给答案")))
    if typ == "wrong":
        q = vault.find_question(g.paths, task["target"])
        if not q:
            raise TrainError("找不到这道题（复盘文件可能改名或删除了）")
        s = new_session(typ, task["title"], task, key=q["key"], board=task["board"])
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
def reply(g, sid, text):
    s = get(sid)
    text = (text or "").strip()
    if not text:
        raise TrainError("内容是空的")
    if is_tired(text):
        return tired_response(g, s, text)
    typ = s["type"]
    if typ in ("recite", "review", "speedrun"):
        return _grade_recite(g, s, text)
    if typ in ("tribulation", "alchemy"):
        return _gauntlet_answer(g, s, text)
    if typ == "feynman":
        return _feynman(g, s, text)
    if typ == "apply":
        return _apply(g, s, text)
    if typ == "wrong":
        return _wrong(g, s, text)
    if typ == "chat":
        return _chat(g, s, text)
    raise TrainError("这一步不需要输入文字，请点按钮")


def action(g, sid, act):
    """按钮：自评（self_ok / self_no）、功法（gen / final）、跳过（skip）"""
    s = get(sid)
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
        return _recite_finish(g, s, p["hit"], p["miss"], None, ok, "")
    raise TrainError("未知操作")


# ---------------------------------------------------------------- 背诵口诀（默写）
def _judge_recite(g, board, it, text):
    """返回 (hit, miss, coverage 或 None(需要自评), 点评, 错误说法)"""
    hit, miss = skeleton.check_terms(it, text)
    if not it["thoughts"]:
        return hit, miss, 1.0, "", []
    if not ai.available():
        return hit, miss, None, "", []
    r = ai.chat_json(prompts.recite_grade(g.persona, board, it, text, miss))
    marks = r.get("答到") or []
    got = sum(1 for x in marks[: len(it["thoughts"])] if x is True)
    return hit, miss, got / len(it["thoughts"]), r.get("点评", ""), r.get("错误说法") or []


def _recite_summary(g, it, hit, miss, cov, wrong_says):
    lines = [f"{g.T('term')} {len(hit)}/{len(it['terms'])}" + (f"，漏 / 错：{'、'.join(miss)}" if miss else "，全对 ✓")]
    if cov is not None and it["thoughts"]:
        lines.append(f"思路要点覆盖 {cov:.0%}")
    if wrong_says:
        lines.append("说错的地方：" + "；".join(wrong_says))
    return "\n".join(lines)


def _self_rate_buttons():
    return _buttons(("self_ok", "思路大体都说到了"), ("self_no", "有明显遗漏"))


def _grade_recite(g, s, text):
    it = _item(g, s["iid"])
    hit, miss, cov, comment, wrong_says = _judge_recite(g, s["board"], it, text)
    if cov is None:
        s["pending"] = {"hit": hit, "miss": miss}
        return _resp(s, [_msg("sys", _recite_summary(g, it, hit, miss, None, [])),
                         _msg("sys", it["text"], fold=f"{g.T('skeleton')}原文"),
                         _msg("npc", "没连 AI，思路部分你自己对照一下：大意都说到了吗？")], input=_self_rate_buttons())
    return _recite_finish(g, s, hit, miss, cov, None, comment, wrong_says)


def _recite_finish(g, s, hit, miss, cov, self_ok, comment, wrong_says=()):
    it = _item(g, s["iid"])
    ok = not miss and (self_ok if cov is None else cov >= g.rules.num("思路达标比例"))
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
    ok = bool(r.get("通过")) if "通过" in r else all(dims.values())
    ev = _drop_dup_npc(g.on_feynman(s["iid"], ok), reply_text)
    g.mark_done(s["task"], ok)
    dim_line = "　".join(f"{'✅' if v else '❌'}{k}" for k, v in dims.items())
    return _resp(s, [_msg("npc", reply_text), _msg("sys", (f"✨ {g.T('feynman')}通过　" if ok else "💥 还没讲透　") + dim_line),
                     _msg("sys", it["text"], fold=f"{g.T('skeleton')}原文")], ev, finished=True)


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
    return _resp(s, [_msg("sys", f"✨ {g.T('apply')}成功" if ok else f"💥 {g.T('apply')}失败"), _msg("npc", comment),
                     _msg("sys", f"参考答案：{q.get('参考答案', '')}\n参考思路：{q.get('参考思路', '')}", fold="参考答案")],
                 ev, finished=True)


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
    ok, iid, extra, r, answer_ok = _grade_wrong(g, s["key"], s["board"], text)
    if ok is None:
        s["pending"] = {"answer_ok": answer_ok}
        return _resp(s, extra, input=_buttons(("self_ok", "思路和答案都对"), ("self_no", "不对")))
    return _wrong_finish(g, s, ok, iid, extra, r)


def _wrong_finish(g, s, ok, iid, extra, r=None):
    ev = _drop_dup_npc(g.on_wrong(s["key"], s["board"], ok, iid), r and r.get("点评"))
    g.mark_done(s["task"], ok)
    head = f"⚔ {g.T('kill')}成功" if ok else f"💥 {g.T('wrong')}逃走了（{int(g.rules.num('回炉间隔天数'))} 天后{g.T('redo')}）"
    if r is not None:
        head += f"　答案{'✓' if r.get('答案正确') else '✗'}　思路{'✓' if r.get('思路正确') else '✗'}"
    if iid:
        head += f"　对应：{iid.split('::', 1)[1]}"
    return _resp(s, [_msg("sys", head)] + extra, ev, finished=True)


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
        hit, miss, cov, comment, _ = _judge_recite(g, step["board"], it, text)
        summary = _recite_summary(g, it, hit, miss, cov, [])
        if cov is None:
            s["pending"] = {"miss": miss}
            return _resp(s, [_msg("sys", summary), _msg("sys", it["text"], fold=f"{g.T('skeleton')}原文")],
                         input=_self_rate_buttons())
        ok = not miss and cov >= g.rules.num("思路达标比例")
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
        n_terms = sum(len(i["terms"]) for i in sk["items"])
        return _resp(s, [_msg("npc", f"「{b}」的{S}草稿在 `{rel}`：{len(sk['items'])} {I}、{n_terms} 个{g.T('term')}（术语）。"
                                     "去 Obsidian 里审一遍：删掉不需要的、补上老师强调的、确认【术语】标得对不对。改好了点“定稿”。")],
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
        digest = vault.skill_digest(g.paths, g.boards[b]["skill"])
        md = ai.chat(prompts.skeleton_gen(b, digest), max_tokens=4000, timeout=240)
        if not skeleton.save_draft(g.paths, b, g.boards[b]["skill"], md):
            raise TrainError(f"{S}已定稿，不会覆盖。要重做请先在文件里把状态改回“草稿”")
        g._skel.pop(b, None)
        sk = g.skel(b)
        n = len(sk["items"]) if sk else 0
        return _resp(s, [_msg("npc", f"草稿已写到 `训练/骨架/{b}.md`（{n} {I}）。去 Obsidian 里审改，改好点“定稿”。")],
                     [{"kind": "info", "msg": f"已生成「{b}」{S}草稿"}],
                     input=_buttons(("final", "已审改，定稿"), ("gen", "重新生成草稿"), ("skip", "稍后再说")))
    if act == "final":
        g._skel.pop(b, None)
        sk = g.skel(b)
        if not sk or not sk["items"]:
            raise TrainError(f"{S}里没有解析到任何一{I}（每一{I}需要一个 `## 标题`）")
        bad = [i["name"] for i in sk["items"] if not i["terms"] and not i["thoughts"]]
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
