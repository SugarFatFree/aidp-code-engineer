# /sprint-aiauto-test — AI 自动化测试统一入口（浏览器端：默认本地 CLI，显式声明才走远程 MCP）

你正在执行 `/sprint-aiauto-test` 命令——AIDP 的 **AI 自动化测试统一入口**，对部署完成的项目跑浏览器仿真测试。

参数：$ARGUMENTS

> ⛔ **上面这行不可删**：`$ARGUMENTS` 是斜杠命令正文的 **runtime 文本替换**，只在 `{{AIDP_HOME}}/commands/*.md` 里生效；
> flow 分片是被 `Read` 进来的普通文本，`${ARGUMENTS:-}` 在那里只是未设置的 shell 变量。缺了它 →
> Phase 0.1 的 `autopilot_tick_flags.py parse --arguments` 恒收空串 → `--unattended` / `--once` / `--target`
> **全部失效**；且本链路退出前已刷过心跳，开发链路据此判「测试链路健康」走暂缓，12 tick 后按 `unconverged`
> 冻结——**一条用例都没跑过**。

> **命名说明**：本命令是「AI 自动化测试」的统一编排入口，当前实现的被测端是**浏览器仿真**，由 chrome-devtools-mcp 套件提供**两个驱动**——本地 `chrome-devtools-cli`（`DRIVER=cli`，**默认**）与远程 MCP（`DRIVER=mcp-remote`，须显式声明），分流铁律见下方；命令名用 `aiauto` 而非 `chrome`，是为未来接入更多 AI 自动化测试工具预留扩展位。涉及具体浏览器启动 / 远端连接的部分仍以 `chrome` 命名（如 `.mcp.json` 的 `chrome-{git_user}` / `--reset-chrome-ip` / chrome-devtools-mcp / 9222 端口），因为那是**工具本体**，不随伞形命令名改动。chrome-devtools-mcp 是**需自行安装的公共 MCP / 插件**：Claude Code 下 `claude mcp add chrome-devtools npx chrome-devtools-mcp@latest`；Codex / DeepSeek Harness 在各自 MCP 配置中添加同一 `npx chrome-devtools-mcp@latest` 命令。

> ⛔⛔ **浏览器驱动最高铁律（任何浏览器自动化动作之前先认这条，不可绕过）**：
> **默认一律用本地 CLI ——经 `/chrome-devtools-mcp:chrome-devtools-cli` 插件技能驱动本机浏览器跑测（`DRIVER=cli`）。**
> **只有**满足下列**任一显式条件**才改用 MCP 连远程 chrome（`DRIVER=mcp-remote`，`mcp__chrome-$GIT_USER__*`）：① 测试方案「二·连接模式」**显式写了「远程」**；② 用户**本次明确说了「用 MCP / 连远程 chrome」**。
> **★ 关键：项目里配了 `.mcp.json` / MCP chrome 工具（`mcp__plugin_chrome-devtools-mcp_chrome-devtools__*` 等）就摆在工具列表里能直接调用 ≠ 授权用 MCP。** 绝不因为"MCP 摆在那、直接调更省事 / 项目已经配了 MCP 服务"就用 MCP 顶替本地 CLI——**"能调用"不是"该调用"**。没有上面两个显式条件之一，哪怕 MCP 完全可用、`.mcp.json` 已就绪，也**一定走 `/chrome-devtools-mcp:chrome-devtools-cli` 本地浏览器**。判定护栏与例外见 **Phase 0.0.7**（`MODE=remote` 需 `HAS_OWN_REMOTE` **且** `DECLARED_REMOTE` 两者同时成立，缺任一即本地 CLI）。

**★ 本命令是 `/sprint-autopilot` 的姊妹命令**：
- `/sprint-autopilot` 负责开发链路（PRD → /version → /sprint-batch + 里程碑通知）
- `/sprint-aiauto-test` 负责测试链路（部署探测 → chrome 启动 → 账号登录 → 仿真测试 + 报告）
- 两者**共享 baseline 文件** `memory/.sprint-autopilot-baseline.json` 传递版本状态
- 两者**100% 复用现有 SKILL**，不新增任何 SKILL

**★ AI 报告产物归属矩阵**（谁产骨架 / 谁 finalize / 谁发里程碑通知——一次讲清，避免散落各 Phase 误读）：

| 产物 | 骨架/创建 | 结果态 finalize | 里程碑通知 |
|------|-----------|-----------------|-----------|
| **AI执行报告**（`AI执行报告/` index.html 结果 + plan.html 计划 + `data/{BUILD}.js`）| **autopilot 子流程 R 唯一产**（Phase 3.1.5 写计划态 + 注册两页）| 计划→结果态由 **autopilot Phase 3.4** finalize；其中**真实 testSummary** 由 **本命令 Phase 3.7（R-4）** 在 #F 后回填 | **#3** 由本命令 Phase 3.7 发 |
| **AI测试报告**（`AI测试报告/` index.html + `data/{BUILD}.js` + screenshots）| **本命令 Phase 3.1~3.2.6 全产**（cp 模板 + 写 data + 注册）| 本命令（同 build 多轮覆盖 data）| **#F** 由本命令发 |
| **版本测试报告**（`版本测试报告/` 单文件 HTML）| **`/version` 发布 Step 3.3.8** 取最终验收 build 产 | 同左 | — |
| **AI数据清理**（`docs/reports/{version}/AI数据清理/${BUILD}_数据清理.md`，每 build 一份）| **本命令 Phase 3.7 Step 4 产**（cp 模板 + 填字段）；**仅 autopilot 驱动（`REPORT_ENABLED=1`）生成，standalone 不生成——与 AI执行/测试报告一致** | 本命令（build finalize 后定稿、随冻结不可变）| — |
| **部署信息段**（各报告 `README.md`）| autopilot Phase 3.4 写 AI执行报告 README；本命令 Phase 3 写 AI测试报告 README | — | — |

> 口径：**AI执行报告骨架 = autopilot 独占产**（约定 21 单一信源），本命令**不产骨架**、只在 #F 后 finalize 真实 testSummary + 发 #3；本 build 骨架缺失即经 Phase 0.2 步骤 2.5.1 自愈交接回 autopilot 补齐，绝不在骨架缺失下散落 AI测试报告。下方各 Phase 是本矩阵的执行细则。

> ⛔ **报告不可变铁律（本 build finalize 后即冻结 — 与 sprint-autopilot.md 单一信源同款）**：本命令 R-4 收尾（§3.7 Step 3）置 baseline `builds[].ai_report_finalized=true`+`ai_report_finalized_at` 后，本 build 的 AI执行报告 / AI测试报告 data **一律冻结不可改**。此后**任何测试结论变化——代码修复 / 产品口径澄清 / 用例范围调整——一律铸新 build 跑新一轮，绝不回写旧 build 的 data**（旧 build = 当时事实、新 build = 现在事实，二者并存才有趋势与审计价值）。**在已 finalized 的 build 上重新 `emit-report.py` = 严重违规**。三重确定性锁：① `emit-report.py` 对已冻结 build 拒写 `exit 2`（逃生阀 `--force-amend` 仅修笔误 + `amendments[]` 留痕）；② autopilot Phase 3.1.5 对已 finalized 的 `current_build` 强制铸新 build 复测（标「第 N 轮复测」）；③ `autopilot-ceremony-gate.py --stage final` 校 data mtime 不晚于 `ai_report_finalized_at`。**同 build 未 finalize 前的多轮收敛（覆盖 data）不受此约束**（那是本 build 尚在进行、未冻结）；一旦 R-4 收尾冻结，结论变化只能走新 build。**★ 铸新 build 出复测报告是【自动仪式】、绝不询问用户**：首测/复测都无条件出报告；复测时旧 build 报告停在上一轮（如 76.9%）是正常态，autopilot Phase 3.1.5 自动铸新 build 出新报告，**严禁**输出"要我重新铸一个 build 出复测报告吗？"这类询问（把既定自动仪式误当选择项，答案恒为是、直接做）。用户唯一决策点 = 是否发起本轮测试，发起即必出报告。

**★ 为什么独立命令**：AI 自动化测试只在"项目部署完成"后才有意义（local dev server 启动后 / cloud CI 发布后）。把它从 `/sprint-autopilot` 拆出去：
- sprint-autopilot Phase 0 配置门槛降低，监听 PRD 更敏捷
- AI 自动化测试可独立跑（研发验证 bug 修复 / 临时跑回归 / 手动触发 UAT 验证）
- 部署失败不阻塞 sprint-autopilot 的 SQL/文档归档主流程

**VCS 能力分流**：Phase 0 前以 `{{AIDP_HOME}}/scripts/vcs.py` 的 `detect_mode(Path.cwd())` 读取 `vcs_mode=git|none`，身份由 `developer_identity(Path.cwd())` 解析。`none` 下不运行 Git fetch/pull、Git diff、commit/push；这些 Git-only 节点记 `unsupported:vcs-disabled`（非 passed），继续已有本地部署 URL 的探测与浏览器测试。没有实际部署就绪证据时不冒充已部署、不测旧服务：记本轮测试 skipped，保留本地测试准备产物与可恢复状态；不得因缺 Git 走 git-pull-conflict 熔断。`git` 沿用原流程。

## 命令语法

```
/sprint-aiauto-test [flags]

# ★ 标准用法（生产 7×24）：操作系统调度（与开发链路一并安装）；版本号自动从 baseline 读
python3 {{AIDP_HOME}}/scripts/aidp_scheduler.py install                       # 测试链路默认每 5 分钟经 agent_loop.sh --once 唤起本命令
# 交互式短期用法（Claude Code 会话内；会话级、7 天过期、空闲才触发、同会话与开发链路串行）
/loop 5m /sprint-aiauto-test --unattended                             # 每 5 分钟读 baseline 看有无新部署，自动跑测

# 典型单次/临时用法
/sprint-aiauto-test --once                                           # 立即跑一次后退出（测当前开发版本）
/sprint-aiauto-test --role admin --once                              # 临时只跑单角色
/sprint-aiauto-test --skip-login                                     # 测试无需登录的页面（登录页 / 注册页）
```

> 完整 flag 清单见下方参数表。

★ **配置入口**：测试环境的 chrome 连接地址、测试环境 URL、测试账号统一维护在 `docs/testing/{version}/研发自测/` 目录（测试环境与账号配置，由 `/sprint-selftest` Step 3 与研发自测用例配套生成）。Phase 0.0.5 优先读取该目录下的配置，字段齐全时**无需任何交互式询问**。开发测试环境账号可直接明文维护（随代码入库便于团队共享）；仅生产/UAT 敏感账号才用 `memory/.sprint-autopilot-credentials.json`。

★ **核心理念要点**（规则细节下沉到对应 Phase）：

- **版本号不传参**：总是测「当前开发版本」，自动从 baseline 读；`--target <V>` 仅边界兜底（Phase 0.2）。
- **用例来源三级优先**：测试人员用例 `正式用例/`（主集）> 研发自测 `研发自测/`（查漏补集，去重后只补主集未覆盖项）> 仅 `正式用例/` 为空才以研发自测兜底（Phase 2.0）。
- **测试方案最终优先**：本命令所有内置规则（渲染模式 / 等待时长 / 工具 / 用例集与顺序等）都是默认 / 兜底；测试人员方案 `正式用例/` 显式写明的任一项直接覆盖默认，方案未规定才用默认填空。三级优先级（自高到低）：① `正式用例/` 测试人员方案 → ② `研发自测/` 研发自测方案 → ③ 本命令内置默认。Phase 0.0.5/0.0.6 读配置、Phase 2.0 选用例、Phase 2.2 控等待、Phase 0.1 定渲染模式均按此优先级。
- **双驱动**：本地走 `chrome-devtools-cli`（不依赖 MCP 服务、切有头/无头免重启 Claude Code），远程走 `chrome-devtools-mcp`（须改 MCP 配置 + 重启）。映射 + 切模式铁律见 Phase 0.1.3 / 0.1.1.5；CLI 命令细节详见依赖 SKILL。
- **本地 CLI 无头优先 — 配了远程 IP 也不抢占（铁律）**：默认用 `chrome-devtools-cli` 连接本机**无头**浏览器跑测。即便项目根 `.mcp.json` 已配好 `chrome-{git_user}` 远程条目，那也**只代表"具备远程能力"、不构成"明确强制要求"**——只要本机 Chrome 能起（无头 `--headless=new` 无需 GUI），就走本地无头 `cli`，**不因"远程已配置"翻成 `mcp`**。唯一能强制走远程的"明确强制要求" = 测试方案「二·连接模式」显式写"远程" 或 用户显式指令；两者都没有时配了远程 IP 也按本地无头跑。**有头浏览器只在两种情形用**：① 无头满足不了（反无头/测分辨率/无头下页面打不开）→ Phase 0.1.3 起即切有头；② 全程无头跑完后开主要几个界面看样式（Phase 3.6 自动眼检，看完切回无头）。详见 Phase 0.1.3 / 3.6。
- **无头优先收敛后切有头（仅远程 `DRIVER=mcp-remote`）**：远程无头跑时中途绝不切模式，先把无头闭环跑到收敛，收敛后才一次性提醒切有头补跑「必须有头」用例。本地 CLI 即时切、无此约束。详见 Phase 3.5。
- **循环交给外部调度**（7×24 = `aidp_scheduler.py` 装的操作系统定时任务；交互式短期 = 会话内 `/loop`）：本命令专注「单轮测试」（检查 baseline → 探测部署 → chrome 跑测 → 写报告 → 退出）。
- **⚠️ 进入浏览器实测前必须确保本 build 的 AI执行报告已存在**：`REPORT_ENABLED=1`（autopilot 驱动，baseline 有 `current_build`）下，若本 build 的 `docs/reports/{V}/AI执行报告/data/{BUILD}.js` 缺失 → **不得直接手驱浏览器、不得在报告缺失下散落 AI测试报告**；由 **Phase 0.2 自愈交接（baseline 读取段步骤 2.5.1）** 回 `/sprint-autopilot --skip-dev`（autopilot 子流程 R 唯一生产 AI执行报告**骨架**）补齐后再实测，Phase 3.2.7 完成核验门兜底。AI执行报告**骨架**本命令不产（autopilot 产）；但本命令在 **#F 之后** finalize data 真实 testSummary + 发 **#3 里程碑通知**（Phase 3.7 · R-4 收尾）。详见 **Phase 0.2 步骤 2.5.1** / 3.2.7 / 3.7。

★ **用户直接调用（无调度包装）的行为**：判据是 **`LOOP_UNATTENDED`（Phase 0.0.0 派生），不是裸的 `IS_LOOP_CONTEXT`**——

| 本轮信号 | 行为 |
|---|---|
| `--once` | 强制立即跑一次完整测试 |
| **`LOOP_UNATTENDED=1`（`/loop` 上下文 / `--no-loop` / 含裸 `--unattended`）★** | **照常进 Phase 1/2/3 跑测**。⛔ **绝不落到下面的"默认"行**——`--unattended` 的语义就是"没人在场、别打印引导等人"；落默认行会让 `/loop 5m /sprint-aiauto-test --unattended` 每 tick 跑完 Phase 0（**心跳照刷、`aiauto_blocked_reason` 照清**）就打印引导退出，**一条用例都不跑**。二次伤害更隐蔽：开发链路 Phase 2 0b 读到"新鲜心跳 + 空 blocked_reason"判 `TEST_LOOP_ALIVE=1` → 走"暂缓"而非熔断 → 12 tick 后按 `unconverged` 冻结，告警文案写"测试链路存活但未收敛，请人工看测试结果/环境"，而真相是测试链路一次都没启动。与 `/sprint-autopilot` Phase 1.3 决策表同款分流。 |
| 默认（无 flag + 非 `/loop` 上下文 + `LOOP_UNATTENDED=0`）| 完成 Phase 0 后**输出引导**「7×24 请用 `python3 {{AIDP_HOME}}/scripts/aidp_scheduler.py install` 装齐开发 + 测试两条链路（会话内临时可用 `/loop 5m /sprint-aiauto-test --unattended`）」+ 退出，**不跑测试**；避免误以为单次直接调用就实现了持续测试。 |

| 参数 / Flag | 默认 | 说明 |
|------------|------|------|
| **（无位置参数）** | 自动读 baseline | 命令从 `memory/.sprint-autopilot-baseline.json` 取最近一个 `phase_beta_done_at != null && internal_released_at == null` 的版本作为测试目标 — 这就是「当前开发版本」 |
| `--target <V>` | 不传 | **边界情况兜底**（通常不用）：强制锁定到指定版本（如手动回归验证 V0.1.0）；与无参模式互斥 |
| `--once` | 关 | 强制立即跑一次完整测试（**不查 deploy_status、且豁免 Phase 0.2「已测去重门」**——`--skip-dev --skip-deploy` 复测、人工修复后只提交未部署的解冻复测都靠它）。**默认交互式**；无头单发跑一轮请配 `--unattended` |
| `--unattended` ★ | 关（由本轮 `/loop` 上下文 / `--no-loop` 自动推导） | **显式声明无人值守**——最可靠的 `LOOP_UNATTENDED=1` 信号，不依赖 prompt 的 `/loop` 字符串探测（0.0.0 的 3 个本轮信号之一）。用于 `/loop` runtime 偶发未把 `/loop` 放进 prompt 时兜底、或 `--once --unattended` 无头跑一轮测试。★ 判定**只看本轮信号**；与 autopilot 共享的 baseline `autopilot.unattended_confirmed` 仅作诊断留痕、**不参与判定**（否则过期标志会吞掉手动调用该弹的窗）|
| `--no-loop` | 关 | 单次部署探测 + 跑/退出（不弹引导）；操作系统调度经 `agent_loop.sh --once` 自动补齐 |
| `--role <name>` | all | 只用指定角色登录测，不轮所有 user_roles |
| `--skip-login` | 关 | 跳过登录，仅测无需登录的页面（适合登录页 / 注册页 / 公开页）|
| `--select <mode>` | `all` | **执行选集（深度维度）**：`all` 全量 / `smoke` 仅 P0（上游把 P0 定义为「核心功能正向(冒烟)」）/ `regression` 仅带 `[回归]` 标记的用例。透传给 SKILL 的 `tasks_state.py init --select`，**复用既有优先级与回归标记、不新造标签**。⛔ **三处强制 all**（见下方护栏）：无人值守 / 编排链内调用 / 新 build 回归轮 |
| `--free-scan` | 关 | ★ **自由巡检**：全部模块用例跑完后，对「菜单可达但本轮无用例覆盖」的页面逐个导航 + 拉运行时错误（用例集永远穷举不了页面，这类页面的接口 500 / JS 报错否则完全测不出）。透传 run-context `free_scan=true`；页数上限 `free_scan_max_pages`（默认 20，超限**不静默截断**、由 SKILL 单写一条 block 巡检项列明被跳过页面）。巡检项以 `entry_kind="free-scan"` + `case_id` 前缀 `运行时-` 落 results，**不计入用例统计、不自动记 bug**，单列报告 §2.6 由人确认后再转 bug（口径见 SKILL） |
| `--capture-warnings` | 关 | 记录 `severity=P3` 的告警类运行时错误（框架废弃警告 / devtools 提示）。默认关——它们不改变 pass/fail，恒记录会让每条用例挂一串 P3、显著抬高报告体积与 token。透传 run-context `capture_warnings=true`；**P1/P2 恒记录，不受本开关影响** |
| `--skip-mcp-check` | 关 | 跳过 chrome-devtools-mcp 检测（无意义，命令会退出，仅供 debug）|
| `--reset-chrome-ip` | 关 | 删项目根 `.mcp.json` 的 `chrome-{git_user}` 条目，重收 |
| `--reset-credentials` | 关 | 删 `memory/.sprint-autopilot-credentials.json`，重收账号 |
| `--headed-glance` | 关 | ★ 仅做有头眼检：直接打开「眼检页面集」逐页截图肉眼快验，**不重跑完整用例**（远程切有头重启 Claude Code 后续用，见 Phase 3.6）|

## Phase 0：前置条件检查

> ⛔ **Phase 0 前置硬门（exit-1 级铁律 — 任何入口 / 任何用户意图都不得绕过）**：在跑任何浏览器实测 / 委派执行之前，**必须先完整跑完 Phase 0.0.0–0.4**——① `0.0.0` 最先派生 `LOOP_UNATTENDED`（否则后续无人值守分支误判挂死）② `0.0.7` 连接模式护栏（同机无 `.mcp.json` 必走本地 CLI，禁 MCP 变体顶替，与文首 ⛔⛔ 浏览器驱动铁律同源）③ `0.2` 步骤 2.5.1 自愈交接（autopilot 驱动但本 build AI执行报告骨架缺失 → 交接回 `/sprint-autopilot --skip-dev` 补齐，绝不在骨架缺失下散落 AI测试报告）。未跑完 Phase 0 → 不得进 Phase 1/2/3。
>
> ⛔⛔ **详细步骤已外置为 9 个分片、进入 Phase 0 的【第一动作】= 按需加载**：Phase 0 的完整 0.0.0–0.4 步骤拆为 **`phase-0-1.md` … `phase-0-7.md`（其中 0.2 因超 20KB 上限二次切分为 `phase-0-6.md` + `phase-0-6b.md`）**（均在 `{{AIDP_HOME}}/flows/sprint-aiauto-test/`）。**按下表「所在分片」列，进入某子步骤前先 Read 对应分片、逐项执行、绝不凭骨架或记忆略过**——下方骨架仅供"知道有哪几步 + 定位分片"，权威判定与操作一律以对应分片为准。分片清单：`phase-0-1.md`(0.0.0/0.0/0.0.5) · `phase-0-2.md`(0.0.6/0.0.7) · `phase-0-3.md`(0.1/0.1.1/0.1.1.4) · `phase-0-4.md`(0.1.1.5/0.1.2/0.1.2.1/0.1.3/0.1.3.5/0.1.4) · `phase-0-5.md`(0.1.5) · `phase-0-6.md`(0.2 子步骤 1–4) · `phase-0-6b.md`(0.2 两段执行铁律) · `phase-0-7.md`(0.3/0.4) · `phase-0-8.md`(0.1.6，★ 可选能力、未启用整段跳过)。

**Phase 0 子步骤骨架（每步先 Read「所在分片」再执行）**：

| 子步骤 | 所在分片 | 作用（一句话） |
|---|---|---|
| **0.0.0** | `phase-0-1.md` | 规范化无人值守信号 `LOOP_UNATTENDED`（所有无人值守分支的统一开关，**必须最先派生**）|
| **0.0** | `phase-0-1.md` | 拉取远端最新代码（同 `/sprint-autopilot` Phase 0.0）|
| **0.0.5** | `phase-0-1.md` | 读取测试方案文档（主配置入口 — 测试环境与账号，独立成文或内嵌皆识别）|
| **0.0.6** | `phase-0-2.md` | 测试方案 AI 自动化段预检 + 自动补全 + 信息收集（供 autopilot / sprint-batch 提前调用）|
| **0.0.7** | `phase-0-2.md` | ★ 连接模式判定护栏（同机无 `.mcp.json` 必走本地 CLI，禁 MCP 变体顶替）|
| **0.1** | `phase-0-3.md`(0.1/0.1.1/0.1.1.4) + `phase-0-4.md`(0.1.1.5/0.1.2/0.1.2.1/0.1.3/0.1.3.5/0.1.4) + `phase-0-5.md`(0.1.5) | chrome-devtools-mcp 检测 + 智能启动（本地 `cli` / 远程 `mcp` 双驱动、无头/有头）|
| **0.2**（子步骤 1–4 + 2.5bis 选集护栏）| `phase-0-6.md` | baseline 读取 + 版本解析（心跳/已测去重门/冻结字段写入契约/熔断冻结门/报告生成门/2.5.1 自愈交接**判定**/deployment/通知配置/报告落点）|
| **0.2**（执行铁律）| `phase-0-6b.md` | 自愈式交接**执行**铁律（`NEED_HANDOFF=1` 必读，含 `handoff_fail_streak` 本地熔断）+ #0a / 通知配置 / 报告落点两路径归属分工 |
| **0.3** | `phase-0-7.md` | 部署 + 测试元数据（研发自测配置优先 → PRD `deployment` 段兜底）|
| **0.4** | `phase-0-7.md` | 测试账号加载（研发自测配置优先 → credentials 文件兜底）|
| **0.4bis** | `phase-0-7.md` | ★ 账号登录冒烟预检（跑用例**前**断言账号真能登进去，别等 Phase 2 白跑一轮）|
| **0.1.6** ★ | `phase-0-8.md` | **WebMCP 驱动就绪（可选能力）**：`check_webmcp.py --detect` 判启用 → 未启用**整段跳过、零痕迹**；启用则校验驱动版本 + 两个浏览器开关 + 两行自检 + 调用约定。⛔ 版本不足**标 block 不静默降级**、不终止整轮 |

> 收口：Phase 0 全部跑完 → 进入 Phase 1。**执行前务必已按上表逐分片 Read（`phase-0-1.md` … `phase-0-6.md` / `phase-0-6b.md` / `phase-0-7.md`；`phase-0-8.md` 仅当 WebMCP 已启用时才需 Read）并逐项完成，不能只看本表。**

---

## Phase 1：部署完成探测

> ⛔ **Phase 1 关键硬门**：① `1.1` 就绪判据统一 —— `curl … 200` 仅对无登录系统足够；`REQUIRES_LOGIN=true` 时**必须以「登录成功后、自身鉴权接口连续 2 次正常取到数据」为就绪判据**（对齐 sprint-autopilot Phase 3.2.1 Step D「部署完成 ≠ 可测」），堵"可达性即就绪"陷阱 ② `1.2` 探测失败熔断 —— `/loop` 无人值守走 `UNATTENDED_YIELD` + `probe_fail_streak +1`，达 `probe_fail_freeze_threshold`（默认 3）置版本级 `needs_human=true` + `aiauto_frozen_at` + `freeze_reason=probe-timeout` + **顶层 `aiauto_blocked_reason`**（四件套）冻结本版、不再每 tick 重探刷 #4。
>
> ⛔⛔ **详细步骤已外置、进入 Phase 1 的【第一动作】= 按需加载**：Phase 1 的完整 1.1–1.3 步骤在 **`{{AIDP_HOME}}/flows/sprint-aiauto-test/phase-1.md`**。**进入本段第一动作 = Read `{{AIDP_HOME}}/flows/sprint-aiauto-test/phase-1.md`，逐项执行、绝不凭骨架或记忆略过**——下方骨架仅供定位，权威判定一律以 `phase-1.md` 为准。

**Phase 1 子步骤骨架（详见 `phase-1.md`）**：

| 子步骤 | 作用（一句话） |
|---|---|
| **1.1** | 探测策略（按 `deployment.mode` 分流 local/cloud + ⛔ 有登录系统就绪判据）|
| **1.2** | 探测失败处置（#4 里程碑通知 + 交互式/无人值守分流 + `probe_fail_streak` 熔断冻结）|
| **1.3** | ★ 里程碑通知 #D（部署完成-开始自动化测试；主集/补集用例对称计数）|

> 收口：探测成功清零 `probe_fail_streak` → 进入 Phase 2。**执行前务必已 Read `phase-1.md`。**

---

## Phase 2：AI 自动化仿真测试主循环

> ⛔ **执行内核委派 `auto-test-runner` skill（单一信源，约定 21）**：本 Phase 的用例执行方法论全部沉淀在 `auto-test-runner` skill，**命令端不复述、不手写逐条 chrome 调用**——只做三件事：① 组装 run-context（2.0.5）② **按模块派「测试执行子 Agent」**（用 `Agent`/Task 工具，prompt 里只给 `auto-test-runner` 的 `SKILL.md` + 方法论文件路径 + 本模块用例路径 + run-context 路径，令子 Agent **自行 `Read`**；⛔ 主循环**不**用 `Skill` 工具 invoke auto-test-runner——子 Agent 拿不到 Skill 工具，且把几千行方法论灌进主循环纯属浪费上下文）③ 消费其产物做 AIDP 后处理（运行时错误升级 bug / AI测试报告 HTML / 里程碑通知）。2.1/2.2 的浏览器操作细节仅为 **skill 内部行为示意**，命令端绝不自己直驱浏览器。
>
> ⛔⛔ **详细步骤已外置为 2 个分片、进入 Phase 2 的【第一动作】= 按需加载**：Phase 2 的完整 2.0–2.4 步骤拆为 **`phase-2-1.md`（2.0）+ `phase-2-2.md`（2.0.5–2.4）**（均在 `{{AIDP_HOME}}/flows/sprint-aiauto-test/`）。**按下表「所在分片」列，进入某子步骤前先 Read 对应分片、逐项执行、绝不凭骨架或记忆略过**——下方骨架仅供定位，权威判定一律以对应分片为准。

**Phase 2 子步骤骨架（每步先 Read「所在分片」再执行）**：

| 子步骤 | 所在分片 | 作用（一句话） |
|---|---|---|
| **2.0.0** | `phase-2-1.md` | ⛔⛔ 用例增量未级联前置门（台账未收口即不许开测）|
| **2.0.0bis** | `phase-2-1.md` | 用例增量前置门的补充判据 |
| **2.0** | `phase-2-1.md` | 用例来源优先级解析（★ 测试人员为主 + 研发自测查漏补充 + 跨版本 `[回归]` 继承 + 渲染模式拆分）|
| **2.0.5** | `phase-2-2.md` | 组装 run-context + 派测试执行子 Agent（★ 执行内核入口）|
| **2.0.7** | `phase-2-1.md` | ★ 前置数据体检门（用例声明的前置数据是否真的在）|
| **2.1** | `phase-2-2.md` | 登录 → 测试 → 登出循环（★ skill 内部行为示意，命令端不手写直驱）|
| **2.2** | `phase-2-2.md` | chrome-devtools-mcp 调用（★ skill 内部行为示意 — auto-test-runner「Web 端驱动适配器」执行）|
| **2.3** | `phase-2-2.md` | `--skip-login` 模式（测公开页）|
| **2.4** | `phase-2-2.md` | ★ 运行时错误全程捕获与 bug 记录（不在用例里也要记）|

> ★ **WebMCP 条件启用入参**（默认不传）：`auto-test-runner` 的 **`invoke` 补充能力**（列出/调用页面登记的工具，属 **Web 适配器的可选能力、不是第五个端**）与其**驱动版本校验**均为**入参门控**，SKILL **明令不自行探测**。组装 run-context（2.0.5）时先跑 `python3 {{AIDP_HOME}}/scripts/check_webmcp.py --detect --json`，`enabled: true` 才把 `webmcp_enabled: true` + `webmcp_entry_symbols` + `webmcp_launch_command` 写进 run-context 并在派子 Agent 的 prompt 里点明；**不传 = `invoke` 与版本校验永不启用**。⛔ 版本不足时由 SKILL 标 `block(webmcp-driver-too-old)`，**不得静默降级为「就当没有 WebMCP」**——那会让这一整类用例全绿式消失、报告看不出漏测。Phase 0.1.6（`phase-0-8.md`）已做驱动就绪预检，本处只负责把入参传下去。

> 收口：auto-test-runner 跑完 → 进入 Phase 3 生成报告。**执行前务必已 Read `phase-2-1.md` + `phase-2-2.md`。**

---

## Phase 3：测试报告生成（HTML — AI测试报告）

> ⛔ **Phase 3 关键硬门**：① `3.0`/`3.2.7` 报告生成门 —— AI测试报告**仅在 `/sprint-autopilot` 流水线驱动（`REPORT_ENABLED=1`，baseline 有 `current_build`）时生成**，standalone 只跑测试不产报告 ② `3.2.5` 截图落盘硬核验 —— 归集后截图目录必须存在且非空，**缺失绝不生成"完成"报告** ③ `3.7`（R-4）finalize AI执行报告真实 testSummary + 发 #3 里程碑通知，一旦 `ai_report_finalized=true` 即冻结、结论变化只能铸新 build（报告不可变铁律，见文首 ⛔）。
>
> ⛔⛔ **详细步骤已外置为 6 个分片、进入 Phase 3 的【第一动作】= 按需加载**：Phase 3 的完整 3.0–3.8 步骤拆为 **`phase-3-1.md` … `phase-3-5.md`（其中 3.4 因超 20KB 上限二次切分为 `phase-3-3.md` + `phase-3-3b.md`）**（均在 `{{AIDP_HOME}}/flows/sprint-aiauto-test/`）。**按下表「所在分片」列，进入某子步骤前先 Read 对应分片、逐项执行、绝不凭骨架或记忆略过**——下方骨架仅供定位，权威判定一律以对应分片为准。分片清单：`phase-3-1.md`(3.0/3.1/3.2/3.2.5) · `phase-3-2.md`(3.2.6) · `phase-3-3.md`(3.2.7/3.2.8/3.3) · `phase-3-3b.md`(3.4) · `phase-3-4.md`(3.5/3.6) · `phase-3-5.md`(3.7/3.8)。

**Phase 3 子步骤骨架（每步先 Read「所在分片」再执行）**：

| 子步骤 | 所在分片 | 作用（一句话） |
|---|---|---|
| **3.0** | `phase-3-1.md` | 报告生成门（AI测试报告仅 autopilot 流水线驱动时生成）|
| **3.1** | `phase-3-1.md` | 报告产物（HTML 唯一形态 — 不产出 docs/testing markdown 报告）|
| **3.2** | `phase-3-1.md` | 报告内容（捕获后渲染进 HTML 的数据）|
| **3.2.5** | `phase-3-1.md` | ★ 归集 skill 证据 + 截图落盘硬核验（强制；缺失绝不生成"完成"报告）|
| **3.2.5bis** | `phase-3-1.md` | ★ 8 维度独立质量检查子 Agent（Critical 门，⛔ 不得跳过）|
| **3.2.6** | `phase-3-2.md` | ★ 生成 AI测试报告 HTML（该 build 子页 + 综合首页刷新）|
| **3.2.7** | `phase-3-3.md` | ★ AI执行报告完成核验门（入口无关，下沉到测试链路）|
| **3.2.8** | `phase-3-3.md` | ★ 沉淀「环境探针档案」（与用例无关的环境事实，供下轮 0.0.5 复用）|
| **3.3** | `phase-3-3.md` | baseline 更新（★ CONVERGED 无条件先算好，供各消费点复用）|
| **3.4** | `phase-3-3b.md` | ★ 里程碑通知 #R（每轮结束）+ #F（最终完成）|
| **3.5** | `phase-3-4.md` | ★ 本轮收敛判定（本地 + 远程通用）+ 切有头提醒（仅 `DRIVER=mcp-remote` 远程）|
| **3.6** | `phase-3-4.md` | ★ 无头跑完后「自动有头眼检」（按环境有头能力自动决策，不询问用户）|
| **3.7** | `phase-3-5.md` | ★ finalize AI执行报告 + 发 #3 里程碑通知（#F 之后 · 本 build 收尾 · R-4）|

> 收口：Phase 3 全部跑完 → 本 build 报告 finalize 冻结、里程碑通知完成。**执行前务必已按上表逐分片 Read（`phase-3-1.md` … `phase-3-3.md` / `phase-3-3b.md` / `phase-3-4.md` … `phase-3-5.md`）。**

---

## 失败处置（里程碑通知 #4 触发处）

任何 Phase 失败均走：

1. **暂停命令**（不退出）
2. **发 #4 里程碑通知**（同 sprint-autopilot 模板，经 `python3 {{AIDP_HOME}}/scripts/notify.py --auto ...`；退出码 3 = 未配置任何通知渠道 → 静默跳过本播报节点，⛔ 不弹窗问人）：
   ```
   🚨 /sprint-aiauto-test {TARGET_VERSION} 卡住，需要你介入
   阶段：Phase {N}
   错误：{摘要 200 字符}
   日志：memory/aiauto-test-{YYYYMMDD-HHMM}.log
   📌 下一步：① 接管  ② 修复后解冻：python3 {{AIDP_HOME}}/scripts/autopilot_unfreeze.py --manual {TARGET_VERSION}
             ③ 交互式会话内回复 retry / skip / abort
   ```
3. **★ 按上下文分流（对齐 sprint-autopilot 失败处置 step 3）**：
   - **交互式**（`LOOP_UNATTENDED=0`）→ 在终端打印同一摘要与四个选项后**结束本轮**（baseline 不更新），由用户在对话中回复 ①接管 / ②retry / ③skip / ④abort 再继续；**绝不长挂轮询等人**。
   - **★ 无人值守**（`LOOP_UNATTENDED=1`）→ **一秒不等**（无人可答）：走 `UNATTENDED_YIELD`（发完 #4 即**退出本 tick**），交下一轮调度唤起按 baseline 状态决定重试；同时**在失败确认点即写盘** `versions.{V}.aiauto_test_unconverged_streak +1`（并入 Phase 3.5 未收敛护栏统一熔断，见下）。

---

## 7×24 守护用法

### #1 ★ 标准：操作系统调度（与开发链路一并安装）

```bash
python3 {{AIDP_HOME}}/scripts/aidp_scheduler.py install [--agent claude|codex|dsh] [--test-interval 5m]
python3 {{AIDP_HOME}}/scripts/aidp_scheduler.py status
```

- 开发链路（`/sprint-autopilot`，默认 10m）与测试链路（本命令，默认 5m）各一个独立定时任务，每轮经 `{{AIDP_HOME}}/scripts/agent_loop.sh --once <命令> --unattended` 唤起（自动补 `--no-loop`、flock 互斥、日志落 `memory/{{AIDP_HOME}}/logs/`），两条链路互不阻塞；任一链路心跳中断由 `aidp_scheduler.py watchdog` 写本地告警台账 `memory/{{AIDP_HOME}}/alerts.jsonl` 并发通知。
- 非交互执行需预授权工具权限（Claude `permissions.allow` / Codex `codex exec --sandbox workspace-write` + 项目 trust / DeepSeek Harness 在 `scheduler.exec.dsh` 配置执行命令），详见 `{{AIDP_HOME}}/reference/agent-tools.md` 第三节；各 CLI 参数以所用版本官方文档为准。

### #2 会话内 `/loop`（Claude Code 交互式短期用法）

```bash
/loop 10m /sprint-autopilot --unattended     # 监听 PRD → 开发 + 里程碑通知（不跑 chrome）
/loop 5m  /sprint-aiauto-test --unattended   # 监听 baseline 看是否有新部署 → AI 自动化实测 + 报告
```

`/loop` 是会话级定时任务：会话关闭即停、7 天后自动过期、只在会话空闲时触发，同一会话两条实际串行（一次长的浏览器实测会推迟开发链路）。7×24 用 #1。

### #3 单次 / 临时

```bash
/sprint-aiauto-test                                       # 用户直接调 = 配置补全 + 提示挂载方式后退出（★ 不传版本号，自动从 baseline 解析）
/sprint-aiauto-test --once                                # 强制跑一次（兜底锁定版本用 --target {V}）
/sprint-aiauto-test --role admin --once   # 临时只跑单角色（★ 无位置参数：版本号自动读 baseline）
/sprint-aiauto-test --headed-glance                       # 仅做有头眼检：打开主要功能界面肉眼快验（不重跑用例；远程切有头重启后续用，见 Phase 3.6）
```

---

## 与其他命令的关系

| 命令 | 关系 |
|------|------|
| `/sprint-autopilot` ★ | **姊妹命令**：autopilot 写 baseline，aiauto-test 读 baseline；两条链路同时运行 |
| `{{AIDP_HOME}}/scripts/aidp_scheduler.py` ★ | 7×24 守护标准方式：两条链路各一个操作系统定时任务 + 心跳巡检 |
| `/loop` | 会话内交互式短期用法 |
| `/sprint-test` | autopilot 内部已调（静态扫描走 code-verification-loop）；aiauto-test 是浏览器实测，互补 |
| `/sprint-bugfix` | aiauto-test 发现**失败用例 + 运行时错误（即使关联用例通过 / 页面无用例覆盖，见 Phase 2.4）**→ 都回写「问题汇总清单」，用户跑 sprint-bugfix 一并修复 |
| `chrome-devtools-mcp` | 实际跑测的工具层（研发自测/ 配置推荐工具；用户也可用其他方式）|
| `/sprint-selftest` | Step 3 与研发自测用例配套生成 `研发自测/` 测试环境与账号配置（chrome 地址 / 测试环境 / 账号配置入口）|
| `notify.py` ★ | 测试阶段里程碑通知 #D/#R/#F + 失败 #4 的发送器（`--auto` 按 `memory/aidp-config.yaml` 的 `notify.channels` 依次尝试，成功即停；未配置任何渠道退出码 3 → 静默跳过，判据见 autopilot 0.1bis）|

## 注意事项

0. **🔗 约定 24 commit checkpoint（本命令的每条 `git commit` 路径通用）**：本命令虽不改业务代码，但仍有会 commit 的分支（如 Phase 0.2 Step 3 自动补全「测试环境与账号」配置后提交）。**这些 commit 之前**先跑 `python3 {{AIDP_HOME}}/scripts/commit_gate.py --quiet` 读 JSON（纯配置提交通常无欠账，但**必须跑过判定、不得默认跳过**）；退出码 3/4 = 本轮结束前有义务未落地（约定 22 台账积压 / CICD 推送欠账），不是禁止 commit。判定字段与处置 **单一信源 = 约定 24**，此处不复述。
1. **不自动 merge master / 不改代码**：本命令只读 + 测试，不修改代码；测试失败由用户跑 `/sprint-bugfix`
2. **配置入口优先 研发自测/ 配置**（chrome 地址 / 测试环境 URL / 账号）+ **账号配置分两类**（开发测试环境明文 / 生产·UAT 走 credentials JSON）：总则见 Phase 0.0.5，账号细则见 Phase 0.4
3. **测试报告 = HTML**：结果渲进 `docs/reports/{version}/AI测试报告/`（`data/{BUILD}.js` + `index.html` 综合首页/各 build 子页 + 图表），截图落 `AI测试报告/screenshots/{BUILD}/`；**不产出 docs/testing markdown 报告**（见 Phase 3.1）。发布时 `/version` Step 3.3.8 取最终验收 build → 版本测试报告单文件 HTML
4. **默认（无参）选版优先级**：先取 phase_beta_done_at 最新 + internal_released_at 为空的版本；如全部已测过 → 退出（不重复测）。**`needs_human=true`（熔断冻结）的版本自动跳过**（探测超时/账号缺失/未收敛达冻结阈值三类熔断，见 Phase 0.2 熔断冻结门）；解冻途径：按冻结类别自动解冻（新部署 / 配置更新 / 环境类自动复探，见 `{{AIDP_HOME}}/flows/sprint-aiauto-test/rationale.md` 冻结枚举表），或人工 `python3 {{AIDP_HOME}}/scripts/autopilot_unfreeze.py --manual <V>`
5. **baseline 失同步保护**：本命令只**追加写** aiauto_tested_at / aiauto_test_report / aiauto_test_build_data 字段 + 刷 `builds[].status:"tested"`/`pass_rate`；不删除 sprint-autopilot 写的字段
6. **mode=none 跳过**：autopilot_decisions.deployment.mode=none 的版本，本命令直接退出（标"该版本不做浏览器测试"）
6bis. **★ `--select` 子集轮的三条硬护栏（子集≠测过了）**：选集会让「通过率」「P0=100%」等准则**只对子集成立**，若不设界就会出现「跑了 5 条 P0 全绿 → 版本被当成测过了」。故：
   - **① 无人值守强制 all**：`--unattended` / `/loop` 上下文 / autopilot 委派 / `sprint-batch` Step 6 调起时，**忽略 `--select` 并终端告警**——这些路径产出的是官方 build 报告并驱动准发布收敛门，子集会让「测过了」名不副实。
   - **② 新 build 回归轮强制 all**：上一 build 缺陷经 `/sprint-bugfix` 修复后的复测属 **build 递增（全量）**，SKILL 硬边界明令禁用选集（`execution-methodology` 第五节：*self-heal 复测锁 round 级/同 build；新回归锁 build 级/全量*）。判据 = 本版 `builds[]` 已有前序 build 且本轮是修复后复测。
   - **③ 子集轮不写「已测」语义**：只写 `aiauto_subset_tested_at` + `aiauto_select_mode`，**不写 `aiauto_tested_at`**（后者是准发布收敛门与 `current-version` 选版的判据，子集不足以支撑）。报告标题与终端摘要须显著标「子集轮（select=<mode>），通过率仅对该子集成立」。
   - 适用场景：**交互式手动快验**（改完一处想先跑冒烟看有没有崩），不替代任何一次正式全量轮。

7. **★ 运行时错误一律记 bug（见 Phase 2.4）**：测试过程中页面出现的接口报错（非 2xx）/ JS 异常（console error）/ 错误 UI，**无论是否属于某条用例、无论关联用例断言是否通过**，都捕获并记为 bug，回写「问题汇总清单」让 `/sprint-bugfix` 接力。**用例全通过但有运行时错误 ≠ 绿灯**，不可直接发布。权限测试用例预期内的 401/403 需在用例正文标 `预期错误:` 才排除。捕获范围 = 本轮用例覆盖到的页面；开启 `--free-scan` 时另覆盖「菜单可达但无用例覆盖」的页面（口径见 Phase 2.1，能力已由 `auto-test-runner` 落地）
8. **★ 双驱动：本地 CLI / 远程 MCP**：浏览器驱动按场景分流（本地 `DRIVER=cli` 免重启切模式 / 远程 `DRIVER=mcp-remote` 须先配后启 + 重启）——见 Phase 0.1.3。
9. **★ 无头优先跑完整闭环、收敛后才提醒切有头（仅 `DRIVER=mcp-remote` 远程）**：见 Phase 3.5（本地 `DRIVER=cli` 无此约束，即时切有头同会话跑掉）。
10. **★ 无头跑完后「自动有头眼检」**：全程无头测试结束后按环境有头能力自动决策（不询问用户）做一次纯肉眼快验——见 Phase 3.6。
