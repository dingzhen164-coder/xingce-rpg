"""历年真题库转换：把“考公脑库”（github.com/ERRRC/kaogongzhentizhengliu）里 10-真题/判断推理 的逐题笔记
转成试炼塔题库格式，写成 训练/题库/<板块>真题-历年.md（每个板块一份，和自己导入的 <板块>真题.md 分开，互不覆盖）。

- 编号 真题-<qid>，和原仓库题号一一对应；原仓库更新后重新转换，已做过的题记录不受影响。
- ### 试卷 写原卷名，试炼塔「整套试炼」按卷子成套（一张卷子的判断推理部分为一套）。
- 题干前用括号写简短来源；有“给定材料”的接在题干前面。
- 解析 = 官方解析 + 问法模型 + 推理链 + 最快解法 + 易错点 + 母题抽象（作答后才显示）。
- 逻辑判断按“考点”分论证逻辑 / 形式逻辑（平行结构、日常结论归形式逻辑）；科学推理归常识判断。
- 图片不复制进转换结果：写一份 图片清单.txt，在 Windows 上用 PowerShell 从原仓库的 90-图片 按清单拷到
  训练/题库/图片/真题库/，题目里写 ![[训练/题库/图片/真题库/题目图/xxx.png]]。

用法：python -m rpg.zhenti <原仓库目录> <输出目录>   （输出目录里生成 题库/…）
"""
import html
import os
import re
import sys
from collections import Counter
from pathlib import Path

IMG_DIR = '训练/题库/图片/真题库'
BOARD_OF_DIR = {'图形推理': '图形推理', '定义判断': '定义判断', '类比推理': '类比推理', '科学推理': '常识判断'}
ORDER = {'图形推理': 0, '定义判断': 1, '类比推理': 2, '形式逻辑': 3, '论证逻辑': 3, '常识判断': 4}
FORMAL = re.compile(r'平行|翻译|真假|分析推理|排序|直言|三段论|日常|归纳|组合|集合|模态|关系推理|综合推理|推出|对应|匹配|'
                    r'条件|充分|必要|命题|演绎|数量|位置|代入|排列|结论|推理题|矛盾|逻辑推理|概念|数学|周期|排队|对话|语义|规则|定义')
ARGUE = re.compile(r'削弱|加强|强化|支持|质疑|反驳|前提|假设|解释|评价|论证|原因|缺陷|漏洞|争论|焦点|结构|方法|'
                   r'调查|实验|因果|论据|观点|建议|对策|逻辑错误')


def logic_board(point):
    """逻辑判断的考点 → 论证逻辑 / 形式逻辑；平行结构先判（它名字里也有“结构”）"""
    if '平行' in point:
        return '形式逻辑'
    # 先看大类名（“-”或括号前），细节描述里常有“假设法”“支持”之类的字，不能拿来判
    for part in (re.split(r'[-（(]', point)[0], point):
        if ARGUE.search(part):
            return '论证逻辑'
        if FORMAL.search(part):
            return '形式逻辑'
    return ''


def to_text(s, base, images):
    """原笔记里的 HTML 片段 → 纯文字；<img> 换成 Obsidian 图片链接，并记下要拷的图"""
    def img(m):
        rel = os.path.normpath(os.path.join(base, m.group(1))).replace('\\', '/')
        rel = rel.split('90-图片/', 1)[-1]
        images.add(rel)
        if rel.startswith('公式图/'):   # 公式图夹在句子里，留在原位
            return '![[%s/%s]]' % (IMG_DIR, rel)
        return '\n![[%s/%s]]\n' % (IMG_DIR, rel)
    s = re.sub(r'<img\b[^>]*?src="([^"]+)"[^>]*>', img, s)
    s = re.sub(r'!\[[^\]]*\]\(([^)]+)\)', img, s)
    s = re.sub(r'<br\s*/?>|</p>|</div>', '\n', s)
    s = re.sub(r'<[^>]+>', '', s)
    s = html.unescape(s).replace(' ', ' ')
    lines = [ln.strip() for ln in s.splitlines()]
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip()


def short_source(paper):
    """2021年江苏省公务员录用考试《行测》题（B类）（网友回忆版） → 2021年江苏省（B类）"""
    head, _, tail = paper.partition('《')
    head = re.sub(r'\s*(?:行政职业能力测验|行测|综合知识).*$', '', head)
    head = re.sub(r'(?:公务员|人员)?(?:录用|招录|招考)?(?:公务员)?考试$', '', head) or head
    extra = ''.join(x[1:-1] for x in re.findall(r'（[^）]*）', tail.partition('》')[2])
                    if not re.search(r'回忆|精选|完整|真题', x))
    return head + extra


def section(t, name, level='###'):
    m = re.search(r'^%s %s\s*\n(.*?)(?=^#{2,3} |\Z)' % (level, re.escape(name)), t, re.M | re.S)
    if not m:
        return ''
    # 笔记部分的小节后面常跟着 **最快解法**：… **同类特征**：… 这样的加粗段，不属于这一节
    return re.split(r'\n\s*\*\*', m.group(1))[0].strip() if level == '##' else m.group(1).strip()


def parse(path):
    t = path.read_text(encoding='utf-8')
    meta = dict(re.findall(r'^(\w+): "(.*)"$', t.split('\n---', 1)[0], re.M))
    note, _, qpart = t.partition('\n---\n\n### 题干')
    if not qpart:                      # 版式略有不同（没有分隔线）也能读
        note, _, qpart = t.partition('### 题干')
    qpart = '### 题干' + qpart
    base = str(path.parent)
    images = set()
    opts, answer = {}, ''
    for ln in section(qpart, '选项').splitlines():
        m = re.match(r'^-?\s*([A-D])[.．、]\s*(.*)$', ln.strip())
        if m:
            v = m.group(2)
            if '✅' in v:
                answer = m.group(1)
            opts[m.group(1)] = to_text(v.replace('✅', ''), base, images).replace('\n', ' ').strip()
    stem = to_text(section(qpart, '题干'), base, images)
    material = section(qpart, '给定材料')
    # 给定材料后面常跟着一段 > [!warning] 疑点（官方解析可能有误…）：那是对解析的复核意见，放进解析，不当材料
    doubt = '\n'.join(re.sub(r'^>\s?', '', ln) for ln in material.splitlines() if ln.startswith('>'))
    doubt = re.sub(r'^\[!\w+\]\s*', '', doubt).strip()
    material = '\n'.join(ln for ln in material.splitlines() if not ln.startswith('>')).strip()
    if material and material != '（无）':
        stem = to_text(material, base, images) + '\n\n' + stem
    parts = [('官方解析', to_text(section(qpart, '官方解析'), base, images))]
    m = re.search(r'\*\*问法模型\*\*[:：]\s*(.+)', note)
    parts.append(('问法模型', m.group(1).strip() if m else ''))
    parts.append(('推理链', re.sub(r'^\d+\.\s*', '', section(note, '推理链', '##'), flags=re.M)))
    m = re.search(r'\*\*最快解法\*\*[:：]\s*(.+)', note)
    parts.append(('最快解法', m.group(1).strip() if m else ''))
    parts.append(('易错点', section(note, '易错点', '##')))
    parts.append(('母题抽象', re.sub(r'^>\s*', '', section(note, '母题抽象', '##'), flags=re.M).strip()))
    parts.append(('疑点', doubt))
    analysis = '\n\n'.join('【%s】\n%s' % (k, to_text(v, base, images) if k != '官方解析' else v) for k, v in parts if v)
    extra = '\n\n'.join('【%s】\n%s' % (k, to_text(v, base, images)) for k, v in parts[1:] if v)   # 只有蒸馏出来的部分
    point = meta.get('考点', '')
    kind = path.parent.name
    board = logic_board(point.split(' / ', 1)[-1]) if kind == '逻辑判断' else BOARD_OF_DIR.get(kind, '')
    return {'qid': meta.get('qid', ''), 'paper': meta.get('试卷', ''), 'year': meta.get('年份', ''),
            'board': board, 'kind': kind, 'point': point, 'topic': point.split(' / ', 1)[-1] or kind,
            'stem': stem, 'options': opts, 'answer': answer, 'analysis': analysis, 'extra': extra, 'images': images}


def block(q):
    # 小节标题行（### / ## 开头）会打乱题库格式，正文里出现就降成普通文字
    clean = lambda s: re.sub(r'^(#+)\s', lambda m: '＃' * len(m.group(1)) + ' ', s, flags=re.M)
    src = short_source(q['paper'])
    if src and q.get('also'):
        src += '等%d卷' % (len(q['also']) + 1)
    return ('## 题目 真题-%s\n### 知识点\n%s\n### 试卷\n%s\n### 模块\n%s\n%s### 题干\n%s%s\n### 选项\n%s\n### 答案\n%s\n### 解析\n%s\n\n'
            % (q['qid'], q['topic'], '\n'.join([q['paper']] + [p for p, _ in q.get('also', [])]), q.get('module', '判断推理'),
               '### 题号\n%s\n' % ' '.join(str(n) for n in [q['num']] + [n for _, n in q.get('also', [])]) if q.get('num') else '', '（%s）' % src if src else '', clean(q['stem']),
               '\n'.join('%s. %s' % (k, q['options'][k]) for k in 'ABCD'), q['answer'] or '（待补）', clean(q['analysis'])))


def convert(src, out):
    src, out = Path(src), Path(out)
    root = src / '10-真题' / '判断推理'
    qs, bad, unknown = [], [], Counter()
    for f in sorted(root.glob('*/*.md')):
        q = parse(f)
        if set(q['options']) != set('ABCD') or not all(q['options'].values()) or not q['stem']:
            bad.append(f.name)
            continue
        if not q['board']:
            unknown[q['point']] += 1
            q['board'] = '论证逻辑' if re.search(r'论证|支持|削弱|加强|前提|解释', q['stem'][-60:]) else '形式逻辑'
        qs.append(q)
    qs.sort(key=lambda q: (-int(q['year'] or 0), q['paper'], ORDER.get(q['board'], 9), int(q['qid'] or 0)))
    folder = out / '题库'
    folder.mkdir(parents=True, exist_ok=True)
    by = Counter()
    for board in sorted({q['board'] for q in qs}):
        mine = [q for q in qs if q['board'] == board]
        by[board] = len(mine)
        head = ('# %s · 历年真题\n\n> 由 rpg/zhenti.py 从考公脑库（ERRRC/kaogongzhentizhengliu）转换，共 %d 题。'
                '重新转换会整份覆盖，自己的笔记别写在这里。\n\n' % (board, len(mine)))
        (folder / ('%s真题-历年.md' % board)).write_text(head + ''.join(block(q) for q in mine), encoding='utf-8', newline='\n')
    images = sorted({i for q in qs for i in q['images']})
    img_list = folder / '图片' / '真题库' / '图片清单.txt'
    img_list.parent.mkdir(parents=True, exist_ok=True)
    img_list.write_text('\r\n'.join(i.replace('/', '\\') for i in images) + '\r\n', encoding='utf-8-sig', newline='')
    return {'total': len(qs), 'boards': dict(by), 'bad': bad, 'unknown': dict(unknown), 'images': len(images),
            'pending': sum(not q['answer'] for q in qs), 'papers': len({q['paper'] for q in qs})}


# ---------------------------------------------------------------- 给已入库的题补上蒸馏解析
# 蒸馏部分从第一行“整行就是【蒸馏小节名】”开始；官方解析里也可能有【备注】这类整行标题，所以只认蒸馏用过的名字
DISTILLED_NAMES = {'细化', '问法模型', '推理链', '最快解法', '易错点', '母题抽象', '疑点', '易混考点辨析', '适用边界（什么时候不要用）'}


def _distilled_start(body, extra):
    names = DISTILLED_NAMES | set(re.findall(r'^【([^】\n]+)】$', extra, re.M))
    for m in re.finditer(r'^【([^】\n]{1,24})】[ \t]*$', body, re.M):
        if m.group(1) in names:
            return m.start()
    return None
_COARSE = {'逻辑填空', '片段阅读', '语句表达', '数学运算', '人文常识', '科技常识', '法律常识', '地理国情', '经济常识',
           '新思想', '时事政治', '马克思主义', '毛中特', '待分类'}


_SKIP_SEC = re.compile(r'相关|同类|链接|题干|选项|官方解析|给定材料|^答案|正确答案|参考答案|材料|考点$|出处|来源|标签|tags|典型提问', re.I)


def _callout_sections(t):
    """言语那批把蒸馏内容放在 “> [!success]- 点击查看答案与解析” 折叠框里：
    **标签**：内容（一行）、单独一行的 **标签** 下面跟几行内容、开头的“细化：…”都认。返回 [(位置, 名称, 内容)]"""
    lines = t.splitlines()
    start = next((i for i, ln in enumerate(lines) if re.match(r'^>\s*\[!\w+\][-+]?.*解析', ln)), None)
    if start is None:
        return []
    box = []
    for ln in lines[start + 1:]:
        if not ln.startswith('>'):
            break
        box.append(re.sub(r'^>\s?', '', ln))
    out, cur = [], None
    for i, ln in enumerate(box):
        inline = re.match(r'^\*\*([^*]{1,20}?)\*\*\s*[:：]\s*(.+)$', ln)
        head = re.match(r'^\*\*([^*]{1,30}?)\*\*\s*$', ln)
        plain = re.match(r'^([\u4e00-\u9fff]{2,4})\s*[:：]\s*(.+)$', ln) if cur is None else None
        if inline or plain:
            m = inline or plain
            out.append([100000 + i, m.group(1).strip(), m.group(2)])
            cur = None
        elif head and re.search(r'[:：]', head.group(1)):   # **正确答案：C** 这种自成一条，不是小节标题
            out.append([100000 + i, head.group(1).strip(), ''])
            cur = None
        elif head:
            cur = [100000 + i, head.group(1).strip(), '']
            out.append(cur)
        elif cur is not None:
            cur[2] += ln + '\n'
    return [tuple(x) for x in out]


def parse_note(path):
    """宽松地读一篇蒸馏笔记：qid 可带引号也可不带，也可只写在文件名开头；
    “## 小节” 和 “**标签**：内容” 两种写法都认，按出现顺序收集（相关题、同类特征、题干选项这些不要）。
    返回 {qid, topic, extra, images}；读不出 qid 时 qid 为空"""
    t = path.read_text(encoding='utf-8', errors='ignore')
    fm, body = '', t
    if t.startswith('---'):
        fm, _, body = t[3:].partition('\n---')
    meta = {k.strip(): v.strip().strip('"\'') for k, v in re.findall(r'^([^\s:：#]+)\s*[:：]\s*(.*)$', fm, re.M)}
    qid = meta.get('qid', '') or meta.get('id', '')
    if not qid.isdigit():
        m = re.match(r'(\d{3,})', path.name)
        qid = m.group(1) if m else ''
    unlink = lambda x: re.sub(r'\[\[(?:[^\]|]*\|)?([^\]]*)\]\]', r'\1', x)
    point = unlink(meta.get('考点', ''))
    note = re.split(r'^#{2,3}\s*题干', body, 1, flags=re.M)[0]
    base, images, found = str(path.parent), set(), []
    for m in re.finditer(r'^\*\*([^*\n]{1,12})\*\*\s*[:：]\s*(.+)$', note, re.M):
        found.append((m.start(), m.group(1).strip(), m.group(2)))
    for m in re.finditer(r'^#{2,3}\s+(.+?)\s*\n(.*?)(?=^#{1,3}\s|\Z)', note, re.M | re.S):
        found.append((m.start(), m.group(1).strip(), re.split(r'\n\s*\*\*[^*\n]{1,12}\*\*\s*[:：]', m.group(2))[0]))
    found += _callout_sections(t)
    if not point:
        m = re.search(r'^考点\s*[:：]\s*(.+)$', note, re.M)
        point = unlink(m.group(1)) if m else ''
    doubt, lines = [], t.splitlines()     # > [!warning] 疑点… 这段复核意见（连续的 > 行）
    for i, ln in enumerate(lines):
        if '[!warning]' in ln:
            for x in lines[i:]:
                if not x.startswith('>'):
                    break
                doubt.append(re.sub(r'^>\s?', '', x))
            break
    doubt = '\n'.join(doubt)
    parts = []
    for _, name, text in sorted(found):
        name = re.sub(r'^[\d.、\s]+|[：:]$', '', name)
        if _SKIP_SEC.search(name):
            continue
        text = '\n'.join(re.sub(r'^\s*(?:>\s*)?(?:\d+\.\s+)?', '', ln) for ln in unlink(text).strip().splitlines()).strip()
        if text:
            parts.append((name, to_text(text, base, images)))
    if doubt:
        parts.append(('疑点', re.sub(r'^\[!\w+\]\s*', '', doubt.strip())))
    return {'qid': qid, 'topic': point.split(' / ', 1)[-1].strip(), 'images': images,
            'extra': '\n\n'.join('【%s】\n%s' % (k, v) for k, v in parts)}


def merge_distilled(train, folder, dry=False):
    """读“考公脑库”式的蒸馏笔记（每题一篇，frontmatter 里有 qid），按编号 真题-<qid> 找到题库里已有的题：
    解析里官方解析保留，后面补上 问法模型 / 推理链 / 最快解法 / 易错点 / 母题抽象 / 疑点（再合并一次会换成新的，不重复）；
    知识点原来只是“逻辑填空”这种大类的，换成蒸馏的细考点。用到的图从蒸馏仓库的 90-图片 拷到 题库/图片/真题库/。"""
    import shutil
    train, folder = Path(train), Path(folder)
    if not folder.is_dir():
        raise ValueError('找不到文件夹：%s' % folder)
    notes, bad, scanned, no_qid, no_parts = {}, 0, 0, [], []
    for f in folder.rglob('*.md'):
        scanned += 1
        try:
            q = parse_note(f)
        except Exception:
            bad += 1
            continue
        if not q['qid']:
            no_qid.append(f.name)
        elif not q['extra']:
            no_parts.append(f.name)
        else:
            notes[q['qid']] = q
    if not notes:
        raise ValueError('在 %d 个 .md 里没读出蒸馏笔记（%d 个没有题号 qid，%d 个没有推理链/易错点这类小节%s）。'
                         '选蒸馏仓库的根目录（vault-…）或“10-真题”文件夹；还不行就把其中一个 .md 发给我看格式'
                         % (scanned, len(no_qid), len(no_parts), '，例：' + (no_parts or no_qid)[0] if no_parts or no_qid else ''))
    root = next((d for d in [folder, *folder.parents] if (d / '90-图片').is_dir()), None)
    bank = train / '题库'
    hit, topics, files, images, missing = set(), 0, [], set(), set()
    for f in sorted(bank.glob('*真题*.md')):
        text = f.read_text(encoding='utf-8')
        heads = list(re.finditer(r'^## 题目 真题-(\d+)\s*$', text, re.M))
        if not heads:
            continue
        out, pos, changed = [], 0, False
        for i, h in enumerate(heads):
            q = notes.get(h.group(1))
            end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
            if not q:
                continue
            block = text[h.start():end]
            m = re.search(r'^### 解析[ \t]*\n(.*?)(?=^### |\Z)', block, re.M | re.S)
            if not m:
                continue
            body = m.group(1).rstrip('\n')
            k = body.find('【师傅解惑】')       # 请师傅讲过的留着，接在蒸馏解析后面
            tutor = body[k:].strip() if k >= 0 else ''
            body = body[:k].rstrip() if k >= 0 else body
            d = _distilled_start(body, q['extra'])
            official = (body[:d] if d is not None else body).rstrip()
            extra = re.sub(r'^(#+)\s', lambda x: '＃' * len(x.group(1)) + ' ', q['extra'], flags=re.M)
            new_body = (official + '\n\n' if official else '') + extra + ('\n\n' + tutor if tutor else '')
            nb = block[:m.start(1)] + new_body + '\n\n' + block[m.end(1):].lstrip('\n')
            t = re.search(r'^### 知识点[ \t]*\n(.*?)\n', nb, re.M)
            if t and q['topic'] and (t.group(1).strip() in _COARSE or not t.group(1).strip()) and q['topic'] != t.group(1).strip():
                nb = nb[:t.start(1)] + q['topic'] + nb[t.end(1):]
                topics += 1
            hit.add(h.group(1))
            images |= q['images']
            if nb != block:
                out.append(text[pos:h.start()] + nb)
                pos = end
                changed = True
        if changed:
            files.append(f.name)
            if not dry:
                f.write_text(''.join(out) + text[pos:], encoding='utf-8', newline='\n')
    copied = 0
    for rel in sorted(images):
        dst = bank / '图片' / '真题库' / rel
        if dst.is_file():
            continue
        src = root / '90-图片' / rel if root else None
        if src and src.is_file():
            copied += 1
            if not dry:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)
        else:
            missing.add(rel)
    return {'scanned': scanned, 'skipped_no_qid': len(no_qid), 'skipped_no_parts': len(no_parts),
            'skip_example': (no_parts or no_qid or [''])[0], 'not_in_bank_example': sorted(set(notes) - hit)[:5],
            'notes': len(notes), 'merged': len(hit), 'not_in_bank': len(set(notes) - hit), 'topics': topics,
            'files': files, 'images_copied': copied, 'images_missing': len(missing), 'unreadable': bad, 'dry': dry}


# ---------------------------------------------------------------- 原题副本（ERRRC/xingcezhenti）
# 每张卷子每个模块一个文件，题目按考试顺序：## 第 N 题　<sub>qid X · 题型</sub>；有材料的是 ## 材料 N 下面挂 ### 第 N 题。
RAW_MODULES = {'01-政治理论': '政治理论', '02-常识判断': '常识判断', '03-言语理解与表达': '言语理解与表达', '04-数量关系': '数量关系'}
RAW_BOARD = {'政治理论': '政治理论', '常识判断': '常识判断', '数量关系': '数量关系', '资料分析': '资料分析'}
VERBAL_BOARD = {'逻辑填空': '逻辑填空', '片段阅读': '片段阅读', '语句表达': '片段阅读'}
BLANK = re.compile(r'(?<=\S)[ \u3000\u00a0]{3,}(?=\S)')   # 句子中间一串空格 = 原卷的填空横线
# 材料管几道题：原题副本里材料下面的题和后面独立的题都是 ### 第 N 题，没有分界。
# 统计全部 173 个材料：相邻两段材料之间最多 5 道题，所以一段材料最多管 5 道；
# 不到 5 道就结束的，靠“自带一大段题干、又不提材料”认出后面的独立题（第 1 道总归是材料题）。
MATERIAL_MAX = 5
MATERIAL_REF = re.compile(r'材料|文中|上文|文段|本文|该文|画线|划线|横线|根据')


def _own_passage(stem):
    plain = re.sub(r'<[^>]+>|!\[\[[^\]]*\]\]|!\[[^\]]*\]\([^)]*\)', '', stem).strip()
    return len(plain) >= 80 and not MATERIAL_REF.search(plain[:300])


def parse_raw(path, module):
    t = path.read_text(encoding='utf-8')
    meta = dict(re.findall(r'^(\S+): "(.*)"$', t.split('\n---', 1)[0], re.M))
    base = str(path.parent)
    out, material, under = [], '', 0
    parts = re.split(r'^(#{2,3} (?:材料 \d+|第 \d+ 题.*))$', t, flags=re.M)
    for head, body in zip(parts[1::2], parts[2::2]):
        if head.startswith('## 材料'):
            material, under = body.split('\n---')[0], 0
            continue
        if head.startswith('## '):
            material = ''
        m = re.match(r'#{2,3} 第 (\d+) 题.*?qid (\d+)\s*·\s*([^<]*)</sub>', head)
        if not m:
            continue
        images = set()
        body = body.split('\n---\n')[0]
        stem, _, rest = body.partition('\n- **A**')
        if material and module != '资料分析':        # 资料分析的题全挂在材料下面（一段材料偶尔管 6、7 道）
            under += 1
            if under > MATERIAL_MAX or (under > 1 and _own_passage(stem)):
                material = ''
        rest = '- **A**' + rest
        opts, answer = {}, ''
        for o in re.finditer(r'^- \*\*([A-H])\*\*[.．]\s*(.*)$', rest, re.M):
            v = o.group(2)
            if '✅' in v:
                answer += o.group(1)
            opts[o.group(1)] = to_text(v.replace('✅', ''), base, images).replace('\n', ' ').strip()
        a = re.search(r'^\*\*答案\*\*：\s*(.*)$', rest, re.M)
        answer = a.group(1).strip() if a else answer
        ana = rest.split('**官方解析**', 1)[1] if '**官方解析**' in rest else ''
        text = to_text(stem, base, images)
        if module == '资料分析':            # 网页按“最后一段是问题、前面是材料”拆，问题自己不能有空行
            text = re.sub(r'\n\s*\n', '\n', text)
        if material.strip():
            text = to_text(material, base, images) + '\n\n' + text
        kind = m.group(3).strip()
        board = VERBAL_BOARD.get(kind, '片段阅读') if module == '言语理解与表达' else RAW_BOARD[module]
        if module == '资料分析':
            kind = kind or '综合'
        out.append({'qid': m.group(2), 'num': int(m.group(1)), 'paper': meta.get('试卷', ''), 'year': meta.get('年份', ''),
                    'module': module, 'board': board, 'topic': kind or module, 'stem': BLANK.sub('____', text),
                    'options': opts, 'answer': answer, 'analysis': to_text(ana, base, images), 'images': images})
    return out


# ---------------------------------------------------------------- 修旧题库：材料串到后面的独立题上
# 旧版 parse_raw 把一段材料接到了它后面所有 ### 题上（材料只管它下面那几道）。题库已经生成并合并过蒸馏解析，
# 不能整份重转，所以只修题干：data/material_fix.json 记着每道受影响的题“正确题干”的长度和指纹，
# 题干末尾正好是这段、前面多出一截的，才把多出的那截删掉；自己改过的题干对不上指纹，不动。
FIX_FILE = Path(__file__).parent / 'data' / 'material_fix.json'
FIX_MARK = '.材料串题已修复-v1'


def _fp(text):
    import hashlib
    return hashlib.sha1(text.encode('utf-8')).hexdigest()[:12]


def _clean_stem(s):
    return re.sub(r'^(#+)\s', lambda m: '＃' * len(m.group(1)) + ' ', s, flags=re.M)


def build_material_fix(src, old_parse):
    """生成修复表：{qid: [正确题干长度, 指纹]}（old_parse 是旧版 parse_raw，只收新旧不同的题）"""
    out, seen = {}, set()
    for folder, module in RAW_MODULES.items():
        for f in sorted((Path(src) / folder).glob('*.md')):
            if f.name == 'README.md':
                continue
            new = {q['qid']: q for q in parse_raw(f, module)}
            for q in old_parse(f, module):
                if q['qid'] in seen:
                    continue
                seen.add(q['qid'])
                n = new.get(q['qid'])
                if n and n['stem'] != q['stem']:
                    good = _clean_stem(n['stem'])
                    out[q['qid']] = [len(good), _fp(good)]
    return out


def _source_tag(stem):
    """题干开头的来源括号（可能套括号：（2018年黑龙江省公务员考试（公检法）题（网友回忆版））"""
    if not stem.startswith('（'):
        return ''
    depth = 0
    for i, c in enumerate(stem[:120]):
        depth += c == '（'
        depth -= c == '）'
        if depth == 0:
            return stem[:i + 1]
        if c == '\n':
            break
    return ''


def trim_stem(stem, fix):
    """题干末尾正好是正确题干（长度 + 指纹对得上）且前面多一截：返回修好的（保留来源括号），否则 None"""
    prefix = _source_tag(stem)
    rest = stem[len(prefix):]
    L, fp = fix
    if len(rest) > L and _fp(rest[-L:]) == fp:
        return prefix + rest[-L:]
    return None


def fix_material_state(state):
    """存档里的题目快照（作答记录、没做完的组）也修：回炉、续闯用的是快照"""
    import json
    if not FIX_FILE.is_file():
        return 0
    table = json.loads(FIX_FILE.read_text(encoding='utf-8'))
    bank = state.get('bank') or {}
    qs = [r.get('question') for r in (bank.get('records') or {}).values()]
    qs += [q for run in (bank.get('runs') or {}).values() for q in run.get('questions', [])]
    n = 0
    for q in qs:
        if not q or not str(q.get('id', '')).startswith('真题-'):
            continue
        fix = table.get(q['id'][3:])
        good = trim_stem(q.get('stem', ''), fix) if fix else None
        if good is not None:
            q['stem'] = good
            n += 1
    return n


def fix_material_leak(paths, force=False):
    """按修复表删掉串进题干的材料。返回 {"fixed", "files"}；做过一次留个标记，下次启动不再扫"""
    import json
    folder = paths.train / '题库' if paths.train else None
    if not folder or not folder.is_dir() or not FIX_FILE.is_file():
        return {'fixed': 0, 'files': []}
    mark = folder / FIX_MARK
    if mark.exists() and not force:
        return {'fixed': 0, 'files': [], 'done_before': True}
    table = json.loads(FIX_FILE.read_text(encoding='utf-8'))
    head = re.compile(r'^## 题目 真题-(\d+)[ \t]*$', re.M)
    fixed, files = 0, []
    for f in sorted(folder.glob('*真题*.md')):
        text = f.read_text(encoding='utf-8')
        if '真题-' not in text:
            continue
        out, pos, n = [], 0, 0
        for m in head.finditer(text):
            fix = table.get(m.group(1))
            if not fix:
                continue
            start = text.find('\n### 题干\n', m.end())
            nxt = head.search(text, m.end())
            if start < 0 or (nxt and start > nxt.start()):
                continue
            body_start = start + len('\n### 题干\n')
            body_end = text.find('\n### ', body_start)
            if body_end < 0:
                continue
            stem = text[body_start:body_end]
            good = trim_stem(stem, fix)
            if good is not None:
                out.append(text[pos:body_start] + good)
                pos = body_end
                n += 1
        if n:
            out.append(text[pos:])
            f.write_text(''.join(out), encoding='utf-8', newline='\n')
            fixed += n
            files.append(f.name)
    try:
        mark.write_text('材料串题修复：%d 题（%s）\n' % (fixed, '、'.join(files)), encoding='utf-8', newline='\n')
    except OSError:
        pass
    return {'fixed': fixed, 'files': files}


def convert_raw(src, out, skip_ids=()):
    """原题副本 → 训练/题库/<板块>真题-<年份>.md（按年份拆，单个文件不至于太大），图片原样拷到 题库/图片/真题库/"""
    import shutil
    src, out = Path(src), Path(out)
    seen, qs, skipped, by_id = set(skip_ids), [], Counter(), {}
    for folder, module in RAW_MODULES.items():
        for f in sorted((src / folder).glob('*.md')):
            if f.name == 'README.md':
                continue
            for q in parse_raw(f, module):
                if q['qid'] in by_id:      # 联考各省卷共用的题：记到第一次出现的那道题上，几张卷子都能刷到它
                    by_id[q['qid']].setdefault('also', []).append((q['paper'], q['num']))
                    skipped['几张卷子共用'] += 1
                    continue
                if q['qid'] in seen:
                    skipped['判断推理已有'] += 1
                    continue
                if set(q['options']) != set('ABCD') or not all(q['options'].values()) or not q['stem']:
                    skipped['不是四个选项'] += 1
                    continue
                if q['answer'] in ('（缺）', ''):
                    q['answer'] = ''
                elif not re.fullmatch(r'[A-D]', q['answer']):
                    skipped['多选题'] += 1
                    continue
                by_id[q['qid']] = q
                qs.append(q)
    qs.sort(key=lambda q: (-int(q['year'] or 0), q['paper'], q['module'], q['num']))
    folder = out / '题库'
    folder.mkdir(parents=True, exist_ok=True)
    by = Counter()
    for board, year in sorted({(q['board'], q['year']) for q in qs}):
        mine = [q for q in qs if q['board'] == board and q['year'] == year]
        by[board] += len(mine)
        head = ('# %s · %s年真题\n\n> 由 rpg/zhenti.py 从 ERRRC/xingcezhenti 原题副本转换，共 %d 题。重新转换会整份覆盖。\n\n'
                % (board, year, len(mine)))
        (folder / ('%s真题-%s.md' % (board, year))).write_text(head + ''.join(block(q) for q in mine), encoding='utf-8', newline='\n')
    images = sorted({i for q in qs for i in q['images']})
    missing = 0
    for i in images:
        dst = folder / '图片' / '真题库' / i
        dst.parent.mkdir(parents=True, exist_ok=True)
        if (src / '90-图片' / i).is_file():
            shutil.copyfile(src / '90-图片' / i, dst)
        else:
            missing += 1
    return {'total': len(qs), 'boards': dict(by), 'skipped': dict(skipped), 'images': len(images), 'missing_images': missing,
            'pending': sum(not q['answer'] for q in qs), 'papers': len({q['paper'] for q in qs})}


# ---------------------------------------------------------------- 资料分析：原题副本（整张卷子、带材料） + 考公脑库蒸馏解析
def _material_traps(kg):
    """15-材料/资料分析/<mid> …md 的「阅读陷阱」：{mid: 文字}"""
    out = {}
    for f in (Path(kg) / '15-材料' / '资料分析').glob('*.md'):
        t = f.read_text(encoding='utf-8')
        m = re.search(r'^mid: "(\d+)"', t, re.M)
        traps = section(t, '阅读陷阱', '##')
        if m and traps:
            out[m.group(1)] = '\n'.join(re.sub(r'^-\s*', '', ln).strip() for ln in traps.splitlines() if ln.strip())
    return out


def convert_ziliao(raw, kg, out):
    """ERRRC/xingcezhenti 的 06-资料分析（505 张卷子，每张 20 题，按考试顺序、材料挂在题上）
    + 考公脑库 10-真题/资料分析 的蒸馏笔记（按 qid 对上：解析补问法模型 / 推理链 / 最快解法 / 易错点 / 母题抽象，知识点用它的 7 大类）
    + 15-材料 的阅读陷阱 → 训练/题库/资料分析真题-<年份>.md；图片拷到 题库/图片/真题库/（先找考公脑库的，没有再找原题副本的）。"""
    import shutil
    raw, kg, out = Path(raw), Path(kg), Path(out)
    notes, mids = {}, {}
    for f in sorted((kg / '10-真题' / '资料分析').glob('*/*.md')):
        n = parse_note(f)
        if n['qid']:
            n['family'] = {'基期计算（增长类）': '增长'}.get(f.parent.name, f.parent.name)   # 这一类只有 1 题，并进增长
            notes[n['qid']] = n
            m = re.search(r'15-材料/资料分析/(\d+)', f.read_text(encoding='utf-8'))
            if m:
                mids[n['qid']] = m.group(1)
    traps = _material_traps(kg)
    qs, by_id, skipped = [], {}, Counter()
    for f in sorted((raw / '06-资料分析').glob('*.md')):
        if f.name == 'README.md':
            continue
        for q in parse_raw(f, '资料分析'):
            if q['qid'] in by_id:
                by_id[q['qid']].setdefault('also', []).append((q['paper'], q['num']))
                skipped['几张卷子共用'] += 1
                continue
            if set(q['options']) != set('ABCD') or not all(q['options'].values()) or not q['stem']:
                skipped['不是四个选项'] += 1
                continue
            if not re.fullmatch(r'[A-D]', q['answer'] or ''):
                q['answer'] = ''
            n = notes.get(q['qid'])
            parts = ['【官方解析】\n' + q['analysis']] if q['analysis'] else []
            if n:
                q['topic'] = n['family']
                if n['topic']:
                    parts.append('【考点】\n' + n['topic'])
                if n['extra']:
                    parts.append(n['extra'])
                q['images'] |= n['images']
            if traps.get(mids.get(q['qid'], '')):
                parts.append('【材料陷阱】\n' + traps[mids[q['qid']]])
            q['analysis'] = '\n\n'.join(parts) or '（待补）'
            by_id[q['qid']] = q
            qs.append(q)
    qs.sort(key=lambda q: (-int(q['year'] or 0), q['paper'], q['num']))
    folder = out / '题库'
    folder.mkdir(parents=True, exist_ok=True)
    years = Counter()
    for year in sorted({q['year'] for q in qs}):
        mine = [q for q in qs if q['year'] == year]
        years[year] = len(mine)
        head = ('# 资料分析 · %s年真题\n\n> 由 rpg/zhenti.py 转换：题目、材料、官方解析来自 ERRRC/xingcezhenti 原题副本，'
                '蒸馏解析来自考公脑库（ERRRC/kaogongzhentizhengliu），共 %d 题。重新转换会整份覆盖。\n\n' % (year, len(mine)))
        (folder / ('资料分析真题-%s.md' % year)).write_text(head + ''.join(block(q) for q in mine), encoding='utf-8', newline='\n')
    images = sorted({i for q in qs for i in q['images']})
    missing = []
    for i in images:
        src = next((d / '90-图片' / i for d in (kg, raw) if (d / '90-图片' / i).is_file()), None)
        if not src:
            missing.append(i)
            continue
        dst = folder / '图片' / '真题库' / i
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    return {'total': len(qs), 'distilled': sum(q['qid'] in notes for q in qs), 'years': dict(years), 'skipped': dict(skipped),
            'papers': len({q['paper'] for q in qs}), 'pending': sum(not q['answer'] for q in qs),
            'images': len(images), 'missing_images': missing[:20], 'missing_count': len(missing),
            'topics': Counter(q['topic'] for q in qs).most_common()}


if __name__ == '__main__':
    if sys.argv[1:2] == ['--ziliao']:   # python -m rpg.zhenti --ziliao <xingcezhenti 目录> <考公脑库目录> <输出目录>
        print(convert_ziliao(sys.argv[2], sys.argv[3], sys.argv[4]))
        sys.exit()
    if sys.argv[1:2] == ['--raw']:   # python -m rpg.zhenti --raw <xingcezhenti 目录> <输出目录> [已有题库目录：跳过重复编号]
        skip = set()
        for f in Path(sys.argv[4]).glob('*真题*.md') if len(sys.argv) > 4 else []:
            skip |= set(re.findall(r'^## 题目 真题-(\d+)', f.read_text(encoding='utf-8'), re.M))
        print(convert_raw(sys.argv[2], sys.argv[3], skip))
    else:
        print(convert(sys.argv[1], sys.argv[2]))
