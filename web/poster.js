/* 🖼 修炼战报：把今日 / 近七日的修炼成果画成一张 1080×1440 的竖版海报（canvas 现画，不用外部库），可以存图、复制、分享。
   数字：POST /api/poster/stats {span: day|week}（rpg/poster.py）；存图：POST /api/poster/save → 训练/战报/<日期>-今日|近七日.png，
   电脑上点「打开」用看图程序打开，平板上「下载到这台设备」。
   五种风格（宣纸、墨夜、青山、朱砂、星夜），选过的风格和范围记在这台设备里。
   用法：POSTER.open("day" | "week")，洞府「☯ 三才时辰」右上角和人物卡上有入口。 */
(function () {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const W = 1080, H = 1440;
  const KAI = '"STKaiti", "KaiTi", "Kaiti SC", "楷体", "Noto Serif CJK SC", "Source Han Serif SC", "Songti SC", "SimSun", serif';
  const NUM = 'Georgia, "Times New Roman", "Noto Serif CJK SC", serif';
  const STYLES = {
    paper: { name: "宣纸", bg: ["#f6f0e2", "#e8dcc2"], ink: "#1e211d", sub: "#5d5a4c", faint: "rgba(60,50,30,.16)", gold: "#a8791c", accent: "#2f8f78", seal: "#b8412d", hill: "#7d8a78", panel: "rgba(255,252,244,.62)" },
    night: { name: "墨夜", bg: ["#16211d", "#0b100e"], ink: "#e9efe9", sub: "#a7b8b0", faint: "rgba(220,240,230,.12)", gold: "#dcb45a", accent: "#4fcaa8", seal: "#d0533c", hill: "#2c3d37", panel: "rgba(30,44,39,.62)" },
    hill: { name: "青山", bg: ["#e7f1ea", "#c3dccd"], ink: "#16302a", sub: "#4c6a5f", faint: "rgba(20,70,50,.14)", gold: "#9a7420", accent: "#2b8a6e", seal: "#b8412d", hill: "#5f9a82", panel: "rgba(250,255,251,.6)" },
    cinnabar: { name: "朱砂", bg: ["#8a2a20", "#4b120e"], ink: "#fbecd4", sub: "#f0c9a8", faint: "rgba(255,230,200,.16)", gold: "#f2c76a", accent: "#ffd58a", seal: "#f2c76a", hill: "#5e1913", panel: "rgba(80,20,14,.45)" },
    star: { name: "星夜", bg: ["#2a1f45", "#100c1c"], ink: "#efe8fb", sub: "#b9aad6", faint: "rgba(230,220,255,.13)", gold: "#e8b84a", accent: "#a98bf6", seal: "#e0674f", hill: "#3a2d5c", panel: "rgba(40,30,66,.55)" },
  };
  const C3 = { lecture: "#3f9e8f", practice: "#c2463a", review: "#c9a227" };
  const QUOTES = ["道阻且长，行则将至", "不积跬步，无以至千里", "博观而约取，厚积而薄发", "千淘万漉虽辛苦，吹尽狂沙始到金",
    "宝剑锋从磨砺出，梅花香自苦寒来", "业精于勤，荒于嬉", "路漫漫其修远兮，吾将上下而求索", "日日行，不怕千万里",
    "守得云开见月明", "心有所向，日复一日，必有精进", "今日之功，他日之果", "一念既出，万山无阻"];
  const store = {
    get(k, d) { try { return localStorage.getItem("poster." + k) || d; } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem("poster." + k, v); } catch (e) { /* 存不了就算了 */ } },
  };
  let S = null;          // 当前弹窗的状态 {span, style, quote, data, avatar, ver}
  let VER = "";

  // ---------------------------------------------------------------- 画图小工具
  function rr(x, c, y, w, h, r) {   // 圆角矩形路径（老平板内核没有 ctx.roundRect）
    x.beginPath(); x.moveTo(c + r, y); x.arcTo(c + w, y, c + w, y + h, r); x.arcTo(c + w, y + h, c, y + h, r);
    x.arcTo(c, y + h, c, y, r); x.arcTo(c, y, c + w, y, r); x.closePath();
  }
  function text(x, s, px, py, font, color, align = "left", base = "alphabetic") {
    x.font = font; x.fillStyle = color; x.textAlign = align; x.textBaseline = base; x.fillText(s, px, py);
  }
  function spaced(x, s, px, py, gap) {   // 字距拉开（居中）
    const ws = [...s].map((ch) => x.measureText(ch).width);
    let cx = px - (ws.reduce((a, b) => a + b, 0) + gap * (ws.length - 1)) / 2;
    x.textAlign = "left";
    [...s].forEach((ch, i) => { x.fillText(ch, cx, py); cx += ws[i] + gap; });
  }
  function fit(x, s, maxW, font) { x.font = font; if (x.measureText(s).width <= maxW) return s; while (s.length > 1 && x.measureText(s + "…").width > maxW) s = s.slice(0, -1); return s + "…"; }
  const hm = (m) => { m = Math.round(m || 0); return m >= 60 ? [Math.floor(m / 60), "时", m % 60 ? [m % 60, "分"] : null] : [m, "分", null]; };
  function drawHm(x, m, cx, y, big, small, color, sub) {   // “3时25分”：数字大、单位小，整体居中
    const [h, u1, rest] = hm(m);
    const parts = [[String(h), `bold ${big}px ${NUM}`, color], [u1, `${small}px ${KAI}`, sub]];
    if (rest) parts.push([String(rest[0]), `bold ${big}px ${NUM}`, color], [rest[1], `${small}px ${KAI}`, sub]);
    const ws = parts.map(([s, f]) => { x.font = f; return x.measureText(s).width + 4; });
    let px = cx - ws.reduce((a, b) => a + b, 0) / 2;
    parts.forEach(([s, f, c], i) => { text(x, s, px, y, f, c); px += ws[i]; });
  }

  function background(x, st) {
    const g = x.createLinearGradient(0, 0, 0, H);
    g.addColorStop(0, st.bg[0]); g.addColorStop(1, st.bg[1]);
    x.fillStyle = g; x.fillRect(0, 0, W, H);
    // 远山：三层，越远越淡
    [[0.10, 1180, 90], [0.16, 1250, 70], [0.24, 1320, 55]].forEach(([a, base, amp], k) => {
      x.save(); x.globalAlpha = a; x.fillStyle = st.hill; x.beginPath(); x.moveTo(0, H);
      for (let px = 0; px <= W; px += 20) {
        const y = base - amp * (0.6 * Math.sin(px / (170 + k * 40) + k * 1.7) + 0.4 * Math.sin(px / (67 + k * 13) + k)) - (k === 0 ? 60 * Math.exp(-Math.pow((px - 760) / 160, 2)) : 0);
        x.lineTo(px, y);
      }
      x.lineTo(W, H); x.closePath(); x.fill(); x.restore();
    });
    // 祥云：几团卷云
    x.save(); x.strokeStyle = st.faint; x.lineWidth = 3;
    [[150, 120, 1], [930, 210, 0.8], [880, 1010, 0.9], [120, 960, 0.7]].forEach(([cx, cy, s]) => {
      for (let i = 0; i < 3; i++) { x.beginPath(); x.arc(cx + i * 38 * s, cy - (i % 2) * 14 * s, (26 - i * 4) * s, Math.PI * 0.9, Math.PI * 2.3); x.stroke(); }
    });
    x.restore();
    // 边框：双线 + 四角回纹
    x.save(); x.strokeStyle = st.gold; x.globalAlpha = 0.75;
    x.lineWidth = 3; x.strokeRect(34, 34, W - 68, H - 68);
    x.lineWidth = 1.2; x.strokeRect(48, 48, W - 96, H - 96);
    [[34, 34, 1, 1], [W - 34, 34, -1, 1], [34, H - 34, 1, -1], [W - 34, H - 34, -1, -1]].forEach(([px, py, sx, sy]) => {
      x.beginPath(); x.moveTo(px + sx * 4, py + sy * 60); x.lineTo(px + sx * 4, py + sy * 4); x.lineTo(px + sx * 60, py + sy * 4);
      x.moveTo(px + sx * 26, py + sy * 26); x.lineTo(px + sx * 44, py + sy * 26); x.lineTo(px + sx * 44, py + sy * 44); x.lineTo(px + sx * 26, py + sy * 44); x.closePath();
      x.lineWidth = 2.5; x.stroke();
    });
    x.restore();
  }

  function seal(x, st, cx, cy) {   // 朱印：「修炼有成」四字回文印，略歪
    x.save(); x.translate(cx, cy); x.rotate(-0.08);
    x.fillStyle = st.seal; x.globalAlpha = 0.9; rr(x, -62, -62, 124, 124, 10); x.fill();
    x.globalAlpha = 1; x.strokeStyle = st.bg[0]; x.lineWidth = 3; rr(x, -53, -53, 106, 106, 6); x.stroke();
    const ch = ["修", "有", "炼", "成"];   // 印文从右往左竖读：修炼 / 有成
    [[22, -22], [-22, -22], [22, 24], [-22, 24]].forEach(([px, py], i) => text(x, ch[i], px, py + 15, `bold 42px ${KAI}`, st.bg[0], "center"));
    x.restore();
  }

  function ring(x, st, cx, cy, r, frac, color) {
    x.save(); x.lineCap = "round";
    x.strokeStyle = st.faint; x.lineWidth = 22; x.beginPath(); x.arc(cx, cy, r, 0, Math.PI * 2); x.stroke();
    if (frac > 0) { x.strokeStyle = color; x.beginPath(); x.arc(cx, cy, r, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * Math.min(1, frac)); x.stroke(); }
    x.restore();
  }

  function dateLabel(d) {
    const wk = "日一二三四五六";
    const f = (s) => { const t = new Date(s + "T12:00:00"); return { y: t.getFullYear(), m: t.getMonth() + 1, d: t.getDate(), w: wk[t.getDay()] }; };
    if (d.span === "week") { const a = f(d.days[0]), b = f(d.days[d.days.length - 1]); return `${a.m}月${a.d}日 — ${b.m}月${b.d}日 · 近七日`; }
    const t = f(d.days[0]); return `${t.y}年${t.m}月${t.d}日 · 周${t.w}`;
  }

  // ---------------------------------------------------------------- 整张海报
  function draw(canvas) {
    const d = S.data, st = STYLES[S.style] || STYLES.paper;
    canvas.width = W; canvas.height = H;
    const x = canvas.getContext("2d");
    background(x, st);
    // 抬头
    x.font = `30px ${KAI}`; x.fillStyle = st.gold; x.textBaseline = "alphabetic"; spaced(x, `${d.brand} · 修炼战报`, W / 2, 128, 10);
    text(x, dateLabel(d), W / 2, 196, `bold 48px ${KAI}`, st.ink, "center");
    x.save(); x.strokeStyle = st.gold; x.globalAlpha = .6; x.lineWidth = 1.5;
    x.beginPath(); x.moveTo(250, 228); x.lineTo(500, 228); x.moveTo(580, 228); x.lineTo(830, 228); x.stroke();
    x.fillStyle = st.gold; x.translate(540, 228); x.rotate(Math.PI / 4); x.fillRect(-7, -7, 14, 14); x.restore();

    // 人物：头像 + 道号 + 境界
    const ax = 190, ay = 340, ar = 74;
    x.save(); x.beginPath(); x.arc(ax, ay, ar, 0, Math.PI * 2); x.closePath();
    if (S.avatar) { x.clip(); const im = S.avatar, s = Math.max(ar * 2 / im.width, ar * 2 / im.height); x.drawImage(im, ax - im.width * s / 2, ay - im.height * s / 2, im.width * s, im.height * s); }
    else { x.fillStyle = st.panel; x.fill(); text(x, [...(d.persona.id || "修")][0], ax, ay + 22, `bold 64px ${KAI}`, st.ink, "center"); }
    x.restore();
    x.save(); x.strokeStyle = st.gold; x.lineWidth = 4; x.beginPath(); x.arc(ax, ay, ar + 6, 0, Math.PI * 2); x.stroke(); x.restore();
    text(x, fit(x, d.persona.id || "", 560, `bold 54px ${KAI}`), 300, 318, `bold 54px ${KAI}`, st.ink);
    text(x, fit(x, d.realm, 420, `bold 44px ${KAI}`), 300, 382, `bold 44px ${KAI}`, st.gold);
    text(x, `${d.score_word} ${d.score} 分 · 目标 ${d.target} 分${d.streak ? ` · 连续打卡 ${d.streak} 天` : ""}`, 300, 428, `28px ${KAI}`, st.sub);

    // 功行：左边一圈（今日：分钟 / 目标；近七日：达标天数），右边三才
    x.save(); x.fillStyle = st.panel; rr(x, 80, 480, W - 160, 330, 26); x.fill(); x.restore();
    const cx = 250, cy = 645;
    const frac = d.span === "week" ? d.hit / 7 : d.minutes / Math.max(1, d.goal);
    ring(x, st, cx, cy, 118, frac, frac >= 1 ? st.gold : st.accent);
    drawHm(x, d.minutes, cx, cy + 4, 58, 28, st.ink, st.sub);
    text(x, d.span === "week" ? `达标 ${d.hit}/7 天` : `目标 ${d.goal} 分`, cx, cy + 50, `24px ${KAI}`, st.sub, "center");
    if (frac >= 1) text(x, d.span === "week" ? "✦ 七日精进 ✦" : "✦ 今日圆满 ✦", cx, cy - 58, `24px ${KAI}`, st.gold, "center");
    const total = d.split.lecture + d.split.practice + d.split.review;
    [["lecture", "闻", "听课"], ["practice", "历", "做题"], ["review", "温", "复习"]].forEach(([k, s, n], i) => {
      const y = 556 + i * 92, v = d.split[k];
      x.save(); x.fillStyle = C3[k]; x.beginPath(); x.arc(452, y + 18, 26, 0, Math.PI * 2); x.fill(); x.restore();
      text(x, s, 452, y + 30, `bold 32px ${KAI}`, "#fff", "center");
      text(x, n, 496, y + 30, `30px ${KAI}`, st.ink);
      const [h, u1, rest] = hm(v);
      text(x, `${h}${u1}${rest ? rest[0] + rest[1] : ""}`, 950, y + 30, `bold 30px ${NUM}`, st.ink, "right");
      x.save(); x.fillStyle = st.faint; rr(x, 496, y + 48, 454, 12, 6); x.fill();
      if (total && v) { x.fillStyle = C3[k]; rr(x, 496, y + 48, Math.max(12, 454 * v / total), 12, 6); x.fill(); }
      x.restore();
    });

    // 四宫格：做题、温简、修为、打卡
    const q = d.questions, c = d.cards;
    const tiles = [
      ["试炼", q.total ? String(q.total) : "—", "道", q.total ? `正确率 ${Math.round(q.acc * 100)}%` : "未曾出手"],
      [d.yj_review, c.total ? String(c.total) : "—", "次", c.total ? `记住 ${Math.round(c.rate * 100)}%` : "玉简未温"],
      [d.xp_word, d.xp > 0 ? "+" + d.xp : "—", "", d.dao ? `道心 · ${d.dao}` : ""],
      ["打卡", String(d.streak || 0), "天", "连续不辍"],
    ];
    tiles.forEach(([name, num, unit, sub], i) => {
      const tx = 80 + i * 236, ty = 840, tw = 212, th = 190;
      x.save(); x.fillStyle = st.panel; rr(x, tx, ty, tw, th, 22); x.fill(); x.restore();
      text(x, name, tx + tw / 2, ty + 46, `28px ${KAI}`, st.sub, "center");
      x.font = `bold 60px ${NUM}`; const nw = x.measureText(num).width; x.font = `26px ${KAI}`; const uw = unit ? x.measureText(unit).width + 6 : 0;
      text(x, num, tx + tw / 2 - uw / 2 - nw / 2, ty + 118, `bold 60px ${NUM}`, i === 2 && d.xp > 0 ? st.gold : st.ink);
      if (unit) text(x, unit, tx + tw / 2 + nw / 2 - uw / 2 + 6, ty + 118, `26px ${KAI}`, st.sub);
      text(x, fit(x, sub, tw - 20, `24px ${KAI}`), tx + tw / 2, ty + 160, `24px ${KAI}`, st.sub, "center");
    });

    // 下半：近七日柱状 / 今日用功最勤的板块
    const by = 1062;
    if (d.span === "week") {
      text(x, "七日功行", 96, by + 8, `bold 30px ${KAI}`, st.ink);
      const max = Math.max(d.goal, ...d.per_day, 1), bx = 120, bw = 840, bh = 80, top = by + 22;
      const gy = top + bh - bh * d.goal / max;
      x.save(); x.setLineDash([8, 8]); x.strokeStyle = st.gold; x.globalAlpha = .7; x.lineWidth = 2;
      x.beginPath(); x.moveTo(bx, gy); x.lineTo(bx + bw, gy); x.stroke(); x.restore();
      d.per_day.forEach((m, i) => {
        const w = 62, px = bx + i * (bw / 7) + (bw / 7 - w) / 2, h = Math.max(4, bh * m / max);
        x.save(); x.fillStyle = m >= d.goal ? st.gold : st.accent; x.globalAlpha = m ? 0.9 : 0.25; rr(x, px, top + bh - h, w, h, Math.min(8, h / 2)); x.fill(); x.restore();
        const t = new Date(d.days[i] + "T12:00:00");
        text(x, i === 6 ? "今" : "日一二三四五六"[t.getDay()], px + w / 2, top + bh + 32, `24px ${KAI}`, st.sub, "center");
      });
      if (d.top.length) text(x, fit(x, "主修：" + d.top.map((b) => b.board).join(" · "), 640, `26px ${KAI}`), 984, by + 8, `26px ${KAI}`, st.sub, "right");
    } else {
      text(x, "用功最勤", 96, by + 8, `bold 30px ${KAI}`, st.ink);
      if (!d.top.length) text(x, "今日尚未分到板块的功课", 260, by + 8, `26px ${KAI}`, st.sub);
      const mx = Math.max(1, ...d.top.map((b) => b.minutes));
      d.top.forEach((b, i) => {
        const y = by - 22 + i * 58;
        text(x, fit(x, b.board, 180, `28px ${KAI}`), 260, y + 30, `28px ${KAI}`, st.ink);
        x.save(); x.fillStyle = st.faint; rr(x, 450, y + 12, 380, 16, 8); x.fill();
        x.fillStyle = [st.gold, st.accent, st.sub][i]; rr(x, 450, y + 12, Math.max(16, 380 * b.minutes / mx), 16, 8); x.fill(); x.restore();
        const [h, u1, rest] = hm(b.minutes);
        text(x, `${h}${u1}${rest ? rest[0] + rest[1] : ""}`, 980, y + 30, `bold 26px ${NUM}`, st.sub, "right");
      });
    }

    // 寄语 + 印 + 落款
    const quote = (S.quote || "").trim();
    if (quote) {
      x.font = `italic 40px ${KAI}`;
      const lines = []; let cur = "";
      for (const ch of quote) { if (x.measureText(cur + ch).width > 700) { lines.push(cur); cur = ch; } else cur += ch; }
      if (cur) lines.push(cur);
      lines.slice(0, 2).forEach((l, i) => text(x, (i === 0 ? "「" : "") + l + (i === Math.min(lines.length, 2) - 1 ? "」" : ""), 470, 1292 + i * 50 - (lines.length > 1 ? 26 : 0), `40px ${KAI}`, st.ink, "center"));
    }
    seal(x, st, 916, 1276);
    text(x, `${d.brand}${VER ? " v" + VER : ""} · ${d.tutor ? "师从 " + d.tutor : ""}`, W / 2, 1376, `22px ${KAI}`, st.sub, "center");
  }

  // ---------------------------------------------------------------- 弹窗
  async function load() {
    const r = await api("/api/poster/stats", { span: S.span });
    const T = (k, dflt) => (typeof DASH !== "undefined" && DASH?.theme?.terms?.[k]) || dflt;
    r.brand = (T("brand", "行测修仙传") || "行测修仙传").replace(/^\S+\s/, "");
    r.score_word = String(T("score", "道行")).replace(/（.*?）|\(.*?\)/g, ""); r.xp_word = T("xp", "修为"); r.yj_review = T("yj_review", "温简");
    r.tutor = r.persona.tutor;
    S.data = r;
    S.avatar = null;
    if (r.persona.avatar) {
      S.avatar = await new Promise((ok) => { const im = new Image(); im.onload = () => ok(im); im.onerror = () => ok(null); im.src = r.persona.avatar; });
    }
  }
  function repaint() { const c = document.getElementById("psCanvas"); if (c && S.data) draw(c); }

  async function open(span) {
    if (!VER) { try { VER = (await api("/api/version")).version || ""; } catch (e) { /* 没有就不写 */ } }
    const dark = document.documentElement.dataset.theme === "dark";
    S = { span: span === "week" ? "week" : store.get("span", "day"), style: store.get("style", dark ? "night" : "paper"), quote: QUOTES[Math.floor(Math.random() * QUOTES.length)], data: null };
    if (span) S.span = span === "week" ? "week" : "day";
    const m = document.getElementById("modal");
    m.innerHTML = `<div class="modal-box ps-box">
      <div class="ps-preview"><canvas id="psCanvas" width="${W}" height="${H}"></canvas><div class="ps-wait" id="psWait">正在拓印…</div></div>
      <div class="ps-side">
        <h3>🖼 修炼战报</h3>
        <div class="ps-label">范围</div>
        <div class="ps-seg" id="psSpan"><a data-v="day">今日</a><a data-v="week">近七日</a></div>
        <div class="ps-label">风格</div>
        <div class="ps-styles" id="psStyle">${Object.entries(STYLES).map(([k, s]) => `<a data-v="${k}" title="${s.name}" style="--a:${s.bg[0]};--b:${s.bg[1]};--c:${s.gold}"><i></i><span>${s.name}</span></a>`).join("")}</div>
        <div class="ps-label">寄语 <small class="faint">（空着就不写）</small></div>
        <div class="row ps-quote"><input id="psQuote" maxlength="40" value="${esc(S.quote)}"><button class="ghost small" id="psDice" title="换一句">🎲</button></div>
        <div class="ps-actions">
          <button class="primary" id="psSave">💾 保存图片</button>
          ${window.isSecureContext && window.ClipboardItem && navigator.clipboard?.write ? '<button id="psCopy">📋 复制图片</button>' : ""}
          <button class="ghost" id="psClose">关闭</button>
        </div>
        <p class="small faint">图片存在库里 训练/战报/，同一天同一范围再存会覆盖。</p>
      </div></div>`;
    m.classList.remove("hidden");
    const mark = () => {
      m.querySelectorAll("#psSpan a").forEach((a) => a.classList.toggle("on", a.dataset.v === S.span));
      m.querySelectorAll("#psStyle a").forEach((a) => a.classList.toggle("on", a.dataset.v === S.style));
    };
    mark();
    const reload = async () => {
      const w = document.getElementById("psWait"); if (w) w.hidden = false;
      try { await load(); repaint(); } catch (e) { showError(e); }
      if (w) w.hidden = true;
    };
    m.querySelectorAll("#psSpan a").forEach((a) => (a.onclick = () => { if (S.span === a.dataset.v) return; S.span = a.dataset.v; store.set("span", S.span); mark(); reload(); }));
    m.querySelectorAll("#psStyle a").forEach((a) => (a.onclick = () => { S.style = a.dataset.v; store.set("style", S.style); mark(); repaint(); }));
    const qi = document.getElementById("psQuote");
    qi.oninput = () => { S.quote = qi.value; repaint(); };
    document.getElementById("psDice").onclick = () => {
      let q; do { q = QUOTES[Math.floor(Math.random() * QUOTES.length)]; } while (q === S.quote && QUOTES.length > 1);
      S.quote = qi.value = q; repaint();
    };
    document.getElementById("psClose").onclick = () => m.classList.add("hidden");
    m.onclick = (e) => { if (e.target === m) m.classList.add("hidden"); };
    document.getElementById("psSave").onclick = save;
    const cp = document.getElementById("psCopy");
    if (cp) cp.onclick = () => document.getElementById("psCanvas").toBlob(async (b) => {
      try { await navigator.clipboard.write([new ClipboardItem({ "image/png": b })]); toast("📋 已复制，可以直接粘贴到微信 / QQ"); } catch (e) { showError(new Error("复制不了：" + (e.message || e))); }
    }, "image/png");
    await reload();
  }

  async function save() {
    const b = document.getElementById("psSave");
    if (!S?.data || b.disabled) return;
    b.disabled = true; b.textContent = "💾 保存中…";
    try {
      const r = await api("/api/poster/save", { span: S.span, data: document.getElementById("psCanvas").toDataURL("image/png") });
      const local = ["127.0.0.1", "localhost", "[::1]"].includes(location.hostname);
      const el = document.createElement("div");
      el.className = "toast";
      el.innerHTML = `🖼 战报存好了 · ${(r.size / 1024).toFixed(0)} KB<div class="small muted">${esc(r.path)}</div>
        <div class="row">${local ? '<button class="small primary" data-o="open">打开</button>' : `<a class="small" href="${esc(r.url)}" download="${esc(r.name)}" target="_blank" rel="noopener">⬇ 下载到这台设备</a>`}
          <span class="spacer"></span><button class="small ghost" data-o="x">关</button></div>`;
      document.getElementById("toasts").appendChild(el);
      const tm = setTimeout(() => el.remove(), 20000);
      el.querySelector('[data-o="x"]').onclick = () => { clearTimeout(tm); el.remove(); };
      const o = el.querySelector('[data-o="open"]');
      if (o) o.onclick = async () => { try { await api("/api/notes/open", { path: r.path }); } catch (e) { showError(e); } };
    } catch (e) { showError(e); }
    b.disabled = false; b.textContent = "💾 保存图片";
  }

  window.POSTER = { open, draw: (c) => draw(c), styles: Object.keys(STYLES) };
})();
