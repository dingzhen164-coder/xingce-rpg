/* 设置页的两张卡：📱 手机 / 平板（局域网模式、地址、二维码、访问口令、添加到主屏幕的做法）和 🆕 版本与更新。
   数据：GET/POST /api/lan、GET /api/version、GET /api/update/check、POST /api/update/apply（见 rpg/lan.py、rpg/update.py） */
(function () {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const local = ["127.0.0.1", "localhost", "::1", "[::1]"].includes(location.hostname);
  let UPD = null;

  async function html() {
    let lan = null, ver = null;
    try { [lan, ver] = await Promise.all([api("/api/lan"), api("/api/version")]); } catch (e) { return ""; }
    const lanCard = !local
      ? `<div class="card dev-card"><h3>📱 手机 / 平板</h3><p class="small muted">你正在用手机 / 平板通过局域网访问电脑上的修仙传。
          想像 App 一样从桌面打开：苹果点浏览器的「分享 → 添加到主屏幕」，安卓点浏览器菜单里的「添加到主屏幕」。局域网设置只能在电脑上改。</p></div>`
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
            <details class="fold" style="margin-top:8px"><summary>像 App 一样放到桌面</summary>
              <div class="small" style="line-height:1.8">苹果（iPad / iPhone，用 Safari）：打开上面的地址 → 底部「分享」→「添加到主屏幕」。<br>
              安卓（Chrome / 自带浏览器）：打开地址 → 右上角菜单 →「添加到主屏幕」或「安装应用」。<br>
              之后点桌面上的「修仙传」图标就全屏打开。电脑要开着、修仙传要在运行。</div></details>
            <details class="fold"><summary>连不上？</summary>
              <div class="small" style="line-height:1.8">① 手机和电脑连的是同一个 Wi-Fi（不要用访客网络）；② 第一次开局域网模式时，Windows 防火墙弹窗要点「允许」
              （错过了：控制面板 → Windows Defender 防火墙 → 允许应用通过防火墙，勾上修仙传 / Python 的“专用”）；③ 改了开关要重启修仙传；
              ④ 出门在外想用：电脑和手机都装 Tailscale（免费），手机用 Tailscale 给电脑的地址打开。</div></details>
          </div></div>` : `<p class="small muted" style="margin-top:8px">打开后，手机 / 平板连同一个 Wi-Fi，用浏览器输入电脑的地址（或扫二维码），输一次访问口令就能用；还能添加到主屏幕当 App 用。</p>`}
      </div>`;
    const verCard = `<div class="card dev-card"><h3>🆕 版本与更新 <small>当前 ${esc(ver.version)}（${ver.frozen ? "exe 版" : "源码版"}）</small></h3>
      <div class="row" style="gap:10px;flex-wrap:wrap;align-items:center"><button id="updCheck">检查更新</button><span id="updMsg" class="small muted"></span></div>
      <div id="updBox"></div>
      <p class="small faint" style="margin-top:6px">${ver.frozen ? "exe 版：有新版本时点「更新并重启」，自动下载、替换、重开（存档、题库都在库里，不受影响）。"
        : "源码版：照旧用压缩包更新；也可以到 GitHub 的 Releases 下载 exe 版，放进 训练/程序/ 双击就能用。"}</p></div>`;
    return (local || lan ? lanCard : "") + (local ? verCard : "");
  }

  function bind() {
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
