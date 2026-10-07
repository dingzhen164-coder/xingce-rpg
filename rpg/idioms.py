"""藏经阁·成语实词录：逻辑填空做完一组，就把每道题正确选项里的成语 / 实词收成词条，按首字拼音首字母排。

一个词条（正确选项里的一个词，几个空就几个词条）里有：
- 释义：从解析里摘“X项“词”指 / 形容 / 比喻 / 意为……”那一句；
- 本题其他选项：同一个空其他选项的词，各带解析里的释义；
- 辨析：解析里讲这个空的那一段（“第一空 / 第二空……”，没有分空就是提到这个词的那段）；
- 真题：题库里的编号、试卷，网页上一点就跳到经卷里这道题，Obsidian 里是 [[题库文件#题目 编号]]。
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
    return bool(re.fullmatch(r'[\u4e00-\u9fff]{2,12}', w or '')) and w not in FUNCTION   # 只收汉字词（排序题的③①②、字母数字不收）


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
            single = blanks(q.get('stem')) == 1          # 只有一个空：选项就是一个完整的词（多是成语），也收
            for v in q['options'].values():
                ws = split_words(v)
                if len(ws) > 1 or (single and len(ws) == 1 and 2 <= len(ws[0]) <= 4):
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


def resplit(opts, k, words, scored=False):
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
    best, best_score, second = None, None, None
    for combo in itertools.product(*cands):
        score = sum(own(seg) for seg in combo)
        for i in range(k):
            col = [seg[i] for seg in combo]
            lens = [len(w) for w in col]
            score += 2 * (max(lens.count(n) for n in set(lens)) - 1)
            if all(len(w) == 3 for w in col) and len({w[-1] for w in col}) == 1 and col[0][-1] in SUFFIX:
                score += 4
        if best_score is None or score > best_score:
            second = best_score
            best, best_score = combo, score
        elif second is None or score > second:
            second = score
    out = dict(zip(keys, (list(x) for x in best)))
    return (out, best_score == second) if scored else out


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


def display_options(g, stem, opts):
    """逻辑填空的选项几个词连在一起（粉笔模考 PDF 拆出来空格丢了，如“截然不同歪曲”）：按题干的空数切开，
    用全角空格连回去给网页显示（“截然不同　歪曲”）。切不出、本来就分好了，原样返回"""
    if not opts or any(len(split_words(v)) != 1 for v in opts.values()):
        return opts
    k = blanks(stem)
    longest = max(len(v.strip()) for v in opts.values())
    raw = {x: v.strip() for x, v in opts.items()}
    cache = g.state.setdefault('fill_split', {})          # AI 切过的存下来，下次不再问
    key = '|'.join(raw[x] for x in sorted(raw))
    if key in cache:
        return dict(cache[key])
    for kk in ([k] if k >= 2 else ([2, 3] if longest >= 7 else [])):
        got = resplit(raw, kk, vocab(g), scored=True)
        if not got:
            continue
        split, tie = got
        if tie:                                             # 词典分不出（如 截然不同|歪曲 还是 截然|不同歪曲）：问一次 AI
            split = _ai_split(raw, kk) or split
        out = {x: "　".join(ws) for x, ws in split.items()}
        if tie and split is not got[0]:
            cache[key] = out
        return out
    return opts


def _ai_split(raw, k):
    """让 AI 把连在一起的选项切成 k 个词；切完拼回去必须和原文一模一样，不然不用"""
    from . import ai
    if not ai.available():
        return None
    msg = [{"role": "system", "content": "你是行测逻辑填空的助手，只输出 JSON。"},
           {"role": "user", "content": "下面是一道有 %d 个空的逻辑填空题的四个选项，每个选项是 %d 个词连在一起写的（空格丢了）。"
            "按词切开，返回 JSON：{\"A\": [\"词1\", \"词2\"], ...}，每个选项正好 %d 个词，不改任何字。\n%s" % (
                k, k, k, "\n".join("%s. %s" % kv for kv in sorted(raw.items())))}]
    try:
        got = ai.chat_json(msg, temperature=0)
    except Exception:
        return None
    if not isinstance(got, dict) or set(got) != set(raw):
        return None
    out = {}
    for x, ws in got.items():
        if not isinstance(ws, list) or len(ws) != k or "".join(map(str, ws)) != raw[x]:
            return None
        out[x] = [str(w) for w in ws]
    return out


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
            if w in deleted(g):
                continue
            e = book.get(w)
            if not e:
                e = book[w] = {'word': w, 'letter': letter(w), 'added': g.t, 'sources': []}
                new.append(w)
            old = next((s for s in e['sources'] if s['key'] == src['key'] and s['blank'] == src['blank']), None)
            src['date'] = old['date'] if old else g.t
            if old:
                _keep_mine(old, src)
                e['sources'][e['sources'].index(old)] = src     # 题库解析更新过：用新的
            else:
                e['sources'].append(src)
    if questions:
        write_file(g)
    return new


VERSION = 3   # 2：粉笔模考选项连在一起时按空数切词；3：只收汉字词


TAG = '（师傅补）'


def clean_tags(g):
    """去掉旧版师傅补的释义前面的“（师傅补）”。有改动返回 True"""
    changed = False
    for e in data(g).values():
        for s in e['sources']:
            for x in [s] + s.get('others', []):
                m = x.get('meaning') or ''
                if m.startswith(TAG):
                    x['meaning'] = m[len(TAG):]
                    changed = True
    return changed


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
        kept = {w: e for w, e in book.items() if any(s.get('edited') or s.get('tutor') for s in e['sources'])}
        book.clear()
        harvest(g, qs)
        for w, e in kept.items():          # 改过的、师傅答过的词条原样留着
            if is_word(w) or any(s.get('edited') for s in e['sources']):
                book[w] = e
        for e in book.values():
            for s in e['sources']:
                s['date'] = dates.get(s['key'], s['date'])
            e['added'] = min(s['date'] for s in e['sources'])
        write_file(g)
    g.state['idioms_ver'] = VERSION
    return True


def _keep_mine(old, src):
    """同一题再收一次（题库解析更新过）：自己改过的、师傅答过的、师傅补的释义留着"""
    if old.get('edited'):
        src.update(meaning=old.get('meaning', ''), compare=old.get('compare', ''), edited=True)
    elif old.get('tutor'):
        src.update(compare=old.get('compare', ''), tutor=True)
        if not src['meaning'] and old.get('meaning'):
            src['meaning'] = old['meaning']
    for o in src['others']:
        om = next((x for x in old.get('others', []) if x['word'] == o['word']), None)
        if om and om.get('meaning') and not o['meaning']:
            o['meaning'] = om['meaning']


def deleted(g):
    return g.state.setdefault('idioms_deleted', [])


def _entry(g, word):
    e = data(g).get(word)
    if not e:
        raise ValueError('找不到词条「%s」' % word)
    return e


def edit(g, word, body):
    """修改词条：词本身（改名，和已有的同名词条合并）、每条出处的释义和辨析"""
    e = _entry(g, word)
    for i, s in enumerate(e['sources']):
        mine = (body.get('sources') or {}).get(str(i)) or {}
        for k in ('meaning', 'compare'):
            if k in mine:
                s[k] = str(mine[k] or '').strip()[:900]
                s['edited'] = True
    new = str(body.get('word') or word).strip()
    if new and new != word:
        if len(new) > 12:
            raise ValueError('词条名太长')
        book = data(g)
        book.pop(word)
        if new in book:
            book[new]['sources'] += e['sources']
        else:
            e.update(word=new, letter=letter(new))
            book[new] = e
        if word not in deleted(g):
            deleted(g).append(word)        # 以后收录不再按旧名字收回来
        if new in deleted(g):
            deleted(g).remove(new)
        links = g.state.setdefault('idiom_cards', {})
        if word in links and new not in links:
            links[new] = links.pop(word)
        elif word in links:
            from . import cards
            cards.delete(g, [links.pop(word)])
    write_file(g)
    sync_card(g, new or word)
    return data(g)[new or word]


def delete(g, word):
    _entry(g, word)
    data(g).pop(word)
    if word not in deleted(g):
        deleted(g).append(word)
    write_file(g)
    sync_card(g, word)


def ask_tutor(g, word):
    """师傅答疑：每条出处让 AI 写一句话辨析，替换原来的辨析；解析没给的释义顺手补上"""
    from . import ai, prompts
    e = _entry(g, word)
    for s in e['sources']:
        r = ai.chat_json(prompts.idiom_compare(g.persona, word, s), temperature=0.4, max_tokens=600)
        text = str(r.get('辨析') or '').strip()
        if text:
            s['compare'] = text
            s['tutor'] = True
        means = r.get('释义') or {}
        if isinstance(means, dict):
            if not s.get('meaning') and means.get(word):
                s['meaning'] = str(means[word]).strip()[:60]
            for o in s.get('others', []):
                if not o.get('meaning') and means.get(o['word']):
                    o['meaning'] = str(means[o['word']]).strip()[:60]
    if len(word) >= 4:                    # 成语：再讲关键字和出处
        try:
            d = ai.chat_json(prompts.idiom_detail(g.persona, word, next((s.get('meaning') for s in e['sources'] if s.get('meaning')), '')),
                             temperature=0.3, max_tokens=700)
        except Exception:
            d = {}
        chars = [{'char': str(c.get('字') or '')[:2], 'meaning': str(c.get('义') or '')[:40],
                  'like': [str(x)[:12] for x in (c.get('同用法') or [])][:4]}
                 for c in (d.get('逐字') or []) if isinstance(c, dict) and c.get('字')][:3]
        src = d.get('出处') if isinstance(d.get('出处'), dict) else {}
        origin = {'from': str(src.get('出自') or '')[:60], 'text': str(src.get('原文') or '')[:160], 'note': str(src.get('说明') or '')[:200]}
        if chars or any(origin.values()):
            e['detail'] = {'chars': chars, 'origin': origin}
    write_file(g)
    sync_card(g, word)
    return e


# ---------------------------------------------------------------- 背成语：师傅答疑过的词条 → 玉简
CARD_DECK = '逻辑填空::成语实词录'


def card_fields(e):
    """一个词条 → 一枚玉简：正面是词，反面是释义、逐字、出处、辨析、本题其他选项（不放真题）"""
    w = e['word']
    det = e.get('detail') or {}
    back = []
    means = list(dict.fromkeys(s['meaning'] for s in e['sources'] if s.get('meaning')))
    if means:
        back.append('**释义**：' + '；'.join(means))
    for c in det.get('chars') or []:
        back.append('**逐字**：%s = %s%s' % (c['char'], c['meaning'], '（同样用法：%s）' % '、'.join(c['like']) if c.get('like') else ''))
    o = det.get('origin') or {}
    if any(o.values()):
        back.append('**出处**：%s%s%s' % (o.get('from') or '', ('“%s”' % o['text']) if o.get('text') else '', ('。' + o['note']) if o.get('note') else ''))
    for s in e['sources']:
        if s.get('compare'):
            back.append('**辨析**：' + s['compare'].replace('\n', ' '))
        if s.get('others'):
            back.append('**本题其他选项**：\n' + '\n'.join('- %s%s' % (x['word'], '：' + x['meaning'] if x.get('meaning') else '') for x in s['others']))
    kind = '成语' if len(w) >= 4 else '实词'
    return {'deck': CARD_DECK, 'type': '问答', 'tags': ['成语实词录', kind],
            'front': '**%s**\n\n（%s · 说出意思和用法）' % (w, kind), 'back': '\n\n'.join(back) or '（见成语实词录）',
            'extra': '由藏经阁「成语实词录」生成：在那里点「师傅答疑」或改词条会同步更新这张卡'}


def sync_card(g, word):
    """师傅答疑过的词条同步成玉简（没答疑过的不收）；词条没了就删掉对应的玉简"""
    from . import cards
    links = g.state.setdefault('idiom_cards', {})
    e = data(g).get(word)
    if not e or not any(s.get('tutor') for s in e['sources']):
        if word in links and not e:
            cards.delete(g, [links.pop(word)])
        return None
    try:
        links[word] = cards.upsert(g, links.get(word), card_fields(e))
    except Exception:
        return None
    return links[word]


def sync_cards(g):
    """把已经答疑过的词条一次补成玉简（升级后第一次打开修炼殿时做一次）"""
    n = 0
    for w, e in list(data(g).items()):
        if any(s.get('tutor') for s in e['sources']) and w not in g.state.get('idiom_cards', {}):
            n += bool(sync_card(g, w))
    return n


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
        det = e.get('detail') or {}
        for c in det.get('chars') or []:
            out.append('- **逐字**：%s = %s%s' % (c['char'], c['meaning'], '（同样用法：%s）' % '、'.join(c['like']) if c.get('like') else ''))
        o = det.get('origin') or {}
        if any(o.values()):
            out.append('- **出处**：%s%s%s' % (o.get('from') or '', ('“%s”' % o['text']) if o.get('text') else '', ('。' + o['note']) if o.get('note') else ''))
        if det:
            out.append('')
        for s in e['sources']:
            link = '[[%s#题目 %s|%s]]' % (_bank_file(s), s['id'], s['id']) if _bank_file(s) else s['id']
            out.append('- **释义**：%s' % (s['meaning'] or '（解析里没有单独解释，见辨析）'))
            if s['others']:
                out.append('- **本题其他选项**：' + '；'.join('%s（%s项）%s' % (o['word'], o['option'], '：' + o['meaning'] if o['meaning'] else '')
                                                       for o in s['others']))
            if s['compare']:
                out.append('- **%s**：' % ('辨析（🧙 师傅）' if s.get('tutor') and not s.get('edited') else '辨析') + s['compare'].replace('\n', ' '))
            out.append('- **真题**：%s%s · 第 %d 空 · 正确选项 %s「%s」 · 收于 %s' % (
                link, ('（%s）' % s['paper']) if s['paper'] else '', s['blank'], s['answer'], s['option_text'], s['date']))
            out.append('')
    try:
        (g.paths.train / FILE).write_text('\n'.join(out).rstrip('\n') + '\n', encoding='utf-8', newline='\n')
    except OSError:
        pass
