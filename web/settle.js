/* 收功结算：记一笔听道 / 自练，或者在修炼里做完一项复习、实战后，弹出一幕结算。
   人物 = 洞府头像（换了头像这里也跟着换）接一身道袍：听课、复习是悬空打坐，做题是站立；双手结印，
   周身是三才时辰对应颜色的灵光（听课青、做题朱、复习金），脚下法阵缓转，灵气上升；
   下面两条进度条从之前涨到之后：今日功行（+分钟）和修为（+修为）。
   用法：const s = SETTLE.snap(); …记录或做完… await refresh(); SETTLE.show({ kind, title, sub, before: s });
   点“收功”、点空白处或按 Esc 关闭。 */
(function () {
  const KIND = {
    lecture: { color: "#3f9e8f", glow: "#7fe0cf", pose: "sit", seal: "闻", word: "闻法圆满", cat: "听课" },
    review: { color: "#c9a227", glow: "#ffe08a", pose: "sit", seal: "温", word: "温养功成", cat: "复习" },
    practice: { color: "#c2463a", glow: "#ff9a7a", pose: "stand", seal: "历", word: "历练归来", cat: "做题" },
  };
  const TRIGRAMS = "☰☱☲☳☴☵☶☷";

  function snap() {
    const d = window.DASH_REF ? window.DASH_REF() : null;
    if (!d) return null;
    return { today: d.minutes?.today || 0, goal: d.minutes?.goal || 300, xp: d.xp || 0, frac: d.realm?.frac || 0,
             realm: d.realm?.name || "", ts: Object.assign({ lecture: 0, practice: 0, review: 0 }, d.timesplit?.today || {}) };
  }

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // 道袍人物（SVG）。头部是圆形头像，没有头像时写名字的第一个字
  function figure(pose, k, avatar, letter) {
    const robe = `url(#robe-${pose})`;
    const head = avatar
      ? `<clipPath id="headClip"><circle cx="100" cy="64" r="25"/></clipPath>
         <image href="${esc(avatar)}" x="75" y="39" width="50" height="50" preserveAspectRatio="xMidYMid slice" clip-path="url(#headClip)"/>`
      : `<circle cx="100" cy="64" r="25" fill="#f1e2c6"/><text x="100" y="73" text-anchor="middle" font-size="26" class="st-letter">${esc(letter)}</text>`;
    const defs = `<defs>
        <linearGradient id="robe-${pose}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#fbf7ee"/><stop offset=".55" stop-color="#e9e2d2"/><stop offset="1" stop-color="${k.color}" stop-opacity=".55"/></linearGradient>
        <linearGradient id="sleeve-${pose}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#f6f1e6"/><stop offset="1" stop-color="${k.color}" stop-opacity=".35"/></linearGradient>
        <radialGradient id="haloFill"><stop offset=".55" stop-color="${k.glow}" stop-opacity="0"/><stop offset=".8" stop-color="${k.glow}" stop-opacity=".35"/><stop offset="1" stop-color="${k.glow}" stop-opacity="0"/></radialGradient>
        <radialGradient id="spark"><stop offset="0" stop-color="#fff"/><stop offset=".35" stop-color="${k.glow}"/><stop offset="1" stop-color="${k.glow}" stop-opacity="0"/></radialGradient>
      </defs>`;
    // 结印的双手：掌根相合，食指中指并拢上指（剑诀），指尖一点灵光
    const mudra = (y) => `<g class="st-mudra" transform="translate(100 ${y}) scale(1.55) translate(-100 ${-y})">
        <path d="M93 ${y + 14} Q92 ${y + 2} 97 ${y - 4} L99 ${y - 22} Q100 ${y - 25} 101 ${y - 22} L103 ${y - 4} Q108 ${y + 2} 107 ${y + 14} Q100 ${y + 19} 93 ${y + 14}Z" fill="#f3dcc0" stroke="#c9a888" stroke-width=".8"/>
        <path d="M97 ${y - 3} L103 ${y - 3} M96.5 ${y + 3} Q100 ${y + 5} 103.5 ${y + 3}" stroke="#c9a888" stroke-width=".7" fill="none"/>
        <circle class="st-spark" cx="100" cy="${y - 25}" r="11" fill="url(#spark)"/></g>`;
    // 头光：头后一圈光轮
    const halo = `<g class="st-halo"><circle cx="100" cy="64" r="40" fill="url(#haloFill)"/>
        <circle cx="100" cy="64" r="34" fill="none" stroke="${k.glow}" stroke-width="1.4" opacity=".9"/>
        <circle cx="100" cy="64" r="38.5" fill="none" stroke="${k.glow}" stroke-width=".6" stroke-dasharray="1.5 3" opacity=".8"/></g>`;
    // 披帛：从肩后绕出、两端飘起
    const ribbon = (y0, y1) => `<path class="st-ribbon" d="M74 ${y0} Q30 ${y0 + 20} 22 ${y1} Q16 ${y1 + 26} 6 ${y1 + 40}" fill="none" stroke="${k.glow}" stroke-width="4" stroke-linecap="round" opacity=".55"/>
        <path class="st-ribbon r" d="M126 ${y0} Q170 ${y0 + 20} 178 ${y1} Q184 ${y1 + 26} 194 ${y1 + 40}" fill="none" stroke="${k.glow}" stroke-width="4" stroke-linecap="round" opacity=".55"/>`;
    if (pose === "sit") {
      return `<svg class="st-fig sit" viewBox="0 0 200 260" aria-hidden="true">${defs}
        <ellipse cx="100" cy="236" rx="76" ry="13" fill="${k.color}" opacity=".18"/>
        ${halo}${ribbon(120, 170)}
        <path d="M30 232 Q36 196 100 192 Q164 196 170 232 Q100 246 30 232Z" fill="${robe}" stroke="#d8ccb3" stroke-width="1"/>
        <path d="M58 214 Q100 206 142 214" stroke="#d8ccb3" stroke-width="1" fill="none"/>
        <path d="M36 226 Q52 212 72 216 M164 226 Q148 212 128 216" stroke="#d8ccb3" stroke-width="1" fill="none"/>
        <path d="M68 112 Q100 98 132 112 L150 206 Q100 216 50 206 Z" fill="${robe}" stroke="#d8ccb3" stroke-width="1"/>
        <path d="M86 108 L100 140 L114 108" fill="none" stroke="${k.color}" stroke-width="2.4" opacity=".7"/>
        <path d="M70 114 Q46 150 56 196 Q72 204 92 190 Q86 168 94 152 Q84 136 82 118Z" fill="url(#sleeve-sit)" stroke="#d8ccb3" stroke-width="1"/>
        <path d="M130 114 Q154 150 144 196 Q128 204 108 190 Q114 168 106 152 Q116 136 118 118Z" fill="url(#sleeve-sit)" stroke="#d8ccb3" stroke-width="1"/>
        <rect x="93" y="84" width="14" height="16" rx="5" fill="#f1dcc0"/>
        ${head}${mudra(150)}</svg>`;
    }
    return `<svg class="st-fig stand" viewBox="0 0 200 300" aria-hidden="true">${defs}
      <ellipse cx="100" cy="288" rx="58" ry="9" fill="${k.color}" opacity=".2"/>
      ${halo}${ribbon(118, 190)}
      <path d="M70 110 Q100 98 130 110 L152 280 Q100 292 48 280 Z" fill="${robe}" stroke="#d8ccb3" stroke-width="1"/>
      <path d="M78 168 Q100 174 122 168" stroke="${k.color}" stroke-width="5" opacity=".65" fill="none"/>
      <path d="M100 172 L96 196 M100 172 L105 194" stroke="${k.color}" stroke-width="1.6" opacity=".6"/>
      <path d="M86 106 L100 136 L114 106" fill="none" stroke="${k.color}" stroke-width="2.4" opacity=".7"/>
      <path class="st-sleeve-l" d="M72 114 Q44 152 50 214 Q66 222 82 204 Q84 168 95 152 Q84 136 82 118Z" fill="url(#sleeve-stand)" stroke="#d8ccb3" stroke-width="1"/>
      <path class="st-sleeve-r" d="M128 114 Q156 152 150 214 Q134 222 118 204 Q116 168 105 152 Q116 136 118 118Z" fill="url(#sleeve-stand)" stroke="#d8ccb3" stroke-width="1"/>
      <rect x="93" y="84" width="14" height="16" rx="5" fill="#f1dcc0"/>
      ${head}${mudra(146)}</svg>`;
  }

  function meter(label, from, to, unit, gainText, color) {
    const a = Math.max(0, Math.min(1, from)), b = Math.max(0, Math.min(1, to));
    return `<div class="st-meter"><div class="st-mrow"><span>${label}</span><span class="st-gain" style="color:${color}">${gainText}</span><span class="st-unit">${unit}</span></div>
      <div class="st-bar"><span class="st-base" style="width:${(Math.min(a, b) * 100).toFixed(1)}%"></span>
        <span class="st-add" data-from="${(a * 100).toFixed(1)}" data-to="${(b * 100).toFixed(1)}" style="left:${(a * 100).toFixed(1)}%;width:0;background:${color}"></span>
        <span class="st-head" style="left:${(a * 100).toFixed(1)}%;background:${color}"></span></div></div>`;
  }

  let el = null, keyFn = null;
  function close() {
    if (!el) return;
    el.classList.add("out");
    const x = el; el = null;
    setTimeout(() => x.remove(), 450);
    document.removeEventListener("keydown", keyFn);
  }

  function show({ kind = "review", title = "", sub = "", lines = [], before = null }) {
    const k = KIND[kind] || KIND.review;
    const d = window.DASH_REF ? window.DASH_REF() : null;
    const after = snap();
    if (!after) return;
    const b = before || after;
    const p = d?.persona || {};
    close();
    const goal = after.goal || 300;
    const dMin = Math.max(0, Math.round(after.today - b.today));
    const dXp = Math.max(0, after.xp - b.xp);
    const leveled = after.realm !== b.realm;
    const xpFrom = leveled ? 0 : b.frac, xpTo = after.frac;
    const catGain = Math.max(0, Math.round((after.ts[kind] || 0) - (b.ts[kind] || 0)));
    const parts = Array.from({ length: 26 }, (_, i) => {
      const x = 8 + Math.random() * 84, s = 2 + Math.random() * 4, dl = (Math.random() * 3.2).toFixed(2), du = (2.6 + Math.random() * 2.4).toFixed(2);
      return `<i style="left:${x.toFixed(1)}%;width:${s.toFixed(1)}px;height:${s.toFixed(1)}px;animation-delay:${dl}s;animation-duration:${du}s"></i>`;
    }).join("");
    const ring = `<svg class="st-ring" viewBox="0 0 200 200" aria-hidden="true">
        <circle cx="100" cy="100" r="94" fill="none" stroke="${k.glow}" stroke-width="1.2" opacity=".8"/>
        <circle cx="100" cy="100" r="84" fill="none" stroke="${k.glow}" stroke-width=".6" stroke-dasharray="2 5" opacity=".9"/>
        <circle cx="100" cy="100" r="58" fill="none" stroke="${k.glow}" stroke-width=".8" opacity=".6"/>
        ${[...TRIGRAMS].map((g, i) => { const a = i * Math.PI / 4 - Math.PI / 2; return `<text x="${(100 + 71 * Math.cos(a)).toFixed(1)}" y="${(100 + 71 * Math.sin(a) + 5).toFixed(1)}" text-anchor="middle" font-size="14" fill="${k.glow}" transform="rotate(${i * 45} ${(100 + 71 * Math.cos(a)).toFixed(1)} ${(100 + 71 * Math.sin(a)).toFixed(1)})">${g}</text>`; }).join("")}
        <path d="M100 42 L150 129 L50 129Z M100 158 L50 71 L150 71Z" fill="none" stroke="${k.glow}" stroke-width=".6" opacity=".5"/></svg>`;
    el = document.createElement("div");
    el.className = `settle st-${kind} st-${k.pose}`;
    el.style.setProperty("--st", k.color);
    el.style.setProperty("--stg", k.glow);
    el.innerHTML = `<div class="st-veil"></div>
      <div class="st-stage">
        <div class="st-scene">
          <div class="st-aura"></div>${k.pose === "stand" ? '<div class="st-pillar"></div>' : ""}
          <div class="st-ringwrap">${ring}</div>
          <div class="st-seal">${k.seal}</div>
          <div class="st-body">${figure(k.pose, k, p.avatar, (p.id || "修").slice(0, 1))}</div>
          <div class="st-parts">${parts}</div>
        </div>
        <div class="st-panel">
          <div class="st-word">${esc(k.word)}</div>
          <div class="st-title">${esc(title)}</div>
          ${sub ? `<div class="st-sub">${esc(sub)}</div>` : ""}
          ${lines.length ? `<div class="st-lines">${lines.map((l) => `<span>${esc(l)}</span>`).join("")}</div>` : ""}
          ${meter(`今日功行 <b>${Math.round(after.today)}</b> / ${goal} 分钟`, b.today / goal, after.today / goal, "", dMin ? `+${dMin} 分钟` : "", k.glow)}
          ${meter(`修为 · ${esc(after.realm)}`, xpFrom, xpTo, "", dXp ? `+${dXp} 修为` : "", k.glow)}
          ${catGain ? `<div class="st-cat">今日${k.cat} <b>${Math.round(after.ts[kind] || 0)}</b> 分钟（本次 +${catGain}）</div>` : ""}
          ${leveled ? `<div class="st-up">✦ 境界精进：${esc(b.realm)} → ${esc(after.realm)} ✦</div>` : ""}
          <button class="primary st-btn">收功</button>
        </div>
      </div>`;
    document.body.appendChild(el);
    requestAnimationFrame(() => {
      el.classList.add("in");
      setTimeout(() => el && el.querySelectorAll(".st-add").forEach((s) => {
        const f = Number(s.dataset.from), t = Number(s.dataset.to);
        s.style.width = Math.max(0, t - f) + "%";
        const h = s.nextElementSibling; if (h) h.style.left = t + "%";
      }), 900);
    });
    el.querySelector(".st-btn").onclick = close;
    el.querySelector(".st-veil").onclick = close;
    keyFn = (e) => { if (e.key === "Escape") close(); };
    document.addEventListener("keydown", keyFn);
  }

  // 修炼里的会话类型 → 结算种类（和后端 trainer.PRACTICE_TYPES 对应；聊天、编撰功法不结算）
  const PRACTICE = ["bank", "bank_review", "wrong", "apply", "tribulation", "alchemy"];
  const REVIEW = ["teach", "recite", "review", "speedrun", "feynman", "example", "mock_review"];
  function kindOf(type) { return PRACTICE.includes(type) ? "practice" : REVIEW.includes(type) ? "review" : null; }

  window.SETTLE = { snap, show, close, kindOf };
})();
