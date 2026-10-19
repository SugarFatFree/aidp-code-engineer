#!/usr/bin/env node
/**
 * 报告渲染冒烟（离线 SPA 白屏/undefined/口径 自检）。被 autopilot-ceremony-gate.py 与 scripts/tests/ 复用。
 *
 * 用法：node report_render_smoke.js <reportDir> <build> [renderScript] [containerSelector]
 *   reportDir        = docs/reports/{V}/{AI执行报告|AI测试报告}（含 *.html + assets/*.js + data/{build}.js）
 *   build            = 形如 V0.1.0_build1001
 *   renderScript     = 可选。只测这一个渲染脚本（"plan.js" 或 "assets/plan.js"）
 *   containerSelector= 可选。配合上一个参数指定容器（如 "#view-plan"）
 *
 * ★ 默认（不传后两个参数）= **自动枚举 reportDir 下每个 *.html**，从各自的
 *   `<script src="assets/*.js">` 取渲染脚本、从 `id="view-*"` 取候选容器，逐页独立渲染并断言。
 *   之所以自动枚举而非写死一对：写死的失败形态正是本门要堵的那一类 —— 有人新加一个渲染页
 *   （exec 的 plan.html + plan.js 就是实例），没人记得同步改这里，于是那一页抛异常整页白屏，
 *   而门始终绿、报告照常交付、链接点开是空白。自动枚举让"新增一页即被覆盖"成为默认。
 *
 * 每页断言 #view-* 容器：
 *   ① 无未捕获异常 ② innerHTML.length > 500（白屏必挂）③ 无字面量 undefined/NaN ④ 无 ≥1000% 百分比（10000% 类）。
 * 输出一行 JSON：{ok, len, undefinedCount, nanCount, bigPct, threw, warns, pages:[...]}
 *   顶层字段为**各页聚合**（len 取最小、计数取和、threw 取首个），保持与既有调用方兼容；
 *   `pages[]` 给出逐页明细（html / script / view / len / ok / reasons）。
 * exit 0=全部通过 / 1=有页不通过 / 2=用法或文件错误。
 */
"use strict";
const fs = require("fs");
const path = require("path");

function makeEl() {
  const el = {
    _html: "", value: "", style: {},
    classList: { toggle() {}, add() {}, remove() {}, contains() { return false; } },
    addEventListener() {}, removeEventListener() {},
    setAttribute() {}, getAttribute() { return null; },
    appendChild() {}, removeChild() {},
    querySelector() { return makeEl(); }, querySelectorAll() { return []; },
    focus() {}, click() {},
  };
  Object.defineProperty(el, "innerHTML", { get() { return el._html; }, set(v) { el._html = String(v); } });
  return el;
}

/** 从 html 源码取「assets/ 下的渲染脚本」与「id="view-*" 容器」两组事实 */
function scanPage(htmlSrc) {
  const scripts = [];
  const views = [];
  const rxScript = /<script[^>]*\ssrc\s*=\s*["']([^"']+)["']/gi;
  let m;
  while ((m = rxScript.exec(htmlSrc))) {
    const src = m[1];
    if (/(^|\/)assets\/[^/]+\.js$/i.test(src)) scripts.push(src.replace(/^\.?\//, ""));
  }
  const rxView = /id\s*=\s*["'](view-[A-Za-z0-9_-]+)["']/gi;
  while ((m = rxView.exec(htmlSrc))) {
    if (views.indexOf(m[1]) < 0) views.push(m[1]);
  }
  return { scripts, views };
}

/** 在一个全新沙箱里按序 eval data + 渲染脚本，返回各候选容器的 innerHTML */
function renderPage(dataJs, scriptPaths, build, viewIds) {
  const cache = {};
  const doc = {
    readyState: "complete", documentElement: makeEl(),
    querySelector(sel) { return cache[sel] || (cache[sel] = makeEl()); },
    querySelectorAll() { return []; },
    getElementById(id) { return cache["#" + id] || (cache["#" + id] = makeEl()); },
    createElement() { return makeEl(); }, addEventListener() {},
  };
  const win = {
    document: doc, location: { hash: "#/build/" + build, search: "", pathname: "/报告/index.html" },
    addEventListener() {}, matchMedia() { return { matches: false, addEventListener() {} }; },
    localStorage: { getItem() { return null; }, setItem() {} },
    print() {}, scrollTo() {},
  };
  const warns = [];
  const sandboxConsole = {
    warn: (...a) => warns.push(a.join(" ")),
    error: (...a) => warns.push("ERR:" + a.join(" ")),
    log() {},
  };
  let threw = null;
  try {
    // ① 先 eval data（自注册 window.__AIRUNS__/__BUILDS__），再按 html 中的顺序 eval 渲染脚本
    const runData = new Function("window", "document", "location", fs.readFileSync(dataJs, "utf8"));
    runData(win, doc, win.location);
    for (const sp of scriptPaths) {
      const runApp = new Function("window", "document", "location", "console", "localStorage",
        fs.readFileSync(sp, "utf8"));
      runApp(win, doc, win.location, sandboxConsole, win.localStorage);
    }
  } catch (e) { threw = String((e && e.stack) || e); }

  const htmls = {};
  for (const v of viewIds) {
    const sel = "#" + v;
    htmls[v] = cache[sel] ? cache[sel]._html : "";
  }
  return { htmls, warns, threw };
}

// ★ undefined/NaN 的检测面要**剔除 <code>/<pre> 的内容**：那里面的 "undefined" 是
//   报告在**讲述**一个技术事实（如缺陷描述里写 `Number(undefined) === NaN` 的成因），
//   不是渲染故障。整页 grep 会把它判成 FAIL，逼作者把技术术语改写成中文「未定义值」
//   才能过门 —— 那是为迎合检查而损失技术准确性（下游实证：8 处命中全属描述文本）。
//   真正的渲染故障形态是"该填值的位置露出了字面量"，那些位置不在 code/pre 里。
// ★ 只认**值位**上的 undefined，不做全文 grep。真正的渲染故障形态是「该填值的位置
//   露出了字面量」——它独占一个元素/单元格、或紧贴 `#` `%` `:` 这类值标记；
//   而报告正文里**叙述** JS 行为（实证：`note` 写「前端 currentTenantId() 在两者皆空时返
//   undefined」）是合法内容，全文 grep 会把它判成数据缺陷，逼作者把技术术语改写成
//   「返 JS 未定义值」才能过门 —— 那是**让文档去迁就检查器**，方向反了。
const VALUE_SLOT_UNDEFINED = [
  />\s*undefined\s*</gi,        // 独占一个元素/单元格
  /#undefined\b/gi,             // build 号派生失败（满页 #undefined 的那种）
  /\bundefined\s*%/gi,          // 比率位
  /:\s*undefined\s*(?:[,}<]|$)/gim,  // 「标签：值」渲染里的值位
  /\bundefined\s*\/\s*undefined\b/gi,  // 分数位两侧都空
];

/** 对单个容器 html 跑四项断言 */
function assertHtml(html) {
  const scanHtml = html
    .replace(/<code\b[^>]*>[\s\S]*?<\/code>/gi, "<code/>")
    .replace(/<pre\b[^>]*>[\s\S]*?<\/pre>/gi, "<pre/>");
  let undefinedCount = 0;
  for (const rx of VALUE_SLOT_UNDEFINED) {
    undefinedCount += (scanHtml.match(rx) || []).length;
  }
  // ⛔ 兜底：即便全部落在叙述性文本里，**密集出现**本身就是渲染故障的征兆
  //    （「满屏 undefined」正是本门最初要抓的形态）。阈值取 8：下游实证的叙述性命中是 1 处。
  const undefinedTotal = (scanHtml.match(/\bundefined\b/gi) || []).length;
  if (undefinedTotal >= 8) undefinedCount = Math.max(undefinedCount, undefinedTotal);
  const nanCount = (scanHtml.match(/>NaN<|>NaN%|\bNaN\b/g) || []).length;
  const bigPct = scanHtml.match(/[1-9]\d{3,}%/g) || [];  // ≥1000%（10000% 类；100% 合法不算）
  return { len: html.length, undefinedCount, nanCount, bigPct };
}

function resolveScript(reportDir, name) {
  const rel = name.indexOf("/") >= 0 ? name : path.join("assets", name);
  return path.join(reportDir, rel);
}

function main() {
  const reportDir = process.argv[2];
  const build = process.argv[3];
  const explicitScript = process.argv[4];
  const explicitView = process.argv[5];
  if (!reportDir || !build) {
    console.error("用法: node report_render_smoke.js <reportDir> <build> [renderScript] [containerSelector]");
    process.exit(2);
  }
  const dataJs = path.join(reportDir, "data", build + ".js");
  if (!fs.existsSync(dataJs)) {
    console.error(JSON.stringify({ ok: false, error: "缺文件: " + dataJs })); process.exit(2);
  }

  // ---- 待测页清单 ----
  const targets = [];
  if (explicitScript) {
    // 显式单对模式（向后兼容的逃生口；容器缺省沿用历史默认 #view-build）
    const sp = resolveScript(reportDir, explicitScript);
    if (!fs.existsSync(sp)) {
      console.error(JSON.stringify({ ok: false, error: "缺文件: " + sp })); process.exit(2);
    }
    const view = String(explicitView || "#view-build").replace(/^#/, "");
    targets.push({ html: "(显式指定)", scripts: [sp], views: [view] });
  } else {
    const htmlFiles = fs.readdirSync(reportDir).filter((f) => /\.html$/i.test(f)).sort();
    if (!htmlFiles.length) {
      // 没有 html 的目录退回历史行为（assets/app.js + #view-build），避免旧调用方直接报错
      const legacy = path.join(reportDir, "assets", "app.js");
      if (!fs.existsSync(legacy)) {
        console.error(JSON.stringify({ ok: false, error: "缺文件: " + legacy })); process.exit(2);
      }
      targets.push({ html: "(无 html，回退 assets/app.js)", scripts: [legacy], views: ["view-build"] });
    }
    for (const hf of htmlFiles) {
      const scan = scanPage(fs.readFileSync(path.join(reportDir, hf), "utf8"));
      if (!scan.scripts.length) continue;           // 非渲染页（无 assets/*.js）→ 不测
      const abs = scan.scripts.map((s) => path.join(reportDir, s));
      targets.push({ html: hf, scripts: abs, views: scan.views });
    }
    if (!targets.length) {
      console.error(JSON.stringify({ ok: false, error: "reportDir 下未发现任何渲染页（*.html + assets/*.js）: " + reportDir }));
      process.exit(2);
    }
  }

  // ---- 逐页渲染 + 断言 ----
  const pages = [];
  for (const t of targets) {
    const scriptNames = t.scripts.map((p) => path.relative(reportDir, p));
    if (!t.views.length) {
      // fail-closed：有渲染脚本却识别不出容器 ⇒ 这一页此后永远测不到，必须报出来而不是跳过
      pages.push({
        html: t.html, script: scriptNames.join(","), view: null, ok: false, len: 0,
        undefinedCount: 0, nanCount: 0, bigPct: [], threw: null, warns: [],
        reasons: ['识别不出渲染容器（页面缺 id="view-*"）：请补容器 id，或显式传 [renderScript] [containerSelector]'],
      });
      continue;
    }
    const r = renderPage(dataJs, t.scripts, build, t.views);
    // hash 指向 build 时必须检查 view-build，不能用首页非空掩盖明细白屏。
    const best = t.views.indexOf("view-build") >= 0 ? "view-build" : t.views[0];
    const a = assertHtml(r.htmls[best] || "");
    const reasons = [];
    if (r.threw) reasons.push("渲染抛异常(白屏)：" + r.threw.split("\n")[0]);
    if (r.warns.some((w) => w.startsWith("ERR:"))) reasons.push("渲染器捕获到异常：" + r.warns.filter((w) => w.startsWith("ERR:")).join("；"));
    if (a.len <= 500) reasons.push("#" + best + " 过短(" + a.len + ")=疑似白屏");
    if (a.undefinedCount) reasons.push("字面量 undefined ×" + a.undefinedCount);
    if (a.nanCount) reasons.push("NaN ×" + a.nanCount);
    if (a.bigPct.length) reasons.push("≥1000% 百分比：" + a.bigPct.join(","));
    pages.push({
      html: t.html, script: scriptNames.join(","), view: "#" + best,
      ok: reasons.length === 0, len: a.len, undefinedCount: a.undefinedCount,
      nanCount: a.nanCount, bigPct: a.bigPct, threw: r.threw, warns: r.warns, reasons,
    });
  }

  // ---- 聚合（顶层字段沿用历史契约，调用方无需改读法）----
  const ok = pages.every((p) => p.ok);
  const firstThrew = (pages.find((p) => p.threw) || {}).threw || null;
  const out = {
    ok,
    len: Math.min.apply(null, pages.map((p) => p.len)),
    undefinedCount: pages.reduce((s, p) => s + p.undefinedCount, 0),
    nanCount: pages.reduce((s, p) => s + p.nanCount, 0),
    bigPct: pages.reduce((s, p) => s.concat(p.bigPct), []),
    threw: firstThrew,
    warns: pages.reduce((s, p) => s.concat(p.warns.map((w) => p.html + ": " + w)), []),
    pages,
  };
  console.log(JSON.stringify(out));
  process.exit(ok ? 0 : 1);
}
main();
