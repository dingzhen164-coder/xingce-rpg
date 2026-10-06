/* 灵台手札：手写笔记本（像 Notability）+ 🧙 师傅编纂（手写 → Markdown）+ 📚 调阅库里的 Markdown 笔记。
   数据：/api/notes（本子列表）、/api/notes/get|save|delete|compile、/api/notes/tree、/api/notes/md（见 rpg/notes.py）。
   - 每页是“纸”上的逻辑坐标（宽 1000、高 1414），屏幕多大都对得上；两层画布：底下纸（横线 / 方格 / 空白），上面笔迹。
   - 平板上用过手写笔之后，手指只滚动、不写字（防手掌误触）；电脑上鼠标直接写。
   - 写完自动保存到库里 训练/手札/手写/（坚果云同步）；师傅编纂把每页画成白底图片交给电脑，排成 Markdown 存到 训练/手札/。
   - 调阅：左边列出库里所有 .md，点开在阅读栏里看（标题、列表、表格、引用、图片都排好）；可以和本子左右并排，边看边记。 */
(function () {
  const PW = 1000, PH = 1414;
  const COLORS = ["#222222", "#1e63d6", "#e53935", "#2e9d57"];
  const WIDTHS = [2, 3.5, 6];
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  let BOOKS = [], INFO = { vision: false, ai: false };
  let TAB = "books";          // 左栏：books 手札 / library 调阅
  let NB = null;              // 打开的本子 {id, title, paper, pages, text, compiled}
  let READ = null;            // 阅读栏里的笔记 {path, name, text, images}
  let FILES = null, FQ = "";  // 库里的 md、搜索
  let tool = { t: "pen", c: COLORS[0], w: WIDTHS[1] };
  let undo = [], redo = [];   // [{page, stroke}]
  let penSeen = false, saveT = null, dirty = false, busy = false;

  // ---------------------------------------------------------------- 页面
  async function render(v) {
    try {
      const r = await api("/api/notes");
      BOOKS = r.notebooks; INFO = r;
    } catch (e) { v.innerHTML = `<div class="card"><p class="muted">${esc(e.message)}</p></div>`; return; }
    v.innerHTML = `<div class="notes" id="notesRoot">${side()}<section class="nt-main" id="ntMain"></section></div>`;
    fit();
    paintMain();
    bindSide();
  }
  function fit() {
    const el = document.getElementById("notesRoot");
    if (el) el.style.height = Math.max(420, innerHeight - el.getBoundingClientRect().top - 12) + "px";
  }
  addEventListener("resize", () => { if (VIEW === "notes" && document.getElementById("notesRoot")) { fit(); sizePages(); } });

  function side() {
    const books = BOOKS.map((b) => `<button class="nt-item ${NB && NB.id === b.id ? "on" : ""}" data-nb="${esc(b.id)}">
        <b>${esc(b.title)}</b><small>${esc(b.updated.slice(5, 16))} · ${b.pages} 页${b.compiled ? " · 已编纂" : ""}</small></button>`).join("");
    return `<aside class="nt-side"><div class="nt-tabs"><button class="${TAB === "books" ? "on" : ""}" data-ntab="books">📓 手札</button>
        <button class="${TAB === "library" ? "on" : ""}" data-ntab="library">📚 调阅</button></div>
      <div class="nt-list" id="ntList">${TAB === "books"
        ? `<button class="primary nt-new" id="ntNew">＋ 新本子</button>${books || '<p class="small muted">还没有手札。点上面「新本子」开始写。</p>'}`
        : `<input id="ntQ" placeholder="搜库里的笔记（文件名 / 文件夹）" value="${esc(FQ)}"><div id="ntFiles">${filesHtml()}</div>`}</div></aside>`;
  }
  function filesHtml() {
    if (!FILES) return '<p class="small muted">读取中…</p>';
    const q = FQ.trim().toLowerCase();
    const hit = FILES.filter((f) => !q || f.path.toLowerCase().includes(q)).slice(0, 400);
    if (!hit.length) return '<p class="small muted">没有找到。</p>';
    let html = "", dir = null;
    for (const f of hit) {
      if (f.dir !== dir) { dir = f.dir; html += `<div class="nt-dir">${esc(dir || "（库根目录）")}</div>`; }
      html += `<button class="nt-file ${READ && READ.path === f.path ? "on" : ""}" data-md="${esc(f.path)}">${esc(f.name)}</button>`;
    }
    return html + (FILES.length > 400 && !q ? '<p class="small faint">文件很多，只列了前 400 个；用上面的搜索找。</p>' : "");
  }
  function bindSide() {
    document.querySelectorAll("[data-ntab]").forEach((b) => (b.onclick = async () => {
      TAB = b.dataset.ntab;
      repaintSide();
      if (TAB === "library" && !FILES) {
        try { FILES = (await api("/api/notes/tree")).files; } catch (e) { FILES = []; showError(e); }
        const box = document.getElementById("ntFiles"); if (box) { box.innerHTML = filesHtml(); bindSide(); }
      }
    }));
    const nn = document.getElementById("ntNew");
    if (nn) nn.onclick = newBook;
    document.querySelectorAll("[data-nb]").forEach((b) => (b.onclick = () => openBook(b.dataset.nb)));
    document.querySelectorAll("[data-md]").forEach((b) => (b.onclick = () => openMd(b.dataset.md)));
    const q = document.getElementById("ntQ");
    if (q) q.oninput = () => { FQ = q.value; document.getElementById("ntFiles").innerHTML = filesHtml(); bindSide(); };
  }
  function repaintSide() {
    const old = document.querySelector(".nt-side");
    if (!old) return;
    const focus = document.activeElement && document.activeElement.id === "ntQ";
    old.outerHTML = side();
    bindSide();
    if (focus) { const q = document.getElementById("ntQ"); q.focus(); q.setSelectionRange(q.value.length, q.value.length); }
  }

  function paintMain() {
    const m = document.getElementById("ntMain");
    if (!m) return;
    m.className = "nt-main" + (READ && NB ? " split" : "");
    if (!READ && !NB) {
      m.innerHTML = `<div class="nt-empty"><div class="nt-empty-mark">🪶</div><h2>灵台手札</h2>
        <p>像在纸上一样手写笔记：选纸（横线 / 方格 / 空白）、换笔、荧光笔、橡皮、撤销。写完自动存进库里，平板上写的电脑上也有。</p>
        <p>写完点底下的「🧙 师傅编纂」，师傅把手写认出来，排成一份 Markdown 笔记存进 训练/手札/。</p>
        <p>左边「📚 调阅」能翻库里所有的 Markdown 笔记，还能和本子并排打开，边看边记。</p>
        <button class="primary" id="ntNew2">＋ 新本子</button></div>`;
      document.getElementById("ntNew2").onclick = newBook;
      return;
    }
    m.innerHTML = (READ ? readerHtml() : "") + (NB ? bookHtml() : "");
    if (READ) bindReader();
    if (NB) bindBook();
  }

  // ---------------------------------------------------------------- 本子
  async function newBook() {
    if (!(await flush())) return;
    try {
      const r = await api("/api/notes/save", { title: "", paper: "lines", pages: [{ strokes: [] }], text: "" });
      NB = await api("/api/notes/get", { id: r.id });
      BOOKS = (await api("/api/notes")).notebooks;
      undo = []; redo = [];
      TAB = "books"; repaintSide(); paintMain();
    } catch (e) { showError(e); }
  }
  async function openBook(id) {
    if (NB && NB.id === id) return;
    if (!(await flush())) return;
    try { NB = await api("/api/notes/get", { id }); undo = []; redo = []; repaintSide(); paintMain(); } catch (e) { showError(e); }
  }
  function bookHtml() {
    const sel = (v, t) => `<option value="${v}" ${NB.paper === v ? "selected" : ""}>${t}</option>`;
    return `<div class="nt-book">
      <div class="nt-bar">
        <input class="nt-title" id="ntTitle" value="${esc(NB.title)}" maxlength="60" title="本子名字（编纂出的 Markdown 也用这个名字）">
        <select id="ntPaper" title="纸">${sel("lines", "横线纸")}${sel("grid", "方格纸")}${sel("blank", "白纸")}</select>
        <span class="nt-tools">
          ${COLORS.map((c) => `<button class="nt-dot ${tool.t === "pen" && tool.c === c ? "on" : ""}" data-col="${c}" style="--c:${c}" title="笔"></button>`).join("")}
          ${WIDTHS.map((w, i) => `<button class="nt-w ${tool.t !== "er" && tool.w === w ? "on" : ""}" data-w="${w}" title="${["细", "中", "粗"][i]}"><i style="height:${w}px"></i></button>`).join("")}
          <button class="${tool.t === "hl" ? "on" : ""}" data-tool="hl" title="荧光笔">🖍</button>
          <button class="${tool.t === "er" ? "on" : ""}" data-tool="er" title="橡皮">🧽</button>
          <button data-act="undo" title="撤销（Ctrl+Z）" ${undo.length ? "" : "disabled"}>↶</button>
          <button data-act="redo" title="重做（Ctrl+Y）" ${redo.length ? "" : "disabled"}>↷</button>
        </span>
        <span class="spacer"></span>
        <span class="small faint" id="ntSaved"></span>
        <button class="ghost small" id="ntClose" title="收起本子（已自动保存）">✕</button>
      </div>
      <div class="nt-pages" id="ntPages">${NB.pages.map((_, i) => pageHtml(i)).join("")}
        <button class="ghost nt-addpage" id="ntAdd">＋ 加一页</button></div>
      <div class="nt-foot">
        <details class="nt-typed" ${NB.text ? "open" : ""}><summary>⌨ 打字补充 <span class="small faint">（编纂时一起交给师傅；认不清的字可以在这里打）</span></summary>
          <textarea id="ntText" rows="3" placeholder="打字记的要点…">${esc(NB.text || "")}</textarea></details>
        <div class="row nt-foot-row"><span class="small muted">${INFO.vision ? "🧙 编纂用识图模型认手写" : INFO.ai ? "🧙 编纂用电脑自带 OCR 认手写、AI 排版（手写认不准时可在设置里填识图模型）" : "没填 AI：编纂只能用 OCR 认字，不排版"}${
          NB.compiled ? ` · 上次编纂：<a data-md="${esc(NB.compiled)}">${esc(NB.compiled)}</a>` : ""}</span><span class="spacer"></span>
          <button class="ghost" id="ntDel">🗑 删除本子</button>
          <button class="primary" id="ntCompile">🧙 师傅编纂</button></div>
      </div></div>`;
  }
  function pageHtml(i) {
    return `<div class="nt-page" data-pg="${i}"><canvas class="nt-bg"></canvas><canvas class="nt-ink" data-pg="${i}"></canvas><span class="nt-pno">${i + 1}</span></div>`;
  }
  function bindBook() {
    sizePages();
    document.querySelectorAll(".nt-ink").forEach(bindInk);
    const $$ = (id) => document.getElementById(id);
    $$("ntTitle").oninput = () => { NB.title = $$("ntTitle").value; queueSave(); };
    $$("ntPaper").onchange = () => { NB.paper = $$("ntPaper").value; sizePages(); queueSave(); };
    $$("ntText").oninput = () => { NB.text = $$("ntText").value; queueSave(); };
    $$("ntAdd").onclick = () => {
      NB.pages.push({ strokes: [] });
      const add = $$("ntAdd");
      add.insertAdjacentHTML("beforebegin", pageHtml(NB.pages.length - 1));
      const pg = add.previousElementSibling;
      sizePages(); bindInk(pg.querySelector(".nt-ink"));
      pg.scrollIntoView({ behavior: "smooth", block: "start" });
      queueSave();
    };
    $$("ntClose").onclick = async () => { if (await flush()) { NB = null; repaintSide(); paintMain(); } };
    $$("ntDel").onclick = async () => {
      if (!confirm(`删除手札「${NB.title}」？手写的笔迹会删掉（已经编纂出的 Markdown 留着）。`)) return;
      try { await api("/api/notes/delete", { id: NB.id }); NB = null; BOOKS = (await api("/api/notes")).notebooks; repaintSide(); paintMain(); }
      catch (e) { showError(e); }
    };
    $$("ntCompile").onclick = compile;
    document.querySelectorAll(".nt-tools [data-col]").forEach((b) => (b.onclick = () => { tool = { t: "pen", c: b.dataset.col, w: tool.t === "pen" ? tool.w : WIDTHS[1] }; syncTools(); }));
    document.querySelectorAll(".nt-tools [data-w]").forEach((b) => (b.onclick = () => { if (tool.t === "er") tool.t = "pen"; tool.w = Number(b.dataset.w); syncTools(); }));
    document.querySelectorAll(".nt-tools [data-tool]").forEach((b) => (b.onclick = () => { tool.t = tool.t === b.dataset.tool ? "pen" : b.dataset.tool; syncTools(); }));
    document.querySelectorAll(".nt-tools [data-act]").forEach((b) => (b.onclick = () => (b.dataset.act === "undo" ? doUndo() : doRedo())));
    document.querySelectorAll(".nt-foot [data-md]").forEach((a) => (a.onclick = () => openMd(a.dataset.md)));
  }
  function syncTools() {
    const bar = document.querySelector(".nt-tools");
    if (!bar) return;
    bar.querySelectorAll("[data-col]").forEach((b) => b.classList.toggle("on", tool.t === "pen" && tool.c === b.dataset.col));
    bar.querySelectorAll("[data-w]").forEach((b) => b.classList.toggle("on", tool.t !== "er" && tool.w === Number(b.dataset.w)));
    bar.querySelectorAll("[data-tool]").forEach((b) => b.classList.toggle("on", tool.t === b.dataset.tool));
    bar.querySelector("[data-act=undo]").disabled = !undo.length;
    bar.querySelector("[data-act=redo]").disabled = !redo.length;
  }

  // ---------------------------------------------------------------- 画
  function sizePages() {
    document.querySelectorAll(".nt-page").forEach((pg) => {
      const w = pg.clientWidth;
      if (!w) return;
      const h = Math.round(w * PH / PW), dpr = window.devicePixelRatio || 1;
      pg.style.height = h + "px";
      pg.querySelectorAll("canvas").forEach((c) => { c.width = Math.round(w * dpr); c.height = Math.round(h * dpr); c.style.width = w + "px"; c.style.height = h + "px"; });
      drawPaper(pg.querySelector(".nt-bg"));
      repaint(Number(pg.dataset.pg));
    });
  }
  function drawPaper(c) {
    const x = c.getContext("2d"), k = c.width / PW;
    x.setTransform(k, 0, 0, k, 0, 0);
    x.fillStyle = "#fffdf6"; x.fillRect(0, 0, PW, PH);
    x.lineWidth = 1.2;
    if (NB.paper === "lines") {
      x.strokeStyle = "rgba(70, 120, 190, .22)";
      for (let y = 120; y < PH - 40; y += 46) { x.beginPath(); x.moveTo(40, y); x.lineTo(PW - 40, y); x.stroke(); }
      x.strokeStyle = "rgba(210, 70, 70, .25)"; x.beginPath(); x.moveTo(110, 40); x.lineTo(110, PH - 40); x.stroke();
    } else if (NB.paper === "grid") {
      x.strokeStyle = "rgba(70, 120, 190, .16)";
      for (let g = 40; g < PW; g += 40) { x.beginPath(); x.moveTo(g, 0); x.lineTo(g, PH); x.stroke(); }
      for (let g = 40; g < PH; g += 40) { x.beginPath(); x.moveTo(0, g); x.lineTo(PW, g); x.stroke(); }
    }
  }
  function strokeOn(x, s) {
    const p = s.p;
    if (!p.length) return;
    x.save();
    x.globalCompositeOperation = s.t === "er" ? "destination-out" : "source-over";
    x.globalAlpha = s.t === "hl" ? 0.32 : 1;
    x.strokeStyle = x.fillStyle = s.c;
    x.lineCap = x.lineJoin = "round";
    x.lineWidth = s.w;
    if (p.length === 1) { x.beginPath(); x.arc(p[0][0], p[0][1], s.w / 2, 0, Math.PI * 2); x.fill(); }
    else {
      x.beginPath(); x.moveTo(p[0][0], p[0][1]);
      for (let i = 1; i < p.length - 1; i++) x.quadraticCurveTo(p[i][0], p[i][1], (p[i][0] + p[i + 1][0]) / 2, (p[i][1] + p[i + 1][1]) / 2);
      x.lineTo(p[p.length - 1][0], p[p.length - 1][1]); x.stroke();
    }
    x.restore();
  }
  function inkCtx(i) {
    const c = document.querySelector(`.nt-ink[data-pg="${i}"]`);
    if (!c) return null;
    const x = c.getContext("2d"), k = c.width / PW;
    x.setTransform(k, 0, 0, k, 0, 0);
    return x;
  }
  function repaint(i, extra) {
    const x = inkCtx(i);
    if (!x) return;
    x.clearRect(0, 0, PW, PH);
    for (const s of NB.pages[i].strokes) strokeOn(x, s);
    if (extra) strokeOn(x, extra);
  }
  function bindInk(c) {
    const i = Number(c.dataset.pg);
    c.style.touchAction = penSeen ? "pan-y" : "none";
    let cur = null;
    const pt = (e) => { const r = c.getBoundingClientRect(); return [Math.round((e.clientX - r.left) * PW / r.width * 10) / 10, Math.round((e.clientY - r.top) * PH / r.height * 10) / 10]; };
    c.onpointerdown = (e) => {
      if (e.pointerType === "pen" && !penSeen) {                 // 用过手写笔：之后手指只滚动（防手掌误触）
        penSeen = true;
        document.querySelectorAll(".nt-ink").forEach((k) => (k.style.touchAction = "pan-y"));
      }
      if (e.pointerType === "touch" && penSeen) return;
      if (e.button > 0 && e.button !== 5) return;
      e.preventDefault();
      c.setPointerCapture(e.pointerId);
      const er = tool.t === "er" || e.button === 5;
      cur = { t: er ? "er" : tool.t, c: tool.t === "hl" ? "#f5d000" : tool.c, w: er ? 26 : tool.t === "hl" ? 22 : tool.w, p: [pt(e)] };
      repaint(i, cur);
    };
    c.onpointermove = (e) => {
      if (!cur) return;
      const evs = e.getCoalescedEvents ? e.getCoalescedEvents() : [e];
      for (const ev of evs) cur.p.push(pt(ev));
      repaint(i, cur);
    };
    c.onpointerup = c.onpointercancel = () => {
      if (!cur) return;
      NB.pages[i].strokes.push(cur);
      undo.push({ page: i, stroke: cur }); redo = [];
      cur = null;
      repaint(i); syncTools(); queueSave();
    };
  }
  function doUndo() {
    const u = undo.pop(); if (!u) return;
    const arr = NB.pages[u.page].strokes, k = arr.lastIndexOf(u.stroke);
    if (k >= 0) arr.splice(k, 1);
    redo.push(u); repaint(u.page); syncTools(); queueSave();
  }
  function doRedo() {
    const u = redo.pop(); if (!u) return;
    NB.pages[u.page].strokes.push(u.stroke);
    undo.push(u); repaint(u.page); syncTools(); queueSave();
  }
  document.addEventListener("keydown", (e) => {
    if (VIEW !== "notes" || !NB || /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName || "")) return;
    const k = e.key.toLowerCase();
    if ((e.ctrlKey || e.metaKey) && k === "z" && !e.shiftKey) { doUndo(); e.preventDefault(); }
    else if ((e.ctrlKey || e.metaKey) && (k === "y" || (k === "z" && e.shiftKey))) { doRedo(); e.preventDefault(); }
  });

  // ---------------------------------------------------------------- 存
  function queueSave() {
    dirty = true;
    const s = document.getElementById("ntSaved"); if (s) s.textContent = "…";
    clearTimeout(saveT);
    saveT = setTimeout(flush, 1200);
  }
  async function flush() {
    clearTimeout(saveT);
    if (!NB || !dirty) return true;
    try {
      const r = await api("/api/notes/save", { id: NB.id, title: NB.title, paper: NB.paper, pages: NB.pages, text: NB.text });
      dirty = false;
      const b = BOOKS.find((x) => x.id === NB.id);
      if (b && (b.title !== r.title || b.pages !== NB.pages.length)) { b.title = r.title; b.pages = NB.pages.length; repaintSide(); }
      const s = document.getElementById("ntSaved"); if (s) s.textContent = "已保存 " + r.updated.slice(11, 16);
      return true;
    } catch (e) { showError(e); return false; }
  }
  addEventListener("beforeunload", () => { if (NB && dirty) navigator.sendBeacon?.("/api/notes/save", new Blob([JSON.stringify({ id: NB.id, title: NB.title, paper: NB.paper, pages: NB.pages, text: NB.text })], { type: "application/json" })); });

  // ---------------------------------------------------------------- 师傅编纂
  function pageImages() {
    const out = [];
    NB.pages.forEach((pg) => {
      if (!pg.strokes.some((s) => s.t !== "er")) return;
      const c = document.createElement("canvas");
      c.width = PW; c.height = PH;
      const ink = document.createElement("canvas");
      ink.width = PW; ink.height = PH;
      const ix = ink.getContext("2d");
      for (const s of pg.strokes) strokeOn(ix, s);
      const x = c.getContext("2d");
      x.fillStyle = "#ffffff"; x.fillRect(0, 0, PW, PH);
      x.drawImage(ink, 0, 0);
      out.push(c.toDataURL("image/png"));
    });
    return out;
  }
  async function compile() {
    if (busy) return;
    if (!(await flush())) return;
    const b = document.getElementById("ntCompile");
    busy = true; b.disabled = true; b.textContent = "🧙 师傅编纂中…（几十秒）";
    try {
      const r = await api("/api/notes/compile", { id: NB.id, images: pageImages(), text: NB.text || "" });
      NB.compiled = r.path;
      READ = { path: r.path, name: r.path.split("/").pop().replace(/\.md$/, ""), text: r.markdown, images: {} };
      toast(`🧙 编纂好了（${esc(r.how)}）：存在 ${esc(r.path)}`);
      BOOKS = (await api("/api/notes")).notebooks;
      repaintSide(); paintMain();
    } catch (e) { showError(e); }
    busy = false;
    const b2 = document.getElementById("ntCompile"); if (b2) { b2.disabled = false; b2.textContent = "🧙 师傅编纂"; }
  }

  // ---------------------------------------------------------------- 阅读栏
  async function openMd(path) {
    try {
      READ = await api("/api/notes/md", { p: path });
      if (TAB === "library") repaintSide();
      paintMain();
    } catch (e) { showError(e); }
  }
  function readerHtml() {
    return `<div class="nt-reader"><div class="nt-rbar"><b>📖 ${esc(READ.name)}</b><span class="small faint">${esc(READ.path)}</span><span class="spacer"></span>
        ${NB ? "" : `<button class="ghost small" id="ntNewBeside" title="开一本手札放在旁边，边看边记">＋ 旁边记手札</button>`}
        <button class="ghost small" id="ntRClose">✕</button></div>
      <div class="nt-md">${mdRender(READ.text, READ.images || {})}</div></div>`;
  }
  function bindReader() {
    document.getElementById("ntRClose").onclick = () => { READ = null; repaintSide(); paintMain(); };
    const nb = document.getElementById("ntNewBeside"); if (nb) nb.onclick = () => (BOOKS.length ? openBook(BOOKS[0].id) : newBook());
    document.querySelectorAll(".nt-md [data-wiki]").forEach((a) => (a.onclick = async () => {
      if (!FILES) { try { FILES = (await api("/api/notes/tree")).files; } catch (e) { FILES = []; } }
      const name = a.dataset.wiki.split("#")[0].split("/").pop();
      const f = FILES.find((x) => x.name === name);
      f ? openMd(f.path) : toast("库里没找到「" + esc(name) + "」");
    }));
    document.querySelectorAll(".nt-md img").forEach((im) => (im.onclick = () => window.zoomImg && zoomImg(im.src)));
  }

  // 小型 Markdown 排版：标题、段落、粗斜体、行内代码、代码块、列表、引用 / Obsidian 提示块、表格、分隔线、图片、[[链接]]
  function mdRender(text, images) {
    const img = (name) => { const p = images[name] || images[name.trim()]; return p ? `<img src="/vault-file?p=${encodeURIComponent(p)}" alt="">` : `<span class="faint">［图：${esc(name)}］</span>`; };
    const inline = (s) => esc(s)
      .replace(/!\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]/g, (_, n) => img(n.replace(/&amp;/g, "&")))
      .replace(/!\[[^\]]*\]\(([^)\s]+)\)/g, (_, n) => img(n.replace(/&amp;/g, "&")))
      .replace(/\[\[([^\]|]+)\|([^\]]+)\]\]/g, (_, a, b) => `<a data-wiki="${a}">${b}</a>`)
      .replace(/\[\[([^\]]+)\]\]/g, (_, a) => `<a data-wiki="${a}">${a}</a>`)
      .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/==(.+?)==/g, "<mark>$1</mark>")
      .replace(/(^|[^*])\*([^*\s][^*]*?)\*/g, "$1<i>$2</i>").replace(/~~(.+?)~~/g, "<s>$1</s>");
    let lines = String(text || "").replace(/\r\n/g, "\n").split("\n");
    let out = "";
    if (lines[0] === "---") {                                   // frontmatter：收成一小块
      const end = lines.indexOf("---", 1);
      if (end > 0) { out += `<details class="nt-fm"><summary>属性</summary><pre>${esc(lines.slice(1, end).join("\n"))}</pre></details>`; lines = lines.slice(end + 1); }
    }
    for (let i = 0; i < lines.length; i++) {
      const l = lines[i];
      if (/^```/.test(l)) {
        const buf = []; i++;
        while (i < lines.length && !/^```/.test(lines[i])) buf.push(lines[i++]);
        out += `<pre><code>${esc(buf.join("\n"))}</code></pre>`; continue;
      }
      let m;
      if ((m = l.match(/^(#{1,6})\s+(.*)$/))) { out += `<h${m[1].length}>${inline(m[2])}</h${m[1].length}>`; continue; }
      if (/^\s*(---|\*\*\*|___)\s*$/.test(l)) { out += "<hr>"; continue; }
      if (/^\s*>/.test(l)) {
        const buf = [];
        while (i < lines.length && /^\s*>/.test(lines[i])) buf.push(lines[i++].replace(/^\s*>\s?/, ""));
        i--;
        const head = buf[0] && buf[0].match(/^\[!(\w+)\][-+]?\s*(.*)$/);
        if (head) out += `<div class="nt-callout nt-co-${esc(head[1].toLowerCase())}"><div class="nt-co-title">${inline(head[2] || head[1])}</div>${mdRender(buf.slice(1).join("\n"), images)}</div>`;
        else out += `<blockquote>${mdRender(buf.join("\n"), images)}</blockquote>`;
        continue;
      }
      if (/^\s*\|.*\|\s*$/.test(l) && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
        const row = (s) => s.trim().replace(/^\||\|$/g, "").split(/(?<!\\)\|/).map((c) => c.trim());
        const head = row(l); i += 2;
        const rows = [];
        while (i < lines.length && /^\s*\|/.test(lines[i])) rows.push(row(lines[i++]));
        i--;
        out += `<div class="tbl-wrap"><table class="nt-table"><thead><tr>${head.map((h) => `<th>${inline(h)}</th>`).join("")}</tr></thead><tbody>${
          rows.map((r) => `<tr>${r.map((c) => `<td>${inline(c.replace(/\\\|/g, "|"))}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
        continue;
      }
      if (/^\s*([-*+]|\d+[.)])\s+/.test(l)) {
        const ordered = /^\s*\d/.test(l), buf = [];
        while (i < lines.length && /^\s*([-*+]|\d+[.)])\s+/.test(lines[i])) {
          const t = lines[i].replace(/^\s*([-*+]|\d+[.)])\s+/, ""), pad = lines[i].match(/^\s*/)[0].length;
          const task = t.match(/^\[( |x)\]\s+(.*)$/i);
          buf.push(`<li style="margin-left:${Math.min(pad, 12) * 0.8}em">${task ? (task[1].trim() ? "☑ " : "☐ ") + inline(task[2]) : inline(t)}</li>`);
          i++;
        }
        i--;
        out += ordered ? `<ol>${buf.join("")}</ol>` : `<ul>${buf.join("")}</ul>`;
        continue;
      }
      if (!l.trim()) continue;
      const buf = [l];
      while (i + 1 < lines.length && lines[i + 1].trim() && !/^(#{1,6}\s|```|\s*>|\s*([-*+]|\d+[.)])\s|\s*\|)/.test(lines[i + 1])) buf.push(lines[++i]);
      out += `<p>${buf.map(inline).join("<br>")}</p>`;
    }
    return out;
  }

  window.NOTES = { render, flush, mdRender };
})();
