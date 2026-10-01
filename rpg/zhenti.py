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
    analysis = '\n\n'.join('【%s】\n%s' % (k, to_text(v, base, images) if k != '官方解析' else v) for k, v in parts if v)
    point = meta.get('考点', '')
    kind = path.parent.name
    board = logic_board(point.split(' / ', 1)[-1]) if kind == '逻辑判断' else BOARD_OF_DIR.get(kind, '')
    return {'qid': meta.get('qid', ''), 'paper': meta.get('试卷', ''), 'year': meta.get('年份', ''),
            'board': board, 'kind': kind, 'point': point, 'topic': point.split(' / ', 1)[-1] or kind,
            'stem': stem, 'options': opts, 'answer': answer, 'analysis': analysis, 'images': images}


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
    img_list.write_text('\r\n'.join(i.replace('/', '\\') for i in images) + '\r\n', encoding='utf-8-sig')
    return {'total': len(qs), 'boards': dict(by), 'bad': bad, 'unknown': dict(unknown), 'images': len(images),
            'pending': sum(not q['answer'] for q in qs), 'papers': len({q['paper'] for q in qs})}


# ---------------------------------------------------------------- 原题副本（ERRRC/xingcezhenti）
# 每张卷子每个模块一个文件，题目按考试顺序：## 第 N 题　<sub>qid X · 题型</sub>；有材料的是 ## 材料 N 下面挂 ### 第 N 题。
RAW_MODULES = {'01-政治理论': '政治理论', '02-常识判断': '常识判断', '03-言语理解与表达': '言语理解与表达', '04-数量关系': '数量关系'}
RAW_BOARD = {'政治理论': '政治理论', '常识判断': '常识判断', '数量关系': '数量关系'}
VERBAL_BOARD = {'逻辑填空': '逻辑填空', '片段阅读': '片段阅读', '语句表达': '片段阅读'}
BLANK = re.compile(r'(?<=\S)[ \u3000\u00a0]{3,}(?=\S)')   # 句子中间一串空格 = 原卷的填空横线


def parse_raw(path, module):
    t = path.read_text(encoding='utf-8')
    meta = dict(re.findall(r'^(\S+): "(.*)"$', t.split('\n---', 1)[0], re.M))
    base = str(path.parent)
    out, material = [], ''
    parts = re.split(r'^(#{2,3} (?:材料 \d+|第 \d+ 题.*))$', t, flags=re.M)
    for head, body in zip(parts[1::2], parts[2::2]):
        if head.startswith('## 材料'):
            material = body.split('\n---')[0]
            continue
        if head.startswith('## '):
            material = ''
        m = re.match(r'#{2,3} 第 (\d+) 题.*?qid (\d+)\s*·\s*([^<]*)</sub>', head)
        if not m:
            continue
        images = set()
        body = body.split('\n---\n')[0]
        stem, _, rest = body.partition('\n- **A**')
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
        if material.strip():
            text = to_text(material, base, images) + '\n\n' + text
        kind = m.group(3).strip()
        board = VERBAL_BOARD.get(kind, '片段阅读') if module == '言语理解与表达' else RAW_BOARD[module]
        out.append({'qid': m.group(2), 'num': int(m.group(1)), 'paper': meta.get('试卷', ''), 'year': meta.get('年份', ''),
                    'module': module, 'board': board, 'topic': kind or module, 'stem': BLANK.sub('____', text),
                    'options': opts, 'answer': answer, 'analysis': to_text(ana, base, images), 'images': images})
    return out


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


if __name__ == '__main__':
    if sys.argv[1:2] == ['--raw']:   # python -m rpg.zhenti --raw <xingcezhenti 目录> <输出目录> [已有题库目录：跳过重复编号]
        skip = set()
        for f in Path(sys.argv[4]).glob('*真题*.md') if len(sys.argv) > 4 else []:
            skip |= set(re.findall(r'^## 题目 真题-(\d+)', f.read_text(encoding='utf-8'), re.M))
        print(convert_raw(sys.argv[2], sys.argv[3], skip))
    else:
        print(convert(sys.argv[1], sys.argv[2]))
