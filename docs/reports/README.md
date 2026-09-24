# docs/reports/ — 版本报告目录

> **隔离级别**：版本级（`docs/reports/{version}/`）。每个版本目录汇集**两大报告族**：① AI 全自动开发/测试报告（命令自动生成）；② 走查/交付报告（Reviewer Agent / `/sprint-close` 生成，分个人级/团队级）。

## 每个版本的目录结构

```
docs/reports/{version}/
├── AI执行报告/                          # 命令自动（/sprint-autopilot）：执行结果 + 执行计划合并拍平、共享 data/
│   ├── index.html                      # 执行结果 SPA 主入口（综合首页 + 各 build 子页）
│   ├── plan.html                       # 执行计划页（结果页链接跳转打开本 build 计划）
│   ├── assets/                         # app.js(结果) + plan.js(计划) + style.css 暗/亮双主题（零 CDN）
│   └── data/{version}_build{N}.js      # 每 build 一份数据，index/plan 共用（Phase 3.1.5 写计划态 → 3.4 finalize 结果态）
├── AI测试报告/                         # 命令自动：多 build 离线静态 SPA（/sprint-aiauto-test）
│   ├── index.html
│   ├── assets/                          # 内联样式 + 手写 SVG 图表（零 CDN）
│   ├── data/{version}_build{N}.js       # 每 build 一份测试数据
│   └── screenshots/{build}/            # 该 build 用例截图，扁平存放 {TC-ID}-{step}.png
│                                        # ⛔ 不建 {role} 子层（会让 SPA 相对路径取图失败）
├── AI数据清理/                         # 命令自动：每 build 一份数据清理文档（仅 autopilot 驱动测试才产）
│   └── {version}_build{N}_数据清理.md   # 测试环境 + 要清理的库 + 清理 SQL（测试后询问是否执行、无人值守只生成不删）
├── 版本测试报告/                       # 命令自动：发布时单文件（/version）
│   └── {version}-测试报告.html
├── review-{user}.md                     # 人工：个人级代码走查报告（Reviewer Agent / sprint-close）
└── delivery-report.md                   # 人工：团队级版本交付报告（sprint-close / 版本交付）
```

> 📌 各报告子目录的骨架与说明见 `{{AIDP_HOME}}/templates/reports/`（`AI执行报告/` `AI测试报告/` `版本测试报告/`），由命令首次产出报告时从模板拷贝；`AI数据清理/` 由 `/sprint-aiauto-test` 在 autopilot 驱动的测试后按 build 生成时才创建。

## 报告族 ①：AI 全自动开发/测试报告（命令自动生成）

| 报告 | 位置 | 生成者 | 时机 |
|------|------|-------|------|
| AI 执行报告（执行结果 + 执行计划，离线 HTML，合并拍平）| `AI执行报告/index.html`（结果，主入口）+ `AI执行报告/plan.html`（计划）+ `AI执行报告/data/{version}_build{N}.js` | `/sprint-autopilot` | Phase 3.1.5 写计划态数据 → Phase 3.4 finalize 结果态 |
| AI 测试报告（多 build 离线 SPA）| `AI测试报告/index.html` | `/sprint-aiauto-test` | 每轮测试收敛后 |
| AI 数据清理（每 build 一份，Markdown）| `AI数据清理/{version}_build{N}_数据清理.md` | `/sprint-aiauto-test`（**仅 autopilot 驱动才产**）| 测试后 best-effort 生成；询问是否执行清理、无人值守只生成不删 |
| 版本测试报告（单文件对外交付）| `版本测试报告/{version}-测试报告.html` | `/version` | 正式发布时取 build 号最大的一轮（最终验收态）|

- **build 号**：`{version}_build{N}`（N 从 1001 自增，`/sprint-autopilot` Phase 3.1.5 铸造、3.4 finalize，不打 git 分支/tag）。
- **模板 / 数据契约 / 离线铁律以 [`{{AIDP_HOME}}/templates/reports/`](../../{{AIDP_HOME}}/templates/reports/README.md) 为权威**（含各级 README + `index.html`/`assets`/`data` 骨架）。

## 报告族 ②：走查 / 交付报告（人工生成）

| 类型 | 命名 | 生成者 |
|------|------|-------|
| 个人级代码走查 | `review-{user}.md` | Reviewer Agent / `/sprint-close` |
| 团队级版本交付 | `delivery-report.md` | 项目负责人 / `/sprint-close` |

文件头部元信息标注责任人，避免多人并写冲突。

## 相关文档

- 报告模板库：[`../../{{AIDP_HOME}}/templates/reports/README.md`](../../{{AIDP_HOME}}/templates/reports/README.md)
- 相关命令：`/sprint-autopilot`、`/sprint-aiauto-test`、`/version`、`/sprint-close`
- 目录约定：[`../init/06_版本与用户目录约定.md`](../init/06_版本与用户目录约定.md) §2.2.2「reports 文件命名约定」
- Reviewer 职责：[`../init/04_agents详细规范.md`](../init/04_agents详细规范.md)
