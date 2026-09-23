/* =========================================================================
 * AI 执行结果报告 — 渲染逻辑
 * 职责：读取 window.__AIRUNS__，渲染综合首页（dashboard）+ 各 build 执行详情子页（章节折叠）。
 * 业务背景：完全离线运行，图表全部手写内联 SVG（双折线趋势 / 环形），零第三方库、零网络请求。
 *           视觉基于「AI执行结果报告」新模板：暗/亮蓝双主题 + cockpit + 需求功能卡 + 测试漏斗
 *           + 缺陷任务卡 + 风险与建议 + 剩余待办。SVG 用 CSS 变量着色 → 切主题无需重渲。
 * 路由：① hash #/build/<build> 直达；② 兼容 query ?build=<build>（boot 时转 hash）。
 * ========================================================================= */
(function () {
  "use strict";

  /* ---------------------------------------------------------------------
   * 状态映射常量（与数据契约 step.actualStatus / feature.status 对齐）
   * ------------------------------------------------------------------- */
  // 步骤/通用执行状态：done 完成 / doing 进行中 / fail 失败 / pend 待处理 / skip 跳过 / plan 仅计划
  var STATUS_TEXT = { done: "✅ 完成", doing: "🔵 进行中", fail: "❌ 失败", pend: "⚠️ 待处理", skip: "⏭️ 跳过", plan: "⏳ 计划" };
  // 功能完成状态文案
  var FEATURE_TEXT = { done: "✅ 完成", doing: "🔵 进行中", fail: "❌ 失败", pend: "⏸ 待决策", skip: "⏭️ 跳过" };
  // 状态 → 主题 CSS 变量（供 SVG 内联着色，切主题自动变色）
  var STEP_VAR = { done: "--done", doing: "--half", fail: "--fail", pend: "--stuck", skip: "--skip" };
  // 功能状态 → act 卡片样式类
  var FEAT_ACT = { done: "up", doing: "dec", pend: "dec", fail: "bad", skip: "skip" };
  // 缺陷严重级 → 任务卡样式类 / 图标
  var SEV_TASK = { P0: "fail", P1: "stuck", P2: "half", P3: "half" };
  var SEV_GLYPH = { P0: "🔴", P1: "🟡", P2: "🔵", P3: "🔵" };
  // 风险等级 → 任务卡样式类 / 图标（与缺陷卡共用 .task / .status-pill 视觉）
  var RISK_LV = { "高": { cls: "fail", g: "🔴" }, "中": { cls: "stuck", g: "🟡" }, "低": { cls: "half", g: "🔵" } };
  // 总体结果 statusKind / 风险等级 → cockpit 段样式
  var SK_SEG = { done: "done", pend: "stuck", fail: "fail" };
  var SK_WORD = { done: "完成", pend: "部分成功", fail: "失败" };
  var SK_GLYPH = { done: "✅", pend: "⚠️", fail: "❌" };
  var RISK_SEG = { "低": "done", "中": "stuck", "高": "fail" };
  // 章节标题前的折叠箭头
  var CHEV = '<svg class="chev" viewBox="0 0 24 24"><path d="M9 6l6 6-6 6"/></svg>';

  // 兄弟「AI测试报告」目录的相对前缀：按当前页所在报告目录名【运行时推导】，
  // 兼容本地中文目录（AI执行报告/AI测试报告）与站点发布用英文 slug（ai-execution-report/ai-test-report）；
  // 二者均不识别时回退英文 slug。这样跨报告链接在本地 file:// 与服务器两端都能打开——
  // 避免把中文目录硬编码进链接、部署到英文 slug 目录后 404。
  function testReportBase() {
    var path = (typeof location !== "undefined" && location.pathname) || "";
    try { path = decodeURIComponent(path); } catch (e) {}
    var segs = path.split("/").filter(Boolean);
    var dir = segs.length >= 2 ? segs[segs.length - 2] : "";   // 当前 html 所在目录名
    var map = { "AI执行报告": "AI测试报告", "ai-execution-report": "ai-test-report" };
    return "../" + (map[dir] || "ai-test-report") + "/";
  }

  /* ---------------------------------------------------------------------
   * 小工具函数
   * ------------------------------------------------------------------- */
  // HTML 转义，防止文本中的特殊字符破坏结构
  function esc(s) {
    if (s == null) return "";
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  // ★ 比率单位守卫（单一信源见 templates/reports/README.md「比率类字段单位口径」）：
  //   契约恒为 0~1 小数（1.0=100%）。收到 >1（误填 0~100 口径，如 100.0）或字符串 → 归一 + 一次性告警（只兜底、不静默）。
  var _rateWarned = false;
  function rate01(v) {
    if (typeof v === "string") { var p = parseFloat(v); v = isNaN(p) ? 0 : p; }
    if (typeof v !== "number" || isNaN(v)) return 0;
    if (v > 1.001) {
      if (!_rateWarned) { console.warn("[report] 比率字段口径异常：收到 " + v + "（契约为 0~1 小数，100% 应写 1.0），已按 0~100 兜底归一，请修生成端 emit-report.py 数据"); _rateWarned = true; }
      return v / 100;
    }
    return v;
  }
  // 百分比格式化（0~1 小数 → "84%"）；误填 0~100 口径由 rate01 归一（不再输出 10000%）
  function pct(v) { return Math.round(rate01(v) * 100) + "%"; }
  // 比率口径异常时的 ⚠ 角标（仅纯 HTML 上下文用，勿放进 SVG <title>）
  function rateWarnBadge(v) {
    var bad = (typeof v === "number" && v > 1.001) || (typeof v === "string" && parseFloat(v) > 1.001);
    return bad ? '<span class="rate-warn" title="数据源单位口径不符契约（应为 0~1 小数），已自动归一显示">⚠</span>' : "";
  }
  function num(v) { return typeof v === "number" ? v : (parseFloat(v) || 0); }
  // ★ 数组字段归一：兼容 {high/medium/low} 或 {高/中/低} 分组对象 → 展平为 [{level,title,...}]（存量报告兼容）；其它非数组 → [] + 告警。
  function toArray(v, field) {
    if (Array.isArray(v)) return v;
    if (v && typeof v === "object") {
      var LM = { high: "高", medium: "中", low: "低", "高": "高", "中": "中", "低": "低" };
      var keys = Object.keys(v);
      if (keys.length && keys.every(function (k) { return Object.prototype.hasOwnProperty.call(LM, k); })) {
        console.warn("[report] 字段 " + (field || "?") + " 为分组对象（" + keys.join(",") + "）→ 已展平兼容渲染；契约应为数组、等级写在每项 level 字段");
        var out = [];
        keys.forEach(function (k) {
          (Array.isArray(v[k]) ? v[k] : []).forEach(function (it) {
            if (it && typeof it === "object") { if (it.level == null) it.level = LM[k]; out.push(it); }
            else out.push({ level: LM[k], title: String(it), what: "" });
          });
        });
        return out;
      }
    }
    if (v != null) console.warn("[report] 字段 " + (field || "?") + " 期望数组，实际 " + (typeof v) + " → 已按空处理");
    return [];
  }
  // 缺失值兜底：避免把 undefined/null 字面量拼进 HTML（契约字段缺失 → 显示 fallback，默认 "—"）
  function val(v, fallback) { return (v == null || v === "") ? (fallback == null ? "—" : fallback) : v; }
  // 渲染彻底失败时的红色错误卡（绝不留白屏，让人一眼分辨"数据不对"而非"任务没跑"）
  function errBanner(b, e) {
    var id = (b && b.build) ? esc(b.build) : "本 build";
    return '<div class="card" style="border:2px solid #ef4444;background:#fef2f2;color:#991b1b;padding:20px;border-radius:10px">'
      + '<h3 style="margin:0 0 8px">⚠ 报告渲染失败（数据字段不符契约，非任务未执行）</h3>'
      + '<p style="margin:0 0 6px">build：<b>' + id + '</b></p>'
      + '<pre style="white-space:pre-wrap;font-size:12px;margin:8px 0;color:#7f1d1d">' + esc(String((e && e.stack) || e)) + '</pre>'
      + '<p style="margin:6px 0 0;font-size:13px">排查：按契约修 <code>data/{BUILD}.js</code>（比率 0~1、risks 为数组、cases 含 result 等）后重跑 <code>emit-report.py</code>。</p></div>';
  }
  // item 6：复测关系徽标（build 复测自上一 finalized build 时，data 带 retestOf/retestRound）
  function retestTag(b) {
    if (!b || !b.retestOf) return "";
    var fixed = (b.fixedDefects && b.fixedDefects.length) ? "，修复 " + b.fixedDefects.map(esc).join("/") : "";
    var tip = "复测自 " + esc(b.retestOf) + (b.retestRound ? " · 第" + b.retestRound + "轮" : "") + fixed;
    return '<span title="' + tip + '" style="display:inline-block;margin-left:6px;padding:1px 7px;border-radius:9px;'
      + 'background:#eef2ff;color:#4338ca;font-size:11px;font-weight:600;vertical-align:middle;">🔁 第'
      + (b.retestRound || "?") + '轮复测</span>';
  }
  function $(sel) { return document.querySelector(sel); }

  /* =====================================================================
   * SVG 图表函数（主题感知：颜色走 CSS 变量 / class，切主题无需重渲）
   * =================================================================== */

  /** 双折线趋势图 — 各 build 的「功能完成率」与「测试通过率」（Y=0~100%）*/
  function svgDualTrend(builds) {
    var W = 720, H = 270, padL = 48, padR = 24, padT = 24, padB = 48;
    var iw = W - padL - padR, ih = H - padT - padB, n = builds.length;
    var yLines = "";
    [0, 25, 50, 75, 100].forEach(function (v) {
      var y = padT + ih - (v / 100) * ih;
      yLines += '<line x1="' + padL + '" y1="' + y + '" x2="' + (W - padR) + '" y2="' + y + '" class="chart-grid"/>'
        + '<text x="' + (padL - 8) + '" y="' + (y + 4) + '" text-anchor="end" font-size="11" class="chart-axis">' + v + '%</text>';
    });
    function px(i) { return n === 1 ? padL + iw / 2 : padL + (i / (n - 1)) * iw; }
    function py(rate) { return padT + ih - num(rate) * ih; }
    function lineSeries(getter, varName, label) {
      var pts = builds.map(function (b, i) { return [px(i), py(getter(b))]; });
      var path = pts.map(function (p, i) { return (i === 0 ? "M" : "L") + p[0].toFixed(1) + " " + p[1].toFixed(1); }).join(" ");
      var dots = "";
      builds.forEach(function (b, i) {
        var p = pts[i];
        dots += '<circle cx="' + p[0].toFixed(1) + '" cy="' + p[1].toFixed(1) + '" r="4" style="fill:var(--card);stroke:var(' + varName + ')" stroke-width="2"><title>build' + b.buildNo + ' ' + label + ' ' + pct(getter(b)) + '</title></circle>';
      });
      return '<path d="' + path + '" fill="none" style="stroke:var(' + varName + ')" stroke-width="2.5" stroke-linejoin="round"/>' + dots;
    }
    var xlabels = "";
    builds.forEach(function (b, i) {
      xlabels += '<text x="' + px(i).toFixed(1) + '" y="' + (H - padB + 18) + '" text-anchor="middle" font-size="11" class="chart-axis">#' + b.buildNo + '</text>';
    });
    return '<svg viewBox="0 0 ' + W + ' ' + H + '" width="100%" height="' + H + '" role="img">'
      + yLines
      + lineSeries(function (b) { return (b.overview || {}).featureRate; }, "--ink", "功能完成率")
      + lineSeries(function (b) { return (b.overview || {}).testPassRate; }, "--done", "测试通过率")
      + xlabels
      + '</svg>';
  }

  /** 步骤进度环形图 — done/doing/fail/pend/skip 分布 */
  function svgDonut(dist, size) {
    size = size || 220;
    var KEYS = ["done", "doing", "fail", "pend", "skip"];
    var cx = size / 2, cy = size / 2, r = size * 0.38, stroke = size * 0.14;
    var total = KEYS.reduce(function (s, k) { return s + (dist[k] || 0); }, 0);
    var circ = 2 * Math.PI * r, offset = 0, arcs = "";
    if (total === 0) {
      arcs = '<circle cx="' + cx + '" cy="' + cy + '" r="' + r + '" fill="none" class="chart-grid" stroke-width="' + stroke + '"/>';
    } else {
      KEYS.forEach(function (k) {
        var val = dist[k] || 0; if (val === 0) return;
        var len = (val / total) * circ;
        arcs += '<circle cx="' + cx + '" cy="' + cy + '" r="' + r + '" fill="none" style="stroke:var(' + STEP_VAR[k] + ')" stroke-width="' + stroke + '" '
          + 'stroke-dasharray="' + len.toFixed(2) + ' ' + (circ - len).toFixed(2) + '" stroke-dashoffset="' + (-offset).toFixed(2) + '" '
          + 'transform="rotate(-90 ' + cx + ' ' + cy + ')"><title>' + (STATUS_TEXT[k] || k) + ' ' + val + '</title></circle>';
        offset += len;
      });
    }
    var doneRate = total ? Math.round((dist.done || 0) / total * 100) : 0;
    return '<svg viewBox="0 0 ' + size + ' ' + size + '" width="' + size + '" height="' + size + '" role="img">' + arcs
      + '<text x="' + cx + '" y="' + (cy - 4) + '" text-anchor="middle" font-size="' + (size * 0.2) + '" font-weight="700" class="chart-center-num">' + doneRate + '%</text>'
      + '<text x="' + cx + '" y="' + (cy + size * 0.13) + '" text-anchor="middle" font-size="' + (size * 0.065) + '" class="chart-center-sub">步骤完成</text></svg>';
  }
  function donutLegend(dist) {
    var KEYS = ["done", "doing", "fail", "pend", "skip"];
    var T = { done: "完成", doing: "进行中", fail: "失败", pend: "待处理", skip: "跳过" };
    return '<div class="legend">' + KEYS.map(function (k) {
      return '<span class="legend-item"><span class="legend-swatch" style="background:var(' + STEP_VAR[k] + ')"></span>' + T[k] + ' ' + (dist[k] || 0) + '</span>';
    }).join("") + '</div>';
  }
  function trendLegend() {
    return '<div class="legend">'
      + '<span class="legend-item"><span class="legend-swatch" style="background:var(--ink)"></span>功能完成率</span>'
      + '<span class="legend-item"><span class="legend-swatch" style="background:var(--done)"></span>测试通过率</span></div>';
  }

  /* =====================================================================
   * 数据加载与全局状态
   * =================================================================== */
  var RUNS = (window.__AIRUNS__ || []).slice().map(function (b) {
    if (b && b.buildNo == null) b.buildNo = parseInt((String(b.build || "").match(/_build(\d+)$/) || [])[1], 10) || 0;  // 渲染端兜底派生（与 emit-report.py P1-6 双保险，防 #undefined）
    return b;
  }).sort(function (a, b) { return a.buildNo - b.buildNo; });

  // 把 steps 聚合成环形分布
  function stepDist(b) {
    var d = { done: 0, doing: 0, fail: 0, pend: 0, skip: 0 };
    (b.steps || []).forEach(function (s) { var k = s.actualStatus || "plan"; if (d[k] != null) d[k]++; });
    return d;
  }
  function resultKind(r) { return r === "success" ? "done" : r === "failed" ? "fail" : "pend"; }
  function resultText(r) { return r === "success" ? "✅ 成功" : r === "failed" ? "❌ 失败" : "⚠️ 部分成功"; }

  /* ---------------------------------------------------------------------
   * 复用片段拼装小函数
   * ------------------------------------------------------------------- */
  // cockpit 单段
  function cpSeg(cls, n, l) { return '<div class="cp-seg ' + cls + '"><span class="cs-n">' + esc(n) + '</span><span class="cs-l">' + esc(l) + '</span></div>'; }
  // cockpit 段 + 段内「?」悬浮说明卡（待人工决策构成 / 风险等级判定标准）。tip 为受控静态 HTML（含 <b>/<br>），不转义
  function cpSegTip(cls, n, l, tip) {
    return '<div class="cp-seg ' + cls + '" tabindex="0"><span class="tipdot" aria-label="说明">?</span>'
      + '<span class="tipbox">' + tip + '</span>'
      + '<span class="cs-n">' + esc(n) + '</span><span class="cs-l">' + esc(l) + '</span></div>';
  }
  // 漏斗单步
  function fstep(cls, n, l, d) { return '<div class="fstep ' + cls + '"><div class="fn">' + esc(n) + '</div><div class="fl">' + esc(l) + '</div><div class="fd">' + esc(d) + '</div></div>'; }
  // 元信息项
  function metaItem(k, v, wide) { return '<div class="meta-item' + (wide ? ' wide' : '') + '"><span class="meta-k">' + esc(k) + '</span><span class="meta-v">' + esc(v) + '</span></div>'; }
  // 折叠章节包装
  function chap(num, title, sub, inner, open) {
    return '<details class="chapter"' + (open === false ? "" : " open") + '><summary>' + CHEV
      + '<span class="eyebrow"><span class="n">' + num + '</span>' + esc(title) + '</span>'
      + (sub ? '<span class="sub">' + esc(sub) + '</span>' : "")
      + '</summary><div class="chapter-inner">' + inner + '</div></details>';
  }

  /* =====================================================================
   * 渲染：综合首页（dashboard）
   * =================================================================== */
  function renderOverview() {
    var root = $("#view-overview");
    if (!RUNS.length) { root.innerHTML = '<div class="card empty-tip">暂无 build 执行数据。请在 data/ 目录添加 {version}_build{N}.js 并在 index.html 引入。</div>'; return; }
    try {
    var latest = RUNS[RUNS.length - 1];
    var lo = latest.overview || {};
    var totalDefects = RUNS.reduce(function (s, b) { return s + (b.defects ? b.defects.length : 0); }, 0);

    // ① 报告头横幅
    var banner = '<div class="rpt-head"><div class="greet"><span class="pdot"></span>AI 执行报告 · 综合首页</div>'
      + '<h1>' + esc(latest.version) + ' · 全部 ' + RUNS.length + ' 个 build 执行总览</h1>'
      + '<div class="head-meta">'
      + '<span>最新 <b>' + esc(latest.build) + '</b></span>'
      + '<span>build 范围 <b>#' + RUNS[0].buildNo + ' ~ #' + latest.buildNo + '</b></span>'
      + '<span>最近完成 <b>' + esc(latest.finishedAt || "—") + '</b></span>'
      + '</div></div>';

    // ② cockpit 关键指标
    var cockpit = '<div class="section" style="margin-top:16px"><div class="cockpit"><div class="cp-band">'
      + '<div class="cp-net-top"><div class="cp-title">关键指标 · <b>' + esc(latest.build) + '</b></div><div class="cp-sub">最新 build 概览 + 累计统计</div></div>'
      + '<div class="cp-bar">'
      + cpSeg("done", pct(lo.featureRate), "最新功能完成率")
      + cpSeg("done", pct(lo.testPassRate), "最新测试通过率")
      + cpSeg("half", String(RUNS.length), "累计 build 数")
      + cpSeg("fail", String(totalDefects), "累计缺陷数")
      + '</div></div></div></div>';

    // ③ 双折线趋势图
    var trend = '<div class="section"><div class="card chart-box"><div class="section-title">各 build 完成率趋势</div>'
      + svgDualTrend(RUNS) + trendLegend()
      + '<div class="chart-caption">横轴：build 序号 ｜ 纵轴：完成率</div></div></div>';

    // ④ 最新 build 步骤环形 + build 列表
    var dist = stepDist(latest);
    var rows = RUNS.slice().reverse().map(function (b) {
      var o = b.overview || {};
      return '<tr class="clickable" data-build="' + esc(b.build) + '">'
        + '<td><strong>' + esc(b.build) + '</strong>' + retestTag(b) + '</td>'
        + '<td class="muted">' + esc(b.finishedAt) + '</td>'
        + '<td><div class="rate-bar"><div class="track"><div class="fill" style="width:' + pct(o.featureRate) + '"></div></div><span class="rate-num">' + pct(o.featureRate) + '</span></div></td>'
        + '<td>' + pct(o.testPassRate) + '</td>'
        + '<td><span class="badge ' + (o.statusKind || resultKind(b.result)) + '">' + esc(o.statusText || resultText(b.result)) + '</span></td>'
        + '<td>' + (b.defects ? b.defects.length : 0) + '</td></tr>';
    }).join("");
    var grid = '<div class="section"><div class="grid-2">'
      + '<div class="card chart-box"><div class="section-title">最新 build 步骤分布</div>' + svgDonut(dist, 220) + donutLegend(dist) + '</div>'
      + '<div class="card"><div class="section-title">Build 列表（点击行查看执行详情）</div><div class="table-wrap"><table class="report-table">'
      + '<thead><tr><th>Build</th><th>完成时间</th><th>功能完成率</th><th>测试通过率</th><th>结果</th><th>缺陷</th></tr></thead>'
      + '<tbody>' + rows + '</tbody></table></div></div></div></div>';

    root.innerHTML = banner + cockpit + trend + grid;

    root.querySelectorAll("tr.clickable").forEach(function (tr) {
      tr.addEventListener("click", function () { location.hash = "#/build/" + encodeURIComponent(tr.getAttribute("data-build")); });
    });
    } catch (e) { console.error("[report] renderOverview 失败", e); root.innerHTML = errBanner(null, e); }
  }

  /* =====================================================================
   * 渲染：单个 build 执行详情子页（章节折叠 + cockpit + 需求功能 + 漏斗 + 任务卡）
   * =================================================================== */
  function renderBuild(build) {
    var root = $("#view-build");
    var b = RUNS.filter(function (x) { return x.build === build; })[0];
    if (!b) { root.innerHTML = '<div class="card empty-tip">未找到 build：' + esc(build) + '</div>'; return; }
    try {
    var o = b.overview || {};
    // ★ 就地归一化（数组字段 + buildNo）：兼容分组对象/漏填，使下方所有 (b.X||[]) 读取恒安全、绝不因单字段异常整页崩
    if (b.buildNo == null) b.buildNo = (String(b.build || "").match(/_build(\d+)$/) || [])[1] || "?";
    b.risks = toArray(b.risks, "risks");
    b.features = toArray(b.features, "features");
    b.steps = toArray(b.steps, "steps");
    b.defects = toArray(b.defects, "defects");
    b.incidents = toArray(b.incidents, "incidents");
    b.todos = toArray(b.todos, "todos").map(function (t) { return (t && typeof t === "object") ? t : { title: String(t), detail: "" }; });

    // —— 报告头 ——
    var head = '<div class="rpt-head"><div class="report-id">' + esc(b.reportId || ("RPT-" + b.buildNo)) + '</div>'
      + '<div class="greet"><span class="pdot"></span>AI 执行报告</div>'
      + '<h1>' + esc(b.build) + ' · AI 全自动执行结果</h1>'
      + '<div class="head-meta">'
      + '<span>版本 / 任务包 <b>' + esc(b.version) + ' ／ ' + esc(b.build) + '</b></span>'
      + '<span>生成时间 <b>' + esc(b.generatedAt || b.finishedAt || "—") + '</b></span>'
      + '<span>执行时间 <b>' + esc((b.startedAt || "—") + " → " + (b.finishedAt || "—")) + '</b></span>'
      + '<span>耗时 <b>' + esc(b.duration || "—") + '</b></span>'
      + '<span><a href="plan.html#/build/' + encodeURIComponent(b.build) + '">→ 查看本 build 执行计划</a></span>'
      + '</div></div>';

    // —— 1 执行概览（cockpit）——
    var sk = o.statusKind || resultKind(b.result);
    var defectCount = (b.defects || []).length;
    var featCount = (b.features || []).length;
    var ts = b.testSummary || {};
    var caseTotal = (ts.total != null) ? ts.total : "—";
    // 风险等级判定标准（固定评判规则，静态 tip）；若数据给了 riskBasis 则附「当前判定」一行
    var RISK_TIP = '<b>判断标准</b>（综合 P0/P1 缺陷数 + 测试通过率 + 性能回归）：<br>'
      + '· <b>低</b>：无 P0/P1 缺陷 且 通过率 ≥ 95% 且 性能回归 ≤ 10%<br>'
      + '· <b>中</b>：≤ 1 个 P0 或 ≤ 3 个 P1，或 通过率 90%–95%，或 性能回归 10%–30%<br>'
      + '· <b>高</b>：> 1 个 P0 或 > 3 个 P1，或 通过率 < 90%，或 性能回归 > 30%'
      + (o.riskBasis ? '<br><br><b>当前判定</b>：' + esc(o.riskBasis) : "");
    var cockpit = '<div class="cockpit"><div class="cp-band">'
      + '<div class="cp-net-top"><div class="cp-title">本次任务包 · <b>' + esc(b.build) + '</b></div>'
      + '<div class="cp-sub">' + featCount + ' 项功能 · ' + caseTotal + ' 测试用例 · ' + defectCount + ' 缺陷</div></div>'
      + '<div class="cp-bar">'
      + '<div class="cp-seg ' + (SK_SEG[sk] || "half") + '"><span class="cs-n">' + (SK_GLYPH[sk] || "•") + '</span><span class="cs-l">执行状态 · ' + (SK_WORD[sk] || esc(o.statusText || "—")) + '</span></div>'
      + cpSeg("done", pct(o.featureRate), "功能完成率")
      + cpSeg("done", pct(o.testPassRate), "测试通过率")
      + cpSegTip("ask", o.pendingCount != null ? String(o.pendingCount) : "—", "待人工决策", "含：待决策功能数 + 待修复缺陷数 + 待实施建议数")
      + cpSeg("half", o.autoFixedCount != null ? String(o.autoFixedCount) : "—", "自动修复缺陷")
      + cpSegTip(RISK_SEG[o.riskLevel] || "stuck", o.riskLevel || "—", "风险等级", RISK_TIP)
      + '</div></div></div>';

    // —— 2 需求功能清单（act 卡）——
    var fDone = (b.features || []).filter(function (f) { return f.status === "done"; }).length;
    var fPend = (b.features || []).filter(function (f) { return f.status === "pend" || f.status === "doing"; }).length;
    var actCards = (b.features || []).map(function (f) {
      var cls = FEAT_ACT[f.status] || "dec";
      var req = f.reqId ? '<span class="req" title="需求功能点编号">' + esc(f.reqId) + '</span>' : "";
      var src = f.reqSource ? '<span class="src">来源：' + esc(f.reqSource) + '</span>' : "";
      var reason = f.reason ? '<span class="desc">⚠️ ' + esc(f.reason) + '</span>' : "";
      var mi = [];
      if (f.sprint) mi.push("归属 <b>" + esc(f.sprint) + "</b>");
      if (f.owner) mi.push("负责人 <b>" + esc(f.owner) + "</b>");
      if (f.duration) mi.push("耗时 <b>" + esc(f.duration) + "</b>");
      var meta = mi.length ? '<div class="meta">' + mi.join(" · ") + "</div>" : "";
      return '<div class="act ' + cls + '"><span class="act-tag">' + esc(FEATURE_TEXT[f.status] || f.status) + '</span>'
        + '<div class="act-main"><b>#' + esc(f.num) + " " + req + esc(f.name) + '</b>' + src + reason + meta + '</div></div>';
    }).join("") || '<div class="empty-tip">无需求功能数据</div>';
    var featInner = '<div class="overview"><div class="ov-head"><span class="ov-big">' + featCount + '</span>'
      + '<div class="ov-tx"><b>件功能 · 按状态拆开看</b><span>完成 → 待决策 / 进行中。待决策项需人工先拍板再继续</span></div>'
      + '<div class="ov-mini"><i class="up">' + fDone + ' 完成</i><i class="td">' + fPend + ' 待跟进</i></div></div>'
      + actCards + '</div>';

    // —— 3 测试详情（漏斗）——
    // 仅当显式给了绝对 URL（跨域/跨主机覆盖）才用 links.testReport，否则按当前页目录运行时推导兄弟报告路径
    var testLink = (b.links && b.links.testReport && /^https?:/i.test(b.links.testReport)) ? b.links.testReport : (testReportBase() + "index.html#/build/" + encodeURIComponent(b.build));
    var funnelInner;
    if (ts.total != null) {
      funnelInner = '<div class="funnel">'
        + fstep("neutral", ts.total, "用例总数", "本次执行覆盖范围")
        + fstep("good", ts.pass != null ? ts.pass : "—", "通过", (ts.passRate != null ? pct(ts.passRate) : "") + " 通过率")
        + fstep("bad", ts.fail != null ? ts.fail : "—", "失败", "需关注 / 已记录")
        + fstep("good", ts.passRate != null ? pct(ts.passRate) : "—", "通过率", ts.coverage != null ? ("覆盖率 " + pct(ts.coverage)) : "")
        + '</div>'
        + '<div class="funnel-link">完整用例 / 截图见 → <a href="' + esc(testLink) + '">AI 测试报告（该 build 子页）</a></div>';
    } else {
      funnelInner = '<div class="empty-tip">本 build 暂无测试摘要（待浏览器实测 finalize）。<br>完整用例 / 截图见 → <a href="' + esc(testLink) + '">AI 测试报告（该 build 子页）</a></div>';
    }

    // —— 4 步骤执行（环形 + 计划 vs 实际）——
    var dist = stepDist(b);
    var stepRows = (b.steps || []).map(function (s) {
      return '<tr><td class="wrap"><strong>' + esc(s.name) + '</strong></td>'
        + '<td><span class="step-type">' + esc(s.type || "—") + '</span></td>'
        + '<td><span class="badge ' + (s.plannedStatus || "plan") + '">' + esc(STATUS_TEXT[s.plannedStatus] || "⏳ 计划") + '</span></td>'
        + '<td><span class="badge ' + (s.actualStatus || "plan") + '">' + esc(STATUS_TEXT[s.actualStatus] || "⏳ 计划") + '</span></td>'
        + '<td class="muted">' + esc(s.duration || "—") + '</td>'
        + '<td class="wrap muted">' + esc(s.output || "") + '</td></tr>';
    }).join("") || '<tr><td colspan="6" class="empty-tip">无步骤数据</td></tr>';
    var stepsInner = '<div class="grid-2">'
      + '<div class="chart-box"><div class="section-title">步骤完成分布</div>' + svgDonut(dist, 200) + donutLegend(dist) + '</div>'
      + '<div><div class="section-title">计划 vs 实际</div><div class="table-wrap"><table class="report-table">'
      + '<thead><tr><th>步骤</th><th>类型</th><th>计划</th><th>实际</th><th>耗时</th><th>产物 / 说明</th></tr></thead>'
      + '<tbody>' + stepRows + '</tbody></table></div></div></div>';

    // —— 5 缺陷清单（任务卡）——
    var defCards = (b.defects || []).map(function (d) {
      var cls = SEV_TASK[d.severity] || "half";
      var glyph = SEV_GLYPH[d.severity] || "🔵";
      return '<div class="task ' + cls + '"><div class="task-top"><div class="body">'
        + '<h3>' + glyph + " " + esc(d.title) + '</h3>'
        + (d.impact ? '<p class="what">' + esc(d.impact) + '</p>' : "")
        + '</div><span class="status-pill ' + cls + '">' + esc(d.severity) + (d.status ? " · " + esc(d.status) : "") + '</span></div>'
        + '<details class="tech"><summary>' + CHEV + '查看技术细节</summary><div class="tech-inner">'
        + '<h6>缺陷编号</h6><p>' + esc(d.id) + '</p>'
        + '<h6>优先级</h6><p><b>' + esc(d.severity) + '</b></p>'
        + (d.status ? '<h6>状态</h6><p>' + esc(d.status) + '</p>' : "")
        + (d.impact ? '<h6>影响</h6><p>' + esc(d.impact) + '</p>' : "")
        + '</div></details></div>';
    }).join("") || '<div class="empty-tip">本次无缺陷</div>';
    var defectsInner = '<div class="tasks">' + defCards + '</div>';

    // —— 风险与建议（质量风险 + 改进建议，复用任务卡；不含具体缺陷条目）——
    var riskCards = (b.risks || []).map(function (r) {
      var lv = RISK_LV[r.level] || RISK_LV["中"];
      return '<div class="task ' + lv.cls + '"><div class="task-top"><div class="body">'
        + '<h3>' + lv.g + " " + esc(r.title) + '</h3>'
        + '<p class="what">' + (r.id ? '<span class="risk-id">' + esc(r.id) + '</span><span class="sep">·</span>' : "") + esc(r.what || "") + '</p>'
        + '</div><span class="status-pill ' + lv.cls + '">' + esc((r.level || "中") + "风险") + '</span></div>'
        + ((r.risk || r.advice) ? '<details class="tech"><summary>' + CHEV + '查看风险与建议</summary><div class="tech-inner">'
            + (r.risk ? '<h6>风险</h6><p>' + esc(r.risk) + '</p>' : "")
            + (r.advice ? '<h6>建议</h6><p>' + esc(r.advice) + '</p>' : "")
            + '</div></details>' : "")
        + '</div>';
    }).join("") || '<div class="empty-tip">无风险项</div>';
    var risksInner = '<div class="tasks">'
      + '<p class="funnel-link" style="margin:0 0 14px"><b>说明</b> 基于测试结果、缺陷分析和执行数据识别的质量风险与改进建议，不含具体缺陷条目（缺陷详情见上一节）。</p>'
      + riskCards + '</div>';
    var riskCount = (b.risks || []).length;
    var rHigh = (b.risks || []).filter(function (r) { return r.level === "高"; }).length;
    var rMid = (b.risks || []).filter(function (r) { return r.level === "中"; }).length;
    var rLow = (b.risks || []).filter(function (r) { return r.level === "低"; }).length;
    var riskSub = riskCount ? ("高 × " + rHigh + " · 中 × " + rMid + (rLow ? " · 低 × " + rLow : "")) : "无";

    // —— 异常处置（可选）——
    var incRows = (b.incidents || []).map(function (x) {
      return '<tr><td class="wrap">' + esc(x.step) + '</td><td class="wrap">' + esc(x.symptom) + '</td><td class="wrap">' + esc(x.action) + '</td><td>' + esc(x.result) + '</td></tr>';
    }).join("");
    var incidentsInner = '<div class="table-wrap"><table class="report-table">'
      + '<thead><tr><th>步骤</th><th>现象</th><th>处置</th><th>结果</th></tr></thead><tbody>' + incRows + '</tbody></table></div>';

    // —— 剩余待办（可选）——
    var todoItems = (b.todos || []).map(function (t) {
      return '<li><input type="checkbox"><div class="ct"><div class="tt">' + esc(t.title) + '</div>'
        + (t.detail ? '<div class="td">' + esc(t.detail) + '</div>' : "") + '</div></li>';
    }).join("");
    var todosInner = '<div class="tcol"><div class="th"><h4>剩余待办</h4><span class="cnt">' + (b.todos || []).length + '</span></div><ul>' + todoItems + '</ul></div>';

    // —— 运行元信息（短字段走紧凑栅格；长字段 触发原因/访问地址 整行铺开；执行计划已移到头部链接 + plan.html）——
    var metaInner = '<div class="meta-grid">'
      + metaItem("版本", b.version) + metaItem("Build 序号", "#" + b.buildNo)
      + (b.retestOf ? metaItem("复测关系", "🔁 复测自 " + b.retestOf + (b.retestRound ? " · 第" + b.retestRound + "轮" : "") + ((b.fixedDefects && b.fixedDefects.length) ? "，修复 " + b.fixedDefects.join("/") : ""), true) : "")
      + metaItem("代码分支", b.branch) + metaItem("部署模式", b.deployMode)
      + metaItem("开始时间", b.startedAt) + metaItem("结束时间", b.finishedAt)
      + metaItem("触发原因", b.trigger, true)
      + metaItem("访问地址", b.deployUrl, true)
      + '</div>';

    // —— 组装（章节序号动态编号，可选章节无数据则跳过）——
    var n = 0, html = head;
    html += chap(++n, "执行概览", "整体" + (SK_WORD[sk] || "完成") + " · 待跟进 " + (o.pendingCount != null ? o.pendingCount : 0) + " 项", cockpit);
    html += chap(++n, "需求功能清单", featCount + " 项", featInner);
    html += chap(++n, "测试详情", ts.total != null ? ("通过率 " + (ts.passRate != null ? pct(ts.passRate) : "—")) : "待实测", funnelInner);
    html += chap(++n, "步骤执行", (b.steps || []).length + " 步", stepsInner);
    html += chap(++n, "缺陷清单", defectCount + " 项", defectsInner);
    html += chap(++n, "风险与建议", riskCount ? (riskCount + " 项 · " + riskSub) : "无", risksInner);
    if (incRows) html += chap(++n, "异常处置", (b.incidents || []).length + " 项", incidentsInner);
    if (todoItems) html += chap(++n, "剩余待办", (b.todos || []).length + " 项", todosInner);
    html += chap(++n, "运行元信息", "", metaInner);

    root.innerHTML = html;
    window.scrollTo(0, 0);
    } catch (e) { console.error("[report] renderBuild 失败", e); root.innerHTML = errBanner(b, e); }
  }

  /* =====================================================================
   * 顶部 build 下拉填充
   * =================================================================== */
  function fillBuildSelect() {
    var sel = $("#build-select");
    sel.innerHTML = RUNS.slice().reverse().map(function (b) {
      var o = b.overview || {};
      return '<option value="' + esc(b.build) + '">' + esc(b.build) + '（' + pct(o.featureRate) + '）</option>';
    }).join("");
    sel.addEventListener("change", function () { location.hash = "#/build/" + encodeURIComponent(sel.value); });
  }

  /* =====================================================================
   * hash 路由：#/overview（默认）｜ #/build/<build标识>
   * =================================================================== */
  function setActive(view) {
    $("#view-overview").classList.toggle("active", view === "overview");
    $("#view-build").classList.toggle("active", view === "build");
    $("#tab-overview").classList.toggle("active", view === "overview");
    $("#tab-build").classList.toggle("active", view === "build");
    document.querySelector(".build-select").style.display = view === "build" ? "flex" : "none";
  }
  function route() {
    var h = location.hash || "#/overview";
    var m = h.match(/^#\/build\/(.+)$/);
    if (m) {
      var build = decodeURIComponent(m[1]);
      setActive("build");
      var sel = $("#build-select");
      if (sel.value !== build) sel.value = build;
      renderBuild(build);
    } else {
      setActive("overview");
      renderOverview();
    }
  }

  /* =====================================================================
   * 主题切换（亮/暗蓝开关）
   * =================================================================== */
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

  // 打印前展开所有 details，打印后还原
  function setupPrint() {
    function setAll(open) {
      var ds = document.querySelectorAll("details");
      for (var i = 0; i < ds.length; i++) {
        var d = ds[i];
        if (open) { if (d.dataset.prevOpen === undefined) d.dataset.prevOpen = d.open ? "1" : "0"; d.open = true; }
        else { d.open = d.dataset.prevOpen === "1"; delete d.dataset.prevOpen; }
      }
    }
    window.addEventListener("beforeprint", function () { setAll(true); });
    window.addEventListener("afterprint", function () { setAll(false); });
  }

  /* =====================================================================
   * 启动
   * =================================================================== */
  function boot() {
    setupTheme();
    setupPrint();
    fillBuildSelect();
    // 兼容 query ?build=<build标识>：boot 时若带 query 且无 hash，转成 hash 路由
    if (!location.hash) {
      var qs = (location.search || "").match(/[?&]build=([^&]+)/);
      if (qs) { location.hash = "#/build/" + qs[1]; }
    }
    $("#tab-overview").addEventListener("click", function () { location.hash = "#/overview"; });
    $("#tab-build").addEventListener("click", function () {
      var sel = $("#build-select");
      var target = sel.value || (RUNS.length ? RUNS[RUNS.length - 1].build : "");
      location.hash = target ? "#/build/" + encodeURIComponent(target) : "#/overview";
    });
    window.addEventListener("hashchange", route);
    route();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
