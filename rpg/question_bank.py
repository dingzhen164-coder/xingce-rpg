"""真题题库：读取训练/题库/<板块>真题.md，供 trainer 顺序实战与错题复练。

格式：## 题目 固定编号；### 知识点/题干/选项/答案/解析。选项用 A. 到 D.。
按文档出现顺序读题，编号是身份，重复编号或格式错误阻止该板块新开组。
存档 bank 含 records（题目快照与作答历史）、runs（可恢复的一组）、groups（组成绩）。
不改写用户题库；首次错误及复练都留记录，首次正确率与复练正确率分开。
"""
import re
import uuid

from . import config


class BankError(ValueError):
    pass


def boards(g):
    return list(dict.fromkeys(list(g.boards) + list(g.rules.side)))


def read(paths, board):
    if not paths.train or not board or '/' in board or '\\' in board or board in ('.', '..'):
        return [], []
    path = paths.train / '题库' / (board + '真题.md')
    if not path.is_file():
        return [], []
    text = path.read_text(encoding='utf-8-sig')
    # 文档中的示例代码块不作为真题，避免模板被误抽。
    text = re.sub(r'^```[^\n]*\n.*?^```[^\n]*$', '', text, flags=re.M | re.S)
    heads = list(re.finditer(r'^##\s+题目\s+(.+?)\s*$', text, re.M))
    questions, errors, seen = [], [], set()
    for i, h in enumerate(heads):
        ident = h.group(1).strip()
        body = text[h.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        fields = {}
        parts = list(re.finditer(r'^###\s+(知识点|题干|选项|答案|解析)\s*$', body, re.M))
        for j, p in enumerate(parts):
            name = p.group(1)
            if name in fields:
                errors.append('题目 %s：重复的 %s 小节' % (ident, name))
            fields[name] = body[p.end():parts[j + 1].start() if j + 1 < len(parts) else len(body)].strip()
        options = {}
        matches = list(re.finditer(r'^\s*([A-D])[.．、)）]\s*(.*)$', fields.get('选项', ''), re.M))
        for j, m in enumerate(matches):
            key = m.group(1)
            if key in options:
                errors.append('题目 %s：选项 %s 重复' % (ident, key))
            end = matches[j + 1].start() if j + 1 < len(matches) else len(fields.get('选项', ''))
            options[key] = fields.get('选项', '')[m.start():end].strip()[2:].strip()
        answer = fields.get('答案', '').strip().upper()
        if ident in seen:
            errors.append('题目 %s：编号重复，请使用固定且唯一的编号' % ident)
        seen.add(ident)
        if not fields.get('题干') or not fields.get('知识点') or not fields.get('解析'):
            errors.append('题目 %s：知识点、题干、解析不能为空' % ident)
        if set(options) != set('ABCD') or not all(options.values()) or answer not in options:
            errors.append('题目 %s：需要 A/B/C/D 四个选项和单个正确答案字母' % ident)
        questions.append({'key': board + '::' + ident, 'id': ident, 'board': board,
                          'topic': fields.get('知识点', ''), 'stem': fields.get('题干', ''),
                          'options': options, 'answer': answer, 'analysis': fields.get('解析', ''),
                          'source': str(path.name)})
    for line in text.splitlines():
        if re.match(r'^##\s+题目(?:\s|$)', line) and not re.match(r'^##\s+题目\s+\S', line):
            errors.append('题目标题需要编号，例如：## 题目 001')
    return questions, errors


def state(g):
    return g.state.setdefault('bank', {'records': {}, 'runs': {}, 'groups': []})


def count(g):
    n = g.rules.num('实战每组题数')
    return 15 if n == 15 else 10


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
        result.append({'board': board, 'total': len(qs), 'remaining': sum(q['key'] not in data['records'] for q in qs),
                       'first_total': len(first), 'first_correct': sum(a['ok'] for a in first),
                       'review_total': len(repeats), 'review_correct': sum(a['ok'] for a in repeats),
                       'wrong': len(wrong), 'errors': errors, 'active': bool(run),
                       'wrong_items': [{'id': r['question']['id'], 'topic': r['question']['topic'],
                                        'last': r['history'][-1], 'tries': len(r['history'])} for r in wrong]})
    return {'boards': result, 'count': count(g), 'groups': [dict(x, rank=rank(g, x['correct'], x['total'])) for x in data['groups'][-20:][::-1]],
            'streak_need': max(1, int(g.rules.num('回炉连续判对'))),
            'bonus': g.rules.xp('实战通关')}


def begin(g, board, mode):
    if board not in boards(g) or mode not in ('new', 'review'):
        raise BankError('板块或训练模式无效')
    data = state(g)
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
    qs = qs[:count(g)]
    if not qs:
        raise BankError(g.T('bank_empty') if mode == 'new' else g.T('bank_no_wrong'))
    run = {'token': uuid.uuid4().hex, 'board': board, 'mode': mode, 'questions': qs,
           'pos': 0, 'results': [], 'phase': 'answer'}
    data['runs'][slot] = run
    return run


def record(g, run, answer):
    if run['phase'] != 'answer':
        raise BankError('这道题已经提交，请点击下一题')
    q = run['questions'][run['pos']]
    if answer not in q['options']:
        raise BankError('请选择 A、B、C 或 D')
    data = state(g)
    rec = data['records'].setdefault(q['key'], {'question': q, 'history': [], 'wrong': False, 'streak': 0})
    first = not rec['history']
    result = {'date': g.t, 'answer': answer, 'ok': answer == q['answer'], 'mode': run['mode'], 'first': first}
    rec['history'].append(result)
    rec['question'] = q
    if result['ok']:
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
    return ev


def finish(g, run):
    group = {'date': g.t, 'board': run['board'], 'mode': run['mode'],
             'total': len(run['results']), 'correct': sum(r['ok'] for r in run['results']),
             'ids': [q['id'] for q in run['questions']],
             'first_count': sum(bool(r.get('first')) for r in run['results']),
             'rank': rank(g, sum(r['ok'] for r in run['results']), len(run['results']))}
    state(g)['groups'].append(group)
    del state(g)['runs'][run['board']]
    return group


def ensure_templates(paths):
    """只创建缺失模板，绝不覆盖用户已添加的题目。"""
    if not paths.train:
        return
    folder = paths.train / '题库'
    folder.mkdir(parents=True, exist_ok=True)
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
