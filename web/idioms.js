/* 藏经阁·成语实词录（数据来自 /api/idioms，见 rpg/idioms.py）。
   逻辑填空每做完一组，正确选项里的成语 / 实词自动收成词条，按首字拼音首字母排：
   字母索引条 → 每个字母一节 → 词条卡（释义、本题其他选项、辨析、真题跳转）。 */
(function () {
  let DATA = null;
  let Q = "";          // 词条搜索
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const LETTERS = "ABCDEFGHJKLMNOPQRSTWXYZ#".split("");

  function card(e) {
    const srcs = e.sources.map((s) => `<div class="id-src">
        <div class="id-mean"><span class="id-k">释义</span>${s.meaning ? esc(s.meaning) : '<span class="faint">解析里没有单独解释，看下面的辨析</span>'}</div>
        ${s.others.length ? `<div class="id-others"><span class="id-k">本题其他选项</span>${s.others.map((o) => `<span class="id-other" title="${esc(o.meaning || "解析里没有单独解释")}"><b>${esc(o.option)}</b> ${esc(o.word)}${o.meaning ? `<i>：${esc(o.meaning)}</i>` : ""}</span>`).join("")}</div>` : ""}
        ${s.compare ? `<details class="id-cmp"><summary><span class="id-k">辨析</span>（本题解析里讲第 ${s.blank} 空的那段）</summary><div>${esc(s.compare).replace(/\n/g, "<br>")}</div></details>` : ""}
        <div class="id-foot"><button class="ghost small id-jump" data-idkey="${esc(s.key)}" data-idq="${esc(s.id)}" data-idboard="${esc(s.board)}">↗ ${esc(s.id)}</button>
          <span class="faint small">${esc(s.paper || "")}${s.blanks > 1 ? ` · 第 ${s.blank} 空` : ""} · 正确选项 ${esc(s.answer)}「${esc(s.option_text)}」 · 收于 ${esc(s.date)}</span></div>
      </div>`).join("");
    return `<div class="id-card" id="idw-${esc(e.word)}"><div class="id-head"><span class="id-word">${esc(e.word)}</span><span class="id-letter">${esc(e.letter)}</span>
        ${e.sources.length > 1 ? `<span class="tag">考过 ${e.sources.length} 次</span>` : ""}</div>${srcs}</div>`;
  }

  function html() {
    const d = DATA;
    const list = Q ? d.entries.filter((e) => e.word.includes(Q) || e.sources.some((s) => s.others.some((o) => o.word.includes(Q)))) : d.entries;
    const bar = `<div class="card id-bar"><div class="row">
        <input id="idQ" placeholder="查词：成语或实词（本题其他选项里的词也能查到）" value="${esc(Q)}">
        <button class="primary" id="idGo">查</button>
        <button class="ghost" id="idFill" title="把以前做过的逻辑填空题（作答记录里有的）一次收进来">⟳ 收录以前做过的逻辑填空</button></div>
      <div class="id-letters">${LETTERS.map((L) => `<a class="${d.letters[L] ? "" : "off"}" data-idletter="${L}">${L}<small>${d.letters[L] || ""}</small></a>`).join("")}</div>
      <p class="small muted" style="margin:6px 0 0">共 ${d.total} 个词条。逻辑填空每做完一组，正确选项里的成语 / 实词自动收进来（关联词、虚词不收），同时写进 训练/${esc(d.file)}。</p></div>`;
    if (!list.length) {
      return bar + `<p class="muted lib-tip">${Q ? "没有查到这个词。" : "还没有词条：去修炼殿做一组逻辑填空（板块试炼、知识点试炼、整套试炼都行），交卷后自动收录；或者点上面的「收录以前做过的逻辑填空」。"}</p>`;
    }
    let cur = null, out = "";
    for (const e of list) {
      if (e.letter !== cur) {
        if (cur !== null) out += "</div>";
        cur = e.letter;
        out += `<h3 class="id-sec" id="idl-${esc(cur)}">${esc(cur)}</h3><div class="id-grid">`;
      }
      out += card(e);
    }
    return bar + out + "</div>";
  }

  async function render() {
    DATA = await api("/api/idioms");
    return html();
  }

  function bind() {
    const go = () => { Q = $("#idQ").value.trim(); rerender(); };
    if ($("#idGo")) { $("#idGo").onclick = go; $("#idQ").onkeydown = (e) => { if (e.key === "Enter") go(); }; }
    const fill = $("#idFill");
    if (fill) fill.onclick = async () => {
      fill.disabled = true; fill.textContent = "收录中…";
      try {
        const r = await api("/api/idioms/backfill", {});
        DATA = r;
        toast(`扫了 ${r.scanned} 道做过的逻辑填空，新收 ${r.new.length} 个词条（共 ${r.total} 个）`);
        rerender();
      } catch (e) { showError(e); fill.disabled = false; }
    };
    document.querySelectorAll("[data-idletter]").forEach((a) => (a.onclick = () => {
      const el = document.getElementById("idl-" + a.dataset.idletter);
      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    }));
    // 真题跳转：切到玉简，搜这道题的编号并直接展开
    document.querySelectorAll(".id-jump").forEach((b) => (b.onclick = () => {
      LIB.tab = "yujian";
      Object.assign(LIB.yj, { q: b.dataset.idq, board: b.dataset.idboard, topic: "", status: "", page: 0, openKey: b.dataset.idkey, from: "idioms" });
      window.scrollTo(0, 0);
      window.render();
    }));
  }
  function rerender() {
    const v = document.getElementById("view");
    const box = v && v.querySelector(".id-root");
    if (!box || !DATA) return;
    box.innerHTML = html();
    bind();
  }
  window.IDIOMS = { render, bind };
})();
