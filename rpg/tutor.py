"""
AI 导师（默认“艾琳学姐”）在关键时刻现场说话。

- 开场问候：每天第一次打开时由 AI 结合学员现状（engine.tutor_context）生成，当天缓存在存档的 tutor_greet 里，
  刷新网页不会重复花钱；
- 升级、晋升、通关、今日达标 / 超额、用休憩卷轴：engine 先放一句台词库里的备用台词（npc 事件，带 scene），
  这里把它换成 AI 现场说的话；
- 默写 / 错题等“结果类”点评由判题时的 AI 直接给出（见 trainer），不经过这里。

条件：规则“导师AI: 开”且填了 API key；AI 出错或超时就保留备用台词，不影响训练。
"""
from . import ai, prompts

AI_SCENES = {
    "升级": "学员刚升级",
    "突破待挑战": "学员经验已满，但要先通过晋升试炼才能继续升级",
    "突破成功": "学员刚通过晋升试炼，获得了新称号",
    "批次通关": "学员刚打通了一整层地下城（一批板块全部精通）",
    "周目通关": "学员刚完成了一整轮征程（全部板块精通一遍）",
    "今日达标": "学员今天的学习时长刚刚达标",
    "今日超额": "学员今天学习时长超过目标的 1.5 倍",
    "请假": "学员今天用了一张休憩卷轴（请假），可能有事或身体不适，要体贴，不要吐槽",
}


def enabled(g):
    return ai.available() and g.rules.on("导师AI")


def _say(g, scene_desc, extra=""):
    return ai.chat(prompts.tutor_line(g.persona, scene_desc, g.tutor_context(), extra),
                   temperature=0.9, max_tokens=300, timeout=25).strip().strip("“”\"")


def enrich(g, events):
    """把事件里的里程碑台词换成 AI 现场说的话（一次最多换一句，其余保留备用台词，避免等太久）"""
    if not enabled(g):
        return events
    for e in events:
        if e.get("kind") == "npc" and e.get("scene") in AI_SCENES:
            extra = ""
            lv = next((x for x in events if x.get("kind") == "level"), None)
            if lv:
                extra = f"新等级 Lv.{lv['v']}，称号「{lv['title']}」" + ("（刚晋升了新称号！）" if lv.get("promoted") else "")
            try:
                e["msg"] = _say(g, AI_SCENES[e["scene"]], extra) or e["msg"]
            except ai.AIError:
                pass
            break
    return events


def greeting(g):
    """今天的开场问候：有缓存用缓存；否则 AI 生成并缓存；AI 不可用返回 None"""
    c = g.state.get("tutor_greet") or {}
    if c.get("d") == g.t and c.get("text"):
        return c["text"]
    if not enabled(g):
        return None
    scene = {"开场·新手": "第一次见到这位新学员", "开场·回归": "学员缺席了好几天后回来了",
             "开场·落后": "今天第一次见面，学员落后于命运之线", "开场·领先": "今天第一次见面，学员领先于命运之线"}.get(
        g.mood(), "今天第一次见面的开场问候")
    try:
        text = _say(g, scene)
    except ai.AIError:
        return None
    g.state["tutor_greet"] = {"d": g.t, "text": text}
    return text


def cached_greeting(g):
    c = g.state.get("tutor_greet") or {}
    return c["text"] if c.get("d") == g.t and c.get("text") else None
