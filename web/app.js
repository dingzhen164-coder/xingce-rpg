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
window.DASH_REF = () => DASH;   // settle.js 用
let SESSION_SNAP = null;         // 开始一项功课时的进度快照，做完后收功结算对比
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
  if (window.CEREMONY) return CEREMONY.realm(e);      // 觅长生式大典画面（web/ceremony.js）
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
  if (VIEW === "notes" && view !== "notes" && window.NOTES) NOTES.flush();
  if (window.CARDS && CARDS.isOpen()) CARDS.close();
  if (window.MINDMAP && MINDMAP.isOpen()) MINDMAP.close();
  VIEW = view;
  if (window.DRAW) setTimeout(() => DRAW.refresh(), 0);
  document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.view === view));
  render();
}
document.querySelectorAll("#nav a").forEach((a) => (a.onclick = () => go(a.dataset.view)));
// 平板 App 的返回键（android/…/MainActivity.java 调这个）：先关画面、弹窗、草稿，再回洞府；返回 false 表示没得退了
window.xcBack = () => {
  const click = (sel) => { const b = document.querySelector(sel); if (b) b.click(); return !!b; };
  if (click(".img-zoom") || click(".cer-ok") || click(".st-btn")) return true;
  if (document.documentElement.classList.contains("drawing") && window.DRAW) { DRAW.close(); return true; }
  if (window.NOTES && NOTES.isFull()) { NOTES.exitFull(); return true; }
  if (window.CARDS && CARDS.isOpen()) { CARDS.close(); return true; }
  if (window.MINDMAP && MINDMAP.isOpen()) { MINDMAP.close(); return true; }
  const m = $("#modal");
  if (m && !m.classList.contains("hidden")) { m.classList.add("hidden"); return true; }
  if (VIEW === "home") return false;
  if (document.documentElement.classList.contains("in-chat") && !confirm("离开这次功课，回洞府？")) return true;
  go("home");
  return true;
};
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
  if (!DASH.ai) w.push(`还没填写 AI 的 API key：${W("yj_review")}、${W("kill")}、真题试炼都能用；导师聊天、「🙋 师傅讲讲」、「🧙 师傅解惑」需要 AI。去“设置”填写。`);
  if (DASH.rest > 0) w.push(`${W("qi")}预警：还需调息 ${DASH.rest} 分钟。站起来走走、喝口水。`);
  (DASH.notices || []).forEach((n) => w.push(esc(n)));
  if (DASH.upgraded?.length) w.push("程序升级了配置文件：" + DASH.upgraded.map((n) => `训练/${esc(n)}`).join("、") + "。原来的版本备份成了同名的“.旧版.md”。");
  if (DASH.other_device) w.push(`另一台电脑（${esc(DASH.other_device)}）10 分钟内在用本程序。两台同时用，坚果云同步可能冲突，请先关掉那台。`);
  if (DASH.conflicts?.length) w.push("存档文件夹里有坚果云冲突副本：" + DASH.conflicts.map(esc).join("、") + "。保留较新的一份，删掉另一份。");
  $("#banner").innerHTML = w.map((x) => `<div class="warn">${x}</div>`).join("");
}

async function render() {
  const v = $("#view");
  document.documentElement.classList.remove("in-chat");
  document.documentElement.classList.toggle("in-notes", VIEW === "notes");
  try {
    if (VIEW === "home") { await refresh(); v.innerHTML = views.home(); bindHome(); }
    else if (VIEW === "train") { if (!DASH) await refresh(); v.innerHTML = await views.train(); bindTrain(); }
    else if (VIEW === "contest") { if (!DASH) await refresh(); await CONTEST.render(v); }
    else if (VIEW === "notes") { if (!DASH) await refresh(); await NOTES.render(v); }
    else if (VIEW === "skeleton") { if (!DASH) await refresh(); v.innerHTML = await views.skeleton(); bindSkeleton(); }
    else if (VIEW === "bank") { HALL = 'shizhan'; return go('train'); }   // 试炼塔并进了修炼殿
    else if (VIEW === "wrong") {
      await refresh(); v.innerHTML = await views.wrong();
      const k = $("#killGo");
      if (k) k.onclick = () => (DASH?.plan?.tasks || []).some((t) => t.id === "wrong:daily")
        ? startTask({ task_id: "wrong:daily" })
        : startTask({ task: { type: "wrong", board: "", target: "", title: `👹 ${W("kill")}` } });
    }
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
// 消息里的网页块：文字（夹着的 ![[库内路径]] 是行内小图，如公式）、图片、成绩表
// 题目：去掉题干、问题、选项之间的空行；连着的 A/B/C/D 行排成选项格（layoutOpts 按最长选项决定一行放 4 个、2 个还是 1 个）
const OPT_RE = /^\s*-?\s*(?:\*\*)?([A-D])\s*[.．、](?:\*\*)?\s*(.*)$/;
function qTextHtml(text, inline) {
  const lines = String(text || "").split("\n").filter((l) => l.trim());
  const out = [];
  let buf = [], opts = [];
  const flushText = () => { if (buf.length) { out.push(`<div class="q-text">${inline(md(buf.join("\n")))}</div>`); buf = []; } };
  const flushOpts = () => {
    if (!opts.length) return;
    if (opts.length < 2 || opts[0][0] !== "A") { buf.push(...opts.map((o) => o[2])); opts = []; return; }   // 不像选项：当正文
    flushText();
    out.push(`<div class="opts">${opts.map(([k, v]) => `<div class="opt"><b>${k}.</b> ${inline(md(v))}</div>`).join("")}</div>`);
    opts = [];
  };
  for (const l of lines) {
    const m = l.match(OPT_RE);
    if (m && (!opts.length || m[1].charCodeAt(0) === opts[opts.length - 1][0].charCodeAt(0) + 1)) { if (!opts.length) flushText(); opts.push([m[1], m[2], l]); }
    else { flushOpts(); buf.push(l); }
  }
  flushOpts(); flushText();
  return out.join("");
}
function layoutOpts(root = document) {
  root.querySelectorAll(".opts").forEach((el) => {
    const W = el.clientWidth;
    if (!W) return;
    el.classList.add("measure");
    const widest = Math.max(...[...el.children].map((c) => c.getBoundingClientRect().width));
    el.classList.remove("measure");
    const gap = 18;
    const cols = widest * 4 + gap * 3 <= W ? 4 : widest * 2 + gap <= W ? 2 : 1;
    el.style.gridTemplateColumns = `repeat(${cols}, minmax(0, 1fr))`;
  });
}
let OPT_T = null;
addEventListener("resize", () => { clearTimeout(OPT_T); OPT_T = setTimeout(() => layoutOpts(), 150); });
function blocksHtml(list, trim = false, question = false) {
  const inline = (h) => h.replace(/!\[\[([^\]]+)\]\]/g, (_, p) => `<img class="inline-img" src="/vault-file?p=${encodeURIComponent(p.replace(/&amp;/g, '&'))}">`);
  const table = (b) => `<div class="tbl-wrap"><table class="result-table"><thead><tr>${b.head.map(h => `<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${
    b.rows.map(r => `<tr class="${r.includes('✗') ? 'bad' : r.includes('✓') ? 'good' : 'sum'}">${r.map(c => `<td>${esc(c)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  return (list || []).map((b) => b.t === "img" ? `<img src="/vault-file?p=${encodeURIComponent(b.v)}${trim ? "&trim=1" : ""}">` : b.t === "table" ? table(b)
    : question ? qTextHtml(b.v, inline) : `<div>${inline(md(b.v))}</div>`).join("");
}
function msgHtml(m) {
  const blocks = blocksHtml(m.blocks, false, !!m.pin);
  if (m.fold) return `<details class="fold"><summary>${esc(m.fold)}</summary><div>${md(m.text)}</div></details>`;
  if (m.who === "npc") return `<div class="npc">${tutorFace()}<div class="say"><div class="who">${esc(DASH?.persona?.tutor || "导师")}</div>${md(m.text)}</div></div>`;
  if (m.who === "me") return `<div class="msg me">${esc(m.text)}</div>`;
  if (m.pin) return `<div class="q-pin ${PIN_MINI ? "mini" : ""}"><div class="msg sys pin-body"><span class="pin-tools">${m.material?.length
      ? `<button class="pin-btn mat-btn ${MAT_OPEN ? "on" : ""}" title="材料放在左边，对照着看">📄 ${MAT_OPEN ? "收起材料" : "弹出材料"}</button>` : ""}<button class="pin-btn pin-fold" title="${PIN_MINI ? "展开题目" : "把题目收成一行"}">📌 ${PIN_MINI ? "展开" : "收起"}</button></span>${md(m.text)}${blocks}</div>
      <div class="pin-drag" title="按住上下拖：调题目框和下面解析各占多少"></div></div>`;
  return `<div class="msg sys">${md(m.text)}${blocks}</div>`;
}
// 题目钉在对话框顶上（往下翻解析时不动）；📌 收成一行 / 展开，每台设备记住
let PIN_MINI = (() => { try { return localStorage.getItem("xrpg-pin-mini") === "1"; } catch (e) { return false; } })();
// 资料分析 / 一拖五：材料放在对话框左边（像粉笔的“弹出材料”），题目和解析在右边；默认弹出，收起后每台设备记住
let MAT_OPEN = (() => { try { return localStorage.getItem("xrpg-mat-open") !== "0"; } catch (e) { return true; } })();
function currentMaterial() {
  for (let i = T.msgs.length - 1; i >= 0; i--) if (T.msgs[i].material?.length) return T.msgs[i].material;
  return null;
}
function materialPane() {
  const mat = currentMaterial();
  if (!mat || !MAT_OPEN) return "";
  return `<div class="mat-pane"><div class="mat-head"><b>📄 材料</b><span class="small faint" style="margin-left:8px">点图片放大</span><span class="spacer"></span><button class="ghost small mat-btn">收起材料</button></div>${blocksHtml(mat, true)}</div>`;
}
// 材料里的图：点一下全屏看（再点 / Esc / 返回键关）
function zoomImg(src) {
  const el = document.createElement("div");
  el.className = "img-zoom";
  el.innerHTML = `<img src="${src}"><span class="small">点任意处关闭</span>`;
  const close = () => { el.remove(); document.removeEventListener("keydown", key); };
  const key = (e) => { if (e.key === "Escape") close(); };
  el.onclick = close;
  document.addEventListener("keydown", key);
  document.body.appendChild(el);
}
// 草稿笔记按题存（web/draw.js）：做题 / 复盘时是屏幕上这道题，别的页面按页面
window.DRAW_KEY = () => {
  if (window.CARDS && CARDS.drawKey()) return CARDS.drawKey();      // 温简：每张卡一份草稿
  if (VIEW === "train" && T.session) for (let i = T.msgs.length - 1; i >= 0; i--) if (T.msgs[i].qkey) return T.msgs[i].qkey;
  return "page:" + VIEW;
};
// 资料分析 / 一拖五：左边材料上的笔记按这段材料存（同一组几道题共用）；材料收起时不算
window.DRAW_MKEY = () => {
  if (VIEW !== "train" || !MAT_OPEN) return "";
  const mat = currentMaterial();
  if (!mat) return "";
  const t = JSON.stringify(mat);
  let h = 5381;
  for (let i = 0; i < t.length; i++) h = ((h * 33) ^ t.charCodeAt(i)) >>> 0;
  return "mat:" + h.toString(36) + ":" + t.length;
};
window.DRAW_IN_MAT = (x, y) => {
  const p = document.querySelector(".mat-pane");
  if (!p) return false;
  const r = p.getBoundingClientRect();
  return x >= r.left && x <= r.right && y >= r.top && y <= r.bottom;
};
// 题目框和下面解析之间的分隔条：按住上下拖，题目框高度记在这台设备（占屏幕高度的百分比）
let PIN_H = (() => { try { return Number(localStorage.getItem("xrpg-pin-h")) || 0; } catch (e) { return 0; } })();
function applyPinH() { document.documentElement.style.setProperty("--pin-h", PIN_H ? PIN_H + "vh" : "46vh"); }
applyPinH();
function bindPinDrag() {
  document.querySelectorAll(".q-pin .pin-drag").forEach((h) => (h.onpointerdown = (e) => {
    const pin = h.closest(".q-pin"), box = $("#msgs");
    if (!pin || !box) return;
    e.preventDefault();
    h.setPointerCapture(e.pointerId);
    pin.classList.add("dragging");
    const y0 = e.clientY, h0 = pin.getBoundingClientRect().height, maxH = box.clientHeight - 60;
    const mv = (ev) => {
      const px = Math.max(70, Math.min(maxH, h0 + ev.clientY - y0));
      PIN_H = Math.round(px / innerHeight * 1000) / 10;
      applyPinH();
    };
    const upf = () => {
      h.removeEventListener("pointermove", mv); h.removeEventListener("pointerup", upf); h.removeEventListener("pointercancel", upf);
      pin.classList.remove("dragging");
      try { localStorage.setItem("xrpg-pin-h", String(PIN_H)); } catch (err) { /* 只管这一次 */ }
    };
    h.addEventListener("pointermove", mv); h.addEventListener("pointerup", upf); h.addEventListener("pointercancel", upf);
  }));
  bindPinReset();
}
function bindPinReset() {   // 双击分隔条：恢复默认高度
  document.querySelectorAll(".q-pin .pin-drag").forEach((h) => (h.ondblclick = () => {
    PIN_H = 0; applyPinH();
    try { localStorage.removeItem("xrpg-pin-h"); } catch (err) { /* 只管这一次 */ }
  }));
}
function bindPins() {
  layoutOpts();
  bindPinDrag();
  if (window.DRAW) DRAW.refresh();
  document.querySelectorAll(".mat-pane img:not(.inline-img), .q-pin img:not(.inline-img)").forEach((im) => (im.onclick = () => zoomImg(im.src)));
  document.querySelectorAll(".mat-btn").forEach((b) => (b.onclick = (e) => {
    e.stopPropagation();
    MAT_OPEN = !MAT_OPEN;
    try { localStorage.setItem("xrpg-mat-open", MAT_OPEN ? "1" : "0"); } catch (err) { /* 只管这一次 */ }
    const keep = $("#msgs")?.scrollTop || 0;
    renderTrain().then(() => { const m = $("#msgs"); if (m) m.scrollTop = keep; });
  }));
  document.querySelectorAll(".q-pin .pin-fold").forEach((b) => (b.onclick = (e) => {
    e.stopPropagation();
    PIN_MINI = !PIN_MINI;
    try { localStorage.setItem("xrpg-pin-mini", PIN_MINI ? "1" : "0"); } catch (err) { /* 只管这一次 */ }
    document.querySelectorAll(".q-pin").forEach((q) => {
      q.classList.toggle("mini", PIN_MINI);
      const btn = q.querySelector(".pin-fold"); btn.textContent = "📌 " + (PIN_MINI ? "展开" : "收起"); btn.title = PIN_MINI ? "展开题目" : "把题目收成一行";
    });
  }));
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
    ${timeCard(d)}
    <div class="grid g5" style="margin-top:14px">
      <div class="stat"><div class="k">🔥 ${esc(W("streak"))}</div><div class="v">${d.streak.days} 天</div><div class="d">${esc(W("xp"))}加成 +${pct(d.streak.bonus)}%</div></div>
      <div class="stat"><div class="k">🪷 ${esc(W("dao"))}</div><div class="v ${d.dao.value < 60 ? "bad" : ""}">${d.dao.value} · ${esc(d.dao.label)}</div><div class="d">近 14 天修炼的稳定度</div></div>
      <div class="stat"><div class="k">🧵 ${esc(W("ideal"))}</div>${ideal}</div>
      <div class="stat"><div class="k">🗺 本轮进度</div><div class="v">${pct(F.progress)}%</div><div class="d">${F.days_left ? `按近 7 天速度还需 ${F.days_left} 天` : "修几天后给出预测"}</div></div>
      <div class="stat"><div class="k">🎯 预计 ${I.target_score} 分</div><div class="v">${I.eta || "—"}</div><div class="d">目标日 ${I.target}</div></div>
    </div>
    ${trib}
    ${boardTimeCard(d)}
    ${lectureCard(d)}
    ${practiceCard(d)}
    ${selfstudyCard(d)}
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

  async train() {
    const tasks = DASH?.plan?.tasks || [];
    const idle = () => !T.session && !T.msgs.length && !T.busy;
    if (idle()) {
      const hub = await hubHtml();
      if (idle()) return hub;   // 殿里的数据还没载完就点了功课：以功课对话框为准，不能被殿覆盖
    }
    const inp = T.input;
    let composer = "";
    if (T.busy) composer = `<div class="thinking">${esc(DASH?.persona?.tutor || "导师")}正在判定</div>`;
    else if (inp.mode === "text" && inp.buttons) {
      // 复盘类（试炼复盘 / 大比复盘 / 题后讨论）：打字框默认收起，点左下角「师傅求助」才打开，题目区域更大
      composer = `${ASK_OPEN ? `<textarea id="answer" placeholder="${esc(inp.placeholder || "")}"></textarea>` : ""}
        <div class="row composer-row" style="margin-top:${ASK_OPEN ? 8 : 0}px"><button class="${ASK_OPEN ? "" : "ghost"} ask-btn" id="askToggle">🙋 ${ASK_OPEN ? "收起" : "师傅求助"}</button>${ASK_OPEN ? `<button class="primary" id="send">问师傅</button>` : ""}<span class="spacer"></span>
        ${inp.buttons.map((b) => `<button class="ghost" data-act="${esc(b.id)}">${esc(b.label)}</button>`).join("")}</div>`;
    }
    else if (inp.mode === "text") composer = `<textarea id="answer" placeholder="${esc(inp.placeholder || "")}"></textarea>
        <div class="row" style="margin-top:8px"><span class="spacer"></span>
        <button class="ghost" data-act="${["bank", "bank_review"].includes(T_TYPE) ? "bank_pause" : "skip"}">${["bank", "bank_review"].includes(T_TYPE) ? "保存并暂停" : "跳过"}</button><button class="primary" id="send">提交</button></div>`;
    else if (inp.mode === "buttons") composer = `<div class="row">${inp.buttons.map((b) => `<button class="${b.id === "skip" ? "ghost" : "primary"}" data-act="${esc(b.id)}">${esc(b.label)}</button>`).join("")}</div>`;
    else if (T.finished && T_TYPE === "mock_review") composer = `<div class="row"><button class="primary" id="backContest">回${esc(NAV("contest"))}</button><button class="ghost" id="backHome">回修炼殿</button></div>`;
    else if (T.finished) composer = `<div class="row"><button class="primary" id="nextTask">下一项功课</button><button class="ghost" id="backHome">回修炼殿</button></div>`;
    return `<div class="train">
      <div class="card"><h3>📜 师尊荐课</h3>${tasks.map(taskRow).join("")}<button class="ghost small" id="toHall" style="margin-top:8px">↩ 回修炼殿</button></div>
      <div class="card chat ${MAT_OPEN && currentMaterial() ? "with-mat" : ""}">${sessionHead()}${materialPane()}<div class="msgs" id="msgs">${T.msgs.map(msgHtml).join("")}</div>
        <div class="composer">${composer}</div></div></div>`;
  },

  async skeleton() {
    const tabs = `<div class="lib-head"><h2>${esc(NAV('skeleton'))}</h2><div class="lib-tabs">
      <button class="${LIB.tab === 'gongfa' ? 'on' : ''}" data-libtab="gongfa">📜 功法</button>
      <button class="${LIB.tab === 'yujian' ? 'on' : ''}" data-libtab="yujian">📖 经卷 · 题库</button>
      <button class="${LIB.tab === 'idioms' ? 'on' : ''}" data-libtab="idioms">📗 成语实词录</button></div></div>`;
    if (LIB.tab === 'idioms') return tabs + `<div class="id-root">${await IDIOMS.render()}</div>`;
    if (LIB.tab === 'yujian') return tabs + await yujianHtml() + importCardHtml();
    const sk = await api("/api/skeletons");
    if (LIB.open) {
      const b = sk.boards.find(x => x.board === LIB.open);
      if (b) return tabs + `<div class="row"><button class="ghost" id="tomeBack">← 回到书架</button></div>` + skeletonCard(sk, b);
      LIB.open = null;
    }
    // 书架：每部功法一卷漂浮的古籍，点开看大项
    const hues = [28, 200, 340, 150, 260, 45, 180, 10, 300, 90, 220, 120];
    return tabs + `<p class="small muted lib-tip">每部功法是一卷古籍，点开研读其中的大项（口诀、思路、举例与掌握程度）。</p><div class="tome-grid">${sk.boards.map((b, i) => {
      const st = b.final ? '已定稿' : b.status === '草稿' ? '草稿' : '未编撰';
      const got = b.items.filter(it => it.level > 0).length;
      return `<div class="tome-slot"><div class="tome" data-tome="${esc(b.board)}" style="--d:${(i % 6) * 0.8}s;--h:${hues[i % hues.length]}">
        <div class="tome-cover"><div class="tome-label">${vlabel(b.board)}</div><div class="tome-seal">${st}</div></div></div>
        <div class="tome-cap">${b.items.length ? `${b.items.length} 大项 · 入门 ${got}` : esc(st)}</div></div>`;
    }).join('')}</div>`;
  },

  async wrong() {
    const w = await api("/api/wrong");
    const rows = w.boards.filter((b) => b.total).map((b) => `<tr><td>${esc(b.board)}</td><td>${b.total}</td><td>${b.new}</td><td style="color:var(--red)">${b.redo}</td><td style="color:var(--green)">${b.done}</td></tr>`).join("");
    const redo = w.redo.map((r) => { const [n, s, q] = r.key.split("|"); return `<tr><td>第${n}季 ${esc(s)} 第${q}题</td><td>${r.due || ""}</td><td>${r.streak || 0}</td><td>${r.tries}</td></tr>`; }).join("");
    const demon = (DASH?.demon || []).map((r, i) => `<tr><td>${i + 1}</td><td>${esc(r.board)}</td><td>${esc(r.name)}</td><td><b style="color:${i < 3 ? "var(--red)" : "inherit"}">${pct(r.acc)}%</b></td><td>${esc(r.grade_name)}</td></tr>`).join("");
    const daily = (DASH?.plan?.tasks || []).find((t) => t.id === "wrong:daily");
    const left = w.boards.reduce((n, b) => n + b.new + b.redo, 0);
    const kill = `<div class="card kill-card"><div class="row"><h3 style="margin:0">⚔ ${esc(W("kill"))}</h3>
        <span class="small muted">和${esc(W("tasks"))}里的「${esc(W("kill"))}」是同一项，在哪斩都算进度</span></div>
      ${daily ? `${bar(Math.min(1, daily.hits.length / daily.quota), "red")}
        <div class="small">今日 <b>${Math.min(daily.hits.length, daily.quota)}/${daily.quota}</b> 只${daily.redo ? `（含${esc(W("redo"))} ${daily.redo}）` : ""}${daily.done ? " · ✅ 今日功课已完成，多斩不限" : ""}</div>`
        : `<div class="small muted">今日功课里没有排${esc(W("kill"))}，想斩也可以直接开斩。</div>`}
      <div class="row"><button class="primary" id="killGo" ${left || daily ? "" : "disabled"}>👹 ${daily && !daily.done ? "斩下一只" : "再斩一只"}</button>
        <span class="small muted">未交手 ${w.boards.reduce((n, b) => n + b.new, 0)} · 待${esc(W("redo"))} ${w.boards.reduce((n, b) => n + b.redo, 0)}</span></div></div>`;
    return kill + `<div class="card"><h3>👹 ${esc(W("demon_rank"))} <small>按最近几季模考正确率从低到高：排在前面的就是你最大的${esc(W("wrong"))}</small></h3>
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
    const boards = d.tree.map((t) => t.board).concat(d.side.map((s) => s.board));
    const opts = boardOptions(boards);
    return `<div class="card hongchen"><h3>📥 好题收进题库经卷 <small>纸质资料、其他 App 上碰到的好题收进来；做题记录在${esc(NAV("home"))}的「${esc(W("practice_title"))}」里记</small></h3>
      <div class="hc-grid">
        <div>
          <div class="row"><select id="aqBoard" style="flex:1">${opts}</select><input id="aqTopic" placeholder="知识点，如 削弱-他因" style="flex:1.4"><input id="aqSrc" placeholder="出处（可空）" style="flex:1.2"></div>
          <textarea id="aqStem" rows="4" placeholder="题干" style="margin-top:6px;width:100%"></textarea>
          ${"ABCD".split("").map((k) => `<div class="row aq-opt"><b>${k}</b><input id="aq${k}" placeholder="选项 ${k}" style="flex:1"></div>`).join("")}
          <div class="row" style="margin-top:6px"><label class="small">答案 <select id="aqAns"><option value="">待补</option><option>A</option><option>B</option><option>C</option><option>D</option></select></label></div>
          <textarea id="aqAna" rows="4" placeholder="解析（可空，以后让师傅解惑补上）" style="margin-top:6px;width:100%"></textarea>
          <div class="row" style="margin-top:6px"><button class="primary" id="aqBtn">收进题库</button><span class="small muted">追加到 训练/题库/&lt;板块&gt;真题.md，编号 自练-日期-序号；之后试炼、知识点试炼、经卷搜索都能用</span></div>
        </div>
      </div></div>
    <div class="grid g2">
      <div class="card"><h3>⚔ 记录${esc(W("boss"))}（模考成绩）</h3>
        <div class="row"><input id="bossName" placeholder="名称，如 第37季" style="flex:2"><input id="bossScore" placeholder="分数" style="flex:1"></div>
        <div class="row" style="margin-top:8px"><button class="primary" id="bossBtn">记录</button><span class="small muted">最近两次的较低分若高于当前${esc(W("score"))}，${esc(W("xp"))}直接补上；达到下一道${esc(W("tribulation"))}线得突破丹</span></div></div>
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
    const cp = chatPrefs();
    return (await DEVICE.html()) + AMB.settingsHtml() + `<div class="card"><h3>🪟 对话框大小与字体 <small>做功课时的对话框；只存在这台设备里（电脑、平板各调各的）</small></h3>
      <div class="row"><label style="flex:1">宽度 <b id="cwV">${cp.w}%</b><input type="range" id="cwR" min="40" max="100" step="5" value="${cp.w}" style="width:100%"></label>
        <label style="flex:1">高度 <b id="chV">${cp.h}%</b><input type="range" id="chR" min="40" max="100" step="5" value="${cp.h}" style="width:100%"></label></div>
      <div class="row"><label style="flex:1">对话框字体 <b id="cfV">${cp.fs}%</b><input type="range" id="cfR" min="80" max="160" step="5" value="${cp.fs}" style="width:100%"></label>
        <div style="flex:1" class="small muted" id="cfDemo">示例：<span style="font-size:calc(15px * ${cp.fs / 100})">人民是历史的创造者，人民是真正的英雄。</span></div></div>
      <div class="row"><label style="display:inline-flex;align-items:center;gap:6px"><input type="checkbox" id="csideR" style="width:auto" ${cp.side ? "checked" : ""}> 左边显示“师尊荐课”栏</label><span class="spacer"></span>
        <button class="ghost small" id="cResetR">恢复默认（宽 80%、高 100%、字体 110%）</button></div>
      <p class="small muted">高度 100% = 从顶栏下面一直到屏幕底；对话框底边总是贴着屏幕底。改了马上生效，下次做功课就是这个大小。</p></div>
      <div class="card"><h3>🎨 风格</h3>
      <div class="row"><button class="${cur === "修仙" ? "primary" : ""}" data-style="修仙">☯ 东方修仙（师尊 劭神韵）</button>
      <button class="${cur === "玄幻" ? "primary" : ""}" data-style="玄幻">⚔ 西方玄幻（艾琳学姐）</button></div>
      <p class="small muted">两种风格共用同一份进度，只换名字、导师、配色和台词。两台电脑同步。</p></div>
      <div class="card"><h3>本机设置 <small>保存在本机 ~/.xingce-rpg/settings.json，不会同步、不会上传</small></h3>
      <label class="small muted">行测库路径（含 copilot/skills 的文件夹；程序放在库里时会自动找到）</label>
      <input id="sVault" value="${esc(s.vault_setting)}" placeholder="${esc(s.vault || "例如 C:\\Users\\你\\Desktop\\行测obsidian\\行测")}">
      <div class="small faint">当前使用：${esc(s.vault || "未找到")}</div><br>
      <div class="ai-switch"><b>🤖 当前 AI</b>
        <select id="sProf">${(s.ai_profiles || []).map(p => `<option value="${esc(p.name)}" ${p.name === s.ai_active ? "selected" : ""}>${esc(p.name)} · ${esc(p.model)}</option>`).join("")}
          ${s.ai_active && (s.ai_profiles || []).some(p => p.name === s.ai_active) ? "" : `<option value="" selected>（当前设置：${esc(s.model)}，还没存成方案）</option>`}</select>
        <button class="small" id="sProfSave" title="把下面这套 接口地址 + 模型 + key 存成一套，起个名字">💾 存为一套</button>
        ${(s.ai_profiles || []).length ? '<button class="small ghost" id="sProfDel" title="删掉下拉里选中的这套">🗑</button>' : ""}</div>
      <p class="small muted" style="margin-top:2px">常用的几套（DeepSeek、通义千问、Kimi、智谱…）各存一套，下拉一选就换；导师、师傅解惑、师傅讲讲、师傅制卡都跟着换。新加一套：下面「常用接口」选一个、填 key 和模型 → 保存 → 「存为一套」。</p>
      <label class="small muted">AI 的 API key ${s.has_key ? `（已填写，末尾 ${esc(s.key_tail)}；不改就留空）` : ""}</label>
      <input id="sKey" type="password" placeholder="sk-……">
      <div class="row" style="margin-top:8px">
        <div style="flex:2"><label class="small muted">接口地址 <select id="sPreset" class="ai-preset"><option value="">常用接口…</option>${AI_PRESETS.map((p, i) => `<option value="${i}">${esc(p[0])}</option>`).join("")}</select></label><input id="sBase" value="${esc(s.base_url)}"></div>
        <div style="flex:1"><label class="small muted">模型</label><input id="sModel" value="${esc(s.model)}"></div></div>
      <details class="sv-vision" style="margin-top:10px"${s.vision_model ? " open" : ""}><summary class="small">🪶 识图模型（师傅制卡读扫描版 PDF 用，可不填）</summary>
      <p class="small muted">填一个能看图的模型（如 qwen-vl-max、gpt-4o、glm-4v）：「🧙 师傅制卡」遇到扫描版 PDF（页面是图片）时让它看图认字。接口地址、key 和上面一样时留空。</p>
      <div class="row">
        <div style="flex:1"><label class="small muted">识图模型</label><input id="sVModel" value="${esc(s.vision_model || "")}" placeholder="如 qwen-vl-max"></div>
        <div style="flex:2"><label class="small muted">接口地址（留空 = 同上）</label><input id="sVBase" value="${esc(s.vision_base_url || "")}" placeholder="${esc(s.base_url)}"></div></div>
      <label class="small muted">识图 API key ${s.vision_has_key ? "（已单独填写；不改就留空）" : "（留空 = 用上面的 key）"}</label>
      <input id="sVKey" type="password" placeholder="sk-……"></details>
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

// 设置里「常用接口」：[名字, 接口地址, 默认模型]（都是 OpenAI 兼容接口；模型名可以自己改）
const AI_PRESETS = [
  ["DeepSeek", "https://api.deepseek.com", "deepseek-chat"],
  ["DeepSeek（深度思考）", "https://api.deepseek.com", "deepseek-reasoner"],
  ["通义千问（阿里百炼）", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus"],
  ["Kimi（月之暗面）", "https://api.moonshot.cn/v1", ""],
  ["智谱 GLM", "https://open.bigmodel.cn/api/paas/v4", "glm-4-flash"],
  ["硅基流动", "https://api.siliconflow.cn/v1", ""],
  ["OpenAI", "https://api.openai.com/v1", ""],
];

// ------------------------------------------------------------ 交互绑定
function bindTaskClicks(root) {
  root.querySelectorAll("[data-task]").forEach((el) => (el.onclick = () => el.dataset.task === "cards:all" && window.CARDS
    ? (VIEW === "train" ? CARDS.review("") : (HALL = "xiulian", go("train"), setTimeout(() => CARDS.review(""), 300)))
    : startTask({ task_id: el.dataset.task })));
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
  const lec7 = (d.lectures || []).reduce((a, x) => a + x.minutes, 0);
  const days = lastDays();
  const allBoards = d.tree.map((t) => t.board).concat(d.side.map((s) => s.board));
  const rows = (d.lectures || []).map((x) => `<div class="lec-row"><span class="faint">${esc(x.d.slice(5))}</span><b>${x.minutes} 分钟</b>
      <span class="muted">${esc(x.note || "")}</span><span class="spacer"></span>
      <select class="lec-board" data-lec-board="${esc(x.id)}" title="这笔听道算哪个模块${x.board ? "" : x.board_auto ? "（从“讲的什么”里认的）" : ""}">
        <option value="">不分模块</option>${allBoards.map((b) => `<option ${b === (x.board || x.board_auto) ? "selected" : ""}>${esc(b)}</option>`).join("")}</select>
      ${!x.board && x.board_auto ? '<span class="faint small">自动</span>' : ""}<button class="ghost small" data-lec-del="${esc(x.id)}" title="记错了，删掉这笔">删</button></div>`).join("");
  return `<div class="card lecture-card tone-lecture" style="margin-top:14px">
    <h3>📿 ${esc(W("lecture_title"))} <small>今日${esc(W("lecture"))} ${m.lecture ?? 0} 分钟 · 近 7 天 ${lec7} 分钟</small></h3>
    <div title="今日${esc(W("lecture"))} ${m.lecture ?? 0} 分钟（占每日目标 ${goal} 分钟）">${sancaiBar({ lecture: m.lecture ?? 0 }, goal, ["lecture"])}</div>
    <p class="small muted">${esc(W("lecture_hint"))}</p>
    <div class="row lec-form">
      <label>${esc(W("lecture"))}几分钟 <input type="number" id="lecMin" min="1" max="600" placeholder="如 90"></label>
      <span class="lec-quick">${[30, 60, 90, 120].map((n) => `<button class="ghost small" data-lec-q="${n}">${n}</button>`).join("")}</span>
      <label>模块（可不选） <select id="lecBoard"><option value="">不分模块</option>${boardOptions(d.tree.map((t) => t.board).concat(d.side.map((s) => s.board)))}</select></label>
      <label style="flex:2">讲的什么（可不填） <input id="lecNote" maxlength="40" placeholder="如：粉笔 判断推理 第3讲"></label>
      <label>哪天 <select id="lecDay">${days.map((ds, k) => `<option value="${ds}">${dayName(ds, k)}</option>`).join("")}</select></label>
      <button class="primary" id="lecGo">📿 记入</button></div>
    <details class="fold" style="margin-top:8px"><summary>近 7 天${esc(W("lecture"))}记录 <span class="muted small">· ${(d.lectures || []).length} 次 · ${lec7} 分钟</span></summary>${rows || `<div class="muted small">近 7 天还没有${esc(W("lecture"))}记录</div>`}</details>
  </div>`;
}
// ------------------------------------------------------------ 三才时辰：听课 / 做题 / 复习，以听课为 1 看比例
let TIME_SPAN = (() => { try { return localStorage.getItem("timeSpan") || "today"; } catch { return "today"; } })();
function hm(m) { m = Math.round(m || 0); return m >= 60 ? `<b>${Math.floor(m / 60)}</b><i>时</i>${m % 60 ? `<b>${m % 60}</b><i>分</i>` : ""}` : `<b>${m}</b><i>分</i>`; }
function timeCard(d) {
  const ts = d.timesplit; if (!ts) return "";
  const t = ts[TIME_SPAN] || ts.today;
  const total = t.lecture + t.practice + t.review;
  const orbs = [
    ["lecture", "闻", "听课", "闻法", `网课、讲座（${W("lecture")}）`],
    ["practice", "历", "做题", "历练", `试炼、${W("kill")}、试剑、炼丹${t.self ? ` · 自练 ${t.self} 分` : " · 含自练"}`],
    ["review", "温", "复习", "温养", `传授、背诵口诀、论道、温养${t.self_review ? ` · ${W("selfstudy")} ${t.self_review} 分` : ` · 含${W("selfstudy")}`}`],
  ].map(([k, seal, name, alias, hint]) => {
    const share = total ? t[k] / total : 0;
    return `<div class="orb orb-${k}" style="--share:${(share * 360).toFixed(1)}deg">
      <div class="orb-ring"><div class="orb-core">
        <div class="orb-seal">${seal}</div>
        <div class="orb-name">${name}<small>${alias}</small></div>
        <div class="orb-num">${hm(t[k])}</div>
        <div class="orb-pct">${total ? Math.round(share * 100) + "%" : "—"}</div>
      </div></div>
      <div class="orb-hint">${esc(hint)}</div></div>`;
  }).join("");
  const base = t.lecture;
  const ratio = (v) => base ? (v / base).toFixed(v / base >= 10 ? 0 : 1).replace(/\.0$/, "") : "—";
  const seg = (k, v) => total ? `<span class="seg seg-${k}" style="flex:${v || 0}" title="${v} 分钟"></span>` : "";
  const ratioLine = base
    ? `听课 <b>1</b> <em>:</em> 做题 <b>${ratio(t.practice)}</b> <em>:</em> 复习 <b>${ratio(t.review)}</b>`
    : `<span class="muted">${total ? "这段时间还没听课，比例以听课为 1，暂时算不出来" : "这段时间还没有记录"}</span>`;
  // 刻度：每一格是一份“听课时长”
  const units = base && total ? Math.min(40, Math.round(total / base)) : 0;
  const ticks = units > 1 ? Array.from({ length: units - 1 }, (_, i) => `<span style="left:${((i + 1) * base / total * 100).toFixed(2)}%"></span>`).join("") : "";
  return `<div class="card sancai" style="margin-top:14px">
    <div class="sancai-head"><h3>☯ 三才时辰 <small>听课 · 做题 · 复习</small></h3><span class="spacer"></span>
      <div class="sancai-tabs">${[["today", "今日"], ["week", "近七日"], ["all", "累计"]].map(([k, n]) => `<a data-tspan="${k}" class="${k === TIME_SPAN ? "on" : ""}">${n}</a>`).join("")}</div></div>
    <div class="orbs">${orbs}</div>
    <div class="ratio">
      <div class="ratio-line">${ratioLine}<span class="spacer"></span><span class="faint small">共 ${Math.round(total)} 分钟 · 以听课为 1</span></div>
      <div class="ratio-bar">${seg("lecture", t.lecture)}${seg("practice", t.practice)}${seg("review", t.review)}<div class="ticks">${ticks}</div></div>
    </div></div>`;
}
function bindTimeCard() {
  document.querySelectorAll("[data-tspan]").forEach((a) => (a.onclick = () => {
    TIME_SPAN = a.dataset.tspan;
    try { localStorage.setItem("timeSpan", TIME_SPAN); } catch {}
    const el = document.querySelector(".sancai");
    if (el) { el.outerHTML = timeCard(DASH); bindTimeCard(); }
  }));
}
// ------------------------------------------------------------ 十二经：各模块的时辰（同三才法印，一排四枚，每个模块一种颜色）
const BOARD_COLORS = ["#c2463a", "#d9822b", "#c9a227", "#6e9f3a", "#2e9d6b", "#b03a5b", "#3f9e8f", "#2f7fb8", "#5b5fc7", "#8a4fbf", "#b85fa6", "#8c6d46"];
let BOARD_SPAN = (() => { try { return localStorage.getItem("boardSpan") || "week"; } catch { return "week"; } })();
function boardTimeCard(d) {
  const bt = d.boardtime; if (!bt) return "";
  const cur = bt[BOARD_SPAN] || bt.week, list = cur.boards;
  const total = list.reduce((a, b) => a + b.total, 0);
  const top = Math.max(1, ...list.map((b) => b.total));
  const orbs = list.map((b, i) => {
    const share = total ? b.total / total : 0;
    return `<div class="orb mini" style="--c:${BOARD_COLORS[i % BOARD_COLORS.length]};--share:${(share * 360).toFixed(1)}deg">
      <div class="orb-ring"><div class="orb-core">
        <div class="orb-seal">${esc(b.board.slice(0, 1))}</div>
        <div class="orb-name">${esc(b.board)}</div>
        <div class="orb-num">${hm(b.total)}</div>
        <div class="orb-pct">${total ? Math.round(share * 100) + "%" : "—"}${b.total === top && total ? " · 最勤" : ""}</div>
      </div></div>
      <div class="orb-split"><span class="l" title="听课">听 ${b.lecture}</span><span class="p" title="做题（含自练）">题 ${b.practice}</span><span class="r" title="复习">复 ${b.review}</span></div></div>`;
  }).join("");
  return `<div class="card sancai shier" style="margin-top:14px">
    <div class="sancai-head"><h3>☸ 十二经 · 各模块时辰 <small>听课（记听道时选了模块的）· 做题（含自练）· 复习，单位分钟</small></h3><span class="spacer"></span>
      <div class="sancai-tabs">${[["today", "今日"], ["week", "近七日"], ["all", "累计"]].map(([k, n]) => `<a data-bspan="${k}" class="${k === BOARD_SPAN ? "on" : ""}">${n}</a>`).join("")}</div></div>
    <div class="orbs orbs4">${orbs}</div>
    <p class="small muted" style="margin:6px 0 0">共 ${Math.round(total)} 分钟${cur.loose ? `，另有 ${cur.loose} 分钟认不出模块（三才时辰里照算）` : ""}。修炼时间按当时在练的模块记；早先没记模块的，按那天修炼记录里各模块练了几次分摊。听道没选模块的，从“讲的什么”里认（写了“图形推理”“图推”“资料”等），认错了在近 7 天听道记录里改。</p></div>`;
}
function bindBoardTime() {
  document.querySelectorAll("[data-bspan]").forEach((a) => (a.onclick = () => {
    BOARD_SPAN = a.dataset.bspan;
    try { localStorage.setItem("boardSpan", BOARD_SPAN); } catch {}
    const el = document.querySelector(".shier");
    if (el) { el.outerHTML = boardTimeCard(DASH); bindBoardTime(); }
  }));
}
// ------------------------------------------------------------ 演武 · 历练记：首页记自己做题（好题收进题库在修仙录）
function lastDays() {
  return [0, 1, 2, 3, 4, 5, 6].map((k) => { const t = new Date(Date.now() - k * 864e5); return t.getFullYear() + "-" + String(t.getMonth() + 1).padStart(2, "0") + "-" + String(t.getDate()).padStart(2, "0"); });
}
function dayName(ds, k) { return k === 0 ? "今天" : k === 1 ? "昨天" : k === 2 ? "前天" : ds.slice(5); }
// 三才时辰的颜色条：做题（朱）· 复习（金）· 听课（青），按每日目标算宽度；only 只画其中几段
function sancaiBar(t, goal, only) {
  const keys = only || ["practice", "review", "lecture"];
  let used = 0;
  return `<div class="tri-bar">${keys.map((k) => {
    const w = Math.max(0, Math.min(100 - used, (t[k] || 0) / goal * 100)); used += w;
    return w ? `<span class="seg-${k}" style="width:${w}%"></span>` : "";
  }).join("")}</div>`;
}
function practiceCard(d) {
  const boards = d.tree.map((t) => t.board).concat(d.side.map((s) => s.board));
  const goal = d.minutes.goal || 300, t = d.timesplit?.today || { practice: 0, self: 0 };
  const list = d.practice || [];
  const today = list.filter((p) => p.d === d.today);
  const sum = (xs, k) => xs.reduce((a, p) => a + (p[k] || 0), 0);
  const rate = (ok, n) => n ? Math.round(ok / n * 100) + "%" : "—";
  const n = sum(today, "total"), ok = sum(today, "correct");
  const wn = sum(list, "total"), wok = sum(list, "correct"), wmin = sum(list, "minutes");
  const days = lastDays();
  const rows = list.map((x) => {
    const r = x.total ? x.correct / x.total : null;
    const pace = x.total && x.minutes ? `${(x.minutes * 60 / x.total).toFixed(0)} 秒/题` : "";
    return `<div class="lec-row pr-row"><span class="faint">${esc(x.d.slice(5))}</span><b>${esc(x.board)}</b>
      ${x.total ? `<span>${x.correct}/${x.total} 题</span><span class="pr-rate ${r >= 0.8 ? "good" : r < 0.6 ? "bad" : ""}">正确率 ${rate(x.correct, x.total)}</span>` : `<span class="muted">只记心得</span>`}
      ${x.minutes ? `<span>${x.minutes} 分钟</span>` : ""}${pace ? `<span class="muted">${pace}</span>` : ""}
      ${x.source ? `<span class="muted">· ${esc(x.source)}</span>` : ""}<span class="spacer"></span>${x.id ? `<button class="ghost small" data-pr-del="${esc(x.id)}" title="记错了，删掉这笔">删</button>` : ""}</div>
      ${x.note ? `<div class="pr-note">${esc(x.note)}</div>` : ""}`;
  }).join("");
  return `<div class="card lecture-card tone-practice" style="margin-top:14px">
    <h3>⚔ ${esc(W("practice_title"))} <small>今日做题 ${t.practice} 分钟 · 其中自练 ${t.self} 分钟${n ? ` · ${ok}/${n} 题 · 正确率 ${rate(ok, n)}` : ""}</small></h3>
    ${sancaiBar({ practice: t.self, drill: t.practice - t.self }, goal, ["practice", "drill"])}
    <p class="small muted">纸质资料、其他 App 上自己刷题，也是演武。练完来此记一笔：分钟算进「做题」，心得写进 训练/演武录/${esc((d.today || "").slice(0, 7))}.md。</p>
    <div class="row lec-form">
      <label>板块 <select id="prBoard">${boardOptions(boards)}<option>其他</option></select></label>
      <label>题数 <input type="number" id="prTotal" min="0" placeholder="如 20"></label>
      <label>对了几题 <input type="number" id="prOk" min="0" placeholder="如 16"></label>
      <label>几分钟 <input type="number" id="prMin" min="0" placeholder="如 40"></label>
      <label style="flex:1">资料（可不填） <input id="prSrc" maxlength="60" placeholder="如：粉笔980 P120"></label>
      <label style="flex:2">心得（可不填） <input id="prNote" maxlength="500" placeholder="错在哪、悟到了什么；只写心得题数留空"></label>
      <label>哪天 <select id="prDay">${days.map((ds, k) => `<option value="${ds}">${dayName(ds, k)}</option>`).join("")}</select></label>
      <button class="primary" id="prBtn">⚔ 记入</button></div>
    <details class="fold" style="margin-top:8px"><summary>近 7 天${esc(W("practice"))}记录 <span class="muted small">· ${list.length} 次 · ${wn} 题 · 正确率 ${rate(wok, wn)} · ${wmin} 分钟</span></summary>${rows || `<div class="muted small">近 7 天还没有${esc(W("practice"))}记录：记一笔就会出现在这里</div>`}</details>
  </div>`;
}
// ------------------------------------------------------------ 静修 · 温养记：首页记自己复习（背口诀、看笔记、整理错题本……）
function selfstudyCard(d) {
  const boards = d.tree.map((t) => t.board).concat(d.side.map((s) => s.board));
  const goal = d.minutes.goal || 300, t = d.timesplit?.today || { review: 0, self_review: 0 };
  const list = d.selfstudy || [];
  const w7 = list.reduce((a, x) => a + x.minutes, 0);
  const days = lastDays();
  const rows = list.map((x) => `<div class="lec-row pr-row"><span class="faint">${esc(x.d.slice(5))}</span><b>${x.minutes} 分钟</b>
      ${x.board ? `<span class="tag">${esc(x.board)}</span>` : ""}<span>${esc(x.topic || "")}</span><span class="spacer"></span>
      <button class="ghost small" data-ss-del="${esc(x.id)}" title="记错了，删掉这笔">删</button></div>
      ${x.note ? `<div class="pr-note">${esc(x.note)}</div>` : ""}`).join("");
  return `<div class="card lecture-card tone-review" style="margin-top:14px">
    <h3>🪷 ${esc(W("selfstudy_title"))} <small>今日${esc(W("selfstudy"))} ${t.self_review || 0} 分钟 · 今日复习共 ${t.review} 分钟 · 近 7 天${esc(W("selfstudy"))} ${w7} 分钟</small></h3>
    ${sancaiBar({ review: t.self_review || 0, rdrill: Math.max(0, t.review - (t.self_review || 0)) }, goal, ["review", "rdrill"])}
    <p class="small muted">不在程序里、自己闭门复习（背口诀、看笔记、整理错题本、回看网课笔记……）也是温养。复习完来此记一笔：分钟算进「复习」，写进 训练/静修录/${esc((d.today || "").slice(0, 7))}.md。</p>
    <div class="row lec-form">
      <label>${esc(W("selfstudy"))}几分钟 <input type="number" id="ssMin" min="1" max="600" placeholder="如 60"></label>
      <span class="lec-quick">${[30, 60, 90].map((n) => `<button class="ghost small" data-ss-q="${n}">${n}</button>`).join("")}</span>
      <label>模块（可不选） <select id="ssBoard"><option value="">不分模块</option>${boardOptions(boards)}</select></label>
      <label style="flex:1.2">复习了什么（可不填） <input id="ssTopic" maxlength="60" placeholder="如：削弱题口诀、错题本"></label>
      <label style="flex:1.6">心得（可不填） <input id="ssNote" maxlength="500" placeholder="哪里还不熟、下次怎么练"></label>
      <label>哪天 <select id="ssDay">${days.map((ds, k) => `<option value="${ds}">${dayName(ds, k)}</option>`).join("")}</select></label>
      <button class="primary" id="ssBtn">🪷 记入</button></div>
    <details class="fold" style="margin-top:8px"><summary>近 7 天${esc(W("selfstudy"))}记录 <span class="muted small">· ${list.length} 次 · ${w7} 分钟</span></summary>${rows || `<div class="muted small">近 7 天还没有${esc(W("selfstudy"))}记录：记一笔就会出现在这里</div>`}</details>
  </div>`;
}
function bindSelfstudy() {
  const b = $("#ssBtn"); if (!b) return;
  document.querySelectorAll("[data-ss-q]").forEach((x) => (x.onclick = () => { $("#ssMin").value = x.dataset.ssQ; }));
  b.onclick = async () => {
    const minutes = Number($("#ssMin").value);
    if (!minutes) return toast(`先填${W("selfstudy")}了几分钟`);
    try {
      const s0 = SETTLE.snap(), day = $("#ssDay");
      const body = { minutes, board: $("#ssBoard").value, topic: $("#ssTopic").value.trim(), note: $("#ssNote").value.trim(), date: day.value };
      const r = await api("/api/selfstudy", body);
      handleEvents(r.events); await refresh(); render();
      SETTLE.show({ kind: "review", title: `${W("selfstudy")} ${minutes} 分钟`, sub: body.topic, before: s0,
        lines: [body.board, day.selectedIndex ? `补记 ${day.options[day.selectedIndex].text}` : ""].filter(Boolean) });
    } catch (e) { showError(e); }
  };
  document.querySelectorAll("[data-ss-del]").forEach((x) => (x.onclick = async () => {
    if (!confirm("删掉这笔记录？（那次的分钟和修为会扣回；静修录文件里的那段请在 Obsidian 里自己删）")) return;
    try { await api("/api/selfstudy/delete", { id: x.dataset.ssDel }); await refresh(); render(); } catch (e) { showError(e); }
  }));
}
function bindPractice() {
  const b = $("#prBtn"); if (!b) return;
  b.onclick = async () => {
    try {
      const s0 = SETTLE.snap();
      const body = { board: $("#prBoard").value, source: $("#prSrc").value, total: $("#prTotal").value, correct: $("#prOk").value,
                     minutes: $("#prMin").value, note: $("#prNote").value, date: $("#prDay").value };
      const r = await api("/api/practice", body);
      handleEvents(r.events); await refresh(); render();
      const n = Number(body.total) || 0, ok = Number(body.correct) || 0, m = Number(body.minutes) || 0;
      SETTLE.show({ kind: "practice", title: `${body.board} · 自练`, sub: body.source, before: s0,
        lines: [n ? `${ok}/${n} 题` : "", n ? `正确率 ${Math.round(ok / n * 100)}%` : "", m ? `${m} 分钟` : "", n && m ? `${Math.round(m * 60 / n)} 秒/题` : ""].filter(Boolean) });
    } catch (e) { showError(e); }
  };
  document.querySelectorAll("[data-pr-del]").forEach((x) => (x.onclick = async () => {
    if (!confirm("删掉这笔记录？（那次的分钟和修为会扣回；日志文件里的那段请在 Obsidian 里自己删）")) return;
    try { await api("/api/practice/delete", { id: x.dataset.prDel }); await refresh(); render(); } catch (e) { showError(e); }
  }));
}
function bindLecture() {
  const go = $("#lecGo"); if (!go) return;
  document.querySelectorAll("[data-lec-q]").forEach((b) => (b.onclick = () => { $("#lecMin").value = b.dataset.lecQ; }));
  go.onclick = async () => {
    const minutes = Number($("#lecMin").value);
    if (!minutes) return toast(`先填${W("lecture")}了几分钟`);
    try {
      const s0 = SETTLE.snap(), note = $("#lecNote").value.trim(), day = $("#lecDay");
      const lb = $("#lecBoard").value;
      const r = await api("/api/lecture", { minutes, note, date: day.value, board: lb });
      handleEvents(r.events); await refresh(); render();
      SETTLE.show({ kind: "lecture", title: `${W("lecture")} ${minutes} 分钟`, sub: note, before: s0,
        lines: [lb, day.selectedIndex ? `补记 ${day.options[day.selectedIndex].text}` : ""].filter(Boolean) });
    } catch (e) { showError(e); }
  };
  document.querySelectorAll("[data-lec-board]").forEach((sel) => (sel.onchange = async () => {
    try { await api("/api/lecture/board", { id: sel.dataset.lecBoard, board: sel.value }); toast(sel.value ? `已算进「${sel.value}」` : "已改成不分模块"); await refresh(); render(); }
    catch (e) { showError(e); }
  }));
  document.querySelectorAll("[data-lec-del]").forEach((b) => (b.onclick = async () => {
    if (!confirm("删掉这笔记录？（那次得到的修为也会扣回）")) return;
    try { await api("/api/lecture/delete", { id: b.dataset.lecDel }); await refresh(); render(); } catch (e) { showError(e); }
  }));
}
function bindHome() {
  bindTaskClicks($("#view"));
  bindLecture();
  bindPractice();
  bindSelfstudy();
  bindTimeCard();
  bindBoardTime();
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
  SESSION_SNAP = window.SETTLE ? SETTLE.snap() : null;
  Object.assign(T, { session: null, title: "准备中…", msgs: [], input: { mode: "none" }, busy: true, finished: false, battle: null });
  go("train");
  try { applyResp(await api("/api/session/start", body)); }
  catch (e) { T.busy = false; T.msgs.push({ who: "sys", text: "⚠ " + e.message }); T.finished = true; }
  renderTrain();
}
let ASK_OPEN = false;     // 复盘时“师傅求助”打字框开着没有（换题就收起，追问中保持打开）
function applyResp(r) {
  T.session = r.session; T.title = r.title; T.busy = false; T_TYPE = r.type;
  if (r.replace && r.scroll !== 'bottom') ASK_OPEN = false;
  // 试炼答题 / 复盘：每一屏只显示当前这道题（不在聊天里越堆越长），从顶上看起
  if (r.replace) T.msgs = [];
  T.top = !!r.replace && r.scroll !== 'bottom';
  T.msgs.push(...r.messages);
  handleEvents(r.events, { inChat: true });
  T.input = r.input || { mode: "none" };
  T.finished = r.finished;
  T.battle = r.battle || null;
  if (r.finished) {
    const kind = window.SETTLE && SETTLE.kindOf(r.type || T_TYPE), before = SESSION_SNAP, title = r.title || T.title, battle = r.battle;
    SESSION_SNAP = null;
    refresh().then(() => {
      if (VIEW === "train") renderTrain();
      if (kind && before) SETTLE.show({ kind, title, before,
        lines: battle && battle.correct != null && battle.total ? [`破关 ${battle.correct}/${battle.total}`, `正确率 ${Math.round(battle.correct / battle.total * 100)}%`] : [] });
    });
  }
}
// 做功课时对话框钉在屏幕上：底边贴着屏幕底，宽高在“设置 → 对话框大小”里调（存在本机浏览器）
const CHAT_DEF = { w: 80, h: 100, side: true, fs: 110 };   // fs：对话框里的字号（%）
function chatPrefs() {
  try { return Object.assign({}, CHAT_DEF, JSON.parse(localStorage.getItem("chatLayout") || "{}")); } catch { return { ...CHAT_DEF }; }
}
function applyChatLayout(p = chatPrefs()) {
  const root = document.documentElement;
  const hdr = document.querySelector("header");
  const ban = $("#banner");
  const top = Math.max(hdr ? hdr.getBoundingClientRect().bottom : 60, ban && ban.offsetHeight ? ban.getBoundingClientRect().bottom : 0) + 8;
  const avail = Math.max(240, innerHeight - top);
  root.style.setProperty("--chat-w", Math.max(40, Math.min(100, p.w)) + "vw");
  root.style.setProperty("--chat-top", Math.round(innerHeight - avail * Math.max(40, Math.min(100, p.h)) / 100) + "px");
  root.classList.toggle("chat-noside", !p.side);
  root.style.setProperty("--chat-fs", String(Math.max(80, Math.min(160, p.fs || 100)) / 100));
}
function fitChat() {
  const tr = $(".train");
  document.documentElement.classList.toggle("in-chat", !!tr);
  if (!tr) return;
  window.scrollTo(0, 0);
  applyChatLayout();
}
window.addEventListener("resize", () => { if ($(".train")) fitChat(); });
async function renderTrain() {
  if (VIEW !== "train") return;
  const html = await views.train().catch((e) => { showError(e); return ''; });
  if (VIEW !== "train") return;
  $("#view").innerHTML = html;
  bindTrain();
  fitChat();
  const box = $("#msgs"); if (box) box.scrollTop = T.top ? 0 : box.scrollHeight;
  startTimer();
  const ta = $("#answer"); if (ta) ta.focus();
}
function bindTrain() {
  fitChat();
  if (!T.session && !T.msgs.length && !T.busy) return bindHub();
  bindTaskClicks($("#view"));
  bindPins();
  const at = $("#askToggle");
  if (at) at.onclick = () => { ASK_OPEN = !ASK_OPEN; renderTrain(); if (ASK_OPEN) { const a = $("#answer"); if (a) a.focus(); } };
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
  const th = $("#toHall");
  if (th) th.onclick = () => {
    if (T.session && !T.finished && !confirm("这项功课还没结束，先回修炼殿吗？（试炼的进度会保存，其他功课需要重新开始）")) return;
    Object.assign(T, { session: null, msgs: [], battle: null }); clearInterval(TIMER); renderTrain();
  };
  const bh = $("#backHome"); if (bh) bh.onclick = () => { Object.assign(T, { session: null, msgs: [], battle: null }); renderTrain(); };
  const bc = $("#backContest"); if (bc) bc.onclick = () => { Object.assign(T, { session: null, msgs: [], battle: null }); go("contest"); };
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
  const short = (x) => x.year !== undefined ? x.name.replace(/ · [^·]*$/, '').replace(/公务员录用考试|录用公务员考试|《行测》|行政职业能力测验|试卷|试题|题|（网友回忆版）|（精选）/g, '').slice(0, 30) : `第${x.set}套`;
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
      return `<div class="set-book"><div class="row"><b>${esc(b.book)}</b><span class="small muted">共 ${b.sets.length} ${b.paper ? '张卷子（新卷在前）' : '套'} · 已完成 ${b.finished}</span><span class="spacer"></span>
        ${nx ? btn(b.book, nx, 'primary', nx.active ? '继续 ' : '开始 ') : '<span class="tag ok">全部完成</span>'}</div>
        <details><summary class="small">选择其他${b.paper ? '卷子' : '套'}</summary>${grid(b)}</details></div>`;
    }).join('')}</div>`;
}
// ------------------------------------------------------------ 修炼殿：两扇门（修炼 / 实战），没在做功课时显示
let HALL = 'xiulian';            // xiulian 修炼（自选功法练习）| shizhan 实战（真题试炼，原试炼塔）
let XL_BOARD = '';               // 修炼殿里选中的板块
async function hubHtml() {
  const d = DASH || {};
  const tower = d.tower;
  const gates = `<div class="hall-gates">
    <div class="gate ${HALL === 'xiulian' ? 'on' : ''}" data-hall="xiulian"><div class="gate-cloud"></div><div class="gate-icon">🧘</div>
      <div class="gate-name">修 炼</div><div class="gate-sub">${esc(W('yj'))}温习 · 斩心魔</div><div class="gate-stat">${esc(W('yj_add'))} · ${esc(W('yj_review'))} · ${esc(W('yj_browse'))} · ${esc(W('yj_stats'))}</div></div>
    <div class="gate ${HALL === 'shizhan' ? 'on' : ''}" data-hall="shizhan"><div class="gate-cloud"></div><div class="gate-icon">⚔</div>
      <div class="gate-name">实 战</div><div class="gate-sub">试炼塔 · 真题成套</div><div class="gate-stat">${tower ? (tower.summit ? '百层已登顶' : `正在攀登第 ${tower.current} 层`) : '真题试炼'}</div></div></div>`;
  const body = HALL === 'shizhan' ? await shizhanHtml() : await xiulianHtml();
  return gates + `<div class="hall-body">${body}</div>`;
}

// 修炼：上面是玉简（照 Anki 的记忆卡片，web/cards.js），下面斩心魔（模考错题）
async function xiulianHtml() {
  const [yj, ln, wr] = await Promise.all([window.CARDS ? CARDS.hubHtml() : '', window.MINDMAP ? MINDMAP.hubHtml() : '', api('/api/wrong')]);
  const tasks = DASH?.plan?.tasks || [];
  const left = tasks.filter(t => !t.done).length;
  const rec = `<details class="card rec-card"><summary><b>📜 师尊荐课</b> <span class="small muted">程序按进度排的建议（温简、心魔回炉、真题试炼），做不做由你 · 还剩 ${left} 项</span></summary>
    ${tasks.map(taskRow).join('') || '<div class="muted small">今天没有推荐</div>'}</details>`;
  const boards = (wr.boards || []).filter(b => b.total);
  const kill = `<div class="card kill-card"><div class="row"><h3 style="margin:0">👹 ${esc(W('kill'))}</h3><span class="small muted">模考板块复盘里做错的题，一只只斩掉</span></div>
    <div class="kill-grid">${boards.map(b => `<button data-xlwrong="${esc(b.board)}" title="${b.redo ? `回炉 ${b.redo}` : ''}${b.new ? ` 未交手 ${b.new}` : ''}">${esc(b.board)}
      <small>${b.redo ? `回炉 ${b.redo}` : b.new ? `未交手 ${b.new}` : '已斩尽'}</small></button>`).join('') || '<p class="small muted">还没有模考错题：模考后到宗门大比导入成绩，错题会出现在这里。</p>'}</div></div>`;
  return rec + yj + ln + kill;
}

let KP_BOARD = '';               // 知识点试炼里选中的板块
function orderSel(o) {
  return `<label class="small">出题 <select class="bankOrder"><option value="seq" ${o !== 'shuffle' ? 'selected' : ''}>按顺序</option><option value="shuffle" ${o === 'shuffle' ? 'selected' : ''}>🔀 乱序</option></select></label>`;
}
function pointHtml(c, count, order) {
  const boards = (c.boards || []).filter(b => b.total);
  if (!boards.length) return '';
  if (!boards.find(b => b.board === KP_BOARD)) KP_BOARD = boards[0].board;
  const b = boards.find(x => x.board === KP_BOARD);
  return `<div class="card kp-card"><div class="row"><h3 style="margin:0">📖 知识点试炼</h3><span class="small muted">挑一类考点连着刷，一组 ${count} 道没做过的，交卷判分</span><span class="spacer"></span>${orderSel(order)}</div>
    <div class="board-seals small-seals">${boards.map(x => `<a class="seal ${x.board === KP_BOARD ? 'on' : ''}" data-kpboard="${esc(x.board)}">${esc(x.board)}</a>`).join('')}</div>
    <div class="toc">${b.topics.map(t => `<a class="toc-chip kp ${t.left ? '' : 'done'}" data-kp="${esc(b.board)}" data-kptopic="${esc(t.name)}" title="未做 ${t.left} / 共 ${t.count}">${esc(t.name)} <span>${t.left}/${t.count}</span></a>`).join('')}
      ${b.more_topics ? `<span class="small muted">…另有 ${b.more_topics} 个小类，可在藏经阁经卷里搜</span>` : ''}</div>
    ${b.topics.length <= 2 ? '<p class="small muted">这个板块的知识点还很粗（只有大类）：用导入页「⑨ 补蒸馏解析」后会细分成考点。</p>' : ''}</div>`;
}
async function shizhanHtml() {
  const [d, c] = await Promise.all([api('/api/bank'), api('/api/library')]);
  const rate = (ok, n) => n ? `${(ok / n * 100).toFixed(0)}%` : '—';
  const done = d.boards.reduce((n, b) => n + b.first_total, 0);
  const wrong = d.boards.reduce((n, b) => n + b.wrong, 0);
  const firstOk = d.boards.reduce((n, b) => n + b.first_correct, 0);
  const boards = d.boards.filter(b => b.total || b.pending || b.wrong);
  return `${pagodaHtml(d.tower, done, wrong, rate(firstOk, done))}
    ${pointHtml(c, d.count, d.order)}
    ${setsHtml(d.sets)}
    <div class="card"><div class="row"><h3 style="margin:0">⚔ 板块试炼</h3><span class="small muted">${d.order === 'shuffle' ? '从没做过的题里随机抽' : '按题库顺序'}一组 ${d.count} 关，交卷判分（做过的不再出）</span><span class="spacer"></span>
      ${orderSel(d.order)} <label class="small">每组 <select id="bankCount"><option value="10" ${d.count === 10 ? 'selected' : ''}>10 关</option><option value="15" ${d.count === 15 ? 'selected' : ''}>15 关</option></select></label></div>
      <div class="arena-grid">${boards.map(b => `<div class="arena ${b.active ? 'active' : ''}">
        <div class="row"><b>${esc(b.board)}</b><span class="spacer"></span>${b.active ? '<span class="tag cur">进行中</span>' : ''}</div>
        <div class="small muted">余 ${b.remaining}/${b.total} · 首次正确率 ${rate(b.first_correct, b.first_total)}${b.pending ? ` · 待补 ${b.pending}` : ''}</div>
        ${bar(b.total ? (b.total - b.remaining) / b.total : 0, 'thin yellow')}
        ${b.errors.length ? `<div class="warn small">${b.errors.slice(0, 2).map(esc).join('<br>')}</div>` : ''}
        <div class="row"><button class="primary small" data-bank="${esc(b.board)}" data-mode="new" ${!b.active && (!b.remaining || b.errors.length) ? 'disabled' : ''}>${b.active ? '续闯' : '闯关'}</button>
          <button class="small" data-bank="${esc(b.board)}" data-mode="review" ${b.active || !b.wrong ? 'disabled' : ''}>回炉${b.wrong ? ' ' + b.wrong : ''}</button></div></div>`).join('')
        || '<p class="muted">题库还是空的：到藏经阁「📖 经卷 · 题库」最下面的「📥 导入真题」入库。</p>'}</div></div>
    <details class="card"><summary><b>📜 ${esc(W('bank_history'))}</b> <span class="small muted">最近 ${d.groups.length} 组</span></summary>${d.groups.map(x => `<div class="row"><span>${esc(x.date)} · ${esc(x.label || x.board)} · ${esc(W(x.mode === 'new' ? 'bank' : 'bank_review'))}</span><span class="spacer"></span><span class="tag ok">${esc(W('bank_rank.' + x.rank))}</span><span>${x.correct}/${x.total}</span>${x.seconds ? `<span class="small muted">⏱ ${clock(x.seconds)}</span>` : ''}</div>`).join('') || '<p class="muted small">尚未留下试炼战绩。</p>'}</details>
    <p class="small muted">点选项的组按考试来：全部选完交卷才揭晓对错，再逐题复盘，看不懂点「🧙 师傅解惑」。首次作答得${esc(W('xp'))}，回炉连续答对 ${d.streak_need} 次消除残影。</p>`;
}

// 试炼塔：一座宝塔只画当前层上下几层，塔身发光的是正在攀登的那层
function pagodaHtml(t, done, wrong, acc) {
  if (!t) return '';
  const top = Math.min(t.layers, t.current + 2);
  const tiers = [];
  for (let n = top; n >= Math.max(1, top - 4); n--) {
    const cls = n === t.current && !t.summit ? 'cur' : n <= t.cleared ? 'clear' : 'up';
    tiers.push(`<div class="tier ${cls}" style="--w:${62 + (top - n) * 9}%"><div class="roof"></div><div class="tier-body"><span>第 ${n} 层</span></div></div>`);
  }
  return `<div class="card pagoda-card"><div class="pagoda">
      <div class="spire">✦</div>${tiers.join('')}<div class="pagoda-base">试 炼 塔</div></div>
    <div class="pagoda-info"><div class="rune">${t.layers} 层 · ${t.total} 道真题</div>
      <div class="floor-big">${t.summit ? '✦ 百层登顶' : `第 <b>${t.current}</b> 层`}</div>
      ${towerProgress(t)}
      <div class="pagoda-stats"><div><b>${done}</b><span>已闯新题</span></div><div><b>${acc}</b><span>首次正确率</span></div><div><b>${wrong}</b><span>${esc(W('bank_wrong'))}</span></div></div>
      <div class="npc">${tutorFace()}<div class="small"><b>${esc(DASH?.persona?.tutor || '')}</b>：${esc(W('bank_intro'))}</div></div></div></div>`;
}

function bindHub() {
  document.querySelectorAll('[data-hall]').forEach(g => g.onclick = () => { HALL = g.dataset.hall; renderTrain(); });
  document.querySelectorAll('[data-xlboard]').forEach(a => a.onclick = () => { XL_BOARD = a.dataset.xlboard; renderTrain(); });
  document.querySelectorAll('[data-xlwrong]').forEach(b => b.onclick = () =>
    startTask({ task: { type: 'wrong', board: b.dataset.xlwrong, target: '', title: `👹 ${W('kill')} · ${b.dataset.xlwrong}` } }));
  document.querySelectorAll('[data-kpboard]').forEach(a => a.onclick = () => { KP_BOARD = a.dataset.kpboard; renderTrain(); });
  document.querySelectorAll('[data-kp]').forEach(a => a.onclick = () => startTask({ task: {
    type: 'bank', board: `点:${a.dataset.kp}:${a.dataset.kptopic}`, target: '', title: `📖 ${a.dataset.kp} · ${a.dataset.kptopic}` } }));
  document.querySelectorAll('[data-xlpill]').forEach(b => b.onclick = () =>
    startTask({ task: { type: 'alchemy', board: b.dataset.xlpill, target: b.dataset.xlpill, title: `⚗ ${W('alchemy')} · ${b.dataset.xlpill}` } }));
  bindTaskClicks($('#view'));
  if (window.CARDS) CARDS.bindHub($('#view'));
  if (window.MINDMAP) MINDMAP.bindHub($('#view'));
  bindSkeleton();   // 大项练习按钮、编撰功法
  if ($('#bankCount')) bindBank();
}
function bindBank() {
  $('#bankCount').onchange = async (e) => {
    try { await api('/api/bank/count', { count: Number(e.target.value) }); toast('已保存，下一组生效'); }
    catch (err) { showError(err); }
  };
  document.querySelectorAll('.bankOrder').forEach(sel => sel.onchange = async (e) => {
    try {
      await api('/api/bank/count', { order: e.target.value });
      toast(e.target.value === 'shuffle' ? '已改成乱序：下一组从没做过的题里随机抽' : '已改回按顺序');
      renderTrain();
    } catch (err) { showError(err); }
  });
  if ($('#importCard')) $('#importCard').ontoggle = (e) => { if (e.target.open) loadImport(); };
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
      <div class="import-sec"><h4>⑨ 补蒸馏解析</h4>
        <p class="small muted">已经入库的历年真题（编号“真题-数字”），可以从本机下载的蒸馏笔记里补上 推理链 / 最快解法 / 易错点 / 母题抽象，知识点换成细考点。
          按题号对上，不花 token；再合并一次会换成新的，不重复。填蒸馏仓库的根目录或其中“10-真题”文件夹的完整路径。</p>
        <div class="row"><input id="dsFolder" style="flex:1;min-width:280px" placeholder="如 C:\\Users\\29356\\Desktop\\行测obsidian\\行测\\蒸馏skill\\言语蒸馏">
          <button class="ghost" id="dsPreview">预览</button><button id="dsGo">合并</button></div></div>
      <div class="import-sec"><h4>⑩ 题库去重</h4>
        <p class="small muted">题干和选项完全一样的题只留一份（来源括号、空格标点不算差别）。留做过的、有蒸馏解析的那份；删掉那份的试卷出处并过来（按卷刷不缺题），作答记录也挪过来。</p>
        <div class="row"><button class="ghost" id="ddPreview">预览</button><button id="ddGo">去重</button></div></div>
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
    const s0 = window.SETTLE ? SETTLE.snap() : null;
    try {
      const r = await api(url, body);
      if (url.endsWith('/answers')) show(`<p>补了 <b>${r.filled}</b> 题的答案（答案表 ${r.key} 个）。</p>`);
      else if (url.endsWith('/install_pymupdf')) show(r.ok ? '<p>✅ 拆分组件装好了，现在可以拆 PDF。</p>' : '<p>⚠ 装完了但还是找不到组件，关掉程序重新打开试试。</p>');
      else if (url.endsWith('/rename')) show(`<p>改了 <b>${r.renamed}</b> 道题的编号（${r.files} 个题库文件），作答记录迁移 ${r.records} 条。</p>`);
      else if (url.endsWith('/normalize')) show(`<p>整理了 <b>${r.changed}</b> 道题（${r.files} 个文件）。${r.flagged_total ? `有 ${r.flagged_total} 道题的序号 OCR 丢了信息，没法自动还原，请对照原书改：${r.flagged.map(esc).join('、')}${r.flagged_total > r.flagged.length ? ' …' : ''}` : ''}</p>`);
      else if (url.endsWith('/remove')) show(`<p>删除了 <b>${r.removed}</b> 题${r.kept ? `，${r.kept} 道已经做过的保留` : ''}。</p>`);
      else if (url.endsWith('/dedupe')) show(`<p>${r.dry ? '预览（还没改）' : '✅ 去重完成'}：${r.groups ? `${r.groups} 组重复，${r.dry ? '要删' : '删了'} <b>${r.removed}</b> 道（${r.boards.map(([b, n]) => esc(b) + ' ' + n).join('、')}）${r.records ? `，${r.records} 条作答记录挪到留下的那道` : ''}。<br><span class="small muted">例：${r.examples.map(esc).join('；')}（左边留下）</span>` : '没有重复的题。'}</p>`);
      else if (url.endsWith('/distill')) show(`<p>${r.dry ? '预览（还没写入）' : '✅ 合并完成'}：扫描 ${r.scanned} 个 .md，读出 <b>${r.notes}</b> 篇蒸馏笔记${r.skipped_no_qid || r.skipped_no_parts ? `（跳过：${r.skipped_no_qid} 个没有题号、${r.skipped_no_parts} 个没有解析小节，例：${esc(r.skip_example)}）` : ''}，对上题库里 <b>${r.merged}</b> 道题${r.topics ? `，其中 ${r.topics} 道的知识点换成了细考点` : ''}；
          ${r.files.length ? `涉及 ${r.files.length} 个题库文件。` : '题库没有要改的。'}${r.not_in_bank ? `<br>${r.not_in_bank} 篇对不上题库（多选题、没导入的模块，或题库里没有这道；例：qid ${r.not_in_bank_example.map(esc).join('、')}）。` : ''}
          ${r.images_copied ? `<br>${r.dry ? '要拷' : '拷了'} ${r.images_copied} 张解析配图。` : ''}${r.images_missing ? `<br>⚠ ${r.images_missing} 张配图在蒸馏文件夹里没找到（解析里会显示“缺图”）。` : ''}${r.unreadable ? `<br>${r.unreadable} 篇读不了，已跳过。` : ''}</p>`);
      else if (url.endsWith('/classify')) show(`<p>补了 ${r.done} 题的知识点，还剩 ${r.left} 题待分类。</p>`);
      else show(importReport(r, dry));
      if (r.practice_minutes) {   // 导入了一份模考：演武 · 历练记记 120 分钟，弹演武结算
        $('#importResult').insertAdjacentHTML('beforeend', `<p>⚔ 已给「${esc(W('practice_title'))}」记 ${r.practice_minutes} 分钟（第 ${r.season || body.season} 季模考）。去「${esc(NAV('contest'))}」录成绩单。</p>`);
        handleEvents(r.events);
        await refresh();
        if (s0) SETTLE.show({ kind: 'practice', title: `第 ${r.season || body.season} 季模考`, sub: '导入模考试卷', before: s0, lines: [`${r.practice_minutes} 分钟`] });
      }
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
  try { $('#dsFolder').value = localStorage.getItem('dsFolder') || ''; } catch {}
  const ds = (e, dry) => {
    const folder = $('#dsFolder').value.trim();
    if (!folder) return show('<p>⚠ 填蒸馏笔记文件夹的路径</p>');
    try { localStorage.setItem('dsFolder', folder); } catch {}
    run(e.target, '/api/import/distill', { folder, dry }, dry);
  };
  $('#dsPreview').onclick = (e) => ds(e, true);
  $('#ddPreview').onclick = (e) => run(e.target, '/api/import/dedupe', { dry: true }, true);
  $('#ddGo').onclick = (e) => { if (confirm('删除重复的题（留一份，作答记录合并）？')) run(e.target, '/api/import/dedupe', {}, false); };
  $('#dsGo').onclick = (e) => ds(e, false);
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

// 竖排题签：一个字一行（不用 writing-mode，有些字体竖排会叠字）
const vlabel = (t) => [...String(t)].map(esc).join('<br>');
let LIB = { tab: 'gongfa', open: null, yj: { board: '', topic: '', q: '', status: '', page: 0 } };
function skeletonCard(sk, b) {
  const sub = (it) => it.level === 0 && it.l1 ? ` · ${W("recite")} ${it.l1}/${sk.need_l1}` : it.level === 2 && it.l3 ? ` · ${W("apply")} ${it.l3}/${sk.need_l3}` : "";
  const st = b.final ? '<span class="tag ok">已定稿</span>' : b.status === "草稿" ? '<span class="tag draft">草稿</span>' : '<span class="tag lock">无</span>';
  const skill = b.hasSkill ? `<span class="small muted">skill：${esc(b.skill)}</span>` : `<span class="small" style="color:var(--red)">skill 未接入：${esc(b.skill || "（未配置）")}</span>`;
  const rows = b.items.map((it) => {
    const cls = it.rusty ? "rust" : "l" + it.level;
    return `<tr><td>${esc(it.name)}</td><td class="small muted">${it.terms} ${esc(W("term"))} · ${it.thoughts} 思路 · 举例${it.exampleOk ? "已过" : "待过"}</td>
      <td><span class="lvchip ${cls}">${it.rusty && it.level === 0 ? esc(W("rust")) : esc(it.levelName)}${sub(it)}${it.lapCheck ? ` · 待${esc(W("speedrun"))}` : ""}</span></td>
      <td class="small muted">${it.next ? esc(W("review")) + " " + it.next : ""}</td></tr>`;
  }).join("");
  return `<div class="card tome-open"><div class="row"><h3 style="margin:0">📜 ${esc(b.board)} ${st}</h3>${skill}<span class="spacer"></span>
    ${b.final ? "" : `<button class="small" data-skel="${esc(b.board)}">${b.status === "草稿" ? "审阅 / 定稿" : "编撰" + esc(W("skeleton"))}</button>`}</div>
    <div class="small faint">文件：${esc(b.file)}</div>
    ${rows ? `<table style="margin-top:8px"><tr><th>${esc(W("item"))}（大项）</th><th>内容</th><th>掌握</th><th></th></tr>${rows}</table>` : '<p class="muted small">这部功法还没有编撰，点右上角按钮开始。</p>'}</div>`;
}
// 导入真题放在经卷 · 题库最下面：每次模考完第一步就是把试卷 PDF 导入题库
function importCardHtml() {
  return `<details class="card import-card" id="importCard" style="margin-top:18px"><summary><b>📥 导入真题</b> <span class="small muted">模考 PDF（每周模考完先导这里）、txt、PDF 练习册一键入库；导入一份模考给${esc(W("practice_title"))}记 120 分钟</span></summary><div id="importBody">载入中…</div></details>`;
}
// ---- 经卷：题库目录 + 搜题
const YJ_STATUS = { '': '全部', new: '未做', done: '做对', wrong: '做错（心魔）', pending: '答案待补' };
const YJ_TAG = { new: '<span class="tag">未做</span>', done: '<span class="tag ok">✓ 做对</span>', wrong: '<span class="tag bad">✗ 心魔</span>', pending: '<span class="tag lock">待补</span>' };
async function yujianHtml() {
  const c = await api('/api/library');
  const y = LIB.yj;
  const bar = `<div class="card yj-search"><div class="row">
    <input id="yjQ" placeholder="搜题：关键词（空格分开都要有）、编号、试卷名…" value="${esc(y.q)}">
    <select id="yjBoard"><option value="">全部板块</option>${c.boards.map(b => `<option ${b.board === y.board ? 'selected' : ''}>${esc(b.board)}</option>`).join('')}</select>
    <select id="yjStatus">${Object.entries(YJ_STATUS).map(([k, v]) => `<option value="${k}" ${k === y.status ? 'selected' : ''}>${v}</option>`).join('')}</select>
    <button class="primary" id="yjGo">搜索</button></div></div>`;
  if (!(y.q || y.board || y.status)) {
    return bar + `<p class="small muted lib-tip">共 ${c.total} 卷经卷。点一个板块翻目录，或直接在上面搜。</p><div class="tome-grid">${c.boards.map((b, i) => `
      <div class="tome-slot"><div class="slip" data-slip="${esc(b.board)}" style="--d:${(i % 6) * 0.7}s">
        <div class="slip-label">${vlabel(b.board)}</div><div class="slip-count">${b.total}</div></div>
        <div class="tome-cap">做过 ${b.done + b.wrong} · 心魔 ${b.wrong}${b.pending ? ` · 待补 ${b.pending}` : ''}</div></div>`).join('')}</div>`;
  }
  const bd = c.boards.find(b => b.board === y.board);
  const home = `<button class="ghost small" id="yjHome">← 回到经卷目录</button>`;
  const toc = bd && bd.topics.length > 1 ? `<div class="card"><div class="row"><b>📖 ${esc(bd.board)} · 目录</b><span class="small muted">按知识点</span><span class="spacer"></span>${home}</div>
    <div class="toc">${[{ name: '', count: bd.total }].concat(bd.topics).map(t => `<a class="toc-chip ${t.name === y.topic ? 'on' : ''}" data-topic="${esc(t.name)}">${esc(t.name || '全部')} <span>${t.count}</span></a>`).join('')}${bd.more_topics ? `<span class="small muted">…另有 ${bd.more_topics} 个小知识点，用搜索找</span>` : ''}</div></div>`
    : `<div class="row">${home}</div>`;
  return bar + toc + `<div id="yjList" class="card">搜寻中…</div>`;
}
async function yjList() {
  const box = $('#yjList');
  if (!box) return;
  const y = LIB.yj;
  try {
    const r = await api('/api/library/search', { q: y.q, board: y.board, topic: y.topic, status: y.status, page: y.page });
    const pager = r.pages > 1 ? `<div class="row"><button class="ghost small" id="yjPrev" ${r.page ? '' : 'disabled'}>上一页</button><span class="small muted">第 ${r.page + 1}/${r.pages} 页</span><button class="ghost small" id="yjNext" ${r.page + 1 < r.pages ? '' : 'disabled'}>下一页</button></div>` : '';
    box.innerHTML = `<div class="row"><b>找到 ${r.total} 卷经卷</b>${y.topic ? `<span class="tag">${esc(y.topic)}</span>` : ''}<span class="spacer"></span><span class="small muted">点一卷展开</span></div>
      ${r.rows.map(x => `<div class="yj-row" data-key="${esc(x.key)}"><div class="row"><span class="small faint">${esc(x.id)}</span><span class="small muted">${esc(x.board)} · ${esc(x.topic)}</span><span class="spacer"></span>${YJ_TAG[x.status] || ''}</div>
        <div class="yj-text">${esc(x.text)}</div>${x.paper ? `<div class="small faint">${esc(x.paper)}</div>` : ''}<div class="yj-detail" hidden></div></div>`).join('') || '<p class="muted">没有符合的经卷。</p>'}${pager}`;
    if ($('#yjPrev')) $('#yjPrev').onclick = () => { y.page--; yjList(); };
    if ($('#yjNext')) $('#yjNext').onclick = () => { y.page++; yjList(); };
    box.querySelectorAll('.yj-row').forEach(row => row.onclick = (e) => { if (!e.target.closest('.yj-detail')) yjOpen(row); });
    if (y.from === 'idioms') {       // 从成语实词录跳过来的：给个回去的按钮
      box.insertAdjacentHTML('afterbegin', '<button class="ghost small" id="yjBackIdioms">← 回成语实词录</button>');
      $('#yjBackIdioms').onclick = () => { Object.assign(y, { q: '', board: '', from: '' }); LIB.tab = 'idioms'; render(); };
    }
    if (y.openKey) {                 // 跳转过来要直接展开的那道题
      const row = [...box.querySelectorAll('.yj-row')].find(r => r.dataset.key === y.openKey);
      y.openKey = '';
      if (row) { await yjOpen(row); row.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
    }
  } catch (e) { box.innerHTML = `<p>⚠ ${esc(e.message)}</p>`; }
}
async function yjOpen(row) {
  const d = row.querySelector('.yj-detail');
  if (!d.hidden) { d.hidden = true; return; }
  d.hidden = false; d.innerHTML = '展开经卷…';
  try {
    const q = await api('/api/library/question', { key: row.dataset.key });
    const hist = q.history.length ? q.history.map(h => `${esc(h.date || '')} 选 ${esc(h.answer || '')} ${h.ok ? '✓' : '✗'}${h.seconds ? ' · ' + clock(h.seconds) : ''}`).join('<br>') : '还没做过';
    d.innerHTML = `<div class="msg sys">${blocksHtml(q.stem)}${q.options.map(o => `<div class="yj-opt"><b>${o.k}.</b> ${blocksHtml(o.blocks)}</div>`).join('')}</div>
      ${q.papers.length ? `<div class="small faint">出处：${q.papers.map(esc).join('；')}</div>` : ''}
      <button class="small yj-reveal">🔓 显现答案与解析</button>
      <div class="yj-ans" hidden><div class="msg sys"><b>答案：${esc(q.answer)}</b> · 知识点：${esc(q.topic)}${blocksHtml(q.analysis)}</div>${q.tutor?.length ? `<div class="msg sys"><b>🧙 师傅解惑</b>${blocksHtml(q.tutor)}</div>` : ''}<div class="small muted">我的作答：<br>${hist}</div></div>`;
    d.querySelector('.yj-reveal').onclick = (e) => { e.target.hidden = true; d.querySelector('.yj-ans').hidden = false; };
  } catch (e) { d.innerHTML = `⚠ ${esc(e.message)}`; }
}
function bindLibrary() {
  document.querySelectorAll('[data-libtab]').forEach(b => b.onclick = () => { LIB.tab = b.dataset.libtab; render(); });
  document.querySelectorAll('[data-tome]').forEach(t => t.onclick = () => { LIB.open = t.dataset.tome; render(); });
  if ($('#tomeBack')) $('#tomeBack').onclick = () => { LIB.open = null; render(); };
  const y = LIB.yj;
  const go = () => { Object.assign(y, { q: $('#yjQ').value.trim(), board: $('#yjBoard').value, status: $('#yjStatus').value, topic: '', page: 0 }); render(); };
  if ($('#yjGo')) { $('#yjGo').onclick = go; $('#yjQ').onkeydown = (e) => { if (e.key === 'Enter') go(); }; }
  document.querySelectorAll('[data-slip]').forEach(t => t.onclick = () => { Object.assign(y, { board: t.dataset.slip, topic: '', page: 0 }); render(); });
  document.querySelectorAll('[data-topic]').forEach(t => t.onclick = () => { y.topic = t.dataset.topic; y.page = 0; render(); });
  if ($('#yjHome')) $('#yjHome').onclick = () => { Object.assign(y, { q: '', board: '', topic: '', status: '', page: 0 }); render(); };
  if (LIB.tab === 'idioms') IDIOMS.bind();
  yjList();
}
function bindSkeleton() {
  bindLibrary();
  if ($('#importCard')) $('#importCard').ontoggle = (e) => { if (e.target.open) loadImport(); };
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
  $("#aqBtn").onclick = async () => {
    try {
      const r = await api("/api/bank/add", { board: $("#aqBoard").value, topic: $("#aqTopic").value, source: $("#aqSrc").value, stem: $("#aqStem").value,
        options: Object.fromEntries("ABCD".split("").map((k) => [k, $("#aq" + k).value])), answer: $("#aqAns").value, analysis: $("#aqAna").value });
      toast(`已收进 训练/题库/${r.file}，编号 ${r.id}${r.pending ? "（答案待补，补上后才会出题）" : ""}`);
      ["aqStem", "aqA", "aqB", "aqC", "aqD", "aqAna"].forEach((id) => { $("#" + id).value = ""; });
      $("#aqAns").value = "";
    } catch (e) { showError(e); }
  };
  $("#leaveBtn").onclick = async () => { try { const r = await api("/api/leave", {}); handleEvents(r.events); render(); } catch (e) { showError(e); } };
  $("#asBtn").onclick = async () => {
    try { const r = await api("/api/boss", { kind: "飞升", name: $("#asName").value || "国考", score: $("#asScore").value, result: $("#asResult").value }); handleEvents(r.events); render(); } catch (e) { showError(e); }
  };
}
function bindSettings() {
  DEVICE.bind();
  const saveChat = (p) => { try { localStorage.setItem("chatLayout", JSON.stringify(p)); } catch {} };
  const readChat = () => ({ w: Number($("#cwR").value), h: Number($("#chR").value), side: $("#csideR").checked, fs: Number($("#cfR").value) });
  if ($("#cwR")) {
    const upd = () => { const p = readChat(); $("#cwV").textContent = p.w + "%"; $("#chV").textContent = p.h + "%"; $("#cfV").textContent = p.fs + "%";
      $("#cfDemo span").style.fontSize = `calc(15px * ${p.fs / 100})`; saveChat(p); applyChatLayout(p); };
    $("#cwR").oninput = upd; $("#chR").oninput = upd; $("#cfR").oninput = upd; $("#csideR").onchange = upd;
    $("#cResetR").onclick = () => { $("#cwR").value = CHAT_DEF.w; $("#chR").value = CHAT_DEF.h; $("#csideR").checked = CHAT_DEF.side; $("#cfR").value = CHAT_DEF.fs; upd(); };
  }
  AMB.bindSettings(showError);
  document.querySelectorAll("button[data-style]").forEach((b) => (b.onclick = async () => {   // 风格按钮（不能用 data-theme：<html data-theme> 是明暗）
    try { await api("/api/theme", { theme: b.dataset.style }); await refresh(); render(); } catch (e) { showError(e); }
  }));
  const prof = $("#sProf");
  if (prof) prof.onchange = async () => {
    if (!prof.value) return;
    try { await api("/api/settings/ai_profile", { action: "use", name: prof.value }); toast(`🤖 已换成「${esc(prof.value)}」`); await refresh(); render(); } catch (e) { showError(e); }
  };
  const ps = $("#sProfSave");
  if (ps) ps.onclick = async () => {
    const name = prompt("给这套 AI 起个名字（如 DeepSeek、通义千问、Kimi）。会存下面填的接口地址、模型和 key：", $("#sModel").value || "");
    if (!name) return;
    try { await api("/api/settings", formBody()); await api("/api/settings/ai_profile", { action: "save", name }); toast(`💾 已存为「${esc(name)}」`); await refresh(); render(); } catch (e) { showError(e); }
  };
  const pd = $("#sProfDel");
  if (pd) pd.onclick = async () => {
    if (!prof.value || !confirm(`删掉「${prof.value}」这套？（当前用着的设置不变）`)) return;
    try { await api("/api/settings/ai_profile", { action: "delete", name: prof.value }); render(); } catch (e) { showError(e); }
  };
  const pre = $("#sPreset");
  if (pre) pre.onchange = () => {
    const p = AI_PRESETS[+pre.value];
    if (!p) return;
    $("#sBase").value = p[1]; $("#sModel").value = p[2]; $("#sKey").value = ""; $("#sKey").placeholder = `${p[0]} 的 API key`;
    toast(`已填好 ${esc(p[0])} 的接口地址${p[2] ? "和模型" : "，模型名填一下"}；再填 key，点「保存」`);
    pre.value = "";
  };
  function formBody() {
    const body = { vault: $("#sVault").value, base_url: $("#sBase").value, model: $("#sModel").value };
    if ($("#sKey").value.trim()) body.api_key = $("#sKey").value.trim();
    body.vision_model = $("#sVModel").value.trim(); body.vision_base_url = $("#sVBase").value.trim();
    if ($("#sVKey").value.trim()) body.vision_api_key = $("#sVKey").value.trim();
    return body;
  }
  $("#sSave").onclick = async () => {
    try { await api("/api/settings", formBody()); $("#sMsg").textContent = "已保存"; await refresh(); } catch (e) { showError(e); }
  };
  $("#sTest").onclick = async () => {
    $("#sMsg").textContent = "测试中…";
    try { const r = await api("/api/settings/test", {}); $("#sMsg").textContent = "✅ " + r.reply; } catch (e) { $("#sMsg").textContent = ""; showError(e); }
  };
}

// ------------------------------------------------------------ 修炼计时（心跳）
// 只在“真正修炼”时计时：开着一项功课（真题试炼 / 斩心魔 / 渡劫 / 炼丹……，或刚做完在看解析）、在温简、在手札里写字，
// 页面可见，并且 2 分钟内有键盘鼠标操作（或正在等 AI 判题）。只是开着网页、看面板、和导师闲聊都不计时。
// 后端也会核对会话是否真的在进行（rpg/trainer.is_studying），前端条件只是省掉无用的上报。
const BEAT = 30;
const STUDY = ["teach", "recite", "review", "speedrun", "feynman", "example", "apply", "wrong", "tribulation", "alchemy", "bank", "bank_review", "mock_review"];
let lastActive = Date.now();
let T_TYPE = "";
["mousemove", "keydown", "click", "scroll", "input"].forEach((ev) => addEventListener(ev, () => (lastActive = Date.now()), { passive: true }));
function studyingNow() {
  return VIEW === "train" && !!T.session && STUDY.includes(T_TYPE) && document.visibilityState === "visible"
    && (T.busy || Date.now() - lastActive < 120000);
}
// 在 🪶 手札里写字也算复习：按秒累计“1 分钟内写过字”的时间，心跳时连同本子编号一起报（服务器核对这本最近真的存过笔迹）
let noteSec = 0;
let cardSec = 0;   // 温简也算复习：按秒累计正在温简的时间（web/cards.js 的 active：在温、看得见、2 分钟内有操作）
setInterval(() => { if (window.NOTES && NOTES.writingId()) noteSec += 1; if (window.CARDS && CARDS.active()) cardSec += 1; }, 1000);
function updateStudyDot() {
  const on = studyingNow() || !!(window.NOTES && NOTES.writingId()) || !!(window.CARDS && CARDS.active());
  $("#todayPill").classList.toggle("on", on);
  $("#todayPill").title = on ? "正在计时：修炼中" : "未计时：只有做功课时才算修炼时间";
}
let beatCount = 0;
setInterval(async () => {
  updateStudyDot();
  const on = studyingNow();
  beatCount += 1;
  if (!on && !noteSec && !cardSec && beatCount % 2) return;          // 不修炼时每分钟只刷新一次状态（多设备提醒、调息、闭关）
  try {
    const nid = !on && window.NOTES ? NOTES.writingId() || (noteSec ? NOTES.lastId() : "") : "";
    const carding = !on && !nid && cardSec > 0;
    const sec = on ? BEAT : Math.min(BEAT, nid ? noteSec : cardSec);
    noteSec = 0; cardSec = 0;
    if (nid && sec) await NOTES.save();          // 先把刚写的存上，服务器才认得“最近写过”
    const r = await api("/api/heartbeat", { seconds: sec, session: on ? T.session : null, notes: nid || null,
      cards: carding || null, cards_board: carding ? CARDS.board() : null });
    if (DASH) { DASH.minutes.today = r.minutes; DASH.other_device = r.other_device; DASH.rest = r.rest; updatePill(); banner(); }
    handleEvents(r.events);
    if (DASH?.retreat && !r.retreat_on && VIEW === "home") render();
  } catch (e) { /* 程序关了就不提示 */ }
}, BEAT * 1000);
setInterval(updateStudyDot, 5000);

render();



// 试炼进度与破关数，不显示任何未提交题目的答案。
const clock = (s) => { s = Math.max(0, Math.round(s)); return s >= 3600 ? `${Math.floor(s / 3600)}:${String(Math.floor(s / 60) % 60).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}` : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; };
// 答题计时：程序记的是准数，网页在两次操作之间自己走秒
let TIMER = null;
function startTimer() {
  clearInterval(TIMER);
  const t = T.battle?.timer;
  if (!t || T.finished) return;
  const t0 = Date.now();
  TIMER = setInterval(() => {
    const q = $('#tQ'), a = $('#tT');
    if (!q || !a) return clearInterval(TIMER);
    const d = (Date.now() - t0) / 1000;
    q.textContent = clock(t.question + d); a.textContent = clock(t.total + d);
  }, 1000);
}
// 修炼对话框顶上：标题和进度合成一行（标题后面跟小标签，底边一道细进度线），不再占一大块
function sessionHead() {
  const b = T.battle;
  if (!b) return `<div class="review-head"><b>${esc(T.title)}</b></div>`;
  return b.label ? reviewHead(b) : bankHead(b);
}
function headRow(title, tags, ratio) {
  return `<div class="review-head"><b>${esc(title)}</b><span class="rh-stats">${tags.filter(Boolean).join("")}</span>
    <i class="rh-bar" style="width:${Math.round(100 * Math.max(0, Math.min(1, ratio)))}%"></i></div>`;
}
// 大比复盘
function reviewHead(b) {
  return headRow("📜 " + b.label, [`<span>第 ${b.position}/${b.total} 题</span>`, `<span class="ok">✓ ${b.ok}</span>`, `<span class="bad">✗ ${b.wrong}</span>`,
    b.blank ? `<span>○ ${b.blank}</span>` : "", `<span>复盘过 ${b.reviewed}</span>`], b.position / b.total);
}
// 真题试炼（答题 / 交卷后复盘）：第几关、试炼塔、已作答、计时、对错
function bankHead(b) {
  const t = b.tower;
  const tower = !t ? "" : t.summit ? `<span title="${t.layers} 层已全部登顶">🗼 已登顶</span>`
    : `<span title="本层 ${t.floor_done}/${t.floor_total} 道 · 再做 ${t.remaining} 道升层">🗼 第 ${t.current} 层 ${t.floor_done}/${t.floor_total}</span>`;
  return headRow(T.title, [
    `<span>${b.phase === "review" ? "复盘 " : ""}第 ${b.position}/${b.total} 关</span>`, tower, `<span>已作答 ${b.answered}</span>`,
    b.timer ? `<span>⏱ 本题 <b id="tQ">${clock(b.timer.question)}</b> · 总 <b id="tT">${clock(b.timer.total)}</b></span>` : "",
    b.correct === null ? "" : `<span class="ok">破关 ${b.correct}</span><span class="bad">${esc(W("bank_wrong"))} ${b.answered - b.correct}</span>`,
  ], b.answered / b.total);
}

function towerProgress(t) {
  if (!t) return '';
  if (t.summit) return `<div class="tower-progress">🗼 ${t.layers} 层已全部登顶 · ${t.completed} 道新题</div>${bar(1, 'thin yellow')}`;
  return `<div class="tower-progress">🗼 正在攀登第 ${t.current} 层 · 本层 ${t.floor_done}/${t.floor_total} 道 · 再做 ${t.remaining} 道升层</div>${bar(t.floor_total ? t.floor_done / t.floor_total : 0, 'thin yellow')}`;
}
