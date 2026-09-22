# /sprint-autopilot — 7×24 全自动开发编排器

> ⚠️⚠️ **本命令不会自己创建定时器（务必看清）**：`/sprint-autopilot` 是**被反复唤起的被调用方**、它自身**不自举定时循环**。**直接调用 `/sprint-autopilot` 默认只跑配置向导**；只有 `/loop`、明确执行意图、`--once` 或其他执行 flag 才跑一轮。**★ 执行一轮 = 把这一对版本的全流程【完整做完】**——含研发执行计划里**全部 Sprint**（不是一个 Sprint 就收工）+ 部署 + AI 测试；**⛔ 无外部调度（操作系统定时任务 / `/loop`）时禁止中途 `UNATTENDED_YIELD`**（`HAS_WAKE_SOURCE=0`，见 Phase 0.0.0 派生 + Phase 3.2 执行粒度）——yield 了没有下一 tick 来接，就是把没干完的活儿丢回给人。要 **7×24 无人值守持续运行，由操作系统调度两条链路**：`python3 {{AIDP_HOME}}/scripts/aidp_scheduler.py install`——为开发链路（本命令，默认 10m）与测试链路（`/sprint-aiauto-test`，默认 5m）各装一个独立定时任务，每轮经 `{{AIDP_HOME}}/scripts/agent_loop.sh --once` 以 `--unattended --no-loop` 唤起；另装第三条独立 watchdog 定时任务巡检两条链路心跳（含从未启动）。Claude Code 会话内的 `/loop 10m /sprint-autopilot --unattended` + `/loop 5m /sprint-aiauto-test --unattended` 只作交互式短期用法（会话级、定时任务 7 天过期、只在会话空闲时触发、同会话两条串行）。文中「7×24 全自动」指的是"装上外部调度后"的能力，**不是** autopilot 会自己起循环。
> - **可选·调度自举（有持久副作用、必经确认门）**：直接调用（非调度上下文）且你表达了"持续运行 / 挂着自动跑 / 7×24"意图时，命令端**可用 `AskUserQuestion` 询问是否代你安装调度**——确认后执行 `python3 {{AIDP_HOME}}/scripts/aidp_scheduler.py install`（先 `--dry-run` 展示将写入的定时任务）；**绝不静默创建**（定时任务是持久副作用）。不确认则按"只跑一轮"执行并在收尾提示上述挂载方式。

你正在执行 `/sprint-autopilot` 命令，启动从「产品在需求大目录下创建版本子目录 + 上传 PRD」到「等 review/merge PR + 等正式打 tag」全链路无人值守开发。

> ⛔⛔ **命令定义性契约（第一铁律，全文最高优先）**：`/sprint-autopilot` 的执行入口分两类：**裸探路调用默认只跑配置向导**；只有 **`/loop` 唤起、存在明确执行意图、或显式 `--once`/执行 flag** 才进入「版本规划(`/version`) → 全量开发(`/sprint-batch`) → AI 自动化测试(`/sprint-aiauto-test`)」全流程。
> 1. **配置向导入口** → 无 `/loop`、无执行意图、无 `--once`/执行 flag 时，仅扫描版本、补全配置并提示标准 loop 用法，然后退出；不得误跑 Phase 2/3。
> 2. **全流程入口** → `/loop`、明确执行意图、`--once`、`--no-loop`、`--target` 或其他显式执行 flag 均进入全流程；流程裁剪仍只能来自用户显式 flag（`--no-planning` / `--skip-dev` / `--skip-deploy` / `--skip-pre-release` / `--skip-aiauto-test`）或交互式用户选择。
>
> **除此之外一律跑满全流程。严禁**由需求语义判定（"看着像增量/bug修复"）、关键词 grep（test-intent）、产物存在性推断等**任何隐式方式**少跑任何一段——模型对需求类型的判断**只允许影响「某段流程内部做什么工作」**（如开发段跑 `/sprint-dev` 累进而非全量 Sprint），**绝不允许影响「是否执行该段流程」**。落地细则见 Phase 3.0「流程裁剪唯一授权原则（P0-0）」+ Phase 3.1.0「incremental 硬判据（P0-1）」+ 收尾门规划产物存在性校验（P0-2）+ 交互单次自跑 AI 测试（P0-4）。

**★ 本命令是顶层编排器**：内部串联 `/version` + `/sprint-batch`（+ 交互单次/第二条 loop 的 `/sprint-aiauto-test`），在关键节点经 `notify.py --auto` 主动发**里程碑通知**播报进度（渠道取 `memory/aidp-config.yaml` 的 `notify.channels`；节点定义见 0.1bis 通知机制表）。

**★ 核心工作模式**：
- **无需传版本号**——命令自动扫描 `docs/requirements/` 下所有 `V*.*.*` 子目录
- **每轮只处理「最近的一对」**：① 上版准发布（如有 Sprint 全关闭但未归档的版本）+ ② 下版全流程（最新有 PRD 但未规划的版本）
- **准发布 ≠ 正式发布**：调 `/version <V> --no-tag` 跑归档（SQL 整理 + 文档清理 + memory 同步），**不打 tag**；tag 留给运维正式部署时手动跑 `/version <V>` 补打
- 这样产品在 `docs/requirements/V0.2.0/产品提供/` 加 PRD 就会触发：V0.1.0 准归档 → V0.2.0 跑全流程

**★ 与 `/sprint-batch` 的边界**：
- `/sprint-batch`：批量跑已规划好的 Sprint，需要先手工跑 `/version`
- `/sprint-autopilot`：自动发现版本号 + 监听 PRD root + 串联多版本动作；适合 7×24 无人值守

参数：$ARGUMENTS

> ⛔ **上面这行不可删**：`$ARGUMENTS` 是斜杠命令正文的 **runtime 文本替换**，只在 `{{AIDP_HOME}}/commands/*.md` 里生效。
> flow 分片是被 `Read` 进来的普通文本，`${ARGUMENTS:-}` 在那里只是一个未设置的 shell 变量。
> 缺了它 → Phase 0.1 的 `autopilot_tick_flags.py parse --arguments "${ARGUMENTS:-}"` 恒收空串 →
> **全部 flag 落 0，含 `--unattended`** → `LOOP_UNATTENDED=0` + `HAS_WAKE_SOURCE=0` →
> Phase 1 落到「输出引导文案 → 退出」，**每 tick 刷一屏引导、永不开工**。

**VCS 能力分流（Phase 0.1 前先执行）**：由 `{{AIDP_HOME}}/scripts/vcs.py` 的 `detect_mode(Path.cwd())` 得到 `vcs_mode=git|none`，`developer_identity(Path.cwd())` 提供身份；把模式传给 Phase 0/2/3 与 `/sprint-dev`、`/sprint-test`、`/sprint-close`、`/sprint-aiauto-test`。`none` 下跳过 fetch/pull、Git 差异/commit/push 与以推送为前提的 CICD/云部署，逐节点在当前 build `steps[]` 和 baseline 记录 `status=skipped`、`reason=unsupported:vcs-disabled`（不是 passed），继续本地规划、Sprint 开发、测试、归档与 AI执行报告。无 Git 不作为 `dirty-tree` 或 `git-pull-conflict` 冻结理由；不可写 `last_deployed_at` 或声称发布/部署成功；无 Git 本地归档核验成功后可写内部游标 `internal_released_at`，仅供选版，不代表正式发布。需要部署后浏览器实测时如实标记未部署并跳过，不对未部署的旧服务测试。Git 模式的推送分类、CICD 与仪式门保持原样；能力缺失不豁免本地仪式产物。

## 命令语法

```
/sprint-autopilot [PRD_root] [flags]

# ★ 标准用法（生产 7×24）：操作系统调度两条链路，缺一不成完整闭环 ★★
python3 {{AIDP_HOME}}/scripts/aidp_scheduler.py install   # 开发（10m）+ 测试（5m）+ 独立 watchdog（5m）三条任务
python3 {{AIDP_HOME}}/scripts/aidp_scheduler.py status    # 定时任务在位 + 两条链路心跳
# 交互式短期用法（Claude Code 会话内；会话级、7 天过期、空闲才触发、同会话两条串行）：
/loop 10m /sprint-autopilot --unattended    # 开发链路：扫 docs/requirements/ → /version → /sprint-batch → 触发部署（不跑浏览器）
/loop 5m  /sprint-aiauto-test --unattended   # 测试链路：监听 baseline 新部署 → chrome 实测 + 报告 + 播报
# ⚠️ 硬前置：autopilot 单命令在【无人值守】下只跑开发链路，写完 last_deployed_at 即止；浏览器实测/AI测试报告靠测试链路。
#    ★ 例外（P0-4）：交互式【单次】调用（LOOP_UNATTENDED=0、无第二条 loop）→ 部署后 autopilot 自己跑一次 /sprint-aiauto-test --once --unattended（除非 --skip-aiauto-test）。
#    只跑 autopilot 一条 → 测试半环【永久不会自动启动】，命令仅能 WARN、无法自愈（见 Phase 3.4 step4③ 双链路自检）。

# 几种典型直接用法（完整 flag 见下方参数表）
/sprint-autopilot                        # 首次直接调用 = 配置向导：扫版本 + 配置补全 + 提示挂载方式后退出
/sprint-autopilot --once                 # 强制立即跑「最近一对」一次（不查 baseline）
/sprint-autopilot --no-loop              # 单次 baseline 检查 + 跑/退出（有外部调度会再次唤起时使用；agent_loop.sh 自动补）
/sprint-autopilot --target V0.2.0        # 强制下版 = V0.2.0（跳过自动发现）
/sprint-autopilot --force-replan         # 无视"规划已存在"，强制重跑 /version 重新规划（PRD 大改时用）
```

| 参数 / Flag | 默认 | 说明 |
|------------|------|------|
| `[PRD_root]` | `docs/requirements/` | PRD 需求大目录，命令在此目录下扫描 `V*.*.*` 子目录 |
| **（无 flag）** | — | **默认 = 配置向导**：扫描版本 → 识别最近一对 → Phase 0 配置补全 → 提示挂载方式（`aidp_scheduler.py install`，或会话内 `/loop 10m /sprint-autopilot --unattended`）+ 退出，**不跑 Phase 2/3**。**例外**：用户**明确表达执行意图**（"开发并测试 / 跑完后续流程 / 帮我自动执行"等）→ **等价 `--once` 全流程**、不停在向导态（见上方「交互式全量执行语义」）|
| `--no-loop` ★ | 关 | 单次 baseline 检查 + 跑最近一对（Phase 2 上版准发布 + Phase 3 下版全流程）/ 退出；适合操作系统调度（`agent_loop.sh --once` 自动补齐）或 `/loop` 包装内周期触发 |
| `--once` | 关 | 强制立即跑最近一对（不查 baseline；PRD 已就绪场景）。**默认交互式**（用户在场、保留弹窗）；如需无头单发跑一轮请配 `--unattended`（见下）|
| `--unattended` ★ | 关（由本轮 `/loop` 上下文 / `--no-loop` 自动推导） | **显式声明无人值守**——最可靠的 `LOOP_UNATTENDED=1` 信号，**不依赖 prompt 的 `/loop` 字符串探测**（0.0.0 的 3 个本轮信号之一）。用于 ① 官方 `/loop` runtime 偶发未把 `/loop` 放进 prompt 上下文时兜底 ② `--once --unattended` 无头跑一轮。★ 判定**只看本轮信号**：本轮既无 `/loop` 上下文也无 `--unattended`/`--no-loop` → 一律按交互式（保留交互式配置确认门）；baseline `autopilot.unattended_confirmed` 仅作诊断留痕、**不参与判定** |
| `--watch` | 关 | 单 Bash session 内短期轮询（≤ 50 分钟）|
| `--watch-interval <秒>` | 300 | `--watch` 模式的 Bash 轮询间隔 |
| `--target <V>` ★ | 自动发现 | 强制下版 = 指定版本（跳过自动 SemVer 排序探测）|
| `--skip-pre-release` ★ | 关 | 跳过 Phase 2 上版准发布，仅跑 Phase 3 下版全流程 |
| `--skip-aiauto-test` ★ | 关 | **用户显式裁剪 AI 自动化测试**（P0-0「唯一合法跳过」的授权来源）：置 `WILL_BROWSER_TEST=0`，本轮不委派浏览器实测、不因「测试链路未挂载」冻结、收尾门按静态-only 档核验 |
| `--skip-dev` ★ | 关 | **置 `ENTRY_MODE=test-only`**（`phase-3-2.md` 步骤 1 的唯一无条件来源）：跳过 Phase 3.2 整个开发循环，直接用现有代码走部署 + 触发测试（「代码已就绪只想部署/测」场景）。⛔ **开发链路里程碑通知 #0/#1/#1b/#1c/#1d/#2/#pre-\* 一律不发**（通知集矩阵 `phase-0-5.md` 0.1bis 的 `test-only` 行），只发测试链路通知 #D/#R/#F/#G/#3 + #4；收尾门的 `EXPECT_CARDS` 亦相应留空 |
| `--skip-deploy` ★ | 关 | 跳过 Phase 3.2 的部署动作，仅开发 + 静态自测，不部署、不发 #1d 部署通知（用户「提交推送+部署阶段可跳过」场景；本轮等效 `deployment.mode=none` 行为，不写 `last_deployed_at`）|
| `--full-auto` | **默认开启** | 跳过 Phase 2/3 中途 AskUserQuestion；Phase 0 的一次性决策收集**不受影响** |
| `--strict-prd` ★ | 关 | 下版 PRD 头部 `autopilot_decisions` 缺字段时**不收集**，直接退出（强制预先填好）|
| `--force-replan` ★ | 关 | **无视 Phase 3.1.0「版本规划已存在」判定**，强制重跑 `/version` 重新规划（用于 PRD 大改、需推翻已有设计的场景）；默认行为是规划产物齐全则跳过 `/version` |
| `--no-planning` ★ | 关 | **显式跳过 `/version` 版本规划**（P0-0 唯一合法的"跳过规划"声明；`NO_PLANNING=1`）——用于用户明确"本版不做规划、直接改码"的场景。**必须在交付台账留痕**，收尾门 `autopilot-ceremony-gate.py --no-planning 1` 认此声明、放行"规划产物缺失"（否则 `full`/`incremental` 缺六类规划产物即 `exit 1`，见 P0-2）。不加此 flag 时全新版本一律跑 `/version`（绝不隐式免规划）|
| `--single-sprint` | 关 | 每个 Sprint 关闭后暂停，交互式下在对话中等用户回复 `continue` 才进下一个（**★ 无人值守下已降级为"绝不空等用户回复"：`HAS_WAKE_SOURCE=1` 走逐 tick 单 Sprint 推进；`HAS_WAKE_SOURCE=0`（无外部调度）⛔ 不得 yield，本轮内连跑到底**，见 Phase 3 `--single-sprint` × `/loop` 说明）|
| `--batch-one-tick` ★ | 关 | **opt-out「逐 tick 单 Sprint」上下文优化**：强制在**单个 tick 内一口气跑完研发执行计划全部 Sprint**（旧默认）。⚠️ 全量开发的所有 Sprint 累积在同一上下文，Sprint 多时**极易撑爆上下文（可破 1M）**——仅在"Sprint 极少 / 想要最快 wall-clock / 交互式盯着看"时用。**默认（不带本 flag）+ `HAS_WAKE_SOURCE=1`（`/loop` 守护 / OS cron）= 逐 tick 单 Sprint 推进**（每 tick 只跑一个 Sprint 后退出、下 tick 从 `run_state` 续跑下一个，把「1 个大上下文」拆成「N 个小上下文」，见 Phase 3.2「执行粒度」）。⛔ **`HAS_WAKE_SOURCE=0`（交互式单次 / 裸 `--unattended`，无人唤起下一 tick）时本 flag 无意义——那种情形【恒】本轮内跑满全部 Sprint、绝不 yield**|
| `--no-notify` | 关 | 本轮强制 `NOTIFY_ENABLED=0`（等效 `notify.enabled=false`），全程不发通知（仪式硬门认其为合法降级，见 0.1bis 矩阵 / Phase 3.4）|
| `--reset-baseline` | 关 | 删除 baseline 文件后退出，下次任意 PRD 变化都触发；不续命 |
| `--reset-unattended` ★ | 关 | 清空 baseline `autopilot.unattended_confirmed` + `autopilot.unattended_confirmed_at` 诊断留痕（`baseline_edit.py del …`）。该字段不参与无人值守判定，本 flag 只用于清掉过期留痕便于排查 |

★ **核心理念**：循环交给外部调度（7×24 = `aidp_scheduler.py` 装的操作系统定时任务；交互式短期 = 会话内 `/loop`）。本命令专注「单轮工作」：配置补全 → baseline 检查 → 有变化跑全流程 / 无变化退出。浏览器实测 / 开发链路的 chrome 相关参数（`--skip-mcp-check` / `--reset-chrome-ip` / `--reset-credentials`）属 `/sprint-aiauto-test`；版本用 `--target <V>` 显式锁定。

★ **用户直接调用（无调度包装）的行为**：命令检测到非调度上下文 → 默认完成「配置补全 + 提示挂载方式」后**退出**，**不跑 Phase 2/3**（避免用户误以为单次直接调用就实现了 7×24）。被调度唤起的调用（`--no-loop` / `--unattended` / `/loop`）→ 正常走 baseline 检查 + Phase 2/3。

> ★ **例外（交互式全量执行语义，强制）**：用户**明确表达执行意图**——交互式给出"开发并测试 / 跑完后续流程 / 帮我把开发测试都做了 / 执行 V0.X 的开发测试 / 已规划完帮我自动执行"等明确意图（**或**带 `--once` / `--skip-dev` / `--target` 等执行 flag）→ **等价于 `--once` 全流程**，直接进 Phase 2/3 并跑完**所有强制仪式硬门**（见下方 Phase 3「⛔ 强制仪式不可精简硬门」），**绝不降级为"配置向导"停在向导态**、**绝不以"交互式 / 省时 / 避免打扰"为由跳过任何强制仪式**。仅当用户**无明确执行意图**（纯探路 / 只想看配置补全）才停在向导态。意图判定不确定时**按"有执行意图"从严处理**（宁可全跑，不可少做）。

> ⛔⛔ **顶层执行铁律 IRON-1 ~ IRON-10（清单 + 单一信源指针 · 与「强制仪式不可精简硬门」同级）**：以下 10 条顶层铁律的**完整细则**已下沉**`{{AIDP_HOME}}/flows/sprint-autopilot/invariants.md`**，每条在那里都有可定位的 `## IRON-N：<铁律名>` 小节——正文只留清单，进入 Phase 2/3 执行框架时按名遵守、按需 `Read` 该文件取细则。**★ 编号即 IRON-N（下方序号 N = `IRON-N`）**：命令 / flows / 各 Phase 里**只需写「适用 IRON-1 / IRON-3 / IRON-7」引用编号，不再各处重复展开完整论述**（同一条规则若在多处各写一遍完整论述，改一条要改多处、必然漂移；现全文唯一定义处 = invariants.md 的 `## IRON-N` 小节）；"见「XXX不变式」/「委派安全铁律」等"按名引用也一律解析到该文件对应小节。
> 1. **执行开始后绝不停下来问「继续/下一批」** — 有可执行工作就一路做完，非阻塞项记待办清单、本轮末统一汇报（唯一允许暂停：Phase 0 配置收集 / 真正硬阻塞走「失败处置」#4）。
> 2. **需求/意图上下文语义 + 入口产物仪式保证**（细则并入 `## IRON-4` 小节的②③项，本条不另设小节） — 经 autopilot 入口的任何工作（含 bugfix/优化增量）都必「铸 build + AI执行报告 + 发里程碑通知 + 收尾闸」；分类只影响"做什么工作"、不影响"是否产仪式产物"；禁"无仪式的裸交付"。
> 3. **阶段推进不变式** — Phase 达成完成判据即在【同一轮】进下一 Phase，禁"汇报/等确认/小结/先停一下"停下交还控制权；靠 baseline `run_state` 持久化断点续跑（权威仍是文件产物 + S0–S4 状态机 + 幂等标志）。
> 4. **入口级仪式不变式（六项保证，路径无关）** — ①不中途征询 ②auto commit+push 到部署分支 ③铸 build + 产 AI执行报告 ④发里程碑通知 ⑤委派/自触发 AI 测试产 AI测试报告 ⑥返回前【无条件】跑收尾 ceremony 闸；`full`/`incremental`/`test-only`/直接增量一律适用。
> 5. **推送分类与监听不变式（★ 作用域全命令，单一信源 = 约定 31.5）** — 每次 AIDP 代码 push 前先调用 `python3 {{AIDP_HOME}}/scripts/classify_push.py --root . --version "$VERSION" [--build "$BUILD"]` 并把完整结果写入当前 build（⛔ **别写成 `classify_commit_change.py`**：它只出分类、无 `--version/--build`、**不落盘**，`classify_push.py` 内部会调它）。无正式代码变更时仍校验 push 成功并写 `cicd_skipped=true`，不触发/监听远端 CICD、不跑就绪探针；正式代码变更或分类错误时，才确认「部署触发→轮询终态（失败重试≤3）→就绪探针→写 `last_deployed_at`」。并刷新顶层 `last_autopilot_head`。
> 6. **上下文管理策略（防单 tick 破 1M）** — `LOOP_UNATTENDED=1` 四管压上下文：①逐 tick 单 Sprint（★ 仅 `HAS_WAKE_SOURCE=1` 时生效；无唤醒源时靠②③④压，绝不用 yield 换上下文——那会停摆） ②子 Agent 隔离（重活留子 Agent、只回传 compact）③compact 读取（不整篇 Read 大产物）④**A3 Phase 承载**（重执行的 Phase 2/3 由子 Agent Read 分片执行，主 loop 只持 run_state + 每 Phase ≤20 行结论摘要；Phase 0/1 因交互/轻量留主循环）；四者仅无人值守生效 + 均有内联回退。
> 7. **委派安全铁律** — 子 Agent 不能 `AskUserQuestion`，故**只委派零交互纯执行段**；交互点全前置到 Phase 0 一次性收集 / 一次性 setup；交互式（`LOOP_UNATTENDED=0`）不委派、内联跑。
> 8. **委派职责矩阵** — 无人值守下 `/version` 规划 / 单 Sprint 开发 / `auto-test-runner` 测试模块 / 报告数据构造【必须】子 Agent 执行（非"优先/建议"）；主循环只做四件事（读写 baseline/run_state · 决定下一 Phase · 派发子 Agent · 发通知）；回传只许 compact 结构化结果。
> 9. **baseline 单一写入口不变式** — 两条 loop 并发写 `memory/.sprint-autopilot-baseline.json`，**一切写操作必须经 `{{AIDP_HOME}}/scripts/baseline_edit.py`**（`flock` + 锁内重读 + 原子替换）；裸 `jq … > tmp && mv` 只保证「不半截」、不保证「不丢对方字段」。
> 10. **缺陷复验闭环不因「没有下一 tick」中断**（IRON-10）— 「修复→重部署→铸新 build→复测」是自动仪式不是选项；交互式单次由本次调用在本轮内跑完（0.3.4bis 那个触发点是 `/loop` 语境，本轮早已跑过）；收尾门 3m 结构级兜底：报告 `defects[]` 有"待复验"却无后继 build 也未冻结 = FAIL。

---

## 阶段总览（命名约定）

本命令是**单一数字阶段流水线**，全程只用一套编号（0 → 1 → 2/3），避免多套命名混淆：

| 阶段 | 名称 | 归属 | 作用 |
|------|------|------|------|
| **Phase 0** | 前置条件检查 | 第一部分 准备 | 配置就绪：拉码 / 通知通道 / 版本扫描 / 决策一次性收集 / **AI 自动化开发测试就绪完整性收口（0.7，缺失即提示补充）** |
| **Phase 1** | PRD 变化检测 | 第一部分 准备 | baseline 监听判定，命中才进入执行。⛔ **其任一「无变化 / 停在配置向导 → 退出」路径，退出前必须先跑 `autopilot-ceremony-gate.py check --no-pipeline-reason "<依据>"`**（本页下方「产物缺失必须显式告知」段给的就是这条命令；invariants ③细则。分片 `phase-1.md` 的 1.5 段已内联该调用（不再靠跨文件回指），**执行体读到那里要退出时回本行取指令**）|
| **Phase 2** | 上版准发布 | 第二部分 执行 | `/version --no-tag` 归档（仅当存在待准发布的上版）|
| **Phase 3** | 下版全流程 | 第二部分 执行 | `/version` + `/sprint-batch`（仅当存在待开发的下版）|

> ⚠️ **命名约定**：文中带 `aiauto-test` / `/sprint-aiauto-test` 前缀的 `Phase N`（如 `aiauto-test Phase 1`、`/sprint-aiauto-test Phase 0.0.6`）指**测试命令自己的**阶段编号，与本命令的 Phase 0~3 是两套独立体系，勿混淆。本命令正文里**无前缀的 `Phase N` 一律指本命令阶段**。

---

# 第一部分：准备与检测（Phase 0 前置检查 + Phase 1 变化检测）

> 本部分全部属「执行前准备」——前置检查（Phase 0）与 PRD 变化检测（Phase 1）都只做配置就绪 + 监听判定；**只有 Phase 1 检测命中后才进入第二部分「执行主流程（Phase 2/3）」**。

## Phase 0：前置条件检查（缺一不可启动）

> ⛔ **Phase 0 前置硬门（exit-1 级铁律 — 任何入口 / 任何 `ENTRY_MODE` / 任何用户意图都不得绕过）**：在执行**任何** 开发 / 部署 / 测试 / **委派（invoke `/sprint-aiauto-test`）** 动作之前，**必须先完整跑完 Phase 0.0–0.7**；未跑完 → 不得进 Phase 1/2/3、也不得 invoke `/sprint-aiauto-test`。
>
> ⛔⛔ **详细步骤已外置、二次切分为 11 片、进入 Phase 0 的【第一动作】= 按需加载**：Phase 0 的完整 0.0–0.7 步骤已切成 **`{{AIDP_HOME}}/flows/sprint-autopilot/phase-0-1.md` … `phase-0-6.md` / `phase-0-6b.md` / `phase-0-6b2.md` / `phase-0-7.md` … `phase-0-9.md`**（每片 ≤20KB；⛔ `phase-0-6b.md` 承载 0.3.4bis 自愈复测与 **0.4 项目状态检查**、`phase-0-6b2.md` 承载 **0.3.4 选版 + 冻结跳过/解冻**〔`TARGET_VERSION` / `PRE_RELEASE_VERSION` 的唯一落盘处〕，漏 Read 即整步跳过）。**进入 Phase 0 后按子步进度依次 `Read` 对应分片**（哪些子步在哪片见下表「所在分片」列，从 `phase-0-1.md` 起）——下方骨架仅供"知道有哪几步 + 定位"，**权威判定与操作一律以对应 `phase-0-N.md` 为准，绝不凭本骨架或记忆略过任一子步骤**。

**Phase 0 子步骤骨架（详见各分片 `phase-0-N.md`）**：

| 子步骤 | 作用（一句话） | 所在分片 | 适用条件（P1-3 — 不满足则整片跳过、无需 Read）|
|---|---|---|---|
| **0.0.0** | 规范化无人值守信号 `LOOP_UNATTENDED`（所有无人值守分支的统一开关，**必须最先派生**）| `phase-0-1.md` | 总是 |
| **0.0.0bis / 0.0.0ter** | 上一轮遗留自检（`autopilot.last_handback`）+ **收尾护栏 fail-open 台账自检**（`memory/.aidp/stop-guard-skips.jsonl`：Stop hook「本可介入却放行」的留痕；放行 ≠ 收口）| `phase-0-1.md` | 总是 |
| **0.0** | 通道与配置就绪（notify 渠道 / 远程 chrome 配置 —— ★ 最前，任何可能 exit 的门之前必跑）| `phase-0-1.md`（Step 0–1）→ `phase-0-2.md`（Step 2–3）→ `phase-0-3.md`（Step 5）| 总是 |
| **0.1** | 拉取远端全部分支 + 当前分支最新代码 + 脏树决策门 | `phase-0-3.md` | 总是 |
| **0.1bis** | 通知机制：里程碑通知节点表（单一信源）| `phase-0-4.md`（渠道选择/回落/公共字段）+ `phase-0-5.md`（通知骨架/应发通知集矩阵/#F·#3·#1d 模板）| **发通知前必读**（渠道选择 + 失败回落判据）；**仅** `NOTIFY_ENABLED=0`（`notify.enabled=false`）/ `--no-notify` 时整片跳过。⛔ 渠道可用 = 更要读，别读反 |
| **0.2** | AI 自动化测试由独立命令 `/sprint-aiauto-test` 承担（归属声明）| `phase-0-6.md` | 总是 |
| **0.3** | PRD root 解析 + 版本扫描 + 状态机识别（下列 0.3.1–0.3.6 的合称）| `phase-0-6.md` + `phase-0-6b2.md` | 总是 |
| **0.3.1** | PRD root 解析（`PRD_ROOT`）| `phase-0-6.md` | 总是 |
| **0.3.2** | 扫描 `V*.*.*` 子目录（仅 SemVer 命名）| `phase-0-6.md` | 总是 |
| **0.3.3** | 解析每个版本的状态（状态机 S1–S4）| `phase-0-6.md` | 总是 |
| **0.3.5** | 决策矩阵（据状态对决定本轮做什么）| `phase-0-6.md` | 总是 |
| **0.3.6** | 发 #0 版本对识别通知 | `phase-0-6.md` | `NOTIFY_ENABLED=1` |
| **0.3.4** | ★ 识别「最近的一对」选版 + 熔断冻结跳过 / 解冻（`TARGET_VERSION` / `PRE_RELEASE_VERSION` 唯一落盘处，后续全 Phase 依赖）| `phase-0-6b2.md` | 总是 |
| **0.3.4bis** | ★ 测试失败自动修复复测闭环 **step 1（三分支裁定）+ step 2（派修复→重部署→铸新 build 复测）** —— 消费测试链路写的 `auto_fixable_pending` | `phase-0-6b.md` | 总是（`auto_fixable_pending` 为空即三分支落 ③、照常走 Phase 1/2/3）|
| **0.4** | 项目状态检查 | `phase-0-6b.md` | 总是 |
| **0.5** | PRD 头部决策预声明（`--full-auto` 默认强制）| `phase-0-7.md` | `--full-auto` / `LOOP_UNATTENDED=1`（交互式可现场问、略读）|
| **0.5bis** | ★ 询问收敛总则（D5 适用面 + D4 最高口径 + D3 逐门默认表 + 仍需人工的两类白名单）| `phase-0-7.md` | **总是**（⛔ 不再以 `LOOP_UNATTENDED=1` 为触发条件：D5 明确白名单与逐门默认对**交互式单次同样生效**，两种模式只在「命中白名单后怎么处置」上不同。此前该行的门控恰好让交互式单次读不到这份唯一信源）|
| **0.5.5** | 测试方案 AI 自动化预检（chrome-devtools-mcp 测试信息 + 安装预检）| `phase-0-8.md` | `IS_FRONTEND_WEB && test_strategy=chrome-mcp && deployment.mode!=none`（纯后端 / static-only / mode=none 整片跳过）|
| **0.6** | ★ 铁律：字段缺失统一在 Phase 0 收集，**禁止执行主流程（Phase 2/3）中途阻塞** | `phase-0-8.md` | 总是 |
| **0.6bis** | ★ 用例前置资源对账门（用例册声明的前置账号/数据 ↔ 约定 38 产物 `01_测试环境与账号.md`；委派 `check_testdata_prereq.py`）| `phase-0-9.md` | 总是（full 模式必判 `no-casebook`，由 Phase 3.1bis 补账）|
| **0.7** | ★ AI 自动化开发测试流程就绪完整性总表（Phase 0 收口门 — 缺失即提示补充）| `phase-0-9.md` | 总是 |

> 收口：0.7 收口门 + 前置硬门均过 → 进入 Phase 1。**执行前务必已按子步进度 Read 对应 `phase-0-N.md` 并逐项完成，不能只看本表。**

## Phase 1：PRD 变化检测（监听核心 — 仍属准备阶段）

> ⛔⛔ **详细步骤已外置、进入 Phase 1 的【第一动作】= 按需加载**：Phase 1 的完整 1.1–1.5（含 1.3bis / 1.3ter）步骤在 **`{{AIDP_HOME}}/flows/sprint-autopilot/phase-1.md`**（约 200 行）。**进入 Phase 1 时第一件事就是 `Read` 该文件、逐项执行**——下方骨架仅供定位，**权威判定一律以 `phase-1.md` 为准**。

**Phase 1 子步骤骨架（详见 `phase-1.md`）**：

| 子步骤 | 作用（一句话） |
|---|---|
| **1.1** | Baseline 文件位置（★ 项目级多版本字典）|
| **1.2** | 变化检测逻辑（按版本 per-key 检测）|
| **1.3** | 四种触发模式 + 上下文感知（含 `IS_LOOP_CONTEXT` 复用 0.0.0 派生）|
| **1.3bis** | ★ 续跑短路门（逐 tick 单 Sprint 不被 `no-change` 判死的唯一落点；⛔ 漏跑 = 多 Sprint 版本永远只跑第一个）|
| **1.3ter** | ★ 通用 stuck 熔断（先于 1.3bis 跑）|
| **1.4** | 检测命中后（进入第二部分执行主流程 Phase 2/3）|
| **1.5** | 用户直接调用的退出引导（默认模式，非 /loop 不跑 Phase 2/3）|

> 收口：Phase 1 检测命中 → 进入第二部分「执行主流程（Phase 2/3）」。**未命中时按调用上下文分流（务必分清，两者行为不同）**：
> - **`LOOP_UNATTENDED=1`（`/loop` 守护 / `--no-loop` / `--unattended`）**：`SHOULD_RUN=0` 且 `PRE_RELEASE_VERSION` 为 null → **静默立即退出本 tick**，**不打印 1.5 配置向导**（每 tick 刷一屏向导纯噪音）；`PRE_RELEASE_VERSION` 非 null → 仍进 Phase 2 做上版准发布。
> - **交互式默认模式（无 flag + 无 `/loop` 上下文）**：才走 **1.5 退出引导**（打印配置就绪清单 + 提示挂 `/loop`）。
>
> **执行前务必已 Read `phase-1.md`（判定以其 1.3 模式表为准）。**

# 第二部分：执行主流程（Phase 2/3）

> 仅在第一部分 Phase 1 检测命中后进入；按 Phase 0.3.5 决策矩阵决定跑 Phase 2（上版准发布）/ Phase 3（下版全流程）/ 两者。

## Phase 2：上版准发布（仅当 PRE_RELEASE_VERSION 非 null）

Git 模式跑 `/version <PRE_RELEASE_VERSION> --no-tag` 准发布归档；无 Git 模式只核验 SQL / 文档 / memory 本地归档（未发布）。两路的成功依据均以 `phase-2.md` 为准。

> ⛔ **准发布前置双门（不可绕过的【跳过门】）**：S2「所有 Sprint 已关闭」≠「可准发布」——每 tick 重入本 Phase 时先过 **0a 部署就绪**（本应部署却 `last_deployed_at` 空 = 部署未完成/就绪探针从未通过 → 暂缓 + `prerelease_deploy_block_streak` 熔断/`needs_human` 冻结）+ **0b 测试收敛**（本 build 浏览器测试已收敛；未收敛按测试链路是否**真能干活**分流——存活判据 = 新鲜心跳 **且** 顶层 `aiauto_blocked_reason` 为空——存活走 `prerelease_test_hold_streak` 暂缓/告警/冻结，不存活走 `test_loop_missing_streak` 熔断）两门；任一未过（`PRERELEASE_HOLD=1`）→ **跳过 Phase 2 的 1~4 步**、不写 `internal_released_at`、不把版本移出 aiauto-test 候选，**但不 `exit`**（同 tick 的 Phase 3 是另一个版本、须照常继续），强制性靠「streak 记账 + 达阈 #4/冻结 + `run-state` 写盘」三件结构化动作保证。
>
> ⛔⛔ **详细步骤已外置、进入 Phase 2 的【第一动作】= 按需加载**：Phase 2 的完整前置双门 + 1–4 步在 **`{{AIDP_HOME}}/flows/sprint-autopilot/phase-2.md`**（单片、~10KB）。**进入 Phase 2 时第一件事就是用 `Read` 工具打开该文件、逐项执行**——下方骨架仅供"知道有哪几步 + 定位"，**权威判定一律以 `phase-2.md` 为准，绝不凭本骨架或记忆略过任一子步骤/硬门**。

**Phase 2 子步骤骨架（详见 `phase-2.md` —— 单片，不切分）**：

| 子步骤 | 作用（一句话） | 所在分片 |
|---|---|---|
| **0（前置双门）** | 0a 部署就绪校验 + 0b 测试收敛校验（任一未过 → 跳过 1~4 步、本 tick 暂缓准发布，含 `prerelease_deploy_block_streak` / `prerelease_test_hold_streak` / `test_loop_missing_streak` 三条熔断 → `needs_human` 冻结）| `phase-2.md` |
| **1** | 里程碑通知 #pre-start（准发布启动，见 0.1bis）| `phase-2.md` |
| **2** | Git 走 `/version --no-tag --unattended`；无 Git 核验本地归档；逐项核验后写本 tick `PRERELEASE_ARCHIVE_OK` | `phase-2.md` |
| **3** | 仅门禁、未让位、归档核验均通过时写 `internal_released_at` 内部游标（无 Git 不代表已发布）| `phase-2.md` |
| **4** | 里程碑通知 #pre-done（准发布完成，提示手动补打 tag）| `phase-2.md` |
| **5** | ★ 分片收尾必写 `run_state`（`baseline_edit.py run-state`，见 `invariants.md` 阶段推进不变式）| `phase-2.md` |

> 收口：双门通过 + 1~4 步完成 → 按 Phase 0.3.5 决策矩阵决定是否继续 Phase 3；任一门未过 → 本 tick 结束 Phase 2。**执行前务必已 Read `phase-2.md` 并按其逐项完成，不能只看本表。**

## Phase 3：下版全流程（仅当 TARGET_VERSION 非 null）

> ⛔ **Phase 3 三条顶层铁律（详情见 flow，此处只留一句提醒）**：① **强制仪式不可精简**——铸 build/AI执行报告/发通知/终审在任何 `ENTRY_MODE` 下均强制，唯一合法跳过 = 技术性不可用（由 `autopilot-ceremony-gate.py check` `exit 1` 校验）；② **非法跳过借口**（交互式/省时/避免打扰/单次不必全套…）一律判违规；③ **报告不可变**——finalize 后冻结、结论变化一律铸新 build，禁回写旧 build。
>
> ⛔⛔ **详细步骤已外置、二次切分为 13 片、进入 Phase 3 的【第一动作】= 按需加载**：Phase 3 的完整 3.0–3.4 步骤已切成 **`{{AIDP_HOME}}/flows/sprint-autopilot/phase-3-1.md` … `phase-3-9.md` / `phase-3-9b.md`**（含二次切分的 `phase-3-3b` / `phase-3-5b` / `phase-3-6b` / `phase-3-9b`）（每片 ≤20KB）。**进入 Phase 3 后按子步进度依次 `Read` 对应分片**（从 `phase-3-1.md`〔顶层铁律 + 入口硬门〕起，哪些子步在哪片见下表「所在分片」列）——下方骨架仅供定位，**权威判定一律以对应 `phase-3-N.md` 为准，绝不凭骨架或记忆略过任一子步骤/硬门**。

**Phase 3 子步骤骨架（详见各分片 `phase-3-N.md`）**：

| 子步骤 | 作用（一句话） | 所在分片 | 适用条件（P1-3）|
|---|---|---|---|
| **（顶层铁律 + 入口硬门）** | 强制仪式不可精简 / 报告不可变 / 进入 Phase 3 第一动作硬门 | `phase-3-1.md` | 总是 |
| **3.0** | 入口路由 + AI执行报告前置硬门（P0-0 流程裁剪唯一授权原则；`test-only` 6 步骨架；incremental 路由）| `phase-3-2.md` | 总是 |
| **3.1.0** | 跳过规划门：`PLANNING_DONE`（**六类**规划产物齐全）+ P0-1 incremental 硬判据②（规划齐）③（无未关闭 Sprint）+ P0-0 两个合法来源 + 裁定回写 baseline | `phase-3-3b.md` | `ENTRY_MODE!=test-only`（**先于 3.1 跑**）|
| **3.1** | 版本规划（已规划则跳过片内 `/version`）+ 启动通知 + 里程碑通知 #1/#1b | `phase-3-3.md` | `ENTRY_MODE!=test-only`（⛔ **不得再加 `PLANNING_DONE=0`**：该值由 3.1.0 计算，拿它当读片前置是循环依赖 —— 整片跳过会连 step 3「解析 Sprint 总数 N + 发 #1b 规划完成通知」一并丢失。**已规划时跳过的是片内 step 2 的 `/version`，不是整片**）|
| **3.1bis** | ★ 用例前置资源对账【补账】（`/version` 刚产出用例册 → 补跑 0.6bis 那道门；**full 模式下这是唯一有效落点**）| `phase-3-3.md` | 本轮跑过 `/version` |
| **3.1.5** | 铸 build 号 + 写本 build 执行数据（计划态）| `phase-3-4.md` | 总是（含 test-only：铸 build 是强制仪式）|
| **3.2** | 批量 Sprint 执行（里程碑通知 #1c 开发开始 / #2 循环内 / #1d 部署完成；`incremental` 改走增量路径）| `phase-3-5.md`（步骤 0–1 + 出口）+ `phase-3-5b.md`（步骤 2–4：执行·推送·部署动作·#2）| `ENTRY_MODE!=test-only`（test-only 跳开发循环）|
| **3.2.1** | CICD 编排（平台 = `cicd.provider`，默认 GitHub Actions；`cicd_watch.py` 监听 + `--mode trigger` / `--mode retry` 触发重试；运行绑定不变式；**CICD 失败第一动作恒为重试、非自查代码**）+ 部署就绪探针 | `phase-3-6.md`（Step A0/A/B）+ `phase-3-6b.md`（Step C + 出口）（Step A0/A/B/C 解析·防重复·触发·监控重试）+ `phase-3-7.md`（Step D 就绪探针 + 超时熔断）| `deployment.mode=cloud` 且已接入 CICD（`memory/aidp-config.yaml` 的 `cicd.provider` ≠ `none` 且 `cicd.pipelines` 已配；`mode=local/none` / 未接入则跳本片、走 Phase 3.2 轻量分支）|
| **3.3** | 终审（version-auditor，无单独通知、并入 3.4）| `phase-3-8.md` | 总是（强制仪式，任何入口不豁免）|
| **3.4** | 完成通知 + 收尾（收尾门 + 双链路收口 P0-4）| `phase-3-8.md`（Step 1–3 finalize/emit-report/#3 通知）+ `phase-3-9.md`（Step 4+ 根因分诊 + ceremony 闸）+ `phase-3-9b.md`（内联校验 ①~④ + 收尾动作）| 总是 |

> 收口：3.4 完成 → 命令退出（不自动 merge/tag/推 master，destructive 动作留人工）。**执行前务必已按子步进度 Read 对应 `phase-3-N.md` 并逐项完成。**

## 命令收尾硬门（★ 入口级 ceremony 闸 — 无条件、结构级，任何入口 / 任何工作方式都跑）

> ⛔⛔ **本节是 `/sprint-autopilot` 的固定收尾动作，不属于任何可被跳过的 Phase**——**无论执行体是逐字走完 Phase 2/3 编号步骤，还是"手动"完成开发/测试（直接调 `/version` / 直接改代码 / 直接驱动 `chrome-devtools-cli`），只要本轮实际发生了开发或测试动作，命令返回【之前】都必须无条件跑完本节**。这道闸把「强制仪式」从"自律级（藏在 Phase 3.4 内、执行体不走那步就漏）"升级为"结构级（入口无条件兜底）"。**执行体不得以"我手动干完了 / 交互式 / 大提示词 / 已精简 / 省时"为由跳过本节。**

> ★ **缺陷处置的判据在别处（单一信源指针，约定 21 不复述）**：收尾时若手里还有本轮发现的缺陷，
> **归类判据 = `/sprint-bugfix`「缺陷处置默认决策纪律」**（先问「不做这个修复，当前行为是不是
> 错的？」是/拿不准 → 直接修），**处置动作 = 本文件「测试失败自动修复复测闭环」**（含 P0-4 交互
> 单次自跑）。⛔ 不得在 autopilot 上下文里因"闭环判据不匹配"就地发明处置方式、更不得弹窗问用户
> 修不修 —— 实测事故正是执行体在此处没有跳去查那条纪律。收尾门 3j 结构级兜底。

**触发判据**：本轮 `/sprint-autopilot` 入口下发生了任一「实际工作」——有 code 改动（本轮有源码提交 / 工作树有源码改动）**或** 有测试执行（驱动过浏览器 / 委派过 `/sprint-aiauto-test`）。纯配置向导态 / Phase 1 无变化退出 / S3–S4 无增量（本就不产仪式产物）→ **不跑本闸，但仍必须跑结构级"未进流水线"告警**：`python3 {{AIDP_HOME}}/scripts/autopilot-ceremony-gate.py check --version <版本> --no-pipeline-reason "<依据>"`（见 Phase 0 前置「产物缺失必须显式告知」+ 入口级仪式不变式 ③细则），打印告警 + 应产=无说明后正常退出——**绝不静默退出让用户以为产物会自动出现**。
> ★ **豁免：逐 tick 单 Sprint 的【中间】yield-tick**（`HAS_WAKE_SOURCE=1` 默认粒度下 `run_state.next_sprint != "done"`——还有 Sprint 未关闭、本 tick 只推进了一个中间 Sprint 并 `UNATTENDED_YIELD` 退出、**未部署、未委派测试**）**同样豁免本闸**：它是跨 tick 续跑的**中间态、非本轮完整交付**（虽有 Sprint 提交了代码触发「有 code 改动」，但部署/测试/finalize 尚未发生）。此时跑 `--stage final` 会因交付台账未产而误判缺失 → step③ 触发**过早**的 `emit-report --kind exec`+写交付台账（dev 尚未完成）churn。仪式产物在**最后一个 Sprint 关闭 → 部署 → 触发测试的那个 tick**（`next_sprint == "done"`）统一收口。故中间 yield-tick **只打印一行进度（`⏭️ Sprint-NNN 关闭，下一 tick 续 Sprint-<next>`）即退、不跑本闸**（与「Phase 1 无变化退出」同类豁免）；build 骨架已在 Phase 3.1.5 铸出、不受影响。
>
> ⛔⛔ **反向硬断言：`HAS_WAKE_SOURCE=0` 时【不存在】合法的中间 yield-tick**——上面这条豁免的前提是"下一 tick 会来接"。
>
> **★ 已升级为结构级机器门（与「产物齐全」同级），⛔ 命令返回前【必跑】**：
> ```bash
> python3 {{AIDP_HOME}}/scripts/autopilot-ceremony-gate.py handback-check --version "$V" --record
> ```
> **自动触发点 = `{{AIDP_HOME}}/hooks/autopilot-stop-guard.py`**（Stop hook 在收尾门通过后再跑一次
> `handback-check`，非零即 `exit 2` 阻止结束）。⚠️ 本条曾长期**只有散文、没有任何自动触发点**——
> ceremony-gate 的 `check` 刻意不含 HANDBACK（时序死结，见其注释），而 `settings.json` 与 hooks
> 里当时对 `handback-check` 零命中，于是一条自称「结构级机器门」的断言，实际强度仍是执行体自律，
> 与它要修复的那个事故同层级。**改动本行前先确认 Stop hook 那一段还在。**
> `exit 1` = 契约违背，**不得就此收工**。判据（两个值本就落盘，纯确定性）：`autopilot.wake_source_this_tick == 0` **且** `run_state.next_phase` 或 `run_state.next_sprint` **任一**非空且 ≠ `done`。
> ⚠️ **两个都要看**：本断言早先只写 `next_sprint != "done"`，而真实事故停在 Phase 3.1→3.2 边界——那时 `next_phase="3.2-dev"` 而 `next_sprint` 尚未进入循环，旧判据恰好判不出来。
>
> **★ 判据只看客观状态、不看收尾话术**：文档一度点名禁"如需无人值守请挂 `/loop`"这一类**具体措辞**，而真实失效用的是**"要我继续进入开发阶段吗 / 你想先看看规划产物吗"**这种征询式变体——措辞完全不同、实质一样，于是没被自己的禁令拦住。**枚举话术堵不住，判定式才堵得住**：命令返回时 `run_state` 是否停在非终态、有没有人会来接，与话术怎么写无关。
>
> 违背时**⛔ 绝不允许就此收工**——必须 ① 回到该 Phase 把剩余流程**在本轮内**跑完（正解），② 确实跑不动（熔断 / `needs_human` / 阻塞）才走「失败处置」显式告警 + `#4` 里程碑通知把**"还剩哪些 Phase/Sprint 未做、为什么停"**讲清楚。挂 loop 的引导只用于**测试链路第二条 loop**，不得用来解释开发链路没跑完（把命令自己该干的活儿说成用户配置缺失；真实事故见 `flows/sprint-autopilot/rationale.md`）。

**收尾动作（按序，缺失绝不静默）**：
1. **① 显式回执（通知渠道就绪态 —— 让"配了但没用"与"确实降级"可区分可追溯）**：打印明确回执：
   - `✅ 通知渠道就绪 channels=<..>` 或 `⚠️ 降级：未配置任何通知渠道 / NOTIFY_ENABLED=0，本轮不发通知`；
   （避免像下游反馈那样"通道明明配好却整程零推送、也无任何告警"。）
2. **② 无条件 ceremony 校验**：跑 `python3 {{AIDP_HOME}}/scripts/autopilot-ceremony-gate.py check --stage <skeleton|final>`——逐项校 **build 号是否铸造 / `docs/reports/{version}/AI执行报告/` SPA 是否产出并注册两页 / 应发通知台账是否登记**。**这道 check 不因"没走进 Phase 3.4"而免跑**——它就是命令收尾的固定动作。
   > ⛔ **`--stage` 选择必须证据化，绝不凭"我以为已委派"选 skeleton（本次反馈根因）**：`skeleton` 是"把 #F/#3 与交付台账的校验延后交给一条**真实存在且在跑**的测试链路"，**唯一合法用它的场景 = `/loop` 无人值守（`LOOP_UNATTENDED=1`）且本 build 已落 `aiauto_delegated_at`（确已 invoke，见子流程 R 委派证据标记）**——此时第二条 `/loop 5m /sprint-aiauto-test --unattended` 会异步跑 `--stage final` 收口。**其余一律用 `final`**：静态-only（`deployment.mode=none`）、**交互式单次调用（`LOOP_UNATTENDED=0`，无第二条 loop 兜底）**、以及**任何"本 build 无 `aiauto_delegated_at` 委派证据"的浏览器测试轮**——因为此时 autopilot 就是 build 关闭方，收尾必须自己跑 `final`（它会连带校 AI测试报告 SPA / #F 通知 / 交付台账，把"内联驱动 chrome 却从未真委派、测试链路 final 门永不执行"的真空当场判 `exit 1`）。判据一句话：**「有真实测试链路会替我跑 final」才 skeleton，否则 final**——绝不因 test-only / 交互单次而降级成永不校验的 skeleton。
3. **③ 缺失即补产、补不齐不静默收尾**：ceremony check `exit 1`（有缺失）→ **逐项打印「缺什么 + 为什么缺 + 补产命令」**（build 缺 → `emit-report.py --kind exec` 铸造 + 写骨架；SPA 缺 → 补 `emit-report.py`；通知台账缺（渠道可用）→ 补发对应里程碑通知 + `autopilot-ceremony-gate.py record-card` 登记）→ **就地补产后复跑 check 直到通过**；结构性不可自愈（脚本/模板缺失）→ 归口「失败处置」熔断（同 Phase 3.4 step4 兜底），**绝不静默 exit 让用户误以为产物已生成**。
4. **④ 双链路收口（P0-4：交互单次【自跑】AI 测试 / 无人值守提醒挂第二条 loop）**：本轮有开发/部署产出、本版需浏览器测试（`deployment.mode != none` 且未 `--skip-deploy`、**未带 `--skip-aiauto-test`**）却**检测不到测试链路已真正承接**——判据 = baseline 顶层 `aiauto_test_heartbeat_at` 缺失/陈旧（无近 30min 心跳）**且** 本 build 未落 `aiauto_delegated_at`（子流程 R 委派证据标记未写 = 从未真 invoke 过测试链路）——时，**按上下文分流收口**：
   > ⛔⛔ **本收口【必须覆盖 `test-only`】，绝不再以"test-only 已在子流程 R 委派浏览器实测"为由排除它（本次反馈根因）**：那句是**假设**不是**证据**——autopilot 完全可能在自身上下文里内联驱动 chrome-devtools-cli 跑完测试而**从未真正 invoke `/sprint-aiauto-test`**（`aiauto_delegated_at` 就没写），此时既无测试链路 final 门、也无 #F/#3，却被旧排除条件放行成"静默全绿"。判据改用**客观委派证据（`aiauto_delegated_at` + 心跳）**，`full` / `incremental` / **`test-only` 一视同仁**：只要"该有浏览器测试、却查不到真委派证据"就触发本收口。
   - **★ 无唤醒源的单次调用（`HAS_WAKE_SOURCE=0`——⛔ 判据是它、**不是** `LOOP_UNATTENDED=0`：`--once --unattended` 两者取值相反，按后者判会让这一档既不内联跑测试、又没有下一 tick 和第二条 loop，当场破掉「一次下达全程跑完」；权威实现见 `phase-3-9.md`）→ autopilot 自己 invoke 一次 `/sprint-aiauto-test --once --unattended` 跑浏览器实测**（Phase 0 full 模式已收集 chrome 配置；这是 P0-4 修复"交互单次浏览器测试 100% 缺席"的闭环——命令自我描述含测试、用户预期的"全链路"就该含测试，不能靠"连续 3 tick 熔断"这种单次永远累积不到的兜底）。**invoke 时按子流程 R 委派证据标记落 `aiauto_delegated_at`**；跑完由 `/sprint-aiauto-test` 产 AI测试报告 + #F/#3 + finalize AI执行报告 + 跑 `--stage final` 收口。**★ 若 chrome 确实不可用/自调用未能产出 #F**（best-effort 失败）→ **不静默放行**：autopilot 收尾自跑一次 `--stage final`（它会因 AI测试报告 SPA / #F 缺失判 `exit 1`）→ 走 ③ 补产逻辑逐项报「缺 #F/#3 通知台账 + AI测试报告」，绝不带缺失全绿收尾（对齐验收标准 1）。chrome-devtools-mcp 不可用/未就绪时它自身 Phase 0.1.5 A0 优雅降级/打印引导，autopilot **不硬失败**（best-effort），但**缺失事实必须经 `--stage final` 显式暴露**。**唯一跳过 = 用户显式 `--skip-aiauto-test`**（P0-0 唯一授权原则）。
   - **有唤醒源（`HAS_WAKE_SOURCE=1`，即操作系统调度 / `/loop` 会再叫醒）→ 不内联跑**（浏览器实测归测试链路（`aidp_scheduler.py` 装的测试链路定时任务，或会话内 `/loop 5m /sprint-aiauto-test --unattended`）异步承担，避免与其重复触发）；仅当检测不到其心跳 → **收尾强提示**：`⚠️ AI测试报告 + 测试通知(#D/#R/#F) 由 /sprint-aiauto-test 产，测试链路未运行 → 测试半环产物缺失；请用 python3 {{AIDP_HOME}}/scripts/aidp_scheduler.py install 装齐两条链路（或会话内并挂 /loop 5m /sprint-aiauto-test --unattended）`。把"测试报告为何没有"讲清楚，而非静默缺失。
5. **⑤ 产物清单收尾打印**：无论过没过，收尾打印本轮**应产 vs 实产**的仪式产物逐项状态（build 号 / AI执行报告 HTML+注册 / 报告本地路径 / 各里程碑通知 / 测试报告归属），缺失项标原因 + 补产命令，**禁止静默收尾**。

> **★ 与 Phase 3.4 step 4 的关系**：Phase 3.4 step 4 是"走到那一步时"的门；本节是"无论走没走到那一步、命令返回前"的**入口级兜底门**。二者用同一个幂等 `autopilot-ceremony-gate.py check`——走过 Phase 3.4 已过门 → 本节复校即刻通过、零额外成本；没走到（手动完成开发/测试）→ 本节是唯一拦截点，把漏产的仪式产物在收尾补齐。这正是下游反馈「强制性只是自律级、不是结构级」的结构级修复。

## 测试失败自动修复复测闭环（item 3 — 与报告不可变铁律配套）

> 目的：测试链路 `#F` 判定不通过时，**开发链路自动闭环修复 + 铸新 build 复测**，不再依赖运维手动挂第二条 bugfix loop、也不回写旧 build 报告（旧 build 已冻结，见「报告不可变铁律」）。**触发时机 = autopilot 每 tick 在 Phase 0.3.4 选到"当前开发版本"后、进 Phase 3 前，先读 baseline 测试信号**：
>
> ⛔ **本闭环是【默认恒开的自动仪式】、绝不作为选项抛给用户（本次反馈铁律，与「铸新 build 出复测报告绝不作为问句」同源）**：只要用户发起了一次 `/sprint-autopilot`（含只测某个功能模块的 test-only 单次调用），"测出可自动修复缺陷 → 自动 `/sprint-bugfix` 修复 → 重部署 → 铸新 build → 复测，最多 3 轮仍不收敛才转人工"就是其**必然内置行为**，在 `full` / `test-only` / `incremental` 三模式下**一律恒开**。**严禁**在任何 `AskUserQuestion` 里把它拆成一个可选维度，**更严禁**把不含自动修复的变体标成"推荐"。用户在本命令里的决策点只有两个：① 是否发起本轮 `/sprint-autopilot` ② （交互式且裁剪意图不明时）开发范围 full / test-only；**"修不修、复测几轮"从来不是选项**。
>
> ⛔⛔ **判定式禁令（★ 判据看【选项】，不看【问法】——本条取代旧的举例式列举）**：
> 凡 `AskUserQuestion` 的**选项集合**中出现下列任一项者，**一律违规**，与问题措辞无关：
>
> | 违规选项（含同义改写） |
> |---|
> | 不修 / 暂不修 / 先不修 |
> | 延后修 / 下版修 / 登记到下个版本 / 记入 backlog 后续处理 |
> | 只修不复测 / 修完不铸新 build |
> | 「是否自动修复」「是否复测」这类把闭环本身作为开关的维度 |
>
> **Why 是判定式而非措辞清单**：列举具体措辞（「是否自动修复复测」「部署+测试 vs
> 部署+测试+自动修复」）换个问法就绕过去了 —— 实际项目中执行体问的是「**这条缺陷
> 怎么处置**：① 现在修+复测 ② 登记下版修 ③ 只修不复测」，措辞与列举项都不同、实质完全一样，
> 执行体因此自认为没踩禁令。**枚举措辞永远堵不住换措辞**；只有"看选项集合"才是可判定的。
> ⛔ 同样违规的还有：把上述任一项**藏进"其他/自定义"的引导语**，或以「工作量较大 / 稳妥起见」
> 为由弹出的范围·进度确认门（与 `/sprint-batch`「零询问连跑铁律」catch-all 同源）。
>
> ⛔ **严重度不改变"修不修"（补"无表可查"的真空）**：面对混合严重度的缺陷集（如
> 1×P1 + 2×P2 + 1×P3）**不存在"按等级决定修不修"的映射表**——**严重度只影响【顺序与紧急度】，
> 绝不影响【是否修复】**。每条缺陷的归类判据是唯一的那一条：**`/sprint-bugfix`「缺陷处置默认
> 决策纪律」——先问「不做这个修复，当前行为是不是错的？」是（含拿不准）→ 可自动修复类、直接修**；
> 只有命中该纪律"必须问"两行（口径/单位/默认值需产品定义、涉及版本号/tag/对外承诺）才归需人工
> 确认类，记 `pending_clarifications[]` 且**不阻塞本轮**。**⛔ 绝不允许**引入"P2 可不铸新 build /
> P3 登记后不处理"这类分级豁免——那等于给"不修"发通行证，正是本铁律要堵的东西。

> ⛔⛔ **IRON-10：交互式单次调用【由本次调用自身跑完闭环】，不得以"没有下一 tick"为由交还用户**
> （与 P0-4「交互单次自跑 AI 测试」同构：两者补的是同一档——交互单次既没有第二条 loop、
> 也没有下一 tick，凡挂在那两者身上的自动仪式都必须由本次调用在本轮内跑完）：
> 本闭环的触发点写的是"每 tick 在 Phase 0.3.4 选到当前开发版本后、进 Phase 3 前读 baseline
> 测试信号"——那是 `/loop` 语境。**交互式单次调用（`LOOP_UNATTENDED=0`）跑完一轮就结束、根本
> 没有"下一 tick"**，闭环无处挂载。故规定：**交互式单次调用在本轮测试产出【可自动修复类】缺陷时，
> 由本次调用【在本轮内】接着完成「修复 → 重部署 → 铸新 build → 复测」**（`--once` 亦同），
> 上限仍是 `retest_auto_cap` 轮、达上限才冻结转人工。**⛔ 绝不允许**以"闭环挂在 tick 边界 /
> 本次调用已收尾"为由把缺陷连同处置决定一起退还用户 —— 那正是实测事故的成因（收尾门 PASS +
> 弹窗问"这条 P1 缺陷怎么处置"）。**完整细则见 `invariants.md` 的 `## IRON-10`（单一信源）**；结构级兜底 = 收尾门 **3m「缺陷复验闭环」**（3j 只读 `auto_fixable_pending` 布尔量，而闭环 step 2「先记账再动手」一开始就把它置 false，"已修复但从未复验"在 3j 眼里完全干净——下游实测正是这么 PASS 的）。

1. **判定信号（读 baseline，不自己跑浏览器）→ 显式三分支裁定（不留 else 歧义）**：读 `versions.{V}.auto_fixable_pending` / `needs_human` / `auto_retest_streak` / `retest_auto_cap`（默认 3）后**按序三选一**，**严禁把"达上限该冻结"混进"否则照常走 Phase 3"**：
   - **① `auto_fixable_pending==true` 且 `needs_human!=true` 且 `auto_retest_streak >= retest_auto_cap`（已做满 3 轮仍有可修复缺陷）→ 执行 step 3 冻结转人工**（⛔ 不得送进正常 Phase 3 开发流——否则既不转人工、又会重部署刷新 `last_deployed_at` 干扰测试链路判据）。
   - **② `auto_fixable_pending==true` 且 `needs_human!=true` 且 `auto_retest_streak < retest_auto_cap` → 进入 step 2 自动修复闭环**（★ `auto_retest_streak` 是**可重置**计数，每派一轮 +1、检测到人工修复即归零——即"每个人工介入周期最多自动跑 3 轮 build"，用累积不重置的 `builds[].retest_round` 会永久达顶、无法在人工修复后重新授予配额，故上限专用 `auto_retest_streak`）。
   - **③ 其余（无 `auto_fixable_pending` / 已 `needs_human` 冻结）→ 照常走 Phase 3**（无 pending 即正常开发/准发布；已冻结版本由 Phase 0.3.4 处理，含 step 3bis 的 `retest-cap` 解冻检测）。
2. **自动修复 → 重部署 → 铸新 build → 复测**（一个 tick 内串起，全部走既有机制、不新造流程）：
   - **修复**：`ENTRY_MODE=incremental` 走 Phase 3.2 增量分支，经 `/sprint-bugfix` 拾取本版「问题汇总清单」里的 `R-`/`C-` 缺陷（aiauto-test 已回写）批量修复；**只修可自动修复类**，`pending_clarifications[]`（需人工确认类）**不碰**（等用户裁决）。
   - **★ 重部署攒批（P1-7 — 一轮测试发现的多缺陷【全修完再部署一次】，不每修一个部署一次）**：本轮所有可自动修复缺陷**全部修完**后**只重部署一次**（一次 CICD 往返 ≈ 4~5min，实测某轮触发 8 次 CICD、其中 3 次是"修一个→部署→再测"的单缺陷往返，纯等待 30+min）。**唯一例外**：某缺陷会**阻断后续用例执行**（如登录接口挂了、关键前置数据造不出）→ 才**立即单独部署**先解阻断、再继续修其余。攒批由 `/sprint-bugfix` 一次批量修复承载（它拾取整份问题汇总清单批量修，不逐条 commit-deploy）。
   - **重部署**：按 `deployment.mode` 部署（Phase 3.2 / 3.2.1），写 `last_deployed_at`。
   - **铸新 build**：Phase 3.1.5 因上一 build 已 `ai_report_finalized` → **强制自增新 build**（标「第 N 轮复测（上轮通过率 X%）」，`retest_of`/`retest_round` 已落 builds[]）；**绝不复用/覆盖旧 build**。
   - **复测**：新部署触发测试链路对新 build 实测 → 新一轮 `#F` + 新报告；收敛则闭环结束，未收敛则下一 tick 再入本闭环（受第 3 步上限约束）。
   - 每次进入本闭环即 `auto_fixable_pending=false`（已派修复，避免同一 tick 重入）**且 `auto_retest_streak +1`**（记一轮自动复测）；修复后仍未收敛由测试链路重新置真。
3. **★ 自动复测达上限 → 转人工修复（不再无限自动烧）**：`auto_retest_streak` 达 `retest_auto_cap`（默认 3）仍未收敛 → **停止自动修复**、按「冻结字段写入契约」**一次写齐**：`versions.{V}.needs_human=true` + **`aiauto_frozen_at=@now`** + **`freeze_reason="unconverged"`** + 顶层 **`aiauto_blocked_reason="frozen:unconverged@{V}"`** + `needs_human_kind="retest-cap"` + `needs_human_reason="自动修复已达 3 轮 build 上限，请手动修复后自动复测"` + 记 `retest_cap_frozen_at`（冻结时刻，retest 专用锚点，与 `aiauto_frozen_at` 并存不互替）
   > ⛔ **`aiauto_frozen_at` + `freeze_reason` + 顶层 `aiauto_blocked_reason` 三者一个都不能少**（契约与枚举值域单一信源 = `{{AIDP_HOME}}/flows/sprint-aiauto-test/phase-0-6.md`「冻结字段写入契约」）：**缺 `aiauto_frozen_at`** → 测试链路两条自动解冻路径的基准时刻取不到、判据恒假 → **永久冻结、只能人工清字段**；**缺 `aiauto_blocked_reason`** → autopilot Phase 2 的 `TEST_LOOP_ALIVE` 仍判 1 → 走「暂缓」而非「熔断」、白等到 12 tick。+ `retest_frozen_head`（★ **冻结这一刻的最新 `git rev-parse HEAD`**——此时第 3 轮自动修复的 commit **均已 commit+push、HEAD 已稳定**，故它就是"autopilot 自身推进到的最后一个 commit"，人工后续任何新提交都必与它不同；**绝不能记第 3 轮修复【前】的 HEAD**，否则冻结瞬间 HEAD 就已≠它、下 tick step 3bis 会误判"人工已修复"假解冻空转、3 轮上限形同虚设）+ 同步刷新顶层 `last_autopilot_head`=同一 HEAD（供 step 3bis 区分"人工新提交" vs "autopilot 自己后续在同分支为别的版本推的提交"）→ 发 #4 @用户（提示"本版已自动修复 3 轮仍未收敛，请在本地手动修复并**提交到部署源分支 `{DEV_BRANCH}`**/重新部署；autopilot 检测到你的修复后会自动铸新 build 复测，无需手动重启测试"）→ Phase 0.3.4 从候选剔除、**本版不再自动派修复**（等人工修复信号，见 3bis）。**★ 语义**：移交人工修复、检测到修复完成即自动复原重测（见 3bis；人工也可直接 `python3 {{AIDP_HOME}}/scripts/autopilot_unfreeze.py --manual <V>` 解冻）。自动修复本身的确定性失败（bugfix 反复失败）仍照常累加 `dev_fail_streak`（另一套熔断，独立于本上限）。
3bis. **★ 人工修复完成检测 → 自动解冻复测（用户"手动修复后自动再跑 AI 测试"的落地闭环）**：被 `retest-cap` 冻结的版本，autopilot **每 tick 在 Phase 0.3.4 剔除候选【之前】先探人工修复信号**——`needs_human_kind=="retest-cap"` 且满足任一：① `git rev-parse HEAD` ≠ `retest_frozen_head` **且** ≠ 顶层 `last_autopilot_head`（★ 双重不等才算"人工新提交"——排除 autopilot 自己冻结后在同一分支为**其它版本**推进的提交造成的假信号；仅当 HEAD 是"既非冻结锚点、也非 autopilot 最后自推"的第三种提交才判人工）② `last_deployed_at` 晚于 `retest_cap_frozen_at`（人工已重新部署）→ 判定「人工修复完成」→ **自动解冻**：清 `needs_human` / `needs_human_kind` / `retest_cap_frozen_at` / `retest_frozen_head` + **一并清冻结契约三件套 `aiauto_frozen_at` / `freeze_reason` / 顶层 `aiauto_blocked_reason`**（写时成套、清时同样成套，残留会让测试链路继续当冻结态）+ **`auto_retest_streak` 归零**（重新授予下一个 3 轮自动复测配额）→ 该版本重回正常候选 → 进 Phase 3 **重部署（如需）→ Phase 3.1.5 铸新 build → 触发测试链路 AI 自动化测试**（`auto_fixable_pending` 由测试链路按新一轮实测结果重新置真）。新一轮若又连吃 3 轮自动修复仍不收敛 → 再次 step 3 冻结转人工，如此"自动 3 轮 ⇄ 人工修复"往复循环，**既永不无限自动烧，也永不把人工修好的代码晾着不复测**。一行日志「🔧 检测到人工修复（新提交/新部署）→ 解冻 <V>、重置自动复测计数、铸新 build 复测」。**★ 无人值守铁律**：本检测与解冻**全自动、不弹 `AskUserQuestion`**（`/loop` 与交互式单次调用下都自动执行）；用户唯一的动作就是"在本地把 bug 修掉并提交/部署"，其余（发现修复→解冻→铸 build→复测→出报告→发通知）全由 autopilot 自动完成。
   > 📌 **信号鲁棒性（已知窄窗 + 兜底）**：条件①（HEAD 双重不等）在**多版本共用同一分支**时有窄漏检窗——若人工对本冻结版本提交后、autopilot 在本次 3bis 探测【之前】又为**另一版本**在同分支自推并把 `last_autopilot_head` 刷成新 HEAD，则当前 HEAD == `last_autopilot_head`、①被掩盖。**条件②（`last_deployed_at` 晚于 `retest_cap_frozen_at`，即人工重新部署）是鲁棒兜底、不受该窗影响**——故 #4 通知明确引导用户"提交并**重新部署**"，只要人工重新部署即必被②命中解冻；即使只提交未部署，下一次人工动作/部署仍会命中，**不致永冻**（自恢复）。**规避建议**：每版本用独立 dev 分支即无此窗。
4. **需人工确认类不进本闭环**：`pending_clarifications[]` 里的产品语义/范围问题**不自动修**——它们在测试链路已"本轮照常 finalize、#F 列出待确认项"（旧 build 报告保留），等用户裁决后由用户 `/sprint-autopilot --once` 铸新 build 复测。autopilot 每 tick 若发现某版**仅剩 `pending_clarifications[]`、无 `auto_fixable_pending`** → 不自动动作（等人），但在 #4 / 终端提示"有 N 项待产品确认，确认后 `--once` 复测"。
5. **standalone / 未挂测试 loop**：本闭环依赖测试链路写 `auto_fixable_pending`；若测试链路未运行（未装调度 / 未挂 `/loop 5m /sprint-aiauto-test --unattended`），`test_loop_missing_streak` 熔断（见 baseline schema）照常兜底，不会空转。

## ★ 子 Agent 派发失败的分层重试与降级（P0-3）

> 委派子 Agent 遇失败的**分层处置细则**（C1 瞬时 API 错误 529/503/超时指数退避重试 · C2 降级阶梯"重试→换小粒度→内联" · C3 内联上下文预算护栏"不足则分批续跑" · C4 降级留痕）已下沉 **`{{AIDP_HOME}}/flows/sprint-autopilot/invariants.md`**。要点：**⛔ 绝不把瞬时 API 错误等同确定性失败直接降级内联**；穷尽 C1/C2 仍失败或【确定性失败】才落到下方「失败处置」熔断。委派点（Phase 3.3 / 3.5 / 测试链路）遇子 Agent 失败一律先走该分层。
## 失败处置（里程碑通知 #4 触发处）

任何 Phase 失败均走以下流程：

1. **暂停命令**（不退出，保留 Claude Code 进程状态，留 working tree + memory 现场）
2. **里程碑通知 #4（红色 header + 需要人工介入，见 0.1bis）**——通知含公共字段 + 下列内容（经 `notify.py --auto` 发送；未配置任何渠道时退出码 3 → 静默跳过本播报节点，终端照常打印同一内容）：
   ```
   🚨 sprint-autopilot 卡住，需要你介入

   阶段：Phase {N} - {阶段名}
   错误摘要：{最后一条 ERROR 日志，截 200 字符}
   现场：
     - 分支：{branch}
     - 最后 commit：{hash} {subject}
     - 失败的 Sprint：{NNN}（如有）
   日志路径：memory/autopilot-{YYYYMMDD-HHMM}.log

   📌 下一步（选其一）：
     1. 你接管：在终端继续输入指令
     2. 修复后解冻重试（无人值守下下一轮自动接续）：
        python3 {{AIDP_HOME}}/scripts/autopilot_unfreeze.py --manual {version}
     3. 交互式会话内：回复 "retry" / "skip" / "abort"
   ```


> ★★ **本段五步（记账 → 判阈 → 冻结四件套 → 发 #4 → 让位）已收进一个脚本，各引用点一律调它、⛔ 不再逐处手抄**：
>
> ```bash
> python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --version "$V" --phase <游标> \
>   --reason <freeze_reason 枚举> --why "<真因，⛔ 别写「失败了」>" [--build "$BUILD"]
> # 退出码：0=已记账让位本 tick／3=已冻结（达阈 **或无唤醒源**）／2=入参错（⛔ 此时什么都没写）
> ```
>
> 手抄稳定漏三样：**只写「走失败处置流程」一句散文而没有 `bump`**（那几类失败永远累不到阈值，最后被通用 stuck 熔断冻成人工专属的 `stuck-phase`）、**写了四件套但没发 #4**（停得住、停不响）、**无唤醒源时阈值恒不可达**（`--once` 没有下一 tick 来叠 streak）。收进一个调用后，这三样在结构上不可能再单独发生。

3. **★ 失败一经确认先立即写熔断计数**（`versions.{V}.dev_fail_streak`，见 step 5）**再交还控制权**——确定性失败据此累积触发熔断，**不被下方等待吞掉**。随后按上下文分流：
   - **交互式**（无 `--unattended`）→ 在终端打印同一摘要与选项后**结束本轮**，由用户在对话中回复 retry / skip / abort 或直接接管；⛔ 不长挂轮询等人。
   - **★ 无人值守**（`LOOP_UNATTENDED=1`：`/loop` 上下文 / `--no-loop` / `--unattended`）→ **一秒不等**（无人可答）：发完 #4 通知即**退出本 tick**（`dev_fail_streak` 已写盘），交由下一轮调度唤起按熔断状态（step 5）决定重试或跳过。
4. 交互式结束本轮时 → 在 `memory/autopilot-{YYYYMMDD-HHMM}.log` 末尾写「待人工回复，状态保留」+ **不回写版本进度/产物态**（`dev_fail_streak` 已在 step 3 写盘、不受影响；下次调用按熔断状态决定重试）
5. **★ 确定性失败熔断（防 /loop 无限重撞同一失败 + #4 刷屏 —— 对称测试链路 Phase 3.5「连续未收敛护栏」）**：并非所有失败都值得下轮重试——`git pull --rebase` 冲突 / version-auditor 反复判同一 Critical / PRD `on_decision_conflict` 决策冲突 / **Phase 3.4 完成核验门结构性不可自愈失败（`dev_fail_phase="3.4-ceremony-gate"`）**等**确定性失败**，下次 `/loop` 唤起会重跑 → 再撞同一失败 → 无限循环 + 每轮刷一张 #4。故：
   - 每次失败**在 step 3 失败确认点即写盘** `versions.{V}.dev_fail_streak`（独立于人工回复等待，确保确定性失败必累积；同一 Phase 连续失败 +1；换 Phase 或成功则清零）+ `dev_fail_phase`。
   - 当 `dev_fail_streak ≥ dev_fail_freeze_threshold`（默认 3，baseline `dev_fail_freeze_threshold` 可覆盖）→ 按「冻结字段写入契约」**一次写齐**：`versions.{V}.needs_human=true` + **`aiauto_frozen_at=@now`** + **`freeze_reason="unconverged"`** + 顶层 **`aiauto_blocked_reason="frozen:unconverged@{V}"`** + `dev_fail_frozen_at`（dev 专用锚点，与 `aiauto_frozen_at` 并存不互替），**发最后一张 #4**
     > ⛔ **同上：三个契约字段缺一即出事**——缺 `aiauto_frozen_at` → 测试链路两条自动解冻路径恒假、**永久冻结**；缺顶层 `aiauto_blocked_reason` → `TEST_LOOP_ALIVE` 误判健康、走「暂缓」白等 12 tick。契约与 `freeze_reason` 枚举值域单一信源 = `{{AIDP_HOME}}/flows/sprint-aiauto-test/phase-0-6.md`「冻结字段写入契约」，此处不复述。（正文标注「已连续 {streak} 轮在 Phase {N} 失败、疑似确定性问题，暂停本版自动重试待人工介入」）后**冻结本版**：后续 `/loop` 唤起在 **Phase 0.3.4「识别最近一对」处把 `needs_human=true` 的版本从 PRE_RELEASE/TARGET 候选剔除**（一行日志「⏸️ {V} 已熔断待人工，跳过」，**不再选中重跑、不再重发 #4**）。
   - 解冻：人工接管修复后清 `needs_human`/`dev_fail_streak` + **冻结契约三件套 `aiauto_frozen_at`/`freeze_reason`/顶层 `aiauto_blocked_reason`**（成套写、成套清）+ `dev_fail_frozen_at`（统一入口：`python3 {{AIDP_HOME}}/scripts/autopilot_unfreeze.py --manual <V>`，一次清齐上述字段；交互式会话内也可回复 "retry"）→ 恢复自动。**瞬态失败**（网络抖动 / 临时锁）streak 未达阈值仍按原样下轮重试、不受影响。

---

## 7×24 守护用法 + 输出示例

> **★ 完整守护挂载用法**（操作系统调度 · 会话内 `/loop` · 单次/临时模式 · 用法对比表 · 权限前置）**+ 输出示例**见 **`{{AIDP_HOME}}/flows/sprint-autopilot/usage-guard.md`**（按需 `Read`）。标准挂法（★ 双链路缺一不可）：
> ```bash
> python3 {{AIDP_HOME}}/scripts/aidp_scheduler.py install   # 开发链路 + 测试链路（漏掉测试链路则浏览器实测/AI测试报告/#F 永不触发）
> ```

## 停止机制 / 与其他命令的关系 / 注意事项

> 这三段（停止机制 · 与其他命令的关系 · 注意事项）为参考性内容，已下沉 **`{{AIDP_HOME}}/flows/sprint-autopilot/usage-guard.md`**（与守护用法同片），按需 `Read`。
