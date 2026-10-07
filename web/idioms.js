/* 藏经阁·成语实词录（数据来自 /api/idioms，见 rpg/idioms.py）。
   逻辑填空每做完一组，正确选项里的成语 / 实词自动收成词条，按首字拼音首字母排：
   字母索引条 → 每个字母一节 → 词条卡（释义、本题其他选项、辨析、真题跳转）。 */
(function () {
  let DATA = null;
  let Q = "";          // 词条搜索
  let EDIT = "";       // 正在修改的词条
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const LETTERS = "ABCDEFGHJKLMNOPQRSTWXYZ#".split("");

  function card(e) {
    const srcs = e.sources.map((s) => `<div class="id-src">
        <div class="id-mean"><span class="id-k">释义</span>${s.meaning ? esc(s.meaning) : '<span class="faint">解析里没有单独解释，看下面的辨析</span>'}</div>
        ${s.others.length ? `<div class="id-others"><span class="id-k">本题其他选项</span>${s.others.map((o) => `<span class="id-other" title="${esc(o.meaning || "解析里没有单独解释")}"><b>${esc(o.option)}</b> ${esc(o.word)}${o.meaning ? `<i>：${esc(o.meaning)}</i>` : ""}</span>`).join("")}</div>` : ""}
        ${s.compare ? (s.tutor || s.edited
          ? `<div class="id-cmp-short"><span class="id-k">${s.tutor && !s.edited ? "🧙 师傅辨析" : "辨析"}</span>${esc(s.compare).replace(/\n/g, "<br>")}</div>`
          : `<details class="id-cmp"><summary><span class="id-k">辨析</span>（本题解析里讲第 ${s.blank} 空的那段）</summary><div>${esc(s.compare).replace(/\n/g, "<br>")}</div></details>`) : ""}
        <div class="id-foot"><button class="ghost small id-jump" data-idkey="${esc(s.key)}" data-idq="${esc(s.id)}" data-idboard="${esc(s.board)}">↗ ${esc(s.id)}</button>
          <span class="faint small">${esc(s.paper || "")}${s.blanks > 1 ? ` · 第 ${s.blank} 空` : ""} · 正确选项 ${esc(s.answer)}「${esc(s.option_text)}」 · 收于 ${esc(s.date)}</span></div>
      </div>`).join("");
    if (EDIT === e.word) return editCard(e);
    const d = e.detail, o = d?.origin || {};
    const detail = !d ? "" : `<div class="id-detail">
        ${(d.chars || []).length ? `<div class="id-chars"><span class="id-k">🔍 逐字</span>${d.chars.map((c) => `<span class="id-char"><b>${esc(c.char)}</b>：${esc(c.meaning)}${
          (c.like || []).length ? `<i>（同样用法：${c.like.map(esc).join("、")}）</i>` : ""}</span>`).join("")}</div>` : ""}
        ${o.from || o.text || o.note ? `<div class="id-origin"><span class="id-k">📜 出处</span>${o.from && o.from !== "不详" ? `<b>${esc(o.from)}</b>` : ""}${
          o.text ? `<span class="id-quote">“${esc(o.text)}”</span>` : ""}${o.note ? `<span class="id-onote">${esc(o.note)}</span>` : ""}</div>` : ""}</div>`;
    return `<div class="id-card" id="idw-${esc(e.word)}"><div class="id-head"><span class="id-word">${esc(e.word)}</span><span class="id-letter">${esc(e.letter)}</span>
        ${e.sources.length > 1 ? `<span class="tag">考过 ${e.sources.length} 次</span>` : ""}</div>${detail}${srcs}
      <div class="id-acts"><button class="ghost small" data-idedit="${esc(e.word)}">✏ 修改</button><button class="ghost small" data-iddel="${esc(e.word)}">🗑 删除</button>
        <button class="small id-tutor" data-idtutor="${esc(e.word)}" title="让师傅把这几个词的区别用一句话讲清（替换上面的辨析）；成语再讲关键字和出处。答疑过的词会自动做成玉简（修炼殿 · 逻辑填空 › 成语实词录）背">🧙 师傅答疑</button></div></div>`;
  }

  function editCard(e) {
    return `<div class="id-card editing" id="idw-${esc(e.word)}"><div class="id-head"><label class="small muted">词条 <input id="idEdWord" value="${esc(e.word)}" maxlength="12"></label></div>
      ${e.sources.map((s, i) => `<div class="id-src"><div class="small faint">${esc(s.id)}${s.blanks > 1 ? ` · 第 ${s.blank} 空` : ""}</div>
        <label class="small muted">释义<textarea rows="2" data-edmean="${i}">${esc(s.meaning)}</textarea></label>
        <label class="small muted">辨析<textarea rows="4" data-edcmp="${i}">${esc(s.compare)}</textarea></label></div>`).join("")}
      <div class="id-acts"><button class="primary small" id="idEdSave">保存</button><button class="ghost small" id="idEdCancel">取消</button>
        <span class="small muted">改过的不会被以后的收录覆盖</span></div></div>`;
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
    document.querySelectorAll("[data-idedit]").forEach((b) => (b.onclick = () => { EDIT = b.dataset.idedit; rerender(); scrollTo(EDIT); }));
    if ($("#idEdCancel")) $("#idEdCancel").onclick = () => { const w = EDIT; EDIT = ""; rerender(); scrollTo(w); };
    if ($("#idEdSave")) $("#idEdSave").onclick = async () => {
      const sources = {};
      document.querySelectorAll("[data-edmean]").forEach((t) => { (sources[t.dataset.edmean] ||= {}).meaning = t.value; });
      document.querySelectorAll("[data-edcmp]").forEach((t) => { (sources[t.dataset.edcmp] ||= {}).compare = t.value; });
      const nw = $("#idEdWord").value.trim();
      try {
        DATA = await api("/api/idioms/edit", { word: EDIT, new_word: nw, sources });
        toast("已保存「" + nw + "」"); EDIT = ""; rerender(); scrollTo(nw);
      } catch (e) { showError(e); }
    };
    document.querySelectorAll("[data-iddel]").forEach((b) => (b.onclick = async () => {
      const w = b.dataset.iddel;
      if (!confirm(`删除词条「${w}」？以后收录也不会再把它收回来。`)) return;
      try { DATA = await api("/api/idioms/delete", { word: w }); toast("已删除「" + w + "」"); rerender(); } catch (e) { showError(e); }
    }));
    document.querySelectorAll("[data-idtutor]").forEach((b) => (b.onclick = async () => {
      const w = b.dataset.idtutor;
      b.disabled = true; b.textContent = "🧙 师傅思考中…";
      try { DATA = await api("/api/idioms/tutor", { word: w }); toast("师傅答疑好了：「" + w + "」的辨析已更新，也收进了修炼殿的玉简（逻辑填空 › 成语实词录）"); rerender(); scrollTo(w); }
      catch (e) { showError(e); b.disabled = false; b.textContent = "🧙 师傅答疑"; }
    }));
    // 真题跳转：切到经卷，搜这道题的编号并直接展开
    document.querySelectorAll(".id-jump").forEach((b) => (b.onclick = () => {
      LIB.tab = "yujian";
      Object.assign(LIB.yj, { q: b.dataset.idq, board: b.dataset.idboard, topic: "", status: "", page: 0, openKey: b.dataset.idkey, from: "idioms" });
      window.scrollTo(0, 0);
      window.render();
    }));
  }
  function scrollTo(w) {
    const el = document.getElementById("idw-" + w);
    if (el) el.scrollIntoView({ block: "center" });
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
