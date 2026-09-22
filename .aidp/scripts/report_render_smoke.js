#!/usr/bin/env node
/**
 * 报告渲染冒烟（离线 SPA 白屏/undefined/口径 自检）。被 autopilot-ceremony-gate.py 与 scripts/tests/ 复用。
 *
 * 用法：node report_render_smoke.js <reportDir> <build>
 *   reportDir = docs/reports/{V}/{AI执行报告|AI测试报告}（含 assets/app.js + data/{build}.js）
 *   build     = 形如 V0.1.0_build1001
 *
 * 用最小 DOM stub 加载 data/{build}.js（自注册 window.__AIRUNS__/__BUILDS__）+ assets/app.js，
 * 把 hash 设为 #/build/{build} 触发 boot()/route()，断言 #view-build：
 *   ① 无未捕获异常 ② innerHTML.length > 500（白屏必挂）③ 无字面量 undefined/NaN ④ 无 ≥1000% 百分比（10000% 类）。
 * 输出一行 JSON：{ok, len, undefinedCount, nanCount, bigPct, threw, warns}；exit 0=通过 / 1=不通过 / 2=用法/文件错。
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

function main() {
  const reportDir = process.argv[2];
  const build = process.argv[3];
  if (!reportDir || !build) {
    console.error("用法: node report_render_smoke.js <reportDir> <build>");
    process.exit(2);
  }
  const appJs = path.join(reportDir, "assets", "app.js");
  const dataJs = path.join(reportDir, "data", build + ".js");
  for (const f of [appJs, dataJs]) {
    if (!fs.existsSync(f)) { console.error(JSON.stringify({ ok: false, error: "缺文件: " + f })); process.exit(2); }
  }

  const cache = {};
  const doc = {
    readyState: "complete", documentElement: makeEl(),
    querySelector(sel) { return cache[sel] || (cache[sel] = makeEl()); },
    querySelectorAll() { return []; },
    getElementById(id) { return cache["#" + id] || (cache["#" + id] = makeEl()); },
    createElement() { return makeEl(); }, addEventListener() {},
  };
  const win = {
    document: doc, location: { hash: "#/build/" + build, search: "" },
    addEventListener() {}, matchMedia() { return { matches: false, addEventListener() {} }; },
    localStorage: { getItem() { return null; }, setItem() {} },
    print() {}, scrollTo() {},
  };
  const warns = [];
  const sandboxConsole = { warn: (...a) => warns.push(a.join(" ")), error: (...a) => warns.push("ERR:" + a.join(" ")), log() {} };

  let threw = null;
  try {
    // ① 先 eval data（自注册 window.__AIRUNS__/__BUILDS__），再 eval app.js（IIFE eval 时读该全局 + boot()）
    const runData = new Function("window", "document", "location", fs.readFileSync(dataJs, "utf8"));
    runData(win, doc, win.location);
    const runApp = new Function("window", "document", "location", "console", "localStorage", fs.readFileSync(appJs, "utf8"));
    runApp(win, doc, win.location, sandboxConsole, win.localStorage);
  } catch (e) { threw = String((e && e.stack) || e); }

  const html = cache["#view-build"] ? cache["#view-build"]._html : "";
  // ★ undefined/NaN 的检测面要**剔除 <code>/<pre> 的内容**：那里面的 "undefined" 是
  //   报告在**讲述**一个技术事实（如缺陷描述里写 `Number(undefined) === NaN` 的成因），
  //   不是渲染故障。整页 grep 会把它判成 FAIL，逼作者把技术术语改写成中文「未定义值」
  //   才能过门 —— 那是为迎合检查而损失技术准确性（下游实证：8 处命中全属描述文本）。
  //   真正的渲染故障形态是"该填值的位置露出了字面量"，那些位置不在 code/pre 里。
  const scanHtml = html
    .replace(/<code\b[^>]*>[\s\S]*?<\/code>/gi, "<code/>")
    .replace(/<pre\b[^>]*>[\s\S]*?<\/pre>/gi, "<pre/>");
  const undefinedCount = (scanHtml.match(/undefined/g) || []).length;
  const nanCount = (scanHtml.match(/>NaN<|>NaN%|\bNaN\b/g) || []).length;
  const bigPct = scanHtml.match(/[1-9]\d{3,}%/g) || [];  // ≥1000%（10000% 类；100% 合法不算）
  const len = html.length;
  const ok = !threw && len > 500 && undefinedCount === 0 && nanCount === 0 && bigPct.length === 0;

  console.log(JSON.stringify({ ok, len, undefinedCount, nanCount, bigPct, threw, warns }));
  process.exit(ok ? 0 : 1);
}
main();
