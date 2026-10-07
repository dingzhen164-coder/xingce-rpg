/* 🌿 灵脉图：每个板块的思维导图（修炼殿玉简下面）。编辑器是 simple-mind-map（github.com/wanglin2/mind-map，MIT，web/vendor/mindmap/），
   用到时才加载（6MB）。数据存在库里 训练/灵脉图/<板块>/<名字>.json（rpg/mindmap.py），改了自动保存。
   - 修炼殿：每个板块一枚会动的“灵脉阵盘”，点开进编辑器（一个板块可以有好几幅）
   - 编辑：点节点选中；Tab 加子节点、Enter 加同级、Del 删除、双击改字、拖动节点换位置；Ctrl+Z / Ctrl+Y 撤销重做
   - 导入 .xmind / Markdown（# 标题层级或 - 列表）/ .json；导出 XMind / 图片 / Markdown / JSON 到 训练/灵脉图/导出/ */
(function () {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const VER = "0.14.0-fix.3";
  const HUES = [40, 200, 150, 280, 10, 320, 180, 95, 220, 260, 30, 170];
  const LAYOUTS = [["logicalStructure", "逻辑结构（向右）"], ["mindMap", "思维导图（两边）"], ["organizationStructure", "组织结构（向下）"],
    ["catalogOrganization", "目录组织"], ["timeline", "时间轴"], ["fishbone", "鱼骨图"]];
  let LIST = null, CUR = null, mm = null, saveT = null, dirty = false, libP = null;

  function loadLib() {
    if (window.simpleMindMap) return Promise.resolve();
    if (libP) return libP;
    libP = new Promise((ok, bad) => {
      const css = document.createElement("link");
      css.rel = "stylesheet"; css.href = `vendor/mindmap/simpleMindMap.esm.min.css?v=${VER}`;
      document.head.appendChild(css);
      const s = document.createElement("script");
      s.src = `vendor/mindmap/simpleMindMap.umd.min.js?v=${VER}`;
      s.onload = () => ok(); s.onerror = () => { libP = null; bad(new Error("思维导图编辑器没加载出来，刷新再试")); };
      document.head.appendChild(s);
    });
    return libP;
  }
  // 富文本插件（节点文字放在 foreignObject 里）在有的内核上量错高度，字只显示半截：去掉它，节点文字用普通 SVG 文字
  const M = () => {
    const Mind = window.simpleMindMap.default || window.simpleMindMap;
    const k = (Mind.pluginList || []).findIndex((p) => p.instanceName === "richText");
    if (k >= 0) Mind.pluginList.splice(k, 1);
    return Mind;
  };
  // 以前（或别处）存的富文本节点 "<p>增长</p>" → 纯文字
  function plain(node) {
    if (!node || !node.data) return node;
    if (node.data.richText || /<[a-z][^>]*>/i.test(node.data.text || "")) {
      const d = document.createElement("div");
      d.innerHTML = String(node.data.text || "").replace(/<\/p>\s*<p[^>]*>/gi, "\n").replace(/<br\s*\/?>/gi, "\n");
      node.data.text = d.textContent.trim();
      delete node.data.richText;
    }
    (node.children || []).forEach(plain);
    return node;
  }

  // ---------------------------------------------------------------- 修炼殿：灵脉阵盘
  function disk(i) {
    // 中间一颗主节点，五条灵脉向外生长，末端的小节点一闪一闪
    const rays = [0, 72, 144, 216, 288].map((a, k) => {
      const r = (a + i * 17) * Math.PI / 180, x = 50 + Math.cos(r) * 33, y = 50 + Math.sin(r) * 33;
      const mx = 50 + Math.cos(r + 0.5) * 18, my = 50 + Math.sin(r + 0.5) * 18;
      return `<path class="ln-vein" d="M50 50 Q${mx.toFixed(1)} ${my.toFixed(1)} ${x.toFixed(1)} ${y.toFixed(1)}" style="--k:${k}"/>
        <circle class="ln-dot" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3.2" style="--k:${k}"/>`;
    }).join("");
    return `<svg viewBox="0 0 100 100" class="ln-svg"><circle cx="50" cy="50" r="46" class="ln-ring"/><circle cx="50" cy="50" r="38" class="ln-ring2"/>
      ${rays}<circle cx="50" cy="50" r="7" class="ln-core"/></svg>`;
  }
  async function hubHtml() {
    try { LIST = await api("/api/mindmap"); } catch (e) { return `<div class="card"><p class="muted">${esc(e.message)}</p></div>`; }
    return `<div class="card ln-hall"><div class="row"><h3 style="margin:0">🌿 灵脉图</h3>
        <span class="small muted">每个板块的知识脉络（思维导图）：自己画、或导入 XMind / Markdown，点阵盘打开</span></div>
      <div class="ln-grid">${LIST.boards.map((b, i) => {
        const n = b.maps.reduce((a, m) => a + m.nodes, 0);
        return `<div class="ln-slot" data-ln="${esc(b.board)}"><div class="ln-disk ${b.maps.length ? "lit" : ""}" style="--h:${HUES[i % HUES.length]};--d:${(i % 6) * 0.7}s">${disk(i)}</div>
          <div class="ln-name">${esc(b.board)}</div><div class="ln-cap">${b.maps.length ? `${b.maps.length} 幅 · ${n} 节` : "未绘"}</div></div>`;
      }).join("")}</div></div>`;
  }
  function bindHub(root = document) {
    root.querySelectorAll("[data-ln]").forEach((el) => (el.onclick = () => openBoard(el.dataset.ln)));
  }
  async function openBoard(board) {
    const b = (LIST?.boards || []).find((x) => x.board === board);
    const maps = b ? b.maps : [];
    if (maps.length > 1) return pickMap(board, maps);
    open(board, maps[0]?.name || board);
  }
  function pickMap(board, maps) {
    const m = $("#modal");
    m.innerHTML = `<div class="modal-box"><h3>🌿 ${esc(board)} · 灵脉图</h3>
      <div class="ln-pick">${maps.map((x) => `<button data-pk="${esc(x.name)}"><b>${esc(x.name)}</b><small>${x.nodes} 节 · ${esc(x.updated)}</small></button>`).join("")}</div>
      <div class="row"><button class="ghost" id="lnPNew">＋ 新画一幅</button><span class="spacer"></span><button class="ghost" id="lnPX">关</button></div></div>`;
    m.classList.remove("hidden");
    m.querySelectorAll("[data-pk]").forEach((x) => (x.onclick = () => { m.classList.add("hidden"); open(board, x.dataset.pk); }));
    $("#lnPX").onclick = () => m.classList.add("hidden");
    $("#lnPNew").onclick = async () => { m.classList.add("hidden"); newMap(board); };
  }
  async function newMap(board, data, name) {
    name = name || prompt(`新画一幅「${board}」的灵脉图，名字：`, board);
    if (!name) return;
    try { const r = await api("/api/mindmap/create", { board, name, data }); open(board, r.name); } catch (e) { showError(e); }
  }

  // ---------------------------------------------------------------- 编辑器
  function stage() {
    let s = document.getElementById("yjStage");
    if (!s) { s = document.createElement("div"); s.id = "yjStage"; s.className = "yj-stage ln-stage"; document.body.appendChild(s); }
    document.documentElement.classList.add("yj-on");
    return s;
  }
  async function open(board, name) {
    const s = stage();
    s.innerHTML = `<div class="yj-top"><button class="ghost" id="lnBack">← 回修炼殿</button><b class="yj-top-title">🌿 灵脉图 · ${esc(board)}</b></div><div class="yj-wait">展开灵脉…</div>`;
    document.getElementById("lnBack").onclick = close;
    let d;
    try { [d] = await Promise.all([api("/api/mindmap/get", { board, name }), loadLib()]); } catch (e) { showError(e); return close(); }
    CUR = { board, name: d.name };
    const data = d.data || {};
    s.innerHTML = `<div class="yj-top"><button class="ghost" id="lnBack">← 回修炼殿</button>
        <b class="yj-top-title">🌿 ${esc(board)} · <a id="lnName" title="改名">${esc(d.name)}</a></b><span class="spacer"></span><span class="small faint" id="lnSaved"></span></div>
      <div class="ln-tools">
        <button data-c="child" title="给选中的节点加子节点（Tab）">＋ 子节点</button><button data-c="sib" title="加同级节点（Enter）">＋ 同级</button>
        <button data-c="del" title="删除选中的节点（Delete）">✕ 删除</button><span class="ln-sep"></span>
        <button data-c="undo" title="撤销（Ctrl+Z）">↶</button><button data-c="redo" title="重做（Ctrl+Y）">↷</button><span class="ln-sep"></span>
        <select id="lnLayout" title="布局">${LAYOUTS.map(([k, v]) => `<option value="${k}" ${k === (data.layout || "logicalStructure") ? "selected" : ""}>${v}</option>`).join("")}</select>
        <button data-c="fit" title="整幅放进屏幕">⤢ 适应</button><button data-c="in" title="放大">＋</button><button data-c="out" title="缩小">－</button><span class="ln-sep"></span>
        <button data-c="import" title="导入 .xmind / Markdown / .json，导成新的一幅">📥 导入</button>
        <select id="lnExport" title="导出到 训练/灵脉图/导出/"><option value="">📤 导出…</option><option value="xmind">XMind（.xmind）</option><option value="png">图片（.png）</option>
          <option value="md">Markdown（.md）</option><option value="json">JSON</option></select>
        <span class="spacer"></span><button class="ghost" data-c="new">＋ 新一幅</button><button class="ghost danger" data-c="trash" title="删掉这一幅">🗑</button>
        <input type="file" id="lnFile" accept=".xmind,.md,.markdown,.txt,.json,.smm" hidden></div>
      <div class="ln-canvas" id="lnCanvas"></div>
      <div class="ln-tip small faint">点节点选中 · 双击改字 · 拖动节点换位置 · 拖空白处移动画布 · 滚轮 / 双指缩放 · 改了自动保存</div>`;
    document.getElementById("lnBack").onclick = close;
    const Mind = M();
    try {
      mm = new Mind({
        el: document.getElementById("lnCanvas"),
        data: plain(data.root || { data: { text: board }, children: [] }),
        layout: data.layout || "logicalStructure",
        theme: data.theme?.template || "default",
        themeConfig: Object.assign({ backgroundColor: "#fffdf6", lineColor: "#3fa48a", generalizationLineColor: "#3fa48a",
          root: { fillColor: "#2f8f78", color: "#fff", borderColor: "#2f8f78", fontSize: 18 },
          second: { fillColor: "#eef7f3", color: "#1d3d36", borderColor: "#3fa48a", fontSize: 15 } }, data.theme?.config || {}),
        viewData: data.view || null,
        mousewheelAction: "zoom", mousewheelZoomActionReverse: true,
      });
      try { mm.rainbowLines && mm.rainbowLines.updateRainLinesConfig({ open: true }); } catch (_) {}
    } catch (e) { showError(e); return; }
    if (!data.view) setTimeout(() => { try { mm.view.fit(); } catch (_) {} }, 100);
    mm.on("data_change", queueSave);
    mm.on("view_data_change", queueSave);
    const cmd = {
      child: () => mm.execCommand("INSERT_CHILD_NODE", true, mm.renderer.activeNodeList.length ? [] : [mm.renderer.root]),
      sib: () => mm.renderer.activeNodeList.length ? mm.execCommand("INSERT_NODE") : toast("先点一下要在哪个节点旁边加"),
      del: () => mm.renderer.activeNodeList.length ? mm.execCommand("REMOVE_NODE") : toast("先点一下要删的节点"),
      undo: () => mm.execCommand("BACK"), redo: () => mm.execCommand("FORWARD"),
      fit: () => mm.view.fit(), in: () => mm.view.enlarge(), out: () => mm.view.narrow(),
      import: () => document.getElementById("lnFile").click(),
      new: () => newMap(board),
      trash: async () => {
        if (!confirm(`删掉「${CUR.name}」这一幅灵脉图？（删了不能恢复）`)) return;
        try { await api("/api/mindmap/delete", CUR); dirty = false; close(); } catch (e) { showError(e); }
      },
    };
    s.querySelectorAll("[data-c]").forEach((b) => (b.onclick = () => cmd[b.dataset.c]()));
    document.getElementById("lnLayout").onchange = (e) => mm.setLayout(e.target.value);
    document.getElementById("lnExport").onchange = (e) => { const v = e.target.value; e.target.value = ""; if (v) exportAs(v); };
    document.getElementById("lnFile").onchange = (e) => { const f = e.target.files[0]; e.target.value = ""; if (f) importFile(f); };
    document.getElementById("lnName").onclick = async () => {
      const n = prompt("改成：", CUR.name);
      if (!n || n === CUR.name) return;
      await flush();
      try { const r = await api("/api/mindmap/rename", { board, name: CUR.name, new: n }); CUR.name = r.name; document.getElementById("lnName").textContent = r.name; } catch (e) { showError(e); }
    };
  }
  function queueSave() {
    dirty = true;
    const el = document.getElementById("lnSaved"); if (el) el.textContent = "…";
    clearTimeout(saveT); saveT = setTimeout(flush, 1200);
  }
  async function flush() {
    clearTimeout(saveT);
    if (!dirty || !mm || !CUR) return;
    dirty = false;
    try {
      await api("/api/mindmap/save", { board: CUR.board, name: CUR.name, data: mm.getData(true) });
      const el = document.getElementById("lnSaved"); if (el) el.textContent = "已保存";
    } catch (e) { dirty = true; showError(e); }
  }
  async function close() {
    await flush();
    try { if (mm) mm.destroy(); } catch (_) {}
    mm = null; CUR = null;
    const s = document.getElementById("yjStage");
    if (s) s.remove();
    document.documentElement.classList.remove("yj-on");
    if (typeof VIEW !== "undefined" && VIEW === "train") renderTrain();
  }
  async function importFile(f) {
    const Mind = M();
    const ext = f.name.split(".").pop().toLowerCase();
    let root;
    try {
      if (ext === "xmind") root = await Mind.xmind.parseXmindFile(f);
      else {
        const text = await f.text();
        if (ext === "json" || ext === "smm") { const o = JSON.parse(text); root = o.root || o; }
        else root = Mind.markdown.transformMarkdownTo(text);
      }
      plain(root);
      if (!root || !root.data) throw new Error("没认出内容（XMind 要 .xmind 文件；Markdown 用 # 标题或 - 列表分层）");
    } catch (e) { return showError(e); }
    await flush();
    newMap(CUR.board, { root, layout: "logicalStructure" }, f.name.replace(/\.[^.]+$/, ""));
  }
  async function exportAs(ext) {
    await flush();
    let data;
    try { data = await mm.export(ext, false, CUR.name); } catch (e) { return showError(e); }
    try {
      const r = await api("/api/mindmap/export", { board: CUR.board, name: CUR.name, ext, data });
      const local = ["127.0.0.1", "localhost", "[::1]"].includes(location.hostname);
      const el = document.createElement("div");
      el.className = "toast nt-pdf-toast";
      el.innerHTML = `📤 导出好了：${esc(r.name)}<div class="small muted">${esc(r.path)}</div>
        <div class="row">${local ? '<button class="small primary" data-o="open">打开</button>' : `<a class="small" href="${esc(r.url)}" download="${esc(r.name)}" target="_blank" rel="noopener">⬇ 下载到这台设备</a>`}
          <span class="spacer"></span><button class="small ghost" data-o="x">关</button></div>`;
      document.getElementById("toasts").appendChild(el);
      const tm = setTimeout(() => el.remove(), 20000);
      el.querySelector('[data-o="x"]').onclick = () => { clearTimeout(tm); el.remove(); };
      const o = el.querySelector('[data-o="open"]');
      if (o) o.onclick = async () => { try { await api("/api/notes/open", { path: r.path }); } catch (e) { showError(e); } };
    } catch (e) { showError(e); }
  }
  addEventListener("beforeunload", () => { if (dirty && mm && CUR) navigator.sendBeacon?.("/api/mindmap/save", new Blob([JSON.stringify({ board: CUR.board, name: CUR.name, data: mm.getData(true) })], { type: "application/json" })); });

  window.MINDMAP = { hubHtml, bindHub, open, close, isOpen: () => !!CUR };
})();
