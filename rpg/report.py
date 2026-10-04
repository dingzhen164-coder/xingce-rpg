"""宗门大比·读成绩截图：粉笔模考报告的两张截图（得分 / 最高分 / 平均分 / 已击败 / 排名，和各模块“共几题、答对几题、正确率、用时”）
→ 自动填成绩单。

认字用系统自带的 OCR：Windows 用 Windows.Media.Ocr（PowerShell 调，不装东西；Windows 10/11 装了中文语言就有），
Mac 用苹果的 Vision（Mac App 里带着 pyobjc；源码版要 pip install pyobjc-framework-Vision）。
都不行时，也可以把报告里的文字复制粘贴进来（手机相册“提取文字”、微信长按图片“提取文字”都行），
同一个解析器处理。
"""
import os
import re
import subprocess
import sys
import tempfile

from . import importer

PS = r'''
param([string]$Path)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
  $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [Type]$t) { $task = $asTask.MakeGenericMethod($t).Invoke($null, @($op)); $task.Wait(-1) | Out-Null; $task.Result }
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Path)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('zh-Hans-CN'))
if ($engine -eq $null) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }
if ($engine -eq $null) { Write-Error 'NO_OCR_LANGUAGE' }
$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
foreach ($line in $result.Lines) { [Console]::WriteLine($line.Text) }
'''


class ReportError(Exception):
    pass


def ocr_mac(path):
    """Mac：苹果 Vision 认字。按从上到下、从左到右排成一行一行（和 Windows OCR 的输出一样给解析器用）"""
    try:
        import Vision
        from Foundation import NSURL
    except ImportError:
        raise ReportError("这台 Mac 缺认字组件：用 Mac App 版，或在终端运行 pip3 install pyobjc-framework-Vision；也可以把报告文字粘贴进来")
    handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(NSURL.fileURLWithPath_(path), None)
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(0)                     # 0 = 准确优先
    req.setRecognitionLanguages_(["zh-Hans", "en-US"])
    req.setUsesLanguageCorrection_(False)           # 数字、百分比别被“纠正”
    ok, err = handler.performRequests_error_([req], None)
    if not ok:
        raise ReportError("Mac 认字失败（%s）：把报告文字粘贴进来也行" % err)
    items = []
    for obs in req.results() or []:
        cand = obs.topCandidates_(1)
        if not cand:
            continue
        box = obs.boundingBox()                     # 原点在左下，0~1
        items.append((1 - (box.origin.y + box.size.height / 2), box.origin.x, box.size.height, str(cand[0].string())))
    items.sort()
    rows = []                                       # 中线差不到半个字高的算同一行
    for y, x, h, t in items:
        if rows and abs(rows[-1][0] - y) < h / 2:
            rows[-1][1].append((x, t))
        else:
            rows.append([y, [(x, t)]])
    return "\n".join(" ".join(t for _, t in sorted(r)) for _, r in rows) + "\n"


def ocr(data):
    """一张图 → 文字（一行一行）。Windows、Mac 能用"""
    if sys.platform == "darwin":
        with tempfile.TemporaryDirectory() as d:
            img = os.path.join(d, "report.png")
            with open(img, "wb") as f:
                f.write(data)
            out = ocr_mac(img)
        if not out.strip():
            raise ReportError("Mac 没认出字：截图清楚吗？也可以把报告文字粘贴进来")
        return out
    if os.name != "nt":
        raise ReportError("这台电脑没有能用的自带 OCR：把报告里的文字复制粘贴到下面的框里也行")
    with tempfile.TemporaryDirectory() as d:
        img = os.path.join(d, "report.png")
        with open(img, "wb") as f:
            f.write(data)
        script = os.path.join(d, "ocr.ps1")
        with open(script, "w", encoding="utf-8-sig") as f:
            f.write(PS)
        try:
            r = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script, "-Path", img],
                               capture_output=True, timeout=90)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise ReportError("调用 Windows OCR 失败（%s）：把报告文字复制粘贴进来也行" % e)
        out = r.stdout.decode("utf-8", errors="replace")
        if r.returncode != 0 or not out.strip():
            err = r.stderr.decode("utf-8", errors="replace")
            if "NO_OCR_LANGUAGE" in err:
                raise ReportError("Windows 没装中文 OCR：设置 → 时间和语言 → 语言 → 中文（简体）→ 语言选项 里装上“光学字符识别”，或者把报告文字粘贴进来")
            raise ReportError("Windows OCR 没认出字：%s" % (err.strip()[-300:] or "没有输出"))
        return out


# ---------------------------------------------------------------- 解析报告文字
MODULES = {"政治理论": "政治理论", "常识判断": "常识判断", "言语理解与表达": "言语理解", "言语理解": "言语理解",
           "数量关系": "数量关系", "判断推理": "判断推理", "资料分析": "资料分析"}
SUBS = {"图形推理": "判断推理", "定义判断": "判断推理", "类比推理": "判断推理", "逻辑判断": "判断推理",
        "逻辑填空": "言语理解", "片段阅读": "言语理解", "语句表达": "言语理解"}
STAT = re.compile(r"共(\d+)题[,，]?答对(\d+)题[,，]?(?:正确率(\d+)%?[,，]?)?(?:用时(\d+)分钟?)?")
NUM = r"(\d{1,3}(?:\.\d{1,2})?)"


def _norm(line):
    """Windows OCR 认中文时字和字之间常有空格：去掉中文、标点旁边的空格，数字之间的留着"""
    line = line.replace("：", ":").replace("％", "%")
    line = re.sub(r"(?<=[^\x00-\x7f])\s+|\s+(?=[^\x00-\x7f])", "", line)
    line = re.sub(r"\s*([%/.,，])\s*", r"\1", line)
    return line.strip()


def parse(text):
    lines = [_norm(x) for x in str(text or "").splitlines()]
    lines = [x for x in lines if x]
    out = {"modules": {}, "sub": {}}
    # 各模块：模块名一行，下一行“共20题，答对11题，正确率55%，用时8分钟”（也可能在同一行）
    cur = None
    for ln in lines:
        name = next((n for n in list(MODULES) + list(SUBS) if ln.startswith(n)), None)
        if name:
            cur = name
        m = STAT.search(re.sub(r"(?<=\d)\s+(?=\d)", "", ln))    # “答对2 5题”：题数里不会有空格，认字拆开的拼回去
        if m and cur:
            v = {"total": int(m.group(1)), "ok": int(m.group(2)), "minutes": int(m.group(4)) if m.group(4) else None}
            if cur in MODULES:
                out["modules"].setdefault(MODULES[cur], v)
            else:
                out["sub"].setdefault(SUBS[cur], {}).setdefault("类比推理" if cur == "类比推理" else cur, v)
            cur = None

    TOKEN = re.compile(r"\d+/\d+|\d{1,3}(?:\.\d{1,2})?%?")

    def near(label, before_first=True):
        """标签对应的数：同一行“93.7最高分”→ 上一行 / 下一行按位置对（粉笔报告：得分在数上面，最高分 / 平均分 / 排名在数下面，
        一行几个标签就对一行里第几个数）"""
        for i, ln in enumerate(lines):
            labels = re.findall(r"最高分|平均分|已击败考生|已击败|排名|得分(?!分布)", ln)
            if label not in labels:
                continue
            k = labels.index(label)
            m = re.search(r"(\d+/\d+|" + NUM + r")%?" + re.escape(label), ln) or re.search(re.escape(label) + r":?(\d+/\d+|" + NUM + ")", ln)
            if m:
                return m.group(1)
            # 一个标签一行、一个数一行（手机“提取文字”常见）：几行标签对应它上面同样几行数
            only = lambda x: bool(re.fullmatch(r"(?:最高分|平均分|已击败考生|已击败|排名)", lines[x]))
            if only(i) and before_first:
                a, b = i, i
                while a - 1 >= 0 and only(a - 1):
                    a -= 1
                while b + 1 < len(lines) and only(b + 1):
                    b += 1
                n = b - a + 1
                if n > 1 and a - n >= 0 and all(TOKEN.fullmatch(lines[x]) for x in range(a - n, a)):
                    return lines[a - n + (i - a)].rstrip("%")
            for j in ((i - 1, i + 1) if before_first else (i + 1, i - 1)):
                if 0 <= j < len(lines):
                    toks = TOKEN.findall(lines[j])
                    if toks and len(toks) >= len(labels) and not re.search(r"[\u4e00-\u9fff]", lines[j]):
                        return toks[k].rstrip("%")
        return None

    score = near("得分", before_first=False)
    if score is None:
        m = re.search(NUM + r"/100", " ".join(lines))
        score = m.group(1) if m else None
    rank = near("排名") or ""
    rp = rank.split("/") if "/" in rank else [None, None]
    fields = {"score": score, "top": near("最高分"), "avg": near("平均分"),
              "beat": near("已击败考生") or near("已击败"), "rank": rp[0], "people": rp[1]}
    joined = "\n".join(lines)
    d = re.search(r"(20\d\d)[.\-/年](\d{1,2})[.\-/月](\d{1,2})", joined)
    fields["date"] = "%s-%02d-%02d" % (d.group(1), int(d.group(2)), int(d.group(3))) if d else None
    s = re.search(r"第([一二三四五六七八九十百零\d]+)季", joined)
    fields["season"] = importer._cn2int(s.group(1)) if s else None
    out["fields"] = {k: v for k, v in fields.items() if v not in (None, "")}
    return out


def scan(images=(), text=""):
    """几张截图（和 / 或粘贴的文字）→ 合并后的解析结果"""
    chunks, engine = [], []
    if text and str(text).strip():
        chunks.append(str(text))
        engine.append("粘贴的文字")
    for data in images:
        chunks.append(ocr(data))
        engine.append("Windows OCR")
    if not chunks:
        raise ReportError("先选成绩截图，或者把报告文字粘贴进来")
    out = {"modules": {}, "sub": {}, "fields": {}}
    for c in chunks:
        r = parse(c)
        for k in ("modules", "fields"):
            for kk, v in r[k].items():
                out[k].setdefault(kk, v)
        for m, subs in r["sub"].items():
            for kk, v in subs.items():
                out["sub"].setdefault(m, {}).setdefault(kk, v)
    out["engine"] = "、".join(dict.fromkeys(engine))
    out["text"] = "\n\n".join(chunks)[:4000]
    return out
