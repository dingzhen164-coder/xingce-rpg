"""藏经阁·成语实词录：逻辑填空做完一组，就把每道题正确选项里的成语 / 实词收成词条，按首字拼音首字母排。

一个词条（正确选项里的一个词，几个空就几个词条）里有：
- 释义：从解析里摘“X项“词”指 / 形容 / 比喻 / 意为……”那一句；
- 本题其他选项：同一个空其他选项的词，各带解析里的释义；
- 辨析：解析里讲这个空的那一段（“第一空 / 第二空……”，没有分空就是提到这个词的那段）；
- 真题：题库里的编号、试卷，网页上一点就跳到玉简里这道题，Obsidian 里是 [[题库文件#题目 编号]]。
同一个词在别的题里又考到，就在这个词条下面再挂一条出处。
存档 state["idioms"]，每次收录后整份重写 训练/成语实词录.md。
"""
import re

from . import question_bank

FILE = '成语实词录.md'
CN_NUM = '一二三四五六七八九十'

# GB2312 一级汉字按拼音排序：用编码区间认首字母（标准库就能做，不用装拼音库）。二级字不按拼音排，认不出归“#”
_GB = [(0xB0A1, 'A'), (0xB0C5, 'B'), (0xB2C1, 'C'), (0xB4EE, 'D'), (0xB6EA, 'E'), (0xB7A2, 'F'), (0xB8C1, 'G'),
       (0xB9FE, 'H'), (0xBBF7, 'J'), (0xBFA6, 'K'), (0xC0AC, 'L'), (0xC2E8, 'M'), (0xC4C3, 'N'), (0xC5B6, 'O'),
       (0xC5BE, 'P'), (0xC6DA, 'Q'), (0xC8BB, 'R'), (0xC8F6, 'S'), (0xCBFA, 'T'), (0xCDDA, 'W'), (0xCEF4, 'X'),
       (0xD1B9, 'Y'), (0xD4D1, 'Z'), (0xD7FA, None)]
# 多音字按 GB2312 里的位置（常用读音）；个别排错的在这里补
_FIX = {}
DEF = re.compile(r'^(?:一词|这个词|本义|的意思)?(?:是|即|就是|为)?(?:指|形容|比喻|意为|意思是|意指|原指|本指|多指|常指|泛指|特指|表示|喻指|借指|用来|用于|谓|'
                 r'强调|侧重|着重|突出|重在|偏重|一般指|通常指|多用于|多形容|总以为|含义|现指|今指|旧指|后指|引申为|引申指|形容的是)')
# 关联词、虚词不收（成语实词录只收成语和实词）
FUNCTION = set('就 才 也 都 而 且 却 但 则 并 又 还 更 再 已 及 与 和 或 即 虽 若 因 故 乃 之 其 以 于 为 所 被 把 将'.split()) | {
    '无论', '不论', '只有', '只要', '即使', '尽管', '虽然', '因为', '所以', '如果', '假如', '既然', '不但', '而且', '不仅', '但是',
    '然而', '因此', '甚至', '并且', '以及', '或者', '除非', '即便', '哪怕', '何况', '况且', '于是', '可见', '从而', '进而', '反而',
    '不管', '不过', '可是', '只是', '仍然', '依然', '已经', '曾经', '正在', '将要', '必须', '应该', '可能', '或许', '也许', '究竟', '到底', '虽说', '固然', '与其', '不如', '宁可', '一旦', '由于', '以致', '以至', '乃至', '就是', '而是', '不是', '还是'}


def is_word(w):
    return bool(w) and '…' not in w and '...' not in w and w not in FUNCTION and not re.fullmatch(r'[\W\d_]+', w)
STOP = re.compile(r'；|。|\n|“|，(?:[A-D](?:项|、)|均|都|皆|符合|不符合|与文|与语|与后|与前|与“|与大|与上|与下|置于|用于此|填入|放到|放于|体现|说明|对应|和文|同文|这里|此处|放在|放入|用在|代入|搭配|故|保留|排除|当选|文段|可以|能够|不能|无法|没有|而文|但文|且)')


def letter(word):
    ch = (word or '#')[0]
    if ch in _FIX:
        return _FIX[ch]
    if 'a' <= ch.lower() <= 'z':
        return ch.upper()
    try:
        b = ch.encode('gb2312')
    except UnicodeEncodeError:
        return '#'
    if len(b) != 2:
        return '#'
    code = b[0] * 256 + b[1]
    for (lo, L), (hi, _) in zip(_GB, _GB[1:]):
        if lo <= code < hi:
            return L
    return '#'


def split_words(opt):
    """“蕴含  方兴未艾” → [蕴含, 方兴未艾]"""
    return [w for w in re.split(r'[\s　，,、；;/｜|]+', (opt or '').strip()) if w]


def _analysis(q):
    text = q.get('analysis') or ''
    text = text.split(question_bank.TUTOR_HEAD)[0]
    return re.split(r'\n?【(?:文段出处|文段来源|出处)】', text)[0].strip()


def define(analysis, word):
    """解析里这个词的释义：“词”后面紧跟“指 / 形容 / 比喻……”的那一截；没有就返回空"""
    for m in re.finditer('“%s”' % re.escape(word), analysis):
        rest = analysis[m.end():]
        if not DEF.match(rest):
            continue
        cut = STOP.search(rest)
        return rest[:cut.start() if cut else 120].strip('，, ')[:160]
    return ''


def _blank_paragraph(analysis, i, n, words):
    """讲第 i 空的那一段：有“第X空”的按空号找，否则找提到这些词的段落"""
    paras = [p.strip() for p in analysis.split('\n') if p.strip()]
    if n > 1:
        tag = '第%s空' % CN_NUM[i] if i < len(CN_NUM) else ''
        hit = [p for p in paras if tag and p.startswith(tag)] or [p for p in paras if tag and tag in p[:30]]
        if hit:
            return hit[0]
    hit = [p for p in paras if any('“%s”' % w in p for w in words)]
    return '\n'.join(hit[:2]) if hit else (paras[0] if paras else '')


def is_fill(q):
    return q.get('board') == '逻辑填空' or str(q.get('topic', '')).startswith('逻辑填空')


def entries_of(q):
    """一道逻辑填空题 → [(词, 词条出处)]"""
    ans = (q.get('answer') or '').strip().upper()
    opts = q.get('options') or {}
    if ans not in opts:
        return []
    split = {k: split_words(v) for k, v in opts.items()}
    right = split[ans]
    n = len(right)
    if not n or any(len(v) != n for v in split.values()):   # 各选项的词数对不齐（写法不统一）：整个选项当一个词条
        n, right = 1, [opts[ans].strip()]
        split = {k: [v.strip()] for k, v in opts.items()}
    ana = _analysis(q)
    out = []
    for i, w in enumerate(right):
        if not is_word(w):
            continue
        others = []
        for k in sorted(split):
            if k == ans:
                continue
            o = split[k][i]
            if o != w and o not in [x['word'] for x in others]:
                others.append({'word': o, 'option': k, 'meaning': define(ana, o)})
        out.append((w, {'key': q['key'], 'id': q['id'], 'board': q['board'], 'source': q.get('source', ''),
                        'paper': (q.get('papers') or [q.get('paper') or ''])[0],
                        'blank': i + 1, 'blanks': n, 'answer': ans, 'option_text': opts[ans],
                        'meaning': define(ana, w), 'others': others,
                        'compare': _blank_paragraph(ana, i, n, [w] + [x['word'] for x in others])[:900]}))
    return out


def data(g):
    return g.state.setdefault('idioms', {})


def harvest(g, questions):
    """收录一批题（一组做完时调用）。返回新收的词（已有词条又考到的不算新词，但会挂上新出处）"""
    book = data(g)
    new = []
    for q in questions:
        if not is_fill(q):
            continue
        for w, src in entries_of(q):
            e = book.get(w)
            if not e:
                e = book[w] = {'word': w, 'letter': letter(w), 'added': g.t, 'sources': []}
                new.append(w)
            old = next((s for s in e['sources'] if s['key'] == src['key'] and s['blank'] == src['blank']), None)
            src['date'] = old['date'] if old else g.t
            if old:
                e['sources'][e['sources'].index(old)] = src     # 题库解析更新过：用新的
            else:
                e['sources'].append(src)
    if questions:
        write_file(g)
    return new


def backfill(g):
    """把以前做过的逻辑填空题（作答记录里有的）一次收进来"""
    keys = {k for k, r in question_bank.state(g)['records'].items() if r.get('history')}
    boards = [b for b in question_bank.boards(g) if b == '逻辑填空'] or question_bank.boards(g)
    qs = [q for b in boards for q in question_bank.read(g.paths, b)[0] if q['key'] in keys and is_fill(q)]
    return {'scanned': len(qs), 'new': harvest(g, qs), 'total': len(data(g))}


def listing(g):
    book = data(g)
    words = sorted(book.values(), key=lambda e: (e['letter'] == '#', e['letter'], e['word']))
    letters = {}
    for e in words:
        letters[e['letter']] = letters.get(e['letter'], 0) + 1
    return {'total': len(words), 'letters': letters, 'entries': words, 'file': FILE}


def _bank_file(src):
    return (src.get('source') or '').rsplit('.md', 1)[0]


def write_file(g):
    if not g.paths.train:
        return
    d = listing(g)
    out = ['# 成语实词录', '',
           '> 逻辑填空每做完一组，正确选项里的成语 / 实词自动收进来，按首字拼音首字母排（程序生成，整份重写；自己的笔记请记在别处）。',
           '> 共 %d 个词条。' % d['total'], '']
    cur = None
    for e in d['entries']:
        if e['letter'] != cur:
            cur = e['letter']
            out += ['## %s' % cur, '']
        out += ['### %s' % e['word'], '']
        for s in e['sources']:
            link = '[[%s#题目 %s|%s]]' % (_bank_file(s), s['id'], s['id']) if _bank_file(s) else s['id']
            out.append('- **释义**：%s' % (s['meaning'] or '（解析里没有单独解释，见辨析）'))
            if s['others']:
                out.append('- **本题其他选项**：' + '；'.join('%s（%s项）%s' % (o['word'], o['option'], '：' + o['meaning'] if o['meaning'] else '')
                                                       for o in s['others']))
            if s['compare']:
                out.append('- **辨析**：' + s['compare'].replace('\n', ' '))
            out.append('- **真题**：%s%s · 第 %d 空 · 正确选项 %s「%s」 · 收于 %s' % (
                link, ('（%s）' % s['paper']) if s['paper'] else '', s['blank'], s['answer'], s['option_text'], s['date']))
            out.append('')
    try:
        (g.paths.train / FILE).write_text('\n'.join(out).rstrip('\n') + '\n', encoding='utf-8', newline='\n')
    except OSError:
        pass
