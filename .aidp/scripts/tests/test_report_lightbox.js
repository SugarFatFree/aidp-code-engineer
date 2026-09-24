#!/usr/bin/env node
/* 截图灯箱交互单测：点开大图后**鼠标滚轮必须能放大缩小**（实测发现的缺陷：只能看、不能缩放）。
 * ⛔ 不用「源码里有没有 wheel 字样」当判据——那是字符串匹配、改坏了照样绿。
 * 这里给一套**会记录并回放事件**的 DOM stub，真正触发 wheel/mousedown 再断言 transform 变化。
 * 直接 `node .aidp/scripts/tests/test_report_lightbox.js` 运行；exit 0=全绿。 */
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = path.resolve(__dirname, "..", "..", "..");
const APP = ".aidp/templates/reports/AI测试报告/assets/app.js";

let passed = 0, failed = 0;
function check(name, cond) {
  if (cond) passed++;
  else { failed++; console.log("  ❌ FAIL: " + name); }
}

function makeEl(tag) {
  const el = {
    tagName: tag || "div", _html: "", value: "", hidden: false, style: {}, _attrs: {}, _handlers: {},
    classList: {
      _set: new Set(),
      add(c) { this._set.add(c); }, remove(c) { this._set.delete(c); },
      toggle(c) { this._set.has(c) ? this._set.delete(c) : this._set.add(c); },
      contains(c) { return this._set.has(c); },
    },
    addEventListener(t, fn) { (el._handlers[t] = el._handlers[t] || []).push(fn); },
    removeEventListener() {},
    setAttribute(k, v) { el._attrs[k] = String(v); },
    removeAttribute(k) { delete el._attrs[k]; },
    getAttribute(k) { return Object.prototype.hasOwnProperty.call(el._attrs, k) ? el._attrs[k] : null; },
    appendChild() {}, removeChild() {}, replaceChild() {}, focus() {}, click() {},
    getBoundingClientRect() { return { left: 0, top: 0, width: 400, height: 300 }; },
    querySelector(s) { return el._children[s] || (el._children[s] = makeEl()); },
    querySelectorAll() { return []; },
    fire(t, ev) { (el._handlers[t] || []).forEach((fn) => fn(Object.assign({ preventDefault() {}, stopPropagation() {} }, ev))); },
    _children: {},
  };
  Object.defineProperty(el, "innerHTML", { get() { return el._html; }, set(v) { el._html = String(v); } });
  return el;
}

function boot() {
  const cache = {};
  const q = (s) => cache[s] || (cache[s] = makeEl());
  const docHandlers = {};
  const doc = {
    readyState: "complete", documentElement: makeEl(), body: makeEl(),
    querySelector: q, querySelectorAll: () => [], getElementById: (id) => q("#" + id),
    createElement: (t) => makeEl(t),
    addEventListener(t, fn) { (docHandlers[t] = docHandlers[t] || []).push(fn); },
    fire(t, ev) { (docHandlers[t] || []).forEach((fn) => fn(Object.assign({ preventDefault() {}, stopPropagation() {} }, ev))); },
  };
  const win = {
    document: doc, location: { hash: "#/overview", search: "" }, addEventListener() {},
    matchMedia: () => ({ matches: false, addEventListener() {} }),
    localStorage: { getItem: () => null, setItem() {} }, print() {}, scrollTo() {},
  };
  win.__BUILDS__ = [];
  const warns = [];
  const c = { warn: (...a) => warns.push(a.join(" ")), error: (...a) => warns.push("ERR:" + a.join(" ")), log() {} };
  let threw = null;
  try {
    new Function("window", "document", "location", "console", "localStorage",
      fs.readFileSync(path.join(ROOT, APP), "utf8"))(win, doc, win.location, c, win.localStorage);
  } catch (e) { threw = String((e && e.stack) || e); }
  return { doc, win, modal: q("#shot-modal"), threw };
}

/** 点开一张大图，返回 {modal, img, doc} */
function openShot() {
  const env = boot();
  if (env.threw) throw new Error("app.js 执行抛错：" + env.threw);
  const thumb = makeEl("img");
  thumb.classList.add("shot-thumb");
  thumb.setAttribute("data-full", "screenshots/b/TC-1-1.webp");
  thumb.setAttribute("data-cap", "用例 TC-1 第 1 步");
  env.doc.fire("click", { target: thumb });
  return { modal: env.modal, img: env.modal.querySelector(".shot-modal-img"), doc: env.doc, env };
}

/** 从 transform 串里取 scale 数值；取不到返回 null（⛔ 不默认 1，否则没实现也"通过"） */
function scaleOf(el) {
  const m = /scale\(([\d.]+)\)/.exec(String((el.style && el.style.transform) || ""));
  return m ? parseFloat(m[1]) : null;
}

console.log("① 打开大图 → 初始可缩放状态");
const o = openShot();
check("点缩略图后灯箱打开（hidden=false）", o.modal.hidden === false);
check("大图 src 已设置", o.img.getAttribute("src") === "screenshots/b/TC-1-1.webp");
check("★ 初始 scale 可读且为 1（缩放状态已初始化）", scaleOf(o.img) === 1);

console.log("② 滚轮向上 → 放大；向下 → 缩小");
const a = openShot();
a.modal.fire("wheel", { deltaY: -120, clientX: 200, clientY: 150 });
const zoomedIn = scaleOf(a.img);
check("★ 滚轮上滚后 scale > 1（放大生效）", zoomedIn !== null && zoomedIn > 1);
a.modal.fire("wheel", { deltaY: 120, clientX: 200, clientY: 150 });
const backOut = scaleOf(a.img);
check("★ 滚轮下滚后 scale 变小（缩小生效）", backOut !== null && backOut < zoomedIn);

console.log("③ 缩放有上下限，不会缩没或撑爆");
const b = openShot();
for (let i = 0; i < 60; i++) b.modal.fire("wheel", { deltaY: -120, clientX: 200, clientY: 150 });
const maxScale = scaleOf(b.img);
check("★ 连续放大后有上限（≤10）", maxScale !== null && maxScale <= 10);
for (let i = 0; i < 120; i++) b.modal.fire("wheel", { deltaY: 120, clientX: 200, clientY: 150 });
const minScale = scaleOf(b.img);
check("★ 连续缩小后有下限（>0.1，不会缩没）", minScale !== null && minScale > 0.1);

console.log("④ 滚轮缩放时阻止页面滚动（默认行为必须被拦）");
const d = openShot();
let prevented = false;
d.modal.fire("wheel", { deltaY: -120, clientX: 200, clientY: 150, preventDefault() { prevented = true; } });
check("★ wheel 调用了 preventDefault（不连带滚底层页面）", prevented);

console.log("⑤ 放大后可拖拽平移（否则放大了看不到边缘）");
const e = openShot();
e.modal.fire("wheel", { deltaY: -120, clientX: 200, clientY: 150 });
const beforeDrag = String(e.img.style.transform || "");
e.img.fire("mousedown", { clientX: 200, clientY: 150, button: 0 });
e.doc.fire("mousemove", { clientX: 260, clientY: 190 });
const afterDrag = String(e.img.style.transform || "");
e.doc.fire("mouseup", {});
check("★ 拖拽后 transform 变化（平移生效）", afterDrag !== beforeDrag && /translate/.test(afterDrag));

console.log("⑥ 重新打开另一张图 → 缩放状态重置，不残留上一张的倍数");
const f = openShot();
f.modal.fire("wheel", { deltaY: -120, clientX: 200, clientY: 150 });
check("先放大成功", scaleOf(f.img) > 1);
const thumb2 = makeEl("img");
thumb2.classList.add("shot-thumb");
thumb2.setAttribute("data-full", "screenshots/b/TC-2-1.webp");
thumb2.setAttribute("data-cap", "另一张");
f.doc.fire("click", { target: thumb2 });
check("★ 再次打开后 scale 重置为 1", scaleOf(f.img) === 1);
check("★ 再次打开后 src 换成新图", f.img.getAttribute("src") === "screenshots/b/TC-2-1.webp");

console.log("");
console.log(failed === 0 ? "✅ 全部通过（" + passed + " 项）" : "❌ " + failed + " 项失败（通过 " + passed + "）");
process.exit(failed === 0 ? 0 : 1);
