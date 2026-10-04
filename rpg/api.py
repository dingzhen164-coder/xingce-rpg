"""
HTTP 接口：把 engine / trainer / store 暴露给网页（web/app.js）。只监听 127.0.0.1，外网访问不到。

每个请求的流程：拿全局锁 → 读配置和存档 → 建 Game → 做事 → housekeeping（检查通关）→ 存档 → 返回 JSON。
配置文件每次都重新读，所以用户在 Obsidian 里改了规则，刷新网页就生效。

接口一览（GET 无参数，POST 请求体是 JSON）：
    GET  /api/dashboard            面板 + 今日任务 + 角色信息 + 提醒
    POST /api/tutor/greet          AI 导师今天的开场问候（每天生成一次并缓存）
    POST /api/theme                {"theme": "修仙"|"玄幻"}  切换风格
    POST /api/retreat/start        {"board", "minutes"}  闭关；POST /api/retreat/end 提前出关
    POST /api/plan/regenerate      重新生成今日任务
    POST /api/session/start        {"task_id"} 或 {"task": {type, board, target, title}} 开始修炼
                                   （type 还可以是 tribulation 渡劫、alchemy 炼丹(board)、chat 聊天）
    POST /api/session/reply        {"session", "text"}      提交文字
    POST /api/session/action       {"session", "action"}    点按钮
    GET  /api/skeletons            各板块骨架与每个大项的掌握度
    GET  /api/wrong                错题池统计
    POST /api/heartbeat            {"seconds", "session"}  网页每 30 秒上报；只有正在修炼的会话才计时
    POST /api/leave                用请假卡
    POST /api/boss                 {"name", "score", "kind": "大比"|"飞升", "result"?}  宗门大比（模考）/ 飞升大典（国考）
    GET  /api/idioms               藏经阁·成语实词录：按首字拼音首字母排的词条
    POST /api/idioms/backfill      把以前做过的逻辑填空题一次收进成语实词录
    POST /api/idioms/edit          {"word", "new_word"?, "sources": {"0": {"meaning", "compare"}}}  修改词条
    POST /api/idioms/delete        {"word"}  删除词条（以后收录也不再收回来）
    POST /api/idioms/tutor         {"word"}  师傅答疑：AI 写一句话辨析，替换原辨析
    GET  /api/mock                 宗门大比：各季模考成绩、六大模块正确率 / 得分 / 用时、走势
    POST /api/mock/marks/scan      {"season", "images": [base64]}  读答题卡截图（绿对红错）→ 每题对错
    POST /api/mock/report/scan     {"images": [base64], "text"?}  读粉笔成绩截图（Windows OCR）或粘贴的报告文字 → 成绩单各项
    POST /api/mock/marks/save      {"season", "marks": {题号: ok/bad}}  写回这一季的板块复盘
    POST /api/mock/analysis        {"season"}  这一季的考情分析对话
    POST /api/mock/analyze         {"season", "text"?, "fresh"?}  师傅大比分析（无 text 先做完整分析；有 text 接着追问）
    POST /api/mock/save            {"season", "score", "avg", "top", "beat", "rank", "people", "date", "minutes": {模块}, "scores": {模块}}
    POST /api/practice             {"board", "total", "correct", "minutes", "source", "note"}  演武（自练做题）+ 日志；"date" 可补记最近 7 天
    POST /api/practice/delete      {"id"}  删掉记错的一笔自练
    POST /api/selfstudy            {"board"?, "minutes", "topic"?, "note"?, "date"?}  静修（自己复习）
    POST /api/selfstudy/delete     {"id"}
    POST /api/bank/add             {"board", "topic", "source", "stem", "options": {A..D}, "answer", "analysis"}  自练好题收进题库
    GET  /api/import               导入真题页：各季模考（已导入数）、待修文件、待分类知识点数
    POST /api/import/preview       {"kind": "season"|"text"|"fix", ...}  拆题预览（不写文件）
    POST /api/import/commit        同上 + {"ai": bool}  入库；拆不干净的写进 训练/题库/_待修/
    POST /api/import/answers       {"prefix", "key"}  按答案表补答案
    POST /api/import/classify      {"limit"}  DeepSeek 补“待分类”的知识点
    POST /api/import/remove        {"prefix"}  撤销一批导入（只删没做过的题）
    POST /api/import/normalize     整理题库格式：选项统一“A. ”，修复 OCR 认错的 ①② / ⅠⅡ
    POST /api/import/rename        {"old", "new", "boards"?}  改编号前缀（题库 + 作答记录一起改）
    POST /api/import/upload_pdf    {"name", "data"(base64), "season"?}  新模考 PDF 存进 FB模考试卷复盘/模考试卷/
    POST /api/import/split         {"file"}  运行 xingce-mokao-split 拆分并导入那一季
    POST /api/import/install_pymupdf  用户点按钮才运行 pip install pymupdf
    GET  /api/appearance           背景 / 语录 / 音乐的可选项和当前选择；POST 同路径保存选择
    POST /api/lecture              {"minutes", "note"?, "date"?, "board"?}  记一笔听道（其他平台看网课），计入每日功行
    POST /api/lecture/delete       {"id"}  删掉记错的一笔
    POST /api/lecture/board        {"id", "board"}  改一笔听道算哪个模块（空 = 不分模块）
    GET  /api/settings             本机设置（不返回完整 key）
    POST /api/settings             {"vault"?, "api_key"?, "base_url"?, "model"?}
    POST /api/settings/test        测试 AI 连接
    GET  /vault-file?p=<库内相对路径>   库里的图片（题目截图、头像）
    GET  /                         web/ 下的静态文件
"""
import datetime as dt
import json
import mimetypes
import re
import traceback
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, unquote, urlparse

from . import appearance, idioms, importer, lan, library, marks, mock, report, question_bank, ai, config, engine, paths as paths_mod, store, themes, trainer, tutor, vault
from .paths import WEB_DIR, Paths, find_vault, load_settings, looks_like_vault, save_settings


class ApiError(Exception):
    pass


@contextmanager
def open_game(save=True):
    with store.LOCK:
        paths = Paths(find_vault())
        paths.ensure_train_dir()
        st = store.Store(paths)
        today = dt.date.today()
        state = st.load(today)
        # 风格存在存档里：它决定用哪套导师设定、哪个台词库
        rules, persona, lines = config.load_all(paths, state.get("theme") or themes.DEFAULT_THEME)
        g = engine.Game(paths, rules, persona, lines, state, today)
        g.store = st
        yield g
        if save and paths.vault:
            st.save(state, today)


def _img_url(g, name):
    if g.paths.vault and name and (g.paths.train / name).is_file():
        return "/vault-file?p=" + ("训练/" + name)
    return ""


def _persona_view(g):
    return {"id": g.persona["ID"], "call": g.persona["称呼"], "tutor": g.persona["导师名"],
            "avatar": _img_url(g, g.persona["头像"]), "tutor_avatar": _img_url(g, g.persona["导师头像"])}


# ---------------------------------------------------------------- 各接口
def dashboard(body):
    with open_game() as g:
        ev = g.housekeeping()
        first_today = g.state.get("last_seen") != g.t
        g.state["last_seen"] = g.t
        plan = g.plan()
        d = g.dashboard()
        cached = tutor.cached_greeting(g)
        if cached:
            d["greeting"] = cached
        upgraded = list(paths_mod.UPGRADED)
        paths_mod.UPGRADED.clear()
        notices = list(paths_mod.NOTICES)
        paths_mod.NOTICES.clear()
        d.update(plan=plan, persona=_persona_view(g), events=tutor.enrich(g, ev), first_today=first_today,
                 greet_pending=bool(not cached and tutor.enabled(g)), upgraded=upgraded, notices=notices,
                 vault=str(g.paths.vault) if g.paths.vault else None, ai=ai.available(),
                 other_device=g.store.heartbeat(), conflicts=g.store.conflicts())
        return d


def tutor_greet(body):
    """网页加载完主页后再调：AI 生成今天的开场问候（慢，所以不放在 dashboard 里）"""
    with open_game() as g:
        return {"text": tutor.greeting(g)}


def plan_regenerate(body):
    with open_game() as g:
        g.housekeeping()
        return g.plan(force=True)


def _find_task(g, tid):
    for t in (g.state.get("plan") or {}).get("tasks", []):
        if t["id"] == tid:
            return t
    raise ApiError("任务不存在（可能已经过了一天），请刷新页面")


def _with_housekeeping(g, resp):
    resp["events"] = tutor.enrich(g, (resp.get("events") or []) + g.housekeeping())
    return resp


def session_start(body):
    with open_game() as g:
        task = _find_task(g, body["task_id"]) if body.get("task_id") else dict(body["task"], id=None)
        return _with_housekeeping(g, trainer.start(g, task))


def session_reply(body):
    with open_game() as g:
        return _with_housekeeping(g, trainer.reply(g, body["session"], body.get("text", "")))


def session_action(body):
    with open_game() as g:
        return _with_housekeeping(g, trainer.action(g, body["session"], body.get("action", "")))


def bank_view(body):
    with open_game(save=False) as g:
        return question_bank.summary(g)


def library_catalog(body):
    with open_game(save=False) as g:
        return library.catalog(g)


def library_search(body):
    with open_game(save=False) as g:
        return library.search(g, body)


def library_question(body):
    with open_game(save=False) as g:
        try:
            return library.detail(g, body.get("key", ""))
        except question_bank.BankError as e:
            raise ApiError(str(e))


def _import_paths():
    """导入不碰存档，不拿全局锁（AI 分类可能要几十秒，不能挡住计时心跳）"""
    p = Paths(find_vault())
    if not p.vault:
        raise ApiError("请先在设置中指定行测库路径")
    p.ensure_train_dir()
    return p


def _import_call(fn, body):
    try:
        return fn(_import_paths(), body)
    except importer.ImportError_ as e:
        raise ApiError(str(e))


def import_status(body):
    return importer.status(_import_paths())


def import_preview(body):
    return _import_call(importer.preview, body)


def _mock_imported(rep, season):
    """导入了一份模考试卷 → 演武 · 历练记记 120 分钟（每季一次）"""
    if season:
        with open_game() as g:
            ev = mock.on_import(g, int(season))
            if ev:
                rep["events"] = tutor.enrich(g, ev)
                rep["practice_minutes"] = mock.IMPORT_MINUTES
    return rep


def import_commit(body):
    rep = _import_call(importer.commit, body)
    if body.get("kind") == "season" and not rep.get("dry"):
        _mock_imported(rep, body.get("season"))
    return rep


def import_answers(body):
    return _import_call(importer.fill_answers, body)


def import_upload_pdf(body):
    return _import_call(importer.save_pdf, body)


def import_split(body):
    rep = _import_call(importer.split_pdf, body)
    return _mock_imported(rep, rep.get("season"))


def idioms_list(body):
    with open_game() as g:
        idioms.migrate(g)
        if idioms.clean_tags(g):
            idioms.write_file(g)
        return idioms.listing(g)


def idioms_backfill(body):
    with open_game() as g:
        r = idioms.backfill(g)
        return dict(r, **idioms.listing(g))


def _idiom_call(fn, *args):
    with open_game() as g:
        try:
            fn(g, *args)
        except ValueError as e:
            raise ApiError(str(e))
        except ai.AIError as e:
            raise ApiError("师傅没回话：%s" % e)
        return idioms.listing(g)


def idioms_edit(body):
    return _idiom_call(idioms.edit, str(body.get("word") or ""), {"word": body.get("new_word"), "sources": body.get("sources") or {}})


def idioms_delete(body):
    return _idiom_call(idioms.delete, str(body.get("word") or ""))


def idioms_tutor(body):
    if not ai.available():
        raise ApiError("师傅答疑要用 AI：先在“设置”里填 AI 的 API key")
    return _idiom_call(idioms.ask_tutor, str(body.get("word") or ""))


def mock_marks_scan(body):
    try:
        season = int(body.get("season") or 0)
    except (TypeError, ValueError):
        raise ApiError("先选是第几季")
    with open_game(save=False) as g:
        try:
            return marks.scan(g.paths, season, marks.decode(body.get("images")))
        except marks.MarksError as e:
            raise ApiError(str(e))


def mock_report_scan(body):
    try:
        return report.scan(marks.decode(body.get("images")), body.get("text") or "")
    except (report.ReportError, marks.MarksError) as e:
        raise ApiError(str(e))


def mock_marks_save(body):
    try:
        season = int(body.get("season") or 0)
    except (TypeError, ValueError):
        raise ApiError("先选是第几季")
    with open_game() as g:
        try:
            r = marks.apply(g.paths, season, body.get("marks") or {})
        except marks.MarksError as e:
            raise ApiError(str(e))
        mock.after_marks(g, season)
        g._acc = {}
        return dict(r, summary=mock.summary(g))


def _season(body):
    try:
        return int(body.get("season") or 0)
    except (TypeError, ValueError):
        raise ApiError("先选是第几季")


def mock_analysis_get(body):
    with open_game(save=False) as g:
        return {"season": _season(body), "conv": mock.analysis(g, _season(body))}


def mock_analyze(body):
    if not ai.available():
        raise ApiError("师傅大比分析要用 AI：先在“设置”里填 AI 的 API key")
    text = str(body.get("text") or "").strip()
    with open_game() as g:
        try:
            conv = mock.analyze(g, _season(body), text or None, fresh=bool(body.get("fresh")))
        except mock.MockError as e:
            raise ApiError(str(e))
        except ai.AIError as e:
            raise ApiError("师傅没回话：%s" % e)
        return {"season": _season(body), "conv": conv}


def mock_summary(body):
    with open_game(save=False) as g:
        return mock.summary(g)


def mock_save(body):
    with open_game() as g:
        try:
            ev = mock.save(g, body)
        except mock.MockError as e:
            raise ApiError(str(e))
        return {"events": tutor.enrich(g, ev + g.housekeeping()) if ev else [], "summary": mock.summary(g)}


def import_install(body):
    return _import_call(importer.install_pymupdf, body)


def import_rename(body):
    """改编号前缀：题库文件和存档里的作答记录一起改，所以要拿存档"""
    with open_game() as g:
        if not g.paths.vault:
            raise ApiError("请先在设置中指定行测库路径")
        try:
            return importer.rename_prefix(g.paths, body, g.state)
        except importer.ImportError_ as e:
            raise ApiError(str(e))


def import_dedupe(body):
    """题库去重：要动存档里的作答记录，所以拿存档；预览不保存"""
    with open_game(save=not body.get("dry")) as g:
        if not g.paths.vault:
            raise ApiError("请先在设置中指定行测库路径")
        return importer.dedupe_bank(g.paths, body, g.state)


def import_distill(body):
    """给已入库的真题补蒸馏解析（读本机的蒸馏笔记文件夹）"""
    from . import zhenti
    p = _import_paths()
    folder = str(body.get("folder") or "").strip().strip('"')
    if not folder:
        raise ApiError("填蒸馏笔记所在的文件夹")
    try:
        return zhenti.merge_distilled(p.train, folder, dry=bool(body.get("dry")))
    except ValueError as e:
        raise ApiError(str(e))


def import_normalize(body):
    return _import_call(importer.normalize_bank, body)


def import_remove(body):
    with open_game(save=False) as g:   # 做过的题有作答记录，不删
        done = set(question_bank.state(g)["records"])
    return _import_call(lambda p, b: importer.remove(p, b, done), body)


def import_classify(body):
    return _import_call(lambda p, b: importer.classify(p, max(1, min(300, int(b.get("limit") or 100)))), body)


def bank_count(body):
    if "order" in body:
        if body["order"] not in question_bank.ORDERS:
            raise ApiError("出题顺序无效")
        with open_game() as g:
            question_bank.state(g)["order"] = body["order"]
        return {"order": body["order"]}
    n = body.get("count")
    if n not in (10, 15):
        raise ApiError("题量只能选择 10 或 15")
    with open_game() as g:
        if not g.paths.vault:
            raise ApiError("请先在设置中指定行测库路径")
        # 追加同名配置，保留用户的其余规则；最后一项生效。
        with g.paths.rules.open("a", encoding="utf-8", newline="\n") as f:
            f.write("\n- 实战每组题数: %s\n" % n)
    return {"count": n}


def skeletons(body):
    with open_game(save=False) as g:
        out = []
        for b, info in g.boards.items():
            sk = g.skel(b)
            items = []
            for it in (sk["items"] if sk else []):
                st = g.state["items"].get(it["id"], {})
                items.append({"id": it["id"], "name": it["name"], "terms": len(it["terms"]) + len(it.get("verses", [])),
                              "thoughts": len(it["thoughts"]), "level": st.get("level", 0),
                              "levelName": g.level_names()[st.get("level", 0)],
                              "l1": st.get("l1", 0), "l3": st.get("l3", 0),
                              "exampleOk": st.get("example_ok", st.get("level", 0) >= 3),
                              "next": st.get("next"), "rusty": st.get("rusty", False),
                              "lapCheck": st.get("lap_check", False)})
            out.append({"board": b, "skill": info["skill"], "hasSkill": g.has_skill(b),
                        "status": (sk["status"] if sk else "无"), "final": bool(sk and sk["final"]),
                        "file": f"训练/骨架/{b}.md", "items": items})
        return {"boards": out, "need_l1": g.rules.num("默写连续通过次数"), "need_l3": g.rules.num("应用连续通过次数")}


def wrong(body):
    with open_game(save=False) as g:
        out = []
        for b, info in g.boards.items():
            qs = vault.wrong_questions(g.paths, info["sources"])
            st = [g.state["wrong"].get(q["key"], {}).get("status", "new") for q in qs]
            out.append({"board": b, "total": len(qs), "new": st.count("new"),
                        "redo": st.count("redo"), "done": st.count("done")})
        redo = [{"key": k, **w} for k, w in g.state["wrong"].items() if w["status"] == "redo"]
        return {"boards": out, "redo": sorted(redo, key=lambda x: x.get("due") or "")}


def heartbeat(body):
    """网页定时上报。只有带着“正在修炼”的会话（见 trainer.is_studying）才计时；
    只是开着网页、看面板、和导师闲聊，只刷新状态，不计时。"""
    sec = max(0, min(90, int(body.get("seconds", 0))))
    studying = trainer.is_studying(body.get("session"))
    with open_game() as g:
        sid = body.get("session")
        ev = tutor.enrich(g, g.add_seconds(sec, trainer.study_kind(sid), trainer.study_board(g, sid))) if studying and sec else []
        return {"events": ev, "minutes": int(g.minutes(g.t)), "studying": studying, "other_device": g.store.heartbeat(),
                "rest": g.resting(), "retreat_on": bool(g.state.get("retreat"))}


def leave(body):
    with open_game() as g:
        ok, msg = g.use_leave()
        ev = [{"kind": "npc", "msg": msg, "scene": "请假"}] if ok else [{"kind": "info", "msg": msg}]
        return {"ok": ok, "events": tutor.enrich(g, ev)}


def boss(body):
    """宗门大比（kind=大比，默认）或飞升大典（kind=飞升，国考）成绩"""
    name = str(body.get("name", "")).strip() or "模考"
    kind = "飞升" if body.get("kind") == "飞升" else "大比"
    try:
        score = float(body["score"])
    except Exception:
        raise ApiError("分数要填数字")
    if not 0 <= score <= 100:
        raise ApiError("分数要在 0–100 之间")
    with open_game() as g:
        if kind == "飞升" and body.get("result"):
            name = f"{name}（{body['result']}）"
        return {"events": tutor.enrich(g, g.add_boss(name, score, kind) + g.housekeeping())}


def theme_set(body):
    name = body.get("theme")
    if name not in themes.THEMES:
        raise ApiError("未知的风格")
    with open_game() as g:
        g.state["theme"] = name
        g.state["tutor_greet"] = None   # 换了导师，重新打招呼
        g.state["plan"] = None          # 功课标题换成新风格的说法
        return {"ok": True}


def lecture_add(body):
    """记一笔听道（其他平台看网课的时间）"""
    with open_game() as g:
        try:
            ev = g.add_lecture(body.get("minutes") or 0, str(body.get("note") or "").strip(), body.get("date") or None,
                               str(body.get("board") or "").strip())
        except (ValueError, TypeError) as e:
            raise ApiError(str(e))
        return {"events": tutor.enrich(g, ev)}


def lecture_board(body):
    with open_game() as g:
        try:
            g.set_lecture_board(str(body.get("id") or ""), str(body.get("board") or ""))
        except ValueError as e:
            raise ApiError(str(e))
        return {"ok": True}


def lecture_delete(body):
    with open_game() as g:
        try:
            g.delete_lecture(str(body.get("id") or ""))
        except ValueError as e:
            raise ApiError(str(e))
        return {"ok": True}


def appearance_get(body):
    with open_game(save=False) as g:
        return appearance.view(g.paths, g.state) if g.paths.vault else {"current": appearance.current({}),
                                                                             "backgrounds": [], "music": [], "quotes": [], "daily": ""}


def appearance_set(body):
    with open_game() as g:
        if not g.paths.vault:
            raise ApiError("请先在设置中指定行测库路径")
        return {"current": appearance.update(g.paths, g.state, body)}


def retreat_start(body):
    try:
        minutes = int(body.get("minutes") or 60)
    except Exception:
        raise ApiError("分钟要填数字")
    board = str(body.get("board", "")).strip()
    with open_game() as g:
        if board not in g.boards and board not in g.rules.side:
            raise ApiError("先选一个板块")
        if g.resting():
            raise ApiError(f"还需调息 {g.resting()} 分钟")
        ok, msg = g.start_retreat(board, max(15, min(240, minutes)))
        if not ok:
            raise ApiError(msg)
        return {"events": [{"kind": "info", "msg": msg}]}


def retreat_end(body):
    with open_game() as g:
        return {"events": tutor.enrich(g, g.end_retreat())}


def practice(body):
    try:
        total, correct = int(body.get("total") or 0), int(body.get("correct") or 0)
        minutes = int(body.get("minutes") or 0)
    except Exception:
        raise ApiError("题数、正确数、分钟要填数字")
    note, source = str(body.get("note") or "").strip(), str(body.get("source") or "").strip()[:60]
    if total < 0 or not (0 <= correct <= total) or (total == 0 and not note):
        raise ApiError("题数要大于 0、正确数不能超过题数（只写日志的话题数填 0）")
    with open_game() as g:
        try:
            return {"events": g.add_practice(str(body.get("board", "")).strip() or "自练", total, correct, minutes, source, note[:5000],
                                             body.get("date") or None)}
        except ValueError as e:
            raise ApiError(str(e))


def selfstudy_add(body):
    with open_game() as g:
        try:
            ev = g.add_selfstudy(str(body.get("board") or ""), body.get("minutes") or 0, str(body.get("topic") or "").strip(),
                                 str(body.get("note") or "").strip(), body.get("date") or None)
        except (ValueError, TypeError) as e:
            raise ApiError(str(e))
        return {"events": tutor.enrich(g, ev)}


def selfstudy_delete(body):
    with open_game() as g:
        try:
            g.delete_selfstudy(str(body.get("id") or ""))
        except ValueError as e:
            raise ApiError(str(e))
        return {"ok": True}


def practice_delete(body):
    with open_game() as g:
        try:
            g.delete_practice(str(body.get("id") or ""))
        except ValueError as e:
            raise ApiError(str(e))
        return {"ok": True}


def bank_add(body):
    with open_game() as g:
        if not g.paths.vault:
            raise ApiError("请先在设置中指定行测库路径")
        try:
            return question_bank.add_question(g, body)
        except question_bank.BankError as e:
            raise ApiError(str(e))


def settings_get(body):
    s = load_settings()
    a = ai.settings()
    key = a["api_key"]
    return {"vault": str(find_vault() or ""), "vault_setting": s.get("vault", ""),
            "base_url": a["base_url"], "model": a["model"],
            "has_key": bool(key), "key_tail": key[-4:] if key else ""}


def settings_set(body):
    s = load_settings()
    if "vault" in body:
        v = str(body["vault"]).strip()
        if v:
            from pathlib import Path
            if not looks_like_vault(Path(v).expanduser()):
                raise ApiError("这个文件夹里没有 copilot/skills 或 FB模考试卷复盘，不像行测库根目录")
        s["vault"] = v
    for k in ("api_key", "base_url", "model"):
        if k in body and str(body[k]).strip():
            s[k] = str(body[k]).strip()
    save_settings(s)
    return settings_get({})


def settings_test(body):
    r = ai.chat([{"role": "user", "content": "回复“连接成功”四个字"}], max_tokens=20, timeout=30)
    return {"ok": True, "reply": r}


ROUTES = {
    ("GET", "/api/dashboard"): dashboard,
    ("POST", "/api/plan/regenerate"): plan_regenerate,
    ("POST", "/api/theme"): theme_set,
    ("GET", "/api/appearance"): appearance_get,
    ("POST", "/api/lecture"): lecture_add,
    ("POST", "/api/lecture/delete"): lecture_delete,
    ("POST", "/api/lecture/board"): lecture_board,
    ("POST", "/api/appearance"): appearance_set,
    ("POST", "/api/retreat/start"): retreat_start,
    ("POST", "/api/retreat/end"): retreat_end,
    ("POST", "/api/tutor/greet"): tutor_greet,
    ("POST", "/api/session/start"): session_start,
    ("POST", "/api/session/reply"): session_reply,
    ("POST", "/api/session/action"): session_action,
    ("GET", "/api/bank"): bank_view,
    ("POST", "/api/bank/count"): bank_count,
    ("GET", "/api/library"): library_catalog,
    ("POST", "/api/library/search"): library_search,
    ("POST", "/api/library/question"): library_question,
    ("GET", "/api/import"): import_status,
    ("POST", "/api/import/preview"): import_preview,
    ("POST", "/api/import/commit"): import_commit,
    ("POST", "/api/import/answers"): import_answers,
    ("POST", "/api/import/classify"): import_classify,
    ("POST", "/api/import/remove"): import_remove,
    ("POST", "/api/import/normalize"): import_normalize,
    ("POST", "/api/import/distill"): import_distill,
    ("POST", "/api/import/dedupe"): import_dedupe,
    ("POST", "/api/import/rename"): import_rename,
    ("POST", "/api/import/upload_pdf"): import_upload_pdf,
    ("POST", "/api/import/split"): import_split,
    ("POST", "/api/import/install_pymupdf"): import_install,
    ("GET", "/api/skeletons"): skeletons,
    ("GET", "/api/wrong"): wrong,
    ("POST", "/api/heartbeat"): heartbeat,
    ("POST", "/api/leave"): leave,
    ("POST", "/api/boss"): boss,
    ("POST", "/api/practice"): practice,
    ("GET", "/api/mock"): mock_summary,
    ("GET", "/api/idioms"): idioms_list,
    ("POST", "/api/idioms/backfill"): idioms_backfill,
    ("POST", "/api/idioms/edit"): idioms_edit,
    ("POST", "/api/idioms/delete"): idioms_delete,
    ("POST", "/api/idioms/tutor"): idioms_tutor,
    ("POST", "/api/mock/save"): mock_save,
    ("POST", "/api/mock/marks/scan"): mock_marks_scan,
    ("POST", "/api/mock/report/scan"): mock_report_scan,
    ("POST", "/api/mock/marks/save"): mock_marks_save,
    ("POST", "/api/mock/analysis"): mock_analysis_get,
    ("POST", "/api/mock/analyze"): mock_analyze,
    ("POST", "/api/practice/delete"): practice_delete,
    ("POST", "/api/selfstudy"): selfstudy_add,
    ("POST", "/api/selfstudy/delete"): selfstudy_delete,
    ("POST", "/api/bank/add"): bank_add,
    ("GET", "/api/settings"): settings_get,
    ("POST", "/api/settings"): settings_set,
    ("POST", "/api/settings/test"): settings_test,
}


def _music_file(paths, rel):
    """网页播放 BGM 用：只允许 训练/外观/音乐/ 里的音频文件"""
    if not paths.vault or not rel:
        return None
    p = (paths.vault / rel).resolve()
    root = appearance.folder(paths, appearance.MUSIC_DIR).resolve()
    if root not in p.parents or not p.is_file() or p.suffix.lower() not in appearance.AUDIO_EXT:
        return None
    return p


# ---------------------------------------------------------------- HTTP
# ---------------------------------------------------------------- 局域网（手机 / 平板）与更新
RUNTIME = {"port": 0, "lan": False}      # server.py 启动时填：端口、是否监听局域网


def lan_get(body):
    return lan.status(RUNTIME["port"], RUNTIME["lan"])


def lan_set(body):
    lan.update(body.get("enabled") if "enabled" in body else None, bool(body.get("new_code")))
    return lan.status(RUNTIME["port"], RUNTIME["lan"])


def update_check(body):
    from . import update
    try:
        return update.check()
    except update.UpdateError as e:
        raise ApiError(str(e))


def update_apply(body):
    from . import update
    try:
        return update.apply()
    except update.UpdateError as e:
        raise ApiError(str(e))


def version_get(body):
    from .paths import FROZEN
    from .version import VERSION
    import sys
    return {"version": VERSION, "frozen": FROZEN, "platform": sys.platform}


ROUTES[("GET", "/api/version")] = version_get
ROUTES[("GET", "/api/update/check")] = update_check
ROUTES[("POST", "/api/update/apply")] = update_apply
ROUTES[("GET", "/api/lan")] = lan_get
ROUTES[("POST", "/api/lan")] = lan_set
LOCAL_ONLY = {"/api/lan", "/api/settings", "/api/update/apply"}     # 只有电脑本机能改的


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # 不在终端刷屏
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_range(self, p, ctype):
        """音频支持 Range（浏览器拖进度、循环播放会用到）"""
        size = p.stat().st_size
        m = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range") or "")
        start, end = 0, size - 1
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else size - 1
            else:
                start = max(0, size - int(m.group(2)))
            end = min(end, size - 1)
        with open(p, "rb") as fp:
            fp.seek(start)
            data = fp.read(end - start + 1)
        self.send_response(206 if m and (m.group(1) or m.group(2)) else 200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(len(data)))
        if m and (m.group(1) or m.group(2)):
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.end_headers()
        self.wfile.write(data)

    def _gate(self, method, url):
        """局域网里别的设备：没输过口令先输口令。返回 True 表示这次请求已经处理完了"""
        addr = self.client_address[0]
        if url.path == "/lan/ping":            # 平板 App 在 Wi-Fi 里找电脑用：不用口令，只说“我是修仙传”
            self._send(200, lan.ping())
            return True
        if url.path == "/lan/login" and method == "POST":
            n = int(self.headers.get("Content-Length") or 0)
            code = parse_qs(self.rfile.read(n).decode("utf-8", errors="ignore")).get("code", [""])[0].strip()
            if code and code == lan.settings()["code"]:
                self.send_response(303)
                self.send_header("Set-Cookie", "%s=%s; Path=/; Max-Age=31536000; HttpOnly; SameSite=Lax" % (lan.COOKIE, lan.token(code)))
                self.send_header("Location", "/")
                self.end_headers()
            else:
                self._send(200, lan.login_page("口令不对，再看一眼电脑上的口令"), "text/html; charset=utf-8")
            return True
        if lan.authorized(addr, self.headers.get("Cookie")):
            if not lan.is_local(addr) and url.path in LOCAL_ONLY and method == "POST":
                self._send(403, {"error": "这项设置只能在电脑上改"})
                return True
            return False
        if url.path.startswith("/api/") or url.path == "/vault-file":
            self._send(401, {"error": "先输入访问口令（刷新页面）"})
        else:
            self._send(200, lan.login_page(), "text/html; charset=utf-8")
        return True

    def _handle(self, method):
        url = urlparse(self.path)
        if self._gate(method, url):
            return
        fn = ROUTES.get((method, url.path))
        if fn:
            try:
                body = {}
                if method == "POST":
                    n = int(self.headers.get("Content-Length") or 0)
                    body = json.loads(self.rfile.read(n).decode("utf-8") or "{}") if n else {}
                self._send(200, fn(body))
            except (ApiError, trainer.TrainError, ai.AIError) as e:
                self._send(400, {"error": str(e)})
            except Exception as e:
                traceback.print_exc()
                self._send(500, {"error": f"程序出错：{e}（终端窗口里有详细信息）"})
            return
        if method != "GET":
            return self._send(404, {"error": "not found"})
        if url.path == "/vault-file":
            rel = unquote(parse_qs(url.query).get("p", [""])[0])
            vp = Paths(find_vault())
            p = vault.safe_vault_file(vp, rel) or _music_file(vp, rel)
            if not p:
                return self._send(404, {"error": "文件不存在"})
            ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            if p.suffix.lower() in appearance.AUDIO_EXT:
                return self._send_range(p, ctype)
            return self._send(200, p.read_bytes(), ctype)
        rel = url.path.lstrip("/") or "index.html"
        f = (WEB_DIR / rel).resolve()
        if WEB_DIR.resolve() not in f.parents or not f.is_file():
            return self._send(404, {"error": "not found"})
        ctype = mimetypes.guess_type(f.name)[0] or "text/plain"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        self._send(200, f.read_bytes(), ctype)

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

