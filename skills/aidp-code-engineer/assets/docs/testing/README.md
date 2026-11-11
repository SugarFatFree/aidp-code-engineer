# docs/testing/ — 测试文档

> **隔离级别**：版本级（不按用户隔离，QA / 研发 / 测试人员统一维护）
> **结构**：`{version}/` 下 **3 个并列子目录**（研发自测 / 正式用例 / sprint-NNN）；权威定义见 [`../init/06_版本与用户目录约定.md`](../init/06_版本与用户目录约定.md) §2.2 表。

> ★ **约定 22 攒批级联落点**：`{version}/研发自测/_开发期用例增量.md`（`_` 起头 → 不占 `NN_` 序号、不进 `00_索引.md`，
> 发布期 `/version` Step 3.3.9.5 合并回用例主文档 `02_…`）。受 `check_cascade_landing.py` 硬门约束；
> 详规见 `{{AIDP_HOME}}/reference/开发期族增量.md`。

普通开发/修复默认 implement+static+related-test，自动测试→必要修复/复验→终端，不另问单测。纯文档不适用须具体依据；缺测试/缺工具属于未核验，真实skip仅受限完成；当前任务/Sprint通过不等于版本通过。

## 目录结构

```
docs/testing/
└── {version}/
    ├── 研发自测/                      # ★ 研发自测方案 + 用例 + chrome 配置（AIDP 生成，经 /sprint-selftest）
    │   ├── 00_索引.md                 # ★ 专职导航锚（已对齐通用范式）：文件清单 + 生成时间 + 主/补充标识（dev-manual-testcase SKILL 第八步产）
    │   ├── 01_研发自测方案.md          # 范围/通过准则/缺陷跟踪 +「用例索引」段（dev-manual-testcase SKILL 第零步产）
    │   ├── 02_全量自测用例.md          # 用例内容主文档（单文件；多文件则 02_自测用例-总览.md + 03_<模块>.md）
    │   ├── 01_测试环境与账号.md        # chrome-devtools-mcp 连接 + 测试 URL + 测试账号（/sprint-selftest Step 3；★ aiauto-test 配置文件，类别≠用例分册，固定 01_ 保留槽、dedup 例外）
    │   └── NN_<业务主题>.md            # 增量（文件名不带"补充"字眼；补充身份记入 00_索引.md）
    ├── 正式用例/                      # ★ 测试人员手动上传的正式测试用例（AIDP 只读、绝不写入/预建；纯测试人员 territory）
    │   └── <模块>测试方案.md / *测试用例.md   # 由测试人员手动提供
    └── sprint-{NNN}/                  # 单 Sprint 自动测试机器证据（不默认创建Markdown报告）
        ├── sprint-{NNN}-unit-scope.json # 当前范围与选择依据
        └── sprint-{NNN}-run-set.json    # 实际运行/复用证据

```

## 三个并列子目录职责

| 子目录 | 职责 | 主要文件 | 生成方/维护方 |
|--------|------|---------|--------------|
| `研发自测/` | 研发自测方案 + 用例 + chrome 配置入口（★ 导航锚 = `00_索引.md`，已对齐通用范式）| `00_索引.md`（锚）、`01_研发自测方案.md`、`02_全量自测用例.md`（或 `02_自测用例-总览.md`+`03_<模块>.md`）、`01_测试环境与账号.md`（配置，固定保留槽、dedup 例外）| `dev-manual-testcase` SKILL，经 **`/sprint-selftest`**（版本规划期 `/version` Step 2.4.3.5 串联）|
| `正式用例/` | **测试人员**手动上传的正式方案/用例（★ AIDP 只读、绝不写入/预建，纯测试人员 territory）| `<模块>测试方案.md` / `*测试用例.md`（测试人员提供）| 测试人员（人工）|
| `sprint-{NNN}/` | 单 Sprint 测试机器证据 | `sprint-{NNN}-unit-scope.json`、`sprint-{NNN}-run-set.json` | `/sprint-test`；light证据存execution context，不建Sprint目录 |

> **三层引用闭环**：测试方案（`研发自测/01_研发自测方案.md`）→ 套件 → 用例（`研发自测/*.md`），由 `dev-manual-testcase` SKILL 强制建立；`研发自测/01_测试环境与账号.md` 与方案文档职责隔离（前者只管连接配置+账号，后者管范围/通过准则/缺陷跟踪）。
>
> **AI 浏览器自动化（独立目标实测）**：不随开发单测执行；启用时推荐 `chrome-devtools-mcp`（**仅 Web 浏览器项目**，桌面/小程序/原生 APP 不适用）。后端接口 / 前端 E2E 的自动化测试可按需挂接外部 `api-tester`（外部可选）或随仓库分发的 `chrome-devtools-mcp` 插件，产物归目标实测证据目录，不以Sprint单测冒充实测。
>
> **版本全量边界**：仅真实 autopilot 委派，且 version/build/验收基线/完整用例集合及必要依赖齐备。基线须逐项映射当前版本正式用例 ID 与可执行测试文件；缺清单即阻塞，禁止回落研发自测/全仓/历史测试全集。独立 aiauto 只执行明确目标。协议见 `{{AIDP_HOME}}/flows/sprint-aiauto-test/phase-2-unit.md`。

## 相关命令

- **`/sprint-selftest`** — 调 `dev-manual-testcase` SKILL 生成 `研发自测/` 方案 + 用例 + `01_测试环境与账号.md`（版本规划期由 `/version` Step 2.4.3.5 串联；也可单独跑 / `--supplement` 补充）
- `/sprint-test` — 当前 task/单 Sprint 相关单测、必要修复复验、已授权同范围静态/审查/CVL，终端结果；日常无报告Markdown
- `/sprint-aiauto-test` — chrome 浏览器仿真测试，产出 HTML 测试报告（落 `docs/reports/{version}/AI测试报告/`）+ 截图

## 相关文档

- [`../init/06_版本与用户目录约定.md`](../init/06_版本与用户目录约定.md) — docs/testing 结构权威定义（§2.2）
- [`../init/04_agents详细规范.md`](../init/04_agents详细规范.md) — QA Agent 职责
- [`../../{{AIDP_HOME}}/skills/dev-manual-testcase/SKILL.md`](../../{{AIDP_HOME}}/skills/dev-manual-testcase/SKILL.md) — 研发自测用例 + 测试方案生成规则
- [`../../{{AIDP_HOME}}/skills/dev-manual-testcase/references/chrome-devtools-mcp-setup.md`](../../{{AIDP_HOME}}/skills/dev-manual-testcase/references/chrome-devtools-mcp-setup.md) — chrome-devtools-mcp 安装/启动/端口转发（仅 Web 项目）
