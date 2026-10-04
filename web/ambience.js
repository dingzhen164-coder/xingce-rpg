/*
  外观与音乐（rpg/appearance.py 提供数据）：背景、语录、BGM。
  - 背景：用 训练/外观/背景/ 里自己放的图片（程序不再自带背景）。
  - 语录：训练/语录.md 一行一句；竖排淡淡地浮在页面右侧（窄屏时在底部）。
  - 语录大小：quote_size 是倍数（0.5 ~ 2），乘在 CSS 的字号上（宽屏竖排、窄屏底部横排都按它缩放）。
  - BGM：默认关闭，顶栏 ♪ 打开，顺序循环或随机播放 训练/外观/音乐/ 里的音频（程序不自带音乐）。
  对外：AMB.load()、AMB.apply(cur)、AMB.save(patch)、AMB.settingsHtml()、AMB.bindSettings()。
*/
const AMB = (() => {
  let DATA = null;            // /api/appearance 的返回
  let QUOTE = "";             // 本次打开显示的语录（随机模式每次打开换一句）
  // 明暗：每台设备各自记（localStorage），默认亮色；"auto" = 跟随系统
  const themeMode = () => { try { return localStorage.getItem("xrpg-theme") || "light"; } catch (e) { return "light"; } };
  function setTheme(mode) {
    try { localStorage.setItem("xrpg-theme", mode); } catch (e) { /* 存不了就只管这一次 */ }
    const m = mode === "auto" ? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light") : mode;
    document.documentElement.dataset.theme = m;
    document.documentElement.style.colorScheme = m;
  }
  function bgCss(key) {
    if (!key || key === "none") return "";
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
    ql.style.setProperty("--quote-scale", String(cur.quote_size ?? 1));
    BGM.setVolume(cur.volume);
  }

  async function load() {
    try { DATA = await fetch("/api/appearance").then((r) => r.json()); apply(); } catch (e) { /* 没有库时不影响使用 */ }
  }
  matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change", () => { if (themeMode() === "auto") { setTheme("auto"); apply(); } });

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
      audio.onended = () => { idx = nextIdx(); if (on) playFile(); };
      audio.play().catch(() => {});
    }

    // 随机播放：把整个列表洗一遍，放完一轮再洗（不会连着两首一样，也不会一首老不轮到）
    let bag = [];
    function nextIdx() {
      if (!(DATA?.current?.shuffle) || list.length < 2) return (idx + 1) % list.length;
      if (!bag.length) bag = list.map((_, i) => i).filter((i) => i !== idx).sort(() => Math.random() - 0.5);
      return bag.shift();
    }
    function start() {
      const cur = DATA?.current || {};
      const music = DATA?.music || [];
      if (!music.length) {
        alert(`还没有背景音乐：把 mp3 / ogg / m4a / wav 放进库里的「${DATA?.folders?.music || "训练/外观/音乐/"}」，刷新网页后再点 ♪。`);
        return;
      }
      vol = cur.volume ?? 0.35;
      list = music; bag = [];
      idx = cur.shuffle ? Math.floor(Math.random() * music.length) : Math.max(0, music.indexOf(cur.track));
      playFile();
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
    const files = DATA.backgrounds.map((p) => tile("file:" + p, p.split("/").pop())).join("");
    const qOpt = (v, t) => `<option value="${v}" ${c.quote === v ? "selected" : ""}>${t}</option>`;
    const tm = themeMode(), tOpt = (v, t) => `<option value="${v}" ${tm === v ? "selected" : ""}>${t}</option>`;
    return `<div class="card"><h3>🌄 外观与音乐 <small>选择会同步到另一台电脑（明暗除外）</small></h3>
      <div class="row" style="align-items:center;gap:10px;margin-bottom:8px"><label>明暗 <select id="ambTheme" style="width:auto">
        ${tOpt("light", "浅色 · 宣纸（默认）")}${tOpt("dark", "深色 · 墨夜")}${tOpt("auto", "跟随系统")}</select></label>
        <span class="small muted">只影响这台设备（电脑、平板各选各的）</span></div>
      <label class="small muted">背景（点一下立即换）</label>
      <div class="bg-grid">${tile("none", "不用背景")}${files}</div>
      <p class="small muted">背景用自己的图片：放进库里的 <b>${esc2(DATA.folders.bg)}</b>（jpg / png / webp），刷新本页就会出现在上面。</p>
      <div class="row"><label style="flex:1">背景遮罩（越大越暗、字越清楚）<input type="range" id="ambDim" min="0" max="0.85" step="0.05" value="${c.dim}"></label></div>
      <hr class="soft">
      <div class="row"><label style="flex:1">语录 <select id="ambQuote">${qOpt("daily", "每日一句")}${qOpt("random", "每次打开随机")}${qOpt("fixed", "固定一句")}${qOpt("off", "不显示")}</select></label>
        <label style="flex:2">固定显示哪一句 <select id="ambFixed">${DATA.quotes.map((q) => `<option ${q === c.fixed ? "selected" : ""}>${esc2(q)}</option>`).join("")}</select></label></div>
      <div class="row" style="align-items:center;gap:12px;margin-top:6px"><label style="flex:1">语录大小 <b id="ambQSizeV">${Math.round((c.quote_size ?? 1) * 100)}%</b>
        <input type="range" id="ambQSize" min="0.5" max="2" step="0.1" value="${c.quote_size ?? 1}"></label></div>
      <p class="small muted">语录在库里的 <b>${esc2(DATA.folders.quotes)}</b>，一行一句（“- ”开头），自己加、改、删，刷新生效。现在共 ${DATA.quotes.length} 句。</p>
      <hr class="soft">
      ${DATA.music.length ? `<div class="row"><label style="flex:2">背景音乐 <select id="ambTrack">
          ${DATA.music.map((p) => `<option value="${esc2(p)}" ${c.track === p ? "selected" : ""}>${esc2(p.split("/").pop())}（顺序循环时从这首开始）</option>`).join("")}</select></label>
        <label style="flex:1">播放顺序 <select id="ambShuffle"><option value="0" ${c.shuffle ? "" : "selected"}>顺序循环</option><option value="1" ${c.shuffle ? "selected" : ""}>随机播放</option></select></label>
        <label style="flex:1">音量 <input type="range" id="ambVol" min="0" max="1" step="0.05" value="${c.volume}"></label>
        <button id="ambPlay">${BGM.on ? "■ 停止" : "▶ 播放"}</button></div>` : `<p>背景音乐：还没有音乐。</p>`}
      <p class="small muted">默认不播放；顶栏的 ♪ 随时开关。音乐放进 <b>${esc2(DATA.folders.music)}</b>（mp3 / ogg / m4a / wav），刷新本页后在上面选；删掉文件就不会再播。</p></div>`;
  }

  function bindSettings(onErr) {
    const guard = (p) => p.catch((e) => onErr ? onErr(e) : alert(e.message));
    document.querySelectorAll("[data-bg]").forEach((b) => (b.onclick = () => guard(save({ bg: b.dataset.bg }).then(() => {
      document.querySelectorAll("[data-bg]").forEach((x) => x.classList.toggle("sel", x === b));
    }))));
    const th = document.getElementById("ambTheme");
    if (th) th.onchange = () => { setTheme(th.value); apply(); if (typeof render === "function") render(); };
    const dim = document.getElementById("ambDim");
    if (!dim) return;
    dim.oninput = () => document.getElementById("bgLayer").style.setProperty("--dim", dim.value);
    dim.onchange = () => guard(save({ dim: Number(dim.value) }));
    document.getElementById("ambQuote").onchange = (e) => { QUOTE = ""; guard(save({ quote: e.target.value })); };
    const qs = document.getElementById("ambQSize");
    qs.oninput = () => { document.getElementById("quoteLayer").style.setProperty("--quote-scale", qs.value);
      document.getElementById("ambQSizeV").textContent = Math.round(qs.value * 100) + "%"; };
    qs.onchange = () => guard(save({ quote_size: Number(qs.value) }));
    document.getElementById("ambFixed").onchange = (e) => guard(save({ fixed: e.target.value, quote: "fixed" }).then(() => { document.getElementById("ambQuote").value = "fixed"; }));
    if (!document.getElementById("ambTrack")) return;   // 还没有音乐
    document.getElementById("ambTrack").onchange = (e) => guard(save({ track: e.target.value }).then(() => BGM.restart()));
    document.getElementById("ambShuffle").onchange = (e) => guard(save({ shuffle: e.target.value === "1" }).then(() => BGM.restart()));
    const vol = document.getElementById("ambVol");
    vol.oninput = () => BGM.setVolume(Number(vol.value));
    vol.onchange = () => guard(save({ volume: Number(vol.value) }));
    document.getElementById("ambPlay").onclick = (e) => { BGM.toggle(); e.target.textContent = BGM.on ? "■ 停止" : "▶ 播放"; };
  }

  return { load, apply, save, settingsHtml, bindSettings, bgm: BGM };
})();
