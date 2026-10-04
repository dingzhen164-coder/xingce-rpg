"""真题题库：读取训练/题库/<板块>真题.md，供 trainer 顺序实战与错题复练。

格式：## 题目 固定编号；### 知识点/题干/选项/答案/解析。选项用 A. 到 D.。
按文档出现顺序读题，编号是身份，重复编号或格式错误阻止该板块新开组。
答案写“（待补）”或留空的题先不出（练习册答案在另一本书里时常见），网页上显示“待补答案 N 道”；
解析可以留空或写“（待补）”，作答后显示“解析待补”。
题干里可以插图：![[训练/题库/图片/<板块>/<编号>.png]]（Obsidian 写法，库内路径），图形推理、资料分析靠它。
真题由 obsidian-to-xingce 仓库的 xingce-tiku skill 批量整理入库，也可以手动添加。
存档 bank 含 records（题目快照与作答历史）、runs（可恢复的一组）、groups（组成绩）。
不改写用户题库；首次错误及复练都留记录，首次正确率与复练正确率分开。
"""
import random
import re
import uuid

from . import config


class BankError(ValueError):
    pass


def boards(g):
    return list(dict.fromkeys(list(g.boards) + list(g.rules.side)))


TODO_RE = re.compile(r'^[（(]?\s*待补\s*[)）]?$')


def read(paths, board):
    """返回 (可以出的题, 格式错误)。答案待补的题不在里面（见 pending）"""
    qs, errors = read_all(paths, board)
    return [q for q in qs if not q['pending']], errors


def pending(paths, board):
    """答案还没补上的题数"""
    return sum(q['pending'] for q in read_all(paths, board)[0])


def files(paths, board):
    """一个板块可以有多份题库：<板块>真题.md（导入、手写）+ <板块>真题-*.md（整批放进来的，如历年真题）"""
    if not paths.train or not board or '/' in board or '\\' in board or board in ('.', '..'):
        return []
    folder = paths.train / '题库'
    main = folder / (board + '真题.md')
    extra = sorted(folder.glob(glob_escape(board) + '真题-*.md')) if folder.is_dir() else []
    return [f for f in [main] + extra if f.is_file()]


def glob_escape(s):
    return re.sub(r'([\[\]*?])', r'[\1]', s)


_CACHE = {}   # 路径 → (修改时间, 大小, 解析结果)：几千道题的大题库不用每次重读


def read_all(paths, board):
    questions, errors, seen = [], [], set()
    for path in files(paths, board):
        st = path.stat()
        hit = _CACHE.get(str(path))
        if not hit or hit[:2] != (st.st_mtime_ns, st.st_size):
            hit = (st.st_mtime_ns, st.st_size, _parse(path, board))
            _CACHE[str(path)] = hit
        qs, errs = hit[2]
        errors += errs
        for q in qs:
            if q['id'] in seen:
                errors.append('题目 %s：编号重复，请使用固定且唯一的编号' % q['id'])
            seen.add(q['id'])
            questions.append(dict(q))
    return questions, errors


def _parse(path, board):
    text = path.read_text(encoding='utf-8-sig')
    # 文档中的示例代码块不作为真题，避免模板被误抽。
    text = re.sub(r'^```[^\n]*\n.*?^```[^\n]*$', '', text, flags=re.M | re.S)
    heads = list(re.finditer(r'^##\s+题目\s+(.+?)\s*$', text, re.M))
    questions, errors = [], []
    for i, h in enumerate(heads):
        ident = h.group(1).strip()
        body = text[h.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        fields = {}
        parts = list(re.finditer(r'^###\s+(知识点|试卷|模块|题号|题干|选项|答案|解析)\s*$', body, re.M))
        for j, p in enumerate(parts):
            name = p.group(1)
            if name in fields:
                errors.append('题目 %s：重复的 %s 小节' % (ident, name))
            fields[name] = body[p.end():parts[j + 1].start() if j + 1 < len(parts) else len(body)].strip()
        options = {}
        matches = list(re.finditer(r'^[ \t]*([A-D])[.．、)）][ \t]*(.*)$', fields.get('选项', ''), re.M))
        for j, m in enumerate(matches):
            key = m.group(1)
            if key in options:
                errors.append('题目 %s：选项 %s 重复' % (ident, key))
            end = matches[j + 1].start() if j + 1 < len(matches) else len(fields.get('选项', ''))
            options[key] = fields.get('选项', '')[m.start():end].strip()[2:].strip()
        answer = fields.get('答案', '').strip().upper()
        todo = not answer or bool(TODO_RE.match(answer))
        analysis = fields.get('解析', '').strip()
        if TODO_RE.match(analysis):
            analysis = ''
        if not fields.get('题干') or not fields.get('知识点'):
            errors.append('题目 %s：知识点、题干不能为空' % ident)
        if set(options) != set('ABCD') or not all(options.values()) or (not todo and answer not in options):
            errors.append('题目 %s：需要 A/B/C/D 四个选项和单个正确答案字母（不知道答案就写“（待补）”）' % ident)
        questions.append({'key': board + '::' + ident, 'id': ident, 'board': board,
                          'topic': fields.get('知识点', ''), 'stem': fields.get('题干', ''),
                          'options': options, 'answer': '' if todo else answer, 'analysis': analysis,
                          'source': str(path.name), 'pending': todo, 'module': fields.get('模块', ''),
                          # 同一道题可能出现在几张卷子里（联考各省卷共用题），试卷、题号一行一个、一一对应
                          'papers': [x.strip() for x in fields.get('试卷', '').splitlines() if x.strip()],
                          'nums': [int(x) for x in fields.get('题号', '').split() if x.isdigit()]})
        questions[-1]['paper'] = (questions[-1]['papers'] or [''])[0]
    for line in text.splitlines():
        if re.match(r'^##\s+题目(?:\s|$)', line) and not re.match(r'^##\s+题目\s+\S', line):
            errors.append('题目标题需要编号，例如：## 题目 001')
    return questions, errors


TUTOR_FILE = '师傅解惑.md'
_TUTOR_HEAD = re.compile(r'^## (\S+) · ', re.M)


def tutor_notes(paths):
    """试炼复盘里请师傅讲过的题：训练/题库/师傅解惑.md，{编号: 讲解}"""
    f = paths.train / '题库' / TUTOR_FILE if paths.train else None
    if not f or not f.is_file():
        return {}
    text = f.read_text(encoding='utf-8')
    heads = list(_TUTOR_HEAD.finditer(text))
    return {h.group(1): text[text.index('\n', h.start()) + 1:heads[i + 1].start() if i + 1 < len(heads) else len(text)].strip()
            for i, h in enumerate(heads)}


def save_tutor_note(paths, q, text, date):
    """存一题的师傅讲解；同一题再讲一次就换成新的"""
    notes = tutor_notes(paths)
    notes.pop(q['id'], None)
    f = paths.train / '题库' / TUTOR_FILE
    old = f.read_text(encoding='utf-8') if f.is_file() else ''
    # 保留原顺序，只换这一题
    keep = [m for m in re.split(r'(?=^## \S+ · )', old, flags=re.M) if m.strip() and not m.startswith('## %s · ' % q['id'])]
    if not keep or not keep[0].startswith('# '):
        keep.insert(0, '# 师傅解惑\n\n> 试炼复盘里点「师傅解惑」的讲解，按题目编号存在这里；同一题再问会换成新的。\n\n')
    keep.append('## %s · %s（%s）\n%s\n\n' % (q['id'], q['board'], date, text.strip()))
    f.write_text(''.join(keep), encoding='utf-8', newline='\n')
    return '训练/题库/' + TUTOR_FILE


TUTOR_HEAD = '【师傅解惑】'


def save_tutor_to_bank(paths, q, text, date):
    """把师傅解惑写进这道题在题库文件里的“### 解析”末尾（原解析不动）；同一题再问就换掉上一次的。
    返回写进的文件名；找不到这道题返回空"""
    for f in files(paths, q['board']):
        t = f.read_text(encoding='utf-8-sig')
        h = re.search(r'^## 题目 %s\s*$' % re.escape(q['id']), t, re.M)
        if not h:
            continue
        nxt = re.search(r'^## 题目 ', t[h.end():], re.M)
        end = h.end() + nxt.start() if nxt else len(t)
        block = t[h.start():end]
        m = re.search(r'^### 解析[ \t]*\n(.*?)(?=^### |\Z)', block, re.M | re.S)
        body = m.group(1) if m else ''
        k = body.find(TUTOR_HEAD)
        keep = (body[:k] if k >= 0 else body).strip()
        if re.fullmatch(r'[（(]?\s*待补\s*[)）]?', keep):
            keep = ''
        clean = re.sub(r'^(#+)\s', lambda x: '＃' * len(x.group(1)) + ' ', text.strip(), flags=re.M)
        new = (keep + '\n\n' if keep else '') + '%s（%s）\n%s\n\n' % (TUTOR_HEAD, date, clean)
        if m:
            block = block[:m.start(1)] + new + block[m.end(1):]
        else:
            block = block.rstrip('\n') + '\n### 解析\n' + new
        f.write_text(t[:h.start()] + block + t[end:], encoding='utf-8', newline='\n')
        return f.name
    return ''


def state(g):
    return g.state.setdefault('bank', {'records': {}, 'runs': {}, 'groups': []})


SET_PREFIX = '套:'
SET_ID = re.compile(r'^(.+)-(\d{2,3})-(\d{2,3})$')
PAPER_BOOK = '历年真题'
# 一张卷子里判断推理的出题顺序；同一部分里按题号（编号里的数字）排
PAPER_ORDER = {'图形推理': 0, '定义判断': 1, '类比推理': 2, '形式逻辑': 3, '论证逻辑': 3, '常识判断': 4}


def sets_of(q):
    """题目属于哪几套：有“### 试卷”的按卷子（一张卷子的一个模块为一套，一道题可能在几张卷子里）；
    练习册按编号 前缀-套-题 → “前缀-套”；其他题没有套"""
    if q.get('papers'):
        return ['%s · %s' % (p, q['module']) if q.get('module') else p for p in q['papers']]
    m = SET_ID.match(q.get('id') or '')
    return ['%s-%s' % (m.group(1), m.group(2))] if m else []


POINT_PREFIX = '点:'
_HEAD = re.compile(r'[-－—（(/]')


# 同一类考点在蒸馏数据里有好几种写法（削弱论证 / 论证削弱 / 削弱质疑 / 削弱型…），按板块归到固定的几类；
# 归不进去的保留原名（不强行合并），题目上的细考点不动，只影响目录和知识点试炼的分组
FAMILIES = {
    '论证逻辑': [('削弱|质疑|反驳', '削弱论证'), ('加强|强化|增强|支持', '加强论证'), ('前提|假设|预设|补充', '前提假设'),
                ('解释|原因|矛盾', '解释说明'), ('评价|焦点|争论', '评价论证'), ('谬误|错误|缺陷|漏洞|悖论', '逻辑谬误'),
                ('平行|相似', '平行结构'), ('结构|方式|方法|思路|策略|模型|论证|推理|逻辑|判断', '论证综合')],
    '形式逻辑': [('平行|相似|结构', '平行结构'), ('真假|真话|假话', '真假推理'),
                ('翻译|复合|选言|假言|联言|直言|模态|三段论|必然|命题|条件', '翻译推理'),
                ('排序|排列|组合|分析|对应|匹配|排队|位置|周期|数学|数量|综合|规则', '分析推理'),
                ('日常|结论|归纳|推出|推断|信息', '归纳推理'), ('集合|概念|关系', '概念关系'), ('谬误|错误|悖论', '逻辑谬误')],
    '定义判断': [('多定义', '多定义'), ('单定义|规定', '单定义')],
    '类比推理': [('语义|近义|反义|比喻|象征|感情色彩', '语义关系'), ('语法|主谓|动宾|偏正|并列结构', '语法关系'),
                ('填空', '填空式类比'), ('三词|多词|多项', '多词类比'),
                ('逻辑|集合|包含|种属|组成|交叉|并列|全同|对立|矛盾|反对', '逻辑关系'),
                ('对应|因果|功能|属性|材料|时间|顺承|必要|条件|职业|工具|场所|原料|目的', '对应关系')],
    '图形推理': [('空间|立体|展开|折纸|拼合|三视图|视图|截面|切面|拼接', '空间重构'),
                ('数量|计数|笔画|一笔画|面|线|点|角|交点|封闭|部分', '数量规律'),
                ('位置|平移|旋转|翻转|移动|方位', '位置规律'), ('样式|叠加|遍历|黑白|运算|求同|求异', '样式规律'),
                ('属性|对称|曲直|开闭|凹凸', '属性规律'), ('分组|分类', '分组分类'), ('功能|特殊|标记', '功能元素')],
}


def topic_head(t, board=''):
    """知识点大类：“削弱论证-因果倒置（…）” → “削弱论证”；有归类表的板块再归到固定的几类"""
    parts = [x.strip() for x in _HEAD.split(t or '') if x.strip()]
    head = parts[0] if parts else (t or '')
    if len(parts) > 1 and head in (board, '图形推理', '类比推理', '定义判断', '逻辑判断', '判断推理'):
        head = parts[1]          # “图形推理-数量规律…”：第一段只是板块名，看第二段
    for pat, name in FAMILIES.get(board, ()):
        if re.search(pat, head):
            return name
    return head


def is_set(slot):
    """不是单个板块的组：整套（套:…）或知识点（点:板块:大类）"""
    return str(slot or '').startswith((SET_PREFIX, POINT_PREFIX))


def label(slot):
    """组名给人看：套:花生600题言语-03 → 花生600题言语 第03套；试卷名原样"""
    if not is_set(slot):
        return slot
    if slot.startswith(POINT_PREFIX):
        board, _, topic = slot[len(POINT_PREFIX):].partition(':')
        return '%s · %s' % (board, topic)
    name = slot[len(SET_PREFIX):]
    m = re.match(r'^(.+)-(\d{2,3})$', name)
    return '%s 第%s套' % (m.group(1), m.group(2)) if m else name


def _order(q, name=''):
    if q.get('papers'):
        names = sets_of(q)
        i = names.index(name) if name in names else 0
        if i < len(q.get('nums', [])):
            return (0, q['nums'][i])
        n = re.findall(r'\d+', q['id'])
        return (PAPER_ORDER.get(q['board'], 9), int(n[-1]) if n else 0)
    return (0, int(SET_ID.match(q['id']).group(3)))


def _set_questions(g, name):
    """一套题可能跨板块（言语书一套里既有片段阅读又有逻辑填空；一张真题卷有图形、定义、类比、逻辑）"""
    qs, errors = [], []
    for board in boards(g):
        got, err = read(g.paths, board)
        mine = [q for q in got if name in sets_of(q)]
        if mine:
            errors += err
        qs += mine
    return sorted(qs, key=lambda q: _order(q, name)), errors


def sets(g):
    """整套试炼的目录：练习册按书（前缀）分；历年真题一张卷子一套，按年份从新到旧"""
    data, books = state(g), {}
    for board in boards(g):
        for q in read(g.paths, board)[0]:
            book = PAPER_BOOK + ('·' + q['module'] if q.get('module') else '') if q.get('papers') else None
            for name in sets_of(q):
                num = name if book else name.rsplit('-', 1)[1]
                x = books.setdefault(book or name.rsplit('-', 1)[0], {}).setdefault(
                    num, {'name': name, 'set': num, 'total': 0, 'done': 0, 'boards': {}})
                x['total'] += 1
                x['done'] += q['key'] in data['records']
                x['boards'][board] = x['boards'].get(board, 0) + 1
    out = []
    for book, d in books.items():
        paper = book.startswith(PAPER_BOOK)
        if paper:
            keys = sorted(d, key=lambda k: (-int((re.match(r'\d{4}', k) or [0])[0]), k))
        else:
            keys = sorted(d, key=int)
        items = [dict(d[k], active=(SET_PREFIX + d[k]['name']) in data['runs']) for k in keys]
        for x in items:
            if paper:
                x['year'] = (re.match(r'\d{4}', x['name']) or [''])[0]
        nxt = next((x for x in items if x['active']), None) or next((x for x in items if x['done'] < x['total']), None)
        out.append({'book': book, 'paper': paper, 'sets': items, 'next': nxt['name'] if nxt else '',
                    'finished': sum(x['done'] == x['total'] for x in items)})
    modules = ['政治理论', '常识判断', '言语理解与表达', '数量关系', '判断推理', '资料分析']
    return sorted(out, key=lambda b: (not b['paper'], next((i for i, m in enumerate(modules) if m in b['book']), 9)))


def count(g):
    n = g.rules.num('实战每组题数')
    return 15 if n == 15 else 10


ORDERS = ('seq', 'shuffle')


def order(g):
    """出题顺序：seq 按题库顺序；shuffle 从没做过的题里随机抽（做过的照样不出）"""
    o = state(g).get('order')
    return o if o in ORDERS else 'seq'


def _pick(g, qs):
    if order(g) == 'shuffle' and len(qs) > count(g):
        return random.sample(qs, count(g))
    return qs[:count(g)]


def summary(g):
    data = state(g)
    result = []
    for board in boards(g):
        qs, errors = read(g.paths, board)
        records = [r for r in data['records'].values() if r['question']['board'] == board]
        first = [r['history'][0] for r in records if r['history']]
        repeats = [a for r in records for a in r['history'][1:]]
        wrong = [r for r in records if r.get('wrong')]
        run = next((r for r in data['runs'].values() if r['board'] == board), None)
        result.append({'board': board, 'total': len(qs), 'pending': pending(g.paths, board), 'remaining': sum(q['key'] not in data['records'] for q in qs),
                       'first_total': len(first), 'first_correct': sum(a['ok'] for a in first),
                       'review_total': len(repeats), 'review_correct': sum(a['ok'] for a in repeats),
                       'method_total': sum(a.get('method_ok') is not None for a in first),
                       'method_correct': sum(a.get('method_ok') is True for a in first),
                       'wrong': len(wrong), 'errors': errors, 'active': bool(run),
                       'wrong_items': [{'id': r['question']['id'], 'topic': r['question']['topic'],
                                        'last': r['history'][-1], 'tries': len(r['history'])} for r in wrong]})
    return {'boards': result, 'count': count(g), 'order': order(g),
            'groups': [dict(x, rank=rank(g, x['correct'], x['total']), label=label(x['board'])) for x in data['groups'][-20:][::-1]],
            'streak_need': max(1, int(g.rules.num('回炉连续判对'))),
            'bonus': g.rules.xp('实战通关'), 'tower': tower(g), 'sets': sets(g)}


def begin(g, board, mode):
    data = state(g)
    if str(board).startswith(POINT_PREFIX) and mode == 'new':
        # 知识点试炼：这个板块里这一类知识点还没做过的题，按题库顺序一组
        if board in data['runs']:
            return data['runs'][board]
        b, _, topic = board[len(POINT_PREFIX):].partition(':')
        if b not in boards(g):
            raise BankError('板块无效')
        qs, errors = read(g.paths, b)
        if errors:
            raise BankError('\n'.join(errors))
        qs = _pick(g, [q for q in qs if topic_head(q['topic'], b) == topic and q['key'] not in data['records']])
        if not qs:
            raise BankError('「%s · %s」的题已经全部做过了（答案待补的不出）' % (b, topic))
        run = {'token': uuid.uuid4().hex, 'board': board, 'mode': 'new', 'questions': qs,
               'pos': 0, 'results': [], 'phase': 'answer'}
        data['runs'][board] = run
        return run
    if is_set(board) and mode == 'new':
        # 整套试炼：这一套还没做过的题一次做完，不受“每轮 10/15 关”限制
        if board in data['runs']:
            return data['runs'][board]
        qs, errors = _set_questions(g, board[len(SET_PREFIX):])
        if errors:
            raise BankError('\n'.join(errors))
        qs = [q for q in qs if q['key'] not in data['records']]
        if not qs:
            raise BankError('%s 已经全部做完（答案待补的题还不能出）' % label(board))
        run = {'token': uuid.uuid4().hex, 'board': board, 'mode': 'new', 'questions': qs,
               'pos': 0, 'results': [], 'phase': 'answer'}
        data['runs'][board] = run
        return run
    if board not in boards(g) or mode not in ('new', 'review'):
        raise BankError('板块或训练模式无效')
    # 同板块最多一组，防止两个标签页重复抽题；已开始的组使用题目快照。
    slot = board
    if slot in data['runs']:
        return data['runs'][slot]
    if mode == 'new':
        qs, errors = read(g.paths, board)
        if errors:
            raise BankError('\n'.join(errors))
        qs = [q for q in qs if q['key'] not in data['records']]
    else:
        qs = [r['question'] for r in data['records'].values()
              if r['question']['board'] == board and r.get('wrong')]
    qs = _pick(g, qs) if mode == 'new' else qs[:count(g)]
    if not qs:
        raise BankError(g.T('bank_empty') if mode == 'new' else g.T('bank_no_wrong'))
    run = {'token': uuid.uuid4().hex, 'board': board, 'mode': mode, 'questions': qs,
           'pos': 0, 'results': [], 'phase': 'answer'}
    data['runs'][slot] = run
    return run


def record(g, run, answer, reasoning="", method_ok=None, feedback=""):
    if run['phase'] != 'answer':
        raise BankError('这道题已经提交，请点击下一题')
    q = run['questions'][run['pos']]
    if answer not in q['options']:
        raise BankError('请选择 A、B、C 或 D')
    data = state(g)
    rec = data['records'].setdefault(q['key'], {'question': q, 'history': [], 'wrong': False, 'streak': 0})
    before_floor = tower(g)['cleared']
    first = not rec['history']
    result = {'date': g.t, 'answer': answer, 'ok': answer == q['answer'], 'mode': run['mode'], 'first': first}
    result.update(reasoning=reasoning, method_ok=method_ok, feedback=feedback)
    rec['history'].append(result)
    rec['question'] = q
    if result['ok'] and method_ok is not False:
        rec['streak'] += 1
        if rec['streak'] >= max(1, int(g.rules.num('回炉连续判对'))):
            rec['wrong'] = False
    else:
        rec['streak'], rec['wrong'] = 0, True
    run['results'].append(result)
    run['phase'] = 'analysis'
    # 每题只有首次作答发修为，复练仍计时，避免无限刷同一道题。
    ev = g._award(g.rules.xp('实战答对') if result['ok'] else g.rules.xp('实战答错'),
                  'bank', q['board'], q['key'], result['ok'],
                  '%s · %s 第%s关' % (g.T('bank'), q['board'], q['id'])) if first else []
    progress = tower(g)
    if first and progress['cleared'] > before_floor:
        msg = '🗼 已完成 %s 道新题，登上试炼塔第 %s 层！' % (progress['completed'], progress['cleared'])
        if progress['summit']:
            msg += ' 百层登顶，试炼圆满！'
        ev.append({'kind': 'info', 'msg': msg})
    return ev


def finish(g, run, keep=False):
    """记一组成绩。keep=True：交卷后还要逐题复盘，组先留在 runs 里，复盘结束再 close"""
    group = {'date': g.t, 'board': run['board'], 'mode': run['mode'],
             'total': len(run['results']), 'correct': sum(r['ok'] for r in run['results']),
             'method_total': sum(r.get('method_ok') is not None for r in run['results']),
             'method_correct': sum(r.get('method_ok') is True for r in run['results']),
             'ids': [q['id'] for q in run['questions']],
             'boards': sorted({q['board'] for q in run['questions']}),
             'first_count': sum(bool(r.get('first')) for r in run['results']),
             'rank': rank(g, sum(r['ok'] for r in run['results']), len(run['results']))}
    state(g)['groups'].append(group)
    if keep:
        run['settled'] = group
    else:
        close(g, run)
    return group


SELF_PREFIX = '自练-'


def add_question(g, body):
    """红尘历练里录一道自练的好题，追加到 <板块>真题.md，编号 自练-年月日-序号"""
    board = str(body.get('board') or '').strip()
    if board not in boards(g):
        raise BankError('先选一个板块')
    stem = str(body.get('stem') or '').strip()
    opts = {k: re.sub(r'\s*\n\s*', ' ', str((body.get('options') or {}).get(k) or '').strip()) for k in 'ABCD'}
    answer = str(body.get('answer') or '').strip().upper()
    if not stem:
        raise BankError('题干不能为空')
    if not all(opts.values()):
        raise BankError('A、B、C、D 四个选项都要填')
    if answer not in ('ABCD') or len(answer) != 1:
        answer = '（待补）'
    topic = re.sub(r'\s+', ' ', str(body.get('topic') or '').strip()) or '自练'
    source = re.sub(r'\s+', ' ', str(body.get('source') or '').strip())
    analysis = str(body.get('analysis') or '').strip() or '（待补）'
    if source:
        stem = '（%s）%s' % (source, stem)
    folder = g.paths.train / '题库'
    folder.mkdir(parents=True, exist_ok=True)
    day = g.t.replace('-', '')
    taken = {q['id'] for q in read_all(g.paths, board)[0]}
    n = 1
    while '%s%s-%02d' % (SELF_PREFIX, day, n) in taken:
        n += 1
    ident = '%s%s-%02d' % (SELF_PREFIX, day, n)
    block = ('\n## 题目 %s\n### 知识点\n%s\n### 题干\n%s\n### 选项\n%s\n### 答案\n%s\n### 解析\n%s\n'
             % (ident, topic, stem, '\n'.join('%s. %s' % (k, v) for k, v in opts.items()), answer, analysis))
    path = folder / (board + '真题.md')
    with path.open('a', encoding='utf-8', newline='\n') as f:
        f.write(block)
    q = next((x for x in read_all(g.paths, board)[0] if x['id'] == ident), None)
    return {'id': ident, 'board': board, 'file': path.name, 'key': board + '::' + ident, 'pending': bool(q and q['pending'])}


def close(g, run):
    state(g)['runs'].pop(run['board'], None)


def ensure_templates(paths):
    """只创建缺失模板，绝不覆盖用户已添加的题目。"""
    if not paths.train:
        return
    folder = paths.train / '题库'
    folder.mkdir(parents=True, exist_ok=True)
    for board in ('图形推理', '资料分析'):  # 这两个板块的题要配图
        (folder / '图片' / board).mkdir(parents=True, exist_ok=True)
    from .paths import DEFAULTS_DIR
    for src in (DEFAULTS_DIR / '题库').glob('*.md'):
        dst = folder / src.name
        if not dst.exists():
            with dst.open('w', encoding='utf-8', newline='\n') as f:
                f.write(src.read_text(encoding='utf-8'))


def rank(g, correct, total):
    """品评由程序计算；旧组战绩也可按当前规则显示，不改写历史。"""
    rate = correct / total if total else 0
    if total and correct == total:
        return 3
    high = max(0, min(1, g.rules.num('试炼上品正确率')))
    mid = max(0, min(high, g.rules.num('试炼中品正确率')))
    return 2 if rate >= high else 1 if rate >= mid else 0


def tower(g):
    """全板块共用一座塔；每题首次提交计一次，答错也计，复练不重复计。
    默认 5000 题 / 100 层。用累计门槛分配题量，非整除目标也能准确登顶。
    直接由 records 推导旧进度，删题库原文不会丢失爬塔成绩，无需重写存档。
    """
    layers = max(1, min(1000, int(g.rules.num('试炼塔层数'))))
    total = max(layers, int(g.rules.num('试炼塔总题数')))
    completed = sum(bool(r.get('history')) for r in state(g)['records'].values())
    boundaries = [(i * total + layers - 1) // layers for i in range(layers + 1)]
    cleared = sum(completed >= b for b in boundaries[1:])
    current = min(cleared + 1, layers)
    lower = boundaries[cleared] if cleared < layers else total
    target = boundaries[current]
    return {'layers': layers, 'total': total, 'completed': completed,
            'cleared': cleared, 'current': current, 'summit': cleared == layers,
            'floor_done': min(max(0, completed - lower), target - lower),
            'floor_total': target - lower, 'next_at': target,
            'remaining': max(0, target - completed),
            'per_floor': (total + layers - 1) // layers}
