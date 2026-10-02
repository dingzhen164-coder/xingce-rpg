/* 草稿笔：点右上角 ✏，页面定住，盖一层透明画布可以写写画画（像粉笔 App 的草稿）。
   笔 / 橡皮 / 撤销 / 重做 / 一键清空；鼠标、触屏、手写笔都能用。关掉草稿就清空（下一题重新画）。
   快捷键：Ctrl+Z 撤销，Ctrl+Y 或 Ctrl+Shift+Z 重做，Esc 关闭。 */
(function () {
  const COLORS = ['#e53935', '#1e63d6', '#222222', '#2e9d57'];
  const st = { on: false, tool: 'pen', color: COLORS[0], width: 3, strokes: [], redo: [], cur: null };
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
      <button data-d="clear" title="一键清空">🗑</button>`;
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
      else if (b.dataset.d === 'clear') { if (st.strokes.length) { st.redo = []; st.strokes.push({ clear: true }); paint(); } }
      syncBar();
    };
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
    st.cur = { erase, color: st.color, width: erase ? 22 : st.width, pts: [[e.clientX, e.clientY]] };
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
  }
  function undo() { if (st.strokes.length) { st.redo.push(st.strokes.pop()); paint(); syncBar(); } }
  function redo() { if (st.redo.length) { st.strokes.push(st.redo.pop()); paint(); syncBar(); } }

  function open() {
    if (!layer) build();
    st.on = true;
    st.strokes = []; st.redo = []; st.cur = null;
    document.documentElement.classList.add('drawing');     // 页面定住，不能滚
    layer.classList.add('on');
    resize();
    syncBar();
    btn.classList.add('on');
  }
  function close() {
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
  window.DRAW = { open, close, state: st };
})();
