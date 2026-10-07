/* 📜 玉简（照 Anki 做的记忆卡片）：修炼殿里的简匣树、温简（复习）、刻简（加卡片）、藏简阁（浏览）、灵识图（统计）、导入、简匣规矩。
   数据都走 /api/cards/…（见 rpg/cards.py）。温简等界面铺在 #yjStage 上（盖住修炼殿，左上角“← 回修炼殿”）。
   键盘：空格 / 回车 显示答案，显示后空格 = 通透；1~4 评分；Ctrl+Z 撤销；Ctrl+Enter 刻入。 */
(function () {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const T = (k) => (typeof W === "function" ? W(k) : k);
  const LS = { get: (k, d) => { try { return localStorage.getItem(k) ?? d; } catch (e) { return d; } }, set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) {} } };
  const CLOSED = new Set(JSON.parse(LS.get("xrpg-yj-closed", "[]")));
  let OV = null;                 // /api/cards 的概览
  let MODE = "";                 // review | add | browse | stats | import
  let R = null;                  // 温简状态 {deck, card, intervals, counts, shown, t0, ask:[], asking}
  let lastActive = 0;
  const TYPE_NAMES = { "问答": "问答", "问答+反向": "问答 + 反向（正反各一张）", "填空": "填空（{{c1::…}} 挖空）" };

  // ---------------------------------------------------------------- 修炼殿里的简匣树
  async function hubHtml() {
    try { OV = await api("/api/cards"); } catch (e) { return `<div class="card"><p class="muted">${esc(e.message)}</p></div>`; }
    const decks = OV.decks;
    const kids = (name) => decks.some((d) => d.name.startsWith(name + "::"));
    const hidden = (name) => { const p = name.split("::"); for (let i = 1; i < p.length; i++) if (CLOSED.has(p.slice(0, i).join("::"))) return true; return false; };
    const num = (n, cls) => `<span class="yj-n ${n ? cls : "zero"}">${n}</span>`;
    const rows = decks.filter((d) => !hidden(d.name)).map((d) => `<div class="yj-row" style="--dep:${d.depth}">
        <span class="yj-fold">${kids(d.name) ? `<a data-yjfold="${esc(d.name)}">${CLOSED.has(d.name) ? "▸" : "▾"}</a>` : ""}</span>
        <a class="yj-name" data-yjgo="${esc(d.name)}" title="温这个简匣（含子匣）">${esc(d.label)}</a>
        ${num(d.new, "new")}${num(d.learn, "learn")}${num(d.review, "due")}
        <a class="yj-gear" data-yjgear="${esc(d.name)}" title="${esc(T("yj_rule"))}、新建子匣、改名、删除">⚙</a></div>`).join("");
    const total = decks.filter((d) => !d.depth).reduce((a, d) => [a[0] + d.new, a[1] + d.learn, a[2] + d.review], [0, 0, 0]);
    return `<div class="card yj-hall">
      <div class="yj-hall-head"><div><div class="yj-title">📜 ${esc(T("yj"))}</div>
        <div class="small muted">共 ${OV.cards} ${esc(T("yj_unit"))} · 今日已温 ${OV.today.n} ${esc(T("yj_unit"))}${OV.today.secs >= 60 ? ` · ${Math.round(OV.today.secs / 60)} 分钟` : ""}</div></div>
        <span class="spacer"></span>
        <button class="primary yj-go-all" data-yjgo="" ${total[0] + total[1] + total[2] ? "" : "disabled"}>🌙 ${esc(T("yj_review"))}全部</button></div>
      <div class="yj-tree"><div class="yj-row yj-th"><span class="yj-fold"></span><span class="yj-name">${esc(T("yj_deck"))}</span>
        <span class="yj-n new">${esc(T("yj_new"))}</span><span class="yj-n learn">${esc(T("yj_learn"))}</span><span class="yj-n due">${esc(T("yj_due"))}</span><span class="yj-gear"></span></div>
        ${rows}</div>
      ${OV.cards ? "" : `<p class="small muted yj-empty">还没有${esc(T("yj"))}。点「✍ ${esc(T("yj_add"))}」自己刻，或者「📥 导入」Anki 导出的文本；用 xingce-card skill 从 PDF / 笔记做的也会出现在这里。</p>`}
      <div class="yj-tools"><button data-yjmode="add">✍ ${esc(T("yj_add"))}</button><button data-yjmode="browse">🏛 ${esc(T("yj_browse"))}</button>
        <button data-yjmode="stats">📊 ${esc(T("yj_stats"))}</button><button data-yjmode="import">📥 导入</button>
        <button class="ghost" id="yjNewDeck">＋ 新${esc(T("yj_deck"))}</button></div></div>`;
  }
  function bindHub(root = document) {
    root.querySelectorAll("[data-yjfold]").forEach((a) => (a.onclick = () => {
      const n = a.dataset.yjfold; CLOSED.has(n) ? CLOSED.delete(n) : CLOSED.add(n);
      LS.set("xrpg-yj-closed", JSON.stringify([...CLOSED])); renderTrain();
    }));
    root.querySelectorAll("[data-yjgo]").forEach((a) => (a.onclick = () => review(a.dataset.yjgo)));
    root.querySelectorAll("[data-yjmode]").forEach((b) => (b.onclick = () => open(b.dataset.yjmode)));
    root.querySelectorAll("[data-yjgear]").forEach((a) => (a.onclick = (e) => { e.stopPropagation(); deckMenu(a, a.dataset.yjgear); }));
    const nd = root.querySelector("#yjNewDeck");
    if (nd) nd.onclick = async () => {
      const name = prompt(`新${T("yj_deck")}的名字（子匣用 :: 隔开，如「资料分析::速算公式」）`);
      if (!name) return;
      try { await api("/api/cards/deck", { action: "create", name }); renderTrain(); } catch (e) { showError(e); }
    };
  }
  function deckMenu(anchor, name) {
    document.querySelectorAll(".yj-menu").forEach((m) => m.remove());
    const m = document.createElement("div");
    m.className = "yj-menu";
    m.innerHTML = `<button data-m="opts">⚙ ${esc(T("yj_rule"))}</button><button data-m="sub">＋ 新建子匣</button><button data-m="add">✍ 往这里${esc(T("yj_add"))}</button>
      <button data-m="browse">🏛 在${esc(T("yj_browse"))}里看</button><button data-m="rename">✎ 改名</button><button data-m="del" class="danger">🗑 删除</button>`;
    document.body.appendChild(m);
    const r = anchor.getBoundingClientRect();
    m.style.top = Math.min(innerHeight - m.offsetHeight - 8, r.bottom + 4) + "px";
    m.style.left = Math.max(8, r.right - m.offsetWidth) + "px";
    const close = () => { m.remove(); removeEventListener("click", away, true); };
    const away = (e) => { if (!m.contains(e.target)) close(); };
    setTimeout(() => addEventListener("click", away, true), 0);
    m.querySelectorAll("button").forEach((b) => (b.onclick = async () => {
      close();
      try {
        const act = b.dataset.m;
        if (act === "opts") return optionsDialog(name);
        if (act === "add") { ADD.deck = name; return open("add"); }
        if (act === "browse") { BR.deck = name; return open("browse"); }
        if (act === "sub") {
          const n = prompt(`在「${name}」下新建子匣，名字：`);
          if (n) { await api("/api/cards/deck", { action: "create", name: name + "::" + n }); CLOSED.delete(name); renderTrain(); }
        } else if (act === "rename") {
          const n = prompt("改成（子匣用 :: 隔开）：", name);
          if (n && n !== name) { await api("/api/cards/deck", { action: "rename", name, new: n }); renderTrain(); }
        } else if (act === "del") {
          const d = OV.decks.find((x) => x.name === name);
          if (d && d.total) {
            if (!confirm(`「${name}」里还有 ${d.total} 张卡。连${T("yj")}一起删掉？（删了不能恢复；温习记录也会删）`)) return;
            await api("/api/cards/deck", { action: "delete", name, with_cards: true });
          } else {
            if (!confirm(`删除空${T("yj_deck")}「${name}」？`)) return;
            await api("/api/cards/deck", { action: "delete", name });
          }
          renderTrain();
        }
      } catch (e) { showError(e); }
    }));
  }
  async function optionsDialog(name) {
    let o;
    try { o = await api("/api/cards/deck", { action: "get", name }); } catch (e) { return showError(e); }
    const v = o.options;
    const m = $("#modal");
    m.innerHTML = `<div class="modal-box yj-opts"><h3>⚙ ${esc(T("yj_rule"))} · ${esc(name)}</h3>
      <p class="small muted">没单独设的沿用上一层${esc(T("yj_deck"))}；子匣的上限也受上层管着（和 Anki 一样）。</p>
      <div class="yj-form">
        <label>每天新${esc(T("yj_unit"))}数<input id="oNew" type="number" min="0" value="${v.new_per_day}"></label>
        <label>每天复习上限<input id="oRev" type="number" min="0" value="${v.rev_per_day}"></label>
        <label>学习步长（分钟）<input id="oSteps" value="${esc(v.learn_steps.join(" "))}"></label>
        <label>重参步长（分钟）<input id="oRe" value="${esc(v.relearn_steps.join(" "))}"></label>
        <label>目标记忆保持率<input id="oRet" type="number" step="0.01" min="0.7" max="0.99" value="${v.retention}"></label>
        <label>忘几次算${esc(T("yj_leech"))}<input id="oLeech" type="number" min="1" value="${v.leech}"></label>
        <label>最长间隔（天）<input id="oMax" type="number" min="1" value="${v.max_ivl}"></label></div>
      <p class="small faint">目标记忆保持率越高，复习越勤；0.9 是 Anki 的默认值。</p>
      <div class="row"><span class="spacer"></span><button class="ghost" id="oCancel">取消</button><button class="primary" id="oSave">保存</button></div></div>`;
    m.classList.remove("hidden");
    $("#oCancel").onclick = () => m.classList.add("hidden");
    $("#oSave").onclick = async () => {
      try {
        await api("/api/cards/deck", { action: "options", name, options: { new_per_day: $("#oNew").value, rev_per_day: $("#oRev").value,
          learn_steps: $("#oSteps").value, relearn_steps: $("#oRe").value, retention: $("#oRet").value, leech: $("#oLeech").value, max_ivl: $("#oMax").value } });
        m.classList.add("hidden"); toast("规矩已更新"); renderTrain();
      } catch (e) { showError(e); }
    };
  }

  // ---------------------------------------------------------------- 舞台（盖在修炼殿上）
  function stage() {
    let s = document.getElementById("yjStage");
    if (!s) { s = document.createElement("div"); s.id = "yjStage"; s.className = "yj-stage"; document.body.appendChild(s); }
    document.documentElement.classList.add("yj-on");
    return s;
  }
  function closeStage() {
    const s = document.getElementById("yjStage");
    if (s) s.remove();
    document.documentElement.classList.remove("yj-on");
    MODE = ""; R = null;
    if (typeof VIEW !== "undefined" && VIEW === "train") renderTrain();
  }
  function head(title, extra = "") {
    return `<div class="yj-top"><button class="ghost" id="yjBack">← 回修炼殿</button><b class="yj-top-title">${title}</b><span class="spacer"></span>${extra}</div>`;
  }
  function bindBack() { const b = document.getElementById("yjBack"); if (b) b.onclick = closeStage; }
  function open(mode) {
    MODE = mode;
    if (mode === "add") return addScreen();
    if (mode === "browse") return browseScreen();
    if (mode === "stats") return statsScreen();
    if (mode === "import") return importScreen();
  }

  // ---------------------------------------------------------------- 卡面
  function render(text, images, ord, side) {
    const holes = [];
    let t = String(text || "");
    if (ord && ord.startsWith("c")) {
      const n = ord.slice(1);
      t = t.replace(/\{\{c(\d+)::([\s\S]*?)(?:::([\s\S]*?))?\}\}/g, (_, k, ans, hint) => {
        holes.push(k === n ? (side === "front" ? `<span class="cloze">[${esc(hint || "…")}]</span>` : `<span class="cloze ans">${esc(ans)}</span>`) : esc(ans));
        return `\u0001${holes.length - 1}\u0002`;
      });
    }
    let html = window.NOTES ? NOTES.mdRender(t, images || {}) : esc(t).replace(/\n/g, "<br>");
    return html.replace(/\u0001(\d+)\u0002/g, (_, i) => holes[+i]);
  }
  function faces(c) {
    const im = c.images;
    if (c.type === "填空") return { front: render(c.front, im, c.ord, "front"), back: render(c.front, im, c.ord, "back") + (c.back ? `<div class="yj-extra">${render(c.back, im)}</div>` : "") };
    const [f, b] = c.ord === "2" ? [c.back, c.front] : [c.front, c.back];
    return { front: render(f, im), back: render(b, im) };
  }

  // ---------------------------------------------------------------- 温简
  async function review(deck) {
    MODE = "review";
    R = { deck, ask: [] };
    stage().innerHTML = head(`🌙 ${esc(T("yj_review"))} · ${esc(deck || "全部" + T("yj_deck"))}`) + `<div class="yj-wait">取简中…</div>`;
    bindBack();
    try { show(await api("/api/cards/next", { deck })); } catch (e) { showError(e); closeStage(); }
  }
  function show(r) {
    if (MODE !== "review") return;
    if (r.events && window.handleEvents) handleEvents(r.events);
    Object.assign(R, { card: r.card, intervals: r.intervals, counts: r.counts, shown: false, t0: Date.now(), ask: [], asking: false });
    lastActive = Date.now();
    const s = stage();
    const cnt = (c) => `<span class="yj-cnt"><i class="new">${c.new}</i> + <i class="learn">${c.learn}</i> + <i class="due">${c.review}</i></span>`;
    const tools = `${cnt(r.counts)}<button class="ghost small" id="yjUndo" title="撤销上一张（Ctrl+Z）">↶ 撤销</button>`;
    if (r.done) {
      s.innerHTML = head(`🌙 ${esc(T("yj_review"))} · ${esc(R.deck || "全部" + T("yj_deck"))}`, tools) + `<div class="yj-finish">
        <div class="yj-moon"><svg viewBox="0 0 64 64" width="76" height="76"><path d="M40 6a26 26 0 1 0 18 44A22 22 0 1 1 40 6z" fill="currentColor"/></svg></div><h2>${esc(T("yj_done"))}</h2>
        <p>${r.next_learn ? `还有参悟中的${esc(T("yj"))}，约 ${esc(r.next_learn)} 后再来。` : "明日再来，记忆会在恰好将忘之时被唤醒。"}</p>
        <div class="row" style="justify-content:center"><button class="primary" id="yjDoneBack">回修炼殿</button><button class="ghost" id="yjDoneAdd">✍ ${esc(T("yj_add"))}</button></div></div>`;
      bindBack(); bindUndo();
      document.getElementById("yjDoneBack").onclick = closeStage;
      document.getElementById("yjDoneAdd").onclick = () => { ADD.deck = R.deck; open("add"); };
      return;
    }
    const c = r.card;
    const f = faces(c);
    const kind = ["new", "learn", "due", "learn"][c.state] || "new";
    s.innerHTML = head(`🌙 ${esc(T("yj_review"))} · ${esc(R.deck || "全部" + T("yj_deck"))}`, tools) + `
      <div class="yj-desk"><div class="yj-slip ${kind}">
        <div class="yj-slip-meta"><span>${esc(c.deck)}</span>${c.leech ? `<span class="tag bad">${esc(T("yj_leech"))}</span>` : ""}${c.tags.map((t) => `<span class="tag">${esc(t)}</span>`).join("")}<span class="spacer"></span>
          <a id="yjEdit" title="改这枚${esc(T("yj"))}">✎ 改</a><a id="yjSusp" title="暂停：以后不出，藏简阁里可恢复">⏸ 暂停</a><a id="yjInfo" title="温习记录">ℹ</a></div>
        <div class="yj-face yj-front">${f.front}</div>
        <div class="yj-back" id="yjBackFace" hidden><div class="yj-rule"></div><div class="yj-face">${f.back}</div>
          <div class="yj-ask"><button class="ghost small" id="yjAskBtn">🙋 师傅讲讲</button><div id="yjAskBox"></div></div></div>
      </div></div>
      <div class="yj-bar" id="yjBar"><button class="primary yj-show" id="yjShow">${esc(T("yj_show"))} <small>空格</small></button></div>`;
    bindBack(); bindUndo();
    s.querySelectorAll(".yj-face img").forEach((im) => (im.onclick = () => window.zoomImg && zoomImg(im.src)));
    document.getElementById("yjShow").onclick = flip;
    document.getElementById("yjEdit").onclick = () => editDialog(c.id, async () => { show(await api("/api/cards/next", { deck: R.deck })); });
    document.getElementById("yjSusp").onclick = async () => {
      try { await api("/api/cards/suspend", { keys: [c.key], on: true }); toast("已暂停这张卡"); show(await api("/api/cards/next", { deck: R.deck })); } catch (e) { showError(e); }
    };
    document.getElementById("yjInfo").onclick = () => infoDialog(c.key);
  }
  function bindUndo() {
    const u = document.getElementById("yjUndo");
    if (u) u.onclick = undo;
  }
  function flip() {
    if (!R || !R.card || R.shown) return;
    R.shown = true;
    document.getElementById("yjBackFace").hidden = false;
    const iv = R.intervals;
    document.getElementById("yjBar").innerHTML = [1, 2, 3, 4].map((k) =>
      `<button class="yj-rate r${k}" data-rate="${k}"><b>${esc(T("yj_r" + k))}</b><small>${["重来", "困难", "良好", "简单"][k - 1]} · ${esc(iv[k] || iv[String(k)] || "")}</small></button>`).join("");
    document.querySelectorAll("[data-rate]").forEach((b) => (b.onclick = () => rate(+b.dataset.rate)));
    document.getElementById("yjAskBtn").onclick = () => ask("");
    const back = document.getElementById("yjBackFace");
    back.querySelectorAll("img").forEach((im) => (im.onclick = () => window.zoomImg && zoomImg(im.src)));
    back.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
  let busy = false;
  async function rate(k) {
    if (!R || !R.shown || busy) return;
    busy = true;
    const secs = Math.round((Date.now() - R.t0) / 1000);
    try { show(await api("/api/cards/answer", { deck: R.deck, key: R.card.key, rating: k, secs })); } catch (e) { showError(e); }
    busy = false;
  }
  async function undo() {
    if (busy) return;
    busy = true;
    try { show(await api("/api/cards/undo", { deck: R.deck })); toast("已撤销"); } catch (e) { showError(e); }
    busy = false;
  }
  async function ask(q) {
    if (!R || !R.card || R.asking) return;
    const box = document.getElementById("yjAskBox");
    if (q) R.ask.push({ role: "user", content: q });
    R.asking = true;
    paintAsk(box, true);
    try {
      const r = await api("/api/cards/explain", { key: R.card.key, question: q, history: R.ask.slice(0, -1) });
      if (!q) R.ask.push({ role: "user", content: "这张卡我没太懂，讲讲？" });
      R.ask.push({ role: "assistant", content: r.reply });
    } catch (e) { showError(e); if (q) R.ask.pop(); }
    R.asking = false;
    paintAsk(document.getElementById("yjAskBox"), false);
  }
  function paintAsk(box, waiting) {
    if (!box) return;
    const md = (s) => (window.NOTES ? NOTES.mdRender(s, {}) : esc(s));
    box.innerHTML = R.ask.map((m) => `<div class="yj-msg ${m.role === "user" ? "me" : "npc"}">${m.role === "user" ? esc(m.content) : md(m.content)}</div>`).join("")
      + (waiting ? `<div class="yj-msg npc faint">师傅思索中…</div>` : "")
      + (R.ask.length && !waiting ? `<div class="row yj-ask-row"><input id="yjAskIn" placeholder="接着问…（回车发送）"><button class="small" id="yjAskGo">问</button></div>` : "");
    const go = () => { const v = document.getElementById("yjAskIn").value.trim(); if (v) ask(v); };
    const b = document.getElementById("yjAskGo");
    if (b) { b.onclick = go; document.getElementById("yjAskIn").onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); go(); } }; }
    const btn = document.getElementById("yjAskBtn"); if (btn) btn.hidden = R.ask.length > 0 || waiting;
  }
  document.addEventListener("keydown", (e) => {
    if (MODE !== "review" || !R) return;
    if (/INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName || "") || !$("#modal").classList.contains("hidden")) return;
    lastActive = Date.now();
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") { e.preventDefault(); return undo(); }
    if (!R.card) return;
    if (e.key === " " || e.key === "Enter") { e.preventDefault(); return R.shown ? rate(3) : flip(); }
    if (R.shown && /^[1-4]$/.test(e.key)) { e.preventDefault(); rate(+e.key); }
  });
  ["pointerdown", "keydown", "wheel"].forEach((ev) => addEventListener(ev, () => { if (MODE === "review") lastActive = Date.now(); }, { passive: true }));

  // ---------------------------------------------------------------- 刻简
  const ADD = { deck: LS.get("xrpg-yj-deck", ""), type: LS.get("xrpg-yj-type", "问答"), tags: "" };
  function deckOptions(sel) {
    const names = (OV?.decks || []).map((d) => d.name);
    if (sel && !names.includes(sel)) names.push(sel);
    return names.map((n) => `<option value="${esc(n)}" ${n === sel ? "selected" : ""}>${esc(n.replace(/::/g, " › "))}</option>`).join("");
  }
  async function ensureOV() { if (!OV) OV = await api("/api/cards"); }
  async function addScreen() {
    await ensureOV().catch(showError);
    if (!ADD.deck) ADD.deck = OV?.decks?.[0]?.name || "";
    const s = stage();
    s.innerHTML = head(`✍ ${esc(T("yj_add"))}`) + `<div class="yj-add">
      <div class="yj-form-row"><label>${esc(T("yj_deck"))}<select id="aDeck">${deckOptions(ADD.deck)}</select></label>
        <button class="ghost small" id="aNewDeck">＋ 新匣</button>
        <label>类型<select id="aType">${Object.entries(TYPE_NAMES).map(([k, v]) => `<option value="${k}" ${k === ADD.type ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></label></div>
      ${editorFields({ front: "", back: "", extra: "", tags: ADD.tags })}
      <div class="row yj-add-foot"><span class="small faint">Ctrl+Enter 刻入；刻完窗口不关，接着刻下一张。图片可以直接粘贴。</span><span class="spacer"></span>
        <button class="primary" id="aSave">✍ 刻入</button></div>
      <div class="yj-preview-wrap"><div class="small muted">预览</div><div class="yj-preview" id="aPrev"></div></div></div>`;
    bindBack();
    bindEditor(s, () => document.getElementById("aType").value);
    document.getElementById("aType").onchange = () => { ADD.type = document.getElementById("aType").value; LS.set("xrpg-yj-type", ADD.type); syncTypeHint(s); preview(); };
    document.getElementById("aDeck").onchange = () => { ADD.deck = document.getElementById("aDeck").value; LS.set("xrpg-yj-deck", ADD.deck); };
    document.getElementById("aNewDeck").onclick = async () => {
      const n = prompt(`新${T("yj_deck")}名字（子匣用 :: 隔开）：`, ADD.deck ? ADD.deck + "::" : "");
      if (!n) return;
      try { const r = await api("/api/cards/deck", { action: "create", name: n }); OV = await api("/api/cards"); ADD.deck = r.name; document.getElementById("aDeck").innerHTML = deckOptions(ADD.deck); } catch (e) { showError(e); }
    };
    const preview = () => {
      const typ = document.getElementById("aType").value;
      const c = { type: typ, front: val("eFront"), back: val("eBack"), ord: typ === "填空" ? ((val("eFront").match(/\{\{c(\d+)::/) || [])[1] ? "c" + val("eFront").match(/\{\{c(\d+)::/)[1] : "c1") : "1", images: {} };
      const f = faces(c);
      document.getElementById("aPrev").innerHTML = `<div class="yj-face">${f.front}</div><div class="yj-rule"></div><div class="yj-face">${f.back}</div>`;
    };
    s.querySelectorAll("#eFront,#eBack").forEach((t) => t.addEventListener("input", preview));
    syncTypeHint(s); preview();
    const save = async () => {
      const body = { deck: document.getElementById("aDeck").value, type: document.getElementById("aType").value, front: val("eFront"), back: val("eBack"), tags: val("eTags") };
      try {
        const r = await api("/api/cards/add", body);
        ADD.tags = body.tags; ADD.deck = body.deck; LS.set("xrpg-yj-deck", body.deck);
        toast(`✍ 已刻入「${esc(body.deck)}」${r.cards > 1 ? `（${r.cards} 张卡）` : ""}`);
        document.getElementById("eFront").value = ""; document.getElementById("eBack").value = ""; preview();
        document.getElementById("eFront").focus();
        OV = null;
      } catch (e) { showError(e); }
    };
    document.getElementById("aSave").onclick = save;
    s.onkeydown = (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); save(); } };
    document.getElementById("eFront").focus();
  }
  const val = (id) => (document.getElementById(id)?.value || "").trim();
  function editorFields(n) {
    return `<label class="yj-field">正面<div class="yj-ed-tools"><button class="ghost small" data-cloze title="选中文字后点：挖成填空 {{c1::…}}（Ctrl+Shift+C）">⌗ 挖空</button>
        <button class="ghost small" data-img="eFront">🖼 图片</button><button class="ghost small" data-pad="eFront">✍ 手写</button></div>
        <textarea id="eFront" rows="4">${esc(n.front)}</textarea></label>
      <label class="yj-field"><span id="eBackLbl">反面</span><div class="yj-ed-tools"><button class="ghost small" data-img="eBack">🖼 图片</button><button class="ghost small" data-pad="eBack">✍ 手写</button></div>
        <textarea id="eBack" rows="4">${esc(n.back)}</textarea></label>
      <label class="yj-field">标签 <span class="small faint">空格隔开</span><input id="eTags" value="${esc(Array.isArray(n.tags) ? n.tags.join(" ") : n.tags || "")}"></label>
      <input type="file" id="eFile" accept="image/*" hidden>`;
  }
  function syncTypeHint(root) {
    const t = root.querySelector("#aType")?.value || root.querySelector("#eType")?.value;
    const l = root.querySelector("#eBackLbl");
    if (l) l.textContent = t === "填空" ? "反面附注（可不填，翻面后显示在下面）" : "反面";
  }
  function bindEditor(root, typeOf) {
    const insert = (id, text) => {
      const ta = document.getElementById(id);
      const a = ta.selectionStart ?? ta.value.length, b = ta.selectionEnd ?? a;
      ta.value = ta.value.slice(0, a) + text + ta.value.slice(b);
      ta.selectionStart = ta.selectionEnd = a + text.length;
      ta.dispatchEvent(new Event("input")); ta.focus();
    };
    const upload = async (id, dataUrl) => {
      try { const r = await api("/api/cards/image", { data: dataUrl }); insert(id, "\n" + r.md + "\n"); } catch (e) { showError(e); }
    };
    const cloze = () => {
      const ta = document.getElementById("eFront");
      const nums = [...ta.value.matchAll(/\{\{c(\d+)::/g)].map((m) => +m[1]);
      const n = (nums.length ? Math.max(...nums) : 0) + 1;
      const a = ta.selectionStart, b = ta.selectionEnd;
      const sel = ta.value.slice(a, b);
      const t = `{{c${n}::${sel || "答案"}}}`;
      ta.value = ta.value.slice(0, a) + t + ta.value.slice(b);
      ta.focus(); ta.selectionStart = a + `{{c${n}::`.length; ta.selectionEnd = ta.selectionStart + (sel || "答案").length;
      ta.dispatchEvent(new Event("input"));
      const ty = root.querySelector("#aType") || root.querySelector("#eType");
      if (ty && ty.value !== "填空") { ty.value = "填空"; ty.dispatchEvent(new Event("change")); }
    };
    root.querySelectorAll("[data-cloze]").forEach((b) => (b.onclick = (e) => { e.preventDefault(); cloze(); }));
    root.querySelectorAll("#eFront,#eBack").forEach((ta) => {
      ta.addEventListener("keydown", (e) => { if (e.key.toLowerCase() === "c" && e.ctrlKey && e.shiftKey && ta.id === "eFront") { e.preventDefault(); cloze(); } });
      ta.addEventListener("paste", (e) => {
        const f = [...(e.clipboardData?.items || [])].find((i) => i.type.startsWith("image/"));
        if (!f) return;
        e.preventDefault();
        const rd = new FileReader(); rd.onload = () => upload(ta.id, rd.result); rd.readAsDataURL(f.getAsFile());
      });
    });
    const file = root.querySelector("#eFile");
    root.querySelectorAll("[data-img]").forEach((b) => (b.onclick = (e) => {
      e.preventDefault();
      file.onchange = () => { const f = file.files[0]; if (!f) return; const rd = new FileReader(); rd.onload = () => upload(b.dataset.img, rd.result); rd.readAsDataURL(f); file.value = ""; };
      file.click();
    }));
    root.querySelectorAll("[data-pad]").forEach((b) => (b.onclick = (e) => { e.preventDefault(); handPad((url) => upload(b.dataset.pad, url)); }));
  }
  // 手写板：写好存成透明底 PNG 放进卡里（平板用笔写公式、画图）
  function handPad(done) {
    const m = document.createElement("div");
    m.className = "yj-pad-wrap";
    m.innerHTML = `<div class="yj-pad"><div class="row"><b>✍ 手写</b><span class="spacer"></span><button class="ghost small" data-p="clear">清空</button>
      <button class="ghost small" data-p="cancel">取消</button><button class="primary small" data-p="ok">放进卡里</button></div><canvas></canvas></div>`;
    document.body.appendChild(m);
    const c = m.querySelector("canvas"), dpr = devicePixelRatio || 1;
    const w = Math.min(760, innerWidth - 40), h = Math.min(420, innerHeight - 160);
    c.width = w * dpr; c.height = h * dpr; c.style.width = w + "px"; c.style.height = h + "px";
    const x = c.getContext("2d"); x.scale(dpr, dpr); x.lineCap = x.lineJoin = "round"; x.lineWidth = 3; x.strokeStyle = "#222";
    let down = false, any = false, last = null;
    const pt = (e) => { const r = c.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
    c.onpointerdown = (e) => { if (e.pointerType === "touch" && LS.get("xrpg-nt-finger", "draw") === "scroll") return; down = true; last = pt(e); try { c.setPointerCapture(e.pointerId); } catch (_) {} e.preventDefault(); };
    c.onpointermove = (e) => { if (!down) return; const p = pt(e); x.beginPath(); x.moveTo(...last); x.lineTo(...p); x.stroke(); last = p; any = true; };
    c.onpointerup = c.onpointercancel = () => { down = false; };
    m.querySelector('[data-p="clear"]').onclick = () => { x.clearRect(0, 0, w, h); any = false; };
    m.querySelector('[data-p="cancel"]').onclick = () => m.remove();
    m.querySelector('[data-p="ok"]').onclick = () => { if (any) done(trimCanvas(c)); m.remove(); };
  }
  function trimCanvas(c) {
    const x = c.getContext("2d"), { width: w, height: h } = c, d = x.getImageData(0, 0, w, h).data;
    let t = h, l = w, b = 0, r = 0;
    for (let y = 0; y < h; y += 2) for (let i = 0; i < w; i += 2) if (d[(y * w + i) * 4 + 3]) { t = Math.min(t, y); b = Math.max(b, y); l = Math.min(l, i); r = Math.max(r, i); }
    const pad = 12, o = document.createElement("canvas");
    o.width = Math.max(1, r - l + pad * 2); o.height = Math.max(1, b - t + pad * 2);
    o.getContext("2d").drawImage(c, l - pad, t - pad, o.width, o.height, 0, 0, o.width, o.height);
    return o.toDataURL("image/png");
  }

  // ---------------------------------------------------------------- 改简（弹窗）
  async function editDialog(id, after) {
    let n;
    try { n = await api("/api/cards/note", { id }); await ensureOV(); } catch (e) { return showError(e); }
    const m = $("#modal");
    m.innerHTML = `<div class="modal-box yj-edit"><h3>✎ 改${esc(T("yj"))}</h3>
      <div class="yj-form-row"><label>${esc(T("yj_deck"))}<select id="eDeck">${deckOptions(n.deck)}</select></label>
        <label>类型<select id="eType">${Object.entries(TYPE_NAMES).map(([k, v]) => `<option value="${k}" ${k === n.type ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></label></div>
      ${editorFields(n)}
      <div class="row"><button class="ghost danger" id="eDel">🗑 删除这枚</button><span class="spacer"></span><button class="ghost" id="eCancel">取消</button><button class="primary" id="eSave">保存</button></div></div>`;
    m.classList.remove("hidden");
    bindEditor(m, () => document.getElementById("eType").value);
    syncTypeHint(m);
    document.getElementById("eType").onchange = () => syncTypeHint(m);
    document.getElementById("eCancel").onclick = () => m.classList.add("hidden");
    document.getElementById("eSave").onclick = async () => {
      try {
        await api("/api/cards/update", { id, deck: document.getElementById("eDeck").value, type: document.getElementById("eType").value, front: val("eFront"), back: val("eBack"), tags: val("eTags") });
        m.classList.add("hidden"); toast("已保存"); if (after) after();
      } catch (e) { showError(e); }
    };
    document.getElementById("eDel").onclick = async () => {
      if (!confirm(`删除这枚${T("yj")}？温习记录也会删掉。`)) return;
      try { await api("/api/cards/delete", { ids: [id] }); m.classList.add("hidden"); toast("已删除"); if (after) after(); } catch (e) { showError(e); }
    };
  }
  async function infoDialog(key) {
    let v;
    try { v = await api("/api/cards/info", { key }); } catch (e) { return showError(e); }
    const s = v.sched;
    const m = $("#modal");
    m.innerHTML = `<div class="modal-box yj-info"><h3>ℹ 简况</h3>
      <div class="yj-kv"><span>状态</span><b>${esc(s.state)}${s.susp ? "（暂停）" : ""}</b><span>下次</span><b>${esc(s.due || "—")}</b>
        <span>稳定度</span><b>${s.stability} 天</b><span>难度</span><b>${s.difficulty} / 10</b><span>温过</span><b>${s.reps} 次</b><span>忘记</span><b>${s.lapses} 次</b></div>
      <table class="nt-table yj-hist"><tr><th>时间</th><th>评分</th><th>用时</th><th>间隔</th></tr>
        ${v.history.map((h) => `<tr><td>${esc(h.t)}</td><td>${esc(h.rating)}</td><td>${h.secs} 秒</td><td>${h.ivl ? h.ivl + " 天" : "—"}</td></tr>`).join("") || '<tr><td colspan="4" class="muted">还没温过</td></tr>'}</table>
      <div class="row"><span class="spacer"></span><button class="primary" id="iOk">好</button></div></div>`;
    m.classList.remove("hidden");
    document.getElementById("iOk").onclick = () => m.classList.add("hidden");
  }

  // ---------------------------------------------------------------- 藏简阁
  const BR = { deck: "", q: "", filter: "", page: 0, sel: new Set(), cur: null };
  async function browseScreen() {
    await ensureOV().catch(showError);
    const s = stage();
    s.innerHTML = head(`🏛 ${esc(T("yj_browse"))}`) + `<div class="yj-browse">
      <div class="yj-bfilter"><select id="bDeck"><option value="">全部${esc(T("yj_deck"))}</option>${deckOptions(BR.deck)}</select>
        <input id="bQ" placeholder="搜正面、反面、标签…" value="${esc(BR.q)}">
        <div class="yj-chips">${[["", "全部"], ["new", T("yj_new")], ["due", "今日到期"], ["susp", "暂停"], ["leech", T("yj_leech")]].map(([k, v]) => `<a class="${BR.filter === k ? "on" : ""}" data-bf="${k}">${esc(v)}</a>`).join("")}</div></div>
      <div class="yj-bbatch" id="bBatch"></div>
      <div class="yj-btable" id="bTable">读取中…</div></div>`;
    bindBack();
    document.getElementById("bDeck").onchange = () => { BR.deck = document.getElementById("bDeck").value; BR.page = 0; loadRows(); };
    let qt = null;
    document.getElementById("bQ").oninput = () => { clearTimeout(qt); qt = setTimeout(() => { BR.q = val("bQ"); BR.page = 0; loadRows(); }, 250); };
    s.querySelectorAll("[data-bf]").forEach((a) => (a.onclick = () => { BR.filter = a.dataset.bf; s.querySelectorAll("[data-bf]").forEach((x) => x.classList.toggle("on", x === a)); BR.page = 0; loadRows(); }));
    loadRows();
  }
  async function loadRows() {
    let r;
    try { r = await api("/api/cards/search", { deck: BR.deck, q: BR.q, filter: BR.filter, page: BR.page }); } catch (e) { return showError(e); }
    BR.sel.clear();
    const box = document.getElementById("bTable");
    if (!box) return;
    const pages = Math.ceil(r.total / r.size);
    box.innerHTML = `<div class="small muted">${r.total} 张卡</div><table class="yj-table"><tr><th><input type="checkbox" id="bAll"></th><th>正面</th><th>${esc(T("yj_deck"))}</th><th>状态</th><th>下次</th><th>温/忘</th></tr>
      ${r.rows.map((x) => `<tr data-key="${esc(x.key)}" data-id="${esc(x.id)}"><td><input type="checkbox" data-sel="${esc(x.key)}"></td>
        <td class="yj-tfront">${esc(x.front)}${x.ord !== "1" ? ` <span class="tag">${esc(x.ord === "2" ? "反向" : x.ord)}</span>` : ""}${x.leech ? ` <span class="tag bad">${esc(T("yj_leech"))}</span>` : ""}</td>
        <td class="small">${esc(x.deck.replace(/::/g, " › "))}</td><td class="small">${esc(x.state)}</td><td class="small">${esc(x.due || "")}</td><td class="small">${x.reps}/${x.lapses}</td></tr>`).join("")
        || `<tr><td colspan="6" class="muted">没有符合的${esc(T("yj"))}</td></tr>`}</table>
      ${pages > 1 ? `<div class="row"><button class="ghost small" id="bPrev" ${BR.page ? "" : "disabled"}>上一页</button><span class="small">${BR.page + 1}/${pages}</span><button class="ghost small" id="bNext" ${BR.page + 1 < pages ? "" : "disabled"}>下一页</button></div>` : ""}`;
    const p = document.getElementById("bPrev"), n = document.getElementById("bNext");
    if (p) p.onclick = () => { BR.page--; loadRows(); };
    if (n) n.onclick = () => { BR.page++; loadRows(); };
    box.querySelectorAll("tr[data-key]").forEach((tr) => (tr.onclick = (e) => {
      if (e.target.matches("input")) return;
      editDialog(tr.dataset.id, loadRows);
    }));
    box.querySelectorAll("[data-sel]").forEach((cb) => (cb.onchange = () => { cb.checked ? BR.sel.add(cb.dataset.sel) : BR.sel.delete(cb.dataset.sel); batchBar(); }));
    document.getElementById("bAll").onchange = (e) => { box.querySelectorAll("[data-sel]").forEach((cb) => { cb.checked = e.target.checked; cb.checked ? BR.sel.add(cb.dataset.sel) : BR.sel.delete(cb.dataset.sel); }); batchBar(); };
    batchBar();
  }
  function batchBar() {
    const b = document.getElementById("bBatch");
    if (!b) return;
    const n = BR.sel.size;
    b.innerHTML = n ? `<span>选了 ${n} 张</span><button class="small" data-b="susp">⏸ 暂停</button><button class="small" data-b="unsusp">▶ 恢复</button>
      <button class="small" data-b="forget">↺ 重置为新</button><button class="small" data-b="info">ℹ 简况</button><button class="small" data-b="move">⇄ 移到…</button><button class="small danger" data-b="del">🗑 删除</button>` : "";
    b.querySelectorAll("[data-b]").forEach((x) => (x.onclick = async () => {
      const keys = [...BR.sel], ids = [...new Set(keys.map((k) => k.split("#")[0]))];
      try {
        const a = x.dataset.b;
        if (a === "susp" || a === "unsusp") await api("/api/cards/suspend", { keys, on: a === "susp" });
        else if (a === "forget") { if (!confirm(`把这 ${keys.length} 张卡重置为新${T("yj_unit")}？温习进度清零。`)) return; await api("/api/cards/forget", { keys }); }
        else if (a === "info") return infoDialog(keys[0]);
        else if (a === "move") {
          const d = prompt(`移到哪个${T("yj_deck")}？（整枚${T("yj")}一起移，子匣用 :: 隔开）`, BR.deck || "");
          if (!d) return;
          await api("/api/cards/move", { ids, deck: d }); OV = null;
        } else if (a === "del") { if (!confirm(`删除这 ${ids.length} 枚${T("yj")}？不能恢复。`)) return; await api("/api/cards/delete", { ids }); }
        toast("好了"); loadRows();
      } catch (e) { showError(e); }
    }));
  }

  // ---------------------------------------------------------------- 灵识图
  async function statsScreen(deck = "") {
    await ensureOV().catch(showError);
    let st;
    try { st = await api("/api/cards/stats", { deck }); } catch (e) { return showError(e); }
    const s = stage();
    const days = [];
    const end = new Date(); end.setHours(end.getHours() - 4);
    for (let i = 7 * 26 - 1 + end.getDay(); i >= 0; i--) { const d = new Date(end); d.setDate(end.getDate() - i); days.push(d.toISOString().slice(0, 10)); }
    const lvl = (n) => (!n ? 0 : n < 10 ? 1 : n < 30 ? 2 : n < 60 ? 3 : 4);
    const heat = days.map((d) => { const h = st.heat[d]; return `<i class="h${lvl(h ? h[0] : 0)}" title="${d}：${h ? h[0] + " 张 · " + Math.round(h[1] / 60) + " 分钟" : "没温"}"></i>`; }).join("");
    const fmax = Math.max(1, ...st.forecast);
    const fc = st.forecast.map((n, i) => `<div class="yj-fbar" title="${i === 0 ? "今天" : i + " 天后"}：${n} 张"><i style="height:${(n / fmax) * 100}%"></i><span>${i % 5 === 0 ? (i ? "+" + i : "今") : ""}</span></div>`).join("");
    const rt = st.ratings, rs = rt[1] + rt[2] + rt[3] + rt[4] || 1;
    s.innerHTML = head(`📊 ${esc(T("yj_stats"))}`, `<select id="sDeck"><option value="">全部${esc(T("yj_deck"))}</option>${deckOptions(deck)}</select>`) + `<div class="yj-stats">
      <div class="yj-kpis"><div><b>${st.streak}</b><span>连续温简天数</span></div><div><b>${st.total_reviews}</b><span>累计温过</span></div>
        <div><b>${st.retention == null ? "—" : (st.retention * 100).toFixed(1) + "%"}</b><span>近 30 天记住率</span></div><div><b>${st.mature}</b><span>间隔 ≥21 天（已熟）</span></div></div>
      <div class="card"><h3>温简热力（近半年）</h3><div class="yj-heat">${heat}</div></div>
      <div class="card"><h3>未来 30 天到期</h3><div class="yj-fc">${fc}</div></div>
      <div class="card yj-two"><div><h3>${esc(T("yj"))}现状</h3>${Object.entries(st.states).map(([k, v]) => `<div class="row small"><span>${esc(k)}</span><span class="spacer"></span><b>${v}</b></div>`).join("")}</div>
        <div><h3>近 30 天评分</h3>${[1, 2, 3, 4].map((k) => `<div class="yj-rbar r${k}"><span>${esc(T("yj_r" + k))}</span><i style="width:${(rt[k] / rs) * 100}%"></i><b>${rt[k]}</b></div>`).join("")}</div></div></div>`;
    bindBack();
    document.getElementById("sDeck").onchange = () => statsScreen(document.getElementById("sDeck").value);
  }

  // ---------------------------------------------------------------- 导入
  async function importScreen() {
    await ensureOV().catch(showError);
    const s = stage();
    s.innerHTML = head("📥 导入") + `<div class="yj-import card">
      <p>导入 <b>Anki 导出的纯文本</b>（「导出 → 纯文本格式的笔记」，每行 正面⇥反面⇥标签），或者 anki-expert 出的 .tsv / 卡片表格。<br>
        <span class="small muted">正面里有 {{c1::…}} 的自动当填空卡；Anki 的粗体、换行、列表会转成 Markdown。图片要另外放进库里。</span></p>
      <div class="yj-form-row"><label>导入到${esc(T("yj_deck"))}<select id="iDeck">${deckOptions(ADD.deck || OV?.decks?.[0]?.name)}</select></label>
        <label class="ghost">选文件 <input type="file" id="iFile" accept=".txt,.tsv,.csv,.md"></label></div>
      <textarea id="iText" rows="12" placeholder="或者直接粘贴：每行一张卡，正面和反面之间用 Tab 隔开"></textarea>
      <div class="row"><span class="small muted" id="iMsg"></span><span class="spacer"></span><button class="primary" id="iGo">导入</button></div></div>`;
    bindBack();
    document.getElementById("iFile").onchange = (e) => {
      const f = e.target.files[0]; if (!f) return;
      const rd = new FileReader(); rd.onload = () => { document.getElementById("iText").value = rd.result; }; rd.readAsText(f, "utf-8");
    };
    document.getElementById("iGo").onclick = async () => {
      let text = document.getElementById("iText").value;
      if (!text.trim()) return toast("先粘贴或选一个文件");
      if (!text.includes("\t") && /^\s*[^|\n]+\|[^|\n]+/m.test(text) && !/^#separator/m.test(text)) text = "#separator:pipe\n" + text;
      try {
        const r = await api("/api/cards/import", { deck: document.getElementById("iDeck").value, text });
        document.getElementById("iMsg").textContent = `导入了 ${r.added} 张${r.skipped ? `，跳过 ${r.skipped} 行（格式不对或正反面是空的）` : ""}`;
        OV = null;
      } catch (e) { showError(e); }
    };
  }

  // 心跳：正在温简、页面看得见、2 分钟内有操作 → 计进“修炼 · 复习”（服务器还会核对 2 分半内真的答过卡）
  const active = () => MODE === "review" && !!R && document.visibilityState === "visible" && Date.now() - lastActive < 120000;
  const board = () => (R && R.deck ? R.deck.split("::")[0] : "");
  window.CARDS = { hubHtml, bindHub, review, open, close: closeStage, isOpen: () => !!MODE, active, board };
})();
