/* 大典画面：境界突破、渡劫成功、宗门大比出成绩时弹出的一整屏（仿“觅长生”那种：墨色夜空、一轮金月、青玉山峦与云雾、
   灵鱼在空中游、落叶飘、月前一个大字，下面一条青色横幅写一段话，再是 ——◇ 小标题 ◇—— 和几行属性，最后一个橙色「确 定」）。
   全部用 SVG / CSS 画，不用图片。用法：
     CEREMONY.show({ title: "化神", subtitle: "化神初期", text: "…", stats: [["道行", "70 分"], …], tone: "jade" }) → Promise（点确定后 resolve）
     CEREMONY.realm(event)   境界提升事件 → 自动配文案
     CEREMONY.contest(info)  宗门大比出成绩 */
(function () {
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const queue = [];
  let busy = false;

  // 每个大境界一段话（原创，按行测修行的意思写）
  const REALM_TEXT = {
    "炼气": "天地灵气顺着周身经脉缓缓流转，丹田深处第一缕真气凝而不散。你终于摸到了修行的门槛——从今往后，每一道真题都是吐纳的灵气，每一次复盘都是周天的运转。",
    "筑基": "千百缕灵气在丹田中汇聚、压实，化作一方坚不可摧的道基。你忽然明白，那些背过的口诀、斩过的心魔，原来都在悄悄夯筑这块基石。根基既成，往后的修为都将立于其上。",
    "金丹": "真元在丹田中旋转、凝缩，一枚金丹缓缓成形，光华内敛。识海从未如此清明，题干里的陷阱、选项间的毫厘之差，竟能一眼看穿。只是丹成之后，道途愈险，切莫懈怠。",
    "元婴": "金丹碎裂的刹那，一个与你一般无二的元婴盘坐丹田，缓缓睁开双眼。神识离体巡游，各板块的功法彼此勾连，在你眼前铺成一张脉络分明的网。你已能以一念统摄万法。",
    "化神": "元婴与神识合而为一，周天法则在识海中纤毫毕现。你仿佛举手投足便能拆解任何一道难题，可下一刻又被一股更宏大的意志轻轻按回肉身——那是考场的天道，也是你还需敬畏的东西。",
    "大乘": "万法归一，心如止水。曾经令你夜不能寐的数量关系、资料分析，如今不过是掌中纹路。你站在山巅回望来路，每一层台阶都刻着你熬过的晨昏。离飞升，只差最后一步。",
    "真仙": "雷劫散尽，天门洞开。你终于踏碎虚空，羽化登仙——那一纸录取通知，便是你的仙籍。回首这一路，所有的苦修都有了意义。",
  };
  const MINOR = [
    "体内真元又凝实了一分，经脉中流转的灵气愈发浑厚。小境界的门槛悄然跨过，你知道，这是日复一日的功课换来的。",
    "一夜修炼，识海中又亮起一盏灯。那些曾经模糊的考点，此刻变得清晰可触。修为精进，再上一层。",
    "灵气在周天里多转了一圈，便多一分沉稳。你没有停下，只是把这一层的感悟默默收进了心里。",
  ];

  function stageOf(name) {
    const m = String(name || "").match(/^(.{2})/);
    return m ? m[1] : name;
  }

  // 一条“灵鱼”：长鳍、分叉尾，青玉半透明
  const FISH = `<svg viewBox="0 0 220 110" class="cer-fish-svg"><defs>
      <linearGradient id="cerFishG" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#bff5e8"/><stop offset=".55" stop-color="#5fc7b3"/><stop offset="1" stop-color="#1f6f66"/></linearGradient></defs>
    <path d="M30 58 C55 30 120 26 160 48 C170 53 170 60 160 64 C122 82 58 84 30 58 Z" fill="url(#cerFishG)"/>
    <path d="M158 54 L212 22 L196 56 L214 92 Z" fill="url(#cerFishG)" opacity=".85"/>
    <path d="M78 44 C86 8 128 -2 142 8 C122 16 108 30 96 46 Z" fill="url(#cerFishG)" opacity=".75"/>
    <path d="M86 70 C92 92 118 102 130 98 C116 90 104 80 98 70 Z" fill="url(#cerFishG)" opacity=".6"/>
    <circle cx="48" cy="54" r="3.2" fill="#0d2f2b"/>
    <path d="M40 62 C70 70 120 70 156 60" stroke="#e8fff9" stroke-width="1.2" fill="none" opacity=".5"/></svg>`;

  // 一侧的山：两层青玉峰 + 亮边
  const MOUNT = (flip) => `<svg viewBox="0 0 520 260" class="cer-mount ${flip ? "r" : "l"}" preserveAspectRatio="none"><defs>
      <linearGradient id="cerM1${flip ? "r" : "l"}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#8fd8c8"/><stop offset=".35" stop-color="#3c8f86"/><stop offset="1" stop-color="#0a2321"/></linearGradient>
      <linearGradient id="cerM2${flip ? "r" : "l"}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#5fb0a4"/><stop offset="1" stop-color="#061615"/></linearGradient></defs>
    <path d="M0 260 L0 170 L60 120 L95 140 L150 60 L185 95 L215 40 L260 110 L300 90 L340 150 L400 140 L455 205 L520 258 L520 260 Z" fill="url(#cerM2${flip ? "r" : "l"})" opacity=".85"/>
    <path d="M40 260 L90 180 L130 200 L190 110 L230 150 L270 95 L320 170 L370 160 L420 220 L470 230 L520 260 Z" fill="url(#cerM1${flip ? "r" : "l"})"/>
    <path d="M190 110 L230 150 M270 95 L320 170" stroke="#d9fff5" stroke-width="2" opacity=".55" fill="none"/></svg>`;

  function sparks(n) {
    return Array.from({ length: n }, () => {
      const a = Math.random() * Math.PI * 2, r = 46 + Math.random() * 10;
      return `<i style="left:${50 + r * Math.cos(a)}%;top:${50 + r * Math.sin(a)}%;animation-delay:${(Math.random() * 3).toFixed(2)}s"></i>`;
    }).join("");
  }
  function leaves(n) {
    return Array.from({ length: n }, () => `<b style="left:${(Math.random() * 100).toFixed(1)}%;top:${(Math.random() * 70).toFixed(1)}%;
      animation-delay:${(Math.random() * 8).toFixed(2)}s;animation-duration:${(9 + Math.random() * 8).toFixed(1)}s;--rot:${Math.round(Math.random() * 360)}deg;
      --s:${(0.6 + Math.random() * 0.8).toFixed(2)}"></b>`).join("");
  }

  function build(o) {
    const el = document.createElement("div");
    el.className = "ceremony tone-" + (o.tone || "jade");
    const title = esc(o.title || "");
    el.innerHTML = `
      <div class="cer-sky">${leaves(14)}</div>
      <div class="cer-stage">
        <div class="cer-moon"><div class="cer-ring">${sparks(26)}</div></div>
        ${MOUNT(false)}${MOUNT(true)}
        <svg class="cer-ridge" viewBox="0 0 1000 120" preserveAspectRatio="none"><defs>
          <linearGradient id="cerRidge" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#cfeee6" stop-opacity=".55"/><stop offset=".35" stop-color="#2e6d66" stop-opacity=".9"/><stop offset="1" stop-color="#071a18"/></linearGradient></defs>
          <path d="M0 120 L0 70 C80 40 140 64 210 52 C290 38 340 70 420 58 C470 50 520 40 560 52 C640 74 700 44 780 54 C860 64 920 46 1000 60 L1000 120 Z" fill="url(#cerRidge)"/></svg>
        <div class="cer-mist m1"></div><div class="cer-mist m2"></div><div class="cer-mist m3"></div>
        <div class="cer-fish f1">${FISH}</div><div class="cer-fish f2">${FISH}</div><div class="cer-fish f3">${FISH}</div>
        <div class="cer-title ${title.length > 2 ? "long" : ""}">${[...(o.title || "")].map((c, i) => `<span style="animation-delay:${0.25 + i * 0.22}s">${esc(c)}</span>`).join("")}</div>
      </div>
      <div class="cer-band">
        <p class="cer-text">${esc(o.text || "")}</p>
        ${o.subtitle ? `<div class="cer-sub"><i></i><span>${esc(o.subtitle)}</span><i></i></div>` : ""}
        ${(o.stats || []).length ? `<div class="cer-stats">${o.stats.map((row) => `<div>${row.map(([k, v]) => `<span><em>${esc(k)}：</em>${esc(v)}</span>`).join("")}</div>`).join("")}</div>` : ""}
      </div>
      <button class="cer-ok">${esc(o.button || "确 定")}</button>`;
    return el;
  }

  function show(o) {
    return new Promise((resolve) => { queue.push([o, resolve]); next(); });
  }
  function next() {
    if (busy || !queue.length) return;
    busy = true;
    const [o, resolve] = queue.shift();
    const el = build(o);
    document.body.appendChild(el);
    requestAnimationFrame(() => el.classList.add("in"));
    let done = false;
    const close = () => {
      if (done) return;
      done = true;
      document.removeEventListener("keydown", key);
      el.classList.add("out");
      setTimeout(() => { el.remove(); busy = false; resolve(); next(); }, 600);
    };
    const key = (e) => { if (e.key === "Enter" || e.key === "Escape") close(); };
    setTimeout(() => document.addEventListener("keydown", key), 800);     // 刚弹出时别被正在按的回车直接关掉
    el.querySelector(".cer-ok").onclick = close;
  }

  // 境界提升：大境界（含渡劫）配大段文案；小境界一句
  function realm(e) {
    const big = stageOf(e.big_name || e.name);
    const major = !!e.major;
    const text = e.tribulation
      ? `天雷滚滚而下，一道接着一道。你咬紧牙关、守住道心，以平日斩过的心魔、背熟的口诀为盾，硬生生扛过了全部雷劫。雷云散去，${REALM_TEXT[big] || "境界豁然开朗。"}`
      : major ? (REALM_TEXT[big] || "瓶颈松动，灵气如潮水般涌入经脉，你踏入了新的大境界。")
        : MINOR[Math.floor(Math.random() * MINOR.length)];
    const stats = [[["道行", `${e.score} 分`], ["目标", `${e.target || "—"} 分`]]];
    if (e.next) stats.push([["下一境", e.next], ...(e.from ? [["来自", e.from]] : [])]);
    return show({ title: major ? big : e.name, subtitle: e.name, text, stats, tone: e.tribulation ? "gold" : "jade" });
  }

  // 宗门大比出成绩
  function contest(s, prev) {
    const diff = s.avg != null ? s.score - s.avg : null;
    let text;
    if (diff == null) text = `第 ${s.season} 季宗门大比落幕。你交出了 ${s.score} 分的答卷——成绩已录入宗门名册，且看下回如何。`;
    else if (diff >= 10) text = `第 ${s.season} 季宗门大比，你出手便压住了全场，比同门平均高出 ${diff.toFixed(1)} 分。长老们交头接耳：此子道基扎实，假以时日，必成大器。只是山外有山，榜首仍在前方。`;
    else if (diff >= 0) text = `第 ${s.season} 季宗门大比，你稳稳胜过同门平均 ${diff.toFixed(1)} 分。不算惊艳，却也守住了自己的位置。差距藏在几个薄弱板块里——回去把心魔一只只斩了，下一季再争。`;
    else text = `第 ${s.season} 季宗门大比，你比同门平均低了 ${(-diff).toFixed(1)} 分。败一场不丢人，丢人的是不知道败在哪。去心魔录里看看这一季的错题，它们就是你下一次突破的台阶。`;
    if (prev && prev.score != null) {
      const d = s.score - prev.score;
      text += d > 0 ? `比上一季精进 ${d.toFixed(1)} 分。` : d < 0 ? `比上一季回落 ${(-d).toFixed(1)} 分，稳住心神。` : "与上一季持平。";
    }
    const mods = (s.modules || []).filter((m) => m.total);
    const best = mods.slice().sort((a, b) => b.acc - a.acc)[0], worst = mods.slice().sort((a, b) => a.acc - b.acc)[0];
    const stats = [[["得分", `${s.score}`], ["大比平均", s.avg ?? "—"], ["最高分", s.top ?? "—"]],
                   [["已击败", s.beat != null ? s.beat + "%" : "—"], ["排名", s.rank ? `${s.rank} / ${s.people || "?"}` : "—"]]];
    if (best && worst && best !== worst) stats.push([["最强", `${best.name} ${Math.round(best.acc * 100)}%`], ["最弱", `${worst.name} ${Math.round(worst.acc * 100)}%`]]);
    const tone = diff == null || diff >= 0 ? "gold" : "crimson";
    return show({ title: "大比", subtitle: `第 ${s.season} 季 · 宗门大比`, text, stats, tone });
  }

  window.CEREMONY = { show, realm, contest };
})();
