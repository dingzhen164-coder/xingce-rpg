/*
  行测修仙传 / 行测魔法学院 前端（原生 JS，无需编译）。改完刷新浏览器即可。

  界面上的说法全部来自后端 /api/dashboard 的 theme.terms（见 rpg/themes.py），用 W("键") 取；
  所以切换风格（设置页）只需要后端改存档里的 theme，前端自动换词、换配色（body 的 class）。

  结构：
    api()            调后端接口（接口说明见 rpg/api.py 顶部）
    views.*          各页面：home 洞府 / train 修炼 / skeleton 藏经阁 / wrong 心魔录 / pill 丹房 / log 修仙录 / settings 设置
    handleEvents()   处理后端事件：+修为提示、境界突破弹窗、导师台词
    heartbeat        每 60 秒上报一次修炼时间（页面可见且 2 分钟内有操作才算）
*/
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const md = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\n/g, "<br>");
const pct = (x) => Math.round((x || 0) * 100);

let DASH = null;
let VIEW = "home";
const T = { session: null, title: "", msgs: [], input: { mode: "none" }, busy: false, finished: false, battle: null };
const W = (k) => DASH?.theme?.terms?.[k] ?? k;   // 当前风格的说法
const NAV = (k) => W("nav." + k).replace(/^\S+\s/, "");  // 去掉图标的页面名

async function api(path, body) {
  const opt = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const r = await fetch(path, opt);
  const data = await r.json().catch(() => ({ error: "服务器没有返回数据（程序是不是关掉了？）" }));
  if (!r.ok || data.error) throw new Error(data.error || r.statusText);
  return data;
}

// ------------------------------------------------------------ 提示与事件
function toast(html, cls = "", ms = 4200) {
  const el = document.createElement("div");
  el.className = "toast " + cls;
  el.innerHTML = html;
  $("#toasts").appendChild(el);
  setTimeout(() => el.remove(), ms);
}
function tutorFace() {
  const u = DASH?.persona?.tutor_avatar;
  return u ? `<div class="face"><img src="${esc(u)}" alt=""></div>` : `<div class="face">${esc(DASH?.theme?.face || "🌸")}</div>`;
}
function npcToast(msg) {
  if (!msg) return;
  toast(`<div class="npc">${tutorFace()}<div><div class="who">${esc(DASH?.persona?.tutor || "导师")}</div>${md(msg)}</div></div>`, "", 9000);
}
function showError(e) { toast("⚠ " + esc(e.message || e), "err", 6000); }

function handleEvents(events, { inChat = false } = {}) {
  for (const e of events || []) {
    if (e.kind === "xp") toast(`+${e.v} ${esc(W("xp"))} <span class="small muted">${esc(e.msg || "")}</span>`, "xp");
    else if (e.kind === "realm") realmUp(e);
    else if (e.kind === "npc" && e.msg) inChat ? T.msgs.push({ who: "npc", text: e.msg }) : npcToast(e.msg);
    else if (e.kind === "info") toast("✦ " + esc(e.msg), "info", 6000);
  }
}
function realmUp(e) {
  const m = $("#modal");
  m.innerHTML = `<div class="levelup ${e.major ? "major" : ""}"><div class="muted rune">${e.major ? `✦ ${esc(W("breakthrough"))} ✦` : `✦ ${esc(W("realm"))}精进 ✦`}</div>
    <div class="lv">${esc(e.name)}</div>
    <div style="font-size:18px;margin-top:8px">${esc(W("score"))} <b style="color:var(--gold)">${e.score}</b> 分</div>
    <br><button class="primary">继续修行</button></div>`;
  m.classList.remove("hidden");
  $("button", m).onclick = () => m.classList.add("hidden");
}

// ------------------------------------------------------------ 导航 / 风格
function go(view) {
  VIEW = view;
  document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.view === view));
  render();
}
document.querySelectorAll("#nav a").forEach((a) => (a.onclick = () => go(a.dataset.view)));
$("#bgmBtn").onclick = () => AMB.bgm.toggle();   // 背景音乐默认关闭，点了才响
AMB.load();                                        // 背景、语录

function applyTheme() {
  if (!DASH?.theme) return;
  document.body.classList.toggle("xiuxian", DASH.theme.name === "修仙");
  document.body.classList.toggle("xuanhuan", DASH.theme.name === "玄幻");
  $(".brand").textContent = W("brand");
  document.title = W("brand").replace(/^\S+\s/, "");
  document.querySelectorAll("#nav a").forEach((a) => (a.textContent = W("nav." + a.dataset.view)));
}

async function refresh() {
  try {
    DASH = await api("/api/dashboard");
    applyTheme();
    handleEvents(DASH.events);
    updatePill();
    banner();
    if (DASH.first_today && DASH.greeting && VIEW !== "home") npcToast(DASH.greeting);
  } catch (e) { showError(e); }
}
function updatePill() {
  if (!DASH) return;
  const m = DASH.minutes;
  $("#todayPill").textContent = `🕯 今日功行 ${m.today} / ${m.goal} 分钟（${W("study")} ${m.study ?? m.today} · ${W("lecture")} ${m.lecture ?? 0}）` + (m.today >= m.goal ? " ✦" : "");
  updateStudyDot();
}
function banner() {
  const w = [];
  if (!DASH.vault) w.push("还没找到行测库，请到“设置”里填写库的路径。");
  if (!DASH.ai) w.push(`还没填写 AI 的 API key：${W("recite")}和${W("kill")}可以自评，导师聊天 / ${W("feynman")} / ${W("apply")} / 生成${W("skeleton")}需要 AI。去“设置”填写。`);
  if (DASH.rest > 0) w.push(`${W("qi")}预警：还需调息 ${DASH.rest} 分钟。站起来走走、喝口水。`);
  (DASH.notices || []).forEach((n) => w.push(esc(n)));
  if (DASH.upgraded?.length) w.push("程序升级了配置文件：" + DASH.upgraded.map((n) => `训练/${esc(n)}`).join("、") + "。原来的版本备份成了同名的“.旧版.md”。");
  if (DASH.other_device) w.push(`另一台电脑（${esc(DASH.other_device)}）10 分钟内在用本程序。两台同时用，坚果云同步可能冲突，请先关掉那台。`);
  if (DASH.conflicts?.length) w.push("存档文件夹里有坚果云冲突副本：" + DASH.conflicts.map(esc).join("、") + "。保留较新的一份，删掉另一份。");
  $("#banner").innerHTML = w.map((x) => `<div class="warn">${x}</div>`).join("");
}

async function render() {
  const v = $("#view");
  try {
    if (VIEW === "home") { await refresh(); v.innerHTML = views.home(); bindHome(); }
    else if (VIEW === "train") { if (!DASH) await refresh(); v.innerHTML = views.train(); bindTrain(); }
    else if (VIEW === "skeleton") { if (!DASH) await refresh(); v.innerHTML = await views.skeleton(); bindSkeleton(); }
    else if (VIEW === "bank") { await refresh(); v.innerHTML = await views.bank(); bindBank(); }
    else if (VIEW === "wrong") { await refresh(); v.innerHTML = await views.wrong(); }
    else if (VIEW === "pill") { await refresh(); v.innerHTML = views.pill(); bindPill(); }
    else if (VIEW === "log") { await refresh(); v.innerHTML = views.log(); bindLog(); }
    else if (VIEW === "settings") { await refresh(); await AMB.load(); v.innerHTML = await views.settings(); bindSettings(); }
  } catch (e) { showError(e); }
}

// ------------------------------------------------------------ 小组件
const STATE_TAG = { current: `<span class="tag cur">◆当前</span>`, mastered: `<span class="tag ok">★圆满</span>`,
  cleared: `<span class="tag ok">已打通</span>`, locked: `<span class="tag lock">🔒未解锁</span>`, later: "" };

function rootBadge(r) {
  if (!r) return "";
  if (!r.on) return `<span class="tag lock">${esc(r.name)}未觉醒</span>`;
  return `<span class="tag root t${r.tier}">${esc(r.name)} · ${esc(r.grade_name)}</span>`;
}
function bar(frac, cls = "") { return `<div class="bar ${cls}"><div style="width:${Math.max(0, Math.min(100, pct(frac)))}%"></div></div>`; }
function taskRow(t) {
  const ck = t.done ? (t.ok === false ? "❌" : "✅") : "⬜";
  return `<div class="task ${t.done ? "done" : ""} ${t.type === "tribulation" ? "trib" : ""}" data-task="${esc(t.id)}">
    <span class="ck">${ck}</span><span class="ttl">${esc(t.title)}</span><span class="spacer"></span><span class="min">${t.minutes} 分钟</span></div>`;
}
function recentList(ev) {
  if (!ev?.length) return '<div class="muted small">还没有记录</div>';
  return ev.map((e) => `<div class="row small"><span class="faint">${esc(e.t?.slice(5, 16).replace("T", " ") || e.d)}</span>
    <span>${esc(e.note)}</span><span class="spacer"></span>${e.xp ? `<b style="color:var(--gold)">+${e.xp}</b>` : ""}</div>`).join("");
}
function msgHtml(m) {
  const blocks = (m.blocks || []).map((b) => b.t === "img" ? `<img src="/vault-file?p=${encodeURIComponent(b.v)}">` : `<div>${md(b.v)}</div>`).join("");
  if (m.fold) return `<details class="fold"><summary>${esc(m.fold)}</summary><div>${md(m.text)}</div></details>`;
  if (m.who === "npc") return `<div class="npc">${tutorFace()}<div class="say"><div class="who">${esc(DASH?.persona?.tutor || "导师")}</div>${md(m.text)}</div></div>`;
  if (m.who === "me") return `<div class="msg me">${esc(m.text)}</div>`;
  return `<div class="msg sys">${md(m.text)}${blocks}</div>`;
}
function boardOptions(list) { return list.map((b) => `<option>${esc(b)}</option>`).join(""); }

// ------------------------------------------------------------ 页面
const views = {
  home() {
    const d = DASH; if (!d) return "";
    const R = d.realm, p = d.persona, I = d.ideal, F = d.forecast;
    const avatar = p.avatar ? `<img src="${esc(p.avatar)}" alt="头像">` : `<div class="def">${esc((p.id || "修").slice(0, 1))}</div>`;
    const diff = I.diff_days;
    const ideal = diff > 0.5 ? `<div class="v bad">落后 ${diff} 天</div><div class="d">${I.catch ? `每天多修 ${I.catch.per_day} 分钟约 ${I.catch.days} 天追平，或去${esc(W("pill_room"))}加练` : ""}</div>`
      : diff < -0.5 ? `<div class="v good">领先 ${-diff} 天</div><div class="d">保持住</div>` : `<div class="v">恰在线上</div><div class="d">按计划修行</div>`;
    const barLabel = R.bottleneck
      ? `<span style="color:var(--gold)">⚡ ${esc(W("bottleneck"))}：积压${esc(W("xp"))} ${R.overflow}，${esc(W("tribulation"))}成功后一次涌入</span>`
      : `${esc(W("xp"))} ${R.into} / ${R.need}${R.next ? ` → ${esc(R.next)}` : ""}`;
    const tasks = d.plan.tasks;
    const doneN = tasks.filter((t) => t.done).length;
    const totalMin = tasks.reduce((a, t) => a + t.minutes, 0);
    let lastBatch = 0;
    const tree = d.tree.map((s) => {
      let h = "";
      if (s.batch !== lastBatch) { lastBatch = s.batch; h += `<div class="batch-h">第 ${s.batch} ${esc(W("batch"))}</div>`; }
      const acc = s.acc ? `实战 ${pct(s.acc.rate)}% ${s.acc.trend}` : "实战 —";
      const sk = s.state === "locked" ? "" : s.skeleton === "none" ? `<span class="tag draft">无${esc(W("skeleton"))}</span>` : s.skeleton === "draft" ? `<span class="tag draft">${esc(W("skeleton"))}草稿</span>` : "";
      const color = s.state === "mastered" ? "green" : s.state === "current" ? "yellow" : "";
      return h + `<div class="skill ${s.state === "locked" ? "locked" : ""}"><div class="top"><span>${esc(s.board)} ${STATE_TAG[s.state] || ""}${sk}</span>
        <span class="muted small">${acc}</span></div>${bar(s.progress, "thin " + color)}
        <div class="faint small">${s.items ? `${s.mastered}/${s.items} ${esc(W("item"))}圆满 · ${pct(s.progress)}%` : ""} ${s.root?.on ? rootBadge(s.root) : ""}</div></div>`;
    }).join("");
    const trib = d.trib ? `<div class="card trib-card"><h3>⚡ ${esc(W("tribulation"))} · 冲击${esc(d.trib.realm)} <small>${d.trib.thunders} 道天雷 · ${esc(d.trib.pill)} ×${d.trib.pills}</small></h3>
        <div class="conds">${d.trib.conds.map((c) => `<div class="cond ${c.ok ? "ok" : "no"}"><b>${c.ok ? "✓" : "✗"} ${esc(c.name)}</b><span class="small">${esc(c.text)}${c.need && !c.ok ? `（${esc(c.need)}）` : ""}</span></div>`).join("")}</div>
        ${d.trib.ready ? `<div class="row" style="margin-top:10px"><button class="primary big" id="tribBtn">⚡ 开始${esc(W("tribulation"))}</button><span class="small muted">开始后不能跳过；失败会道基受损，冷却几天并需${esc(W("heal"))}</span></div>` : ""}</div>` : "";
    const retreat = d.retreat ? `<div class="card retreat row"><b>🧘 ${esc(W("retreat"))}中：${esc(d.retreat.board)}</b> <span id="retreatLeft" class="muted"></span>
        <span class="spacer"></span><button class="small" id="retreatEnd">${esc(W("retreat_end"))}</button></div>` : "";
    const roots = d.roots.map((r) => `<div class="root ${r.on ? "on t" + r.tier : ""}"><div class="row"><b>${esc(r.name)}</b><span class="spacer"></span><span class="small">${esc(r.grade_name)}</span></div>
        <div class="small muted">${r.acc != null ? `正确率 ${pct(r.acc)}%` : "暂无数据"}${r.on && r.bonus ? ` · ${esc(W("xp"))} +${pct(r.bonus)}%` : ""}${!r.on ? ` · 觉醒：${r.route === "功法" ? `${esc(W("skeleton"))}全部圆满` : "两季正确率达线"}` : ""}</div></div>`).join("");
    const demon = d.demon.slice(0, 6).map((r, i) => `<div class="row small"><span class="rank">${i + 1}</span><span>${esc(r.board)}</span><span class="spacer"></span><b style="color:${i < 2 ? "var(--red)" : "var(--muted)"}">${pct(r.acc)}%</b></div>`).join("") || '<div class="muted small">还没有模考数据</div>';
    const weekly = d.weekly.map((q) => `<div class="small"><div class="row"><span>${q.done ? "✅" : "⬜"} ${esc(q.name)}</span><span class="spacer"></span><span class="muted">${q.progress}/${q.target}</span></div>${bar(q.progress / q.target, "thin " + (q.done ? "green" : ""))}</div>`).join("");
    const bag = d.bag.length ? d.bag.map((b) => `<div class="small row"><b>${esc(b.name)}</b><span class="muted">×${b.count}</span><span class="spacer"></span><span class="faint">${esc(b.desc)}</span></div>`).join("") : `<div class="muted small">空空如也。${esc(W("boss"))}达到${esc(W("tribulation"))}线得突破信物，${esc(W("weekly"))}全勤得护身之物。</div>`;
    const boss = d.boss.length ? d.boss.slice().reverse().map((b) => `${esc(b.name)} <b>${b.score}</b> <span class="faint small">${b.d}</span>`).join(" · ") : `<span class="muted">还没有战绩。模考出分后到“${esc(NAV("log"))}”页记录。</span>`;
    const ascend = d.ascend.length ? `<div class="ascend">🌈 ${esc(W("ascend"))}：${d.ascend.map((b) => `${esc(b.name)} ${b.score} 分`).join("；")}</div>` : "";
    return `
    <div class="card npc greet">${tutorFace()}<div><div class="who">${esc(p.tutor)}</div><div id="greet">${md(d.greeting)}${d.greet_pending ? '<div class="thinking small">正在打量你</div>' : ""}</div></div></div>
    ${retreat}
    <div class="card hero">
      <div class="avatar">${avatar}</div>
      <div class="hero-main">
        <div class="hero-name">${esc(p.id)}<small>「${esc(p.call)}」</small></div>
        <div class="realm-name">${esc(R.name)}${R.bottleneck ? ` <span class="tag cur">${esc(W("bottleneck"))}</span>` : ""}</div>
        <div class="hero-title">第 ${d.lap} 个${esc(W("lap"))} · ${d.batch.index ? `第 ${d.batch.index}/${d.batch.count} ${esc(W("batch"))}：${d.batch.boards.map(esc).join("、")}` : "本轮已圆满"}</div>
        <div class="row small muted" style="margin-top:8px"><span>${barLabel}</span><span class="spacer"></span><span>累计 ${d.xp}</span></div>
        ${bar(R.frac)}
      </div>
      <div class="hero-score"><div class="small muted">${esc(W("score"))}</div><div class="big">${R.score}<span>分</span></div>
        <div class="small muted">目标 ${R.target} 分</div></div>
    </div>
    <div class="grid g5" style="margin-top:14px">
      <div class="stat"><div class="k">🔥 ${esc(W("streak"))}</div><div class="v">${d.streak.days} 天</div><div class="d">${esc(W("xp"))}加成 +${pct(d.streak.bonus)}%</div></div>
      <div class="stat"><div class="k">🪷 ${esc(W("dao"))}</div><div class="v ${d.dao.value < 60 ? "bad" : ""}">${d.dao.value} · ${esc(d.dao.label)}</div><div class="d">近 14 天修炼的稳定度</div></div>
      <div class="stat"><div class="k">🧵 ${esc(W("ideal"))}</div>${ideal}</div>
      <div class="stat"><div class="k">🗺 本轮进度</div><div class="v">${pct(F.progress)}%</div><div class="d">${F.days_left ? `按近 7 天速度还需 ${F.days_left} 天` : "修几天后给出预测"}</div></div>
      <div class="stat"><div class="k">🎯 预计 ${I.target_score} 分</div><div class="v">${I.eta || "—"}</div><div class="d">目标日 ${I.target}</div></div>
    </div>
    ${trib}
    ${lectureCard(d)}
    <div class="grid g2" style="margin-top:14px">
      <div class="card"><h3>📜 ${esc(W("tasks"))} <small>${doneN}/${tasks.length} · 约 ${totalMin} 分钟</small></h3>
        <div id="tasks">${tasks.map(taskRow).join("") || `<div class="muted">今天没有功课。去“${esc(NAV("skeleton"))}”编撰${esc(W("skeleton"))}。</div>`}</div>
        <div class="row" style="margin-top:8px"><button class="ghost small" id="regen">重新生成${esc(W("tasks"))}</button>
        <button class="small" id="chatBtn">💬 ${esc(W("chat_btn"))}</button>
        ${diff >= 1 ? `<button class="small" id="goPill">⚗ 去${esc(W("pill_room"))}加练</button>` : ""}</div></div>
      <div class="card"><h3>⚔ 修炼进度 <small>${esc(W("skeleton"))}圆满度 · 实战正确率 · ${esc(W("root"))}</small></h3><div class="tree">${tree}</div></div>
    </div>
    <div class="grid g3" style="margin-top:14px">
      <div class="card"><h3>🌱 ${esc(W("root"))}</h3><div class="roots">${roots}</div></div>
      <div class="card"><h3>👹 ${esc(W("demon_rank"))} <small>正确率越低，${esc(W("wrong"))}越凶</small></h3>${demon}
        <h3 style="margin-top:14px">🏯 ${esc(W("weekly"))}</h3>${weekly}</div>
      <div class="card"><h3>🎒 ${esc(W("bag"))}</h3>${bag}
        <h3 style="margin-top:14px">⚔ ${esc(W("boss"))}</h3><div>${boss}</div>${ascend}
        <h3 style="margin-top:14px">📖 最近</h3>${recentList(d.recent.slice(0, 5))}</div>
    </div>`;
  },

  train() {
    const tasks = DASH?.plan?.tasks || [];
    if (!T.session && !T.msgs.length) {
      return `<div class="card"><h3>${esc(W("nav.train"))}</h3><p class="muted">从${esc(W("tasks"))}里选一项开始：</p>${tasks.map(taskRow).join("") || '<div class="muted">今天没有功课</div>'}</div>`;
    }
    const inp = T.input;
    let composer = "";
    if (T.busy) composer = `<div class="thinking">${esc(DASH?.persona?.tutor || "导师")}正在判定</div>`;
    else if (inp.mode === "text") composer = `<textarea id="answer" placeholder="${esc(inp.placeholder || "")}"></textarea>
        <div class="row" style="margin-top:8px"><span class="small muted">Ctrl / ⌘ + Enter 提交</span><span class="spacer"></span>
        <button class="ghost" data-act="${["bank", "bank_review"].includes(T_TYPE) ? "bank_pause" : "skip"}">${["bank", "bank_review"].includes(T_TYPE) ? "保存并暂停" : "跳过"}</button><button class="primary" id="send">提交</button></div>`;
    else if (inp.mode === "buttons") composer = `<div class="row">${inp.buttons.map((b) => `<button class="${b.id === "skip" ? "ghost" : "primary"}" data-act="${esc(b.id)}">${esc(b.label)}</button>`).join("")}</div>`;
    else if (T.finished) composer = `<div class="row"><button class="primary" id="nextTask">下一项功课</button><button class="ghost" id="backHome">回${esc(NAV("home"))}</button></div>`;
    return `<div class="train">
      <div class="card"><h3>📜 ${esc(W("tasks"))}</h3>${tasks.map(taskRow).join("")}</div>
      <div class="card chat"><h3>${esc(T.title)}</h3>${battlePanel()}<div class="msgs" id="msgs">${T.msgs.map(msgHtml).join("")}</div>
        <div class="composer">${composer}</div></div></div>`;
  },

  async bank() {
    const d = await api('/api/bank');
    const rate = (ok, n) => n ? `${(ok / n * 100).toFixed(1)}%（${ok}/${n}）` : '—';
    const done = d.boards.reduce((n,b) => n + b.first_total, 0);
    const wrong = d.boards.reduce((n,b) => n + b.wrong, 0);
    return `<div class="card bank-banner"><div class="rune">⚔ ${esc(NAV('bank'))} ⚔</div><h2>以真题验${esc(W('skeleton'))}，在实战中精进</h2>
      <div class="npc">${tutorFace()}<div><b>${esc(DASH.persona.tutor)}</b><p>${esc(W('bank_intro'))}</p></div></div>
      ${towerHtml(d.tower)}
      <details class="card import-card" id="importCard"><summary><b>📥 导入真题</b> <span class="small muted">模考复盘、OCR 出来的 txt 一键入库，不用 AI 逐题核对</span></summary><div id="importBody">载入中…</div></details>
      <div class="bank-counters"><span>已完成 ${done} 道新题</span><span>${esc(W('bank_wrong'))} ${wrong}</span><span>通关可获${esc(W('xp'))}</span></div>
      <p class="small muted">在「训练/题库/板块名真题.md」添加${esc(W('bank_library'))}，或用上面的「📥 导入真题」批量入库（图放在「训练/题库/图片/板块名/」）。按文档顺序出题，题库不足一组时做剩余题；新题与错题正确率独立统计。</p>
      <label>每轮试炼 <select id="bankCount"><option value="10" ${d.count === 10 ? 'selected' : ''}>10 关</option><option value="15" ${d.count === 15 ? 'selected' : ''}>15 关</option></select></label>
      <p class="small muted">首次作答获得${esc(W('xp'))}，新题组结算另有基础 ${d.bonus} ${esc(W('xp'))}（计入现有加成，旧组只按新记录比例发奖）。${esc(W('bank_review'))}计时，连续答对 ${d.streak_need} 次消除残影，不重复发奖。题量调整从下一轮生效。</p></div>
      ${setsHtml(d.sets)}
      <div class="grid g2">${d.boards.map(b => `<div class="card bank-board"><div class="row"><h3>⚔ ${esc(b.board)} · ${esc(W('bank'))}</h3><span class="spacer"></span>${rootBadge(DASH.roots?.find(r => r.board === b.board))}</div>
      <p>${esc(W('bank_library'))} ${b.total} 道 · ${esc(W('bank_remaining'))} ${b.remaining} · ${esc(W('bank_wrong'))} ${b.wrong}</p>
      ${b.pending ? `<p class="small pending-note">另有 <b>${b.pending}</b> 道还没有答案，补上才会出题：上面「📥 导入真题 → ④ 补答案」填答案表</p>` : ''}
      ${bar(b.total ? (b.total - b.remaining) / b.total : 0, 'thin yellow')}
      <p class="small">首次正确率 ${rate(b.first_correct, b.first_total)} · 复练正确率 ${rate(b.review_correct, b.review_total)} · 首次方法通过率 ${rate(b.method_correct, b.method_total)}（仅统计AI已审核）</p>
      ${b.errors.length ? `<div class="warn">${b.errors.map(esc).join('<br>')}</div>` : ''}
      <div class="row"><button class="primary" data-bank="${esc(b.board)}" data-mode="new" ${!b.active && (!b.remaining || b.errors.length) ? 'disabled' : ''}>${esc(W(b.active ? 'bank_resume' : 'bank_start'))}</button>
      <button data-bank="${esc(b.board)}" data-mode="review" ${b.active || !b.wrong ? 'disabled' : ''}>${esc(W('bank_review'))}</button></div>
      ${b.wrong_items.length ? `<details><summary>${esc(W('bank_wrong'))}（错题）</summary>${b.wrong_items.map(q => `<p>编号 ${esc(q.id)} · ${esc(q.topic)} · 上次选 ${esc(q.last.answer)} · 共 ${q.tries} 次 · ${esc(q.last.date)}</p>`).join('')}</details>` : ''}</div>`).join('')}</div>
      <div class="card"><h3>📜 ${esc(W('bank_history'))}</h3>${d.groups.map(x => `<div class="row"><span>${esc(x.date)} · ${esc(x.label || x.board)} · ${esc(W(x.mode === 'new' ? 'bank' : 'bank_review'))}</span><span class="spacer"></span><span class="tag ok">${esc(W('bank_rank.' + x.rank))}</span><span>${rate(x.correct, x.total)}</span></div>`).join('') || '尚未留下试炼战绩，选一门功法开始吧。'}</div>`;
  },

  async skeleton() {
    const sk = await api("/api/skeletons");
    const sub = (it) => it.level === 0 && it.l1 ? ` · ${W("recite")} ${it.l1}/${sk.need_l1}` : it.level === 2 && it.l3 ? ` · ${W("apply")} ${it.l3}/${sk.need_l3}` : "";
    return sk.boards.map((b) => {
      const st = b.final ? '<span class="tag ok">已定稿</span>' : b.status === "草稿" ? '<span class="tag draft">草稿</span>' : '<span class="tag lock">无</span>';
      const skill = b.hasSkill ? `<span class="small muted">skill：${esc(b.skill)}</span>` : `<span class="small" style="color:var(--red)">skill 未接入：${esc(b.skill || "（未配置）")}</span>`;
      const rows = b.items.map((it) => {
        const cls = it.rusty ? "rust" : "l" + it.level;
        return `<tr><td>${esc(it.name)}</td><td class="small muted">${it.terms} ${esc(W("term"))} · ${it.thoughts} 思路 · 举例${it.exampleOk ? "已过" : "待过"}</td>
          <td><span class="lvchip ${cls}">${it.rusty && it.level === 0 ? esc(W("rust")) : esc(it.levelName)}${sub(it)}${it.lapCheck ? ` · 待${esc(W("speedrun"))}` : ""}</span></td>
          <td class="small muted">${it.next ? esc(W("review")) + " " + it.next : ""}</td>
          <td>${b.final ? `${["recite", "feynman", "example", "apply"].map(type => `<a data-free="${esc(it.id)}" data-train="${type}" data-board="${esc(b.board)}" data-name="${esc(it.name)}">${esc(W(type))}</a>`).join(" · ")}` : ""}</td></tr>`;
      }).join("");
      return `<div class="card"><div class="row"><h3 style="margin:0">📜 ${esc(b.board)} ${st}</h3>${skill}<span class="spacer"></span>
        ${b.final ? "" : `<button class="small" data-skel="${esc(b.board)}">${b.status === "草稿" ? "审阅 / 定稿" : "编撰" + esc(W("skeleton"))}</button>`}</div>
        <div class="small faint">文件：${esc(b.file)}</div>
        ${rows ? `<table style="margin-top:8px"><tr><th>${esc(W("item"))}（大项）</th><th>内容</th><th>掌握</th><th></th><th></th></tr>${rows}</table>` : ""}</div>`;
    }).join("");
  },

  async wrong() {
    const w = await api("/api/wrong");
    const rows = w.boards.filter((b) => b.total).map((b) => `<tr><td>${esc(b.board)}</td><td>${b.total}</td><td>${b.new}</td><td style="color:var(--red)">${b.redo}</td><td style="color:var(--green)">${b.done}</td></tr>`).join("");
    const redo = w.redo.map((r) => { const [n, s, q] = r.key.split("|"); return `<tr><td>第${n}季 ${esc(s)} 第${q}题</td><td>${r.due || ""}</td><td>${r.streak || 0}</td><td>${r.tries}</td></tr>`; }).join("");
    const demon = (DASH?.demon || []).map((r, i) => `<tr><td>${i + 1}</td><td>${esc(r.board)}</td><td>${esc(r.name)}</td><td><b style="color:${i < 3 ? "var(--red)" : "inherit"}">${pct(r.acc)}%</b></td><td>${esc(r.grade_name)}</td></tr>`).join("");
    return `<div class="card"><h3>👹 ${esc(W("demon_rank"))} <small>按最近几季模考正确率从低到高：排在前面的就是你最大的${esc(W("wrong"))}</small></h3>
      <table><tr><th>#</th><th>板块</th><th>${esc(W("root"))}</th><th>正确率</th><th>品阶</th></tr>${demon || '<tr><td colspan="5" class="muted">还没有模考数据</td></tr>'}</table></div>
      <div class="card"><h3>📕 ${esc(W("wrong"))}一览 <small>来自模考板块复盘里做错 ❌ / 没做 ⚪ 的题</small></h3>
      <table><tr><th>板块</th><th>${esc(W("wrong"))}</th><th>未交手</th><th>${esc(W("redo"))}</th><th>已斩</th></tr>${rows || '<tr><td colspan="5" class="muted">还没有数据</td></tr>'}</table></div>
      <div class="card"><h3>💀 ${esc(W("redo"))} <small>没斩掉的，到期出现在${esc(W("tasks"))}里</small></h3>
      <table><tr><th>题目</th><th>再战日</th><th>连续斩</th><th>交手次数</th></tr>${redo || '<tr><td colspan="4" class="muted">全部斩尽</td></tr>'}</table></div>`;
  },

  pill() {
    const d = DASH;
    const allBoards = boardOptions(d.tree.map((t) => t.board).concat(d.side.map((s) => s.board)));
    const pills = d.pills.length ? d.pills.map((p) => `<div class="small row"><span>${esc(p.grade)}${esc(p.name)}</span><span class="muted">${esc(p.board)} · 成功率 ${pct(p.rate)}%</span><span class="spacer"></span><span class="faint">${p.d}</span></div>`).join("") : '<div class="muted small">还没炼过</div>';
    const behind = d.ideal.diff_days >= 1;
    return `<div class="grid g2">
      <div class="card"><h3>⚗ ${esc(W("alchemy"))} <small>${behind ? `落后 ${d.ideal.diff_days} 天，正是加练的时候` : "功课之外的加练"}</small></h3>
        <p class="muted small">选一个板块开一炉：${esc(W("recite"))}与${esc(W("kill"))}混合。成功率 ≥80% 上品、≥50% 中品，否则下品；成丹后这一炉的${esc(W("xp"))}再加 10% / 20% / 30%（数值在规则.md 里改）。</p>
        <div class="row"><select id="pillBoard">${boardOptions(d.pill_boards)}</select><button class="primary" id="pillBtn" ${d.pill_boards.length ? "" : "disabled"}>开炉</button></div>
        <h3 style="margin-top:14px">最近的${esc(W("pill"))}</h3>${pills}</div>
      <div class="card"><h3>🧘 ${esc(W("retreat"))} <small>专注一个板块，期间该板块${esc(W("xp"))}加成</small></h3>
        ${d.retreat ? `<p><b>正在${esc(W("retreat"))}：${esc(d.retreat.board)}</b> <span id="retreatLeft" class="muted"></span></p><button id="retreatEnd">${esc(W("retreat_end"))}</button>`
          : `<div class="row"><select id="rtBoard">${allBoards}</select><select id="rtMin"><option value="60">60 分钟</option><option value="90">90 分钟</option><option value="120">120 分钟</option><option value="30">30 分钟</option></select>
          <button class="primary" id="rtBtn">开始${esc(W("retreat"))}</button></div><p class="small muted">${esc(W("retreat"))}期间照常做这个板块的功课或${esc(W("alchemy"))}；时间到自动${esc(W("retreat_end"))}，导师会点评收获。</p>`}
        <h3 style="margin-top:14px">🎒 ${esc(W("bag"))}</h3>${d.bag.length ? d.bag.map((b) => `<div class="small"><b>${esc(b.name)}</b> ×${b.count} <span class="faint">${esc(b.desc)}</span></div>`).join("") : '<div class="muted small">空</div>'}</div>
    </div>`;
  },

  log() {
    const d = DASH;
    return `<div class="grid g2">
      <div class="card"><h3>⚔ 记录${esc(W("boss"))}（模考成绩）</h3>
        <div class="row"><input id="bossName" placeholder="名称，如 第37季" style="flex:2"><input id="bossScore" placeholder="分数" style="flex:1"></div>
        <div class="row" style="margin-top:8px"><button class="primary" id="bossBtn">记录</button><span class="small muted">最近两次的较低分若高于当前${esc(W("score"))}，${esc(W("xp"))}直接补上；达到下一道${esc(W("tribulation"))}线得突破丹</span></div></div>
      <div class="card"><h3>🌲 记录${esc(W("practice"))}（资料分析、常识等自练）</h3>
        <div class="row"><input id="prBoard" placeholder="板块" style="flex:2"><input id="prTotal" placeholder="题数" style="flex:1"><input id="prOk" placeholder="对了几题" style="flex:1"><input id="prMin" placeholder="分钟" style="flex:1"></div>
        <div class="row" style="margin-top:8px"><button class="primary" id="prBtn">记录</button><span class="small muted">分钟计入今天的修炼时间</span></div></div>
    </div>
    <div class="grid g2">
      <div class="card"><h3>📜 ${esc(W("leave"))} <small>本月已用 ${d.leave.used}/${d.leave.total}</small></h3>
        <p class="muted">生病、家里有事、加班……用一份${esc(W("leave"))}：今天${esc(W("streak"))}不断，也不计入${esc(W("ideal"))}。</p>
        <button id="leaveBtn" ${d.leave.today ? "disabled" : ""}>${d.leave.today ? "今天已告假" : "使用" + esc(W("leave"))}</button></div>
      <div class="card ascend-card"><h3>🌈 ${esc(W("ascend"))}（国考）</h3>
        ${d.ascend.length ? d.ascend.map((b) => `<div><b>${esc(b.name)}</b> ${b.score} 分 <span class="faint small">${b.d}</span></div>`).join("") : '<p class="muted small">国考出分后在这里留下记录。</p>'}
        <div class="row" style="margin-top:8px"><input id="asName" placeholder="如 2026 国考" style="flex:2"><input id="asScore" placeholder="行测分数" style="flex:1">
        <select id="asResult"><option>进面</option><option>上岸</option><option>未进面</option></select><button class="primary" id="asBtn">记录</button></div></div>
    </div>
    <div class="card"><h3>📖 修行日志</h3>${recentList(d.recent)}</div>`;
  },

  async settings() {
    const s = await api("/api/settings");
    const cur = DASH?.theme?.name;
    return AMB.settingsHtml() + `<div class="card"><h3>🎨 风格</h3>
      <div class="row"><button class="${cur === "修仙" ? "primary" : ""}" data-theme="修仙">☯ 东方修仙（师尊 劭神韵）</button>
      <button class="${cur === "玄幻" ? "primary" : ""}" data-theme="玄幻">⚔ 西方玄幻（艾琳学姐）</button></div>
      <p class="small muted">两种风格共用同一份进度，只换名字、导师、配色和台词。两台电脑同步。</p></div>
      <div class="card"><h3>本机设置 <small>保存在本机 ~/.xingce-rpg/settings.json，不会同步、不会上传</small></h3>
      <label class="small muted">行测库路径（含 copilot/skills 的文件夹；程序放在库里时会自动找到）</label>
      <input id="sVault" value="${esc(s.vault_setting)}" placeholder="${esc(s.vault || "例如 C:\\Users\\你\\Desktop\\行测obsidian\\行测")}">
      <div class="small faint">当前使用：${esc(s.vault || "未找到")}</div><br>
      <label class="small muted">AI 的 API key ${s.has_key ? `（已填写，末尾 ${esc(s.key_tail)}；不改就留空）` : ""}</label>
      <input id="sKey" type="password" placeholder="sk-……">
      <div class="row" style="margin-top:8px">
        <div style="flex:2"><label class="small muted">接口地址</label><input id="sBase" value="${esc(s.base_url)}"></div>
        <div style="flex:1"><label class="small muted">模型</label><input id="sModel" value="${esc(s.model)}"></div></div>
      <div class="row" style="margin-top:12px"><button class="primary" id="sSave">保存</button><button id="sTest">测试 AI 连接</button><span id="sMsg" class="small muted"></span></div></div>
      <div class="card"><h3>改规则 / 人设 / 台词</h3>
      <p>在 Obsidian 里直接编辑库里的这些文件，保存后刷新网页就生效：</p>
      <ul><li><b>训练/规则.md</b>：目标日、境界分数线、渡劫条件、灵根门槛、丹药、周常、修为值……</li>
      <li><b>训练/角色设定.md</b>：ID、头像；两种风格各自的称呼、导师名 / 头像 / 人设</li>
      <li><b>训练/台词库.md</b>（修仙）/ <b>台词库·玄幻.md</b>：导师的备用台词（没连 AI 时用）</li>
      <li><b>训练/骨架/板块.md</b>：每个板块的${esc(W("skeleton"))}（默写标准）</li></ul>
      <p class="small muted">头像：把图片放进 <b>训练/</b>，文件名写进角色设定.md 的“头像”“修仙.导师头像”。</p></div>`;
  },
};

// ------------------------------------------------------------ 交互绑定
function bindTaskClicks(root) {
  root.querySelectorAll("[data-task]").forEach((el) => (el.onclick = () => startTask({ task_id: el.dataset.task })));
}
function bindRetreatTimer() {
  const el = $("#retreatLeft"), btn = $("#retreatEnd");
  if (btn) btn.onclick = async () => { try { const r = await api("/api/retreat/end", {}); handleEvents(r.events); render(); } catch (e) { showError(e); } };
  if (!el || !DASH?.retreat) return;
  const tick = () => {
    const s = Math.max(0, Math.round(DASH.retreat.end - Date.now() / 1000));
    el.textContent = `还剩 ${Math.floor(s / 60)} 分 ${s % 60} 秒`;
    if (s <= 0) { clearInterval(window._rt); render(); }
  };
  tick();
  clearInterval(window._rt);
  window._rt = setInterval(() => { if (!document.body.contains(el)) return clearInterval(window._rt); tick(); }, 1000);
}
// ------------------------------------------------------------ 听道（其他平台看网课）：首页记录，计入每日功行
function lectureCard(d) {
  const m = d.minutes, goal = m.goal || 300;
  const sw = Math.min(100, (m.study ?? 0) / goal * 100), lw = Math.min(100 - sw, (m.lecture ?? 0) / goal * 100);
  const left = Math.max(0, goal - m.today);
  const days = [0, 1, 2, 3, 4, 5, 6].map((k) => { const t = new Date(Date.now() - k * 864e5); return t.getFullYear() + "-" + String(t.getMonth() + 1).padStart(2, "0") + "-" + String(t.getDate()).padStart(2, "0"); });
  const dayName = (ds, k) => k === 0 ? "今天" : k === 1 ? "昨天" : k === 2 ? "前天" : ds.slice(5);
  const rows = (d.lectures || []).map((x) => `<div class="lec-row"><span class="faint">${esc(x.d.slice(5))}</span><b>${x.minutes} 分钟</b>
      <span class="muted">${esc(x.note || "")}</span><span class="spacer"></span><button class="ghost small" data-lec-del="${esc(x.id)}" title="记错了，删掉这笔">删</button></div>`).join("");
  return `<div class="card lecture-card" style="margin-top:14px">
    <h3>📿 ${esc(W("lecture_title"))} <small>今日功行 ${m.today} / ${goal} 分钟 · ${esc(W("study"))} ${m.study ?? 0} · ${esc(W("lecture"))} ${m.lecture ?? 0}${left ? ` · 还差 ${left} 分钟` : " · 已圆满 ✦"}</small></h3>
    <div class="dual-bar" title="${esc(W("study"))} ${m.study ?? 0} 分钟 + ${esc(W("lecture"))} ${m.lecture ?? 0} 分钟"><span class="s" style="width:${sw}%"></span><span class="l" style="width:${lw}%"></span></div>
    <p class="small muted">${esc(W("lecture_hint"))}</p>
    <div class="row lec-form">
      <label>${esc(W("lecture"))}几分钟 <input type="number" id="lecMin" min="1" max="600" placeholder="如 90"></label>
      <span class="lec-quick">${[30, 60, 90, 120].map((n) => `<button class="ghost small" data-lec-q="${n}">${n}</button>`).join("")}</span>
      <label style="flex:2">讲的什么（可不填） <input id="lecNote" maxlength="40" placeholder="如：粉笔 判断推理 第3讲"></label>
      <label>哪天 <select id="lecDay">${days.map((ds, k) => `<option value="${ds}">${dayName(ds, k)}</option>`).join("")}</select></label>
      <button class="primary" id="lecGo">📿 记入</button></div>
    ${rows ? `<details class="fold" style="margin-top:8px"><summary>近 7 天${esc(W("lecture"))}记录</summary>${rows}</details>` : ""}
  </div>`;
}
function bindLecture() {
  const go = $("#lecGo"); if (!go) return;
  document.querySelectorAll("[data-lec-q]").forEach((b) => (b.onclick = () => { $("#lecMin").value = b.dataset.lecQ; }));
  go.onclick = async () => {
    const minutes = Number($("#lecMin").value);
    if (!minutes) return toast(`先填${W("lecture")}了几分钟`);
    try {
      const r = await api("/api/lecture", { minutes, note: $("#lecNote").value.trim(), date: $("#lecDay").value });
      handleEvents(r.events); await refresh(); render();
    } catch (e) { showError(e); }
  };
  document.querySelectorAll("[data-lec-del]").forEach((b) => (b.onclick = async () => {
    if (!confirm("删掉这笔记录？（那次得到的修为也会扣回）")) return;
    try { await api("/api/lecture/delete", { id: b.dataset.lecDel }); await refresh(); render(); } catch (e) { showError(e); }
  }));
}
function bindHome() {
  bindTaskClicks($("#view"));
  bindLecture();
  $("#regen").onclick = async () => { try { await api("/api/plan/regenerate", {}); render(); } catch (e) { showError(e); } };
  $("#chatBtn").onclick = () => startTask({ task: { type: "chat", board: "", target: "", title: `💬 ${W("tutor_room")}` } });
  const gp = $("#goPill"); if (gp) gp.onclick = () => go("pill");
  const tb = $("#tribBtn"); if (tb) tb.onclick = () => startTask({ task: { type: "tribulation", board: "", target: String(DASH.trib.gate), title: `⚡ ${W("tribulation")} · ${DASH.trib.realm}` } });
  bindRetreatTimer();
  if (DASH?.greet_pending) {
    DASH.greet_pending = false;
    api("/api/tutor/greet", {}).then((r) => {
      if (r.text) { DASH.greeting = r.text; const el = $("#greet"); if (el) el.innerHTML = md(r.text); }
      else { const t = $("#greet .thinking"); if (t) t.remove(); }
    }).catch(() => { const t = $("#greet .thinking"); if (t) t.remove(); });
  }
}

async function startTask(body) {
  Object.assign(T, { session: null, title: "准备中…", msgs: [], input: { mode: "none" }, busy: true, finished: false, battle: null });
  go("train");
  try { applyResp(await api("/api/session/start", body)); }
  catch (e) { T.busy = false; T.msgs.push({ who: "sys", text: "⚠ " + e.message }); T.finished = true; }
  renderTrain();
}
function applyResp(r) {
  T.session = r.session; T.title = r.title; T.busy = false; T_TYPE = r.type;
  T.msgs.push(...r.messages);
  handleEvents(r.events, { inChat: true });
  T.input = r.input || { mode: "none" };
  T.finished = r.finished;
  T.battle = r.battle || null;
  if (r.finished) refresh().then(() => VIEW === "train" && renderTrain());
}
function renderTrain() {
  if (VIEW !== "train") return;
  $("#view").innerHTML = views.train();
  bindTrain();
  const box = $("#msgs"); if (box) box.scrollTop = box.scrollHeight;
  const ta = $("#answer"); if (ta) ta.focus();
}
function bindTrain() {
  bindTaskClicks($("#view"));
  const send = $("#send");
  if (send) {
    send.onclick = submitText;
    $("#answer").onkeydown = (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submitText(); };
  }
  document.querySelectorAll("[data-act]").forEach((b) => (b.onclick = () => doAction(b.dataset.act)));
  const nx = $("#nextTask");
  if (nx) nx.onclick = () => {
    const t = (DASH?.plan?.tasks || []).find((x) => !x.done);
    t ? startTask({ task_id: t.id }) : (toast(`${W("tasks")}全部完成 ✦`), go("home"));
  };
  const bh = $("#backHome"); if (bh) bh.onclick = () => { Object.assign(T, { session: null, msgs: [] }); go("home"); };
}
async function submitText() {
  const text = $("#answer").value.trim();
  if (!text) return;
  T.msgs.push({ who: "me", text }); T.busy = true; renderTrain();
  try { applyResp(await api("/api/session/reply", { session: T.session, text })); }
  catch (e) { T.busy = false; T.msgs.push({ who: "sys", text: "⚠ " + e.message }); }
  renderTrain();
}
async function doAction(act) {
  T.busy = true; renderTrain();
  try { applyResp(await api("/api/session/action", { session: T.session, action: act })); }
  catch (e) { T.busy = false; T.msgs.push({ who: "sys", text: "⚠ " + e.message }); }
  renderTrain();
}
// 整套试炼：练习册按“前缀-套-题”编号，一次刷完一整套（跨板块，如言语书一套里有片段阅读和逻辑填空）
function setsHtml(books) {
  if (!books?.length) return '';
  // 练习册：第NN套；历年真题：卷子名去掉“《行测》…”这类尾巴
  const short = (x) => x.year !== undefined ? x.name.replace(/公务员录用考试|录用公务员考试|《行测》|试卷|题|（网友回忆版）/g, '').slice(0, 30) : `第${x.set}套`;
  const btn = (book, x, cls, verb = '') => `<button class="${cls}" data-bank="套:${esc(x.name)}" data-mode="new" data-title="${esc(x.year !== undefined ? x.name : book + ' 第' + x.set + '套')}"
      title="${esc(x.name)}" ${!x.active && x.done >= x.total ? 'disabled' : ''}>${x.active ? '▶ ' : x.done >= x.total ? '✓ ' : ''}${verb}${esc(short(x))} <span class="small">${x.done}/${x.total}</span></button>`;
  const grid = (b) => {
    if (!b.paper) return `<div class="set-grid">${b.sets.map(x => btn(b.book, x, 'ghost')).join('')}</div>`;
    const years = [...new Set(b.sets.map(x => x.year))];
    return years.map(y => `<p class="small muted">${esc(y)} 年</p><div class="set-grid">${b.sets.filter(x => x.year === y).map(x => btn(b.book, x, 'ghost')).join('')}</div>`).join('');
  };
  return `<div class="card set-card"><h3>📚 整套试炼 <span class="small muted">一次刷完一整套，做完再看下一套；答案待补的题不出</span></h3>
    ${books.map(b => {
      const nx = b.sets.find(x => x.name === b.next);
      return `<div class="set-book"><div class="row"><b>${esc(b.book)}</b><span class="small muted">共 ${b.sets.length} ${b.paper ? '张卷子（只含判断推理，新卷在前）' : '套'} · 已完成 ${b.finished}</span><span class="spacer"></span>
        ${nx ? btn(b.book, nx, 'primary', nx.active ? '继续 ' : '开始 ') : '<span class="tag ok">全部完成</span>'}</div>
        <details><summary class="small">选择其他${b.paper ? '卷子' : '套'}</summary>${grid(b)}</details></div>`;
    }).join('')}</div>`;
}
function bindBank() {
  const focusTower = () => {
    const box = $("#towerViewport"), floor = $(".tower-floor.current");
    if (box && floor) box.scrollTop = floor.offsetTop + floor.parentElement.offsetTop - box.clientHeight / 2 + floor.offsetHeight / 2;
  };
  requestAnimationFrame(focusTower);
  $("#towerLocate").onclick = focusTower;
  $("#towerTop").onclick = () => { $("#towerViewport").scrollTop = 0; };
  $("#towerBottom").onclick = () => { const b = $("#towerViewport"); b.scrollTop = b.scrollHeight; };
  $('#bankCount').onchange = async (e) => {
    try { await api('/api/bank/count', { count: Number(e.target.value) }); toast('已保存，下一组生效'); }
    catch (err) { showError(err); }
  };
  $('#importCard').ontoggle = (e) => { if (e.target.open) loadImport(); };
  document.querySelectorAll('[data-bank]').forEach(b => b.onclick = () => startTask({ task: {
    type: b.dataset.mode === 'review' ? 'bank_review' : 'bank', board: b.dataset.bank,
    target: b.dataset.bank, title: `⚔ ${b.dataset.title || b.dataset.bank} · ${W(b.dataset.mode === 'review' ? 'bank_review' : 'bank')}`
  } }));
}
// ------------------------------------------------------------ 导入真题（rpg/importer.py）
let IMPORT_TEXT = null;   // 选中的 txt 内容（只在浏览器里读，导入时发给本机程序）
let IMPORT_PDF = null;    // 选中的 PDF（base64），由本机程序抽文字
let IMPORT_KEEP = '';     // 导入后整页重画时保留的结果报告
async function loadImport() {
  const box = $('#importBody');
  try {
    const d = await api('/api/import');
    const opts = ['<option value="">自动识别</option>', ...d.boards.map(b => `<option>${esc(b)}</option>`)].join('');
    box.innerHTML = `
      <div class="import-sec"><h4>① 模考（粉笔模考 PDF：自动拆分成板块复盘，再导入；题干、答案、截图都准）</h4>
        <div class="row"><input type="file" id="pdfFile" accept=".pdf,application/pdf" style="flex:2">
          <label style="flex:1">第几季 <input id="pdfSeason" type="number" min="1" placeholder="文件名有“第X季”就不用填"></label>
          <button class="primary" id="pdfGo" ${d.splitter && d.pymupdf ? '' : 'disabled'}>拆分并导入</button></div>
        ${!d.splitter ? '<p class="small">⚠ 没找到 xingce-mokao-split，先运行一次 skill 安装脚本。</p>' : ''}
        ${d.splitter && !d.pymupdf ? '<p class="small">⚠ 拆 PDF 需要 pymupdf 组件（只装一次）。<button id="pymuGo">安装拆分组件</button></p>' : ''}
        ${d.pdfs.filter(x => !x.split).map(x => `<div class="row"><span>📄 ${esc(x.file)}</span><span class="small muted">${x.season ? `第 ${x.season} 季 · 还没拆` : '文件名里没有“第X季”'}</span><span class="spacer"></span>
          <button data-split="${esc(x.file)}" ${x.season && d.splitter && d.pymupdf ? '' : 'disabled'}>拆分并导入</button></div>`).join('')}
        <p class="small muted">PDF 会存进 ${esc(d.pdf_dir)}，拆好的复盘在 FB模考试卷复盘/板块复盘/第N季/（和以前做复盘的一样）。下面是已经拆好的各季：</p>
        ${d.seasons.map(x => `<div class="row"><span>第 ${x.season} 季</span><span class="small muted">已导入 ${x.imported} 题</span><span class="spacer"></span>
          <button class="ghost" data-imp-season="${x.season}" data-dry="1">预览</button><button data-imp-season="${x.season}">导入</button></div>`).join('')
          || '<p class="small muted">还没有板块复盘。用 xingce-mokao-split 拆模考 PDF 后这里会出现。</p>'}</div>
      <div class="import-sec"><h4>② txt / PDF（练习册、试卷；有文字层的 PDF 能保留填空横线）</h4>
        <div class="row"><input type="file" id="impFile" accept=".txt,.md,.pdf,text/plain,application/pdf"><span class="small muted" id="impFileInfo"></span></div>
        <div class="row"><label>来源 <input id="impSource" placeholder="自动识别，如 2025年国考"></label>
          <label><input type="checkbox" id="impNoSource"> 没有来源</label>
          <label>编号前缀 <input id="impPrefix" placeholder="如 四海逻辑600"></label>
          <label>整份板块 <select id="impBoard">${opts}</select></label>
          <label>第一套是练习几 <input id="impStart" type="number" min="1" placeholder="不填自动（按“练习题NN”）" style="width:13em"></label>
          ${d.ai ? '<label><input type="checkbox" id="impAI"> 用 AI 补认不出的板块和知识点（DeepSeek，只发题干）</label>' : ''}</div>
        <div class="row"><button class="ghost" id="impPreview">预览</button><button class="primary" id="impCommit">导入</button></div></div>
      <div class="import-sec"><h4>③ 待修（拆不干净的题，在 Obsidian 里改好、清空“检查”后重新导入）</h4>
        ${d.fixes.map(x => `<div class="row"><span>训练/题库/_待修/${esc(x.file)}</span><span class="small muted">${x.total} 题，已改好 ${x.ready}</span><span class="spacer"></span>
          <button data-imp-fix="${esc(x.file)}">重新导入</button></div>`).join('') || '<p class="small muted">没有待修的题。</p>'}</div>
      <div class="import-sec"><h4>④ 补答案（练习册答案在另一本时）</h4>
        <p class="small muted">整本一次补：前缀填导入时的编号前缀（如“花生600题”），答案每行一套：<code>练习01 ADDBA CDCAB DBBCC BBADD</code>。
          只补一套：前缀写到第几套（如“花生600题-03”），答案写 <code>1-5 ABCDA 6-10 …</code> 或 <code>1.A 2.B</code>。</p>
        <div class="row"><label>编号前缀 <input id="ansPrefix" placeholder="如 花生600题"></label><button id="ansGo">补答案</button></div>
        <textarea id="ansKey" rows="5" style="width:100%" placeholder="练习01 ADDBA CDCAB DBBCC BBADD&#10;练习02 DDACB DADAC DDBAA DABAB&#10;……"></textarea></div>
      <div class="import-sec"><h4>⑥ 整理题库格式</h4>
        <div class="row"><button id="normGo">整理全部题库</button><span class="small muted">选项统一写成“A. ”；把 OCR 认错的序号还原成 ①②③、ⅠⅡⅢ。只改题干和选项，编号、答案、作答记录不动</span></div></div>
      <div class="import-sec"><h4>⑧ 改编号前缀</h4>
        <p class="small muted">两本书用了同一个前缀、或者想改个更清楚的名字时用。题库、作答记录一起改，做过的题历史不丢。只勾部分板块时只改这些板块里的题。</p>
        <div class="row"><label>旧前缀 <input id="rnOld" placeholder="如 花生600题"></label><label>新前缀 <input id="rnNew" placeholder="如 花生600题逻辑"></label>
          <button id="rnGo">改前缀</button></div>
        <div class="row small">${d.boards.map((b) => `<label><input type="checkbox" class="rnB" value="${esc(b)}"> ${esc(b)}</label>`).join(" ")}</div></div>
      <div class="import-sec"><h4>⑦ 撤销一批导入</h4>
        <div class="row"><label>编号前缀 <input id="rmPrefix" placeholder="如 花生600题"></label>
          <button class="ghost" id="rmGo">删除这批没做过的题</button><span class="small muted">导错了想重导时用；做过的题有作答记录，会保留</span></div></div>
      <div class="import-sec"><h4>⑤ 知识点</h4><div class="row"><span>“待分类”的题：${d.unsorted} 道</span><span class="spacer"></span>
        ${d.ai ? `<button id="clsGo" ${d.unsorted ? '' : 'disabled'}>AI 补 100 题</button>` : '<span class="small muted">在设置里填 DeepSeek key 后可以让 AI 补；不补也能正常做题</span>'}</div></div>
      <div id="importResult" class="import-result">${IMPORT_KEEP}</div>`;
    const hadResult = !!IMPORT_KEEP;
    IMPORT_KEEP = '';
    bindImport();
    if (hadResult) $('#importResult').scrollIntoView({ block: 'center' });
  } catch (e) { box.innerHTML = `<p class="small">⚠ ${esc(e.message)}</p>`; }
}

function importReport(r, dry) {
  const boards = r.boards.map(([b, n]) => `${esc(b)} ${n}`).join('，') || '—';
  return `<div class="card inner"><b>${dry ? '预览' : '已导入'}：${esc(r.name || '')}</b>
    ${r.split_log ? `<details class="fold"><summary>拆分记录</summary><div>${md(r.split_log)}</div></details>` : ''}${r.source ? ` <span class="tag">${esc(r.source)}</span>` : ''}
    ${r.note ? `<p class="small">${esc(r.note)}</p>` : ''}
    <p>${dry ? '可以入库' : '入库'} <b>${r.ready}</b> 题（${boards}）· 进待修 ${r.fix} 题 · 已有跳过 ${r.dup} 题</p>
    <p class="small muted">其中知识点待分类 ${r.unsorted} 题，答案待补 ${r.no_answer} 题（答案待补的题先不出）。${r.fix_file ? '待修文件：' + esc(r.fix_file) : ''}</p>
    ${r.samples.map(q => `<details class="fold"><summary>${esc(q.id)} · ${esc(q.board)} · ${esc(q.topic)} · 答案 ${esc(q.answer)}</summary><div>${md(q.stem)}<br>${'ABCD'.split('').map(k => esc(k + '. ' + (q.options[k] || ''))).join('<br>')}</div></details>`).join('')}
    ${r.problems.length ? `<details class="fold"><summary>待修的题（前 ${r.problems.length} 道）</summary><div>${r.problems.map(p => esc(p.id + '：' + p.problems.join('；'))).join('<br>')}</div></details>` : ''}</div>`;
}

function bindImport() {
  const show = (html) => {   // 结果写在卡片最底下：写完滚过去，免得以为“没反应”
    const el = $('#importResult'); el.innerHTML = html;
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };
  const run = async (btn, url, body, dry) => {
    const label = btn.textContent; btn.disabled = true; btn.textContent = '处理中…';
    show('<p class="muted">处理中，请稍候…</p>');
    try {
      const r = await api(url, body);
      if (url.endsWith('/answers')) show(`<p>补了 <b>${r.filled}</b> 题的答案（答案表 ${r.key} 个）。</p>`);
      else if (url.endsWith('/install_pymupdf')) show(r.ok ? '<p>✅ 拆分组件装好了，现在可以拆 PDF。</p>' : '<p>⚠ 装完了但还是找不到组件，关掉程序重新打开试试。</p>');
      else if (url.endsWith('/rename')) show(`<p>改了 <b>${r.renamed}</b> 道题的编号（${r.files} 个题库文件），作答记录迁移 ${r.records} 条。</p>`);
      else if (url.endsWith('/normalize')) show(`<p>整理了 <b>${r.changed}</b> 道题（${r.files} 个文件）。${r.flagged_total ? `有 ${r.flagged_total} 道题的序号 OCR 丢了信息，没法自动还原，请对照原书改：${r.flagged.map(esc).join('、')}${r.flagged_total > r.flagged.length ? ' …' : ''}` : ''}</p>`);
      else if (url.endsWith('/remove')) show(`<p>删除了 <b>${r.removed}</b> 题${r.kept ? `，${r.kept} 道已经做过的保留` : ''}。</p>`);
      else if (url.endsWith('/classify')) show(`<p>补了 ${r.done} 题的知识点，还剩 ${r.left} 题待分类。</p>`);
      else show(importReport(r, dry));
      if (!dry) {   // 入库后整页重画：下面各板块的题数要跟着变
        IMPORT_KEEP = $('#importResult').innerHTML;
        await render();
        const card = $('#importCard');
        if (card) card.open = true;   // 触发 toggle → loadImport，再把这次的结果放回去
      }
    } catch (e) { show(`<p>⚠ ${esc(e.message)}</p>`); }
    finally { btn.disabled = false; btn.textContent = label; }
  };
  document.querySelectorAll('[data-imp-season]').forEach(b => b.onclick = () => run(b,
    b.dataset.dry ? '/api/import/preview' : '/api/import/commit', { kind: 'season', season: Number(b.dataset.impSeason) }, !!b.dataset.dry));
  document.querySelectorAll('[data-imp-fix]').forEach(b => b.onclick = () => run(b, '/api/import/commit', { kind: 'fix', file: b.dataset.impFix }, false));
  const splitRun = (btn, file) => run(btn, '/api/import/split', { file }, false);
  document.querySelectorAll('[data-split]').forEach(b => b.onclick = () => splitRun(b, b.dataset.split));
  $('#pdfGo').onclick = async (e) => {
    const f = $('#pdfFile').files[0];
    if (!f) return show('<p>⚠ 先选一份模考 PDF</p>');
    const btn = e.target; btn.disabled = true; btn.textContent = '上传中…';
    try {
      const buf = new Uint8Array(await f.arrayBuffer());
      let bin = ''; for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
      const r = await api('/api/import/upload_pdf', { name: f.name, data: btoa(bin), season: Number($('#pdfSeason').value) || 0 });
      btn.disabled = false; btn.textContent = '拆分并导入';
      show('<p>已保存，正在拆分（大约半分钟）…</p>');
      await splitRun(btn, r.file);
    } catch (err) { show(`<p>⚠ ${esc(err.message)}</p>`); btn.disabled = false; btn.textContent = '拆分并导入'; }
  };
  if ($('#pymuGo')) $('#pymuGo').onclick = (e) => {
    if (confirm('将运行 pip install pymupdf 安装拆 PDF 用的组件（需要联网，只装一次），继续？')) run(e.target, '/api/import/install_pymupdf', {}, false);
  };
  $('#impFile').onchange = async (e) => {
    const f = e.target.files[0]; IMPORT_TEXT = null; IMPORT_PDF = null;
    if (!f) return;
    const buf = await f.arrayBuffer();
    if (!$('#impPrefix').value) $('#impPrefix').placeholder = f.name.replace(/\.[^.]+$/, '').slice(0, 12) + '（不填就按来源/文件名）';
    if (/\.pdf$/i.test(f.name)) {
      const u8 = new Uint8Array(buf);
      let bin = ''; for (let i = 0; i < u8.length; i += 0x8000) bin += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000));
      IMPORT_PDF = btoa(bin);
      $('#impFileInfo').textContent = `${f.name} · PDF ${Math.round(f.size / 1024)} KB`;
      return;
    }
    try { IMPORT_TEXT = new TextDecoder('utf-8', { fatal: true }).decode(buf); }
    catch { IMPORT_TEXT = new TextDecoder('gb18030').decode(buf); }   // 有些 OCR 软件存成 GBK
    IMPORT_TEXT = IMPORT_TEXT.replace(/^\uFEFF/, '');
    $('#impFileInfo').textContent = `${f.name} · ${IMPORT_TEXT.length} 字`;
  };
  const textBody = () => {
    if (!IMPORT_TEXT && !IMPORT_PDF) throw new Error('先选一个 txt 或 PDF 文件');
    return { ...(IMPORT_PDF ? { kind: 'pdf', data: IMPORT_PDF } : { kind: 'text', text: IMPORT_TEXT }), name: $('#impFile').files[0]?.name || '', source: $('#impSource').value.trim(),
             no_source: $('#impNoSource').checked, prefix: $('#impPrefix').value.trim(), board: $('#impBoard').value, ai: !!$('#impAI')?.checked,
             start_set: Number($('#impStart').value) || 0 };
  };
  $('#impPreview').onclick = (e) => { try { run(e.target, '/api/import/preview', textBody(), true); } catch (err) { show(`<p>⚠ ${esc(err.message)}</p>`); } };
  $('#impCommit').onclick = (e) => { try { run(e.target, '/api/import/commit', textBody(), false); } catch (err) { show(`<p>⚠ ${esc(err.message)}</p>`); } };
  $('#ansGo').onclick = (e) => run(e.target, '/api/import/answers', { prefix: $('#ansPrefix').value.trim(), key: $('#ansKey').value }, false);
  $('#normGo').onclick = (e) => run(e.target, '/api/import/normalize', {}, false);
  $('#rnGo').onclick = (e) => {
    const o = $('#rnOld').value.trim(), n = $('#rnNew').value.trim();
    const boards = [...document.querySelectorAll('.rnB:checked')].map((x) => x.value);
    if (!o || !n) return show('<p>⚠ 填旧前缀和新前缀</p>');
    if (!confirm(`把编号「${o}-…」改成「${n}-…」（${boards.length ? '只改：' + boards.join('、') : '全部板块'}）？`)) return;
    run(e.target, '/api/import/rename', { old: o, new: n, boards }, false);
  };
  $('#rmGo').onclick = (e) => {
    const pre = $('#rmPrefix').value.trim();
    if (!pre || !confirm(`删除编号以「${pre}-」开头、还没做过的所有题（题库和待修文件里都删）？`)) return;
    run(e.target, '/api/import/remove', { prefix: pre }, false);
  };
  if ($('#clsGo')) $('#clsGo').onclick = (e) => run(e.target, '/api/import/classify', { limit: 100 }, false);
}

function bindSkeleton() {
  document.querySelectorAll("[data-skel]").forEach((b) => (b.onclick = () =>
    startTask({ task: { type: "skeleton", board: b.dataset.skel, target: b.dataset.skel, title: `📜 「${b.dataset.skel}」${W("skeleton")}` } })));
  document.querySelectorAll("[data-free]").forEach((a) => (a.onclick = () =>
    startTask({ task: { type: a.dataset.train || "recite", board: a.dataset.board, target: a.dataset.free, title: `${W(a.dataset.train || "recite")} · ${a.dataset.board}「${a.dataset.name}」` } })));
}
function bindPill() {
  const pb = $("#pillBtn");
  if (pb) pb.onclick = () => { const b = $("#pillBoard").value; startTask({ task: { type: "alchemy", board: b, target: b, title: `⚗ ${W("alchemy")} · ${b}` } }); };
  const rb = $("#rtBtn");
  if (rb) rb.onclick = async () => {
    try { const r = await api("/api/retreat/start", { board: $("#rtBoard").value, minutes: $("#rtMin").value }); handleEvents(r.events); render(); } catch (e) { showError(e); }
  };
  bindRetreatTimer();
}
function bindLog() {
  $("#bossBtn").onclick = async () => {
    try { const r = await api("/api/boss", { name: $("#bossName").value, score: $("#bossScore").value }); handleEvents(r.events); render(); } catch (e) { showError(e); }
  };
  $("#prBtn").onclick = async () => {
    try { const r = await api("/api/practice", { board: $("#prBoard").value, total: $("#prTotal").value, correct: $("#prOk").value, minutes: $("#prMin").value }); handleEvents(r.events); render(); } catch (e) { showError(e); }
  };
  $("#leaveBtn").onclick = async () => { try { const r = await api("/api/leave", {}); handleEvents(r.events); render(); } catch (e) { showError(e); } };
  $("#asBtn").onclick = async () => {
    try { const r = await api("/api/boss", { kind: "飞升", name: $("#asName").value || "国考", score: $("#asScore").value, result: $("#asResult").value }); handleEvents(r.events); render(); } catch (e) { showError(e); }
  };
}
function bindSettings() {
  AMB.bindSettings(showError);
  document.querySelectorAll("[data-theme]").forEach((b) => (b.onclick = async () => {
    try { await api("/api/theme", { theme: b.dataset.theme }); await refresh(); render(); } catch (e) { showError(e); }
  }));
  $("#sSave").onclick = async () => {
    const body = { vault: $("#sVault").value, base_url: $("#sBase").value, model: $("#sModel").value };
    if ($("#sKey").value.trim()) body.api_key = $("#sKey").value.trim();
    try { await api("/api/settings", body); $("#sMsg").textContent = "已保存"; await refresh(); } catch (e) { showError(e); }
  };
  $("#sTest").onclick = async () => {
    $("#sMsg").textContent = "测试中…";
    try { const r = await api("/api/settings/test", {}); $("#sMsg").textContent = "✅ " + r.reply; } catch (e) { $("#sMsg").textContent = ""; showError(e); }
  };
}

// ------------------------------------------------------------ 修炼计时（心跳）
// 只在“真正修炼”时计时：开着一项功课（背诵 / 论道 / 试剑 / 斩心魔 / 温养 / 渡劫 / 炼丹，或刚做完在看解析），
// 页面可见，并且 2 分钟内有键盘鼠标操作（或正在等 AI 判题）。只是开着网页、看面板、和导师闲聊都不计时。
// 后端也会核对会话是否真的在进行（rpg/trainer.is_studying），前端条件只是省掉无用的上报。
const BEAT = 30;
const STUDY = ["recite", "review", "speedrun", "feynman", "example", "apply", "wrong", "tribulation", "alchemy", "bank", "bank_review"];
let lastActive = Date.now();
let T_TYPE = "";
["mousemove", "keydown", "click", "scroll", "input"].forEach((ev) => addEventListener(ev, () => (lastActive = Date.now()), { passive: true }));
function studyingNow() {
  return VIEW === "train" && !!T.session && STUDY.includes(T_TYPE) && document.visibilityState === "visible"
    && (T.busy || Date.now() - lastActive < 120000);
}
function updateStudyDot() {
  const on = studyingNow();
  $("#todayPill").classList.toggle("on", on);
  $("#todayPill").title = on ? "正在计时：修炼中" : "未计时：只有做功课时才算修炼时间";
}
let beatCount = 0;
setInterval(async () => {
  updateStudyDot();
  const on = studyingNow();
  beatCount += 1;
  if (!on && beatCount % 2) return;          // 不修炼时每分钟只刷新一次状态（多设备提醒、调息、闭关）
  try {
    const r = await api("/api/heartbeat", { seconds: on ? BEAT : 0, session: on ? T.session : null });
    if (DASH) { DASH.minutes.today = r.minutes; DASH.other_device = r.other_device; DASH.rest = r.rest; updatePill(); banner(); }
    handleEvents(r.events);
    if (DASH?.retreat && !r.retreat_on && VIEW === "home") render();
  } catch (e) { /* 程序关了就不提示 */ }
}, BEAT * 1000);
setInterval(updateStudyDot, 5000);

render();



// 试炼进度与破关数，不显示任何未提交题目的答案。
function battlePanel() {
  const b = T.battle;
  if (!b) return '';
  return `<div class="battle-panel"><div class="row"><b>⚔ ${esc(W(b.mode === 'review' ? 'bank_review' : 'bank'))}</b><span class="spacer"></span><span>第 ${b.position}/${b.total} 关</span></div>
    ${towerProgress(b.tower)}${bar(b.answered / b.total, 'thin yellow')}<div class="bank-counters"><span>已作答 ${b.answered}</span><span>破关 ${b.correct}</span><span>${esc(W('bank_wrong'))} ${b.answered - b.correct}</span></div></div>`;
}


// 100 层自上而下绘制，已登层、正在攀登层和未到达层采用不同颜色。
function towerHtml(t) {
  if (!t) return '';
  const floors = Array.from({length: t.layers}, (_, i) => t.layers - i).map(n => {
    const current = n === t.current;
    const cleared = n <= t.cleared;
    const width = 35 + 65 * (1 - (n - 1) / Math.max(1, t.layers - 1));
    const label = current ? (t.summit ? '✦ 百层登顶' : '◆ 正在攀登') : cleared ? '已登层' : '待攀登';
    return `<div class="tower-floor ${cleared ? 'cleared' : ''} ${current ? 'current' : ''}" style="width:${width}%" title="第 ${n} 层 · ${label}" aria-label="第 ${n} 层 · ${label}"><span>${n} 层</span><span class="tower-windows">▪ ▪ ▪</span><span>${current ? label : cleared ? '✓' : '·'}</span></div>`;
  }).join('');
  return `<section class="tower-layout" aria-label="试炼塔进度"><div class="tower-art"><div class="tower-controls"><button class="small" id="towerTop">塔顶</button><button class="small" id="towerLocate">定位当前层</button><button class="small" id="towerBottom">塔底</button></div>
    <div class="tower-viewport" id="towerViewport" tabindex="0" aria-label="可滚动查看全部楼层"><div class="tower-structure"><div class="tower-roof">✦</div>${floors}<div class="tower-base">试 炼 塔</div></div></div></div>
    <div class="tower-summary"><div class="rune">${t.layers} 层 · ${t.total} 道真题</div><h2>${t.summit ? '✦ 已登顶' : `已登上第 ${t.cleared} 层`}</h2>
    ${towerProgress(t)}<p>全板块累计完成 <b>${t.completed}</b> 道新题</p><p class="small muted">默认每完成 ${t.per_floor} 道新题升一层。首次提交即计数；正确率另行统计，错题复练不重复增加层数。</p>
    <p class="small muted">已有作答自动折算进度。题库逐步添加，不改变 ${t.total} 题的登顶目标。</p><div class="tower-legend"><span>金色：当前层</span><span>绿色：已登层</span><span>灰色：待攀登</span></div></div></section>`;
}
function towerProgress(t) {
  if (!t) return '';
  if (t.summit) return `<div class="tower-progress">🗼 ${t.layers} 层已全部登顶 · ${t.completed} 道新题</div>${bar(1, 'thin yellow')}`;
  return `<div class="tower-progress">🗼 正在攀登第 ${t.current} 层 · 本层 ${t.floor_done}/${t.floor_total} 道 · 再做 ${t.remaining} 道升层</div>${bar(t.floor_total ? t.floor_done / t.floor_total : 0, 'thin yellow')}`;
}
