# AI执行报告

> 一个 build 的 **AI 执行报告** = **执行结果**（`index.html`，主入口）+ **执行计划**（`plan.html`），二者**合并为同一套离线页面**、同目录、共享 `data/` 数据与 `assets/style.css` 样式。由 `/sprint-autopilot` 自动生成。

## 目录结构（已拍平，不再分 执行计划/ + 执行结果/ 两层）

```
AI执行报告/
├── README.md
├── index.html                     ← 执行结果 SPA 主入口（综合首页 + 各 build 子页）
├── plan.html                      ← 执行计划页（结果页各 build 详情头部「→ 查看本 build 执行计划」链接跳转打开）
├── assets/
│   ├── style.css                  （暗/亮双主题，结果页 + 计划页共用；零 CDN）
│   ├── app.js                     （执行结果渲染逻辑）
│   └── plan.js                    （执行计划渲染逻辑：工作流 stepper + 计划甘特 + 步骤依赖 + 功能点比对）
└── data/{version}_build{N}.js     ← 每 build 一份数据，index.html 与 plan.html 共用（window.__AIRUNS__.push）
```

> 📌 **为何合并 + 拍平**：执行计划与执行结果是**同一个 build 的一体两面**（计划=开发前的步骤/依赖/功能点清单，结果=开发后的完成情况），共用同一份 `data/{build}.js`。拆成两层子目录、两套形态（md + HTML）会让数据双写、目录越积越乱；合并为「以结果页为主入口 + 计划页链接跳转」后，一份数据驱动两个视图，结构与同级 `AI测试报告/` 一致。
> 📌 模板目录里的数据是带 `示例_` 前缀的样例（`data/示例_build1001.js`）；运行时 `/sprint-autopilot` 按 build 写 `data/{version}_build{N}.js`，并在 `index.html` 与 `plan.html` 的「数据注入区」各追加一行 `<script src="data/...">`（务必在 `app.js` / `plan.js` 之前）。

## 两个视图（同源数据驱动）

| 视图 | 文件 | 内容 | 数据来源 |
|------|------|------|---------|
| **执行结果**（主入口）| `index.html` + `assets/app.js` | 综合首页（各 build 完成率趋势 + build 列表）+ 各 build 子页：执行概览(cockpit) / 需求功能清单 / 测试详情 / 步骤执行 / 缺陷清单 / 风险与建议 / 异常处置 / 剩余待办 / 运行元信息 | `data/{build}.js` 的 `overview/steps(actualStatus)/features/testSummary/defects/risks/...` |
| **执行计划**（链接打开）| `plan.html` + `assets/plan.js` | 按 build:Build 元信息 + **执行工作流 stepper**（sprint-autopilot 全任务顺序 + 依赖）+ **计划时间线甘特**（手写内联 SVG）+ **步骤依赖表** + **需求功能点比对清单**（逐条对照 `01_研发需求.md`）| 同一份 `data/{build}.js` 的 `steps(plannedStatus/type)/features/planSource/...` |

> 计划侧读 `step.plannedStatus`（计划态）+ 类型估算耗时画甘特；结果侧读 `step.actualStatus`（实际态）。同一份 `steps`/`features` 驱动两个视图，**无数据双写**。

> 📌 **承接 Sprint 验收结论（AIDP 不再单独出 `验收报告.md`）**：每 Sprint 的**功能验收结果**（✅ 通过 / ⚠️ 部分通过 / ❌ 移入下期）由本报告「**需求功能清单**」段（`features[].status`）承载；**Sprint 回顾 / 经验教训 / 遗留事项**由「**风险与建议**」段承载；缺陷统计由「**缺陷清单**」段承载。手动分步流（无 autopilot、不产本报告）下，验收结论落 `progress.md` + Sprint 归档（见 `/sprint-close` Step 2）。

## 怎么读

- 双击 `index.html`（离线 `file://` 可开）→ 综合首页看各 build 完成率趋势 → 点 build 行或切「执行详情」tab 看单 build 详情。
- 单 build 详情页头部「**→ 查看本 build 执行计划**」链接 → 打开 `plan.html#/build/{build}`，看本次 build 的工作流 / 甘特 / 步骤依赖 / 功能点比对；计划页顶部「**← 返回执行结果**」回到结果页对应子页。
- **URL 直达指定 build**：结果 `index.html#/build/{version}_build{N}`；计划 `plan.html#/build/{version}_build{N}`（均兼容 `?build=...`）。
- 测试用例 / 截图详情见同级 AI测试报告（`../AI测试报告/`）的 `index.html` 对应 build 子页——页面内「测试详情」跳转链接已按当前页所在目录【运行时推导】，本地 file:// 与服务器两端都能打开，无需手填。

## 数据契约

`data/{build}.js` 字段 schema 见 `data/示例_build1001.js`（完整字段注释）。要点:
- 计划侧用到的字段:`steps[].plannedStatus / type / name / output`、`features[].reqId / reqSource / sprint / status`、`planSource`、`trigger / branch / deployMode / startedAt`。
- 结果侧用到的字段:`overview`、`steps[].actualStatus`、`testSummary`、`defects`、`risks`、`incidents`、`todos`、`links`。
- **离线铁律**:零 CDN / 零 fetch,数据用 `<script src>` 注入 `window.__AIRUNS__`,图表手写内联 SVG,`file://` 双击即开。**计划不产出独立 md**——内容在 `plan.html`,由 `data/{build}.js` 数据驱动。

## 交付信息（autopilot 自动维护）

> 报告只落仓库本地，由 `emit-report.py` 交付后回写 baseline `report_deliveries`。

- **本地目录**：docs/reports/{version}/AI执行报告/
- **访问方式**：仓库内相对路径 `docs/reports/{version}/AI执行报告/index.html`（本 build 结果页加 `#/build/{version}_build{N}`）
- **最后同步**：{ts}

> 里程碑通知 #3 中的报告链接给仓库内相对路径（或代码托管平台上的文件链接）。
