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

from . import question_bank, ai, prompts, skeleton, tutor, vault

SESSIONS = {}
FINISHED = {}   # 刚结束的会话 {id: (类型, 结束时间)}：结束后看解析的几分钟也算修炼时间
STUDY_TYPES = ("recite", "review", "speedrun", "feynman", "example", "apply", "wrong", "tribulation", "alchemy", "bank", "bank_review")
REVIEW_GRACE = 180  # 秒


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
            + (f"{g.T('term')}（【口诀】）共 {len(it['verses'])} 句，必须一字不差；" if it.get("verses") else "")
            + (f"列全分类清单（共 {len(it['terms'])} 个），" if it["terms"] else "")
            + f"再用自己的话讲思路（共 {len(it['thoughts'])} 条）。允许同义表达与不同顺序，含义要对应，不能混淆上位分类和下位方法。")


def _wrong_intro(g, q, head):
    return _msg("sys", f"{head}第{q['season']}季 · {q['source']} · 第{q['num']}题（上次你选了 {q['mine'] or '未作答'}）",
                blocks=vault.render_blocks(g.paths, q))


# ---------------------------------------------------------------- 开始
def start(g, task):
    """task：今日功课里的一项（dict），或临时构造的 {"type","board","target","title","id"}"""
    typ = task["type"]
    if typ not in ("chat", "skeleton") and g.resting():
        raise TrainError(f"{g.T('qi')}预警：还需调息 {g.resting()} 分钟。去喝口水、走两步，回来再修炼。")
    if typ in ("bank", "bank_review"):
        return _start_bank(g, task)
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
        if not task.get("target"):   # 修炼殿里自选板块斩心魔：挑这个板块最该斩的一只（到期回炉 > 没交手过 > 其余）
            pool = sorted(g._pool_wrong([task["board"]]))
            if not pool:
                raise TrainError(f"「{task['board']}」还没有{g.T('wrong')}（模考板块复盘里做错的题）")
            task = dict(task, target=pool[0][2])
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
    if s.get("discuss"):
        return _discuss_reply(g, s, text)
    typ = s["type"]
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


def action(g, sid, act):
    """按钮：自评（self_ok / self_no）、功法（gen / final）、跳过（skip）"""
    s = get(sid)
    if s["type"] in ("bank", "bank_review"):
        return _bank_action(g, s, act)
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
def _discuss_input():
    return {"mode": "text", "placeholder": "还有哪里不懂？直接问师傅（会参照这个板块的 skill），Ctrl+Enter 发送",
            "buttons": [{"id": "ask_explain", "label": "🧙 师傅解惑"}, {"id": "discuss_end", "label": "结束复盘"}]}


def _to_discuss(g, s, messages, events, ctx):
    """判完分不马上关门：进入复盘，可以点“师傅解惑”或继续追问；点“结束复盘”才算这次修炼结束"""
    s["discuss"] = dict(ctx, board=s.get("board", ""), history=[])
    return _resp(s, messages + [_msg("sys", "可以继续复盘：点「🧙 师傅解惑」让师傅按功法讲透，或者直接打字追问。")],
                 events, input=_remember(s, _discuss_input()))


def _skill_digest(g, board):
    skill = g.boards.get(board, {}).get("skill") or SIDE_SKILLS.get(board)
    return vault.skill_digest(g.paths, skill) if skill else ""


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
    return _resp(s, _discuss_ask(g, s, text), input=_remember(s, _discuss_input()))


def _discuss_action(g, s, act):
    if act == "ask_explain":
        return _resp(s, [_msg("me", "🧙 师傅，这题给我讲透。")] + _discuss_ask(g, s, "请按 skill 的方法把这道题完整讲一遍"),
                     input=_remember(s, _discuss_input()))
    if act in ("discuss_end", "skip"):
        return _resp(s, [_msg("npc", _say(g, "试炼·复盘结束") or "复盘完了就去下一项。")], finished=True)
    raise TrainError("这一步请打字追问，或点「师傅解惑」/「结束复盘」")


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
    run.setdefault('reasoning', task['board'] == '论证逻辑')   # 整套试炼按套刷，统一用选项按钮
    # 选项按钮的组按“考试”来：全部选完交卷才判分，再逐题复盘；写拆题过程的组仍然一题一判（要逐题审方法）
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


def _review_show(g, s, run, events=None, extra=None, head=False):
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
    rr = _bank_resp(g, s, run, msgs, events, _buttons(*btns))
    rr['replace'] = True
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
        run.setdefault('explain', {})[str(i)] = _explain(g, qs[i], res[i])
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
    """师傅解惑：按这道题所属板块的 skill 讲题；没连 AI 时给一句台词，提示先看解析"""
    skill = g.boards.get(q['board'], {}).get('skill') or SIDE_SKILLS.get(q['board'])
    digest = vault.skill_digest(g.paths, skill) if skill else ''
    try:
        return ai.chat(prompts.bank_explain(g.persona, q, r['answer'], digest), temperature=0.6, max_tokens=1500)
    except ai.AIError as e:
        raise TrainError('师傅没回话：%s' % e)


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


def _bank_reply(g, s, text):
    run = question_bank.state(g)["runs"].get(s["board"])
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
