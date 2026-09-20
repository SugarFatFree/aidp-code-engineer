# AI测试报告（离线静态 SPA）

> 多个 build 共享的离线静态测试报告项目。`/sprint-aiauto-test` 每轮测试收敛后把该 build 的结果写进 `data/{version}_build{N}.js` 并刷新本项目。**双击 `index.html` 即可打开**，无需起服务器、无需联网。

## 结构

| 文件/目录 | 作用 |
|----------|------|
| `index.html` | 入口 SPA：综合首页（全部 build 趋势 + KPI + 图表）+ 切换到每个 build 子页 |
| `assets/app.js` | 渲染逻辑 + 手写 SVG 图表（环形/趋势/堆叠柱）+ hash 路由视图切换 |
| `assets/style.css` | 样式（状态色：通过绿 / 失败红 / 阻塞橙 / 忽略灰）|
| `data/{version}_build{N}.js` | 每 build 一份测试数据（`window.__BUILDS__.push({...})`）|
| `data/示例_build*.js` | 示例数据（下游可删；演示数据契约 + 趋势/切换效果）|
| `screenshots/{build}/` | 该 build 的用例截图，扁平存放 `{TC-ID}-{step}.png`（⛔ 不建 `{role}` 子层，会让 SPA 相对路径取图失败）|

## 离线铁律

- **零 CDN / 零网络**：图表全部手写内联 SVG，不引第三方库。
- **数据用 `<script src="data/xxx.js">` 注入**（不用 `fetch`，`file://` 下 fetch 被 CORS 挡）。
- 新增 build：`/sprint-aiauto-test` 写 `data/{build}.js` + 在 `index.html` 数据注入区追加一行 `<script src="data/{build}.js"></script>`（在 `assets/app.js` 之前）。

## 数据契约

见 `../README.md`（reports 模板库总说明）的 schema。`data/示例_build1001.js` 是可直接复制的范例。

## 交付信息（autopilot 自动维护）

> 报告只落仓库本地，由 `emit-report.py` 交付后回写 baseline `report_deliveries`。

- **本地目录**：docs/reports/{version}/AI测试报告/
- **访问方式**：仓库内相对路径 `docs/reports/{version}/AI测试报告/index.html`（本 build 结果页加 `#/build/{version}_build{N}`）
- **最后同步**：{ts}

> 里程碑通知 #F 中的报告链接给仓库内相对路径（或代码托管平台上的文件链接）。
