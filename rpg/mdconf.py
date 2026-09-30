"""
解析 “- 键: 值” 格式的 Markdown 配置文件。

设计目的：规则.md / 角色设定.md 要让用户在 Obsidian 里直接改，所以不用 JSON/YAML，
只认这样的行（冒号中英文都行）：

    - 满级目标日: 2027-12-01        # 行尾两个以上空格再加 # 是注释
    - 第1批: 论证逻辑, 形式逻辑, 一拖五

标题、引用、普通文字、空行都会被忽略；键可以带点（如 “经验.默写通过”）。
同一个键写了多次，以最后一次为准。
"""
import re

LINE_RE = re.compile(r"^\s*[-*]\s+([^:：#>\n]+?)\s*[:：]\s*(.*?)\s*$")
COMMENT_RE = re.compile(r"\s{2,}#.*$|\t#.*$")


def parse(text):
    """返回 {键: 原始字符串值}（保持文件里的顺序）"""
    out = {}
    in_code = False
    for ln in text.splitlines():
        if ln.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = LINE_RE.match(ln)
        if not m:
            continue
        key = m.group(1).strip()
        val = COMMENT_RE.sub("", m.group(2)).strip()
        if val.startswith("#"):  # “- ID:  # 说明” —— 值留空、后面直接是注释
            val = ""
        out[key] = val
    return out


def split_list(val):
    """“a, b，c、d” → ["a", "b", "c", "d"]"""
    return [x.strip() for x in re.split(r"[,，、]", val or "") if x.strip()]


def to_num(val, default):
    try:
        f = float(str(val).strip().rstrip("%"))
        if str(val).strip().endswith("%"):
            f /= 100
        return int(f) if f == int(f) and isinstance(default, int) else f
    except Exception:
        return default


def sections(text):
    """按 “## 标题” 分段，返回 {标题: [以 - 开头的条目文字]}，给台词库用"""
    out, cur = {}, None
    for ln in text.splitlines():
        h = re.match(r"^##\s+(.+?)\s*$", ln)
        if h:
            cur = h.group(1)
            out.setdefault(cur, [])
            continue
        m = re.match(r"^\s*[-*]\s+(.+?)\s*$", ln)
        if m and cur:
            out[cur].append(m.group(1))
    return out
