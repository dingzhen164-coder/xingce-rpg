"""
HTTP 接口：把 engine / trainer / store 暴露给网页（web/app.js）。只监听 127.0.0.1，外网访问不到。

每个请求的流程：拿全局锁 → 读配置和存档 → 建 Game → 做事 → housekeeping（检查通关）→ 存档 → 返回 JSON。
配置文件每次都重新读，所以用户在 Obsidian 里改了规则，刷新网页就生效。

接口一览（GET 无参数，POST 请求体是 JSON）：
    GET  /api/dashboard            面板 + 今日任务 + 角色信息 + 提醒
    POST /api/tutor/greet          AI 导师今天的开场问候（每天生成一次并缓存）
    GET  /api/changelog            版本更新记录（rpg/data/changelog.md）
    GET  /api/notes …              灵台手札：本子列表；POST get {id} / save / delete / compile（师傅编纂）；GET tree（库里的 md、pdf）；POST md {p}（读一篇）
                                   POST pdfopen {p}（调阅 PDF → 批注本）/ pdfexport {id, overlays}；GET /notes-pdfpage?p=&n=（PDF 一页的底图）
    GET  /api/app/latest           平板 App 的最新版本（电脑替平板去 GitHub 下安装包）；/app/xingce-xiuxian.apk 拿安装包
    POST /api/theme                {"theme": "修仙"|"玄幻"}  切换风格
    POST /api/retreat/start        {"board", "minutes"}  闭关；POST /api/retreat/end 提前出关
    POST /api/plan/regenerate      重新生成今日任务
    POST /api/session/start        {"task_id"} 或 {"task": {type, board, target, title}} 开始修炼
                                   （type 还可以是 tribulation 渡劫、alchemy 炼丹(board)、chat 聊天）
    POST /api/session/reply        {"session", "text"}      提交文字
    POST /api/session/action       {"session", "action"}    点按钮
    GET  /api/skeletons            各板块骨架与每个大项的掌握度
    GET  /api/wrong                错题池统计
    POST /api/heartbeat            {"seconds", "session", "notes"}  网页每 30 秒上报；只有正在修炼的会话、或 1 分钟内动过笔的手札才计时
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
    GET  /vault-file?p=<库内相对路径>   库里的图片（题目截图、头像）；&trim=1 裁掉四周空白（材料截图）
    GET  /                         web/ 下的静态文件
"""
import datetime as dt
import json
import mimetypes
import re
import traceback
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, quote, unquote, urlparse

from . import appapk, appearance, cardgen, cards, mindmap, notes, poster, tianji, idioms, importer, lan, library, marks, mock, report, question_bank, ai, config, engine, paths as paths_mod, store, themes, trainer, tutor, vault
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


def realm_break(body):
    """⚡ 突破：修为圆满后由修炼者自己按住「突破」进入下一层（不自动升级，留一点仪式感）"""
    with open_game() as g:
        try:
            ev = g.break_through()
        except ValueError as e:
            raise ApiError(str(e))
        return {"events": tutor.enrich(g, ev), "realm": g.realm_info()}


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
    noting = not studying and bool(body.get("notes")) and notes.writing(body.get("notes"))   # 在手札里写（1 分钟内动过笔）
    carding = not studying and not noting and bool(body.get("cards")) and cards.reviewing()        # 在温简（2 分半内答过一张）
    tj = body.get("tianji") if not (studying or noting or carding) and tianji.studying() else None  # 在天机简报里学（5 分钟内翻过、填过、答过）
    with open_game() as g:
        sid = body.get("session")
        if studying and sec:
            ev = tutor.enrich(g, g.add_seconds(sec, trainer.study_kind(sid), trainer.study_board(g, sid)))
        elif (noting or carding) and sec:
            ev = tutor.enrich(g, g.add_seconds(sec, "review", body.get("cards_board") if carding and body.get("cards_board") in g.boards else ""))
        elif tj and sec:      # 精卷算做题，研读 / 消化算复习，都记在政治理论
            ev = tutor.enrich(g, g.add_seconds(sec, "practice" if tj == "quiz" else "review", "政治理论" if "政治理论" in g.boards else ""))
        else:
            ev = []
        studying = studying or noting or carding or bool(tj)
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
            "has_key": bool(key), "key_tail": key[-4:] if key else "",
            "vision_model": s.get("vision_model", ""), "vision_base_url": s.get("vision_base_url", ""),
            "vision_has_key": bool(s.get("vision_api_key")),
            "ai_profiles": [{"name": x.get("name", ""), "base_url": x.get("base_url", ""), "model": x.get("model", ""),
                             "key_tail": (x.get("api_key") or "")[-4:]} for x in s.get("ai_profiles") or []],
            "ai_active": s.get("ai_active", "")}


def settings_set(body):
    s = load_settings()
    if "vault" in body:
        v = str(body["vault"]).strip()
        if v:
            from pathlib import Path
            if not looks_like_vault(Path(v).expanduser()):
                raise ApiError("这个文件夹里没有 copilot/skills 或 FB模考试卷复盘，不像行测库根目录")
        s["vault"] = v
    changed = False
    for k in ("api_key", "base_url", "model"):
        if k in body and str(body[k]).strip():
            changed |= s.get(k) != str(body[k]).strip()
            s[k] = str(body[k]).strip()
    if changed:                  # 手改了接口 / 模型 / key：已经不是哪一套方案了（要留着就再“存为一套”，同名会覆盖）
        s["ai_active"] = ""
    for k in ("vision_model", "vision_base_url", "vision_api_key"):     # 识图模型可以清空
        if k in body and (k != "vision_api_key" or str(body[k]).strip()):
            s[k] = str(body[k]).strip()
    save_settings(s)
    return settings_get({})


def ai_profile(body):
    """AI 方案：把几套 接口地址 + 模型 + key 存起来，随时切换（切换 = 把那套抄到当前设置）。
    {action: save（把当前这套存成 name）| use | delete, name}"""
    s = load_settings()
    profs = [x for x in s.get("ai_profiles") or [] if x.get("name")]
    name = str(body.get("name") or "").strip()[:30]
    act = body.get("action")
    if not name:
        raise ApiError("先给这套 AI 起个名字")
    if act == "save":
        cur = ai.settings()
        if not cur["api_key"]:
            raise ApiError("当前还没填 API key，先填好再存")
        p = {"name": name, "base_url": cur["base_url"], "model": cur["model"], "api_key": cur["api_key"]}
        profs = [x for x in profs if x["name"] != name] + [p]
        s["ai_active"] = name
    elif act == "use":
        p = next((x for x in profs if x["name"] == name), None)
        if not p:
            raise ApiError("没有这套 AI：%s" % name)
        s.update(base_url=p["base_url"], model=p["model"], api_key=p["api_key"])
        s["ai_active"] = name
    elif act == "delete":
        profs = [x for x in profs if x["name"] != name]
        if s.get("ai_active") == name:
            s["ai_active"] = ""
    else:
        raise ApiError("不认识的操作")
    s["ai_profiles"] = profs
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
    ("POST", "/api/realm/break"): realm_break,
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


def app_latest(body):
    """平板 App 问最新版本（电脑替它去 GitHub 看、把安装包下到本机）"""
    from . import appapk
    return dict(appapk.latest(), apk_port=RUNTIME.get("apk_port") or 0, path="/app/" + appapk.NAME)


# ---------------------------------------------------------------- 灵台手札
def _notes_call(fn, *a):
    with open_game(save=False) as g:
        if not g.paths.vault:
            raise ApiError("还没找到行测库")
        try:
            return fn(g.paths, *a)
        except notes.NotesError as e:
            raise ApiError(str(e))
        except ai.AIError as e:
            raise ApiError("师傅编纂失败：%s" % e)


def notes_list(body):
    return {"notebooks": _notes_call(notes.listing), "vision": ai.vision_available(), "ai": ai.available()}


def notes_get(body):
    return _notes_call(notes.get, body.get("id"))


def notes_save(body):
    return _notes_call(notes.save, body)


def notes_delete(body):
    return _notes_call(notes.delete, body.get("id"))


def notes_compile(body):
    return _notes_call(notes.compile, body.get("id"), body.get("images") or [], body.get("text"))


def notes_pdf(body):
    r = _notes_call(notes.export_pdf, body.get("id"), body.get("images") or [])
    r["url"] = "/notes-file?p=%s&t=%s" % (quote(r["path"]), export_token(r["path"]))
    return r


def notes_pdfs(body):
    return {"files": _notes_call(notes.pdf_list)}


def notes_pdfopen(body):
    return _notes_call(notes.pdf_open, body.get("p") or body.get("path"), body.get("title") or "")


def notes_pdfexport(body):
    r = _notes_call(notes.export_pdf_annot, body.get("id"), body.get("overlays") or [])
    r["url"] = "/notes-file?p=%s&t=%s" % (quote(r["path"]), export_token(r["path"]))
    return r


def notes_open(body):
    with open_game(save=False) as g:
        p = notes.export_file(g.paths, body.get("path")) if g.paths.vault else None
    if not p:
        raise ApiError("找不到导出的文件")
    try:
        notes.open_local(p)
    except Exception as e:
        raise ApiError("打不开：%s（文件在 %s）" % (e, p))
    return {"ok": True}


def export_token(rel):
    """平板下载导出的 PDF 用的口令（系统浏览器下载时没有 cookie）：按文件路径 + 局域网口令算"""
    import hashlib
    return hashlib.sha256(("xingce-pdf:%s:%s" % (lan.settings().get("code", ""), rel)).encode("utf-8")).hexdigest()[:20]


def notes_tree(body):
    return {"files": _notes_call(notes.md_tree)}


def notes_md(body):
    return _notes_call(notes.read_md, body.get("p") or body.get("path"))


# ---------------------------------------------------------------- 📜 玉简（记忆卡片，见 rpg/cards.py）
def _cards(fn, *a, save=True):
    with open_game(save=save) as g:
        if not g.paths.vault:
            raise ApiError("还没找到行测库")
        try:
            return fn(g, *a)
        except cards.CardError as e:
            raise ApiError(str(e))


def cards_overview(body):
    return _cards(cards.overview)


def cards_next(body):
    return _cards(lambda g: cards.next_card(g, body.get("deck") or ""))


def cards_answer(body):
    def run(g):
        ev = tutor.enrich(g, cards.answer(g, body.get("key"), int(body.get("rating") or 0), body.get("secs") or 0))
        r = cards.next_card(g, body.get("deck") or "")
        r["events"] = ev
        return r
    return _cards(run)


def cards_undo(body):
    def run(g):
        key = cards.undo(g)
        r = cards.next_card(g, body.get("deck") or "")
        if key and r.get("card", {}).get("key") != key:     # 撤销的那张直接再拿出来
            r["card"] = cards.card_view(g, key)
            r["intervals"] = cards.intervals(g, key, r["card"]["deck"])
            r.pop("done", None)
        return r
    return _cards(run)


def cards_add(body):
    return _cards(lambda g: cards.add(g, body))


def cards_note(body):
    return _cards(lambda g: cards.note_get(g, body.get("id")), save=False)


def cards_update(body):
    return _cards(lambda g: cards.update(g, body))


def cards_delete(body):
    return _cards(lambda g: cards.delete(g, body.get("ids") or []))


def cards_suspend(body):
    return _cards(lambda g: cards.suspend(g, body.get("keys") or [], bool(body.get("on", True))))


def cards_forget(body):
    return _cards(lambda g: cards.forget(g, body.get("keys") or []))


def cards_move(body):
    return _cards(lambda g: cards.move(g, body.get("ids") or [], body.get("deck")))


def cards_deck(body):
    return _cards(lambda g: cards.deck_action(g, body))


def cards_search(body):
    return _cards(lambda g: cards.search(g, body))


def cards_info(body):
    return _cards(lambda g: cards.info(g, body.get("key")))


def cards_stats(body):
    return _cards(lambda g: cards.stats(g, body.get("deck") or ""))


def cards_import(body):
    return _cards(lambda g: cards.import_text(g, body))


def cards_image(body):
    return _cards(lambda g: cards.save_image(g.paths, body.get("data")), save=False)


def cards_add_many(body):
    return _cards(lambda g: cards.add_many(g, body.get("deck"), body.get("cards") or []))


def _gen(fn, body):
    with open_game(save=False) as g:
        if not g.paths.vault:
            raise ApiError("还没找到行测库")
        p = g.paths
    try:
        return fn(p, body)
    except (cardgen.GenError, notes.NotesError) as e:
        raise ApiError(str(e))
    except ai.AIError as e:
        raise ApiError(str(e))


def cardgen_load(body):
    return _gen(cardgen.load, body)


def cardgen_chunks(body):
    return _gen(cardgen.chunks, body)


def cardgen_files(body):
    return _gen(lambda p, b: cardgen.vault_files(p), body)


def cardgen_gen(body):
    return _gen(cardgen.gen, body)


def cards_explain(body):
    """🙋 师傅讲讲：翻面后看不懂，问 AI（可追问）"""
    with open_game(save=False) as g:
        try:
            card = cards.card_view(g, body.get("key"))
        except cards.CardError as e:
            raise ApiError(str(e))
    if not ai.available():
        raise ApiError("还没填 AI 的 API key：设置里填好才能请师傅讲")
    try:
        reply = ai.chat(cards.explain_prompt(card, body.get("question"), body.get("history")), temperature=0.5, max_tokens=900)
    except ai.AIError as e:
        raise ApiError(str(e))
    saved = _cards(lambda g: cards.save_explain(g, body.get("key"), body.get("question"), reply), save=False)
    return {"reply": reply.strip(), "saved": saved}


# ---------------------------------------------------------------- 🌿 灵脉图（思维导图，见 rpg/mindmap.py）
def _mm(fn, *a):
    with open_game(save=False) as g:
        if not g.paths.vault:
            raise ApiError("还没找到行测库")
        p = g.paths
    try:
        return fn(p, *a)
    except mindmap.MapError as e:
        raise ApiError(str(e))


def mm_list(body):
    return _mm(mindmap.listing)


def mm_get(body):
    return _mm(mindmap.get, body.get("board"), body.get("name"))


def mm_save(body):
    r = _mm(mindmap.save, body.get("board"), body.get("name"), body.get("data"))
    r.pop("data", None)
    return r


def mm_create(body):
    return _mm(mindmap.create, body.get("board"), body.get("name"), body.get("data"))


def mm_rename(body):
    return _mm(mindmap.rename, body.get("board"), body.get("name"), body.get("new"))


def mm_delete(body):
    return _mm(mindmap.delete, body.get("board"), body.get("name"))


def mm_export(body):
    r = _mm(mindmap.export, body.get("board"), body.get("name"), body.get("ext"), body.get("data"))
    r["url"] = "/notes-file?p=%s&t=%s" % (quote(r["path"]), export_token(r["path"]))
    return r


# ---------------------------------------------------------------- 🖼 修炼战报（见 rpg/poster.py、web/poster.js）
def poster_stats(body):
    with open_game(save=False) as g:
        try:
            d = poster.stats(g, body.get("span") or "day")
        except poster.PosterError as e:
            raise ApiError(str(e))
        d.update(persona=_persona_view(g), today=g.t, theme=g.theme)
        return d


def poster_save(body):
    with open_game(save=False) as g:
        if not g.paths.vault:
            raise ApiError("还没找到行测库")
        try:
            r = poster.save(g.paths, body.get("data"), body.get("span") or "day", g.t)
        except poster.PosterError as e:
            raise ApiError(str(e))
    r["url"] = "/notes-file?p=%s&t=%s" % (quote(r["path"]), export_token(r["path"]))
    return r


# ---------------------------------------------------------------- 🔮 天机简报（见 rpg/tianji.py、web/tianji.js）
def _tj(fn, *a, save=True):
    with open_game(save=save) as g:
        if not g.paths.vault:
            raise ApiError("还没找到行测库")
        try:
            return fn(g, *a)
        except tianji.TianjiError as e:
            raise ApiError(str(e))


def tj_list(body):
    return _tj(tianji.listing, save=False)


def tj_import(body):
    """网页把 PDF 读成 dataURL / base64 传上来 → 存临时文件 → 解析入库"""
    import base64
    import tempfile
    from pathlib import Path
    raw = str(body.get("data") or "")
    raw = raw.split(",", 1)[1] if raw.startswith("data:") else raw
    try:
        pdf = base64.b64decode(raw)
    except Exception:
        raise ApiError("PDF 数据不对")
    if not pdf.startswith(b"%PDF"):
        raise ApiError("这不是 PDF 文件")
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "upload.pdf"
        f.write_bytes(pdf)
        return _tj(lambda g: tianji.save_import(g.paths, f), save=False)


def tj_get(body):
    return _tj(tianji.get, body.get("kind"), body.get("id"))


def tj_mark(body):
    r = _tj(tianji.mark, body.get("kind"), body.get("id"), body)
    return r


def tj_meta(body):
    return _tj(tianji.set_meta, body.get("kind"), body.get("id"), body, save=False)


def tj_delete(body):
    return _tj(tianji.delete, body.get("kind"), body.get("id"))


def tj_cards(body):
    return _tj(tianji.forgot_cards, body.get("kind"), body.get("id"))


def tj_ask(body):
    """🧙 问师傅：question 空 = 总结这一条怎么记（尤其红字）；否则就这一条提问。可以追问（history）"""
    with open_game(save=False) as g:
        if not g.paths.vault:
            raise ApiError("还没找到行测库")
        try:
            data = tianji.load(g.paths, body.get("kind"), body.get("id"))
            msgs = tianji.ask_prompt(data, int(body.get("news") or 0), str(body.get("question") or "").strip(), body.get("history"))
        except (tianji.TianjiError, ValueError) as e:
            raise ApiError(str(e))
    if not ai.available():
        raise ApiError("还没填 AI 的 API key：设置里填好才能问师傅")
    tianji.touch()
    try:
        reply = ai.chat(msgs, temperature=0.5, max_tokens=1200).strip()
    except ai.AIError as e:
        raise ApiError(str(e))
    saved = _tj(lambda g: tianji.save_ask(g, body.get("kind"), body.get("id"), int(body.get("news") or 0), str(body.get("question") or "").strip(), reply))
    return {"reply": reply, "saved": saved}


def tj_pdf(body):
    with open_game(save=False) as g:
        rel = str(body.get("path") or "")
    return {"url": "/notes-file?p=%s&t=%s" % (quote(rel), export_token(rel))}


def changelog_get(body):
    from . import changelog
    return {"entries": changelog.entries()}


def version_get(body):
    from .paths import FROZEN
    from .version import VERSION
    import sys
    return {"version": VERSION, "frozen": FROZEN, "platform": sys.platform}


ROUTES[("GET", "/api/version")] = version_get
ROUTES[("GET", "/api/changelog")] = changelog_get
ROUTES[("GET", "/api/app/latest")] = app_latest
ROUTES[("GET", "/api/cards")] = cards_overview
ROUTES[("GET", "/api/mindmap")] = mm_list
for _n, _f in (("get", mm_get), ("save", mm_save), ("create", mm_create), ("rename", mm_rename), ("delete", mm_delete), ("export", mm_export)):
    ROUTES[("POST", "/api/mindmap/" + _n)] = _f
ROUTES[("POST", "/api/settings/ai_profile")] = ai_profile
ROUTES[("POST", "/api/poster/stats")] = poster_stats
ROUTES[("GET", "/api/tianji")] = tj_list
for _n, _f in (("import", tj_import), ("get", tj_get), ("mark", tj_mark), ("meta", tj_meta), ("delete", tj_delete), ("cards", tj_cards), ("pdf", tj_pdf), ("ask", tj_ask)):
    ROUTES[("POST", "/api/tianji/" + _n)] = _f
ROUTES[("POST", "/api/poster/save")] = poster_save
for _n, _f in (("next", cards_next), ("answer", cards_answer), ("undo", cards_undo), ("add", cards_add), ("note", cards_note),
               ("update", cards_update), ("delete", cards_delete), ("suspend", cards_suspend), ("forget", cards_forget),
               ("move", cards_move), ("deck", cards_deck), ("search", cards_search), ("info", cards_info),
               ("stats", cards_stats), ("import", cards_import), ("image", cards_image), ("explain", cards_explain),
               ("add_many", cards_add_many), ("gen/load", cardgen_load), ("gen/chunks", cardgen_chunks), ("gen/run", cardgen_gen), ("gen/files", cardgen_files)):
    ROUTES[("POST", "/api/cards/" + _n)] = _f
ROUTES[("GET", "/api/notes")] = notes_list
ROUTES[("POST", "/api/notes/get")] = notes_get
ROUTES[("POST", "/api/notes/save")] = notes_save
ROUTES[("POST", "/api/notes/delete")] = notes_delete
ROUTES[("POST", "/api/notes/compile")] = notes_compile
ROUTES[("GET", "/api/notes/tree")] = notes_tree
ROUTES[("POST", "/api/notes/md")] = notes_md
ROUTES[("POST", "/api/notes/pdf")] = notes_pdf
ROUTES[("POST", "/api/notes/open")] = notes_open
ROUTES[("POST", "/api/notes/pdfopen")] = notes_pdfopen
ROUTES[("GET", "/api/notes/pdfs")] = notes_pdfs
ROUTES[("POST", "/api/notes/pdfexport")] = notes_pdfexport
ROUTES[("GET", "/api/update/check")] = update_check
ROUTES[("POST", "/api/update/apply")] = update_apply
ROUTES[("GET", "/api/lan")] = lan_get
ROUTES[("POST", "/api/lan")] = lan_set
LOCAL_ONLY = {"/api/lan", "/api/settings", "/api/update/apply", "/api/notes/open"}     # 只有电脑本机能改的


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # 不在终端刷屏
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8", cache=False):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "max-age=604800" if cache else "no-store")
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
        if url.path == "/app/" + appapk.NAME and method == "GET":    # 平板 App 安装包：公开的东西，不用口令（系统浏览器下载时没有 cookie）
            try:
                data = appapk.apk_bytes()
            except appapk.ApkError as e:
                self._send(502, {"error": str(e)})
                return True
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.android.package-archive")
            self.send_header("Content-Disposition", 'attachment; filename="%s"' % appapk.NAME)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return True
        if url.path == "/notes-file" and method == "GET":       # 导出的手札 PDF：带对的 t 就给（平板交给系统浏览器下载，没有 cookie）
            q = parse_qs(url.query)
            rel = unquote(q.get("p", [""])[0])
            if lan.authorized(addr, self.headers.get("Cookie")) or q.get("t", [""])[0] == export_token(rel):
                p = notes.export_file(Paths(find_vault()), rel)
                if not p:
                    self._send(404, {"error": "文件不存在"})
                    return True
                from urllib.parse import quote
                data = p.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", mimetypes.guess_type(p.name)[0] or "application/octet-stream")
                self.send_header("Content-Disposition", "attachment; filename*=UTF-8''%s" % quote(p.name))
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
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
        if url.path == "/notes-pdfpage":            # 调阅 PDF 的一页底图（rpg/notes.py pdf_page）
            q = parse_qs(url.query)
            try:
                data = notes.pdf_page(Paths(find_vault()), unquote(q.get("p", [""])[0]), int(q.get("n", ["0"])[0]))
            except (notes.NotesError, ValueError) as e:
                return self._send(404, {"error": str(e)})
            return self._send(200, data, "image/jpeg", cache=True)
        if url.path == "/vault-file":
            rel = unquote(parse_qs(url.query).get("p", [""])[0])
            vp = Paths(find_vault())
            p = vault.safe_vault_file(vp, rel) or _music_file(vp, rel)
            if not p:
                return self._send(404, {"error": "文件不存在"})
            ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            if p.suffix.lower() in appearance.AUDIO_EXT:
                return self._send_range(p, ctype)
            if parse_qs(url.query).get("trim") == ["1"]:          # 材料截图：裁掉四周空白（rpg/imgtrim.py）
                from . import imgtrim
                b = imgtrim.trim(p)
                if b:
                    return self._send(200, b, "image/png")
            return self._send(200, p.read_bytes(), ctype)
        rel = url.path.lstrip("/") or "index.html"
        f = (WEB_DIR / rel).resolve()
        if WEB_DIR.resolve() not in f.parents or not f.is_file():
            return self._send(404, {"error": "not found"})
        ctype = mimetypes.guess_type(f.name)[0] or "text/plain"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        self._send(200, f.read_bytes(), ctype, cache=rel.startswith("vendor/"))   # 第三方库（6MB 的思维导图编辑器）让平板缓存，不每次重下

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

