/*
  外观与音乐（rpg/appearance.py 提供数据）：背景、语录、BGM。
  - 背景：BUILTIN_BG 是程序自带、用 SVG 现画的几张（跟随系统亮色 / 暗色）；也可以用 训练/外观/背景/ 里的图片。
  - 语录：训练/语录.md 一行一句；竖排淡淡地浮在页面右侧（窄屏时在底部）。
  - BGM：默认关闭，顶栏 ♪ 打开，循环播放 训练/外观/音乐/ 里的音频（程序不自带音乐）。
  对外：AMB.load()、AMB.apply(cur)、AMB.save(patch)、AMB.settingsHtml()、AMB.bindSettings()、AMB.builtinNames()。
*/
const AMB = (() => {
  let DATA = null;            // /api/appearance 的返回
  let QUOTE = "";             // 本次打开显示的语录（随机模式每次打开换一句）
  const dark = () => matchMedia("(prefers-color-scheme: dark)").matches;
  const svgUrl = (svg) => `url("data:image/svg+xml;utf8,${encodeURIComponent(svg)}")`;

  // 可复现的伪随机数：同一张背景每次画出来一样
  function rng(seed) { let s = seed; return () => ((s = (s * 9301 + 49297) % 233280) / 233280); }
  // 山脊线：从左到右的折线 + 平滑曲线，下方封闭
  function ridge(seed, base, amp, step, sharp = false) {
    const r = rng(seed); let d = `M0 900 L0 ${base}`; let x = 0, y = base;
    while (x < 1600) {
      const nx = x + step * (0.6 + r() * 0.8), ny = base - r() * amp;
      d += sharp ? ` L${(x + nx) / 2} ${ny - amp * 0.35} L${nx} ${ny}` : ` Q${(x + nx) / 2} ${ny - amp * 0.45} ${nx} ${ny}`;
      x = nx; y = ny;
    }
    return d + " L1600 900 Z";
  }
  function stars(seed, n, h, color) {
    const r = rng(seed); let s = "";
    for (let i = 0; i < n; i++) s += `<circle cx="${(r() * 1600).toFixed(0)}" cy="${(r() * h).toFixed(0)}" r="${(r() * 1.6 + 0.3).toFixed(1)}" fill="${color}" opacity="${(r() * 0.7 + 0.2).toFixed(2)}"/>`;
    return s;
  }
  const blur = (id, v) => `<filter id="${id}" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="${v}"/></filter>`;
  const wrap = (body, defs = "") => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice"><defs>${defs}</defs>${body}</svg>`;

  const BUILTIN_BG = {
    "水墨远山": (dk) => {
      const sky = dk ? ["#0b1210", "#1b2925"] : ["#f6f1e5", "#e4ddca"];
      const hills = dk ? ["#2a3c37", "#21312d", "#172420", "#0d1512"] : ["#cfccbf", "#aaa99b", "#7e8076", "#4b4f48"];
      const mist = dk ? "#9fb5ad" : "#ffffff";
      return wrap(`<rect width="1600" height="900" fill="url(#g)"/>
        <circle cx="1210" cy="190" r="${dk ? 62 : 46}" fill="${dk ? "#ece7d2" : "#c4553c"}" opacity="${dk ? 0.85 : 0.75}"/>
        ${dk ? '<circle cx="1210" cy="190" r="120" fill="#ece7d2" opacity=".08" filter="url(#b2)"/>' : ""}
        ${hills.map((c, i) => `<path d="${ridge(7 + i * 13, 430 + i * 110, 170 - i * 25, 260 - i * 30)}" fill="${c}" opacity="${0.55 + i * 0.15}"/>
          <rect y="${520 + i * 110}" width="1600" height="70" fill="${mist}" opacity="${dk ? 0.06 : 0.35}" filter="url(#b)"/>`).join("")}`,
        `<linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${sky[0]}"/><stop offset="1" stop-color="${sky[1]}"/></linearGradient>${blur("b", 18)}${blur("b2", 30)}`);
    },
    "云海仙山": (dk) => {
      const sky = dk ? ["#0d1420", "#2a3346"] : ["#dfe9ee", "#f6f2e6"];
      const peak = dk ? ["#1e2836", "#141b26"] : ["#8b98a0", "#5f6d76"];
      const cloud = dk ? "#5c6b7e" : "#ffffff";
      const r = rng(31); let clouds = "";
      for (let i = 0; i < 46; i++) clouds += `<ellipse cx="${(r() * 1700 - 50).toFixed(0)}" cy="${(560 + r() * 260).toFixed(0)}" rx="${(90 + r() * 160).toFixed(0)}" ry="${(30 + r() * 40).toFixed(0)}" fill="${cloud}" opacity="${dk ? 0.35 : 0.85}"/>`;
      return wrap(`<rect width="1600" height="900" fill="url(#g)"/>${dk ? stars(5, 90, 400, "#dfe8ff") : ""}
        <path d="${ridge(11, 520, 330, 210, true)}" fill="${peak[0]}" opacity=".8"/>
        <path d="${ridge(23, 600, 280, 260, true)}" fill="${peak[1]}"/>
        <g filter="url(#b)">${clouds}</g>`,
        `<linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${sky[0]}"/><stop offset="1" stop-color="${sky[1]}"/></linearGradient>${blur("b", 14)}`);
    },
    "星河夜空": (dk) => {
      const sky = dk ? ["#05070f", "#141a33"] : ["#2b3557", "#6d7aa3"];
      return wrap(`<rect width="1600" height="900" fill="url(#g)"/>
        <ellipse cx="800" cy="330" rx="900" ry="90" fill="#c9d6ff" opacity=".18" transform="rotate(-18 800 330)" filter="url(#b)"/>
        <ellipse cx="800" cy="330" rx="700" ry="35" fill="#fff4dc" opacity=".16" transform="rotate(-18 800 330)" filter="url(#b)"/>
        ${stars(3, 420, 760, "#ffffff")}
        <path d="${ridge(17, 780, 90, 220)}" fill="#05070c" opacity=".95"/>`,
        `<linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${sky[0]}"/><stop offset="1" stop-color="${sky[1]}"/></linearGradient>${blur("b", 26)}`);
    },
    "落日孤鸿": (dk) => {
      const sky = dk ? ["#1a0f12", "#4a2a22", "#7a4630"] : ["#f3e3c8", "#f0c99a", "#e7a77a"];
      const birds = [[520, 260, 1], [565, 245, 0.8], [600, 275, 0.7]].map(([x, y, s]) =>
        `<path d="M${x} ${y} q${12 * s} ${-10 * s} ${24 * s} 0 q${12 * s} ${-10 * s} ${24 * s} 0" stroke="${dk ? "#1a0f10" : "#3a2a24"}" stroke-width="3" fill="none"/>`).join("");
      return wrap(`<rect width="1600" height="900" fill="url(#g)"/>
        <circle cx="1050" cy="520" r="120" fill="${dk ? "#d9603d" : "#c8442c"}" opacity=".9"/>
        <circle cx="1050" cy="520" r="220" fill="#f2a060" opacity=".18" filter="url(#b)"/>${birds}
        <path d="${ridge(41, 640, 120, 300)}" fill="${dk ? "#2b1a18" : "#9a7366"}" opacity=".8"/>
        <path d="${ridge(53, 730, 90, 260)}" fill="${dk ? "#140b0b" : "#5d443d"}"/>`,
        `<linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${sky[0]}"/><stop offset=".6" stop-color="${sky[1]}"/><stop offset="1" stop-color="${sky[2]}"/></linearGradient>${blur("b", 40)}`);
    },
    "魔法星空": (dk) => {
      const sky = dk ? ["#0a0718", "#2a1749"] : ["#3b2a66", "#9a7cc9"];
      const castle = "M300 900 L300 640 L330 640 L330 600 L350 560 L370 600 L370 640 L420 640 L420 520 L445 470 L470 520 L470 640 L540 640 L540 580 L560 545 L580 580 L580 640 L620 640 L620 900 Z";
      return wrap(`<rect width="1600" height="900" fill="url(#g)"/>${stars(9, 300, 700, "#f3e9ff")}
        <circle cx="1250" cy="200" r="70" fill="#f6e7b8" opacity=".85"/><circle cx="1280" cy="185" r="62" fill="${sky[0]}" opacity=".9"/>
        <path d="${ridge(61, 760, 80, 240)}" fill="#120a24"/><path d="${castle}" fill="#0d071b"/>
        <rect x="438" y="540" width="14" height="22" fill="#f6c86a" opacity=".85"/><rect x="352" y="610" width="10" height="16" fill="#f6c86a" opacity=".7"/>`,
        `<linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${sky[0]}"/><stop offset="1" stop-color="${sky[1]}"/></linearGradient>`);
    },
    "符文法阵": (dk) => {
      const bg = dk ? "#0c0a16" : "#efe8f6", line = dk ? "#b89cff" : "#6b4bb0";
      const runes = "ᚠᚢᚦᚨᚱᚲᚷᚹᚺᚾᛁᛃᛇᛈᛉᛊᛏᛒᛖᛗᛚᛜᛞᛟ";
      let t = "";
      for (let i = 0; i < 24; i++) {
        const a = (i / 24) * Math.PI * 2;
        t += `<text x="${(1200 + Math.cos(a) * 285).toFixed(0)}" y="${(450 + Math.sin(a) * 285 + 10).toFixed(0)}" font-size="28" fill="${line}" text-anchor="middle" opacity=".55">${runes[i]}</text>`;
      }
      return wrap(`<rect width="1600" height="900" fill="${bg}"/>
        <g fill="none" stroke="${line}" opacity=".35"><circle cx="1200" cy="450" r="330" stroke-width="2"/><circle cx="1200" cy="450" r="250"/>
        <circle cx="1200" cy="450" r="160" stroke-width="2"/><polygon points="1200,190 1425,580 975,580"/><polygon points="1200,710 975,320 1425,320"/></g>${t}
        <circle cx="1200" cy="450" r="380" fill="${line}" opacity=".06" filter="url(#b)"/>`, blur("b", 40));
    },
  };
  const THEME_OF = { "水墨远山": "修仙", "云海仙山": "修仙", "星河夜空": "修仙", "落日孤鸿": "修仙", "魔法星空": "玄幻", "符文法阵": "玄幻" };

  function bgCss(key) {
    if (!key || key === "none") return "";
    if (key.startsWith("builtin:")) {
      const f = BUILTIN_BG[key.slice(8)];
      return f ? svgUrl(f(dark())) : "";
    }
    if (key.startsWith("file:")) return `url("/vault-file?p=${encodeURIComponent(key.slice(5))}")`;
    return "";
  }

  function pickQuote(cur) {
    const qs = DATA?.quotes || [];
    if (cur.quote === "off" || !qs.length && cur.quote !== "fixed") return "";
    if (cur.quote === "fixed") return cur.fixed || qs[0] || "";
    if (cur.quote === "daily") return DATA.daily || qs[0];
    if (!QUOTE || !qs.includes(QUOTE)) QUOTE = qs[Math.floor(Math.random() * qs.length)];
    return QUOTE;
  }

  function apply(cur) {
    cur = cur || DATA?.current;
    if (!cur) return;
    const layer = document.getElementById("bgLayer"), ql = document.getElementById("quoteLayer");
    const css = bgCss(cur.bg);
    layer.style.backgroundImage = css || "none";
    layer.style.setProperty("--dim", String(cur.dim ?? 0.35));
    document.body.classList.toggle("has-bg", !!css);
    ql.textContent = pickQuote(cur);
    BGM.setVolume(cur.volume);
  }

  async function load() {
    try { DATA = await fetch("/api/appearance").then((r) => r.json()); apply(); } catch (e) { /* 没有库时不影响使用 */ }
  }
  matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change", () => apply());

  async function save(patch) {
    const r = await fetch("/api/appearance", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(patch) }).then((x) => x.json());
    if (r.error) throw new Error(r.error);
    DATA.current = r.current;
    apply();
    return r.current;
  }

  // ---------------------------------------------------------------- BGM
  const BGM = (() => {
    let on = false, audio = null, list = [], idx = 0, vol = 0.35;

    function playFile() {
      if (!list.length) return;
      audio = new Audio(`/vault-file?p=${encodeURIComponent(list[idx % list.length])}`);
      audio.volume = vol;
      audio.onended = () => { idx = (idx + 1) % list.length; if (on) playFile(); };
      audio.play().catch(() => {});
    }

    function start() {
      const cur = DATA?.current || {};
      const music = DATA?.music || [];
      if (!music.length) {
        alert(`还没有背景音乐：把 mp3 / ogg / m4a / wav 放进库里的「${DATA?.folders?.music || "训练/外观/音乐/"}」，刷新网页后再点 ♪。`);
        return;
      }
      vol = cur.volume ?? 0.35;
      list = music; idx = Math.max(0, music.indexOf(cur.track)); playFile();
      on = true; btn();
    }
    function stop() {
      on = false;
      if (audio) { audio.pause(); audio = null; }
      btn();
    }
    function btn() {
      const b = document.getElementById("bgmBtn");
      if (!b) return;
      b.classList.toggle("on", on);
      b.title = on ? "背景音乐：开（点一下关闭）" : "背景音乐：关（点一下打开）";
    }
    return {
      toggle() { on ? stop() : start(); },
      restart() { if (on) { stop(); start(); } },
      setVolume(v) { vol = v ?? vol; if (audio) audio.volume = vol; },
      get on() { return on; },
    };
  })();

  // ---------------------------------------------------------------- 设置页
  function settingsHtml() {
    if (!DATA?.current) return `<div class="card"><h3>🌄 外观与音乐</h3><p class="small muted">先在下面设置好行测库路径。</p></div>`;
    const c = DATA.current, esc2 = (s) => String(s ?? "").replace(/[&<>"]/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[m]));
    const tile = (key, label) => `<button class="bg-tile ${c.bg === key ? "sel" : ""}" data-bg="${esc2(key)}" title="${esc2(label)}">
      <span class="bg-thumb" style='background-image:${bgCss(key) || "none"}'></span><span class="bg-name">${esc2(label)}</span></button>`;
    const builtins = Object.keys(BUILTIN_BG).map((n) => tile("builtin:" + n, `${n}${THEME_OF[n] === "玄幻" ? "（玄幻）" : ""}`)).join("");
    const files = DATA.backgrounds.map((p) => tile("file:" + p, p.split("/").pop())).join("");
    const qOpt = (v, t) => `<option value="${v}" ${c.quote === v ? "selected" : ""}>${t}</option>`;
    return `<div class="card"><h3>🌄 外观与音乐 <small>选择会同步到另一台电脑</small></h3>
      <label class="small muted">背景（点一下立即换）</label>
      <div class="bg-grid">${tile("none", "不用背景")}${builtins}${files}</div>
      <p class="small muted">自己的图片：放进库里的 <b>${esc2(DATA.folders.bg)}</b>（jpg / png / webp），刷新本页就会出现在上面。</p>
      <div class="row"><label style="flex:1">背景遮罩（越大越暗、字越清楚）<input type="range" id="ambDim" min="0" max="0.85" step="0.05" value="${c.dim}"></label></div>
      <hr class="soft">
      <div class="row"><label style="flex:1">语录 <select id="ambQuote">${qOpt("daily", "每日一句")}${qOpt("random", "每次打开随机")}${qOpt("fixed", "固定一句")}${qOpt("off", "不显示")}</select></label>
        <label style="flex:2">固定显示哪一句 <select id="ambFixed">${DATA.quotes.map((q) => `<option ${q === c.fixed ? "selected" : ""}>${esc2(q)}</option>`).join("")}</select></label></div>
      <p class="small muted">语录在库里的 <b>${esc2(DATA.folders.quotes)}</b>，一行一句（“- ”开头），自己加、改、删，刷新生效。现在共 ${DATA.quotes.length} 句。</p>
      <hr class="soft">
      ${DATA.music.length ? `<div class="row"><label style="flex:2">背景音乐 <select id="ambTrack">
          ${DATA.music.map((p) => `<option value="${esc2(p)}" ${c.track === p ? "selected" : ""}>${esc2(p.split("/").pop())}（从这首开始循环播放全部）</option>`).join("")}</select></label>
        <label style="flex:1">音量 <input type="range" id="ambVol" min="0" max="1" step="0.05" value="${c.volume}"></label>
        <button id="ambPlay">${BGM.on ? "■ 停止" : "▶ 播放"}</button></div>` : `<p>背景音乐：还没有音乐。</p>`}
      <p class="small muted">默认不播放；顶栏的 ♪ 随时开关。音乐放进 <b>${esc2(DATA.folders.music)}</b>（mp3 / ogg / m4a / wav），刷新本页后在上面选；删掉文件就不会再播。</p></div>`;
  }

  function bindSettings(onErr) {
    const guard = (p) => p.catch((e) => onErr ? onErr(e) : alert(e.message));
    document.querySelectorAll("[data-bg]").forEach((b) => (b.onclick = () => guard(save({ bg: b.dataset.bg }).then(() => {
      document.querySelectorAll("[data-bg]").forEach((x) => x.classList.toggle("sel", x === b));
    }))));
    const dim = document.getElementById("ambDim");
    if (!dim) return;
    dim.oninput = () => document.getElementById("bgLayer").style.setProperty("--dim", dim.value);
    dim.onchange = () => guard(save({ dim: Number(dim.value) }));
    document.getElementById("ambQuote").onchange = (e) => { QUOTE = ""; guard(save({ quote: e.target.value })); };
    document.getElementById("ambFixed").onchange = (e) => guard(save({ fixed: e.target.value, quote: "fixed" }).then(() => { document.getElementById("ambQuote").value = "fixed"; }));
    if (!document.getElementById("ambTrack")) return;   // 还没有音乐
    document.getElementById("ambTrack").onchange = (e) => guard(save({ track: e.target.value }).then(() => BGM.restart()));
    const vol = document.getElementById("ambVol");
    vol.oninput = () => BGM.setVolume(Number(vol.value));
    vol.onchange = () => guard(save({ volume: Number(vol.value) }));
    document.getElementById("ambPlay").onclick = (e) => { BGM.toggle(); e.target.textContent = BGM.on ? "■ 停止" : "▶ 播放"; };
  }

  return { load, apply, save, settingsHtml, bindSettings, bgm: BGM, builtinNames: () => Object.keys(BUILTIN_BG) };
})();
