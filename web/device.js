/* 设置页的两张卡：📱 手机 / 平板（局域网模式、地址、二维码、访问口令、添加到主屏幕的做法）和 🆕 版本与更新。
   数据：GET/POST /api/lan、GET /api/version、GET /api/update/check、POST /api/update/apply（见 rpg/lan.py、rpg/update.py） */
(function () {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const local = ["127.0.0.1", "localhost", "::1", "[::1]"].includes(location.hostname);
  const inApp = /XingceApp\//.test(navigator.userAgent) && typeof XC !== "undefined";      // 平板 App（android/）里
  const android = /Android/i.test(navigator.userAgent);
  const standalone = matchMedia("(display-mode: standalone), (display-mode: fullscreen)").matches || navigator.standalone;
  // 平板 App 安装包：从电脑拿（电脑替平板去 GitHub 下好，平板不用能上 GitHub），见 rpg/appapk.py
  const APK = "/app/xingce-xiuxian.apk";
  const vnum = (s) => String(s || "").split(".").map((x) => parseInt(x, 10) || 0);
  const newer = (a, b) => { const x = vnum(a), y = vnum(b); for (let i = 0; i < 4; i++) { if ((x[i] || 0) !== (y[i] || 0)) return (x[i] || 0) > (y[i] || 0); } return false; };
  let UPD = null;

  // 在 App 里 / 主屏幕打开：给页面打个记号（样式按触屏收紧）；浏览器里的平板：顶栏多一个 ⛶ 全屏按钮
  const root = document.documentElement;
  if (inApp) root.classList.add("in-app");
  if (matchMedia("(pointer: coarse)").matches) root.classList.add("touch");
  const fs = document.getElementById("fsBtn");
  const canFs = !local && !inApp && !standalone && root.requestFullscreen;
  if (fs && canFs) {
    fs.style.display = "";
    fs.onclick = () => (document.fullscreenElement ? document.exitFullscreen() : root.requestFullscreen({ navigationUI: "hide" })).catch(() => {});
    document.addEventListener("fullscreenchange", () => fs.classList.toggle("on", !!document.fullscreenElement));
  }

  async function html() {
    let lan = null, ver = null, log = [];
    try { [lan, ver] = await Promise.all([api("/api/lan"), api("/api/version")]); } catch (e) { return ""; }
    try { log = (await api("/api/changelog")).entries || []; } catch (e) { /* 没有就不显示 */ }
    // 版本更新记录：整块默认收起；展开后最新一版默认打开，其余点开看
    const logHtml = !log.length ? "" : `<details class="fold changelog"><summary>📜 版本更新记录（共 ${log.length} 版，最新 ${esc(log[0].version)}）</summary>
      ${log.map((e, i) => `<details class="cl-ver" ${i === 0 ? "open" : ""}><summary><b>v${esc(e.version)}</b>${e.date ? ` <span class="faint small">${esc(e.date)}</span>` : ""}${e.version === ver.version ? ' <span class="tag ok">当前</span>' : ""}</summary>
        <ul>${e.items.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></details>`).join("")}</details>`;
    const lanCard = inApp
      ? `<div class="card dev-card"><h3>📱 平板 App <small>v${esc(XC.version())} · 连着 ${esc(location.host)}</small></h3>
          <p class="small muted">数据都在电脑上，这里只是打开它。返回键：先关弹窗，再回洞府，在洞府按两次退出。</p>
          <div class="row" style="gap:10px;flex-wrap:wrap;align-items:center"><button id="appUpd">检查 App 更新</button><span id="appMsg" class="small muted"></span></div>
          <p class="small faint">新版本由电脑替平板去 GitHub 下载，再传给平板（平板不用能上 GitHub）；装上直接覆盖，不丢东西。</p>
          <button class="ghost" id="appReset">换一台电脑 / 重新寻找洞府</button></div>`
      : !local
      ? `<div class="card dev-card"><h3>📱 手机 / 平板</h3>
          ${android ? `<p><b>推荐装「行测修仙传」平板 App：</b>全屏打开，没有浏览器的地址栏、工具栏，自动找到电脑。
            <a class="btn-link" href="${APK}" target="_blank" rel="noopener">⬇ 下载安装包（APK）</a></p>
            <p class="small muted">下载后点开安装；如果提示“禁止安装未知来源应用”，按提示允许浏览器安装一次。
            暂时不装的话，点顶栏的 ⛶ 也能全屏。</p>`
          : `<p class="small muted">想像 App 一样全屏打开：Safari 点「分享 → 添加到主屏幕」，之后从桌面图标打开就没有浏览器的框。</p>`}
          <p class="small faint">局域网设置只能在电脑上改。</p></div>`
      : `<div class="card dev-card"><h3>📱 手机 / 平板 <small>电脑当主机，同一个 Wi-Fi 下的手机、平板用浏览器打开；数据只存电脑上这一份</small></h3>
        <div class="row" style="gap:12px;flex-wrap:wrap;align-items:center">
          <label class="switch"><input type="checkbox" id="lanOn" ${lan.enabled ? "checked" : ""}> 允许手机 / 平板连进来（局域网模式）</label>
          ${lan.restart ? `<span class="tag bad">重启程序后生效</span>` : lan.listening ? `<span class="tag ok">已开</span>` : ""}
        </div>
        ${lan.enabled ? `<div class="dev-lan">
          ${lan.qr ? `<div class="dev-qr">${lan.qr}</div>` : ""}
          <div class="dev-info">
            <div>手机 / 平板浏览器输入：${lan.urls.length ? lan.urls.map((u) => `<b class="dev-url">${esc(u)}</b>`).join(" 或 ") : "<b>（没找到局域网地址：电脑连上 Wi-Fi / 网线了吗？）</b>"}${lan.qr ? "，或者扫左边的二维码" : ""}</div>
            <div style="margin-top:6px">访问口令：<b class="dev-code">${esc(lan.code)}</b> <button class="ghost small" id="lanNewCode">换一个</button>
              <span class="small muted">第一次打开要输，之后这台设备记住</span></div>
            <details class="fold" style="margin-top:8px" open><summary>像 App 一样全屏用</summary>
              <div class="small" style="line-height:1.8"><b>安卓平板 / 手机：装「行测修仙传」App</b>（<a href="${APK}" target="_blank" rel="noopener">下载 APK</a>，
              或在平板浏览器里打开上面的地址 → 设置页里点下载）。装好打开，它会在 Wi-Fi 里自己找到这台电脑，全屏、没有浏览器的框。<br>
              苹果（iPad / iPhone，用 Safari）：打开上面的地址 →「分享」→「添加到主屏幕」，从桌面图标打开就是全屏。<br>
              电脑要开着、修仙传要在运行。</div></details>
            <details class="fold"><summary>连不上？</summary>
              <div class="small" style="line-height:1.8">① 手机和电脑连的是同一个 Wi-Fi（不要用访客网络）；② 第一次开局域网模式时，Windows 防火墙弹窗要点「允许」
              （错过了：控制面板 → Windows Defender 防火墙 → 允许应用通过防火墙，勾上修仙传 / Python 的“专用”）；③ 改了开关要重启修仙传；
              ④ 出门在外想用：电脑和手机都装 Tailscale（免费），手机用 Tailscale 给电脑的地址打开。</div></details>
          </div></div>` : `<p class="small muted" style="margin-top:8px">打开后，手机 / 平板连同一个 Wi-Fi，用浏览器输入电脑的地址（或扫二维码），输一次访问口令就能用；还能添加到主屏幕当 App 用。</p>`}
      </div>`;
    const mac = ver.platform === "darwin";
    const kind = ver.frozen ? (mac ? "Mac App" : "exe 版") : "源码版";
    const verCard = `<div class="card dev-card"><h3>🆕 版本与更新 <small>当前 ${esc(ver.version)}（${kind}）</small></h3>
      <div class="row" style="gap:10px;flex-wrap:wrap;align-items:center"><button id="updCheck">检查更新</button><span id="updMsg" class="small muted"></span></div>
      <div id="updBox"></div>
      <p class="small faint" style="margin-top:6px">${ver.frozen && mac ? "Mac App：有新版本时点「到 GitHub 下载」，下载 xingce-xiuxian-mac.zip，解压后把新的「行测修仙传」拖进「应用程序」替换旧的（存档、题库都在库里，不受影响）。"
        : ver.frozen ? "exe 版：有新版本时点「更新并重启」，自动下载、替换、重开（存档、题库都在库里，不受影响）。"
        : "源码版：照旧用压缩包更新；也可以到 GitHub 的 Releases 下载 exe 版，放进 训练/程序/ 双击就能用。"}</p>${logHtml}</div>`;
    return (local || lan ? lanCard : "") + (local ? verCard : logHtml ? `<div class="card dev-card"><h3>🆕 版本 <small>${esc(ver.version)}</small></h3>${logHtml}</div>` : "");
  }

  function bind() {
    const au = document.getElementById("appUpd");
    if (au) au.onclick = async () => {
      const msg = document.getElementById("appMsg");
      au.disabled = true; msg.textContent = "正在问电脑（电脑去 GitHub 看最新版本）…";
      let r;
      try { r = await api("/api/app/latest"); } catch (e) { msg.textContent = e.message; au.disabled = false; return; }
      au.disabled = false;
      const cur = XC.version();
      if (!r.latest) { msg.textContent = r.error || "还没有平板 App 安装包"; return; }
      if (!newer(r.latest, cur)) { msg.textContent = `已经是最新版（${cur}）` + (r.error ? `；${r.error}` : ""); return; }
      if (!r.ready) { msg.textContent = `有新版本 ${r.latest}，但电脑没下到安装包：${r.error || "再试一次"}`; return; }
      msg.innerHTML = `有新版本 <b>${esc(r.latest)}</b>（现在 ${esc(cur)}）`;
      au.textContent = `⬆ 更新到 ${r.latest}`;
      au.className = "primary";
      au.onclick = () => {
        if (XC.installApk) {                       // 新版 App：自己从电脑下载，交给系统安装
          window.xcApk = (state, text) => { msg.textContent = text; au.disabled = state === "busy"; };
          au.disabled = true;
          XC.installApk(location.origin + r.path);
        } else if (r.apk_port) {                   // 旧版 App：换个端口的链接会交给平板的浏览器下载
          msg.textContent = "已交给平板浏览器下载：下完点通知栏或下载列表里的安装包，按提示安装（第一次可能要允许浏览器安装应用）";
          location.href = `${location.protocol}//${location.hostname}:${r.apk_port}/xingce-xiuxian.apk`;
        } else {
          msg.textContent = "电脑那边要先打开局域网模式并重启修仙传";
        }
      };
    };
    const rs = document.getElementById("appReset");
    if (rs) rs.onclick = () => { if (confirm("忘掉这台电脑的地址，回到寻找洞府？")) XC.reset(); };
    const on = document.getElementById("lanOn");
    if (on) on.onchange = async () => {
      try { await api("/api/lan", { enabled: on.checked }); toast(on.checked ? "局域网模式已打开：重启修仙传后生效" : "局域网模式已关闭：重启修仙传后生效"); render(); }
      catch (e) { showError(e); }
    };
    const nc = document.getElementById("lanNewCode");
    if (nc) nc.onclick = async () => {
      if (!confirm("换一个访问口令？已经连过的手机 / 平板要重新输入。")) return;
      try { await api("/api/lan", { new_code: true }); render(); } catch (e) { showError(e); }
    };
    const chk = document.getElementById("updCheck");
    if (chk) chk.onclick = async () => {
      const msg = document.getElementById("updMsg"), box = document.getElementById("updBox");
      chk.disabled = true; msg.textContent = "正在问 GitHub…";
      try {
        UPD = await api("/api/update/check");
        if (!UPD.latest) msg.textContent = "还没有发布过 exe 版。";
        else if (!UPD.newer) msg.textContent = `已经是最新版（${UPD.current}）。`;
        else {
          msg.textContent = `有新版本 ${UPD.latest}！`;
          box.innerHTML = `<div class="upd-new">${UPD.notes ? `<div class="small">${md(UPD.notes)}</div>` : ""}
            <div class="row" style="gap:10px;margin-top:8px">${UPD.frozen && UPD.windows && UPD.asset_url ? `<button class="primary" id="updApply">更新并重启</button>` : ""}
              <a href="${esc(UPD.page)}" target="_blank" rel="noopener">到 GitHub 下载</a></div></div>`;
          const ap = document.getElementById("updApply");
          if (ap) ap.onclick = async () => {
            ap.disabled = true; ap.textContent = "下载中…（几十 MB，稍等）";
            try { await api("/api/update/apply", {}); document.body.innerHTML = '<div style="display:grid;place-items:center;height:100vh;font-size:22px;color:#e8dcc0;background:#0e1412">正在换上新版本，修仙传马上重新打开……</div>'; }
            catch (e) { showError(e); ap.disabled = false; ap.textContent = "更新并重启"; }
          };
        }
      } catch (e) { msg.textContent = e.message; }
      chk.disabled = false;
    };
  }
  window.DEVICE = { html, bind };
})();
