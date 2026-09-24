# docs/ — 项目文档体系

> 本目录按 AIDP 范式组织，分为三层隔离级别：**项目级 / 版本级 / 版本+用户级**。
> 完整规则见 [`init/06_版本与用户目录约定.md`](init/06_版本与用户目录约定.md)。

## 目录结构

```
docs/
│── ★ 项目级（单一真源，不隔离） ─────────────────
├── init/                         AIDP 范式文档本体
├── references/                   第三方接口资料（根 = 跨版本通用区；★ 另有 {version}/ 各版本区，见下）
├── architecture/                 架构约束 / 技术选型 / UI 规范
│
│── ★ 版本级（按版本隔离，团队共享）───────────────
├── references/{version}/         ★ 版本级：本版「提给第三方的需求」+ 本版对方资料（/sprint-design 落盘；引用链强制）
├── prototype/{version}/          原型资源 code + mockup
├── deployment/
│   ├── {version}/                部署产物（版本级）：00_索引.md + sql/{增量,全量}/ + 部署流程/ + 配置文件/{增量,全量}/
│   └── tools/                    ★ 非版本隔离：跨版本运维 / 一次性工具归档（项目级特例）
├── requirements/
│   └── {version}/研发需求/00_索引.md + 01_研发需求.md  AIDP 版本需求基线（由 /version 生成）
├── design/detail/{version}/      版本详细设计（00_索引.md + 01_详细设计.md / 02_数据库设计.md / 03_接口设计.md …）
├── design/detail/全量/           ★ 跨版本全量详细设计（非版本目录，/version Step 3.3.11 正式发布时生成）
├── testing/{version}/            测试文档（3 子目录：研发自测/ 正式用例/ sprint-NNN/；AI 测试报告落 docs/reports/{version}/AI测试报告/）
├── plans/{version}/              研发执行计划（00_索引.md + 01_研发执行计划.md）
├── reports/{version}/            走查/交付 + AI报告（AI执行/AI测试/AI数据清理/版本测试）
├── audit/合规检查-{YYYYMMDD}.md  范式合规检查报告（★ 根级，与 {version}/ 并列）
├── audit/{version}/              版本规划产物审计报告
├── prompts/{version}/            大型 Prompt 存档
│
│── ★ 版本+用户级（双层隔离）────────────────────
├── bugfix/{version}/             Bug 记录（文件命名带 user）
└── implementation/{version}/{user}/ 个人实施过程记录
```

## 各子目录职责

| 子目录 | 内容 | 写入者 |
|--------|------|--------|
| `init/` | AIDP 范式文档（00-06） | 仅 AIDP 升级时修改 |
| `references/`（根）| **通用区**：第三方跨版本通用接口文档 / 能力清单（OCR / TTS 等） | 全栈按需 |
| `references/{version}/` | **各版本区**（版本级隔离）：本版「提给第三方的需求」+ 本版对方资料；★ 必须被 `01_研发需求.md` + `01_详细设计.md` 引用（`version-auditor` E 审计） | `/sprint-design` 落盘 + `/version` 发布期复核 |
| `architecture/` | 架构约束、技术选型、UI 规范 | `/sprint-design` 动态填充 + 人工补充 |
| `prototype/{version}/code/` | 原型代码（vibe coding 产物） | 产品/设计前期提供 |
| `prototype/{version}/mockup/` | 高保真原型（视觉最高优先级） | 人工提供 或 UI Agent 自动生成 |
| `requirements/{version}/` | AIDP 版本需求基线 | `/sprint-requirements` |
| `design/detail/{version}/` | 详细设计、API、数据库 | `/sprint-design` |
| `deployment/{version}/` | 部署产物双轨（约定 37）：`sql/增量/` + `sql/全量/`、`配置文件/增量/配置项清单.md` + `配置文件/全量/`（nginx / compose / k8s / 配置中心），另有 `00_索引.md` + `部署流程/` | `/sprint-design`（增量 SQL）+ `/sprint-dev` Step X.7/X.8（增量配置 + 部署流程）+ `/version` Step 3.3.7.9（全量两轨） |
| `deployment/tools/` | ★ **非版本隔离**（项目级特例）：跨版本运维脚本 / 一次性迁移工具归档 | 各角色按需（详见 [`init/06_版本与用户目录约定.md`](init/06_版本与用户目录约定.md) §2.5.4.1）|
| `testing/{version}/` | 测试文档（研发自测/ 正式用例/ sprint-NNN/） | `/sprint-selftest`+`/sprint-test`+`/sprint-aiauto-test` |
| `plans/{version}/` | 研发执行计划 | `/sprint-plan` |
| `reports/{version}/` | 走查/交付报告 + AI报告（AI执行/AI测试/AI数据清理/版本测试） | Reviewer / 命令自动 |
| `audit/合规检查-{YYYYMMDD}.md` | 范式合规检查报告（**根级、与 `{version}/` 并列**）| aidp-compliance |
| `audit/{version}/` | 版本规划产物审计报告 | version-auditor / aidp-compliance |
| `prompts/{version}/` | 大型 Prompt 存档 | 各角色按需 |
| `bugfix/{version}/` | Bug 记录（一人一天一份汇总） | 发现者 + 修复者 |
| `implementation/{version}/{user}/` | 个人踩坑笔记 | 各开发者 |

> `superpowers/`（plans / specs）是**模板仓库自身维护期**的规格与计划留档，**不属于下游文档体系**，
> 故不在上表内，也不进文档导航（`verify.py::NAV_SCAN_EXCLUDED` 已登记）。

## 文件命名规范

详见各子目录的 `README.md`，或 [`init/06_版本与用户目录约定.md`](init/06_版本与用户目录约定.md)。

| 路径 | 文件命名 |
|------|---------|
| `bugfix/{version}/` | `bugfix-{YYYYMMDD}-{user}.md`（一天一人一份汇总） |
| `plans/{version}/` | `01_研发执行计划.md`（必需） + `plan-{user}.md`（可选） |
| `reports/{version}/` | 团队级用类型名（`delivery-report.md`），个人级带 user（`review-{user}.md`） |
| `docs/deployment/{version}/sql/增量/` | `{NN}_<中文名>.sql`（中文命名+两位序号前缀，如 `01_用户表DDL.sql`，`99_回滚脚本.sql` 序号保留；⛔ `sql/` 根下不得直放 `.sql`；详见 [`init/06_版本与用户目录约定.md`](init/06_版本与用户目录约定.md) §2.5.4） |
| `docs/deployment/{version}/sql/全量/` | `00_索引.md` + `{NN}_建表-<业务域>.sql` + `{NN}_初始化数据.sql`（全新部署基线，发布期产出，不含 ALTER；约定 37） |
| `docs/deployment/{version}/配置文件/` | `增量/配置项清单.md`（固定名，本版变更）+ `全量/`（`00_索引.md` + 引导层环境文件 + nginx/compose/k8s 完整份 + `<配置中心>/*.yml`）；⛔ 根下不得直放配置产物 |
