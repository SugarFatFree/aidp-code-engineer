# sprint-dev · Phase 1 开发执行详情（分片 2/2 · Phase 1.3–1.4）

> **【分片 2/2 · phase-1-dev 二次切分】** 本片是 `/sprint-dev` 命令 **Phase 1 开发执行**段的后半，覆盖 **Phase 1.3（前端开发，视觉/内容/操作逻辑三层对齐，约定 4）/ Phase 1.4（并行开发，全栈场景推荐）**。前片 `phase-1-dev-1.md` 覆盖 Phase 1.0pre / 1.1 / 1.1.5 / 1.2（后端开发）。以本文件为准逐项执行、不得略过任一子步骤。

---

### Phase 1.3：前端开发（如在范围内）

读取 `{{AIDP_HOME}}/agents/frontend.md` 获取角色定义。

#### 输入文件

项目级：
1. `memory/techContext.md`
2. `memory/systemPatterns.md`
3. `docs/prototype/{version}/code/` — UI 原型代码
4. `code/` — 已有脚手架

版本级 / 迭代级：
5. `docs/design/detail/{version}/*.md` — **全目录 glob 读取**（模块结构 / 公共组件清单 / 内部 API 接口定义等全部专题主文档；★ 兼容约定 14 三态命名，不硬编码裸名 `详细设计.md`/`数据库设计.md`/`接口设计.md`——拆分态是 `01_详细设计.md`/`02_数据库设计.md`/`03_接口设计.md`…；先读 `00_索引.md`（如有））
6. 其中 **对外开放接口**（专题主文档，★ 如存在 — 前端调用对外接口时必须按文档声明的鉴权方式拼装请求头 / 处理限流 429 / 实现幂等键，**不要复用内部接口的 axios baseURL**，单独配一个对外接口的 base 前缀实例；本地 MD 为权威，同目录 `openapi.yaml`（如存在）是派生的机读副本，正文仍是接口定义来源）
7. `docs/prototype/{version}/mockup/` — ★ 高保真原型（视觉最高优先级）

#### 开发步骤

```
Step 0: ★ UI 视觉来源判定 + L1/L2 二层分级
  - 检查 `docs/prototype/{version}/mockup/{module}/` → 有高保真 = 情形 A
  - 否则检查 `docs/architecture/UI规范约束.md`：
      • 无效/空模板 → 情形 B（**不询问**，视觉沿用 `code/`）
      • 有效 →
          - **交互式（默认，用户在场）**：用 `AskUserQuestion` 询问用户："直接对齐原型(C) / 参考原型 + UI 规范优化(D)"二选一，**禁止 Agent 自行决策**
          - **★ `--unattended`（autopilot `/loop` 无人值守；GAP 兜底）**：**绝不弹窗**——读 PRD `autopilot_decisions.visual_baseline` **预声明消费**（`prototype-only`→C、`optimize-with-uispec`→D、`mockup-strict`→按情形 A）。这是**用户在 PRD 里预先显式选定**（非 Agent 自行决策，仍满足约定 4「C/D 用户显式选」），结果记入 Sprint UI 基线；PRD 未声明该字段 → 保守默认 C（直接对齐原型、不做 UI 规范再创作）+ 终端 WARN 提示补声明
  - 判定结果写入当前 Sprint UI 规范作为基线
  - ★ **视觉对齐 L1/L2 二层分级（详见 CLAUDE.md 约定 4）**：
      • **L1 大体页面样式（必须严格对齐 — 偏差 Critical）**：容器/版心、颜色 token（主色/品牌色/文字色/警告/成功/危险）、字号 h1~caption 体系、间距体系、圆角等级、阴影等级、字体、必须出现的元素 — 误差 ≤ 2px / 一阶色阶
      • **L2 组件内部细节（项目组件默认 — 偏差 Important 不阻塞验收，仅 L1 偏差 Critical 强阻塞）**：表单类（el-input/select/checkbox/radio/date-picker/cascader/...）/ 反馈类（el-message/notification/dialog/drawer/popover/tooltip）/ 展示类（el-tag/badge/progress/card/skeleton/alert）/ 导航类（el-pagination/tabs/breadcrumb/steps/menu）的下拉箭头/日历视觉/弹窗动画/Tag 圆角/Progress 样式 — 项目组件默认实现，不强行覆写
      • **L2 主题 token 仍受 L1 约束**：`<el-tag type="success">` 的绿色 从 L1 体系取项目品牌绿，不用 Element Plus 默认浅绿；通过 `theme/variables.scss` / `--el-color-*` 统一覆写
      • **图标缺失**：原型用了项目图标库没有的图标款 → 拉 SVG 入 `src/assets/icons/`（详见 frontend.md 核心原则 10 配套流程），禁止为单图标引入完整图标库
      • **不确定时默认归 L1**（保守，避免视觉漂移）
      • `/sprint-test` `code-verification-loop`「代码质量」维度子项「视觉还原」按 L1/L2 分级回检：L1 偏差 Critical 强阻塞回 `/sprint-bugfix`；L2 偏差 Important 不阻塞验收
  - ★ **字段/列裁剪三件套（详见 CLAUDE.md 约定 4）**：原型可见的列表列/表单字段，若因接口不支持需裁剪/改名/被接口字段覆盖 → 禁止静默删除，必须 ① 在研发需求登记「原型字段→处置」对照表 ② 经产品确认（C/D 决策门）③ 触发约定 22 级联（统一走末段 Step X.0.0）。本 Step 仅做事前门提示，规则单一信源在约定 4，不复述
Step 0.3: ★ 设计令牌落地门（情形 B/C 必过 — 约定 4「情形 B/C 设计令牌提取铁律」；先令牌、后写页面）
  - **仅情形 B/C 触发**（无高保真、对齐原型）；情形 A/D 走高保真、本门退化为"从高保真核对 token"。
  - **① 取设计令牌**：读 `docs/design/detail/{version}/NN_设计令牌.md`（UI Agent 流程 A Step 4 已产出；`NN` 实际续编序号、见详细设计 `00_索引.md`，兼容历史裸名 `设计令牌.md`）→ **缺失则由 Frontend Agent 现场从原型 `code/` 提取补出**（主色/辅助色/文字色/背景色 + 字号阶梯/行高 + 间距刻度/圆角/阴影 + 字体，逐项标原型来源）。
  - **② 落全局主题**：据令牌建/更新 `code/frontend/{子项目}/src/theme/variables.scss`（或 `src/styles/tokens.css` / 组件库 theme 覆写）——**所有页面样式引用主题变量**。
  - **③ 铁律**：**禁止**跳过本门直接用组件库默认主题充数、**禁止**散落硬编码色值/尺寸。这是"用项目组件（约定 28 实现选型层）≠ 用组件库默认观感（约定 4 视觉层）"的落地保障——用 Element Plus 不豁免主色/字号/间距/圆角取自原型体系。
  - **验收**：`设计令牌.md` + 主题文件是前端验收基线，`code-verification-loop` 维度 4 情形 B/C 也据此强校验 L1（单一信源见约定 4，不复述）。
Step 0.4: ★ 原型内容 + 操作逻辑 逐页对照门（约定 4「对齐原型 = 视觉 + 内容 + 操作逻辑 三层」；防原型元素/行为被静默漏做或简化）
  - **有原型 code/ 时必过**（尤其情形 B/C）：开发某页**前**，对照 `docs/design/detail/{version}/NN_原型内容基线.md`（UI Agent 流程 A Step 1.5 产出；`NN` 实际续编序号、见详细设计 `00_索引.md`，兼容历史裸名 `原型内容基线.md`）**逐项确认**——**① 内容元素**（区块/卡片、表格列、表单字段、筛选/排序/分页、按钮与次级操作、空态/加载/错误/成功交互态、跳转/弹窗）**② 操作逻辑/交互流**（点击→反馈/跳转、校验规则与时机、字段联动、条件显隐/禁用、筛选排序分页行为、增删改-保存-取消/批量流、二次确认、默认值、多步步序、错误处理）**均须与原型一致**。
  - **基线缺失**（未跑 UI Agent / 直接累进）→ Frontend Agent **先从原型 code/ 现场盘点本页元素 + 操作逻辑补出基线条目，再开发**（消费 `DESIGN-MANIFEST.json`/`DESIGN-HANDOFF.md` 若存在）。
  - **凡"原型有、本次不实现或要改行为"的元素/逻辑**：**严禁静默省略或擅自简化/改流程**——必须走约定 4「字段/列裁剪三件套」：① 研发需求登记「原型元素/逻辑→处置」留痕 ② `AskUserQuestion` 产品确认门（`--unattended` 消费 PRD `autopilot_decisions` 预声明、缺则保守默认"照原型实现"、不静默砍/不静默改）③ 触发约定 22 级联（统一走末段 Step X.0.0）。未标处置的元素与操作逻辑**默认必须照原型实现**。
  - **验收**：`原型内容基线.md` 是内容 + 操作逻辑完整性验收基线，`code-verification-loop` 维度 4「内容 + 操作逻辑完整性」子行（情形 B/C）逐页核对原型有/实现无或行为不符/未标处置 → Critical；`dev-manual-testcase` 据基线每元素/状态/操作流一用例。单一信源见约定 4，不复述。
Step 0.5: ★ 公共组件检查与实现（先实现/复用公共组件）
Step 1: API 调用层
  - 仅真实 HTTP 请求；失败 / 超时 / 空响应 → 空状态 / 错误提示 / 重试，禁止 Mock 兜底
  - 唯一例外：后端尚未启动开发的接口可临时 Mock，经**拦截器 / MSW + 构建期守卫**（`if (import.meta.env.DEV)` 等）提供并带 `// DEV_MOCK since= owner= REMOVE_WHEN=` 标注块（⛔ 无字段的裸标记没有任何机器门认得），后端启动后当轮清除。⛔ **别给 `DEV_MOCK` 套运行时开关**——那是 `THIRD_PARTY_MOCK`（第三方未交付、要活到 UAT/Demo）的形态；`DEV_MOCK` 绝不能进生产，套上运行时开关就意味着它在生产有机会被打开，机器门判 Important。两类目的相反，判据单一信源 = `rules/code.md` 约定 26「守卫策略按标记分流」
  - **★ 请求通道单一判据 + 消费者点登记门**（判据单一信源 = `frontend.md`「请求通道单一判据」，本步只做编排、不复述）：本步**新增/改动任何请求发起点**时先跑
    `git diff --name-only | xargs grep -lE "fetch\(|new EventSource|new WebSocket|axios\.(get|post|request)|\.getReader\(\)" 2>/dev/null`——命中即 ① **确认该通道走项目 URL 解析单一信源**（禁自拼 base/context-path，无单一信源则先抽再写、绝不第 N 份平行实现；可跑 `code-verification-loop` 维度 8 硬门脚本 `check_request_channel_url.py <前端目录> --changed <本次改动文件> --json` 快速确认无新增平行实现，判据不复述）② 在 `*事实清单.md`「路径消费者点」表**补登记新行**。**堵的缺口**：Step X.6 只在 base/context-path 改动时**联动既有**消费者点，**不覆盖"消费者点集合本身变大"**——新增请求通道时无人登记，正是双前缀 404 的温床。
Step 2: 页面和组件
  - 视觉：按 Step 0 判定的情形 + L1/L2 分级（L1 严格对齐基准 / L2 用项目组件默认）；情形 A/D → `mockup/` 为基准；情形 B/C → `code/` 原型自身样式为基准
  - 交互：一律按 `code/` 原型
Step 3: 路由配置
Step 4: （★ 不在此逐任务校验）前端校验（lint + 类型检查，不打包）已收敛到验收（/sprint-test），
        仅改动侧 + 资源受限执行，见 agents/frontend.md「Step 4」
Step 4.5: ★ UI 还原度静态门（约定 39 R2/R3/R10；纯静态、不起服务、不打包）：
        执行：python3 {{AIDP_HOME}}/scripts/check_ui_fidelity.py --json
        —— R2 状态视觉区分 / R3 截断可读性 判 Important；**R10 导出必须导全量判 Critical 且零豁免**。
        判定口径单一信源 = 该脚本 + rules/code.md 约定 39，命令端只编排不复述（约定 21）。
        —— 退出码：`0`=无 Critical · `1`=有 Critical · `2`=入参错（修参数重跑、不算违规）。
        Critical 当场修；Important 逐条判断是真问题还是加 `fidelity-ignore: <规则号> <原因>`
        （**原因必须写**；⛔ R10 不接受豁免）。
        —— **为什么开发期就要跑**：约定 39 的定性依据是「96% 的缺陷走一遍正常流程就会碰到，
        却全漏到 QA 侧 —— 问题不是测得不够狠，是测得太晚」。测试期的 `code-verification-loop`
        维度 10 委派的是**同一个脚本**，开发期先跑一遍等于把返工提前到还没交付之前。
```

---

### Phase 1.4：并行开发（★ 全栈场景推荐）

当范围为 "all"（空参数）时，调用 `superpowers:subagent-driven-development`：

```
并行任务：
  subagent-1 (backend-dev)：按后端开发步骤执行
  subagent-2 (frontend-dev)：按前端开发步骤执行

共享输入：docs/design/detail/{version}/* + 01_研发执行计划.md
独立产出：后端代码 / 前端代码

★ 必填字段（缺一即派单不合规，见下）：
  cascade_mode: ledger | now      # 默认 ledger（攒批）
  dev_scale:    S | M | L
```

> ⛔⛔ **派单简报必须携带 `cascade_mode` + `dev_scale`，且 `ledger` 时【不得罗列待改文档清单】**：
> 这两个判定结果由主链路的 `postdev-writeback-1.md` 步骤 3.5 / 3.8 先判好，而**子 Agent 读不到那份 flow**
> ——简报里一旦直接点名"要改哪 6 份文档"，就等价于一次强制 `--cascade-now` 全量级联，
> 攒批机制在派单路径上当场失效（实测：6 个源文件的小改动，文档改动量是代码的 1.75 倍）。
> **字段语义、`ledger` 模式下「文档级联」段的替换文本、台账一行格式，
> 单一信源 = `{{AIDP_HOME}}/reference/开发期族增量.md`「子 Agent 执行时的派单契约」**，此处不复述。

