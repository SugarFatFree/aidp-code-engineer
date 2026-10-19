#!/usr/bin/env node
/* P1-7 单测：报告渲染（口径 pct + 坏数据健壮性）。直接 `node .aidp/scripts/tests/test_report_render.js` 运行；exit 0=全绿。
 * pct 是 IIFE 私有函数，经【公开渲染路径】断言其行为（0.84→84%、100.0→100% 不出 10000%）。 */
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = path.resolve(__dirname, "..", "..", "..");

function makeEl() {
  const el = { _html: "", value: "", style: {},
    classList: { toggle() {}, add() {}, remove() {}, contains() { return false; } },
    addEventListener() {}, removeEventListener() {}, setAttribute() {}, getAttribute() { return null; },
    appendChild() {}, querySelector() { return makeEl(); }, querySelectorAll() { return []; }, focus() {}, click() {} };
  Object.defineProperty(el, "innerHTML", { get() { return el._html; }, set(v) { el._html = String(v); } });
  return el;
}

function render(appRel, globalVar, data, build) {
  const cache = {};
  const doc = { readyState: "complete", documentElement: makeEl(),
    querySelector(s) { return cache[s] || (cache[s] = makeEl()); }, querySelectorAll() { return []; },
    getElementById(id) { return cache["#" + id] || (cache["#" + id] = makeEl()); }, createElement() { return makeEl(); }, addEventListener() {} };
  const win = { document: doc, location: { hash: "#/build/" + build, search: "" }, addEventListener() {},
    matchMedia() { return { matches: false, addEventListener() {} }; },
    localStorage: { getItem() { return null; }, setItem() {} }, print() {}, scrollTo() {} };
  win[globalVar] = [data];
  const warns = [];
  const c = { warn: (...a) => warns.push(a.join(" ")), error: (...a) => warns.push("ERR:" + a.join(" ")), log() {} };
  let threw = null;
  try {
    new Function("window", "document", "location", "console", "localStorage",
      fs.readFileSync(path.join(ROOT, appRel), "utf8"))(win, doc, win.location, c, win.localStorage);
  } catch (e) { threw = String((e && e.stack) || e); }
  return { html: (cache["#view-build"] || {})._html || "", warns, threw };
}

const EXEC = ".aidp/templates/reports/AI执行报告/assets/app.js";
const TEST = ".aidp/templates/reports/AI测试报告/assets/app.js";
let fails = [];
function check(cond, msg) { console.log((cond ? "  ✅ " : "  ❌ ") + msg); if (!cond) fails.push(msg); }

console.log("① pct 口径经渲染路径（防 10000%）");
let r = render(TEST, "__BUILDS__", { build: "V0.1.0_build1", version: "V0.1.0", buildNo: 1,
  summary: { total: 50, pass: 42, fail: 5, block: 2, skip: 1, passRate: 0.84 }, suites: [], cases: [], defects: [], runtimeErrors: [] }, "V0.1.0_build1");
check(!r.threw && r.html.indexOf("84%") >= 0, "passRate 0.84 → 渲染出 84%");
check(r.html.indexOf("8400%") < 0, "passRate 0.84 → 不出现 8400%");

r = render(TEST, "__BUILDS__", { build: "V0.1.0_build1", version: "V0.1.0", buildNo: 1,
  summary: { total: 5, pass: 5, fail: 0, block: 0, skip: 0, passRate: 100.0 }, suites: [], cases: [], defects: [], runtimeErrors: [] }, "V0.1.0_build1");
check(r.html.indexOf("100%") >= 0 && !/[1-9]\d{3,}%/.test(r.html), "passRate 100.0 → 100%（无 10000%）+ 口径 warn");
check(r.warns.some((w) => w.indexOf("口径异常") >= 0), "passRate 100.0 → 控制台口径告警");

console.log("② 坏数据健壮性（非空 + 无字面量 undefined）");
// risks 分组对象（白屏根因）
r = render(EXEC, "__AIRUNS__", { build: "V0.1.0_build1", version: "V0.1.0",
  overview: { statusKind: "pass", featureRate: 1, testPassRate: 1, pendingCount: 0 },
  steps: [{ name: "x" }], features: [{ num: 1, name: "f", status: "done" }], defects: [],
  risks: { high: [], medium: ["R1"], low: ["R2"] }, todos: ["t1"] }, "V0.1.0_build1");
check(!r.threw, "exec risks 分组对象 → 不抛异常(不白屏)");
check(r.html.length > 500, "exec risks 分组对象 → 页面非空(>500)");
check(r.html.indexOf("undefined") < 0, "exec risks 分组对象 → 无字面量 undefined");

// cases 缺 result（别名 status）+ 无 buildNo
r = render(TEST, "__BUILDS__", { build: "V0.1.0_build9", version: "V0.1.0",
  summary: { total: 1, pass: 1, fail: 0, block: 0, skip: 0, passRate: 1 }, suites: [], defects: [], runtimeErrors: [],
  cases: [{ id: "TC-1", name: "别名标题", status: "pass", detail: "别名备注" }] }, "V0.1.0_build9");
check(r.html.indexOf("undefined") < 0, "test cases 用 name/status/detail → 无字面量 undefined");
check(r.html.indexOf("#undefined") < 0, "test 无 buildNo → 派生后无 #undefined");
check(r.html.indexOf("别名标题") >= 0, "test cases name → 别名容错渲染出标题");

console.log("③ 新增回归：na 分布与待实测状态可见");
r = render(TEST, "__BUILDS__", { build: "V0.1.0_build-na", version: "V0.1.0", buildNo: 3,
  summary: { total: 3, pass: 1, fail: 0, block: 0, skip: 0, na: 2, passRate: 1 },
  suites: [], defects: [], runtimeErrors: [],
  cases: [
    { id: "NA-1", title: "不适用一", suite: "S", result: "na", note: "本版无此功能", screenshot: "" },
    { id: "NA-2", title: "不适用二", suite: "S", result: "na", note: "本端不支持", screenshot: "" },
    { id: "P-1", title: "已通过", suite: "S", result: "pass", note: "", screenshot: "" }
  ]
}, "V0.1.0_build-na");
check(!r.threw && r.html.indexOf("不适用") >= 0, "na 用例 → 渲染出不适用语义");
check(r.html.indexOf("100%") >= 0, "na=2/pass=1 → 可执行分母为 1，显示 100%");

r = render(EXEC, "__AIRUNS__", { build: "V0.1.0_build-pending", version: "V0.1.0",
  overview: { statusKind: "pend", featureRate: 0, testPassRate: null, coverage: null, pendingCount: 2 },
  steps: [{ name: "浏览器实测", actualStatus: "plan", plannedStatus: "plan" }], features: [],
  testSummary: { total: null, pass: 0, fail: 0, block: 0, skip: 0, pendingBrowserTest: true },
  defects: [], risks: [], todos: []
}, "V0.1.0_build-pending");
check(!r.threw && r.html.length > 500, "待实测 exec → 页面非空");
check(r.html.indexOf("待实测") >= 0 || r.html.indexOf("计划") >= 0, "待实测 exec → 不伪装成已测完成");

console.log();
if (fails.length) { console.log("❌ " + fails.length + " 项失败"); process.exit(1); }
console.log("✅ 全部通过"); process.exit(0);
