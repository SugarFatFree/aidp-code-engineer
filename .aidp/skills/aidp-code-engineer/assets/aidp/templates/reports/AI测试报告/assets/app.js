/* =========================================================================
 * AI测试报告 — 渲染逻辑
 * 职责：读取 window.__BUILDS__，渲染综合首页 + 各 build 子页；纯前端视图切换（hash 路由）。
 * 业务背景：完全离线运行，图表全部手写内联 SVG（环形/饼/柱状/折线），零第三方库、零网络请求。
 * ========================================================================= */
(function () {
  "use strict";

  /* ---------------------------------------------------------------------
   * 状态色与文案常量（与数据契约 result 对齐）
   * ------------------------------------------------------------------- */
  var COLORS = { pass: "#16a34a", fail: "#dc2626", block: "#f59e0b", skip: "#9ca3af", na: "#64748b", brand: "#2563eb" };
  var RESULT_TEXT = { pass: "通过", fail: "失败", block: "阻塞", skip: "忽略", na: "不适用" };
  // na = 本场景不存在该功能、永远不测（≠ block 的"以后能测"、≠ skip 的"以后要测"）；
// 不进通过率分母，单列展示 —— 记成 pass 会把"不适用"读成"已验证通过"。
var RESULT_KEYS = ["pass", "fail", "block", "skip", "na"];

  /* ---------------------------------------------------------------------
   * 小工具函数
   * ------------------------------------------------------------------- */
  // HTML 转义，防止 note/title 中的特殊字符破坏结构
  function esc(s) {
    if (s == null) return "";
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  // ★ 比率单位守卫（单一信源见 templates/reports/README.md「比率类字段单位口径」）：契约恒 0~1 小数（1.0=100%）。
  //   收到 >1（误填 0~100 口径，如 100.0）或字符串 → 归一 + 一次性告警（只兜底、不静默，不再输出 10000%）。
  var _rateWarned = false, _caseAliasWarned = false;
  function rate01(v) {
    if (typeof v === "string") { var p = parseFloat(v); v = isNaN(p) ? 0 : p; }
    if (typeof v !== "number" || isNaN(v)) return 0;
    if (v > 1.001) {
      if (!_rateWarned) { console.warn("[report] 比率字段口径异常：收到 " + v + "（契约为 0~1 小数，100% 应写 1.0），已按 0~100 兜底归一，请修生成端 emit-report.py 数据"); _rateWarned = true; }
      return v / 100;
    }
    return v;
  }
  // 百分比格式化（0~1 小数 → "84%"）；误填 0~100 口径由 rate01 归一
  function pct(v) { return Math.round(rate01(v) * 100) + "%"; }
  // 比率口径异常时的 ⚠ 角标（仅纯 HTML 上下文用，勿放进 SVG <title>）
  function rateWarnBadge(v) {
    var bad = (typeof v === "number" && v > 1.001) || (typeof v === "string" && parseFloat(v) > 1.001);
    return bad ? '<span class="rate-warn" title="数据源单位口径不符契约（应为 0~1 小数），已自动归一显示">⚠</span>' : "";
  }
  // ★ 数组字段归一：{high/medium/low}|{高/中/低} 分组对象 → 展平为数组（存量兼容）；其它非数组 → [] + 告警。
  function toArray(v, field) {
    if (Array.isArray(v)) return v;
    if (v && typeof v === "object") {
      var LM = { high: "高", medium: "中", low: "低", "高": "高", "中": "中", "低": "低" };
      var keys = Object.keys(v);
      if (keys.length && keys.every(function (k) { return Object.prototype.hasOwnProperty.call(LM, k); })) {
        console.warn("[report] 字段 " + (field || "?") + " 为分组对象（" + keys.join(",") + "）→ 已展平兼容渲染");
        var out = [];
        keys.forEach(function (k) { (Array.isArray(v[k]) ? v[k] : []).forEach(function (it) {
          if (it && typeof it === "object") { if (it.level == null) it.level = LM[k]; out.push(it); } else out.push({ level: LM[k], title: String(it) });
        }); });
        return out;
      }
    }
    if (v != null) console.warn("[report] 字段 " + (field || "?") + " 期望数组，实际 " + (typeof v) + " → 已按空处理");
    return [];
  }
  // 缺失值兜底：避免把 undefined/null 字面量拼进 HTML（默认 "—"）
  function val(v, fallback) { return (v == null || v === "") ? (fallback == null ? "—" : fallback) : v; }
  // 渲染彻底失败时的红色错误卡（绝不留白屏）
  function errBanner(b, e) {
    var id = (b && b.build) ? esc(b.build) : "本 build";
    return '<div class="card" style="border:2px solid #ef4444;background:#fef2f2;color:#991b1b;padding:20px;border-radius:10px">'
      + '<h3 style="margin:0 0 8px">⚠ 报告渲染失败（数据字段不符契约，非任务未执行）</h3>'
      + '<p style="margin:0 0 6px">build：<b>' + id + '</b></p>'
      + '<pre style="white-space:pre-wrap;font-size:12px;margin:8px 0;color:#7f1d1d">' + esc(String((e && e.stack) || e)) + '</pre>'
      + '<p style="margin:6px 0 0;font-size:13px">排查：按契约修 <code>data/{BUILD}.js</code>（比率 0~1、cases 含 result/title、buildNo 等）后重跑 <code>emit-report.py</code>。</p></div>';
  }
  function $(sel) { return document.querySelector(sel); }
  // driver 字段口径（cli|mcp-remote|mcp-plugin-fallback|manual）→ 友好标签；plugin 降级加⚠️警示，防报告失真被忽略
  function driverLabel(d) {
    var map = {
      "cli": "本机 CLI（chrome-devtools）", "mcp-remote": "远程 MCP",
      "mcp-plugin-fallback": "⚠️ 插件 MCP 降级（本机 cli 不可用时的同插件 MCP 协议路径）",
      "manual": "手工", "mcp": "MCP（旧口径）",
    };
    return map[d] || (d || "—");
  }
  // ★ 渲染模式 = 环境事实字段（缺陷反馈修复）：严禁把"未取到/异常值"兜底成「有头」（旧 bug：!== headless → 有头，
  //   把"没实测/没填对"伪装成有头）。三态：headless→无头 / headed→有头 / 其它(null/未取到/异常)→显式「未取到」并标 ⚠️。
  //   渲染模式等环境事实字段必须由执行期取证填充（见 README「环境事实类字段」），取不到写 renderMode=null（不许编）。
  //   b.renderModeSource：来源标注（显式指定 / 复用已有实例〔含来源〕 / 无头不可用降级〔含原因〕），有则附显。
  function renderModeLabel(b) {
    var rm = b.renderMode;
    var label = rm === "headless" ? "无头"
              : rm === "headed"   ? "有头"
              : (rm ? "⚠️ 异常值：" + String(rm) : "⚠️ 未取到");
    if (b.renderModeSource) label += "（来源：" + String(b.renderModeSource) + "）";
    return label;
  }
  // item 6：复测关系徽标（build 由上一 finalized build 修复后铸新复测时，data 带 retestOf/retestRound）
  function retestTag(b) {
    if (!b || !b.retestOf) return "";
    var fixed = (b.fixedDefects && b.fixedDefects.length) ? "，修复 " + b.fixedDefects.map(esc).join("/") : "";
    var tip = "复测自 " + esc(b.retestOf) + (b.retestRound ? " · 第" + b.retestRound + "轮" : "") + fixed;
    return '<span title="' + tip + '" style="display:inline-block;margin-left:6px;padding:1px 7px;border-radius:9px;'
      + 'background:#eef2ff;color:#4338ca;font-size:11px;font-weight:600;vertical-align:middle;">🔁 第'
      + (b.retestRound || "?") + '轮复测</span>';
  }
  function el(tag, attrs, html) {
    var e = document.createElement(tag);
    if (attrs) for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (html != null) e.innerHTML = html;
    return e;
  }

  /* =====================================================================
   * SVG 图表函数（全部返回 SVG 字符串，无外部依赖）
   * =================================================================== */

  /**
   * 环形图（甜甜圈）— 展示 pass/fail/block/skip/na 分布
   * @param {object} dist {pass,fail,block,skip,na}
   * @param {number} size 画布边长
   */
  function svgDonut(dist, size) {
    size = size || 220;
    var cx = size / 2, cy = size / 2;
    var r = size * 0.38, stroke = size * 0.14;
    var total = RESULT_KEYS.reduce(function (s, k) { return s + (dist[k] || 0); }, 0);
    var circ = 2 * Math.PI * r;
    var offset = 0, arcs = "";
    if (total === 0) {
      arcs = '<circle cx="' + cx + '" cy="' + cy + '" r="' + r + '" fill="none" stroke="#e5e7eb" stroke-width="' + stroke + '"/>';
    } else {
      RESULT_KEYS.forEach(function (k) {
        var val = dist[k] || 0;
        if (val === 0) return;
        var frac = val / total;
        var len = frac * circ;
        // stroke-dasharray 段 + 旋转定位实现环形分段
        arcs += '<circle cx="' + cx + '" cy="' + cy + '" r="' + r + '" fill="none" '
              + 'stroke="' + COLORS[k] + '" stroke-width="' + stroke + '" '
              + 'stroke-dasharray="' + len.toFixed(2) + ' ' + (circ - len).toFixed(2) + '" '
              + 'stroke-dashoffset="' + (-offset).toFixed(2) + '" '
              + 'transform="rotate(-90 ' + cx + ' ' + cy + ')" stroke-linecap="butt"><title>'
              + RESULT_TEXT[k] + ' ' + val + '</title></circle>';
        offset += len;
      });
    }
    var passRate = total ? Math.round((dist.pass || 0) / total * 100) : 0;
    return '<svg viewBox="0 0 ' + size + ' ' + size + '" width="' + size + '" height="' + size + '" role="img">'
      + arcs
      + '<text x="' + cx + '" y="' + (cy - 4) + '" text-anchor="middle" font-size="' + (size * 0.2) + '" font-weight="700" fill="#1f2937">' + passRate + '%</text>'
      + '<text x="' + cx + '" y="' + (cy + size * 0.13) + '" text-anchor="middle" font-size="' + (size * 0.065) + '" fill="#6b7280">通过率</text>'
      + '</svg>';
  }

  /** 图例（环形/饼图共用）*/
  function legendHtml(dist) {
    return '<div class="legend">' + RESULT_KEYS.map(function (k) {
      return '<span class="legend-item"><span class="legend-swatch" style="background:' + COLORS[k] + '"></span>'
        + RESULT_TEXT[k] + ' ' + (dist[k] || 0) + '</span>';
    }).join("") + '</div>';
  }

  /**
   * 各 build 通过率趋势 — 折线 + 数据点（X=buildNo，Y=通过率 0~100%）
   * @param {Array} builds 已按 buildNo 升序
   */
  function svgTrend(builds) {
    var W = 720, H = 260, padL = 48, padR = 24, padT = 24, padB = 44;
    var iw = W - padL - padR, ih = H - padT - padB;
    var n = builds.length;
    // Y 轴网格线 0/25/50/75/100
    var yLines = "";
    [0, 25, 50, 75, 100].forEach(function (v) {
      var y = padT + ih - (v / 100) * ih;
      yLines += '<line x1="' + padL + '" y1="' + y + '" x2="' + (W - padR) + '" y2="' + y + '" stroke="#eef0f2"/>'
        + '<text x="' + (padL - 8) + '" y="' + (y + 4) + '" text-anchor="end" font-size="11" fill="#9ca3af">' + v + '%</text>';
    });
    function px(i) { return n === 1 ? padL + iw / 2 : padL + (i / (n - 1)) * iw; }
    function py(rate) { return padT + ih - rate01(rate) * ih; }  // rate01 归一，防 0~100 口径把点画到画布外
    var pts = builds.map(function (b, i) { return [px(i), py(b.summary.passRate)]; });
    // 折线路径
    var path = pts.map(function (p, i) { return (i === 0 ? "M" : "L") + p[0].toFixed(1) + " " + p[1].toFixed(1); }).join(" ");
    // 面积填充（折线下方淡色）
    var area = "M" + pts[0][0].toFixed(1) + " " + (padT + ih) + " "
      + pts.map(function (p) { return "L" + p[0].toFixed(1) + " " + p[1].toFixed(1); }).join(" ")
      + " L" + pts[pts.length - 1][0].toFixed(1) + " " + (padT + ih) + " Z";
    // 数据点 + X 轴标签
    var dots = "", xlabels = "";
    builds.forEach(function (b, i) {
      var p = pts[i];
      dots += '<circle cx="' + p[0].toFixed(1) + '" cy="' + p[1].toFixed(1) + '" r="4.5" fill="#fff" stroke="' + COLORS.brand + '" stroke-width="2"><title>build' + b.buildNo + ' ' + pct(b.summary.passRate) + '</title></circle>'
        + '<text x="' + p[0].toFixed(1) + '" y="' + (p[1] - 10).toFixed(1) + '" text-anchor="middle" font-size="11" font-weight="600" fill="' + COLORS.brand + '">' + pct(b.summary.passRate) + '</text>';
      xlabels += '<text x="' + p[0].toFixed(1) + '" y="' + (H - padB + 18) + '" text-anchor="middle" font-size="11" fill="#6b7280">#' + b.buildNo + '</text>';
    });
    return '<svg viewBox="0 0 ' + W + ' ' + H + '" width="100%" height="' + H + '" role="img">'
      + yLines
      + '<path d="' + area + '" fill="' + COLORS.brand + '" fill-opacity="0.08"/>'
      + '<path d="' + path + '" fill="none" stroke="' + COLORS.brand + '" stroke-width="2.5" stroke-linejoin="round"/>'
      + dots + xlabels
      + '</svg>';
  }

  /**
   * 套件分解柱状图（堆叠柱）— 每个套件一根柱，按 pass/fail/block/skip/na 堆叠。
   * 套件名按柱宽自动折行（最多 2 行）+ 超长末尾省略，并以 <title> 提供完整名，
   * 避免长名横向溢出与相邻柱标签互相叠加导致文字无法识别。
   */
  function svgSuiteBars(suites) {
    var W = 720, padL = 24, padR = 24, padT = 16, padB = 66;
    var n = suites.length || 1;
    var rowGap = 14;
    var barW = Math.min(64, (W - padL - padR - (n - 1) * rowGap) / n);
    var maxTotal = Math.max.apply(null, suites.map(function (s) { return s.total; }).concat([1]));
    var ih = 180;
    var H = padT + ih + padB;
    // 单行可容纳字符数（按柱宽估算，中文约 12px/字；最少 4 字，保证窄柱也可读）
    var maxChars = Math.max(4, Math.floor(barW / 12));
    // 套件名按宽度折行：最多 2 行，超出末尾省略号；返回行数组
    function wrapName(name) {
      var chars = Array.from(String(name == null ? "" : name));
      if (chars.length <= maxChars) return [chars.join("")];
      var line1 = chars.slice(0, maxChars).join("");
      var rest = chars.slice(maxChars);
      if (rest.length <= maxChars) return [line1, rest.join("")];
      return [line1, rest.slice(0, Math.max(1, maxChars - 1)).join("") + "…"];
    }
    var bars = "", labels = "";
    suites.forEach(function (s, i) {
      var x = padL + i * (barW + rowGap);
      var cx = x + barW / 2;
      var y = padT + ih;
      // 标签组：折行套件名（≤2 行）+ 例数行；整组挂 <title> 显示完整名，鼠标悬停可见全称
      var lines = wrapName(s.name);
      var nameTexts = lines.map(function (ln, li) {
        return '<text x="' + cx + '" y="' + (padT + ih + 16 + li * 13) + '" text-anchor="middle" font-size="10.5" fill="#6b7280">' + esc(ln) + '</text>';
      }).join("");
      var countY = padT + ih + 16 + lines.length * 13 + 1;
      labels += '<g><title>' + esc(s.name) + '（' + s.total + ' 例）</title>' + nameTexts
        + '<text x="' + cx + '" y="' + countY + '" text-anchor="middle" font-size="10" fill="#9ca3af">' + s.total + ' 例</text></g>';
      RESULT_KEYS.forEach(function (k) {
        var val = s[k] || 0;
        if (val === 0) return;
        var h = (val / maxTotal) * ih;
        y -= h;
        bars += '<rect x="' + x + '" y="' + y.toFixed(1) + '" width="' + barW + '" height="' + h.toFixed(1) + '" fill="' + COLORS[k] + '" rx="2"><title>' + esc(s.name) + ' ' + RESULT_TEXT[k] + ' ' + val + '</title></rect>';
      });
    });
    return '<svg viewBox="0 0 ' + W + ' ' + H + '" width="100%" height="' + H + '" role="img">'
      + '<line x1="' + padL + '" y1="' + (padT + ih) + '" x2="' + (W - padR) + '" y2="' + (padT + ih) + '" stroke="#e5e7eb"/>'
      + bars + labels
      + '</svg>';
  }

  /* =====================================================================
   * 数据加载与全局状态
   * =================================================================== */
  var BUILDS = (window.__BUILDS__ || []).slice().map(function (b) {
    if (b && b.buildNo == null) b.buildNo = parseInt((String(b.build || "").match(/_build(\d+)$/) || [])[1], 10) || 0;  // 渲染端兜底派生（与 emit-report.py P1-6 双保险，防 #undefined）
    return b;
  }).sort(function (a, b) { return a.buildNo - b.buildNo; });

  /* =====================================================================
   * 渲染：综合首页
   * =================================================================== */
  function renderOverview() {
    var root = $("#view-overview");
    if (!BUILDS.length) { root.innerHTML = '<div class="card empty-tip">暂无 build 数据。请在 data/ 目录添加 示例_buildNNNN.js 并在 index.html 引入。</div>'; return; }
    try {

    var latest = BUILDS[BUILDS.length - 1];
    // 累计统计
    var totalCases = BUILDS.reduce(function (s, b) { return s + b.summary.total; }, 0);
    var totalDefects = BUILDS.reduce(function (s, b) { return s + (b.defects ? b.defects.length : 0); }, 0);

    // ① KPI 卡
    var kpi = '<div class="kpi-grid">'
      + '<div class="kpi accent-pass"><div class="kpi-label">最新 build 通过率</div><div class="kpi-value">' + pct(latest.summary.passRate) + '</div><div class="kpi-sub">' + esc(latest.build) + '</div></div>'
      + '<div class="kpi accent-brand"><div class="kpi-label">累计 build 数</div><div class="kpi-value">' + BUILDS.length + '</div><div class="kpi-sub">#' + BUILDS[0].buildNo + ' ~ #' + latest.buildNo + '</div></div>'
      + '<div class="kpi"><div class="kpi-label">累计执行用例</div><div class="kpi-value">' + totalCases + '</div><div class="kpi-sub">含历次回归</div></div>'
      + '<div class="kpi accent-fail"><div class="kpi-label">累计缺陷数</div><div class="kpi-value">' + totalDefects + '</div><div class="kpi-sub">所有 build 合计</div></div>'
      + '</div>';

    // ② 趋势图
    var trend = '<div class="section"><div class="section-title">各 build 通过率趋势</div>'
      + '<div class="card chart-box">' + svgTrend(BUILDS) + '<div class="chart-caption">横轴：build 序号 ｜ 纵轴：通过率</div></div></div>';

    // ③ 最新 build 用例分布环形图 + ④ build 列表
    var dist = { pass: latest.summary.pass, fail: latest.summary.fail, block: latest.summary.block, skip: latest.summary.skip };
    var rows = BUILDS.slice().reverse().map(function (b) {
      var s = b.summary;
      return '<tr class="clickable" data-build="' + esc(b.build) + '">'
        + '<td><strong>' + esc(b.build) + '</strong>' + retestTag(b) + '</td>'
        + '<td class="muted">' + esc(b.finishedAt) + '</td>'
        + '<td><div class="rate-bar"><div class="track"><div class="fill" style="width:' + pct(s.passRate) + '"></div></div><span class="rate-num">' + pct(s.passRate) + '</span></div></td>'
        + '<td><span class="dot pass"></span>' + s.pass + '</td>'
        + '<td><span class="dot fail"></span>' + s.fail + '</td>'
        + '<td><span class="dot block"></span>' + s.block + '</td>'
        + '<td><span class="dot skip"></span>' + s.skip + '</td>'
        + '<td>' + (b.defects ? b.defects.length : 0) + '</td></tr>';
    }).join("");

    var grid = '<div class="grid-2 section">'
      + '<div class="card chart-box"><div class="section-title">最新 build 用例分布</div>' + svgDonut(dist, 220) + legendHtml(dist) + '</div>'
      + '<div class="card"><div class="section-title">Build 列表（点击行查看详情）</div><div class="table-wrap"><table class="report-table">'
      + '<thead><tr><th>Build</th><th>完成时间</th><th>通过率</th><th>通过</th><th>失败</th><th>阻塞</th><th>忽略</th><th>缺陷</th></tr></thead>'
      + '<tbody>' + rows + '</tbody></table></div></div></div>';

    root.innerHTML = '<div class="section">' + kpi + '</div>' + trend + grid;

    // 绑定行点击 → 跳转该 build 子页
    root.querySelectorAll("tr.clickable").forEach(function (tr) {
      tr.addEventListener("click", function () { location.hash = "#/build/" + encodeURIComponent(tr.getAttribute("data-build")); });
    });
    } catch (e) { console.error("[report] renderOverview 失败", e); root.innerHTML = errBanner(null, e); }
  }

  /* =====================================================================
   * 渲染：单个 build 子页
   * =================================================================== */
  function renderBuild(build) {
    var root = $("#view-build");
    var b = BUILDS.filter(function (x) { return x.build === build; })[0];
    if (!b) { root.innerHTML = '<div class="card empty-tip">未找到 build：' + esc(build) + '</div>'; return; }
    try {
    var s = b.summary || {};
    // ★ 就地归一化：buildNo 兜底 + cases 字段别名容错（AI 最易写成 name/status/detail，契约是 title/result/note）+ 数组字段
    if (b.buildNo == null) b.buildNo = (String(b.build || "").match(/_build(\d+)$/) || [])[1] || "?";
    b.cases = toArray(b.cases, "cases").map(function (c) {
      c = c || {};
      var aliased = (c.title == null && c.name != null) || (c.result == null && c.status != null) || (c.note == null && c.detail != null);
      if (aliased && !_caseAliasWarned) { console.warn("[report] cases[] 使用了非契约字段名（name/status/detail）→ 已按 title/result/note 兼容；请修生成端字段名"); _caseAliasWarned = true; }
      return { id: c.id, title: (c.title != null ? c.title : c.name), suite: (c.suite != null ? c.suite : c.suiteId),
               result: (c.result != null ? c.result : c.status) || "", note: (c.note != null ? c.note : c.detail), screenshot: c.screenshot };
    });
    b.defects = toArray(b.defects, "defects");
    b.runtimeErrors = toArray(b.runtimeErrors, "runtimeErrors");
    b.suites = toArray(b.suites, "suites");
    var dist = { pass: s.pass, fail: s.fail, block: s.block, skip: s.skip };

    // 概览 KPI
    var kpi = '<div class="kpi-grid">'
      + '<div class="kpi accent-pass"><div class="kpi-label">通过率</div><div class="kpi-value">' + pct(s.passRate) + rateWarnBadge(s.passRate) + '</div><div class="kpi-sub">' + s.pass + ' / ' + s.total + ' 通过</div></div>'
      + '<div class="kpi"><div class="kpi-label">用例总数</div><div class="kpi-value">' + s.total + '</div></div>'
      + '<div class="kpi accent-fail"><div class="kpi-label">失败 / 阻塞</div><div class="kpi-value">' + s.fail + ' / ' + s.block + '</div></div>'
      + '<div class="kpi"><div class="kpi-label">缺陷 / 运行时错误</div><div class="kpi-value">' + (b.defects ? b.defects.length : 0) + ' / ' + (b.runtimeErrors ? b.runtimeErrors.length : 0) + '</div></div>'
      + '</div>';

    // 环形 + 套件柱状
    var charts = '<div class="grid-2 section">'
      + '<div class="card chart-box"><div class="section-title">用例分布</div>' + svgDonut(dist, 220) + legendHtml(dist) + '</div>'
      + '<div class="card chart-box"><div class="section-title">套件分解</div>' + svgSuiteBars(b.suites || []) + legendHtml(dist) + '</div>'
      + '</div>';

    // 用例明细表
    var caseRows = (b.cases || []).map(function (c) {
      // 截图列：内联缩略图，点击经事件委托弹出页内大图 modal（无截图则显示 —）
      var shot = c.screenshot
        ? '<img class="shot-thumb" src="' + esc(c.screenshot) + '" alt="截图" loading="lazy" data-full="' + esc(c.screenshot) + '" data-cap="' + esc(c.id + "　" + c.title) + '" />'
        : '<span class="muted">—</span>';
      return '<tr><td>' + esc(c.id) + '</td><td class="wrap">' + esc(c.title) + '</td><td class="muted">' + esc(c.suite) + '</td>'
        + '<td><span class="badge ' + c.result + '">' + (RESULT_TEXT[c.result] || c.result) + '</span></td>'
        + '<td class="wrap muted">' + esc(c.note) + '</td><td>' + shot + '</td></tr>';
    }).join("") || '<tr><td colspan="6" class="empty-tip">无用例</td></tr>';
    var caseTable = '<div class="section"><div class="card"><div class="section-title">用例明细</div><div class="table-wrap"><table class="report-table">'
      + '<thead><tr><th>用例 ID</th><th>标题</th><th>套件</th><th>结果</th><th>备注</th><th>截图</th></tr></thead><tbody>' + caseRows + '</tbody></table></div></div></div>';

    // 缺陷表
    var defRows = (b.defects || []).map(function (d) {
      return '<tr><td>' + esc(d.id) + '</td><td class="wrap">' + esc(d.title) + '</td><td><span class="sev ' + esc(d.severity) + '">' + esc(d.severity) + '</span></td>'
        + '<td>' + esc(d.caseId) + '</td><td>' + esc(d.status) + '</td></tr>';
    }).join("") || '<tr><td colspan="5" class="empty-tip">无缺陷</td></tr>';
    var defTable = '<div class="section"><div class="card"><div class="section-title">缺陷汇总</div><div class="table-wrap"><table class="report-table">'
      + '<thead><tr><th>缺陷 ID</th><th>标题</th><th>严重级</th><th>关联用例</th><th>状态</th></tr></thead><tbody>' + defRows + '</tbody></table></div></div></div>';

    // 运行时错误表
    var rtRows = (b.runtimeErrors || []).map(function (r) {
      return '<tr><td>' + esc(r.id) + '</td><td class="wrap">' + esc(r.desc) + '</td><td class="muted">' + esc(r.url) + '</td><td>' + esc(r.status) + '</td></tr>';
    }).join("") || '<tr><td colspan="4" class="empty-tip">无运行时错误</td></tr>';
    var rtTable = '<div class="section"><div class="card"><div class="section-title">运行时错误</div><div class="table-wrap"><table class="report-table">'
      + '<thead><tr><th>错误 ID</th><th>描述</th><th>页面</th><th>状态</th></tr></thead><tbody>' + rtRows + '</tbody></table></div></div></div>';

    // 元信息
    // 运行元信息：短字段走紧凑栅格；长字段（部署模式 / 触发原因 / 访问地址）整行铺开（wide），避免在窄列里挤成多行 / 撑破
    var meta = '<div class="section"><div class="card"><div class="section-title">运行元信息</div><div class="meta-grid">'
      + metaItem("版本", b.version) + metaItem("Build 序号", "#" + b.buildNo)
      + (b.retestOf ? metaItem("复测关系", "🔁 复测自 " + b.retestOf + (b.retestRound ? " · 第" + b.retestRound + "轮" : "") + ((b.fixedDefects && b.fixedDefects.length) ? "，修复 " + b.fixedDefects.join("/") : ""), true) : "")
      + metaItem("代码分支", b.branch) + metaItem("渲染模式", renderModeLabel(b))
      + metaItem("驱动方式", driverLabel(b.driver), b.driver === "mcp-plugin-fallback")
      + metaItem("开始时间", b.startedAt) + metaItem("结束时间", b.finishedAt)
      + metaItem("部署模式", b.deployMode, true)
      + metaItem("触发原因", b.trigger, true)
      + metaItem("访问地址", b.testUrl, true)
      + '</div></div></div>';

    root.innerHTML = '<div class="section">' + kpi + '</div>' + charts + caseTable + defTable + rtTable + meta;
    } catch (e) { console.error("[report] renderBuild 失败", e); root.innerHTML = errBanner(b, e); }
  }
  function metaItem(k, v, wide) {
    return '<div class="meta-item' + (wide ? ' wide' : '') + '"><span class="meta-k">' + esc(k) + '</span><span class="meta-v">' + esc(v) + '</span></div>';
  }

  /* =====================================================================
   * 截图灯箱（modal）：点击用例明细「截图」列缩略图 → 页内弹出大图
   * 用事件委托绑定，兼容各 build 子页动态渲染出来的缩略图；按 Esc / 点遮罩 / 点关闭按钮关闭。
   * 缩略图加载失败（离线无对应 png）时优雅降级为「—」，不显示裂图。
   * =================================================================== */
  function setupShotModal() {
    var modal = $("#shot-modal");
    if (!modal) return;
    var imgEl = modal.querySelector(".shot-modal-img");
    var capEl = modal.querySelector(".shot-modal-cap");
    function open(src, caption) {
      imgEl.setAttribute("src", src);
      capEl.textContent = caption || "";
      modal.hidden = false;
      document.body.style.overflow = "hidden";   // 弹窗期间禁滚动底层
    }
    function close() {
      modal.hidden = true;
      imgEl.removeAttribute("src");
      document.body.style.overflow = "";
    }
    // 委托：点击任意缩略图开图
    document.addEventListener("click", function (e) {
      var t = e.target;
      if (t && t.classList && t.classList.contains("shot-thumb")) {
        open(t.getAttribute("data-full"), t.getAttribute("data-cap"));
      }
    });
    // 关闭：关闭按钮 / 点遮罩 / Esc
    var closeBtn = modal.querySelector(".shot-modal-close");
    if (closeBtn) closeBtn.addEventListener("click", close);
    var backdrop = modal.querySelector(".shot-modal-backdrop");
    if (backdrop) backdrop.addEventListener("click", close);
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !modal.hidden) close(); });
    // 缩略图加载失败 → 降级为「—」（error 不冒泡，用捕获阶段委托）
    document.addEventListener("error", function (e) {
      var t = e.target;
      if (t && t.classList && t.classList.contains("shot-thumb") && t.parentNode) {
        var span = document.createElement("span");
        span.className = "muted"; span.textContent = "—";
        t.parentNode.replaceChild(span, t);
      }
    }, true);
  }

  /* =====================================================================
   * 顶部 build 下拉填充
   * =================================================================== */
  function fillBuildSelect() {
    var sel = $("#build-select");
    sel.innerHTML = BUILDS.slice().reverse().map(function (b) {
      return '<option value="' + esc(b.build) + '">' + esc(b.build) + '（' + pct(b.summary.passRate) + '）</option>';
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
      window.scrollTo(0, 0);
    } else {
      setActive("overview");
      renderOverview();
    }
  }

  /* =====================================================================
   * 启动
   * =================================================================== */
  function boot() {
    fillBuildSelect();
    setupShotModal();
    renderOverview();
    // tab 切换
    $("#tab-overview").addEventListener("click", function () { location.hash = "#/overview"; });
    $("#tab-build").addEventListener("click", function () {
      var sel = $("#build-select");
      var target = sel.value || (BUILDS.length ? BUILDS[BUILDS.length - 1].build : "");
      location.hash = target ? "#/build/" + encodeURIComponent(target) : "#/overview";
    });
    window.addEventListener("hashchange", route);
    route();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
