/* 🔮 天机简报：政治理论的时政学习（数据见 rpg/tianji.py）。
   首页两栏：
   - 📰 月半时政：按时间顺序一期一本，封面学《求是》杂志（红色刊名、期号、会动的日出 / 祥云 / 飞鸽、封面要目）；
   - 📜 专题时政：按专题分类（两会·政府报告、经济、农业、外交、科技…），每份是一页会动的红头文件（红色文头、文号、红线五角星、盖章）。
   右上「＋ 导入 PDF」（或把 PDF 拖进来）：小黑月半时政的讲义直接拆成可学的一期。
   点开一期，四步学：
   - 📖 研读：一条条新闻（专题是每道母题的原文速递），消化清单要考的字句标红；读完点「✓ 读完了」；
   - ✍ 消化：消化清单的挖空，点一下揭开（算记得），再点一下标成没记住（红），没记住的可以一键刻成玉简（填空）；
   - 📝 精卷：小黑金卷 / 母题，点选项就判，出答案和解析，能跳回原文；
   - 📊 小结：进度、错题、没记住的空。
   计时：开着这一期、5 分钟内动过就算学习时间（研读 / 消化算复习，精卷算做题，都记在政治理论）。 */
(function () {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const local = ["127.0.0.1", "localhost", "[::1]"].includes(location.hostname);
  const CN = "〇一二三四五六七八九十";
  const cn = (n) => (n <= 10 ? CN[n] : n < 20 ? "十" + CN[n - 10] : CN[Math.floor(n / 10)] + "十" + (n % 10 ? CN[n % 10] : ""));
  const store = {
    get(k, d) { try { return localStorage.getItem("tianji." + k) || d; } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem("tianji." + k, v); } catch (e) { /* 只管这一次 */ } },
  };
  let LIST = null;
  let TAB = store.get("tab", "month");
  let CUR = null;            // {kind, id, data, progress, stat}
  let MODE = "read";
  let NEWS = 0;              // 研读看到第几条
  let ONLY_FORGOT = false, ONLY_WRONG = false;
  let REDO = new Set();      // 精卷里点了「重做这题」的题
  let LEFT = store.get("left", "toc");   // 研读页左栏：toc 目录 / ask 问师傅
  let ASKING = false;
  let lastAct = 0;
  let ROOT = null;
  const act = () => (lastAct = Date.now());
  ["click", "scroll", "keydown", "touchstart"].forEach((e) => addEventListener(e, () => { if (CUR && VIEW === "tianji") act(); }, { passive: true, capture: true }));

  // ---------------------------------------------------------------- 封面：求是杂志（月半时政）
  function qiushi(it, i) {
    const s = it.stat, issue = ((it.month || 1) - 1) * 2 + (it.half === "下" ? 2 : 1);
    const heads = (it.heads || []).slice(0, 3);
    return `<a class="tj-cover tj-qs" data-open="month|${esc(it.id)}" style="--d:${(i % 6) * 0.7}s" title="${esc(it.title)}">
      <div class="tj-qs-top"><b class="tj-qs-name">月半时政</b>
        <div class="tj-qs-meta"><span>${it.year || ""}</span><span>第${issue}期</span><small>YUEBAN SHIZHENG</small></div></div>
      <div class="tj-qs-sub">${esc(cn(it.month || 0))}月 · ${esc(it.half || "")}半月</div>
      <svg class="tj-qs-art" viewBox="0 0 200 110" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
        <defs><radialGradient id="tjSun${i}"><stop offset="0" stop-color="#ffe9a8"/><stop offset=".55" stop-color="#ffb347"/><stop offset="1" stop-color="#e2492f"/></radialGradient>
          <linearGradient id="tjSky${i}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fbe3c4"/><stop offset="1" stop-color="#f6c79a"/></linearGradient></defs>
        <rect width="200" height="110" fill="url(#tjSky${i})"/>
        <g class="tj-rays" style="transform-origin:100px 78px">${Array.from({ length: 12 }, (_, k) => `<path d="M100 78 L${100 + 140 * Math.cos(k * Math.PI / 6)} ${78 + 140 * Math.sin(k * Math.PI / 6)} L${100 + 140 * Math.cos(k * Math.PI / 6 + .12)} ${78 + 140 * Math.sin(k * Math.PI / 6 + .12)}Z" fill="#fff4d6" opacity=".45"/>`).join("")}</g>
        <circle class="tj-sun" cx="100" cy="78" r="26" fill="url(#tjSun${i})"/>
        <g class="tj-cloud c1"><ellipse cx="40" cy="40" rx="22" ry="6" fill="#fff" opacity=".8"/><ellipse cx="52" cy="36" rx="12" ry="6" fill="#fff" opacity=".8"/></g>
        <g class="tj-cloud c2"><ellipse cx="160" cy="28" rx="20" ry="5" fill="#fff" opacity=".7"/><ellipse cx="150" cy="25" rx="10" ry="5" fill="#fff" opacity=".7"/></g>
        <path d="M0 92 L20 84 L34 88 L50 76 L70 86 L88 80 L100 84 L118 74 L136 84 L154 78 L172 86 L200 80 L200 110 L0 110Z" fill="#a8322a" opacity=".85"/>
        <path d="M0 98 Q50 90 100 98 T200 96 L200 110 L0 110Z" fill="#7d1f1a"/>
        <g class="tj-dove d1"><path d="M0 0 q6 -6 12 0 q-6 -3 -12 0z M6 0 q6 -6 12 0" fill="none" stroke="#fff" stroke-width="1.6"/></g>
        <g class="tj-dove d2"><path d="M0 0 q5 -5 10 0 M5 0 q5 -5 10 0" fill="none" stroke="#fff" stroke-width="1.4"/></g>
        <g class="tj-flag" transform="translate(150 46)"><line x1="0" y1="0" x2="0" y2="40" stroke="#5a1a14" stroke-width="1.5"/>
          <path class="tj-flag-cloth" d="M0 0 h24 v15 h-24z" fill="#de2910"/><path d="M5 4 l1 2.4 2.5 .1 -2 1.5 .8 2.4 -2.3 -1.4 -2.1 1.4 .7 -2.4 -2 -1.5 2.5 -.1z" fill="#ffde00"/></g>
      </svg>
      <ul class="tj-qs-lines">${heads.map((h) => `<li>${esc(h)}</li>`).join("") || "<li>本期要目</li>"}</ul>
      ${progBar(s)}</a>`;
  }
  // ---------------------------------------------------------------- 封面：红头文件（专题时政）
  function hongtou(it, i, n) {
    const s = it.stat;
    return `<a class="tj-cover tj-hd" data-open="topic|${esc(it.id)}" style="--d:${(i % 5) * 0.9}s" title="${esc(it.title)}">
      <div class="tj-hd-org">天机简报专题文件</div>
      <div class="tj-hd-no">天机〔${it.year || ""}〕${n}号</div>
      <div class="tj-hd-rule"><i></i><b>★</b><i></i></div>
      <div class="tj-hd-title">关于学习${esc(it.title)}的专题</div>
      <div class="tj-hd-text"><i style="width:92%"></i><i style="width:100%"></i><i style="width:78%"></i><i style="width:96%"></i><i style="width:60%"></i></div>
      <svg class="tj-hd-seal" viewBox="0 0 100 100" aria-hidden="true"><circle cx="50" cy="50" r="44" fill="none" stroke="#d62a1e" stroke-width="5"/>
        <path id="tjArc${i}" d="M18 52 A32 32 0 1 1 82 52" fill="none"/><text font-size="12" fill="#d62a1e" font-weight="700" letter-spacing="2"><textPath href="#tjArc${i}" startOffset="50%" text-anchor="middle">天机简报编纂处</textPath></text>
        <path d="M50 34 l4.7 9.6 10.6 1.5 -7.7 7.5 1.8 10.5 -9.4 -5 -9.4 5 1.8 -10.5 -7.7 -7.5 10.6 -1.5z" fill="#d62a1e"/></svg>
      <div class="tj-hd-cat">${esc(it.category || "其他")}</div>
      ${progBar(s)}</a>`;
  }
  function progBar(s) {
    if (!s) return "";
    const p = Math.round((s.frac || 0) * 100);
    return `<div class="tj-prog"><div class="tj-prog-bar"><i style="width:${p}%"></i></div>
      <div class="tj-prog-t"><span>读 ${s.read}/${s.news}</span><span>空 ${s.seen}/${s.blanks}</span><span>题 ${s.done}/${s.questions}</span></div></div>`;
  }

  // ---------------------------------------------------------------- 首页
  function hubHtml() {
    const L = LIST || { month: [], topic: [] };
    let body = "";
    if (TAB === "month") {
      const years = {};
      L.month.forEach((it) => (years[it.year] = years[it.year] || []).push(it));
      const ys = Object.keys(years).sort((a, b) => b - a);
      body = ys.map((y) => {
        // 时间顺序：从这一年最早导入的那一期排到最晚（中间没导入的留一个空位，点了就导入）
        const have = {};
        years[y].forEach((it) => (have[(it.month - 1) * 2 + (it.half === "下" ? 1 : 0)] = it));
        const ks = Object.keys(have).map(Number);
        const slots = [];
        for (let k = Math.min(...ks); k <= Math.max(...ks); k++) slots.push(k);
        return `<div class="tj-year"><h3>${y} 年 <small>${years[y].length} 期</small></h3>
          <div class="tj-grid">${slots.map((k, i) => have[k] ? qiushi(have[k], i)
            : `<a class="tj-cover tj-empty" data-import="1"><b>${cn(Math.floor(k / 2) + 1)}月${k % 2 ? "下" : "上"}</b><span>还没导入<br>点这里导入 PDF</span></a>`).join("")}</div></div>`;
      }).join("") || emptyHtml("月半时政");
    } else {
      const by = {};
      L.topic.forEach((it) => (by[it.category || "其他"] = by[it.category || "其他"] || []).push(it));
      const cats = (L.categories || []).filter((c) => by[c]);
      let n = 0;
      body = cats.map((c) => `<div class="tj-year"><h3>${esc(c)} <small>${by[c].length} 份</small></h3>
        <div class="tj-grid">${by[c].map((it, i) => hongtou(it, n + i, ++n)).join("")}</div></div>`).join("") || emptyHtml("专题时政");
    }
    return `<div class="tj-hub">
      <div class="card tj-head"><div><h2>${esc(W("nav.tianji"))}</h2><div class="muted small">政治理论 · 时政。月半时政按时间一期一期学，专题时政按专题归档；每一期都是 研读 → 消化 → 精卷。</div></div>
        <span class="spacer"></span>
        <div class="tj-tabs"><a data-tab="month" class="${TAB === "month" ? "on" : ""}">📰 月半时政 <small>${L.month.length}</small></a><a data-tab="topic" class="${TAB === "topic" ? "on" : ""}">📜 专题时政 <small>${L.topic.length}</small></a></div>
        <button class="primary" id="tjImport">＋ 导入 PDF</button>
        <input type="file" id="tjFile" accept="application/pdf,.pdf" multiple hidden></div>
      <div class="tj-drop" id="tjDrop" hidden>松手导入 PDF</div>
      ${body}</div>`;
  }
  function emptyHtml(name) {
    return `<div class="card tj-blank"><div class="tj-blank-ico">${TAB === "month" ? "📰" : "📜"}</div>
      <h3>还没有${name}</h3>
      <p class="muted">点右上「＋ 导入 PDF」，或者把小黑月半时政班的 PDF 拖进这个页面。<br>
      程序会自动拆成「课程讲义 / 消化清单 / 精卷 / 答案与解析」：讲义一条条读，消化清单的空自动对出答案，精卷点选项就判。</p>
      <button class="primary" data-import="1">＋ 导入 PDF</button></div>`;
  }

  async function load() { LIST = await api("/api/tianji"); }
  async function render(v) {
    ROOT = v;
    if (CUR) return renderIssue();
    try { await load(); } catch (e) { showError(e); LIST = { month: [], topic: [] }; }
    v.innerHTML = hubHtml();
    bindHub();
  }
  function bindHub() {
    const v = ROOT;
    v.querySelectorAll("[data-tab]").forEach((a) => (a.onclick = () => { TAB = a.dataset.tab; store.set("tab", TAB); v.innerHTML = hubHtml(); bindHub(); }));
    const file = v.querySelector("#tjFile");
    v.querySelectorAll("#tjImport, [data-import]").forEach((b) => (b.onclick = (e) => { e.preventDefault(); file.click(); }));
    file.onchange = () => importFiles([...file.files]);
    v.querySelectorAll("[data-open]").forEach((a) => (a.onclick = () => { const [k, id] = a.dataset.open.split("|"); open(k, id); }));
    const drop = v.querySelector("#tjDrop");
    const hub = v.querySelector(".tj-hub");
    hub.ondragover = (e) => { e.preventDefault(); drop.hidden = false; };
    hub.ondragleave = (e) => { if (!hub.contains(e.relatedTarget)) drop.hidden = true; };
    hub.ondrop = (e) => { e.preventDefault(); drop.hidden = true; importFiles([...e.dataTransfer.files].filter((f) => /\.pdf$/i.test(f.name) || f.type === "application/pdf")); };
  }
  async function importFiles(files) {
    if (!files.length) return;
    for (const f of files) {
      const t = document.createElement("div");
      t.className = "toast"; t.innerHTML = `📥 正在拆《${esc(f.name)}》…`;
      document.getElementById("toasts").appendChild(t);
      try {
        const data = await new Promise((ok, bad) => { const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = () => bad(new Error("读不了这个文件")); r.readAsDataURL(f); });
        const r = await api("/api/tianji/import", { name: f.name, data });
        t.innerHTML = `✅ 导入了「${esc(r.title)}」（${r.kind === "month" ? "月半时政" : "专题时政"}）<div class="small muted">${r.news} 条${r.kind === "month" ? "新闻" : "原文"} · 消化清单 ${r.cloze} 段 ${r.found}/${r.blanks} 个空对出答案 · 精卷 ${r.questions} 题（${r.answered} 题有答案）</div>`;
        TAB = r.kind; store.set("tab", TAB);
      } catch (e) { t.className = "toast err"; t.innerHTML = `⚠ 《${esc(f.name)}》没导进去：${esc(e.message || e)}`; }
      setTimeout(() => t.remove(), 12000);
    }
    if (VIEW === "tianji" && !CUR) render(ROOT);
  }

  // ---------------------------------------------------------------- 一期
  async function open(kind, id, mode) {
    try {
      const r = await api("/api/tianji/get", { kind, id });
      CUR = Object.assign({ kind, id }, r);
      MODE = mode || store.get("mode", "read");
      NEWS = 0; REDO = new Set(); act();
      renderIssue();
      window.scrollTo(0, 0);
    } catch (e) { showError(e); }
  }
  function close() { CUR = null; if (VIEW === "tianji") render(ROOT); }

  function answersOf(i) {      // 第 i 条新闻里消化清单要考的字句（按顺序）
    const out = [];
    CUR.data.cloze.forEach((c) => {
      if (c.news !== i) return;
      c.parts.forEach((p, k) => { if (p.a) { const prev = c.parts[k - 1]; out.push({ a: p.a, pre: prev && prev.t ? prev.t.slice(-4) : "" }); } });
    });
    return out;
  }
  function highlight(paras, ans) {
    let k = 0;
    return paras.map((p) => {
      let html = "", pos = 0;
      while (k < ans.length) {
        const { a, pre } = ans[k];
        let j = pre ? p.indexOf(pre + a, pos) : -1;          // 带上空前面的几个字找，免得标到前文里同样的词
        j = j >= 0 ? j + pre.length : p.indexOf(a, pos);
        if (j < 0) break;
        html += esc(p.slice(pos, j)) + `<mark class="tj-key">${esc(a)}</mark>`;
        pos = j + a.length; k++;
      }
      return `<p>${html + esc(p.slice(pos))}</p>`;
    }).join("");
  }

  function issueHead() {
    const d = CUR.data, s = CUR.stat;
    const tabs = [["read", "📖 研读", `${s.read}/${s.news}`], ["cloze", "✍ 消化", `${s.seen}/${s.blanks}`], ["quiz", "📝 精卷", `${s.done}/${s.questions}`], ["sum", "📊 小结", Math.round(s.frac * 100) + "%"]];
    return `<div class="card tj-ihead ${CUR.kind}">
      <button class="ghost" id="tjBack">← ${esc(W("nav.tianji").replace(/^\S+\s/, ""))}</button>
      <div class="tj-ititle"><b>${esc(CUR.kind === "month" ? `${d.title} · 月半时政` : d.title)}</b><small class="muted">${esc(d.overview || "")}</small></div>
      <span class="spacer"></span>
      ${CUR.kind === "topic" ? `<select id="tjCat" title="归到哪个专题">${(LIST?.categories || [d.category]).map((c) => `<option ${c === d.category ? "selected" : ""}>${esc(c)}</option>`).join("")}</select>` : ""}
      ${d.pdf ? `<button class="ghost small" id="tjNote" title="把这一期的讲义原文开成一本手札，直接用笔勾画、写批注（自动保存）">✏ 勾画笔记</button>
        <button class="ghost small" id="tjPdf" title="看原来的 PDF">📄 原文</button>` : ""}
      <button class="ghost small" id="tjDel" title="从天机简报里删掉这一期（学习进度一起删）">🗑</button>
      <div class="tj-itabs">${tabs.map(([k, n, c]) => `<a data-mode="${k}" class="${MODE === k ? "on" : ""}">${n}<small>${c}</small></a>`).join("")}</div></div>`;
  }

  function readHtml() {
    const d = CUR.data, pr = CUR.progress;
    if (!d.news.length) return `<div class="card muted">这一期没有讲义，直接去「✍ 消化」或「📝 精卷」。</div>`;
    NEWS = Math.max(0, Math.min(NEWS, d.news.length - 1));
    const n = d.news[NEWS], read = pr.read.includes(NEWS);
    let lastGroup = null;
    const toc = d.news.map((x, i) => {
      const g = x.group && x.group !== lastGroup ? `<div class="tj-toc-g">${esc(x.group)}</div>` : "";
      lastGroup = x.group;
      return `${g}<a data-news="${i}" class="${i === NEWS ? "on" : ""} ${pr.read.includes(i) ? "done" : ""}">
        <span class="tj-toc-n">${pr.read.includes(i) ? "✓" : CUR.kind === "month" ? x.no : i + 1}</span>
        <span>${x.stars ? `<em class="tj-star">${"★".repeat(x.stars)}</em>` : ""}${esc(x.title)}</span></a>`;
    }).join("");
    const qs = n.qs.map((k) => d.questions[k]).filter(Boolean);
    const leftTabs = `<div class="tj-ltabs"><a data-left="toc" class="${LEFT === "toc" ? "on" : ""}">📑 目录</a><a data-left="ask" class="${LEFT === "ask" ? "on" : ""}">🧙 问师傅</a></div>`;
    return `<div class="tj-read ${LEFT === "ask" ? "asking" : ""}">
      <aside class="card tj-toc">${leftTabs}${LEFT === "ask" ? askHtml(n) : `<div class="tj-toc-list">${toc}</div>`}</aside>
      <article class="card tj-news">
        <div class="tj-news-head">${n.stars ? `<span class="tj-star big">${"★".repeat(n.stars)}</span>` : ""}${n.tag && n.tag !== n.group ? `<span class="tag">${esc(n.tag)}</span>` : ""}
          ${n.group ? `<span class="tag">${esc(n.group)}</span>` : ""}<span class="faint small">第 ${NEWS + 1} / ${d.news.length} 条</span></div>
        <h2>${esc(CUR.kind === "month" ? n.title : (qs[0] ? "原文速递 · 第 " + qs[0].no + " 题" : n.title))}</h2>
        ${CUR.kind === "topic" && qs[0] ? `<div class="tj-news-q">${esc(qs[0].stem)}</div>` : ""}
        <div class="tj-news-body">${highlight(n.paras, answersOf(NEWS))}</div>
        <div class="faint small tj-key-tip"><mark class="tj-key">标红</mark> 的是消化清单要挖的空</div>
        <div class="row tj-news-foot">
          <button class="${read ? "ghost" : "primary"}" id="tjRead">${read ? "↺ 标成没读" : "✓ 读完了"}</button>
          ${qs.length ? `<button class="ghost" id="tjToQuiz">📝 本条 ${qs.length} 道题 →</button>` : ""}
          <span class="spacer"></span>
          <button class="ghost" id="tjPrev" ${NEWS ? "" : "disabled"}>← 上一条</button><button class="ghost" id="tjNext" ${NEWS < d.news.length - 1 ? "" : "disabled"}>下一条 →</button></div>
      </article></div>`;
  }

  // 🧙 问师傅：针对正在读的这一条。「总结怎么记」重点讲红字；也可以打字问不懂的地方（可追问），问过的都留着
  function askHtml(n) {
    const saved = ((CUR.progress.ask || {})[String(NEWS)]) || [];
    const md = (s) => (window.NOTES ? NOTES.mdRender(s, {}) : esc(s).replace(/\n/g, "<br>"));
    return `<div class="tj-ask">
      <div class="tj-ask-for">问的是：<b>${esc(n.title)}</b></div>
      <button class="primary small tj-ask-mem" id="tjAskMem" ${ASKING ? "disabled" : ""}>🧠 总结这一条怎么记（红字）</button>
      <div class="tj-ask-msgs" id="tjAskMsgs">${saved.map((x) => `<div class="tj-am me">${esc(x.q)}<small>${esc(x.t || "")}</small></div><div class="tj-am ai">${md(x.a)}</div>`).join("")
        || '<div class="muted small tj-ask-empty">点上面的按钮，师傅把这一条理一遍、教你记红字；看不懂的地方也可以直接在下面问。</div>'}
        ${ASKING ? '<div class="tj-am ai faint">师傅思索中…</div>' : ""}</div>
      <div class="tj-ask-in"><textarea id="tjAskIn" rows="2" placeholder="哪里不懂？比如：“四个面向”是哪四个？（回车发送，Shift+回车换行）"></textarea>
        <button class="small" id="tjAskGo" ${ASKING ? "disabled" : ""}>问</button></div></div>`;
  }
  async function ask(question) {
    if (ASKING) return;
    const saved = ((CUR.progress.ask || {})[String(NEWS)]) || [];
    const history = [];
    saved.slice(-3).forEach((x) => { history.push({ role: "user", content: x.q }, { role: "assistant", content: x.a }); });
    ASKING = true; act();
    const idx = NEWS;
    keepAsk();
    try {
      const r = await api("/api/tianji/ask", { kind: CUR.kind, id: CUR.id, news: idx, question, history: question ? history : [] });
      CUR.progress.ask = CUR.progress.ask || {};
      CUR.progress.ask[String(idx)] = r.saved;
    } catch (e) { showError(e); }
    ASKING = false;
    keepAsk(true);
  }
  function keepAsk(bottom) {        // 只重画左栏，正文不动
    const box = ROOT && ROOT.querySelector(".tj-toc");
    if (!box || MODE !== "read" || LEFT !== "ask") return;
    const n = CUR.data.news[NEWS];
    box.innerHTML = box.querySelector(".tj-ltabs").outerHTML + askHtml(n);
    bindLeft();
    const m = document.getElementById("tjAskMsgs"); if (m) m.scrollTop = bottom ? m.scrollHeight : m.scrollHeight;
  }
  function bindLeft() {
    ROOT.querySelectorAll("[data-left]").forEach((a) => (a.onclick = () => { LEFT = a.dataset.left; store.set("left", LEFT); keepScroll(renderIssue); }));
    const mem = document.getElementById("tjAskMem"); if (mem) mem.onclick = () => ask("");
    const goBtn = document.getElementById("tjAskGo"), inp = document.getElementById("tjAskIn");
    const send = () => { const q = inp.value.trim(); if (q) ask(q); };
    if (goBtn) goBtn.onclick = send;
    if (inp) inp.onkeydown = (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); } };
    ROOT.querySelectorAll(".tj-am.ai img").forEach((im) => (im.onclick = () => window.zoomImg && zoomImg(im.src)));
  }

  function clozeHtml() {
    const d = CUR.data, pr = CUR.progress, s = CUR.stat;
    if (!d.cloze.length) return `<div class="card muted">这一期没有消化清单。</div>`;
    const items = d.cloze.map((c, i) => {
      const keys = c.parts.map((p, k) => (p.a ? `${i}-${k}` : null)).filter(Boolean);
      if (ONLY_FORGOT && !keys.some((k) => pr.cloze[k] === 0)) return "";
      const body = c.parts.map((p, k) => {
        if (p.br) return "<br>";
        if (p.t != null) return esc(p.t);
        if (!p.a) return `<span class="tj-b nil" title="没在讲义里找到这个空的答案">（见讲义）</span>`;
        const key = `${i}-${k}`, st = pr.cloze[key];
        const cls = st === 1 ? "ok" : st === 0 ? "no" : "hid";
        return `<button class="tj-b ${cls}" data-b="${key}" style="--w:${Math.max(2, [...p.a].length)}em">${esc(p.a)}</button>`;
      }).join("");
      let g = "";
      if (CUR.kind === "topic" && c.title !== (d.cloze[i - 1] || {}).title) g = `<h3 class="tj-cl-g">${esc(c.title)}</h3>`;
      return `${g}<div class="card tj-cl">${CUR.kind === "month" ? `<div class="tj-cl-h">${c.no}. ${esc(c.title)}</div>` : `<span class="tj-cl-n">${c.no}</span>`}<div class="tj-cl-body">${body}</div></div>`;
    }).join("");
    const left = s.forgot - ((pr.carded || []).filter((k) => pr.cloze[k] === 0).length);
    return `<div class="card tj-bar">
        <span>点空格揭开 = 记得 <b class="tj-b ok demo">✓</b>；再点一下 = 没记住 <b class="tj-b no demo">✗</b></span><span class="spacer"></span>
        <span class="small muted">已过 ${s.seen}/${s.blanks} · 没记住 <b style="color:var(--red)">${s.forgot}</b></span>
        <label class="small"><input type="checkbox" id="tjOnlyNo" ${ONLY_FORGOT ? "checked" : ""}> 只看没记住的</label>
        <button class="ghost small" id="tjClozeReset" title="全部重新遮住，再过一遍">↺ 重练</button>
        <button class="small ${left > 0 ? "primary" : "ghost"}" id="tjCards" ${left > 0 ? "" : "disabled"} title="没记住的空做成填空玉简，放进 政治理论::天机简报 简匣">🀄 没记住的刻成${esc(W("yj"))}${left > 0 ? ` (${left})` : ""}</button></div>
      ${items || '<div class="card muted">没有没记住的空 👍</div>'}`;
  }

  function quizHtml() {
    const d = CUR.data, pr = CUR.progress, s = CUR.stat;
    if (!d.questions.length) return `<div class="card muted">这一期没有精卷。</div>`;
    let lastGroup = null;
    const cards = d.questions.map((q) => {
      const r = pr.quiz[String(q.key)];
      const fresh = !r || REDO.has(q.key);
      if (ONLY_WRONG && (!r || r.ok)) return "";
      const g = q.group && q.group !== lastGroup ? `<h3 class="tj-cl-g">${esc(q.group)}</h3>` : "";
      lastGroup = q.group;
      const opts = ["A", "B", "C", "D"].map((k) => {
        let cls = "";
        if (!fresh) cls = k === q.answer ? "right" : k === r.a ? "wrong" : "dim";
        return `<button class="tj-opt ${cls}" data-q="${q.key}" data-c="${k}" ${fresh ? "" : "disabled"}><b>${k}</b><span>${esc(q.opts[k] || "")}</span></button>`;
      }).join("");
      const news = q.news != null ? d.news[q.news] : null;
      const ana = fresh ? "" : `<div class="tj-ana ${r.ok ? "ok" : "no"}"><div class="tj-ana-h">${r.ok ? "✓ 答对了" : `✗ 你选 ${r.a}，正确答案 ${q.answer || "（没找到）"}`}
          <span class="spacer"></span>${news ? `<a data-goread="${q.news}">📖 回原文</a>` : ""}<a data-redo="${q.key}">↺ 重做这题</a></div>
        <div class="tj-ana-b">${esc(q.analysis || "（没有解析）")}</div></div>`;
      return `${g}<div class="card tj-q ${fresh ? "" : r.ok ? "is-ok" : "is-no"}" id="tjq${q.key}">
        <div class="tj-q-h"><span class="tj-q-n">${q.no}</span><span class="tag">${esc(q.kind)}</span>${news && CUR.kind === "month" ? `<span class="faint small">${esc(news.title)}</span>` : ""}</div>
        <div class="tj-q-stem">${esc(q.stem)}</div>
        ${q.stmts.length ? `<div class="tj-q-stmts">${q.stmts.map((x) => `<div>${esc(x)}</div>`).join("")}</div>` : ""}
        <div class="tj-opts">${opts}</div>${ana}</div>`;
    }).join("");
    return `<div class="card tj-bar"><span>点选项就判，判完看解析。</span><span class="spacer"></span>
        <span class="small muted">已做 ${s.done}/${s.questions} · 对 <b style="color:var(--green)">${s.right}</b>${s.done ? ` · 正确率 ${Math.round(s.right / s.done * 100)}%` : ""}</span>
        <label class="small"><input type="checkbox" id="tjOnlyWrong" ${ONLY_WRONG ? "checked" : ""}> 只看错题</label>
        <button class="ghost small" id="tjQuizReset">↺ 整卷重做</button></div>${cards || '<div class="card muted">没有错题 👍</div>'}`;
  }

  function sumHtml() {
    const d = CUR.data, pr = CUR.progress, s = CUR.stat;
    const ring = (frac, label, sub, color) => `<div class="tj-ring" style="--p:${Math.round(frac * 360)}deg;--c:${color}"><div><b>${Math.round(frac * 100)}%</b><span>${label}</span><small>${sub}</small></div></div>`;
    const wrong = d.questions.filter((q) => pr.quiz[String(q.key)] && !pr.quiz[String(q.key)].ok);
    const forgot = [];
    d.cloze.forEach((c, i) => c.parts.forEach((p, k) => { if (p.a && pr.cloze[`${i}-${k}`] === 0) forgot.push(p.a); }));
    return `<div class="card tj-sum">
        ${ring(s.news ? s.read / s.news : 1, "研读", `${s.read}/${s.news} 条`, "#3f9e8f")}
        ${ring(s.blanks ? s.seen / s.blanks : 1, "消化", `${s.seen}/${s.blanks} 空 · 忘 ${s.forgot}`, "#c9a227")}
        ${ring(s.questions ? s.done / s.questions : 1, "精卷", `${s.done}/${s.questions} 题 · 对 ${s.right}`, "#c2463a")}</div>
      <div class="tj-sum2">
        <div class="card"><h3>✗ 错题 <small>${wrong.length}</small></h3>${wrong.map((q) => `<a class="tj-sum-q" data-goq="${q.key}"><b>${q.no}.</b> ${esc(q.stem.slice(0, 60))}…</a>`).join("") || '<div class="muted small">没有错题</div>'}</div>
        <div class="card"><h3>✗ 没记住的空 <small>${forgot.length}</small></h3><div class="tj-forgot">${forgot.map((a) => `<span>${esc(a)}</span>`).join("") || '<span class="muted small">没有</span>'}</div></div></div>`;
  }

  function renderIssue() {
    if (!ROOT || !CUR) return;
    const body = MODE === "read" ? readHtml() : MODE === "cloze" ? clozeHtml() : MODE === "quiz" ? quizHtml() : sumHtml();
    ROOT.innerHTML = `<div class="tj-issue">${issueHead()}<div class="tj-ibody">${body}</div></div>`;
    bindIssue();
  }
  async function mark(body) {
    act();
    const r = await api("/api/tianji/mark", Object.assign({ kind: CUR.kind, id: CUR.id }, body));
    CUR.progress = r.progress; CUR.stat = r.stat;
    if (r.events?.length) handleEvents(r.events);
    return r;
  }
  function keepScroll(fn) { const y = window.scrollY; fn(); window.scrollTo(0, y); }

  function bindIssue() {
    const v = ROOT, $$ = (s) => v.querySelectorAll(s), $1 = (s) => v.querySelector(s);
    $1("#tjBack").onclick = close;
    $$("[data-mode]").forEach((a) => (a.onclick = () => { MODE = a.dataset.mode; store.set("mode", MODE); renderIssue(); window.scrollTo(0, 0); }));
    const cat = $1("#tjCat");
    if (cat) cat.onchange = async () => { try { await api("/api/tianji/meta", { kind: CUR.kind, id: CUR.id, category: cat.value }); CUR.data.category = cat.value; toast(`归到「${esc(cat.value)}」`); } catch (e) { showError(e); } };
    const pdf = $1("#tjPdf");
    if (pdf) pdf.onclick = async () => {
      try {
        if (local) await api("/api/notes/open", { path: CUR.data.pdf });
        else { const r = await api("/api/tianji/pdf", { path: CUR.data.pdf }); window.open(r.url, "_blank"); }
      } catch (e) { showError(e); }
    };
    $1("#tjDel").onclick = async () => {
      if (!confirm(`从天机简报里删掉「${CUR.data.title}」？学习进度一起删（库里的原 PDF 留着，可以再导入）。`)) return;
      try { await api("/api/tianji/delete", { kind: CUR.kind, id: CUR.id }); close(); } catch (e) { showError(e); }
    };
    // 研读
    if (MODE === "read") { bindLeft(); const m = document.getElementById("tjAskMsgs"); if (m) m.scrollTop = m.scrollHeight; }
    const note = $1("#tjNote");
    if (note) note.onclick = async () => {
      try {
        await api("/api/notes/pdfopen", { p: CUR.data.pdf, title: `天机简报 · ${CUR.data.title}` });
        NOTES.openPdfLater(CUR.data.pdf); go("notes");
      } catch (e) { showError(e); }
    };
    $$("[data-news]").forEach((a) => (a.onclick = () => { NEWS = +a.dataset.news; renderIssue(); window.scrollTo(0, 0); }));
    const rd = $1("#tjRead");
    if (rd) rd.onclick = async () => {
      const was = CUR.progress.read.includes(NEWS);
      try {
        await mark({ read: NEWS, off: was ? 1 : 0 });
        if (!was && NEWS < CUR.data.news.length - 1) NEWS++;
        renderIssue(); window.scrollTo(0, 0);
      } catch (e) { showError(e); }
    };
    const tq = $1("#tjToQuiz");
    if (tq) tq.onclick = () => { const k = CUR.data.news[NEWS].qs[0]; MODE = "quiz"; renderIssue(); setTimeout(() => document.getElementById("tjq" + k)?.scrollIntoView({ block: "start" }), 50); };
    const pv = $1("#tjPrev"), nx = $1("#tjNext");
    if (pv) pv.onclick = () => { NEWS--; renderIssue(); window.scrollTo(0, 0); };
    if (nx) nx.onclick = () => { NEWS++; renderIssue(); window.scrollTo(0, 0); };
    // 消化
    $$(".tj-b[data-b]").forEach((b) => (b.onclick = async () => {
      const key = b.dataset.b, st = CUR.progress.cloze[key];
      const ok = st === undefined ? 1 : st === 1 ? 0 : 1;
      b.className = "tj-b " + (ok ? "ok" : "no");
      try { await mark({ cloze: key, ok }); keepScroll(renderIssue); } catch (e) { showError(e); }
    }));
    const on = $1("#tjOnlyNo"); if (on) on.onchange = () => { ONLY_FORGOT = on.checked; renderIssue(); };
    const cr = $1("#tjClozeReset");
    if (cr) cr.onclick = async () => { if (!confirm("把这一期消化清单的空全部重新遮住，再过一遍？")) return; try { await mark({ reset: "cloze" }); renderIssue(); } catch (e) { showError(e); } };
    const cc = $1("#tjCards");
    if (cc) cc.onclick = async () => {
      try {
        const r = await api("/api/tianji/cards", { kind: CUR.kind, id: CUR.id });
        const g = await api("/api/tianji/get", { kind: CUR.kind, id: CUR.id });
        CUR.progress = g.progress; CUR.stat = g.stat;
        toast(`🀄 刻好 ${r.added} 枚${esc(W("yj"))}，在修炼殿「政治理论 › 天机简报」简匣里`);
        keepScroll(renderIssue);
      } catch (e) { showError(e); }
    };
    // 精卷
    $$(".tj-opt[data-q]").forEach((b) => (b.onclick = async () => {
      const key = +b.dataset.q;
      try { await mark({ quiz: key, choice: b.dataset.c }); REDO.delete(key); keepScroll(renderIssue); } catch (e) { showError(e); }
    }));
    $$("[data-redo]").forEach((a) => (a.onclick = () => { REDO.add(+a.dataset.redo); keepScroll(renderIssue); }));
    $$("[data-goread]").forEach((a) => (a.onclick = () => { NEWS = +a.dataset.goread; MODE = "read"; renderIssue(); window.scrollTo(0, 0); }));
    const ow = $1("#tjOnlyWrong"); if (ow) ow.onchange = () => { ONLY_WRONG = ow.checked; renderIssue(); };
    const qr = $1("#tjQuizReset");
    if (qr) qr.onclick = async () => { if (!confirm("清掉这一期精卷的作答，整卷重做？（修为不会重复发）")) return; try { await mark({ reset: "quiz" }); REDO = new Set(); renderIssue(); } catch (e) { showError(e); } };
    $$("[data-goq]").forEach((a) => (a.onclick = () => { const k = a.dataset.goq; MODE = "quiz"; renderIssue(); setTimeout(() => document.getElementById("tjq" + k)?.scrollIntoView({ block: "start" }), 50); }));
  }

  // 心跳：开着一期、看得见、2 分钟内动过 → 研读 / 消化算复习，精卷算做题
  const active = () => (VIEW === "tianji" && CUR && document.visibilityState === "visible" && Date.now() - lastAct < 120000 ? (MODE === "quiz" ? "quiz" : "read") : "");

  window.TIANJI = { render, open, close, active, isOpen: () => !!CUR, importFiles };
})();
