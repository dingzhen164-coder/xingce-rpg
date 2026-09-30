"""
训练会话：网页上一次“点任务 → 对话 → 出结果”的流程。

会话类型（session["type"]）：
    recite    默写（学习）          review / speedrun  复查 / 新周目速通（也是默写）
    feynman   费曼讲解（多轮追问）   apply     应用小题（AI 出题 → 学员答 → AI 判）
    wrong     错题判断               trial     突破试炼（连续默写多个大项）
    skeleton  生成 / 定稿骨架        chat      和导师聊天

每个函数返回给网页的统一结构（api.py 原样转成 JSON）：
    {"session": id, "type": 类型, "title": 标题,
     "messages": [{"who": "npc"|"sys"|"me", "text": 文字, "blocks": [题目块], "fold": 折叠标题}],
     "events":   engine 返回的事件（+经验 / 升级 / 导师台词）,
     "input":    {"mode": "text"|"buttons"|"none", "placeholder": 提示, "buttons": [{"id", "label"}]},
     "finished": 是否结束}

没填 API key 时：默写 / 复查 / 突破 / 错题 退化为“自评模式”（程序比对术语 + 学员自己判断思路），
费曼 / 应用 / 生成骨架 必须有 AI。
会话只存在内存里（程序重启就没了），训练结果在出结果那一刻就写进存档，所以不会丢。
"""
import random
import re
import uuid

from . import ai, prompts, skeleton, tutor, vault

SESSIONS = {}
TIRED_WORDS = ("累", "不想学", "学不动", "好烦", "烦死", "崩溃", "坚持不下去", "想放弃", "太难了", "不想练")


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


def _item(g, iid):
    it = g.find_item(iid)
    if not it:
        raise TrainError("咒文书（骨架）里找不到这一章（可能改过标题或还没定稿），请点“重新生成今日委托”")
    return it


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
    inp = s.get("last_input") or _text_input("")
    return _resp(s, [_msg("npc", reply), _msg("sys", "缓一缓再继续；想休息也可以去“编年史”页用休憩卷轴，或者直接关掉——今天学够保底分钟，圣火就不会熄。")],
                 input=inp)


def new_session(typ, title, task, **data):
    s = {"id": uuid.uuid4().hex[:12], "type": typ, "title": title, "task": task, **data}
    SESSIONS[s["id"]] = s
    return s


def get(sid):
    s = SESSIONS.get(sid)
    if not s:
        raise TrainError("这次训练已经结束或程序重启过，请从任务列表重新开始")
    return s


# ---------------------------------------------------------------- 开始
def start(g, task):
    """task：今日任务里的一项（dict），或临时构造的 {"type","board","target","title","id"}"""
    typ = task["type"]
    if typ in ("recite", "review", "speedrun"):
        it = _item(g, task["target"])
        s = new_session(typ, task["title"], task, iid=it["id"], board=task["board"])
        return _resp(s, [_msg("npc", _recite_prompt(task["board"], it, typ))],
                     input=_remember(s, _text_input("凭记忆咏唱这一章咒文的全部内容，写完按 Ctrl+Enter 提交")))
    if typ == "feynman":
        _need_ai("费曼讲解")
        it = _item(g, task["target"])
        s = new_session(typ, task["title"], task, iid=it["id"], board=task["board"], history=[], asked=0)
        return _resp(s, [_msg("npc", f"传授奥义时间。把「{it['name']}」讲给学姐听：它是什么、题目里怎么认出来、怎么用、容易错在哪。"
                                     "就当学姐是刚入学的新生～")],
                     input=_remember(s, _text_input("像给新生上课一样讲出来")))
    if typ == "apply":
        _need_ai("应用小题")
        it = _item(g, task["target"])
        q = ai.chat_json(prompts.apply_question(g.persona, task["board"], it), temperature=0.7)
        s = new_session(typ, task["title"], task, iid=it["id"], board=task["board"], q=q)
        return _resp(s, [_msg("npc", f"实战演练（考点：{it['name']}）——木桩已经立好了：\n\n{q.get('题目', '')}")],
                     input=_remember(s, _text_input("先说你认出的考点和思路，再给答案")))
    if typ == "wrong":
        q = vault.find_question(g.paths, task["target"])
        if not q:
            raise TrainError("找不到这道题（复盘文件可能改名或删除了）")
        s = new_session(typ, task["title"], task, key=q["key"], board=task["board"])
        blocks = vault.render_blocks(g.paths, q)
        return _resp(s, [_msg("sys", f"⚔ 魔物现身！第{q['season']}季 · {q['source']} · 第{q['num']}题（上次你选了 {q['mine'] or '未作答'}，被它咬了一口）", blocks=blocks),
                         _msg("npc", "用咒文书里的方法打它：这是什么题型 → 用什么方法 → 关键依据落在哪句话 → 选哪个。")],
                     input=_remember(s, _text_input("题型 → 方法 → 依据 → 答案")))
    if typ == "trial":
        return _start_trial(g, task)
    if typ == "skeleton":
        return _start_skeleton(g, task)
    if typ == "chat":
        s = new_session("chat", "和导师聊聊", task, history=[])
        s["history"] = []
        return _resp(s, [_msg("npc", tutor.cached_greeting(g) or g.say(g.mood()) or "说吧，找学姐什么事？")],
                     input=_remember(s, _text_input("想说什么都行：问方法、让学姐帮你排计划、或者只是聊两句")))
    raise TrainError(f"未知的任务类型：{typ}")


RESULT_SCENES = {"默写通过", "默写未过", "费曼通过", "费曼未过", "错题判对", "错题判错"}


def _drop_dup_npc(ev, comment):
    """AI 已经给了点评时，去掉台词库里的“结果类”台词，避免导师连说两句"""
    if not comment:
        return ev
    return [e for e in ev if not (e.get("kind") == "npc" and e.get("scene") in RESULT_SCENES)]


def _remember(s, inp):
    s["last_input"] = inp
    return inp


def _need_ai(what):
    if not ai.available():
        raise TrainError(f"{what}需要 AI：请先在“设置”里填写 API key")


def _recite_prompt(board, it, typ):
    head = {"recite": "咏唱咒文", "review": "驱散遗忘", "speedrun": "重温咒文", "trial": "晋升试炼"}.get(typ, "咏唱咒文")
    return (f"{head}：{board}「{it['name']}」。凭记忆咏唱这一章咒文的全部内容——"
            f"【术语】是咒文真名，必须一字不差（共 {len(it['terms'])} 个）；【思路】说出大意即可（共 {len(it['thoughts'])} 条）。")


# ---------------------------------------------------------------- 回复
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
    if typ == "trial":
        return _trial_answer(g, s, text)
    if typ == "feynman":
        return _feynman(g, s, text)
    if typ == "apply":
        return _apply(g, s, text)
    if typ == "wrong":
        return _wrong(g, s, text)
    if typ == "chat":
        return _chat(g, s, text)
    raise TrainError("这个训练不需要输入文字，请点按钮")


def action(g, sid, act):
    """按钮操作：自评（self_ok / self_no）、骨架（gen / final）、跳过（skip）"""
    s = get(sid)
    if act == "skip":
        return _resp(s, [_msg("sys", "已跳过，这项任务留在列表里。")], finished=True)
    if s["type"] == "skeleton":
        return _skeleton_action(g, s, act)
    if act in ("self_ok", "self_no") and s.get("pending"):
        ok = act == "self_ok"
        p = s.pop("pending")
        if s["type"] == "trial":
            return _trial_record(g, s, ok and not p["miss"])
        if s["type"] == "wrong":
            return _wrong_finish(g, s, ok and p.get("answer_ok", True), "", [])
        return _recite_finish(g, s, p["hit"], p["miss"], None, ok, "")
    raise TrainError("未知操作")


# ---------------------------------------------------------------- 默写
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


def _recite_summary(it, hit, miss, cov, wrong_says):
    lines = [f"咒文真名 {len(hit)}/{len(it['terms'])}" + (f"，漏 / 错：{'、'.join(miss)}" if miss else "，全对 ✓")]
    if cov is not None and it["thoughts"]:
        lines.append(f"思路要点覆盖 {cov:.0%}")
    if wrong_says:
        lines.append("说错的地方：" + "；".join(wrong_says))
    return "\n".join(lines)


def _grade_recite(g, s, text):
    it = _item(g, s["iid"])
    hit, miss, cov, comment, wrong_says = _judge_recite(g, s["board"], it, text)
    if cov is None:  # 自评
        s["pending"] = {"hit": hit, "miss": miss}
        return _resp(s, [_msg("sys", _recite_summary(it, hit, miss, None, [])),
                         _msg("sys", it["text"], fold="咒文书原文"),
                         _msg("npc", "没连 AI，思路部分你自己对照一下：大意都说到了吗？")],
                     input=_buttons(("self_ok", "思路大体都说到了"), ("self_no", "有明显遗漏")))
    return _recite_finish(g, s, hit, miss, cov, None, comment, wrong_says)


def _recite_finish(g, s, hit, miss, cov, self_ok, comment, wrong_says=()):
    it = _item(g, s["iid"])
    need = g.rules.num("思路达标比例")
    ok = not miss and (self_ok if cov is None else cov >= need)
    ev = _drop_dup_npc(g.on_recite(s["iid"], ok, s["type"]), comment)
    g.mark_done(s["task"], ok)
    msgs = [_msg("sys", ("✨ 咏唱成功\n" if ok else "💥 咏唱失败\n") + _recite_summary(it, hit, miss, cov, list(wrong_says)))]
    if comment:
        msgs.append(_msg("npc", comment))
    msgs.append(_msg("sys", it["text"], fold="咒文书原文"))
    return _resp(s, msgs, ev, finished=True)


# ---------------------------------------------------------------- 突破试炼
def _start_trial(g, task):
    gate = int(task["target"])
    gates = sorted(int(x) for x in g.rules.nums("突破等级"))
    rank = gates.index(gate) if gate in gates else 0
    if rank == 0 and g.current_batch() is not None:
        boards = g.batch_boards(g.current_batch())
    else:
        boards = list(g.boards)
    pool = [it for b in boards for it in g.final_items(b)
            if g.state["items"].get(it["id"], {}).get("level", 0) >= 1]
    if rank >= 2:
        redo = sum(1 for w in g.state["wrong"].values() if w["status"] == "redo")
        if redo:
            raise TrainError(f"这一关要求回炉清单清零，现在还有 {redo} 道回炉题")
    if not pool:
        raise TrainError("还没有能咏唱的咒文，先去学几章再来挑战试炼")
    n = min(len(pool), int(g.rules.num("突破题数")))
    queue = [it["id"] for it in random.sample(pool, n)]
    s = new_session("trial", task["title"], task, gate=gate, queue=queue, i=0, passed=[])
    return _trial_next(g, s, [_msg("npc", f"晋升试炼开始。学姐随机抽 {n} 章咒文让你咏唱，成功率 ≥ {g.rules.num('突破通过率'):.0%} 才能晋升。别让学姐失望哦～")])


def _trial_next(g, s, msgs):
    if s["i"] >= len(s["queue"]):
        ev = g.on_trial(s["gate"], s["passed"], len(s["queue"]))
        ok = s["gate"] in g.state["gates"]
        g.mark_done(s["task"], ok)
        msgs.append(_msg("sys", f"试炼结束：{len(s['passed'])}/{len(s['queue'])} 章咏唱成功"))
        return _resp(s, msgs, ev, finished=True)
    iid = s["queue"][s["i"]]
    it = _item(g, iid)
    msgs.append(_msg("npc", f"第 {s['i'] + 1}/{len(s['queue'])} 个：" + _recite_prompt(iid.split('::')[0], it, "trial")))
    return _resp(s, msgs, input=_remember(s, _text_input("凭记忆写出全部内容")))


def _trial_answer(g, s, text):
    iid = s["queue"][s["i"]]
    it = _item(g, iid)
    hit, miss, cov, comment, _ = _judge_recite(g, iid.split("::")[0], it, text)
    if cov is None:
        s["pending"] = {"hit": hit, "miss": miss}
        return _resp(s, [_msg("sys", _recite_summary(it, hit, miss, None, [])), _msg("sys", it["text"], fold="标准")],
                     input=_buttons(("self_ok", "思路大体都说到了"), ("self_no", "有明显遗漏")))
    s["_last_ok"] = not miss and cov >= g.rules.num("思路达标比例")
    return _trial_record(g, s, s["_last_ok"], _recite_summary(it, hit, miss, cov, []))


def _trial_record(g, s, ok, summary=""):
    iid = s["queue"][s["i"]]
    if ok:
        s["passed"].append(iid)
    s["i"] += 1
    return _trial_next(g, s, [_msg("sys", ("✅ " if ok else "❌ ") + (summary or ""))])


# ---------------------------------------------------------------- 费曼
def _feynman(g, s, text):
    it = _item(g, s["iid"])
    s["history"].append({"role": "user", "content": text})
    max_rounds = int(g.rules.num("费曼追问轮数"))
    left = max(0, max_rounds - s["asked"])
    r = ai.chat_json(prompts.feynman_turn(g.persona, s["board"], it, s["history"], left), temperature=0.5)
    reply_text = r.get("reply", "")
    s["history"].append({"role": "assistant", "content": reply_text})
    done = bool(r.get("done")) or left == 0
    if not done:
        s["asked"] += 1
        return _resp(s, [_msg("npc", reply_text)], input=_remember(s, _text_input("回答追问")))
    dims = r.get("维度") or {}
    ok = bool(r.get("通过")) if "通过" in r else all(dims.values())
    ev = _drop_dup_npc(g.on_feynman(s["iid"], ok), reply_text)
    g.mark_done(s["task"], ok)
    dim_line = "　".join(f"{'✅' if v else '❌'}{k}" for k, v in dims.items())
    return _resp(s, [_msg("npc", reply_text), _msg("sys", ("✨ 奥义传授成功　" if ok else "💥 还没讲透　") + dim_line),
                     _msg("sys", it["text"], fold="咒文书原文")], ev, finished=True)


# ---------------------------------------------------------------- 应用
def _apply(g, s, text):
    it = _item(g, s["iid"])
    q = s["q"]
    r = ai.chat_json(prompts.apply_grade(g.persona, s["board"], it, q.get("题目", ""), q.get("参考答案", ""),
                                         q.get("参考思路", ""), text))
    ok = bool(r.get("通过"))
    ev = g.on_apply(s["iid"], ok)
    g.mark_done(s["task"], ok)
    return _resp(s, [_msg("sys", "✨ 演练成功" if ok else "💥 演练失败"), _msg("npc", r.get("点评", "")),
                     _msg("sys", f"参考答案：{q.get('参考答案', '')}\n参考思路：{q.get('参考思路', '')}", fold="参考答案")],
                 ev, finished=True)


# ---------------------------------------------------------------- 错题
def _answer_letter(text):
    m = re.findall(r"(?<![A-Za-z])([A-Ha-h])(?![A-Za-z])", text)
    return m[-1].upper() if m else ""


def _wrong(g, s, text):
    q = vault.find_question(g.paths, s["key"])
    if not q:
        raise TrainError("找不到这道题")
    names = [it["name"] for it in g.final_items(s["board"])]
    if not ai.available():
        letter = _answer_letter(text)
        s["pending"] = {"answer_ok": letter == q["correct"].upper() if letter else True}
        return _resp(s, [_msg("sys", f"正确答案：{q['correct']}" + (f"（你答 {letter}）" if letter else "")),
                         _msg("sys", q["analysis"] or "（这题还没有解析）", fold="复盘解析"),
                         _msg("npc", "没连 AI，对照解析自己判断：思路和答案都对吗？")],
                     input=_buttons(("self_ok", "思路和答案都对"), ("self_no", "不对")))
    qtext = "\n".join(b["v"] for b in vault.render_blocks(g.paths, q) if b["t"] == "text")
    r = ai.chat_json(prompts.wrong_grade(g.persona, s["board"], qtext, q["correct"], q["mine"], q["analysis"], names, text))
    ok = bool(r.get("答案正确")) and bool(r.get("思路正确"))
    iname = (r.get("对应大项") or "").strip()
    iid = skeleton.item_id(s["board"], iname) if iname in names else ""
    extra = [_msg("npc", r.get("点评", "")),
             _msg("sys", f"正确答案：{q['correct']}\n正确思路：{r.get('正确思路', '')}", fold="正确思路"),
             _msg("sys", q["analysis"] or "（这题还没有解析）", fold="复盘解析")]
    return _wrong_finish(g, s, ok, iid, extra, r)


def _wrong_finish(g, s, ok, iid, extra, r=None):
    ev = _drop_dup_npc(g.on_wrong(s["key"], s["board"], ok, iid), r and r.get("点评"))
    g.mark_done(s["task"], ok)
    head = "⚔ 讨伐成功" if ok else "💥 魔物逃走了（两天后卷土重来）"
    if r is not None:
        head += f"　答案{'✓' if r.get('答案正确') else '✗'}　思路{'✓' if r.get('思路正确') else '✗'}"
    if iid:
        head += f"　对应大项：{iid.split('::', 1)[1]}"
    return _resp(s, [_msg("sys", head)] + extra, ev, finished=True)


# ---------------------------------------------------------------- 骨架
def _start_skeleton(g, task):
    b = task["board"]
    s = new_session("skeleton", task["title"], task, board=b)
    sk = g.skel(b)
    rel = f"训练/骨架/{b}.md"
    if sk and sk["final"]:
        return _resp(s, [_msg("sys", f"「{b}」咒文书已定稿（{len(sk['items'])} 章）。")], finished=True)
    if sk:
        n_terms = sum(len(i["terms"]) for i in sk["items"])
        return _resp(s, [_msg("npc", f"「{b}」的咒文书草稿在 `{rel}`：{len(sk['items'])} 章、{n_terms} 个咒文真名（术语）。"
                                     "去 Obsidian 里审一遍：删掉不需要的、补上老师强调的、确认【术语】标得对不对。改好了点“定稿”。")],
                     input=_buttons(("final", "已审改，定稿"), ("gen", "重新生成草稿"), ("skip", "稍后再说")))
    has = vault.skill_dir(g.paths, g.boards.get(b, {}).get("skill"))
    if not has:
        return _resp(s, [_msg("sys", f"找不到「{b}」的 skill 文件夹（{g.boards.get(b, {}).get('skill')}），"
                                     f"可以在 Obsidian 里手写 `{rel}`（格式见 训练/骨架/ 里其他文件或 DESIGN.md）。")],
                     finished=True)
    return _resp(s, [_msg("npc", f"「{b}」还没有咒文书。学姐从解题 skill「{g.boards[b]['skill']}」里帮你提炼一份草稿，你再审改。大约需要 30–60 秒。")],
                 input=_buttons(("gen", "生成草稿"), ("skip", "稍后再说")))


def _skeleton_action(g, s, act):
    b = s["board"]
    if act == "gen":
        _need_ai("编纂咒文书（生成骨架）")
        digest = vault.skill_digest(g.paths, g.boards[b]["skill"])
        md = ai.chat(prompts.skeleton_gen(b, digest), max_tokens=4000, timeout=240)
        if not skeleton.save_draft(g.paths, b, g.boards[b]["skill"], md):
            raise TrainError("咒文书已定稿，不会覆盖。要重做请先在文件里把状态改回“草稿”")
        g._skel.pop(b, None)
        return _after_gen(g, s)
    if act == "final":
        g._skel.pop(b, None)
        sk = g.skel(b)
        if not sk or not sk["items"]:
            raise TrainError("咒文书里没有解析到任何章节（每一章需要一个 `## 标题`）")
        bad = [i["name"] for i in sk["items"] if not i["terms"] and not i["thoughts"]]
        skeleton.set_final(g.paths, b, True)
        g._skel.pop(b, None)
        g.mark_done(s["task"], True)
        msg = f"「{b}」咒文书已定稿：{len(sk['items'])} 章。明天的委托会开始安排它；也可以回营地点“重新生成今日委托”马上开始。"
        if bad:
            msg += f"\n注意：这些章节下面没有条目：{'、'.join(bad)}"
        return _resp(s, [_msg("sys", msg)], [{"kind": "info", "msg": "咒文书定稿"}], finished=True)
    raise TrainError("未知操作")


def _after_gen(g, s):
    b = s["board"]
    sk = g.skel(b)
    n = len(sk["items"]) if sk else 0
    return _resp(s, [_msg("npc", f"草稿已写到 `训练/骨架/{b}.md`（{n} 章）。去 Obsidian 里审改，改好点“定稿”。")],
                 [{"kind": "info", "msg": f"已生成「{b}」咒文书草稿"}],
                 input=_buttons(("final", "已审改，定稿"), ("gen", "重新生成草稿"), ("skip", "稍后再说")))


# ---------------------------------------------------------------- 聊天
def _chat(g, s, text):
    s["history"].append({"role": "user", "content": text})
    if not ai.available():
        return _resp(s, [_msg("npc", g.say(g.mood()) or "（没连 AI，学姐只会说台词库里的话）")], input=_text_input(""))
    cur = g.current_batch()
    knowledge = "\n".join(f"{b}：" + "、".join(it["name"] for it in g.final_items(b))
                          for b in (g.batch_boards(cur) if cur is not None else []) if g.final_items(b))
    r = ai.chat(prompts.free_chat(g.persona, s["history"][-12:], g.tutor_context(), knowledge),
                temperature=0.8, max_tokens=500)
    s["history"].append({"role": "assistant", "content": r})
    return _resp(s, [_msg("npc", r)], input=_text_input(""))
