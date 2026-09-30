"""
AI 导师（修仙：师尊劭神韵；玄幻：艾琳学姐）在关键时刻现场说话。

- 开场问候：每天第一次打开时由 AI 结合学员现状（engine.tutor_context）生成，当天缓存在存档的 tutor_greet 里，
  刷新网页不会重复花钱；
- 突破、渡劫、灵根、出关、成丹、今日达标 / 超额、告假……（见 AI_SCENES）：engine 先放一句台词库里的备用台词（npc 事件，带 scene），
  这里把它换成 AI 现场说的话；
- 默写 / 错题等“结果类”点评由判题时的 AI 直接给出（见 trainer），不经过这里。

条件：规则“导师AI: 开”且填了 API key；AI 出错或超时就保留备用台词，不影响训练。
"""
from . import ai, prompts

# 这些时刻由 AI 现场说话（按重要程度排序：一次事件里有多个时只换最靠前的一句）
AI_SCENES = {
    "渡劫成功": "学员刚渡劫成功，突破了大境界",
    "渡劫失败": "学员刚渡劫失败，道基受损，需要疗伤、冷却几天——要安慰并指出失败的那一关该怎么补",
    "周目通关": "学员刚完成了一整轮（全部板块修炼一遍）",
    "批次通关": "学员刚打通了一整批板块",
    "灵根激活": "学员刚觉醒了一条新的灵根（一个板块修炼圆满或正确率达标）",
    "瓶颈": "学员修为已到大境界门槛，进入瓶颈，需要满足条件后渡劫——告诉学员还差哪些条件",
    "小境界提升": "学员的小境界刚提升",
    "出关": "学员刚结束闭关，请点评这次闭关的收获",
    "成丹": "学员刚加练完一炉，炼成并服下丹药",
    "宗门大比": "学员刚记录了一次模考（宗门大比）成绩，请点评（与自己的境界比较）",
    "灵根晋阶": "学员某条灵根的品阶提升了",
    "灵根跌落": "学员某条灵根的品阶跌落了（该板块最近正确率下降）",
    "走火入魔": "学员连续修炼太久或连续失败太多次，被强制调息——要关心并让学员休息",
    "顿悟": "学员刚才触发了顿悟，获得额外修为",
    "周常完成": "学员完成了本周全部周常",
    "今日超额": "学员今天学习时长超过目标的 1.5 倍",
    "今日达标": "学员今天的学习时长刚刚达标",
    "护心丹": "学员昨天断了修炼，护心丹自动保住了连续打卡",
    "请假": "学员今天用了请假（告假），可能有事或身体不适，要体贴，不要训斥",
}
ORDER = list(AI_SCENES)


def enabled(g):
    return ai.available() and g.rules.on("导师AI")


def _say(g, scene_desc, extra=""):
    return ai.chat(prompts.tutor_line(g.persona, scene_desc, g.tutor_context(), extra),
                   temperature=0.9, max_tokens=300, timeout=25).strip().strip("“”\"")


def enrich(g, events):
    """把事件里的里程碑台词换成 AI 现场说的话（一次最多换一句——最重要的那句，其余保留备用台词，避免等太久）"""
    cands = [e for e in events if e.get("kind") == "npc" and e.get("scene") in AI_SCENES]
    if not cands:
        return events
    e = min(cands, key=lambda x: ORDER.index(x["scene"]))
    keep = {id(e)}
    # 同一批事件里其余的里程碑台词只保留最重要的一句，免得导师一口气说好几段
    events = [x for x in events if not (x.get("kind") == "npc" and x.get("scene") in AI_SCENES and id(x) not in keep)]
    if not enabled(g):
        return events
    extra = e.get("extra", "")
    realm = next((x for x in events if x.get("kind") == "realm"), None)
    if realm:
        extra += f" 新境界：{realm['name']}（{realm['score']} 分）" + ("，突破了大境界！" if realm.get("major") else "")
    try:
        e["msg"] = _say(g, AI_SCENES[e["scene"]], extra) or e["msg"]
    except ai.AIError:
        pass
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
