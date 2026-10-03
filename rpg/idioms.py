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


# ---------------------------------------------------------------- 选项里几个词连在一起（粉笔模考 PDF 导入时空格丢了）
# “克服渐进性纠正”要切成 克服 / 渐进性 / 纠正：没有词典库，就用题库自己当词典——历年逻辑填空里用空格分好的选项词、
# 解析里打了引号的词；再看四个选项同一个空的词长是不是一致、结尾是不是同一个字（渐进性 / 持续性 / 阶段性）。
_VOCAB = {'sig': None, 'words': set()}


def vocab(g):
    files = question_bank.files(g.paths, '逻辑填空') if g.paths.train else []
    sig = tuple((str(f), f.stat().st_mtime_ns) for f in files)
    if _VOCAB['sig'] != sig:
        words = set()
        for q in question_bank.read_all(g.paths, '逻辑填空')[0]:
            for v in q['options'].values():
                ws = split_words(v)
                if len(ws) > 1:
                    words.update(w for w in ws if 2 <= len(w) <= 6)
            words.update(w for w in re.findall(r'“([\u4e00-\u9fff]{2,6})”', q.get('analysis') or ''))
        _VOCAB.update(sig=sig, words=words)
    return _VOCAB['words']


def _cuts(text, k):
    """把 text 切成 k 段、每段 2–4 个字的所有切法"""
    if k == 1:
        return [[text]] if 2 <= len(text) <= 4 else []
    out = []
    for n in (2, 3, 4):
        if len(text) - n >= 2 * (k - 1):
            out += [[text[:n]] + rest for rest in _cuts(text[n:], k - 1)]
    return out


def resplit(opts, k, words):
    """四个选项都没分词时一起切：词典里有的词加分，同一个空四个选项词长一致、结尾同字加分，三字词略减分。
    切不出（字数对不上）返回 None"""
    import itertools
    keys = sorted(opts)
    cands = [_cuts(opts[x], k) for x in keys]
    if not all(cands) or len(keys) < 2:
        return None
    def one(w):
        if w in words:
            return 3
        if len(w) == 3:
            return 1 if w[-1] in SUFFIX else -2
        if len(w) == 4 and (w[:2] in words or w[2:] in words):   # 没见过的四字块，一半是认识的双字词：多半是两个词拼的
            return -2
        return 0

    def own(seg):
        return sum(one(w) for w in seg)
    # 每个选项先按自己的分数留前几种切法，再一起比对齐
    cands = [sorted(c, key=own, reverse=True)[:6] for c in cands]
    best, best_score = None, None
    for combo in itertools.product(*cands):
        score = sum(own(seg) for seg in combo)
        for i in range(k):
            col = [seg[i] for seg in combo]
            lens = [len(w) for w in col]
            score += 2 * (max(lens.count(n) for n in set(lens)) - 1)
            if all(len(w) == 3 for w in col) and len({w[-1] for w in col}) == 1 and col[0][-1] in SUFFIX:
                score += 4
        if best_score is None or score > best_score:
            best, best_score = combo, score
    return dict(zip(keys, (list(x) for x in best)))


SUFFIX = set('性化感度力型式者家学观论率量制界级态')   # 三字词常见的后缀：渐进性、现代化、获得感……


def blanks(stem):
    return len(re.findall(r'_{2,}|＿{2,}|（\s*）|\(\s*\)', stem or ''))


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


def entries_of(q, words=None):
    """一道逻辑填空题 → [(词, 词条出处)]。words：分词用的词典（见 vocab）"""
    ans = (q.get('answer') or '').strip().upper()
    opts = q.get('options') or {}
    if ans not in opts:
        return []
    split = {k: split_words(v) for k, v in opts.items()}
    if all(len(v) == 1 for v in split.values()):     # 选项没分词：按题干里的空数切（没有横线时，长到不像一个词才切）
        k = blanks(q.get('stem'))
        longest = max(len(v[0]) for v in split.values())
        tries = [k] if k >= 2 else ([2, 3] if longest >= 7 else [])
        for kk in tries:
            got = resplit({x: v[0] for x, v in split.items()}, kk, words or set())
            if got:
                split = got
                break
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
    if g.state.get('idioms_ver') != VERSION and data(g):
        migrate(g)
    g.state['idioms_ver'] = VERSION
    book = data(g)
    new = []
    words = None
    for q in questions:
        if not is_fill(q):
            continue
        if words is None:
            words = vocab(g)
        for w, src in entries_of(q, words):
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


VERSION = 2   # 2：粉笔模考选项连在一起时按空数切词


def migrate(g):
    """旧版收的词条（选项连在一起时整串当一个词）按新规则重收一遍；收录日期保留"""
    if g.state.get('idioms_ver') == VERSION:
        return False
    book = data(g)
    if book:
        dates = {}
        for e in book.values():
            for s in e['sources']:
                dates[s['key']] = min(dates.get(s['key'], s['date']), s['date'])
        qs = []
        for b in {s['board'] for e in book.values() for s in e['sources']}:
            qs += [q for q in question_bank.read_all(g.paths, b)[0] if q['key'] in dates]
        book.clear()
        harvest(g, qs)
        for e in book.values():
            for s in e['sources']:
                s['date'] = dates.get(s['key'], s['date'])
            e['added'] = min(s['date'] for s in e['sources'])
        write_file(g)
    g.state['idioms_ver'] = VERSION
    return True


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
