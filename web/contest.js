/* 宗门大比：每周粉笔模考的成绩与走势（数据来自 /api/mock，见 rpg/mock.py）。
   - 顶上一排数字：模考总平均分、最近一次、最高、大比平均分、平均击败、最近排名、平均正确率
   - 分数走势（我的 / 大比平均 / 最高分）、六大模块正确率走势：折线图，悬停看每一季的数，下面可展开数据表
   - 六大模块：选一季或“历次平均”，看得分（没录就估）、正确率、用时
   - 大比复盘：选一季，按板块逐题复盘（和试炼交卷后的复盘一样；时间记进“修炼 · 复习”，见 rpg/trainer.py mock_review）
   - 历次模考一览 + 录入成绩单（粉笔成绩单上的数字照抄） */
(function () {
  let MOCK = null;
  let PICK = "avg";          // 模块统计看哪一季："avg" = 历次平均
  let EDIT = null;           // 正在录入的季
  let AN = null;             // 考情分析看哪一季
  const CONV = {};           // 季 → 考情分析对话
  let AN_BUSY = false;
  let AN_FOLD = (() => { try { return localStorage.getItem("xrpg-an-fold") !== "0"; } catch (e) { return true; } })();   // 考情分析默认收起
  const setFold = (v) => { AN_FOLD = v; try { localStorage.setItem("xrpg-an-fold", v ? "1" : "0"); } catch (e) { /* 只管这一次 */ } };
  let MK = null;             // 答题卡截图识别结果 {season, marks, sections, images, ...}
  let MK_SEASON = null;
  let REPORT = null;         // 成绩截图认出来的各模块答对数（保存时一起存）
  let RV = null;             // 大比复盘看哪一季
  let RV_WRONG = false;      // 只复盘错题和没做的
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const f1 = (x) => (x == null ? "—" : (Math.round(x * 10) / 10).toString());
  const pc = (x) => (x == null ? "—" : Math.round(x * 100) + "%");

  // ---------------------------------------------------------------- 折线图（一条 y 轴；悬停十字线 + 提示）
  function lineChart(id, { xs, series, yMin, yMax, unit = "", ticks = 5 }) {
    const W = 760, H = 260, L = 40, R = 16, T = 14, B = 30;
    const iw = W - L - R, ih = H - T - B;
    const x = (i) => L + (xs.length <= 1 ? iw / 2 : (i * iw) / (xs.length - 1));
    const y = (v) => T + ih - ((v - yMin) / (yMax - yMin)) * ih;
    const grid = Array.from({ length: ticks + 1 }, (_, k) => {
      const v = yMin + ((yMax - yMin) * k) / ticks;
      return `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" class="cg"/><text x="${L - 6}" y="${y(v) + 4}" class="cy">${Math.round(v)}${unit}</text>`;
    }).join("");
    const xl = xs.map((t, i) => (xs.length > 12 && i % 2 && i !== xs.length - 1 ? "" : `<text x="${x(i)}" y="${H - 8}" class="cx">${esc(t)}</text>`)).join("");
    const lines = series.map((s) => {
      const pts = s.values.map((v, i) => (v == null ? null : [x(i), y(v)]));
      let d = "", pen = false;
      pts.forEach((p) => { if (!p) { pen = false; return; } d += (pen ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1); pen = true; });
      const dots = pts.map((p) => (p ? `<circle cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="4" class="cd" style="fill:${s.color}"/>` : "")).join("");
      return `<path d="${d}" class="cl${s.dash ? " dash" : ""}" style="stroke:${s.color}"/>${dots}`;
    }).join("");
    const legend = series.map((s) => `<span class="lg"><i style="background:${s.color};border-color:${s.color}"${s.dash ? ' class="dash"' : ""}></i>${esc(s.name)}</span>`).join("");
    const table = `<details class="ctable"><summary>看数据表</summary><div class="tbl-wrap"><table><thead><tr><th>季</th>${series.map((s) => `<th>${esc(s.name)}</th>`).join("")}</tr></thead>
      <tbody>${xs.map((t, i) => `<tr><td>${esc(t)}</td>${series.map((s) => `<td>${s.values[i] == null ? "—" : f1(s.values[i]) + unit}</td>`).join("")}</tr>`).join("")}</tbody></table></div></details>`;
    return `<div class="chart" id="${id}" data-chart='${esc(JSON.stringify({ xs, series: series.map((s) => ({ name: s.name, color: s.color, values: s.values })), L, R, W, unit }))}'>
      <div class="legend">${legend}</div>
      <div class="cwrap"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="折线图">${grid}${xl}
        <line class="cross" x1="0" x2="0" y1="${T}" y2="${T + ih}" style="display:none"/>${lines}</svg><div class="tip" hidden></div></div>
      ${table}</div>`;
  }
  function bindCharts() {
    document.querySelectorAll(".chart[data-chart]").forEach((el) => {
      const c = JSON.parse(el.dataset.chart);
      const svg = el.querySelector("svg"), tip = el.querySelector(".tip"), cross = el.querySelector(".cross"), wrap = el.querySelector(".cwrap");
      const n = c.xs.length;
      const move = (ev) => {
        const r = svg.getBoundingClientRect();
        const vx = ((ev.clientX - r.left) / r.width) * c.W;
        const iw = c.W - c.L - c.R;
        const i = n <= 1 ? 0 : Math.max(0, Math.min(n - 1, Math.round(((vx - c.L) / iw) * (n - 1))));
        const px = n <= 1 ? c.L + iw / 2 : c.L + (i * iw) / (n - 1);
        cross.setAttribute("x1", px); cross.setAttribute("x2", px); cross.style.display = "";
        tip.hidden = false;
        tip.innerHTML = `<b>${esc(c.xs[i])}</b>` + c.series.map((s) => `<div><i style="background:${s.color}"></i>${esc(s.name)}<span>${s.values[i] == null ? "—" : f1(s.values[i]) + c.unit}</span></div>`).join("");
        const left = (px / c.W) * r.width;
        tip.style.left = Math.min(Math.max(0, left + 12), wrap.clientWidth - tip.offsetWidth - 4) + "px";
      };
      wrap.addEventListener("pointermove", move);
      wrap.addEventListener("pointerdown", move);
      wrap.addEventListener("pointerleave", () => { tip.hidden = true; cross.style.display = "none"; });
    });
  }

  // ---------------------------------------------------------------- 页面
  const kpi = (label, value, sub = "", cls = "") => `<div class="kpi ${cls}"><div class="k">${label}</div><div class="v">${value}</div>${sub ? `<div class="d">${sub}</div>` : ""}</div>`;

  function moduleGrid(d) {
    const s = PICK === "avg" ? null : d.seasons.find((x) => String(x.season) === String(PICK));
    const mods = s ? s.modules : d.modules.map((m) => ({ ...m, ok: null }));
    const opts = [`<option value="avg" ${PICK === "avg" ? "selected" : ""}>历次平均</option>`]
      .concat(d.seasons.slice().reverse().map((x) => `<option value="${x.season}" ${String(PICK) === String(x.season) ? "selected" : ""}>第 ${x.season} 季</option>`)).join("");
    const cards = mods.map((m, i) => `<div class="mod" style="--mc:var(--s${(d.module_names.indexOf(m.name) % 6) + 1})">
        <div class="mod-h"><b>${esc(m.name)}</b>${s && m.total ? `<span class="faint small">${m.ok}/${m.total} 题</span>` : `<span class="faint small">${m.seasons || ""}${m.seasons ? " 季" : ""}</span>`}</div>
        <div class="mod-row"><span>得分</span><b>${f1(m.score)}</b>${s && m.estimated ? '<span class="faint small">估</span>' : ""}</div>
        <div class="mod-row"><span>正确率</span><b>${pc(m.acc)}</b></div>
        <div class="mbar"><span style="width:${Math.round((m.acc || 0) * 100)}%"></span></div>
        <div class="mod-row"><span>用时</span><b>${m.minutes == null ? "—" : f1(m.minutes) + " 分"}</b>${m.minutes != null && s && m.total ? `<span class="faint small">${Math.round((m.minutes * 60) / m.total)} 秒/题</span>` : ""}</div>
        ${s && m.boards && m.boards.length > 1 ? `<div class="mod-sub">${m.boards.map((b) => `<span>${esc(b.board)} ${b.ok}/${b.total}</span>`).join("")}</div>` : ""}
      </div>`).join("");
    return `<div class="card contest-card"><div class="row"><h3 style="margin:0">☯ 六大模块 <small>得分（没录成绩单的按答对题数折算，标“估”）· 正确率 · 用时</small></h3><span class="spacer"></span>
      <select id="mkPick">${opts}</select></div><div class="mods">${cards || '<p class="muted">还没有模考复盘。</p>'}</div></div>`;
  }

  function form(d) {
    const s = d.seasons.find((x) => String(x.season) === String(EDIT)) || d.seasons[d.seasons.length - 1];
    if (!s) return "";
    const v = (k) => (s[k] == null ? "" : s[k]);
    const opts = d.seasons.slice().reverse().map((x) => `<option value="${x.season}" ${x.season === s.season ? "selected" : ""}>第 ${x.season} 季${x.score == null ? "（未录）" : ""}</option>`).join("");
    const modIn = (key, ph) => d.module_names.map((m) => {
      const mm = s.modules.find((x) => x.name === m);
      const val = key === "minutes" ? mm?.minutes : mm && !mm.estimated ? mm.score : null;
      return `<label>${esc(m)} <input type="number" step="0.1" min="0" data-mk-${key}="${esc(m)}" value="${val == null ? "" : val}" placeholder="${ph}"></label>`;
    }).join("");
    return `<div class="card contest-card" id="mkForm"><h3>📝 录入成绩单 <small>照抄粉笔模考报告上的数字；空着的不算。第一次录分数时也记进${esc(W("boss"))}（修为、悟道、突破丹照旧）</small></h3>
      <div class="rp-auto"><b>📷 从成绩截图自动填</b> <span class="small muted">粉笔模考报告里“得分 / 最高分 / 平均分 / 排名”和“各模块共几题、答对几题、用时”那两张截图（Windows 自带 OCR 认字）</span>
        <div class="row mk-row"><input type="file" id="rpFiles" accept="image/png,image/jpeg" multiple><button class="primary small" id="rpScan">识别并填入</button></div>
        <details class="fold"><summary>不是 Windows / 认不出：把报告文字粘贴进来（手机相册、微信“提取文字”都行）</summary>
          <textarea id="rpText" rows="4" placeholder="得分 64.5 … 最高分 93.7 平均分 56 已击败考生 71.5% … 政治理论 共20题，答对11题，正确率55%，用时8分钟 …"></textarea></details>
        <div id="rpResult" class="small"></div></div>
      <div class="row mk-row">
        <label>哪一季 <select id="mkSeason">${opts}</select></label>
        <label>考试日期 <input type="date" id="mkDate" value="${esc(s.date || "")}"></label>
        <label>我的分数 <input type="number" step="0.1" id="mkScore" value="${v("score")}" placeholder="如 68.5"></label>
        <label>大比平均分 <input type="number" step="0.1" id="mkAvg" value="${v("avg")}" placeholder="如 53.7"></label>
        <label>最高分 <input type="number" step="0.1" id="mkTop" value="${v("top")}" placeholder="如 91.4"></label>
        <label>已击败 % <input type="number" step="0.1" id="mkBeat" value="${v("beat")}" placeholder="如 5.9"></label>
        <label>排名 <input type="number" id="mkRank" value="${v("rank")}" placeholder="如 38580"></label>
        <label>总人数 <input type="number" id="mkPeople" value="${v("people")}" placeholder="如 44774"></label>
      </div>
      <details class="fold" id="mkModsFold" ${s.minutes != null ? "open" : ""}><summary>各模块用时（分钟）· 各模块得分（报告里有就填，没有会按答对题数估）</summary>
        <div class="row mk-row">${modIn("minutes", "用时")}</div>
        <div class="row mk-row">${modIn("score", "得分")}</div></details>
      <div class="row" style="margin-top:8px"><button class="primary" id="mkSave">保存这一季</button><span class="small muted">对错题数从「FB模考试卷复盘/板块复盘/第N季」自动统计，不用填</span></div></div>`;
  }

  // ---------------------------------------------------------------- 考情分析：师傅大比分析 + 追问（存档，也写进 训练/宗门大比/第N季考情分析.md）
  function analysisCard(d) {
    const ss = d.seasons.slice().reverse();
    if (AN == null) AN = ss[0]?.season;
    const conv = CONV[AN] || [];
    const opts = ss.map((x) => `<option value="${x.season}" ${x.season === AN ? "selected" : ""}>第 ${x.season} 季</option>`).join("");
    const msgs = conv.map((m) => m.role === "assistant"
      ? `<div class="npc an-msg">${tutorFace()}<div class="say"><div class="who">${esc(DASH?.persona?.tutor || "师尊")} <span class="faint small">${esc(m.t || "")}</span></div>${md(m.content)}</div></div>`
      : `<div class="msg me an-me">${esc(m.content)}</div>`).join("");
    const fold = AN_FOLD && !AN_BUSY;
    return `<div class="card contest-card an-card ${fold ? "folded" : ""}"><div class="row" style="flex-wrap:wrap;gap:8px"><h3 style="margin:0">🧙 考情分析 <small>师傅看这一季的成绩、各模块 / 各板块对错和用时，和以前比；分析完可以接着问，对话会保存</small></h3>
        <span class="spacer"></span><select id="anSeason" style="width:auto">${opts}</select>
        <button class="${conv.length ? "ghost" : "primary"}" id="anGo" ${AN_BUSY ? "disabled" : ""}>${AN_BUSY ? "师傅分析中…" : conv.length ? "🔄 重新分析" : "🧙 师傅大比分析"}</button>
        <button class="ghost" id="anFold">${fold ? "▸ 展开" : "▾ 收起"}</button></div>
      ${fold ? `<p class="small muted" style="margin:8px 0 0">${conv.length ? `第 ${AN} 季已分析（${conv.filter((m) => m.role === "assistant").length} 段师傅的话），点「展开」看。` : `还没分析过第 ${AN} 季。`}</p></div>` : `
      <div class="an-body">${msgs || `<p class="muted small">还没分析过第 ${AN} 季。先导入答题卡截图、录好成绩单，师傅分析得更准。</p>`}</div>
      ${conv.length ? `<div class="an-ask"><textarea id="anText" rows="2" placeholder="接着问师傅：比如“数量关系该先补哪类题？”“时间怎么分配？”（Ctrl+Enter 发送）"></textarea>
        <button class="primary" id="anSend" ${AN_BUSY ? "disabled" : ""}>问师傅</button></div>` : ""}
      <p class="small faint" style="margin:6px 0 0">对话存在 训练/宗门大比/第 ${AN} 季考情分析.md</p></div>`}`;
  }

  // ---------------------------------------------------------------- 导入答题卡截图（绿对红错）
  function marksCard(d) {
    const ss = d.seasons.slice().reverse();
    if (MK_SEASON == null) MK_SEASON = ss[0]?.season;
    const opts = ss.map((x) => `<option value="${x.season}" ${x.season === MK_SEASON ? "selected" : ""}>第 ${x.season} 季</option>`).join("");
    let preview = "";
    if (MK && MK.season === MK_SEASON) {
      const cell = (n) => { const v = MK.marks[n]; return `<span class="mk-dot ${v === "ok" ? "ok" : v === "bad" ? "bad" : "none"}" data-mkdot="${n}" title="点一下改对 / 错">${n}</span>`; };
      const ok = Object.values(MK.marks).filter((v) => v === "ok").length, bad = Object.values(MK.marks).filter((v) => v === "bad").length;
      const miss = MK.total - ok - bad;
      preview = `<div class="mk-sum">对 <b class="ok">${ok}</b> · 错 <b class="bad">${bad}</b>${miss ? ` · 没识别到 <b>${miss}</b>（灰色，点一下设成对 / 错，或再加一张截图）` : ""}
          <span class="faint small">${MK.images.map((x) => x.matched ? `第 ${x.image} 张：${x.from}–${x.to} 题${x.ambiguous ? "（位置不太确定，核对一下）" : ""}` : `第 ${x.image} 张没对上：${esc(x.why)}`).join("；")}</span></div>
        ${MK.sections.map((sec) => `<div class="mk-sec"><div class="small muted">${esc(sec.name)}</div><div class="mk-dots">${Array.from({ length: sec.to - sec.from + 1 }, (_, i) => cell(String(sec.from + i))).join("")}</div></div>`).join("")}
        <div class="row" style="margin-top:8px"><button class="primary" id="mkMarksSave">保存到第 ${MK.season} 季复盘</button>
          <span class="small muted">写进 板块复盘/第${MK.season}季 的复盘文件（错题“我的答案”记成“？”）；心魔录、正确率、灵根跟着更新</span></div>`;
    }
    return `<div class="card contest-card" id="mkMarksCard"><h3>📸 导入答题卡截图 <small>粉笔模考报告里的答题卡（绿 = 对、红 = 错）；可以选几张，滚动截的重叠也行</small></h3>
      <div class="row mk-row"><label>哪一季 <select id="mkMarksSeason">${opts}</select></label>
        <label>截图 <input type="file" id="mkMarksFiles" accept="image/png,image/jpeg" multiple></label>
        <button class="primary" id="mkMarksScan">识别</button></div>${preview}</div>`;
  }

  // ---------------------------------------------------------------- 大比复盘
  function reviewCard(d) {
    const ss = d.seasons.filter((s) => (s.review || []).length);
    if (!ss.length) return "";
    if (RV == null || !ss.some((s) => s.season === RV)) RV = ss[ss.length - 1].season;
    const cur = ss.find((s) => s.season === RV);
    const opts = ss.slice().reverse().map((s) => `<option value="${s.season}" ${s.season === RV ? "selected" : ""}>第 ${s.season} 季${s.date ? "（" + esc(s.date) + "）" : ""}</option>`).join("");
    const all = cur.review.reduce((a, b) => a + b.total, 0), seen = cur.review.reduce((a, b) => a + b.reviewed, 0);
    const tiles = cur.review.map((b) => {
      const bad = b.wrong + b.blank, full = b.reviewed >= b.total;
      return `<button class="rv-board ${full ? "done" : ""}" data-rv="${esc(b.board)}" ${RV_WRONG && !bad ? "disabled" : ""}>
        <b>${esc(b.board)}</b><span class="rv-cnt"><i class="ok">✓ ${b.ok}</i><i class="bad">✗ ${b.wrong}</i>${b.blank ? `<i class="blank">○ ${b.blank}</i>` : ""}</span>
        <span class="rv-bar"><i style="width:${Math.round(100 * b.reviewed / b.total)}%"></i></span>
        <small>${b.resume ? `⏸ 上次看到第 ${b.resume} 题` : full ? "已复盘完" : b.reviewed ? `已复盘 ${b.reviewed}/${b.total}` : `${b.total} 题 · 未复盘`}</small></button>`;
    }).join("");
    return `<div class="card contest-card rv-card"><div class="row" style="flex-wrap:wrap;gap:10px"><h3 style="margin:0">📜 大比复盘
        <small>像刷完一组题那样，把这一季模考逐题过一遍：看题 → 对答案 → 读解析 → 不懂就问师傅。复盘时间记进「修炼 · 复习」</small></h3>
        <span class="spacer"></span><select id="rvPick" style="width:auto">${opts}</select></div>
      <div class="row" style="gap:12px;margin:8px 0 4px;align-items:center"><span class="small muted">这一季已复盘 <b>${seen}</b>/${all} 题</span>
        <label class="small" style="display:inline-flex;gap:6px;align-items:center;cursor:pointer"><input type="checkbox" id="rvWrong" style="width:auto" ${RV_WRONG ? "checked" : ""}> 只复盘错题和没做的</label>
        <span class="spacer"></span><button class="primary" id="rvStart">${seen ? "从第一个板块复盘" : "开始复盘"}</button></div>
      <div class="rv-grid">${tiles}</div></div>`;
  }
  function startReview(board) {
    startTask({ task: { type: "mock_review", season: RV, board, only_wrong: RV_WRONG, title: `大比复盘 · 第${RV}季` } });
  }
  function bindReview() {
    const pick = document.getElementById("rvPick");
    if (!pick) return;
    pick.onchange = () => { RV = Number(pick.value); rerender(); };
    document.getElementById("rvWrong").onchange = (e) => { RV_WRONG = e.target.checked; rerender(); };
    document.getElementById("rvStart").onclick = () => {
      const cur = MOCK.seasons.find((s) => s.season === RV);
      const first = (cur?.review || []).find((b) => !RV_WRONG || b.wrong + b.blank);
      if (first) startReview(first.board); else toast("这一季没有错题，全对！");
    };
    document.querySelectorAll("[data-rv]").forEach((b) => (b.onclick = () => startReview(b.dataset.rv)));
  }

  function html(d) {
    const o = d.overall, ss = d.seasons;
    if (!ss.length) {
      return `<div class="card contest-hero"><h2>⚔ ${esc(W("boss"))}</h2><p class="muted">还没有模考。模考完先到「${esc(NAV("skeleton"))} → 📖 经卷 · 题库」最下面的「📥 导入真题」导入模考 PDF，这里就会出现成绩与走势。</p></div>`;
    }
    const lr = o.latest_rank;
    const head = `<div class="card contest-hero"><div class="row"><h2>⚔ ${esc(W("boss"))}</h2><span class="small muted">共 ${o.count} 季模考 · 录了成绩单的 ${o.scored} 季</span></div>
      <div class="kpis">
        ${kpi("模考总平均分", f1(o.mean), o.scored ? `${o.scored} 季` : "录成绩单后显示", "hero")}
        ${kpi("最近一次", f1(o.latest))}
        ${kpi("最高", f1(o.best))}
        ${kpi("大比平均分", f1(o.mean_avg), o.mean != null && o.mean_avg != null ? `我比平均 ${o.mean - o.mean_avg >= 0 ? "+" : ""}${f1(o.mean - o.mean_avg)}` : "")}
        ${kpi("平均已击败", o.mean_beat == null ? "—" : f1(o.mean_beat) + "%")}
        ${kpi("最近排名", lr ? `${lr.rank}<small>/${lr.people || "?"}</small>` : "—", lr ? `第 ${lr.season} 季` : "")}
        ${kpi("平均正确率", o.mean_acc == null ? "—" : Math.round(o.mean_acc) + "%", "按复盘对错")}
      </div></div>`;
    const xs = ss.map((s) => "第" + s.season + "季");
    const vals = ss.flatMap((s) => [s.score, s.avg, s.top]).filter((v) => v != null);
    const lo = vals.length ? Math.max(0, Math.floor(Math.min(...vals) / 10) * 10 - 10) : 0;
    const scoreChart = lineChart("chScore", {
      xs, yMin: lo, yMax: 100, unit: "", ticks: Math.round((100 - lo) / 10),
      series: [
        { name: "我的分数", color: "var(--s1)", values: ss.map((s) => s.score) },
        { name: "大比平均分", color: "var(--s2)", values: ss.map((s) => s.avg), dash: true },
        { name: "最高分", color: "var(--s3)", values: ss.map((s) => s.top), dash: true },
      ],
    });
    const accChart = lineChart("chAcc", {
      xs, yMin: 0, yMax: 100, unit: "%",
      series: d.module_names.map((m, i) => ({ name: m, color: `var(--s${i + 1})`,
        values: ss.map((s) => { const x = s.modules.find((y) => y.name === m); return x ? Math.round(x.acc * 1000) / 10 : null; }) })),
    });
    const rows = ss.slice().reverse().map((s) => `<tr><td><b>第 ${s.season} 季</b></td><td>${esc(s.date || "")}</td>
        <td class="num"><b>${f1(s.score)}</b>${s.score_from_boss ? '<span class="faint small"> 修仙录</span>' : ""}</td><td class="num">${f1(s.avg)}</td><td class="num">${f1(s.top)}</td>
        <td class="num">${s.beat == null ? "—" : f1(s.beat) + "%"}</td><td class="num">${s.rank ? `${s.rank}/${s.people || "?"}` : "—"}</td>
        <td class="num">${s.ok}/${s.total}（${pc(s.acc)}）</td><td class="num">${s.minutes == null ? "—" : s.minutes + " 分"}</td>
        <td><button class="ghost small" data-mk-edit="${s.season}">${s.score == null ? "录入" : "改"}</button></td></tr>`).join("");
    return head + reviewCard(d) + analysisCard(d) + `
      <div class="grid g2 contest-grid" style="margin-top:14px">
        <div class="card contest-card"><h3>📈 分数走势 <small>我的分数 · 大比平均分 · 最高分（满分 100，y 轴从 ${lo} 起）</small></h3>${scoreChart}</div>
        <div class="card contest-card"><h3>🎯 各模块正确率走势 <small>点图例看各条线；悬停看每一季</small></h3>${accChart}</div>
      </div>
      ${moduleGrid(d)}
      <div class="card contest-card"><h3>🏯 历次大比 <small>排名、大比平均分、已击败照抄粉笔报告；对错题数来自复盘</small></h3>
        <div class="tbl-wrap"><table class="mk-table"><thead><tr><th>季</th><th>日期</th><th>我的分数</th><th>大比平均</th><th>最高分</th><th>已击败</th><th>排名</th><th>答对</th><th>用时</th><th></th></tr></thead>
        <tbody>${rows}</tbody></table></div></div>
      ${marksCard(d)}
      ${form(d)}
      <p class="small muted">模考流程：① 到「${esc(NAV("skeleton"))} → 📖 经卷 · 题库」最下面「📥 导入真题」导入模考 PDF（自动拆成板块复盘、入题库，并给演武 · 历练记记 120 分钟）→ ② 在这里导入答题卡截图（对错）→ ③ 录成绩单 → ④ 「📜 大比复盘」逐题复盘 → ⑤ 点「🧙 师傅大比分析」→ ⑥ 去心魔录斩错题。</p>`;
  }

  async function loadConv(season) {
    if (season == null || CONV[season]) return;
    try { CONV[season] = (await api("/api/mock/analysis", { season })).conv; } catch (e) { CONV[season] = []; }
  }
  async function ask(body) {
    AN_BUSY = true; rerender();
    try { CONV[AN] = (await api("/api/mock/analyze", { season: AN, ...body })).conv; }
    catch (e) { showError(e); }
    AN_BUSY = false; rerender();
    const last = [...document.querySelectorAll(".an-msg")].pop();
    if (last) last.scrollIntoView({ block: "start" });
  }
  function bindReport() {
    const btn = document.getElementById("rpScan");
    if (!btn) return;
    btn.onclick = async () => {
      const files = [...document.getElementById("rpFiles").files], text = document.getElementById("rpText").value;
      if (!files.length && !text.trim()) return toast("先选成绩截图，或者粘贴报告文字");
      btn.disabled = true; btn.textContent = "识别中…";
      try {
        const images = await Promise.all(files.map((f) => new Promise((ok, bad) => { const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = bad; r.readAsDataURL(f); })));
        const r = await api("/api/mock/report/scan", { images, text });
        const f = r.fields || {};
        const sel = document.getElementById("mkSeason");
        if (f.season && [...sel.options].some((o) => o.value === String(f.season))) sel.value = String(f.season);
        const set = (id, v) => { if (v != null && v !== "") document.getElementById(id).value = v; };
        set("mkScore", f.score); set("mkAvg", f.avg); set("mkTop", f.top); set("mkBeat", f.beat);
        set("mkRank", f.rank); set("mkPeople", f.people); set("mkDate", f.date);
        let mins = 0;
        for (const [m, v] of Object.entries(r.modules || {})) {
          const inp = document.querySelector(`[data-mk-minutes="${m}"]`);
          if (inp && v.minutes != null) { inp.value = v.minutes; mins++; }
        }
        if (mins) document.getElementById("mkModsFold").open = true;
        REPORT = { season: sel.value, modules: r.modules || {}, sub: r.sub || {} };
        const got = ["score:得分", "avg:平均分", "top:最高分", "beat:已击败", "rank:排名", "date:日期"].filter((x) => f[x.split(":")[0]] != null).map((x) => x.split(":")[1]);
        const mods = Object.entries(r.modules || {}).map(([m, v]) => `${esc(m)} ${v.ok}/${v.total}${v.minutes != null ? ` · ${v.minutes}分` : ""}`).join("；");
        document.getElementById("rpResult").innerHTML = `✅ 认出（${esc(r.engine)}）：${got.join("、") || "（成绩数字没认出）"}${f.season ? ` · 第 ${f.season} 季` : ""}<br>${mods || "（各模块没认出）"}
          <br><span class="muted">已填进下面的表，核对一下再点「保存这一季」。各模块答对数会一起存（没导入答题卡截图时用它算正确率）。</span>`;
      } catch (e) { showError(e); }
      btn.disabled = false; btn.textContent = "识别并填入";
    };
  }
  function bindExtra() {
    bindReport();
    const an = document.getElementById("anSeason");
    if (an) an.onchange = async () => { AN = Number(an.value); await loadConv(AN); rerender(); };
    const go = document.getElementById("anGo");
    if (go) go.onclick = () => {
      if ((CONV[AN] || []).length && !confirm("重新分析会清掉这一季之前的考情对话，确定吗？")) return;
      setFold(false);
      ask({ fresh: true });
    };
    const fb = document.getElementById("anFold");
    if (fb) fb.onclick = () => { setFold(!AN_FOLD); rerender(); };
    const send = document.getElementById("anSend"), ta = document.getElementById("anText");
    if (send) {
      const fire = () => { const t = ta.value.trim(); if (t) ask({ text: t }); };
      send.onclick = fire;
      ta.onkeydown = (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); fire(); } };
    }
    const ms = document.getElementById("mkMarksSeason");
    if (ms) ms.onchange = () => { MK_SEASON = Number(ms.value); rerender(); };
    const scan = document.getElementById("mkMarksScan");
    if (scan) scan.onclick = async () => {
      const files = [...document.getElementById("mkMarksFiles").files];
      if (!files.length) return toast("先选答题卡截图");
      scan.disabled = true; scan.textContent = "识别中…";
      try {
        const images = await Promise.all(files.map((f) => new Promise((ok, bad) => { const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = bad; r.readAsDataURL(f); })));
        MK = await api("/api/mock/marks/scan", { season: MK_SEASON, images });
        rerender();
        document.getElementById("mkMarksCard")?.scrollIntoView({ block: "start" });
      } catch (e) { showError(e); scan.disabled = false; scan.textContent = "识别"; }
    };
    document.querySelectorAll("[data-mkdot]").forEach((el) => (el.onclick = () => {
      const n = el.dataset.mkdot;
      MK.marks[n] = MK.marks[n] === "ok" ? "bad" : "ok";
      rerender();
      document.getElementById("mkMarksCard")?.scrollIntoView({ block: "start" });
    }));
    const save = document.getElementById("mkMarksSave");
    if (save) save.onclick = async () => {
      try {
        const r = await api("/api/mock/marks/save", { season: MK.season, marks: MK.marks });
        MOCK = r.summary; MK = null;
        toast(`第 ${MK_SEASON} 季的对错已写进复盘（改了 ${r.changed} 题）`);
        await refresh(); rerender();
      } catch (e) { showError(e); }
    };
  }
  function bind() {
    bindCharts();
    bindExtra();
    bindReview();
    // 点图例：隐藏 / 显示那条线（颜色跟着线走，不重排）
    document.querySelectorAll(".chart .lg").forEach((lg, k) => (lg.onclick = () => {
      const chart = lg.closest(".chart");
      const idx = [...chart.querySelectorAll(".lg")].indexOf(lg);
      lg.classList.toggle("off");
      const paths = chart.querySelectorAll("svg path.cl");
      const p = paths[idx]; if (!p) return;
      const on = !lg.classList.contains("off");
      let n = p.nextElementSibling;
      p.style.display = on ? "" : "none";
      while (n && n.tagName === "circle") { n.style.display = on ? "" : "none"; n = n.nextElementSibling; }
    }));
    const pick = document.getElementById("mkPick");
    if (pick) pick.onchange = () => { PICK = pick.value; rerender(); };
    document.querySelectorAll("[data-mk-edit]").forEach((b) => (b.onclick = () => {
      EDIT = b.dataset.mkEdit; rerender();
      document.getElementById("mkForm")?.scrollIntoView({ behavior: "smooth", block: "center" });
    }));
    const sel = document.getElementById("mkSeason");
    if (sel) sel.onchange = () => { EDIT = sel.value; rerender(); };
    const save = document.getElementById("mkSave");
    if (save) save.onclick = async () => {
      const g = (id) => document.getElementById(id).value;
      const pickMods = (key) => Object.fromEntries([...document.querySelectorAll(`[data-mk-${key}]`)].map((i) => [i.getAttribute(`data-mk-${key}`), i.value]));
      try {
        const r = await api("/api/mock/save", { season: g("mkSeason"), date: g("mkDate"), score: g("mkScore"), avg: g("mkAvg"), top: g("mkTop"),
          beat: g("mkBeat"), rank: g("mkRank"), people: g("mkPeople"), minutes: pickMods("minutes"), scores: pickMods("score"),
          report: REPORT && String(REPORT.season) === String(g("mkSeason")) ? REPORT : null });
        REPORT = null;
        MOCK = r.summary; EDIT = g("mkSeason");
        toast(`第 ${EDIT} 季成绩单已保存`);
        rerender();
        const ss = MOCK.seasons, k = ss.findIndex((x) => String(x.season) === String(EDIT));
        if (window.CEREMONY && k >= 0 && ss[k].score != null && g("mkScore") !== "") {
          const prev = ss.slice(0, k).reverse().find((x) => x.score != null);
          await CEREMONY.contest(ss[k], prev);          // 大比出成绩的大典画面，关掉后再弹修为、境界
        }
        handleEvents(r.events);
      } catch (e) { showError(e); }
    };
  }
  function rerender() {
    const v = document.getElementById("view");
    if (!MOCK || !v) return;
    v.innerHTML = html(MOCK);
    bind();
  }
  async function render(v) {
    MOCK = await api("/api/mock");
    if (AN == null && MOCK.seasons.length) AN = MOCK.seasons[MOCK.seasons.length - 1].season;
    await loadConv(AN);
    v.innerHTML = html(MOCK);
    bind();
  }
  window.CONTEST = { render };
})();
