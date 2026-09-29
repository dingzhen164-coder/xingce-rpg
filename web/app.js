/*
  行测 RPG 前端（原生 JS，无需编译）。改完刷新浏览器即可。

  结构：
    api()                 调后端接口（接口说明见 rpg/api.py 顶部）
    views.*               各页面的渲染函数：home / train / skeleton / wrong / log / settings
    handleEvents()        处理后端返回的事件：+经验提示、升级弹窗、导师台词
    heartbeat             每 60 秒上报一次学习时间（页面可见且 2 分钟内有操作才算）

  训练页的状态在 T 对象里：当前会话 id、对话消息、输入方式（文字 / 按钮）。
*/
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
// 很简单的 Markdown：**粗体**、`代码`、换行
const md = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\n/g, "<br>");
const pct = (x) => Math.round((x || 0) * 100);

let DASH = null;           // 最近一次 /api/dashboard 的结果
let VIEW = "home";
const T = { session: null, title: "", msgs: [], input: { mode: "none" }, busy: false, finished: false };

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
function npcToast(msg) {
  if (!msg) return;
  const name = DASH?.persona?.tutor || "导师";
  toast(`<div class="npc"><div class="face">🎖</div><div><div class="who">${esc(name)}</div>${md(msg)}</div></div>`, "", 7000);
}
function showError(e) { toast("⚠ " + esc(e.message || e), "err", 6000); }

function handleEvents(events, { inChat = false } = {}) {
  for (const e of events || []) {
    if (e.kind === "xp") toast(`+${e.v} EXP <span class="small muted">${esc(e.msg || "")}</span>`, "xp");
    else if (e.kind === "level") levelUp(e);
    else if (e.kind === "npc" && e.msg) inChat ? T.msgs.push({ who: "npc", text: e.msg }) : npcToast(e.msg);
    else if (e.kind === "info") toast("ℹ " + esc(e.msg));
  }
}
function levelUp(e) {
  const m = $("#modal");
  m.innerHTML = `<div class="levelup"><div class="muted">LEVEL UP</div><div class="lv">Lv.${e.v}</div>
    <div style="font-size:20px;margin-top:6px">预估 <b style="color:var(--gold)">${e.score}</b> 分</div>
    <div class="muted">称号：${esc(e.title)}</div><br><button class="primary">继续变强</button></div>`;
  m.classList.remove("hidden");
  $("button", m).onclick = () => m.classList.add("hidden");
}

// ------------------------------------------------------------ 导航
function go(view) {
  VIEW = view;
  document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.view === view));
  render();
}
document.querySelectorAll("#nav a").forEach((a) => (a.onclick = () => go(a.dataset.view)));

async function refresh() {
  try {
    DASH = await api("/api/dashboard");
    handleEvents(DASH.events);
    updatePill();
    banner();
    if (DASH.first_today && DASH.greeting && VIEW !== "home") npcToast(DASH.greeting);  // 主页顶部本来就显示问候
  } catch (e) { showError(e); }
}
function updatePill() {
  if (!DASH) return;
  const m = DASH.minutes;
  $("#todayPill").textContent = `⏱ ${m.today} / ${m.goal} 分钟` + (m.today >= m.goal ? " ✅" : "");
}
function banner() {
  const w = [];
  if (!DASH.vault) w.push("还没找到行测库，请到“设置”里填写库的路径。");
  if (!DASH.ai) w.push("还没填写 AI 的 API key：默写和错题可以用自评模式，费曼讲解 / 应用题 / 生成骨架需要 AI。去“设置”填写。");
  if (DASH.other_device) w.push(`另一台电脑（${esc(DASH.other_device)}）10 分钟内在用训练程序。两台同时用，坚果云同步可能冲突，请先关掉那台。`);
  if (DASH.conflicts?.length) w.push("存档文件夹里有坚果云冲突副本：" + DASH.conflicts.map(esc).join("、") + "。请告诉 AI 帮你合并，或删掉旧的那份。");
  $("#banner").innerHTML = w.map((x) => `<div class="warn">${x}</div>`).join("");
}

async function render() {
  const v = $("#view");
  try {
    if (VIEW === "home") { await refresh(); v.innerHTML = views.home(); bindHome(); }
    else if (VIEW === "train") { v.innerHTML = views.train(); bindTrain(); }
    else if (VIEW === "skeleton") { v.innerHTML = await views.skeleton(); bindSkeleton(); }
    else if (VIEW === "wrong") { v.innerHTML = await views.wrong(); }
    else if (VIEW === "log") { await refresh(); v.innerHTML = views.log(); bindLog(); }
    else if (VIEW === "settings") { v.innerHTML = await views.settings(); bindSettings(); }
  } catch (e) { showError(e); }
}

// ------------------------------------------------------------ 页面
const STATE_TAG = { current: '<span class="tag cur">◆本批</span>', mastered: '<span class="tag ok">★已掌握</span>',
  cleared: '<span class="tag ok">已通关</span>', locked: '<span class="tag lock">🔒待接入</span>', later: "" };

const views = {
  home() {
    const d = DASH; if (!d) return "";
    const L = d.level, p = d.persona, I = d.ideal, F = d.forecast;
    const avatar = p.avatar ? `<img src="${esc(p.avatar)}" alt="头像">` : `<div class="def">${esc((p.call || "岸").slice(-1))}</div>`;
    const diff = I.diff_days;
    const ideal = diff > 0.5 ? `<div class="v bad">落后 ${diff} 天</div><div class="d">${I.catch ? `每天多学 ${I.catch.per_day} 分钟，约 ${I.catch.days} 天追平（共 ${I.catch.hours} 小时）` : ""}</div>`
      : diff < -0.5 ? `<div class="v good">领先 ${-diff} 天</div><div class="d">保持住</div>` : `<div class="v">正好在线上</div><div class="d">按计划走</div>`;
    const gate = L.gate ? `<div class="small" style="color:var(--gold)">⚡ 经验已满，完成「突破试炼」才能升到 Lv.${L.gate + 1}</div>` : "";
    const batch = d.batch.index ? `第 ${d.batch.index}/${d.batch.count} 批：${d.batch.boards.map(esc).join("、")}` : "本周目已通关";
    const tasks = d.plan.tasks;
    const doneN = tasks.filter((t) => t.done).length;
    const totalMin = tasks.filter((t) => !t.optional).reduce((a, t) => a + t.minutes, 0);
    let lastBatch = 0;
    const tree = d.tree.map((s) => {
      let h = "";
      if (s.batch !== lastBatch) { lastBatch = s.batch; h += `<div class="batch-h">第 ${s.batch} 批</div>`; }
      const acc = s.acc ? `实战 ${pct(s.acc.rate)}% ${s.acc.trend}` : "实战 —";
      const sk = s.state === "locked" ? "" : s.skeleton === "none" ? '<span class="tag draft">无骨架</span>' : s.skeleton === "draft" ? '<span class="tag draft">骨架草稿</span>' : "";
      const color = s.state === "mastered" ? "green" : s.state === "current" ? "yellow" : "";
      return h + `<div class="skill ${s.state === "locked" ? "locked" : ""}"><div class="top"><span>${esc(s.board)} ${STATE_TAG[s.state] || ""}${sk}</span>
        <span class="muted small">${acc}</span></div><div class="bar thin ${color}"><div style="width:${pct(s.progress)}%"></div></div>
        <div class="faint small">${s.items ? `${s.mastered}/${s.items} 大项掌握 · ${pct(s.progress)}%` : ""}</div></div>`;
    }).join("");
    const side = d.side.map((s) => {
      const r = s.acc ? s.acc.rate : 0;
      return `<div class="stat"><div class="row"><b>${esc(s.board)}</b><span class="spacer"></span><span class="small muted">目标 ${pct(s.target)}%</span></div>
        <div>实战 <b>${s.acc ? pct(r) + "%" : "—"}</b> ${s.acc ? s.acc.trend : ""}</div>
        <div class="bar thin blue"><div style="width:${Math.min(100, pct(r / s.target))}%"></div></div></div>`;
    }).join("");
    const boss = d.boss.length ? d.boss.slice().reverse().map((b) => `${esc(b.name)} <b>${b.score}</b> <span class="faint small">${b.d}</span>`).join(" · ") : '<span class="muted">还没有记录。模考 / 国考出分后到“记录”页录入。</span>';
    return `
    <div class="card npc"><div class="face">🎖</div><div><div class="who">${esc(p.tutor)}</div><div>${md(d.greeting)}</div></div></div>
    <div class="card hero">
      <div class="avatar">${avatar}<div class="lv-badge">Lv.${L.level}</div></div>
      <div class="hero-main">
        <div class="hero-name">${esc(p.id)}<small>「${esc(p.call)}」</small></div>
        <div class="hero-title">称号：${esc(L.title)} · 第 ${d.lap} 周目 · ${esc(batch)}</div>
        <div class="row small muted" style="margin-top:8px"><span>EXP ${L.into} / ${L.need}</span><span class="spacer"></span><span>累计 ${d.xp}</span></div>
        <div class="bar"><div style="width:${pct(L.frac)}%"></div></div>${gate}
      </div>
      <div class="hero-score"><div class="small muted">等级预估</div><div class="big">${L.score}<span>分</span></div>
        <div class="small muted">满级 Lv.${L.max_level} = ${L.max_score} 分</div></div>
    </div>
    <div class="grid g4" style="margin-top:14px">
      <div class="stat"><div class="k">🔥 连续打卡</div><div class="v">${d.streak.days} 天</div><div class="d">经验加成 +${pct(d.streak.bonus)}%</div></div>
      <div class="stat"><div class="k">📅 理想线</div>${ideal}</div>
      <div class="stat"><div class="k">🗺 本周目进度</div><div class="v">${pct(F.progress)}%</div><div class="d">${F.days_left ? `按近 7 天速度还需 ${F.days_left} 天` : "练几天后给出预测"}</div></div>
      <div class="stat"><div class="k">🏁 预计满级</div><div class="v">${I.eta || "—"}</div><div class="d">目标 ${I.target}${I.daily_rate ? ` · 日均 ${I.daily_rate} EXP` : ""}</div></div>
    </div>
    <div class="grid g2" style="margin-top:14px">
      <div class="card"><h3>📜 今日任务 <small>${doneN}/${tasks.length} · 约 ${totalMin} 分钟</small></h3>
        <div id="tasks">${tasks.map(taskRow).join("") || '<div class="muted">今天没有任务。去“骨架”页生成骨架，或者到“记录”页录入自练。</div>'}</div>
        <div class="row" style="margin-top:8px"><button class="ghost small" id="regen">重新生成今日任务</button>
        <button class="ghost small" id="chatBtn">和${esc(p.tutor)}聊聊</button></div></div>
      <div class="card"><h3>⚔ 技能树 <small>骨架掌握度 · 实战正确率（最近 3 季）</small></h3><div class="tree">${tree}</div></div>
    </div>
    <div class="grid g2" style="margin-top:14px">
      <div class="card"><h3>🧭 副线 <small>不做骨架，只看实战正确率</small></h3><div class="grid g2">${side}</div>
        <div class="small muted" style="margin-top:8px">回炉中的错题：${d.redo} 道</div></div>
      <div class="card"><h3>👹 Boss 战</h3><div>${boss}</div>
        <h3 style="margin-top:14px">🕘 最近</h3>${recentList(d.recent.slice(0, 6))}</div>
    </div>`;
  },

  train() {
    if (!T.session && !T.msgs.length) {
      const tasks = DASH?.plan?.tasks || [];
      return `<div class="card"><h3>训练</h3><p class="muted">从今日任务里选一个开始：</p>${tasks.map(taskRow).join("") || '<div class="muted">没有任务</div>'}</div>`;
    }
    const tasks = DASH?.plan?.tasks || [];
    const inp = T.input;
    let composer = "";
    if (T.busy) composer = `<div class="thinking">${esc(DASH?.persona?.tutor || "导师")}正在看你的答案</div>`;
    else if (inp.mode === "text") composer = `<textarea id="answer" placeholder="${esc(inp.placeholder || "")}"></textarea>
        <div class="row" style="margin-top:8px"><span class="small muted">Ctrl / ⌘ + Enter 提交</span><span class="spacer"></span>
        <button class="ghost" data-act="skip">跳过</button><button class="primary" id="send">提交</button></div>`;
    else if (inp.mode === "buttons") composer = `<div class="row">${inp.buttons.map((b) => `<button class="${b.id === "skip" ? "ghost" : "primary"}" data-act="${esc(b.id)}">${esc(b.label)}</button>`).join("")}</div>`;
    else if (T.finished) composer = `<div class="row"><button class="primary" id="nextTask">下一个任务</button><button class="ghost" id="backHome">回主页</button></div>`;
    return `<div class="train">
      <div class="card"><h3>今日任务</h3>${tasks.map(taskRow).join("")}</div>
      <div class="card chat"><h3>${esc(T.title)}</h3><div class="msgs" id="msgs">${T.msgs.map(msgHtml).join("")}</div>
        <div class="composer">${composer}</div></div></div>`;
  },

  async skeleton() {
    const sk = await api("/api/skeletons");
    // 掌握度后面附上当前级别的进度，如“未学 · 默写 1/2”
    const sub = (it) => it.level === 0 && it.l1 ? ` · 默写 ${it.l1}/${sk.need_l1}` : it.level === 2 && it.l3 ? ` · 应用 ${it.l3}/${sk.need_l3}` : "";
    return sk.boards.map((b) => {
      const st = b.final ? '<span class="tag ok">已定稿</span>' : b.status === "草稿" ? '<span class="tag draft">草稿</span>' : '<span class="tag lock">无</span>';
      const skill = b.hasSkill ? `<span class="small muted">skill：${esc(b.skill)}</span>` : `<span class="small" style="color:var(--red)">skill 未接入：${esc(b.skill || "（未配置）")}</span>`;
      const rows = b.items.map((it) => {
        const cls = it.rusty ? "rust" : "l" + it.level;
        return `<tr><td>${esc(it.name)}</td><td class="small muted">${it.terms} 术语 · ${it.thoughts} 思路</td>
          <td><span class="lvchip ${cls}">${it.rusty && it.level === 0 ? "生锈" : esc(it.levelName)}${sub(it)}${it.lapCheck ? " · 待速通" : ""}</span></td>
          <td class="small muted">${it.next ? "复查 " + it.next : ""}</td>
          <td>${b.final ? `<a data-free="${esc(it.id)}" data-board="${esc(b.board)}" data-name="${esc(it.name)}">默写一次</a>` : ""}</td></tr>`;
      }).join("");
      return `<div class="card"><div class="row"><h3 style="margin:0">${esc(b.board)} ${st}</h3>${skill}<span class="spacer"></span>
        ${b.final ? "" : `<button class="small" data-skel="${esc(b.board)}">${b.status === "草稿" ? "审核 / 定稿" : "生成骨架"}</button>`}</div>
        <div class="small faint">文件：${esc(b.file)}</div>
        ${rows ? `<table style="margin-top:8px"><tr><th>大项</th><th>内容</th><th>掌握度</th><th></th><th></th></tr>${rows}</table>` : ""}</div>`;
    }).join("");
  },

  async wrong() {
    const w = await api("/api/wrong");
    const rows = w.boards.filter((b) => b.total).map((b) => `<tr><td>${esc(b.board)}</td><td>${b.total}</td><td>${b.new}</td><td style="color:var(--red)">${b.redo}</td><td style="color:var(--green)">${b.done}</td></tr>`).join("");
    const redo = w.redo.map((r) => { const [n, s, q] = r.key.split("|"); return `<tr><td>第${n}季 ${esc(s)} 第${q}题</td><td>${r.due || ""}</td><td>${r.streak || 0}</td><td>${r.tries}</td></tr>`; }).join("");
    return `<div class="card"><h3>错题池 <small>来自模考板块复盘里的 ❌ / ⚪ 题</small></h3>
      <table><tr><th>板块</th><th>错题</th><th>未练</th><th>回炉中</th><th>已过关</th></tr>${rows || '<tr><td colspan="5" class="muted">还没有错题数据</td></tr>'}</table></div>
      <div class="card"><h3>回炉清单 <small>判错的题，到期后出现在每日任务里</small></h3>
      <table><tr><th>题目</th><th>下次</th><th>连续判对</th><th>练过</th></tr>${redo || '<tr><td colspan="4" class="muted">清空了，漂亮</td></tr>'}</table></div>`;
  },

  log() {
    const d = DASH;
    return `<div class="grid g2">
      <div class="card"><h3>👹 录入 Boss 战（模考 / 国考真实分）</h3>
        <div class="row"><input id="bossName" placeholder="名称，如 第37季模考 / 2026国考" style="flex:2"><input id="bossScore" placeholder="分数" style="flex:1"></div>
        <div class="row" style="margin-top:8px"><button class="primary" id="bossBtn">录入</button><span class="small muted">每次录分 +经验，比上次高还有额外奖励</span></div></div>
      <div class="card"><h3>📝 录入自练（资料分析、常识等）</h3>
        <div class="row"><input id="prBoard" placeholder="板块" style="flex:2"><input id="prTotal" placeholder="题数" style="flex:1"><input id="prOk" placeholder="对了几题" style="flex:1"><input id="prMin" placeholder="分钟" style="flex:1"></div>
        <div class="row" style="margin-top:8px"><button class="primary" id="prBtn">录入</button><span class="small muted">分钟会计入今天的学习时间</span></div></div>
    </div>
    <div class="card"><h3>🎫 请假卡 <small>本月已用 ${d.leave.used}/${d.leave.total}</small></h3>
      <p class="muted">生病、家里有事、加班……用一张请假卡：今天不断打卡，也不计入理想线。</p>
      <button id="leaveBtn" ${d.leave.today ? "disabled" : ""}>${d.leave.today ? "今天已请假" : "今天请假"}</button></div>
    <div class="card"><h3>🕘 经验记录</h3>${recentList(d.recent)}</div>`;
  },

  async settings() {
    const s = await api("/api/settings");
    return `<div class="card"><h3>本机设置 <small>保存在本机 ~/.xingce-rpg/settings.json，不会同步、不会上传</small></h3>
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
      <ul><li><b>训练/规则.md</b>：满级目标日、每日时长、分批、经验值、复查间隔……</li>
      <li><b>训练/角色设定.md</b>：ID、称呼、头像、称号、导师人设</li>
      <li><b>训练/台词库.md</b>：导师在各种场景说的话，可以自己加</li>
      <li><b>训练/骨架/板块.md</b>：每个板块的默写标准</li></ul></div>`;
  },
};

function taskRow(t) {
  const ck = t.done ? (t.ok === false ? "❌" : "✅") : "⬜";
  return `<div class="task ${t.done ? "done" : ""} ${t.optional ? "opt" : ""}" data-task="${esc(t.id)}">
    <span class="ck">${ck}</span><span class="ttl">${esc(t.title)}</span><span class="spacer"></span><span class="min">${t.minutes} 分钟</span></div>`;
}
function recentList(ev) {
  if (!ev?.length) return '<div class="muted small">还没有记录</div>';
  return ev.map((e) => `<div class="row small"><span class="faint">${esc(e.t?.slice(5, 16).replace("T", " ") || e.d)}</span>
    <span>${esc(e.note)}</span><span class="spacer"></span><b style="color:var(--gold)">+${e.xp}</b></div>`).join("");
}
function msgHtml(m) {
  const blocks = (m.blocks || []).map((b) => b.t === "img" ? `<img src="/vault-file?p=${encodeURIComponent(b.v)}">` : `<div>${md(b.v)}</div>`).join("");
  if (m.fold) return `<details class="fold"><summary>${esc(m.fold)}</summary><div>${md(m.text)}</div></details>`;
  if (m.who === "npc") return `<div class="npc"><div class="face">🎖</div><div class="say"><div class="who">${esc(DASH?.persona?.tutor || "导师")}</div>${md(m.text)}</div></div>`;
  if (m.who === "me") return `<div class="msg me">${esc(m.text)}</div>`;
  return `<div class="msg sys">${md(m.text)}${blocks}</div>`;
}

// ------------------------------------------------------------ 交互绑定
function bindTaskClicks(root) {
  root.querySelectorAll("[data-task]").forEach((el) => (el.onclick = () => startTask({ task_id: el.dataset.task })));
}
function bindHome() {
  bindTaskClicks($("#view"));
  $("#regen").onclick = async () => { try { await api("/api/plan/regenerate", {}); render(); } catch (e) { showError(e); } };
  $("#chatBtn").onclick = () => startTask({ task: { type: "chat", board: "", target: "", title: "和导师聊聊" } });
}

async function startTask(body) {
  Object.assign(T, { session: null, title: "准备中…", msgs: [], input: { mode: "none" }, busy: true, finished: false });
  go("train");
  try { applyResp(await api("/api/session/start", body)); }
  catch (e) { T.busy = false; T.msgs.push({ who: "sys", text: "⚠ " + e.message }); T.finished = true; }
  renderTrain();
}
function applyResp(r) {
  T.session = r.session; T.title = r.title; T.busy = false;
  T.msgs.push(...r.messages);
  handleEvents(r.events, { inChat: true });
  T.input = r.input || { mode: "none" };
  T.finished = r.finished;
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
    const t = (DASH?.plan?.tasks || []).find((x) => !x.done && !x.optional) || (DASH?.plan?.tasks || []).find((x) => !x.done);
    t ? startTask({ task_id: t.id }) : (toast("今日任务全部完成！"), go("home"));
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
function bindSkeleton() {
  document.querySelectorAll("[data-skel]").forEach((b) => (b.onclick = () =>
    startTask({ task: { type: "skeleton", board: b.dataset.skel, target: b.dataset.skel, title: `「${b.dataset.skel}」骨架` } })));
  document.querySelectorAll("[data-free]").forEach((a) => (a.onclick = () =>
    startTask({ task: { type: "recite", board: a.dataset.board, target: a.dataset.free, title: `默写 · ${a.dataset.board}「${a.dataset.name}」` } })));
}
function bindLog() {
  $("#bossBtn").onclick = async () => {
    try { const r = await api("/api/boss", { name: $("#bossName").value, score: $("#bossScore").value }); handleEvents(r.events); render(); } catch (e) { showError(e); }
  };
  $("#prBtn").onclick = async () => {
    try { const r = await api("/api/practice", { board: $("#prBoard").value, total: $("#prTotal").value, correct: $("#prOk").value, minutes: $("#prMin").value }); handleEvents(r.events); render(); } catch (e) { showError(e); }
  };
  $("#leaveBtn").onclick = async () => { try { const r = await api("/api/leave", {}); handleEvents(r.events); render(); } catch (e) { showError(e); } };
}
function bindSettings() {
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

// ------------------------------------------------------------ 学习计时（心跳）
let lastActive = Date.now();
["mousemove", "keydown", "click", "scroll"].forEach((ev) => addEventListener(ev, () => (lastActive = Date.now()), { passive: true }));
setInterval(async () => {
  if (document.visibilityState !== "visible" || Date.now() - lastActive > 120000) return;
  try {
    const r = await api("/api/heartbeat", { seconds: 60 });
    if (DASH) { DASH.minutes.today = r.minutes; DASH.other_device = r.other_device; updatePill(); banner(); }
    handleEvents(r.events);
  } catch (e) { /* 程序关了就不提示 */ }
}, 60000);

render();
