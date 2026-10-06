/* 草稿笔：点右上角 ✏，页面定住，盖一层透明画布可以写写画画（像粉笔 App 的草稿）。
   笔 / 橡皮 / 撤销 / 重做 / 一键清空；鼠标、触屏、手写笔都能用。
   笔记按题保存（这台设备的浏览器里）：做题 / 复盘时每道题各有一份，关掉再打开、换题再回来都还在；只有点 🗑 才清掉。
   不在做题时按页面存。哪道题由 app.js 的 window.DRAW_KEY() 给（题目那条消息带的 qkey）。
   资料分析 / 一拖五：起笔在左边材料框里的笔画算“材料笔记”，存在这段材料名下（window.DRAW_MKEY()），同一组几道题共用；
   其余笔画还是这道题自己的。
   快捷键：Ctrl+Z 撤销，Ctrl+Y 或 Ctrl+Shift+Z 重做，Esc 关闭。 */
(function () {
  const COLORS = ['#e53935', '#1e63d6', '#222222', '#2e9d57'];
  const st = { on: false, tool: 'pen', color: COLORS[0], width: 3, strokes: [], redo: [], cur: null, key: '' };
  const PREFIX = 'xrpg-draw:', INDEX = 'xrpg-draw-index', KEEP = 300;

  // ---------------------------------------------------------------- 按题存笔记
  const keyNow = () => { try { return (window.DRAW_KEY && window.DRAW_KEY()) || 'page'; } catch (e) { return 'page'; } };
  const mkeyNow = () => { try { return (window.DRAW_MKEY && window.DRAW_MKEY()) || ''; } catch (e) { return ''; } };
  const inMat = (x, y) => { try { return !!(window.DRAW_IN_MAT && window.DRAW_IN_MAT(x, y)); } catch (e) { return false; } };
  function visible(strokes) {           // 最后一次“清空”之后的笔画才算数
    let from = 0;
    strokes.forEach((s, i) => { if (s.clear) from = i + 1; });
    return strokes.slice(from).filter((s) => s.pts && s.pts.length);
  }
  function load(key, mat) {
    if (!key) return [];
    try {
      const raw = JSON.parse(localStorage.getItem(PREFIX + key) || '[]');
      return raw.map((s) => ({ erase: !!s.e, color: s.c, width: s.w, pts: s.p, mat: !!mat }));
    } catch (e) { return []; }
  }
  function store(key, strokes) {
    const list = strokes.map((s) => ({ e: s.erase ? 1 : 0, c: s.color, w: s.width, p: s.pts.map(([x, y]) => [Math.round(x), Math.round(y)]) }));
    let idx = JSON.parse(localStorage.getItem(INDEX) || '[]').filter((k) => k !== key);
    if (list.length) {
      localStorage.setItem(PREFIX + key, JSON.stringify(list));
      idx.push(key);
    } else {
      localStorage.removeItem(PREFIX + key);
    }
    while (idx.length > KEEP) localStorage.removeItem(PREFIX + idx.shift());     // 只留最近 300 份笔记
    localStorage.setItem(INDEX, JSON.stringify(idx));
  }
  function save() {
    if (!st.key) return;
    const all = visible(st.strokes);
    try {
      if (st.mkey) {                    // 材料笔记、题目笔记分开存
        store(st.mkey, all.filter((s) => s.mat));
        store(st.key, all.filter((s) => !s.mat));
      } else {
        store(st.key, all);
      }
    } catch (e) { /* 存不下（浏览器空间满了）就只留在这一次 */ }
    refresh();
  }
  // ✏ 按钮上的小点：这道题有笔记
  function refresh() {
    if (!btn) return;
    let has = false;
    try { has = !!localStorage.getItem(PREFIX + keyNow()) || (!!mkeyNow() && !!localStorage.getItem(PREFIX + mkeyNow())); } catch (e) { /* 读不了就不显示 */ }
    btn.classList.toggle('has', has);
  }
  let layer, canvas, ctx, bar;

  function build() {
    layer = document.createElement('div');
    layer.className = 'draw-layer';
    canvas = document.createElement('canvas');
    layer.appendChild(canvas);
    bar = document.createElement('div');
    bar.className = 'draw-bar';
    bar.innerHTML = `
      <button data-d="close" title="关闭草稿（Esc）">✕</button>
      <button data-d="pen" title="笔">✏️</button>
      ${COLORS.map((c) => `<button data-c="${c}" class="dot" style="--c:${c}" title="颜色"></button>`).join('')}
      <button data-w="3" class="thin" title="细">细</button><button data-w="6" class="thick" title="粗">粗</button>
      <button data-d="eraser" title="橡皮擦">🧽</button>
      <button data-d="undo" title="撤销（Ctrl+Z）">↶</button>
      <button data-d="redo" title="重做（Ctrl+Y）">↷</button>
      <button data-d="clear" title="清除屏幕上的笔记（这道题的，和左边材料上的；可以撤销）">🗑</button>`;
    layer.appendChild(bar);
    document.body.appendChild(layer);
    ctx = canvas.getContext('2d');
    bar.addEventListener('pointerdown', (e) => e.stopPropagation());
    bar.onclick = (e) => {
      const b = e.target.closest('button');
      if (!b) return;
      if (b.dataset.c) { st.color = b.dataset.c; st.tool = 'pen'; }
      else if (b.dataset.w) { st.width = Number(b.dataset.w); if (st.tool !== 'eraser') st.tool = 'pen'; }
      else if (b.dataset.d === 'close') return close();
      else if (b.dataset.d === 'pen') st.tool = 'pen';
      else if (b.dataset.d === 'eraser') st.tool = 'eraser';
      else if (b.dataset.d === 'undo') undo();
      else if (b.dataset.d === 'redo') redo();
      else if (b.dataset.d === 'clear') { if (visible(st.strokes).length) { st.redo = []; st.strokes.push({ clear: true }); paint(); save(); } }
      syncBar();
    };
    layer.addEventListener('contextmenu', (e) => e.preventDefault());     // 平板长按不弹菜单、不选字
    layer.addEventListener('selectstart', (e) => e.preventDefault());
    canvas.addEventListener('pointerdown', down);
    canvas.addEventListener('pointermove', move);
    canvas.addEventListener('pointerup', up);
    canvas.addEventListener('pointercancel', up);
    window.addEventListener('resize', () => st.on && resize());
  }

  function syncBar() {
    bar.querySelectorAll('button').forEach((b) => {
      const on = (b.dataset.d === 'pen' && st.tool === 'pen') || (b.dataset.d === 'eraser' && st.tool === 'eraser')
        || (b.dataset.c && b.dataset.c === st.color && st.tool === 'pen') || (b.dataset.w && Number(b.dataset.w) === st.width);
      b.classList.toggle('on', !!on);
    });
    bar.querySelector('[data-d=undo]').disabled = !st.strokes.length;
    bar.querySelector('[data-d=redo]').disabled = !st.redo.length;
    canvas.style.cursor = st.tool === 'eraser' ? 'cell' : 'crosshair';
  }

  function resize() {
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(innerWidth * dpr);
    canvas.height = Math.round(innerHeight * dpr);
    canvas.style.width = innerWidth + 'px';
    canvas.style.height = innerHeight + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    paint();
  }

  // 每一笔存成点列，撤销/重做就是从头重画；橡皮是“擦除模式”的一笔，“清空”也是一步（可以撤销回来）
  function paint() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    let from = 0;
    st.strokes.forEach((s, i) => { if (s.clear) from = i + 1; });
    for (const s of st.strokes.slice(from)) drawStroke(s);
    if (st.cur) drawStroke(st.cur);
  }
  function drawStroke(s) {
    if (s.clear || !s.pts.length) return;
    ctx.save();
    ctx.globalCompositeOperation = s.erase ? 'destination-out' : 'source-over';
    ctx.strokeStyle = s.color;
    ctx.fillStyle = s.color;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    const p = s.pts;
    if (p.length === 1) {
      ctx.beginPath(); ctx.arc(p[0][0], p[0][1], s.width / 2, 0, Math.PI * 2); ctx.fill();
    } else {
      ctx.lineWidth = s.width;
      ctx.beginPath();
      ctx.moveTo(p[0][0], p[0][1]);
      for (let i = 1; i < p.length - 1; i++) {      // 中点二次曲线，笔迹更顺
        const mx = (p[i][0] + p[i + 1][0]) / 2, my = (p[i][1] + p[i + 1][1]) / 2;
        ctx.quadraticCurveTo(p[i][0], p[i][1], mx, my);
      }
      ctx.lineTo(p[p.length - 1][0], p[p.length - 1][1]);
      ctx.stroke();
    }
    ctx.restore();
  }

  function down(e) {
    if (e.button && e.button !== 0) return;
    canvas.setPointerCapture(e.pointerId);
    const erase = st.tool === 'eraser' || e.button === 5;          // 手写笔的橡皮头也算橡皮
    st.cur = { erase, color: st.color, width: erase ? 22 : st.width, pts: [[e.clientX, e.clientY]], mat: !!st.mkey && inMat(e.clientX, e.clientY) };
    paint();
    e.preventDefault();
  }
  function move(e) {
    if (!st.cur) return;
    const evs = e.getCoalescedEvents ? e.getCoalescedEvents() : [e];
    for (const x of evs) st.cur.pts.push([x.clientX, x.clientY]);
    paint();
    e.preventDefault();
  }
  function up() {
    if (!st.cur) return;
    st.strokes.push(st.cur);
    st.cur = null;
    st.redo = [];
    paint();
    syncBar();
    save();
  }
  function undo() { if (st.strokes.length) { st.redo.push(st.strokes.pop()); paint(); syncBar(); save(); } }
  function redo() { if (st.redo.length) { st.strokes.push(st.redo.pop()); paint(); syncBar(); save(); } }

  function open() {
    if (!layer) build();
    st.on = true;
    st.key = keyNow();
    st.mkey = mkeyNow();
    st.strokes = load(st.mkey, true).concat(load(st.key)); st.redo = []; st.cur = null;     // 这段材料的笔记 + 这道题的笔记接着显示
    try { window.getSelection().removeAllRanges(); } catch (e) { /* 没有选中 */ }   // 平板上按 ✏ 时可能顺带选中了字
    document.documentElement.classList.add('drawing');     // 页面定住，不能滚
    layer.classList.add('on');
    resize();
    syncBar();
    btn.classList.add('on');
  }
  function close() {
    if (st.on) save();                  // 关掉不清：存起来，下次打开这道题还在
    st.on = false;
    st.strokes = []; st.redo = [];
    layer.classList.remove('on');
    document.documentElement.classList.remove('drawing');
    btn.classList.remove('on');
  }

  const btn = document.getElementById('drawBtn');
  if (btn) btn.onclick = () => (st.on ? close() : open());
  document.addEventListener('keydown', (e) => {
    if (!st.on) return;
    const k = e.key.toLowerCase();
    if (k === 'escape') close();
    else if ((e.ctrlKey || e.metaKey) && k === 'z' && !e.shiftKey) { undo(); e.preventDefault(); }
    else if ((e.ctrlKey || e.metaKey) && (k === 'y' || (k === 'z' && e.shiftKey))) { redo(); e.preventDefault(); }
  });
  window.DRAW = { open, close, refresh, state: st };
})();
