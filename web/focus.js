/* ◎ 专注模式：顶栏「◎」→ 选正计时或番茄钟（25 / 45 / 60 / 90 分钟）→ 藏起顶栏、提醒条、语录和导师的弹窗，只留正在做的题 / 卡 / 笔记；
   电脑浏览器里顺便全屏。顶上一颗小胶囊：剩余（或已用）时间、⏸ 暂停、✕ 退出。
   倒计时到点：轻响一声，问「歇 5 分钟 / 再来一轮 / 退出专注」；歇完再响一声。
   专注只是“不打扰”，不另外记修炼时间（修炼时间照旧由做功课 / 温简 / 写手札的心跳来记）。
   今天完成了几轮番茄记在这台设备里（胶囊上显示）。Esc 或平板返回键退出。 */
(function () {
  const root = document.documentElement;
  const btn = document.getElementById("focusBtn");
  const MODES = [[0, "正计时", "不限时，想停就停"], [25, "25 分钟", "一个番茄"], [45, "45 分钟", "一节课"], [60, "60 分钟", ""], [90, "90 分钟", "一整块"]];
  const F = { on: false, mode: 0, start: 0, paused: 0, pausedAt: 0, rest: false, tick: null, fs: false };
  const today = () => { const d = new Date(Date.now() - 4 * 3600e3); return d.getFullYear() + "-" + (d.getMonth() + 1) + "-" + d.getDate(); };
  const store = {
    get(k, d) { try { return localStorage.getItem("focus." + k) ?? d; } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem("focus." + k, v); } catch (e) { /* 存不了就算了 */ } },
  };
  const rounds = () => { const r = String(store.get("rounds", "")).split("|"); return r[0] === today() ? +r[1] || 0 : 0; };
  const addRound = () => store.set("rounds", today() + "|" + (rounds() + 1));
  const mmss = (s) => { s = Math.max(0, Math.round(s)); const h = Math.floor(s / 3600), m = Math.floor(s / 60) % 60; return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(s % 60).padStart(2, "0"); };

  let pill = null;
  function chime(times = 2) {   // 一声磬：WebAudio 现合成，不用音频文件
    try {
      const ac = new (window.AudioContext || window.webkitAudioContext)();
      for (let i = 0; i < times; i++) {
        [528, 792, 1056].forEach((f, k) => {
          const o = ac.createOscillator(), g = ac.createGain(), t = ac.currentTime + i * 0.9;
          o.type = "sine"; o.frequency.value = f;
          g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.22 / (k + 1), t + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, t + 2.2);
          o.connect(g); g.connect(ac.destination); o.start(t); o.stop(t + 2.3);
        });
      }
      setTimeout(() => ac.close(), times * 900 + 2500);
    } catch (e) { /* 没声音就算了 */ }
  }

  function elapsed() { return ((F.pausedAt || Date.now()) - F.start - F.paused) / 1000; }
  function render() {
    if (!pill) return;
    const len = (F.rest ? 5 : F.mode) * 60;
    const e = elapsed();
    pill.querySelector(".fc-time").textContent = len ? mmss(len - e) : mmss(e);
    pill.querySelector(".fc-label").textContent = F.rest ? "调息" : F.mode ? "专注" : "专注 · 正计时";
    pill.querySelector(".fc-pause").textContent = F.pausedAt ? "▶" : "⏸";
    pill.querySelector(".fc-pause").title = F.pausedAt ? "继续" : "暂停";
    const n = rounds();
    pill.querySelector(".fc-rounds").textContent = n ? "· 今日 " + n + " 轮" : "";
    pill.classList.toggle("rest", F.rest);
    pill.classList.toggle("paused", !!F.pausedAt);
    pill.style.setProperty("--p", len ? Math.min(1, e / len) : 0);
    if (len && e >= len && !F.pausedAt) done();
  }
  function done() {
    clearInterval(F.tick); F.tick = null;
    chime(F.rest ? 1 : 2);
    if (F.rest) { F.rest = false; ask("调息好了", "再来一轮？"); return; }
    addRound();
    ask(`✦ 专注圆满 · ${F.mode} 分钟 ✦`, `今天第 ${rounds()} 轮。站起来走走，喝口水。`, true);
  }
  function ask(title, sub, rest) {
    const m = document.getElementById("modal");
    m.innerHTML = `<div class="modal-box fc-ask"><h3>${title}</h3><p class="muted">${sub}</p>
      <div class="row" style="justify-content:center;gap:10px;flex-wrap:wrap">
        ${rest ? '<button class="primary" data-a="rest">🍵 歇 5 分钟</button>' : ""}
        <button class="${rest ? "" : "primary"}" data-a="again">◎ 再来一轮</button>
        <button class="ghost" data-a="exit">退出专注</button></div></div>`;
    m.classList.remove("hidden");
    m.querySelectorAll("[data-a]").forEach((b) => (b.onclick = () => {
      m.classList.add("hidden");
      if (b.dataset.a === "rest") { F.rest = true; restart(); }
      else if (b.dataset.a === "again") { F.rest = false; restart(); }
      else exit();
    }));
  }
  function restart() {
    F.start = Date.now(); F.paused = 0; F.pausedAt = 0;
    clearInterval(F.tick); F.tick = setInterval(render, 500); render();
  }

  function enter(mode) {
    F.mode = mode; F.rest = false; F.on = true;
    store.set("mode", String(mode));
    root.classList.add("focus");
    if (btn) btn.classList.add("on");
    if (!pill) {
      pill = document.createElement("div");
      pill.className = "fc-pill";
      pill.innerHTML = `<span class="fc-dot">◎</span><span class="fc-label"></span><b class="fc-time"></b><span class="fc-rounds"></span>
        <button class="fc-pause" type="button"></button><button class="fc-x" type="button" title="退出专注（Esc）">✕</button>`;
      pill.querySelector(".fc-pause").onclick = () => {
        if (F.pausedAt) { F.paused += Date.now() - F.pausedAt; F.pausedAt = 0; } else F.pausedAt = Date.now();
        render();
      };
      pill.querySelector(".fc-x").onclick = exit;
    }
    document.body.appendChild(pill);
    // 电脑浏览器里顺便全屏（App 里、主屏幕打开的本来就全屏；不让全屏也不要紧）
    const inApp = root.classList.contains("in-app");
    if (!inApp && !document.fullscreenElement && root.requestFullscreen) {
      root.requestFullscreen({ navigationUI: "hide" }).then(() => (F.fs = true)).catch(() => {});
    }
    restart();
    dispatchEvent(new Event("resize"));      // 做功课的对话框按顶栏位置排的：顶栏藏起来了重新排
  }
  function exit() {
    if (!F.on) return;
    F.on = false;
    clearInterval(F.tick); F.tick = null;
    root.classList.remove("focus");
    if (btn) btn.classList.remove("on");
    if (pill) pill.remove();
    if (F.fs && document.fullscreenElement) document.exitFullscreen().catch(() => {});
    F.fs = false;
    dispatchEvent(new Event("resize"));
  }

  function chooser() {
    const last = +store.get("mode", "25");
    const m = document.getElementById("modal");
    m.innerHTML = `<div class="modal-box fc-choose"><h3>◎ 专注模式</h3>
      <p class="small muted">藏起顶栏、提醒和导师的弹窗，只留眼前这道题 / 这枚玉简 / 这页手札。修炼时间照常记。</p>
      <div class="fc-modes">${MODES.map(([v, n, h]) => `<a data-m="${v}" class="${v === last ? "on" : ""}"><b>${n}</b><small>${h}</small></a>`).join("")}</div>
      <div class="row" style="justify-content:flex-end;gap:8px;margin-top:14px"><button class="ghost" id="fcCancel">取消</button><button class="primary" id="fcGo">开始专注</button></div></div>`;
    m.classList.remove("hidden");
    let pick = last;
    m.querySelectorAll("[data-m]").forEach((a) => {
      a.onclick = () => { pick = +a.dataset.m; m.querySelectorAll("[data-m]").forEach((b) => b.classList.toggle("on", b === a)); };
      a.ondblclick = () => { m.classList.add("hidden"); enter(+a.dataset.m); };
    });
    document.getElementById("fcCancel").onclick = () => m.classList.add("hidden");
    document.getElementById("fcGo").onclick = () => { m.classList.add("hidden"); enter(pick); };
  }

  if (btn) btn.onclick = () => (F.on ? exit() : chooser());
  // Esc：画笔、看大图、弹窗先各自收起；都没有时退出专注
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || !F.on) return;
    if (root.classList.contains("drawing") || document.querySelector(".img-zoom")) return;
    const m = document.getElementById("modal");
    if (m && !m.classList.contains("hidden")) return;
    exit();
  });
  // 浏览器自己退出全屏（按了 Esc）时，专注也一起退
  document.addEventListener("fullscreenchange", () => { if (F.fs && !document.fullscreenElement) { F.fs = false; exit(); } });

  window.FOCUS = { enter, exit, isOn: () => F.on, chooser };
})();
