/* =========================================================================
 * AI 执行计划 — 渲染逻辑（AI 执行报告的「计划」侧）
 * 职责：读取 window.__AIRUNS__（与 index.html 执行结果共用同一份数据），按 build 渲染计划页：
 *       Build 元信息 + 执行工作流 stepper + 计划时间线甘特（手写内联 SVG）+ 步骤依赖表 + 需求功能点比对清单。
 * 业务背景：完全离线运行，零第三方库，图表手写内联 SVG（与 app.js 同风格、共用 style.css）。
 *           计划侧主要读 step.plannedStatus / step.type / step.output / features，结果侧（app.js）读 actualStatus / defects 等。
 * 路由：① hash #/build/<build> 直达；② 兼容 ?build=<build>（boot 时转 hash）；无参时取最新 build。
 * ========================================================================= */
(function () {
  "use strict";

  // 计划状态文案（plannedStatus）：done 已完成 / plan 计划 / skip 跳过 / doing 进行中 / fail 失败 / pend 待处理
  var PLAN_TEXT = { done: "✅ 完成", plan: "⏳ 计划", skip: "⏭️ 跳过", doing: "🔵 进行中", fail: "❌ 失败", pend: "⚠️ 待处理" };
  // 计划状态 → badge 样式类（与 style.css .badge.* 对齐）
  var PLAN_BADGE = { done: "done", plan: "plan", skip: "skip", doing: "doing", fail: "fail", pend: "pend" };
  // 功能点完成状态文案 / badge
  var FEATURE_TEXT = { done: "✅ 完成", doing: "🔵 进行中", fail: "❌ 未完成", pend: "⏸ 待决策", skip: "⏭️ 跳过" };
  var FEATURE_BADGE = { done: "done", doing: "doing", fail: "fail", pend: "pend", skip: "skip" };
  // 步骤类型 → 默认计划耗时（分钟），用于甘特：当 step.duration 未知（"—"）时按类型估算
  var TYPE_MIN = { 准备: 5, 前置: 5, 规划: 18, 构建: 3, 开发: 120, 部署: 12, 测试: 60, 报告: 5, 审计: 20 };
  var CHEV = '<svg class="chev" viewBox="0 0 24 24"><path d="M9 6l6 6-6 6"/></svg>';

  /* ------------------------- 小工具 ------------------------- */
  function esc(s) {
    if (s == null) return "";
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function $(sel) { return document.querySelector(sel); }
  // 兄弟「AI测试报告」目录相对前缀：按当前页所在报告目录名【运行时推导】，兼容本地中文目录与部署英文 slug，
  // 二者均不识别时回退英文 slug——避免硬编码中文目录、部署后 404。
  function testReportBase() {
    var path = (typeof location !== "undefined" && location.pathname) || "";
    try { path = decodeURIComponent(path); } catch (e) {}
    var segs = path.split("/").filter(Boolean);
    var dir = segs.length >= 2 ? segs[segs.length - 2] : "";
    var map = { "AI执行报告": "AI测试报告", "ai-execution-report": "ai-test-report" };
    return "../" + (map[dir] || "ai-test-report") + "/";
  }
  // 解析耗时字符串 → 分钟：支持 "2h10m" / "40m" / "1h" / "8 小时 30 分"；无法解析返回 null
  function durMin(s) {
    if (s == null) return null;
    s = String(s);
    var min = 0, hit = false;
    var h = s.match(/(\d+)\s*(?:h|小时|时)/); if (h) { min += parseInt(h[1], 10) * 60; hit = true; }
    var m = s.match(/(\d+)\s*(?:m|分)/); if (m) { min += parseInt(m[1], 10); hit = true; }
    return hit ? min : null;
  }
  // 步骤计划耗时（分钟）：优先实际 duration，其次按类型估算，兜底 15
  function planMin(step) {
    var d = durMin(step.duration);
    if (d != null && d > 0) return d;
    return TYPE_MIN[step.type] || 15;
  }

  /* ------------------------- 数据 ------------------------- */
  var RUNS = (window.__AIRUNS__ || []).slice().sort(function (a, b) { return a.buildNo - b.buildNo; });

  // 折叠章节包装（与结果页同构）
  function chap(num, title, sub, inner) {
    return '<details class="chapter" open><summary>' + CHEV
      + '<span class="eyebrow"><span class="n">' + num + '</span>' + esc(title) + '</span>'
      + (sub ? '<span class="sub">' + esc(sub) + '</span>' : "")
      + '</summary><div class="chapter-inner">' + inner + '</div></details>';
  }
  function metaItem(k, v, wide) { return '<div class="meta-item' + (wide ? ' wide' : '') + '"><span class="meta-k">' + esc(k) + '</span><span class="meta-v">' + esc(v || "—") + '</span></div>'; }

  /* ------------------------- 工作流 stepper ------------------------- */
  // 计划状态 → stepper 圆点样式类
  function stepperDotCls(s) { return PLAN_BADGE[s] || "plan"; }
  function renderStepper(steps) {
    if (!steps.length) return '<div class="empty-tip">无步骤数据</div>';
    var nodes = steps.map(function (s, i) {
      var st = s.plannedStatus || "plan";
      return '<div class="snode ' + stepperDotCls(st) + '">'
        + '<div class="sdot">' + (i + 1) + '</div>'
        + '<div class="sbody"><div class="stitle">' + esc(s.name) + '</div>'
        + '<div class="smeta"><span class="step-type">' + esc(s.type || "—") + '</span>'
        + '<span class="badge ' + (PLAN_BADGE[st] || "plan") + '">' + esc(PLAN_TEXT[st] || "⏳ 计划") + '</span>'
        + (s.duration && s.duration !== "—" ? '<span class="sdur">计划/实际 ' + esc(s.duration) + '</span>' : '<span class="sdur">计划 ~' + planMin(s) + 'm</span>')
        + '</div>'
        + (s.output ? '<div class="sout">' + esc(s.output) + '</div>' : "")
        + '</div></div>';
    }).join("");
    return '<div class="stepper">' + nodes + '</div>';
  }

  /* ------------------------- 计划时间线（甘特，手写 SVG）------------------------- */
  function svgGantt(steps) {
    if (!steps.length) return '<div class="empty-tip">无步骤数据</div>';
    var rowH = 30, padT = 8, padB = 26, labelW = 150, barPad = 10;
    var W = 760, innerW = W - labelW - barPad - 12;
    var H = padT + steps.length * rowH + padB;
    var cum = 0, total = 0, segs = [];
    steps.forEach(function (s) { var m = planMin(s); segs.push({ s: s, start: cum, len: m }); cum += m; });
    total = cum || 1;
    var grid = "";
    [0, 0.25, 0.5, 0.75, 1].forEach(function (f) {
      var x = labelW + barPad + f * innerW;
      grid += '<line x1="' + x.toFixed(1) + '" y1="' + padT + '" x2="' + x.toFixed(1) + '" y2="' + (H - padB) + '" class="chart-grid"/>'
        + '<text x="' + x.toFixed(1) + '" y="' + (H - padB + 16) + '" text-anchor="middle" font-size="10" class="chart-axis">' + Math.round(f * total) + 'm</text>';
    });
    var rows = segs.map(function (g, i) {
      var st = g.s.plannedStatus || "plan";
      var y = padT + i * rowH;
      var bx = labelW + barPad + (g.start / total) * innerW;
      var bw = Math.max(3, (g.len / total) * innerW);
      // 标题（步骤名）直接限制为 10 个字符，超出截断加省略号；完整名仍由 <title> 悬浮显示
      var nm = g.s.name.length > 10 ? g.s.name.slice(0, 10) + "…" : g.s.name;
      return '<text x="' + (labelW - 4) + '" y="' + (y + rowH / 2 + 4) + '" text-anchor="end" font-size="11" class="chart-lbl">' + esc(nm) + '</text>'
        + '<rect x="' + bx.toFixed(1) + '" y="' + (y + 6) + '" width="' + bw.toFixed(1) + '" height="' + (rowH - 14) + '" rx="4" class="gbar ' + (PLAN_BADGE[st] || "plan") + '"><title>' + esc(g.s.name) + ' · ' + g.len + 'm</title></rect>'
        + '<text x="' + (bx + bw + 5).toFixed(1) + '" y="' + (y + rowH / 2 + 4) + '" font-size="10" class="chart-axis">' + g.len + 'm</text>';
    }).join("");
    return '<svg viewBox="0 0 ' + W + ' ' + H + '" width="100%" height="' + H + '" role="img" class="gantt-svg">' + grid + rows + '</svg>'
      + '<div class="chart-caption">横轴：计划累计耗时（分钟）｜ 已完成步骤用实际耗时，未发生步骤按类型估算</div>';
  }

  /* ------------------------- 步骤依赖表 ------------------------- */
  function renderDepTable(steps) {
    var rows = steps.map(function (s, i) {
      var st = s.plannedStatus || "plan";
      var dep = s.dep ? s.dep : (i === 0 ? "—" : (i) + " " + (steps[i - 1].name.length > 30 ? steps[i - 1].name.slice(0, 29) + "…" : steps[i - 1].name));
      return '<tr><td class="wrap"><strong>' + esc(s.name) + '</strong></td>'
        + '<td><span class="step-type">' + esc(s.type || "—") + '</span></td>'
        + '<td class="wrap muted">' + esc(dep) + '</td>'
        + '<td class="wrap muted">' + esc(s.artifact || s.output || "—") + '</td>'
        + '<td><span class="badge ' + (PLAN_BADGE[st] || "plan") + '">' + esc(PLAN_TEXT[st] || "⏳ 计划") + '</span></td></tr>';
    }).join("") || '<tr><td colspan="5" class="empty-tip">无步骤数据</td></tr>';
    return '<div class="table-wrap"><table class="report-table">'
      + '<thead><tr><th>步骤</th><th>类型</th><th>依赖前置</th><th>预期产物</th><th>计划状态</th></tr></thead>'
      + '<tbody>' + rows + '</tbody></table></div>';
  }

  /* ------------------------- 需求功能点比对清单 ------------------------- */
  function featureEvidence(f) {
    if (f.status === "done") return (f.sprint ? f.sprint + " 已归档" : "已完成") + (f.duration ? "（" + f.duration + "）" : "");
    if (f.status === "pend" || f.status === "doing") return f.reason ? f.reason : "待跟进";
    if (f.status === "fail") return f.reason ? f.reason : "未完成";
    if (f.status === "skip") return "本 build 跳过";
    return "—";
  }
  function renderFeatureTable(features) {
    var rows = features.map(function (f) {
      var st = f.status || "pend";
      return '<tr><td><span class="req-id">' + esc(f.reqId || ("FP-" + f.num)) + '</span></td>'
        + '<td class="wrap"><strong>' + esc(f.name) + '</strong></td>'
        + '<td class="wrap muted">' + esc(f.reqSource || "—") + '</td>'
        + '<td>' + esc(f.sprint || "—") + '</td>'
        + '<td style="text-align:center">✅</td>'
        + '<td><span class="badge ' + (FEATURE_BADGE[st] || "pend") + '">' + esc(FEATURE_TEXT[st] || "⏸ 待决策") + '</span></td>'
        + '<td class="wrap muted">' + esc(featureEvidence(f)) + '</td></tr>';
    }).join("") || '<tr><td colspan="7" class="empty-tip">无需求功能点数据</td></tr>';
    var done = features.filter(function (f) { return f.status === "done"; }).length;
    var note = '<p class="funnel-link" style="margin:0 0 14px"><b>说明</b> 逐条对照需求文档功能规格点，标注本 build 计划纳入与完成情况。计划纳入 ✅ = 本 build 应交付；状态/证据为对照实际开发结果的回填。</p>';
    var sum = '<div class="chart-caption" style="margin-top:10px">需求功能点共 ' + features.length + ' 项 · 计划纳入 ' + features.length + ' 项 · 已完成 ' + done + ' 项</div>';
    return note + '<div class="table-wrap"><table class="report-table">'
      + '<thead><tr><th>功能点</th><th>名称</th><th>来源</th><th>归属 Sprint</th><th>计划纳入</th><th>完成状态</th><th>证据</th></tr></thead>'
      + '<tbody>' + rows + '</tbody></table></div>' + sum;
  }

  /* ------------------------- 渲染计划页 ------------------------- */
  function renderPlan(build) {
    var root = $("#view-plan");
    if (!RUNS.length) { root.innerHTML = '<div class="card empty-tip">暂无 build 数据。请在 data/ 目录添加 {version}_build{N}.js 并在 plan.html / index.html 同步引入。</div>'; return; }
    var b = RUNS.filter(function (x) { return x.build === build; })[0] || RUNS[RUNS.length - 1];
    var steps = b.steps || [], features = b.features || [];

    // —— 报告头 ——
    var head = '<div class="rpt-head"><div class="report-id">' + esc((b.reportId || ("RPT-" + b.buildNo)) + " · PLAN") + '</div>'
      + '<div class="greet"><span class="pdot"></span>AI 执行报告 · 执行计划</div>'
      + '<h1>' + esc(b.build) + ' · AI 计划执行内容</h1>'
      + '<div class="head-meta">'
      + '<span>版本 <b>' + esc(b.version) + '</b></span>'
      + '<span>铸造时间 <b>' + esc(b.startedAt || "—") + '</b></span>'
      + '<span><a href="index.html#/build/' + encodeURIComponent(b.build) + '">→ 查看本 build 执行结果</a></span>'
      + '</div></div>';

    // —— 一、Build 元信息 ——
    var metaInner = '<div class="meta-grid">'
      + metaItem("Build 号", b.build) + metaItem("版本", b.version)
      + metaItem("分支", b.branch) + metaItem("部署模式", b.deployMode)
      + metaItem("铸造时间", b.startedAt) + metaItem("规划来源", b.planSource)
      + metaItem("触发原因", b.trigger, true)
      + '</div>';

    // —— 二、执行工作流（stepper）——
    var doneSteps = steps.filter(function (s) { return s.plannedStatus === "done"; }).length;

    // —— 五、需求功能点比对 ——
    var fDone = features.filter(function (f) { return f.status === "done"; }).length;

    var n = 0, html = head;
    html += chap(++n, "Build 元信息", b.deployMode || "", metaInner);
    html += chap(++n, "执行工作流", steps.length + " 步 · 顺序 + 依赖", renderStepper(steps));
    html += chap(++n, "计划时间线", "甘特（计划耗时）", svgGantt(steps));
    html += chap(++n, "步骤依赖表", doneSteps + " / " + steps.length + " 已完成", renderDepTable(steps));
    html += chap(++n, "需求功能点比对", features.length + " 项 · 已完成 " + fDone, renderFeatureTable(features));
    html += chap(++n, "关联", "", '<div class="meta-grid">'
      + metaItem("执行结果", "index.html#/build/" + b.build, true)
      + metaItem("测试报告", (b.links && b.links.testReport && /^https?:/i.test(b.links.testReport)) ? b.links.testReport : (testReportBase() + "index.html#/build/" + b.build), true)
      + '</div>');

    root.innerHTML = html;
    window.scrollTo(0, 0);
  }

  /* ------------------------- build 下拉 + 路由 + 主题 ------------------------- */
  function fillBuildSelect() {
    var sel = $("#build-select");
    sel.innerHTML = RUNS.slice().reverse().map(function (b) {
      return '<option value="' + esc(b.build) + '">' + esc(b.build) + '</option>';
    }).join("");
    sel.addEventListener("change", function () { location.hash = "#/build/" + encodeURIComponent(sel.value); });
  }
  function route() {
    var h = location.hash || "";
    var m = h.match(/^#\/build\/(.+)$/);
    var build = m ? decodeURIComponent(m[1]) : (RUNS.length ? RUNS[RUNS.length - 1].build : "");
    var sel = $("#build-select");
    if (sel && build && sel.value !== build) sel.value = build;
    // 「返回执行结果」链接带上当前 build，回到结果页对应子页
    var back = $("#back-result");
    if (back && build) back.setAttribute("href", "index.html#/build/" + encodeURIComponent(build));
    renderPlan(build);
  }
  function setupTheme() {
    function syncTips() {
      var theme = document.documentElement.getAttribute("data-theme");
      var tip = theme === "dark-blue" ? "切换到亮色" : "切换到暗色";
      var toggles = document.querySelectorAll(".theme-toggle");
      for (var i = 0; i < toggles.length; i++) toggles[i].setAttribute("data-tip", tip);
    }
    window.toggleTheme = function () {
      var cur = document.documentElement.getAttribute("data-theme");
      var next = cur === "dark-blue" ? "light-blue" : "dark-blue";
      document.documentElement.setAttribute("data-theme", next);
      try { localStorage.setItem("reportTheme", next); } catch (e) {}
      syncTips();
    };
    syncTips();
  }

  function boot() {
    setupTheme();
    fillBuildSelect();
    if (!location.hash) {
      var qs = (location.search || "").match(/[?&]build=([^&]+)/);
      if (qs) { location.hash = "#/build/" + qs[1]; }
    }
    window.addEventListener("hashchange", route);
    route();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
