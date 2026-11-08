#!/usr/bin/env node
"use strict";
// 运行真实版本报告内联脚本，不复制判定逻辑。
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const ROOT = path.resolve(__dirname, "../../..");
const template = path.join(ROOT, ".aidp/templates/reports/版本测试报告/{version}-测试报告.html");
const scripts = [...fs.readFileSync(template, "utf8").matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
function render(builds) {
  const nodes = {};
  const context = vm.createContext({ window: {}, console,
    document: { getElementById(id) { return nodes[id] || (nodes[id] = { innerHTML: "", textContent: "" }); } } });
  scripts.slice(0, -1).forEach(s => vm.runInContext(s, context));
  context.window.__BUILDS__ = structuredClone(builds);
  vm.runInContext(scripts.at(-1), context, { timeout: 1000 });
  return { html: nodes.app.innerHTML, badge: nodes["report-subline"]?.innerHTML || "" };
}
const build = "V0.1.0_build123", commit = "a".repeat(40);
function fixture(status = "PASS") {
  return { build, commit, buildNo: 123, version: "V0.1.0",
    summary: { total: 1, pass: 1, fail: 0, block: 0, skip: 0, na: 0, passRate: 1,
      overallStatus: status, unitStatus: status, browserStatus: "PASS" },
    cases: [{ id: "TC-1", title: "全量实测通过", result: "pass" }], suites: [], defects: [], runtimeErrors: [],
    unitTests: { schema: 1, build, commit, status, reason: "本 build 全量单测", reused: false,
      counts: null, failed_cases: [], primary_error: null,
      runs: [{ run_id: "real-run-1", status, command: ["python3", "-m", "unittest"],
        cwd: "code/backend", env_id: "local", counts: null, failed_cases: [], primary_error: null }] } };
}
let passed = 0;
function test(name, fn) { fn(); passed++; console.log("通过：" + name); }
function notGreen(r) {
  assert(!r.badge.includes("测试通过"), "不能显示测试通过");
  assert(!r.html.includes("达到发布标准"), "不能显示达到发布标准");
}
function green(r) { assert(r.badge.includes("测试通过")); assert(r.html.includes("达到发布标准")); }
for (const status of ["FAIL", "UNVERIFIED", "TIMEOUT", "RUNNING", "PASS"]) {
  test("unit " + status + "：真实内联脚本的联合结论与证据", () => {
    const r = render([fixture(status)]);
    status === "PASS" ? green(r) : notGreen(r);
    assert(r.html.includes("全量实测") && r.html.includes("全量单测"));
    assert(r.html.includes(status + " · "));
    for (const text of ["real-run-1", "python3", "code/backend", "passed：未提供", "failed：未提供", "skipped：未提供", build, commit]) assert(r.html.includes(text), text);
    if (status === "FAIL") assert(r.badge.includes("未通过"));
    if (status === "RUNNING") assert(r.html.includes("不能作为最终验收报告"));
  });
}
test("browser FAIL + unit PASS：摘要和 100% 不能掩盖真实失败", () => {
  const p = fixture(); p.cases[0].result = "fail";
  const r = render([p]); notGreen(r); assert(r.badge.includes("未通过"));
});
function backend(status) {
  const p = fixture(status);
  p.browserTests = { status: "N/A", reason: "纯后端无浏览器适用面" };
  p.summary = { ...p.summary, total: 0, pass: 0, passRate: 0, browserStatus: "N/A" }; p.cases = [];
  return p;
}
test("纯后端 N/A + unit PASS：不伪造浏览器通过率", () => {
  const r = render([backend("PASS")]); green(r);
  assert(r.html.includes("N/A · 不适用") && r.html.includes("纯后端无浏览器适用面"));
});
for (const status of ["FAIL", "UNVERIFIED", "TIMEOUT", "RUNNING"]) test("纯后端 N/A + unit " + status, () => notGreen(render([backend(status)])));
test("缺少 N/A 理由不能通过", () => { const p = backend("PASS"); delete p.browserTests.reason; notGreen(render([p])); });
test("N/A 与已有实测 PASS 冲突不能通过", () => { const p = fixture(); p.browserTests = { status: "N/A", reason: "无界面" }; notGreen(render([p])); });
test("实测全部 na 带理由 + unit PASS", () => {
  const p = fixture(); Object.assign(p.summary, { pass: 0, na: 1, passRate: 0, browserStatus: "N/A" });
  p.cases[0] = { ...p.cases[0], result: "na", note: "本场景不存在" }; green(render([p]));
});
for (const mutate of [
  p => { p.unitTests.commit = "wrong"; },
  p => { p.unitTests.build = "wrong"; },
  p => { delete p.commit; },
  p => { p.unitTests.runs = []; },
  p => { p.unitTests.runs[0].command = []; },
  p => { p.unitTests.runs[0].run_id = ""; },
  p => { p.unitTests.runs.push(structuredClone(p.unitTests.runs[0])); },
  p => { p.unitTests.counts = { passed: -1 }; },
  p => { p.unitTests.runs[0].primary_error = "AssertionError despite PASS"; },
  p => { p.cases = []; },
  p => { p.cases[0].result = "unknown"; },
  p => { p.summary.total = 5; },
  p => { p.summary.overallStatus = "FAIL"; },
  p => { p.summary.unitStatus = "TIMEOUT"; },
  p => { p.summary.browserStatus = "FAIL"; },
  p => { p.summary.browserTested = false; },
  p => { p.summary.pendingCases = 1; },
  p => { p.unitTests = null; }
]) test("证据缺失或与摘要矛盾：" + mutate.toString(), () => {
  const p = fixture(); mutate(p); const r = render([p]); notGreen(r); assert(r.html.includes("UNVERIFIED"));
});
for (const mutate of [
  p => { p.unitTests.runs[0].failed_cases = ["failed_test"]; },
  p => { p.unitTests.counts = { passed: 1, failed: 2, skipped: 0 }; },
  p => { p.unitTests.runs[0].status = "FAIL"; },
  p => { p.defects.push({ id: "D1", title: "真实缺陷", status: "open", severity: "P3" }); },
  p => { p.runtimeErrors.push({ id: "R1", desc: "真实错误" }); },
  p => { p.summary.openBugs = 1; },
  p => { p.suites.push({ name: "失败套件", total: 1, pass: 0, fail: 1 }); }
]) test("真实失败优先：" + mutate.toString(), () => {
  const p = fixture(); mutate(p); const r = render([p]); notGreen(r); assert(r.badge.includes("未通过"));
});
test("先失败后超时：FAIL 与 TIMEOUT 同时保留", () => {
  const p = fixture("TIMEOUT"); p.unitTests.runs.unshift({ ...p.unitTests.runs[0], run_id: "failed-run", status: "FAIL" });
  const r = render([p]); notGreen(r); assert(r.badge.includes("未通过"));
  assert(r.html.includes("TIMEOUT · 超时") && r.html.includes("验证尚未完成"));
});
test("实测通过率从计数计算，忽略陈旧 passRate", () => {
  const p = fixture(); p.summary.passRate = 0;
  const r = render([p]); green(r); assert(r.html.includes('<div class="kpi-value">100%</div>'));
});
test("真实零计数保持零，未知不补零", () => {
  const p = fixture(); p.unitTests.counts = { passed: 3, failed: 0, skipped: null };
  const r = render([p]); green(r); assert(r.html.includes("passed：3；failed：0；skipped：未提供"));
});
test("legacy 无 unitTests 保持原有兼容", () => {
  const p = fixture(); delete p.unitTests;
  for (const k of ["overallStatus", "unitStatus", "browserStatus"]) delete p.summary[k];
  const r = render([p]); green(r); assert(!r.html.includes("全量单测"));
});
test("联合摘要存在却丢失 unitTests 不能伪装 legacy", () => { const p = fixture(); delete p.unitTests; notGreen(render([p])); });
test("browserTests 明确未核验且缺失 unitTests 不能伪装 legacy", () => {
  const p = fixture(); delete p.unitTests;
  for (const k of ["overallStatus", "unitStatus", "browserStatus"]) delete p.summary[k];
  p.browserTests = { status: "TIMEOUT", reason: "浏览器超时" }; notGreen(render([p]));
});
test("最新失败不回退旧 PASS，原始输入不变", () => {
  const old = fixture(), latest = fixture("FAIL"); latest.buildNo++;
  const input = [latest, old], before = JSON.stringify(input); notGreen(render(input)); assert.equal(JSON.stringify(input), before);
});
const flow = fs.readFileSync(path.join(ROOT, ".aidp/flows/version/release-4b.md"), "utf8");
const converter = flow.match(/```javascript\n(function prepareReleaseBuild[\s\S]*?)\n```/);
assert(converter, "发布流程必须携带可执行转换");
const conversion = vm.createContext({}); vm.runInContext(converter[1], conversion);
function convert(builds) { return conversion.releaseBuildScript(structuredClone(builds)); }
function convertedPayload(builds) { const c = vm.createContext({ window: {} }); vm.runInContext(convert(builds), c); return JSON.parse(JSON.stringify(c.window.__BUILDS__[0])); }
test("真实发布转换保留身份、联合证据、failureTriage；递归去除截图且不改源", () => {
  const p = backend("FAIL"); p.failureTriage = { schema: 1, build, commit, items: [{ category: "environment", reason: "原样保留" }] };
  p.screenshots = ["secret.png"]; p.unitTests.runs[0].screenshot = "nested.png";
  const before = JSON.stringify(p), result = convertedPayload([p]);
  for (const k of ["build", "buildNo", "commit", "summary", "browserTests", "failureTriage"]) assert.deepEqual(result[k], p[k]);
  assert.equal(result.unitTests.status, "FAIL"); assert.equal(result.unitTests.runs[0].run_id, "real-run-1");
  assert(!convert([p]).includes("secret.png") && !convert([p]).includes("nested.png"));
  assert.equal(JSON.stringify(p), before); notGreen(render([result]));
});
for (const mutate of [
  p => { p.unitTests.status = "RUNNING"; },
  p => { p.unitTests.runs[0].status = "RUNNING"; },
  p => { p.browserTests = { status: "RUNNING", reason: "待执行" }; },
  p => { p.summary.pendingBrowserTest = true; },
  p => { p.summary.overallStatus = "RUNNING"; },
  p => { p.summary.unitStatus = "RUNNING"; },
  p => { p.summary.browserStatus = "RUNNING"; },
  p => { p.status = "RUNNING"; }
]) test("最新 RUNNING 拒绝转换：" + mutate.toString(), () => {
  const old = fixture(), latest = fixture(); latest.buildNo++; mutate(latest);
  assert.throws(() => convert([latest, old]), /RUNNING/); notGreen(render([latest, old]));
});
for (const status of ["FAIL", "UNVERIFIED", "TIMEOUT"]) test("转换保留终态 " + status, () => notGreen(render([convertedPayload([fixture(status)])])));
test("转换按最新 buildNo 选失败轮，legacy 可派生编号且保持缺字段", () => {
  const old = fixture(), latest = fixture("FAIL"); latest.buildNo++; assert.equal(convertedPayload([latest, old]).unitTests.status, "FAIL");
  delete old.unitTests; delete old.buildNo;
  for (const k of ["overallStatus", "unitStatus", "browserStatus"]) delete old.summary[k];
  const p = convertedPayload([old]); assert(!Object.hasOwn(p, "unitTests")); green(render([p]));
  assert.throws(() => convert([latest, latest]), /重复/);
  assert.throws(() => convert([{ build: "missing_number" }]), /非法/);
});
test("发布内联与 HTML 渲染双层转义：命令、run_id、失败用例、首要错误", () => {
  const p = fixture("FAIL"), dangerous = '</script><img src=x onerror="alert(1)"> &  ';
  Object.assign(p.unitTests, { failed_cases: [dangerous], primary_error: dangerous });
  Object.assign(p.unitTests.runs[0], { run_id: dangerous, command: ["python3", dangerous], failed_cases: [dangerous], primary_error: dangerous });
  const source = convert([p]); assert(!source.includes("</script>")); assert(!source.includes(" ") && !source.includes(" "));
  const payload = convertedPayload([p]); assert.equal(payload.unitTests.primary_error, dangerous);
  const r = render([payload]); notGreen(r); assert(!r.html.includes("<img"));
  assert(r.html.includes("&lt;/script&gt;&lt;img") && r.html.includes("&amp;"));
});
console.log(passed + " passed, 0 failed");
