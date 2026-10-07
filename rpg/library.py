"""藏经阁·经卷：题库目录、搜题、看题。只读题库和作答记录，不改任何文件。

- catalog：每个板块多少题、做过几道、做错几道，知识点目录（按题数排）
- search：关键词（空格分开，全部都要命中）在编号、题干、选项、知识点、试卷里找；可按板块、知识点、作答状态筛
- detail：一道题的题干、选项（图片转网页块），答案、解析和自己的作答记录
"""
import re
from collections import Counter

from . import question_bank

PAGE = 30
topic_head = question_bank.topic_head


IMG = re.compile(r'!\[\[[^\]]*\]\]|!\[[^\]]*\]\([^)]*\)')


def _status(data, q):
    rec = data['records'].get(q['key'])
    if q['pending']:
        return 'pending'
    if not rec or not rec.get('history'):
        return 'new'
    return 'wrong' if rec.get('wrong') else 'done'


def catalog(g):
    data = question_bank.state(g)
    out = []
    for board in question_bank.boards(g):
        qs, errors = question_bank.read_all(g.paths, board)
        if not qs:
            continue
        st = Counter(_status(data, q) for q in qs)
        topics = Counter(topic_head(q['topic'], board) for q in qs)
        left = Counter(topic_head(q['topic'], board) for q in qs if _status(data, q) == 'new')
        out.append({'board': board, 'total': len(qs), 'new': st['new'], 'done': st['done'], 'wrong': st['wrong'],
                    'pending': st['pending'], 'errors': len(errors),
                    'topics': [{'name': k, 'count': v, 'left': left[k]} for k, v in topics.most_common(60)],
                    'more_topics': max(0, len(topics) - 60)})
    return {'boards': out, 'total': sum(b['total'] for b in out)}


def _snippet(q):
    s = IMG.sub('［图］', q['stem'])
    s = re.sub(r'^（[^）]{2,40}）', '', s.strip())   # 去掉题干前的来源括号
    return re.sub(r'\s+', ' ', s)[:90]


def search(g, body):
    words = [w for w in str(body.get('q') or '').lower().split() if w]
    board, topic, status = body.get('board') or '', body.get('topic') or '', body.get('status') or ''
    page = max(0, int(body.get('page') or 0))
    data = question_bank.state(g)
    hits = []
    for b in question_bank.boards(g):
        if board and b != board:
            continue
        for q in question_bank.read_all(g.paths, b)[0]:
            if topic and topic_head(q['topic'], b) != topic:
                continue
            st = _status(data, q)
            if status and st != status:
                continue
            if words:
                hay = ' '.join([q['id'], q['topic'], q['stem'], ' '.join(q['options'].values()), ' '.join(q.get('papers', []))]).lower()
                if not all(w in hay for w in words):
                    continue
            hits.append((q, st))
    rows = [{'key': q['key'], 'id': q['id'], 'board': q['board'], 'topic': q['topic'], 'status': st,
             'paper': question_bank.label('套:' + q['papers'][0]) if q.get('papers') else '', 'text': _snippet(q)}
            for q, st in hits[page * PAGE:(page + 1) * PAGE]]
    return {'total': len(hits), 'page': page, 'pages': (len(hits) + PAGE - 1) // PAGE, 'rows': rows}


def detail(g, key):
    from . import trainer
    board, _, ident = str(key).partition('::')
    q = next((x for x in question_bank.read_all(g.paths, board)[0] if x['id'] == ident), None)
    if not q:
        raise question_bank.BankError('找不到这道题（题库可能改过）')
    rec = question_bank.state(g)['records'].get(q['key']) or {}
    return {'key': q['key'], 'id': q['id'], 'board': q['board'], 'topic': q['topic'], 'papers': q.get('papers', []),
            'stem': trainer._bank_blocks(g, board, q['stem']),
            'options': [{'k': k, 'blocks': trainer._bank_blocks(g, board, v)} for k, v in q['options'].items()],
            'answer': q['answer'] or '（待补）',
            'analysis': trainer._bank_blocks(g, board, q['analysis'] or '（暂无解析）'),
            'history': [{'date': h.get('date'), 'answer': h.get('answer'), 'ok': h.get('ok'), 'seconds': h.get('seconds')}
                        for h in rec.get('history', [])],
            'status': _status(question_bank.state(g), q),
            'tutor': _tutor(g, board, q)}


def _tutor(g, board, q):
    """旧版只存在 师傅解惑.md 的讲解；已经写进题库解析的就不重复显示"""
    from . import trainer
    if question_bank.TUTOR_HEAD in (q['analysis'] or ''):
        return []
    note = question_bank.tutor_notes(g.paths).get(q['id'])
    return trainer._bank_blocks(g, board, note) if note else []
