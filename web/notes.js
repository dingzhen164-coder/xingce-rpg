/* 灵台手札：手写笔记本（像 Notability）+ 📄 导出 PDF + 📚 调阅库里的 Markdown 笔记。
   数据：/api/notes（本子列表）、/api/notes/get|save|delete|compile、/api/notes/tree、/api/notes/md（见 rpg/notes.py）。
   - 每页是“纸”上的逻辑坐标（宽 1000、高 1414），屏幕多大都对得上；两层画布：底下纸（横线 / 方格 / 空白），上面笔迹。
   - 平板上用过手写笔之后，手指只滚动、不写字（防手掌误触）；电脑上鼠标直接写。
   - 写完自动保存到库里 训练/手札/手写/（坚果云同步）；导出 PDF 把每页（纸 + 笔迹）画成图片交给电脑，拼成 A4 PDF 存到 训练/手札/导出/。
   - 调阅：左边列出库里所有 .md，点开在阅读栏里看（标题、列表、表格、引用、图片都排好）；可以和本子左右并排，边看边记。
   - 调阅 PDF：库里的 .pdf 也列出来（📕），点开是一本“PDF 批注本”：每页底图是 PDF 那一页（/notes-pdfpage 现渲染），
     上面照常用笔、荧光笔、橡皮勾画，自动保存；「📄 导出批注 PDF」把笔迹叠到原 PDF 上存到 训练/手札/导出/。
     PDF 页数多：只有滚到附近的页才给画布分配内存（IntersectionObserver），滚远了就释放。 */
(function () {
  const PW = 1000, PH = 1414;
  const ph = (i) => (NB && NB.pdf ? (NB.pages[i] && NB.pages[i].h) || PH : PH);     // 这一页的高度（PDF 每页比例不同）
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
  let saveT = null, dirty = false, busy = false;
  let lastWrite = 0;          // 最后一次落笔 / 打字的时刻：记笔记算复习时间，停笔超过 1 分钟就不算（app.js 心跳读）
  const LS = { get: (k, d) => { try { return localStorage.getItem(k) ?? d; } catch (e) { return d; } }, set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) {} } };
  // 手指：draw 写字 / scroll 只翻页。用过一次手写笔就自动变成 scroll（像 Notability），每台设备记住；工具栏 👆 可以切
  let FINGER = LS.get("xrpg-nt-finger", "draw");
  let SIDE_MIN = LS.get("xrpg-nt-side", "") === "min";          // 左栏收起
  const OPEN = new Set(JSON.parse(LS.get("xrpg-nt-open", "[]")));   // 调阅里展开的板块
  const touchDev = () => document.documentElement.classList.contains("touch") || matchMedia("(pointer: coarse)").matches;

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
    if (PENDING) { const p = PENDING; PENDING = null; openPdf(p); }     // 从藏经阁「功法 · 教材」点过来的 PDF
  }
  let PENDING = null;
  function fit() {
    const el = document.getElementById("notesRoot");
    if (el) el.style.height = Math.max(420, innerHeight - el.getBoundingClientRect().top - 12) + "px";
  }
  addEventListener("resize", () => {
    if (VIEW === "notes" && document.getElementById("notesRoot")) { const keep = NB ? curPos() : null; fit(); if (NB) { sizePages(); restorePos(keep); } }
  });

  function side() {
    const books = BOOKS.map((b) => `<button class="nt-item ${NB && NB.id === b.id ? "on" : ""}" data-nb="${esc(b.id)}">
        <span class="nt-del" data-del="${esc(b.id)}" title="${b.pdf ? "删除这本批注（原 PDF 不动）" : "删除这本手札"}">🗑</span><b>${b.pdf ? "📕 " : ""}${esc(b.title)}</b><small>${esc(b.updated.slice(5, 16))} · ${b.pages} 页</small></button>`).join("");
    if (SIDE_MIN) return `<aside class="nt-side min"><button class="nt-sidebtn" id="ntSideOpen" title="展开左栏">»</button>
        <button class="nt-sidebtn ${TAB === "books" ? "on" : ""}" data-ntab="books" title="手札">📓</button>
        <button class="nt-sidebtn ${TAB === "library" ? "on" : ""}" data-ntab="library" title="调阅">📚</button></aside>`;
    return `<aside class="nt-side"><div class="nt-tabs"><button class="${TAB === "books" ? "on" : ""}" data-ntab="books">📓 手札</button>
        <button class="${TAB === "library" ? "on" : ""}" data-ntab="library">📚 调阅</button>
        <button class="nt-fold" id="ntSideMin" title="收起左栏">«</button></div>
      <div class="nt-list" id="ntList">${TAB === "books"
        ? `<button class="primary nt-new" id="ntNew">＋ 新本子</button>${books || '<p class="small muted">还没有手札。点上面「新本子」开始写。</p>'}`
        : `<input id="ntQ" placeholder="搜库里的笔记（文件名 / 文件夹）" value="${esc(FQ)}"><div id="ntFiles">${filesHtml()}</div>`}</div></aside>`;
  }
  function filesHtml() {
    if (!FILES) return '<p class="small muted">读取中…</p>';
    const q = FQ.trim().toLowerCase();
    const hit = FILES.filter((f) => !q || f.path.toLowerCase().includes(q)).slice(0, 400);
    if (!FILES.length) return '<p class="small muted">库里没找到行测各板块的文件夹（如「言语之逻辑填空」「资料分析」）。</p>';
    if (q && !hit.length) return '<p class="small muted">没有找到。</p>';
    const tops = [...new Set(FILES.map((f) => f.top))];
    let html = "";
    for (const top of tops) {
      const mine = (q ? hit : FILES).filter((f) => f.top === top);
      if (q && !mine.length) continue;
      const open = q || OPEN.has(top);
      html += `<button class="nt-top ${open ? "open" : ""}" data-top="${esc(top)}"><i>${open ? "▾" : "▸"}</i>${esc(top)}<small>${FILES.filter((f) => f.top === top).length}</small></button>`;
      if (!open) continue;
      let dir = top;
      html += '<div class="nt-sub">';
      for (const f of mine) {
        if (f.dir !== dir) { dir = f.dir; html += `<div class="nt-dir">${esc(dir.slice(top.length + 1))}</div>`; }
        html += f.kind === "pdf"
          ? `<button class="nt-file pdf ${NB && NB.pdf === f.path ? "on" : ""}" data-pdf="${esc(f.path)}" title="PDF：点开可以用笔勾画">📕 ${esc(f.name)}</button>`
          : `<button class="nt-file ${READ && READ.path === f.path ? "on" : ""}" data-md="${esc(f.path)}">${esc(f.name)}</button>`;
      }
      html += "</div>";
    }
    return html;
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
    document.querySelectorAll("[data-top]").forEach((b) => (b.onclick = () => {
      const t = b.dataset.top;
      OPEN.has(t) ? OPEN.delete(t) : OPEN.add(t);
      LS.set("xrpg-nt-open", JSON.stringify([...OPEN]));
      document.getElementById("ntFiles").innerHTML = filesHtml(); bindSide();
    }));
    const sm = document.getElementById("ntSideMin"), so = document.getElementById("ntSideOpen");
    if (sm) sm.onclick = () => { SIDE_MIN = true; LS.set("xrpg-nt-side", "min"); const k = resizeKeep(); repaintSide(); setTimeout(k, 0); };
    if (so) so.onclick = () => { SIDE_MIN = false; LS.set("xrpg-nt-side", ""); const k = resizeKeep(); repaintSide(); setTimeout(k, 0); };
    if (SIDE_MIN) document.querySelectorAll(".nt-side [data-ntab]").forEach((b) => (b.onclick = async () => {
      TAB = b.dataset.ntab; SIDE_MIN = false; LS.set("xrpg-nt-side", ""); const k = resizeKeep(); repaintSide(); setTimeout(k, 0);
      if (TAB === "library" && !FILES) document.querySelector('.nt-tabs [data-ntab="library"]').click();
    }));
    const nn = document.getElementById("ntNew");
    if (nn) nn.onclick = newBook;
    document.querySelectorAll("[data-nb]").forEach((b) => (b.onclick = () => openBook(b.dataset.nb)));
    document.querySelectorAll("[data-del]").forEach((x) => (x.onclick = (e) => { e.stopPropagation(); delBook(x.dataset.del); }));
    document.querySelectorAll("[data-md]").forEach((b) => (b.onclick = () => openMd(b.dataset.md)));
    document.querySelectorAll("[data-pdf]").forEach((b) => (b.onclick = () => openPdf(b.dataset.pdf)));
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
        <p>写完点本子右上角的「📄 导出 PDF」，整本连纸带字存成 PDF（训练/手札/导出/），打印、发给别人都方便。</p>
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
  async function delBook(id) {
    const b = BOOKS.find((x) => x.id === id);
    if (!confirm(b && b.pdf ? `删除「${b.title}」上的批注？只删笔迹，库里的原 PDF 不动。` : `删除手札「${b ? b.title : id}」？手写的笔迹会删掉（已经导出的 PDF 留着）。`)) return;
    try {
      await api("/api/notes/delete", { id });
      if (NB && NB.id === id) { setFull(false); NB = null; dirty = false; }
      BOOKS = (await api("/api/notes")).notebooks; repaintSide(); paintMain();
    } catch (e) { showError(e); }
  }
  async function openPdf(path) {
    if (NB && NB.pdf === path) return;
    if (!(await flush())) return;
    try {
      const r = await api("/api/notes/pdfopen", { p: path });
      BOOKS = (await api("/api/notes")).notebooks;
      NB = await api("/api/notes/get", { id: r.id }); undo = []; redo = [];
      repaintSide(); paintMain();
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
        <input class="nt-title" id="ntTitle" value="${esc(NB.title)}" maxlength="60" title="${NB.pdf ? "批注本的名字（导出的 PDF 也用这个名字）" : "本子名字（导出的 PDF 也用这个名字）"}">
        ${NB.pdf ? "" : `<select id="ntPaper" title="纸">${sel("lines", "横线纸")}${sel("grid", "方格纸")}${sel("blank", "白纸")}</select>`}
        <span class="nt-jump" title="${NB.pdf ? esc(NB.pdf) + " · " : ""}输入页码回车跳过去">${NB.pdf ? "📕" : "📄"} 第<input id="ntJump" type="number" min="1" max="${NB.pages.length}" value="1" inputmode="numeric">/ <span id="ntTotal">${NB.pages.length}</span> 页</span>
        <span class="nt-tools">
          ${COLORS.map((c) => `<button class="nt-dot ${tool.t === "pen" && tool.c === c ? "on" : ""}" data-col="${c}" style="--c:${c}" title="笔"></button>`).join("")}
          ${WIDTHS.map((w, i) => `<button class="nt-w ${tool.t !== "er" && tool.w === w ? "on" : ""}" data-w="${w}" title="${["细", "中", "粗"][i]}"><i style="height:${w}px"></i></button>`).join("")}
          <button class="${tool.t === "hl" ? "on" : ""}" data-tool="hl" title="荧光笔">🖍</button>
          <button class="${tool.t === "er" ? "on" : ""}" data-tool="er" title="橡皮">🧽</button>
          <button data-act="undo" title="撤销（Ctrl+Z）" ${undo.length ? "" : "disabled"}>↶</button>
          <button data-act="redo" title="重做（Ctrl+Y）" ${redo.length ? "" : "disabled"}>↷</button>
          ${touchDev() ? `<button data-act="finger" class="${FINGER === "draw" ? "on" : ""}" title="手指写字（关掉 = 手指只翻页，笔写字）">☝</button>` : ""}
        </span>
        <span class="spacer"></span>
        <button class="primary nt-compile" id="ntPdf" title="${NB.pdf ? "把勾画叠到原 PDF 上：训练/手札/导出/名字（批注）.pdf" : "整本（连横线 / 方格纸）存成 A4 PDF：训练/手札/导出/本子名.pdf"}">${NB.pdf ? "📄 导出批注 PDF" : "📄 导出 PDF"}</button>
        <button class="ghost small nt-fullbtn" id="ntFull" title="全屏写（再点一次退出）">${fullIcon(isFull())}</button>
        <button class="ghost small" id="ntClose" title="收起本子（已自动保存）">✕</button>
      </div>
      ${NB.pdf_missing ? `<div class="warn">原来的 PDF（${esc(NB.pdf)}）不见了，可能挪走或改了名；笔迹还在，底图显示不出来。</div>` : ""}
      <div class="nt-pages" id="ntPages">${NB.pages.map((_, i) => pageHtml(i)).join("")}
        ${NB.pdf ? "" : '<button class="ghost nt-addpage" id="ntAdd">＋ 加一页</button>'}</div>
      </div>`;
  }
  // 全屏图标用画的（有的平板字体里没有 ⛶ 这类符号，会显示成空框）
  function fullIcon(on) {
    const d = on ? "M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5" : "M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5";
    return `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="${d}"/></svg>`;
  }
  function pageHtml(i) {
    const bg = NB.pdf
      ? `<img class="nt-pdfimg" loading="lazy" draggable="false" alt="" src="/notes-pdfpage?p=${encodeURIComponent(NB.pdf)}&n=${i}&v=${NB.pdf_v || 0}">`
      : '<canvas class="nt-bg"></canvas>';
    return `<div class="nt-page" data-pg="${i}" style="aspect-ratio:${PW} / ${ph(i)}">${bg}<canvas class="nt-ink" data-pg="${i}"></canvas><canvas class="nt-live" data-pg="${i}"></canvas><span class="nt-pno">${i + 1}</span></div>`;
  }
  // 记住每本翻到哪一页（每台设备各记各的）：存“第几页 + 这一页往下多少”，换了屏幕宽度也能回到同一处
  const POS_KEY = "xrpg-nt-pos";
  const readPos = () => { try { return JSON.parse(LS.get(POS_KEY, "{}")) || {}; } catch (e) { return {}; } };
  function pageTop(box, pg) { return pg.getBoundingClientRect().top - box.getBoundingClientRect().top + box.scrollTop; }
  function curPos() {
    const box = document.getElementById("ntPages");
    if (!box) return null;
    for (const pg of box.querySelectorAll(".nt-page")) {
      const t = pageTop(box, pg), h = pg.offsetHeight || 1;
      if (t + h > box.scrollTop + 1) return { pg: Number(pg.dataset.pg), f: Math.max(0, Math.round((box.scrollTop - t) / h * 1000) / 1000) };
    }
    return null;
  }
  function savePos() {
    if (!NB) return;
    const p = curPos();
    if (!p) return;
    const all = readPos();
    delete all[NB.id];
    all[NB.id] = p;
    const ids = Object.keys(all);
    ids.slice(0, Math.max(0, ids.length - 80)).forEach((k) => delete all[k]);     // 只留最近 80 本
    LS.set(POS_KEY, JSON.stringify(all));
  }
  const resizeKeep = () => { const k = NB ? curPos() : null; return () => { sizePagesIf(); restorePos(k); }; };   // 改了宽度（收起左栏等）后回到同一处
  function showPage() {             // 页码框跟着滚动显示当前页（正在输入时不改）
    const j = document.getElementById("ntJump"), p = curPos();
    if (j && p && document.activeElement !== j) j.value = p.pg + 1;
  }
  function restorePos(p) {
    const box = document.getElementById("ntPages");
    const pg = p && box && box.querySelector(`.nt-page[data-pg="${p.pg}"]`);
    if (pg) box.scrollTop = pageTop(box, pg) + (p.f || 0) * pg.offsetHeight;
  }
  function bindBook() {
    NEAR.clear();
    sizePages();
    restorePos(readPos()[NB.id]);
    let posT = 0;
    document.getElementById("ntPages").addEventListener("scroll", () => { clearTimeout(posT); posT = setTimeout(() => { savePos(); showPage(); }, 150); }, { passive: true });
    showPage();
    const jump = document.getElementById("ntJump");
    const goPage = () => {
      const n = Math.max(1, Math.min(NB.pages.length, Math.round(Number(jump.value) || 1)));
      jump.value = n;
      restorePos({ pg: n - 1, f: 0 });
      savePos();
    };
    jump.onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); goPage(); jump.blur(); } };
    jump.onchange = goPage;
    jump.onfocus = () => jump.select();
    document.querySelectorAll(".nt-ink").forEach(bindInk);
    const $$ = (id) => document.getElementById(id);
    $$("ntTitle").oninput = () => { NB.title = $$("ntTitle").value; queueSave(); };
    if ($$("ntPaper")) $$("ntPaper").onchange = () => { NB.paper = $$("ntPaper").value; sizePages(); queueSave(); };
    if ($$("ntAdd")) $$("ntAdd").onclick = () => {
      NB.pages.push({ strokes: [] });
      const add = $$("ntAdd");
      add.insertAdjacentHTML("beforebegin", pageHtml(NB.pages.length - 1));
      const pg = add.previousElementSibling;
      sizePages(); bindInk(pg.querySelector(".nt-ink"));
      pg.scrollIntoView({ behavior: "smooth", block: "start" });
      const tot = document.getElementById("ntTotal"); if (tot) tot.textContent = NB.pages.length;
      const jp = document.getElementById("ntJump"); if (jp) jp.max = NB.pages.length;
      queueSave();
    };
    $$("ntClose").onclick = async () => { if (await flush()) { setFull(false); NB = null; repaintSide(); paintMain(); } };
    $$("ntFull").onclick = () => setFull(!isFull());
    $$("ntPdf").onclick = exportPdf;
    document.querySelectorAll(".nt-tools [data-col]").forEach((b) => (b.onclick = () => { tool = { t: "pen", c: b.dataset.col, w: tool.t === "pen" ? tool.w : WIDTHS[1] }; syncTools(); }));
    document.querySelectorAll(".nt-tools [data-w]").forEach((b) => (b.onclick = () => { if (tool.t === "er") tool.t = "pen"; tool.w = Number(b.dataset.w); syncTools(); }));
    document.querySelectorAll(".nt-tools [data-tool]").forEach((b) => (b.onclick = () => { tool.t = tool.t === b.dataset.tool ? "pen" : b.dataset.tool; syncTools(); }));
    document.querySelectorAll(".nt-tools [data-act]").forEach((b) => (b.onclick = () => {
      const a = b.dataset.act;
      if (a === "undo") doUndo(); else if (a === "redo") doRedo();
      else { FINGER = FINGER === "draw" ? "scroll" : "draw"; LS.set("xrpg-nt-finger", FINGER); b.classList.toggle("on", FINGER === "draw");
        toast(FINGER === "draw" ? "☝ 手指也能写字" : "☝ 手指只翻页，用笔写字"); }
    }));
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
  const sizePagesIf = () => { if (NB) sizePages(); };
  // 画布只给滚到附近的页分配（PDF 动辄几十页，每页三层画布全开会占掉上 G 内存）；滚远了就缩成 1×1 释放
  const NEAR = new Set();
  let IO = null;
  function sizeOne(pg) {
    const w = pg.clientWidth, i = Number(pg.dataset.pg);
    if (!w) return;
    const h = Math.round(w * ph(i) / PW), dpr = window.devicePixelRatio || 1;
    pg.style.height = h + "px";
    const on = NEAR.has(i);
    pg.querySelectorAll("canvas").forEach((c) => {
      const cw = on ? Math.round(w * dpr) : 1, chh = on ? Math.round(h * dpr) : 1;
      if (c.width !== cw || c.height !== chh) { c.width = cw; c.height = chh; }
      c.style.width = w + "px"; c.style.height = h + "px";
    });
    if (!on) return;
    const bg = pg.querySelector(".nt-bg");
    if (bg) drawPaper(bg);
    repaint(i);
  }
  function sizePages() {
    const box = document.getElementById("ntPages");
    if (IO) IO.disconnect();
    IO = "IntersectionObserver" in window && box ? new IntersectionObserver((ents) => {
      for (const en of ents) {
        const i = Number(en.target.dataset.pg), was = NEAR.has(i);
        if (en.isIntersecting) NEAR.add(i); else NEAR.delete(i);
        if (was !== NEAR.has(i)) sizeOne(en.target);
      }
    }, { root: box, rootMargin: "1500px 0px" }) : null;
    document.querySelectorAll(".nt-page").forEach((pg) => {
      if (!IO) NEAR.add(Number(pg.dataset.pg));
      sizeOne(pg);
      if (IO) IO.observe(pg);
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
  function inkCtx(i, cls = "nt-ink") {
    const c = document.querySelector(`.${cls}[data-pg="${i}"]`);
    if (!c) return null;
    const x = c.getContext("2d"), k = c.width / PW;
    x.setTransform(k, 0, 0, k, 0, 0);
    return x;
  }
  // 整页重画只在撤销 / 重做 / 换尺寸时做；写字时只画正在写的这一笔（以前每动一下都把整页重画一遍，写得越多越卡）
  function repaint(i) {
    const x = inkCtx(i);
    if (!x) return;
    x.clearRect(0, 0, PW, ph(i));
    for (const s of NB.pages[i].strokes) strokeOn(x, s);
  }
  let liveRaf = 0, livePage = -1, liveStroke = null;
  function drawLive() {
    liveRaf = 0;
    const s = liveStroke;
    if (!s) return;
    if (s.t === "er") { const x = inkCtx(livePage); if (x) strokeOn(x, s); return; }   // 橡皮直接擦在墨迹层上（重复擦同一处结果不变）
    const x = inkCtx(livePage, "nt-live");
    if (!x) return;
    x.clearRect(0, 0, PW, ph(livePage));
    strokeOn(x, s);
  }
  function live(i, s) {
    livePage = i; liveStroke = s;
    if (!liveRaf) liveRaf = requestAnimationFrame(drawLive);     // 一帧最多画一次
  }
  function commitLive(i, s) {
    if (liveRaf) { cancelAnimationFrame(liveRaf); liveRaf = 0; }
    const lx = inkCtx(i, "nt-live");
    if (lx) lx.clearRect(0, 0, PW, ph(i));
    const x = inkCtx(i);
    if (x) strokeOn(x, s);                                       // 只把这一笔加到墨迹层上
    liveStroke = null;
  }
  // 笔 / 鼠标 → 写；手指 → 翻页（FINGER=scroll 时，翻页由这里自己做，浏览器不插手，笔写字时页面不会跟着滑）
  let inking = false;
  function bindInk(c) {
    const i = Number(c.dataset.pg);
    let cur = null, pid = null, drag = null;
    const pt = (e) => { const r = c.getBoundingClientRect(); return [Math.round((e.clientX - r.left) * PW / r.width * 10) / 10, Math.round((e.clientY - r.top) * ph(i) / r.height * 10) / 10]; };
    const box = () => document.getElementById("ntPages");
    c.onpointerdown = (e) => {
      if (e.pointerType === "pen" && FINGER === "draw" && LS.get("xrpg-nt-finger", "") === "") {   // 第一次用笔：手指改成只翻页
        FINGER = "scroll"; LS.set("xrpg-nt-finger", FINGER);
        const b = document.querySelector('.nt-tools [data-act="finger"]'); if (b) b.classList.remove("on");
      }
      e.preventDefault();
      if (e.pointerType === "touch" && (FINGER === "scroll" || inking)) {
        if (inking || drag) return;                           // 正在写字时手掌碰到：不理
        stopFling();
        drag = { id: e.pointerId, y: e.clientY, x: e.clientX, t: e.timeStamp, v: 0, vx: 0 };
        try { c.setPointerCapture(e.pointerId); } catch (_) {}
        return;
      }
      if (e.button > 0 && e.button !== 5) return;
      if (cur) return;
      stopFling();
      try { c.setPointerCapture(e.pointerId); } catch (_) {}
      pid = e.pointerId; inking = true;
      const er = tool.t === "er" || e.button === 5;
      cur = { t: er ? "er" : tool.t, c: tool.t === "hl" ? "#f5d000" : tool.c, w: er ? 26 : tool.t === "hl" ? 22 : tool.w, p: [pt(e)] };
      live(i, cur);
    };
    c.onpointermove = (e) => {
      if (drag && e.pointerId === drag.id) {
        const b = box(), dy = e.clientY - drag.y, dx = e.clientX - drag.x, dt = Math.max(1, e.timeStamp - drag.t);
        if (b) { b.scrollTop -= dy; b.scrollLeft -= dx; }
        drag.v = 0.8 * (-dy / dt) + 0.2 * drag.v; drag.vx = 0.8 * (-dx / dt) + 0.2 * drag.vx;
        drag.y = e.clientY; drag.x = e.clientX; drag.t = e.timeStamp;
        return;
      }
      if (!cur || e.pointerId !== pid) return;
      const evs = e.getCoalescedEvents ? e.getCoalescedEvents() : [e];
      for (const ev of evs) cur.p.push(pt(ev));
      live(i, cur);
    };
    c.onpointerup = c.onpointercancel = (e) => {
      if (drag && e.pointerId === drag.id) {
        const v = drag.v, vx = drag.vx; drag = null;
        if (e.type === "pointerup") fling(v, vx);
        return;
      }
      if (!cur || e.pointerId !== pid) return;
      NB.pages[i].strokes.push(cur);
      undo.push({ page: i, stroke: cur }); redo = [];
      commitLive(i, cur);
      cur = null; pid = null; inking = false; lastWrite = Date.now();
      syncTools(); queueSave();
    };
  }
  let flingT = 0;
  function stopFling() { cancelAnimationFrame(flingT); flingT = 0; }
  function fling(v, vx) {                                     // 松手后惯性滑一段
    const b = document.getElementById("ntPages");
    const cap = (x) => Math.max(-4, Math.min(4, x));
    v = cap(v); vx = cap(vx);
    if (!b || (Math.abs(v) < 0.05 && Math.abs(vx) < 0.05)) return;
    let last = performance.now();
    const step = (now) => {
      const dt = now - last; last = now;
      b.scrollTop += v * dt; b.scrollLeft += vx * dt;
      v *= Math.pow(0.995, dt); vx *= Math.pow(0.995, dt);
      if (Math.abs(v) > 0.02 || Math.abs(vx) > 0.02) flingT = requestAnimationFrame(step); else flingT = 0;
    };
    flingT = requestAnimationFrame(step);
  }

  // 全屏写：本子铺满整个屏幕（浏览器里顺便进系统全屏）
  const isFull = () => document.documentElement.classList.contains("nt-full");
  function setFull(on) {
    if (on === isFull()) return;
    document.documentElement.classList.toggle("nt-full", on);
    const inApp = document.documentElement.classList.contains("in-app");
    try {
      if (on && !inApp && !document.fullscreenElement) document.documentElement.requestFullscreen?.().catch(() => {});
      if (!on && document.fullscreenElement) document.exitFullscreen?.().catch(() => {});
    } catch (e) {}
    const b = document.getElementById("ntFull"); if (b) b.innerHTML = fullIcon(on);
    const keep = curPos();
    setTimeout(() => { sizePagesIf(); restorePos(keep); }, 60);
  }
  document.addEventListener("fullscreenchange", () => { if (!document.fullscreenElement && isFull()) setFull(false); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && isFull()) setFull(false); });

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
  let ver = 0, saving = null;      // ver：每改一次加一；存的时候又写了新笔画，存完还要再存（以前会把存盘途中写的几笔当成已存，丢掉）
  function queueSave() {
    dirty = true; ver++;
    clearTimeout(saveT);
    saveT = setTimeout(flush, 1200);
  }
  async function flush() {
    clearTimeout(saveT);
    if (saving) { await saving; }
    if (!NB || !dirty) return true;
    const v0 = ver, book = NB;
    const body = JSON.stringify({ id: book.id, title: book.title, paper: book.paper, pages: book.pages, text: book.text });
    let done;
    saving = new Promise((r) => (done = r));
    try {
      const r = await fetch("/api/notes/save", { method: "POST", headers: { "Content-Type": "application/json" }, body }).then((x) => x.json());
      if (r.error) throw new Error(r.error);
      saving = null; done();
      const b = BOOKS.find((x) => x.id === book.id);
      if (b && (b.title !== r.title || b.pages !== book.pages.length)) { b.title = r.title; b.pages = book.pages.length; repaintSide(); }
      if (NB === book && ver !== v0) return flush();       // 存的这会儿又写了：接着存，直到存上最新的
      if (NB === book) dirty = false;
      return true;
    } catch (e) { saving = null; done(); showError(e); return false; }
  }
  addEventListener("beforeunload", () => { if (NB && dirty) navigator.sendBeacon?.("/api/notes/save", new Blob([JSON.stringify({ id: NB.id, title: NB.title, paper: NB.paper, pages: NB.pages, text: NB.text })], { type: "application/json" })); });

  // ---------------------------------------------------------------- 📄 导出 PDF
  // 每页画成图片（纸的横线 / 方格 + 笔迹，橡皮擦掉的地方露出纸），末尾没写字的空白页不要
  function pageImages() {
    const K = 1.6, out = [];
    let last = -1;
    NB.pages.forEach((pg, i) => { if (pg.strokes.some((s) => s.t !== "er")) last = i; });
    for (let i = 0; i <= last; i++) {
      const c = document.createElement("canvas");
      c.width = PW * K; c.height = PH * K;
      drawPaper(c);
      const ink = document.createElement("canvas");
      ink.width = PW * K; ink.height = PH * K;
      const ix = ink.getContext("2d");
      ix.setTransform(K, 0, 0, K, 0, 0);
      for (const s of NB.pages[i].strokes) strokeOn(ix, s);
      const x = c.getContext("2d");
      x.setTransform(1, 0, 0, 1, 0, 0);
      x.drawImage(ink, 0, 0);
      out.push(c.toDataURL("image/jpeg", 0.88));
    }
    return out;
  }
  // PDF 批注本：每页只画笔迹（透明 PNG），没写的页传 null，电脑把它们叠到原 PDF 上
  function overlayImages() {
    const K = 1.6;
    return NB.pages.map((pg, i) => {
      if (!pg.strokes.some((s) => s.t !== "er")) return null;
      const c = document.createElement("canvas");
      c.width = PW * K; c.height = Math.round(ph(i) * K);
      const x = c.getContext("2d");
      x.setTransform(K, 0, 0, K, 0, 0);
      for (const s of pg.strokes) strokeOn(x, s);
      return c.toDataURL("image/png");
    });
  }
  async function exportPdf() {
    if (busy) return;
    if (!(await flush())) return;
    const b = document.getElementById("ntPdf"), label = b.textContent;
    busy = true; b.disabled = true; b.textContent = "📄 导出中…";
    try {
      let r;
      if (NB.pdf) {
        const ov = overlayImages();
        if (!ov.some(Boolean)) throw new Error("还没在这个 PDF 上写画，没有可以导出的批注");
        r = await api("/api/notes/pdfexport", { id: NB.id, overlays: ov });
      } else {
        const imgs = pageImages();
        if (!imgs.length) throw new Error("这本手札还没写字，没有可以导出的页");
        r = await api("/api/notes/pdf", { id: NB.id, images: imgs });
      }
      const local = ["127.0.0.1", "localhost", "[::1]"].includes(location.hostname);
      const el = document.createElement("div");
      el.className = "toast nt-pdf-toast";
      el.innerHTML = `📄 导出好了：${r.pages} 页${r.marked != null ? `（${r.marked} 页有批注）` : ""} · ${(r.size / 1024 / 1024).toFixed(1)} MB<div class="small muted">${esc(r.path)}</div>
        <div class="row">${local ? '<button class="small primary" data-o="open">打开</button>' : `<a class="small" href="${esc(r.url)}" download="${esc(r.name)}" target="_blank" rel="noopener">⬇ 下载到这台设备</a>`}
          <span class="spacer"></span><button class="small ghost" data-o="x">关</button></div>`;
      document.getElementById("toasts").appendChild(el);
      const tm = setTimeout(() => el.remove(), 20000);
      el.querySelector('[data-o="x"]').onclick = () => { clearTimeout(tm); el.remove(); };
      const o = el.querySelector('[data-o="open"]');
      if (o) o.onclick = async () => { try { await api("/api/notes/open", { path: r.path }); } catch (e) { showError(e); } };
    } catch (e) { showError(e); }
    busy = false;
    const b2 = document.getElementById("ntPdf"); if (b2) { b2.disabled = false; b2.textContent = label; }
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
    // 带颜色的字：只放行 <span style="color:…">…</span> / <font color="…">…</font>（颜色值查过格式），其它 HTML 照样当文字显示
    const COLOR = /^(#[0-9a-fA-F]{3,8}|[a-zA-Z]{3,20}|rgba?\([\d\s.,%]+\))$/;
    const colors = (h) => h
      .replace(/&lt;span style=&quot;\s*color\s*:\s*([^;&]+?)\s*;?\s*&quot;&gt;/gi, (m, c) => (COLOR.test(c) ? `<span style="color:${c}">` : m))
      .replace(/&lt;font color=&quot;([^&]+?)&quot;&gt;/gi, (m, c) => (COLOR.test(c) ? `<span style="color:${c}">` : m))
      .replace(/&lt;\/(span|font)&gt;/gi, "</span>");
    const inline = (s) => colors(esc(s))
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

  // 正在记笔记：开着本子、页面看得见、1 分钟内写过字 → 返回本子编号（心跳带上，服务器再核对最近真的存过笔迹）
  const writingId = () => (VIEW === "notes" && NB && document.visibilityState === "visible" && (inking || Date.now() - lastWrite <= 60000) ? NB.id : "");
  window.NOTES = { openPdfLater: (p) => { PENDING = p; }, writingId, lastId: () => (NB ? NB.id : ""), save: () => flush(), render, flush: () => { setFull(false); return flush(); }, mdRender, isFull, exitFull: () => setFull(false) };
})();
