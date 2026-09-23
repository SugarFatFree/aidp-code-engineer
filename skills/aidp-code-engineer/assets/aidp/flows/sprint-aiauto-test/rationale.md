# sprint-aiauto-test · rationale（理据 / 根因 / 反例）

> 本文件承载 `/sprint-aiauto-test` 各 Phase 外置背后的**理据 / 根因 / 反例 / 历史事故**——这些对人类维护者有价值、但对执行期模型是噪音（稀释祈使信号），故从执行路径剥离，执行时**不加载**。

## 为什么把 Phase 0 / 2 / 3 外置

命令主体原 1715 行、含 50 个 `⛔` 硬门，一次性整份入上下文会触发「lost in the middle」漏步、几十条硬门互相稀释、长流程「满足即止」跳步。按 `{{AIDP_HOME}}/flows/README.md` 约定，把三段最大且最自包含的 Phase 段外置为 `phase-0-*.md` / `phase-2-*.md` / `phase-3-*.md`（各段又按 20KB 上限二次切分，实际分片清单见命令主体骨架表；⛔ 这三个不带序号的文件名**已不存在**），命令主体压到 ~280 行、每段留「关键硬门 + 骨架表 + Read 指针」薄壳，进入该 Phase 的第一动作即按需 `Read` 对应 flow 文件。

## 报告产物与轮次通知的边界

AI测试报告的官方交付物是 HTML 离线 SPA，结论和截图引用写入 `data/{BUILD}.js`；根层另写叙述性 Markdown 会产生两份互相漂移的结论。但 `build-*/round-*/tasks.md` 和 `run-context.md` 是 SKILL 的进度与上下文产物，不能把“禁止 Markdown 报告”错误扩大到这些文件，否则断点续跑状态丢失。

每轮未收敛且未达冻结阈值时，提前让位之前必须真正发送 #R；只在终端 `echo` 一句“只发 #R”不会登记通知台账。达到冻结阈值时依既有仪式收口与 #4 路径处置。

## Phase 0.2 相关根因（对应 `phase-0-6.md`）

- **心跳 ≠ 能干活（双链路互等死锁）**——"loop 进程还在跑"与"本版本还能推进"是两件事。若只写 `aiauto_test_heartbeat_at`，冻结门 `exit 0` 之后 autopilot 侧会读到新鲜心跳判 `TEST_LOOP_ALIVE=1` → 准发布"暂缓、不累加 missing-streak、不冻结"，而测试侧其实已 `needs_human` 冻结待人——**双方互等、零告警、build 永不收口**。故必须同时维护 `aiauto_blocked_reason`。
- **`aiauto_blocked_reason` 必须带 `@<version>` 后缀，读侧也必须解析它**——该值形如 `frozen:<reason>@<version>`。若读侧只判"非空即测试链路已死"，则 A 版一冻结、**B 版每 tick 被连坐**：autopilot 会给 B 累加 `test_loop_missing_streak`，3 tick 后把 B 也冻上并写下 `config-missing / 测试链路未挂载` 这个**错误诊断**，让人去查一条一直好好挂着的 loop。故读侧口径：全局类原因（`chrome-unavailable`，机器无浏览器/驱动）对任何版本成立；其余为版本类，只对 `@` 后那一版成立；无 `@` 的历史值按全局保守处理。
- **冻结版本不得饿死后续版本**——`needs_human` 的版本每 tick 都在冻结门 early-exit，若它恰是「最老待测版本」就会永久霸占 `baseline_edit.py current-version` 的结果，后续版本一次都测不上；叠加上一条即形成"一版冻结 → 全线连坐"。故选版在待测集内**未冻结优先**，全冻结才回落（保留其自动解冻判定的机会）。
- **冻结前必须先收口 exec 报告（④）**——浏览器路径下本命令是 build 的**关闭方**（R-4）。任何在 R-4 之前 early-exit 的冻结分支若直接退出，autopilot 早已交付的 exec 骨架就再没有第二个人来关闭：永远收不到该 build 的 `#3` 通知，报告页停在"待测"占位。故契约第 ④ 条要求先以"最后已知结论"收口再冻结。
- **已测去重门的三重豁免**——② `--once` 尤其不能漏：`--skip-dev --skip-deploy` 的复测、人工修复后【只提交未部署】触发的解冻复测都走这条路；不豁免的话这类轮次会 `exit 0` 什么都不做，而心跳处已乐观清空 `aiauto_blocked_reason` → autopilot 判"测试链路健康"、随后自跑 `--stage final` 必因缺 `#F`/AI测试报告 FAIL。


- Phase 0 各子步骤（连接模式护栏 0.0.7 / 自愈交接 0.2·2.5.1 / 熔断冻结门）的历史事故与反例。
- Phase 3 报告不可变铁律、截图落盘硬核验的下游反馈根因。

- **★ `CONVERGED` 判据把"红"判成"绿"（全链路唯一一处）**——`THIS_ROUND_FAIL_COUNT` 全仓仅 1 处引用、**0 处赋值**，而写法是 `${THIS_ROUND_FAIL_COUNT:-0}`：没人汇总 = 取 0 = "本轮零失败"。于是不论实际失败多少条都判 `CONVERGED=1` → 发绿灯 #F → finalize → 写 `aiauto_tested_at`。修法：改 **fail-closed**（`-z "${VAR+x}"` 判未定义即判未收敛），并要求 Phase 2 显式汇总各执行子 Agent 回传的 `fail` 之和。**教训**：`:-默认值` 在"默认值恰好等于通过侧"时是最危险的写法，它把"没人告诉我"伪装成"一切正常"。
- **★ `driver_actual` 写盘用了不存在的变量 + 时序不对**——反失真门（ceremony-gate 3i）比对的是"报告自述 driver"与"运行时独立记录 `builds[].driver_actual`"。但写盘那行用了 `$CURRENT_BUILD`（全仓从未赋值，`[ -n ... ]` 恒假 → 整行静默不执行），且 0.0.7 跑在 build 号解析之前、此刻根本拿不到 build。净效果：字段永不落盘 → 3i 每轮只打印一行 DEGRADE 然后放过，**规则写对了、落地写错变量名，事故复现路径原样保留**。修法：0.0.7 先落版本级 `driver_actual_pending`（一定写得进），Phase 0.6 解析出 `BUILD` 后立即认领改挂到 build 名下并清除待认领字段。
- **★ bash 里写字面 `{V}`/`{BUILD}` 占位符**——同一行曾混用 `--version "{V}" --build "${BUILD}"`，自证是笔误。后果两层：门指向不存在的路径恒 FAIL；`bump`/`set` 把 streak 与冻结字段**记进一个字面名为 `{V}` 的假版本键**，真实版本的熔断永不触发。本仓已有同类事故（提交 `7e5076d` 清除过误写入的 `versions.V9.9.8/V9.9.9`）。
- **`CONVERGED` 的作用域与时序**——它曾被算在 3.5「切有头提醒」里，而那段**只有远程 mcp 路径**会走。本地 cli（默认路径、无头）跑到消费点时拿到空值，连锁产生三个故障：`aiauto_test_unconverged_streak` 假累计→假冻结、AI执行报告永停骨架、`#3` 通知永不发。故必须无条件前置到 3.3 开头。
- **冻结字段三件套为何缺一不可**——① 缺 `aiauto_frozen_at`：解冻判据要拿它当基准时刻做比较，取不到即恒假 → **永久冻结**，只能人工清 baseline。② 缺 `aiauto_blocked_reason`：autopilot 侧只看到测试链路的新鲜心跳、误判"健康"，于是无限暂缓准发布，而测试链路其实一条用例都没跑 → **双链路互等**。③ `aiauto_blocked_reason` 缺 `@<版本>` 后缀：autopilot 读侧靠它区分"全局不可用"与"仅那一版卡住"，缺了会让本版的冻结把**其它版本**一并连坐误判成"测试链路未挂载"。

- **冻结前的仪式收口（3.4 冻结级熔断的 ①②③ 三步为何不可省）**——冻结的语义是「本版暂停自动重测、等人工」，但**冻结动作本身不产出任何结论**。若只置 `needs_human` 就收工，本 build 的 AI执行报告会永久停在 autopilot 写的**骨架态**（`testSummary` 还是占位）、`#3` 与终态 `#F` 永不发出——最后收到的通知是第 N 轮的 #R「未收敛」，然后一片安静，既不知道判定为不通过、也拿不到报告链接，而 build 已被冻结、再没有任何路径会回来补。故必须先 finalize 报告 + 发两条通知，再跑确定性 gate 复核这两件事**真的落了盘**（散文式收口极易漏步），过了才允许冻结。这与「报告不可变铁律」并不冲突：finalize 恰恰是让它进入不可变终态的那一步。



### 统计为何必须走 `gen_report.py`（`phase-3-3.md` 收敛判定）

`THIS_ROUND_FAIL_COUNT` 曾写成「Phase 2 各子 Agent fail 之和，执行体本块内就地赋值」。问题有三层：

1. **与 SKILL 直接冲突**：`auto-test-runner` 的 `report-format.md` 与 SKILL 约束 10（事实字段可溯源、禁模板默认）都写着「统计由 `gen_report.py` 从 `results/*.json` 聚合，**人不手工计数**」。
2. **拿不到该拿的字段**：`auto_cover_rate` / `auto_success_rate` 只有聚合脚本会算，手工累加恒缺。
3. **分流会错**：`gen_report.py` 内部走 `split_entries` 把「自由巡检项」与「用例」分开；手工累加会把巡检项混进 `total`，而 SKILL 明确把这条列为"方向恰好相反"的错误。

更讽刺的是：命令端自己的 `{{AIDP_HOME}}/scripts/emit-report.py` 就写着「统计字段须由 `gen_report.py` 聚合，不得手填」——两边同一条规矩。现已接线：统计由 `phase-3-3.md` 调 `gen_report.py` 聚合。

取不到时**留空**而非补 0：留空会被下一行 `-z` 判成"未收敛"（fail-closed），补 0 则直接把红判成绿。

## 收敛判定的两处断链（phase-3-3 · 3.6）⛔ 改那两行前先读本节

`THIS_ROUND_FAIL_COUNT` 的取值曾同时踩中两个错，任一成立即 fail-closed 恒判「未收敛」：

1. **round 目录少 `build-` 前缀**——SKILL 契约（`auto-test-runner/SKILL.md`）与同仓其余 5 处
   一律是 `build-${BUILD}/round-*`（见 `phase-3-1.md` 的 BTR 用法），只有这一处漏了 → `RD` 恒空。
2. **`.fail` 键不存在**——`gen_report.py` 返回 `{'total', 'eligible_total', 'counts':{'pass','fail','block','na'}, 'na_count', 'pass_rate', …}`，
   失败数在 `.counts.fail`，顶层无 `fail` → `jq -r '.fail // empty'` 恒 empty。

后果不是"少一个数"，而是**方向性错误**：`CONVERGED=0` 让 3.7 整步跳过（`ai_report_finalized`
永不写、`#3` 永不发、AI执行报告永停骨架），并在 10 轮后按 `unconverged` 冻结、发红色 `#F`
「测试结论：❌ 不通过」——**而真相可能是全部用例通过**。把绿判红比把红判绿更难被发现，
因为没人会去质疑一个"失败"的结论。


## 去重门状态口径：为什么必须是 `tested|closed` 二元判定

`phase-0-6.md`「本 build 已测过」的判据读 `builds[].status`，而该字段是**两段式**写入的：
`phase-3-2.md` 先刷 `tested`，随后 R-4 收尾（`phase-3-5.md` Step 3）**改写为 `closed`**
（连同 `ai_report_finalized:true` 冻结报告）。

只认 `tested` 会得到一个**反直觉的失效方向：越是成功收敛，越会被反复重跑。**
一轮完整成功的测试收尾后 `status` 已是 `closed` → 去重门恒假 → 不跳过 →
每个 5 分钟 tick 重跑一整套浏览器用例 → 走到 R-4 调 `emit-report.py` 时命中
「报告不可变铁律」拒写 `exit 2` → `AI_REPORT_URL` 空 → final 门 FAIL →
`report_gate_fail_streak` 累加 → 约 15 分钟后把一个**本已成功收敛**的版本
按 `handoff-exhausted` 冻结。

窗口期一直持续到 autopilot 下一 tick 完成 Phase 2 准发布（写 `internal_released_at`）为止；
而准发布常被双门 hold 住，于是持续空烧。

判据本身只有一行，但**方向是"把已完成的工作判成未完成"**，且症状（冻结 + 重跑）
看起来像"测试不稳定"，极易被误诊。`phase-3-4.md` 的对应判定一直是 `closed|tested` 二元，
只有去重门这一处漏了。


## freeze_reason 枚举（权威定义 —— 写入方与解冻方共同的单一信源）

> ⛔ **本表是 `freeze_reason` 取值的唯一权威**，`check_freeze_contract.py` 直接解析本表做机器校验。
> 新增冻结场景 = 先在本表加一行（含解冻类别），再去写入站点；**不得**在散文里就地造一个
> `needs_human_reason="随手写的中文"` 了事——那样它既不进任何 `case` 分支、也不被任何守卫看见，
> 净效果是这一版**永久停摆且零告警**（实测四个站点正是这么长出来的）。

| freeze_reason | 解冻类别 | 解冻信号 |
|---|---|---|
| `probe-timeout` | 环境类 | 新部署；或环境类自动复探到期放行（`autopilot_unfreeze.py --env-reprobe`：冻结后 20min × 2^n、单次间隔封顶 4h、最多 10 次，用尽转人工）|
| `deploy-unreachable` | 环境类 | 同上 |
| `chrome-unavailable` | 环境类 | 同上 |
| `pipeline-unknown` | 环境类 | 同上（流水线对照表变化后复探即可能唯一命中）|
| `cicd-run-vanished` | 环境类 | 同上 |
| `cicd-unreachable` | 环境类 | 同上（CICD 平台不可达 / 触发或重试被平台拒绝；按 `cicd_unreachable_streak` 连续 3 次才冻结）|
| `cicd-cli-unavailable` | 环境类 | 同上（CICD 提供方 CLI 未安装 / 未登录 / 凭据失效；按 `cicd_cli_fail_streak` 连续 3 次才冻结；装好或重新登录后复探即放行）|
| `account-missing` | 配置类 | 账号文件 mtime 晚于冻结时刻 |
| `account-invalid` | 配置类 | 同上 |
| `testplan-incomplete` | 配置类 | 测试方案文件 mtime 晚于冻结时刻 |
| `cicd-auto-trigger-off` | 配置类 | `memory/aidp-config.yaml` mtime（开启 `cicd.auto_trigger` / 调整 `cicd.provider`·`cicd.pipelines`）|
| `prd-missing` | 配置类 | **PRD 目录 mtime**：`docs/requirements/{V}/产品提供/` 晚于冻结时刻。⛔ 与 `config-missing` 分开：后者认心跳，而心跳是本链路每 tick 无条件先写的，自己写的冻结会被自己刚刷的心跳立刻解冻 |
| `config-missing` | 配置类 | **心跳专判**：测试链路心跳晚于冻结时刻（补挂第二条 loop 不产生新部署，故不能用 mtime）|
| `preflight-incomplete` | 门控类 | **只由 Phase 0.7 前置收口门再次通过时显式解冻**（成功路径调 `autopilot_unfreeze.py preflight-gate`，同时清版本级四件套 + 顶层 blocked_reason）。⛔ 探针一律不判——它此前借用 `config-missing`，而后者认心跳，双 loop 下第二条 loop 每 5 分钟刷心跳就把它误解冻，而前置配置一字节没变 |
| `unconverged` | 收敛类 | 新部署 或 人工 |
| `plan-transient` | 收敛类 | **HEAD 变更**（有人推了新提交 ⇒ 具备重试价值）或 人工。`/version` 规划因**派发失败 / 网络抖动 / 超时**等瞬态原因未走完时用它，⛔ 别再回落 `release-blocked`——那是交接类、仅人工，把一次重试就能过去的事钉成必须人来救，而 `needs_human_reason` 还会把人指向一份根本没有 Critical 的审计报告 |
| `release-blocked` | 交接类 | **仅人工**（发布期验收阻塞，须人清 P0 后重跑发布）|
| `audit-critical` | 交接类 | **仅人工**（累进路径增量审计检出 Critical，须人裁决 + 回对应 SKILL 补齐文档后重跑；无任何自动信号能证明它已解决）|
| `handoff-exhausted` | 交接类 | 仅人工 |
| `stuck-phase` | 交接类 | 仅人工 |

> **★ `retest-cap` 是唯一合法的变体、不是漏网**：复测达上限的冻结走 `needs_human_kind="retest-cap"`
> + `retest_cap_frozen_at`，**不写 `freeze_reason`**。它的解冻判据是「人工是否有新提交」
> （`HEAD` ≠ `retest_frozen_head` 且 ≠ `last_autopilot_head`），与本表任何一类都不同构，
> 故独立成一路（口径单一信源 = 命令主体 step 3bis）。守卫按 `needs_human_kind` 识别并放行。

## 冻结分类：为什么 `cicd-auto-trigger-off` 归配置类、`stuck-phase` 归交接类

**`cicd-auto-trigger-off`** 在**部署尚未发生时**（首次触发）或重试前冻结
（`cicd.auto_trigger=false` 时无人可触发 / 重试 CICD 流水线）。它们此前**只写不认**——不在任何解冻 case 分支里，
而通用解冻路径①的判据是「冻结后有新部署」：部署根本没发生过，`last_deployed_at` 永远不会前进，
于是这条路径**永不触发**。净效果：项目只要没开自动触发，7×24 链路 100% 在首次部署处永久停摆，
只能人工 `--reset-baseline`。

归**配置类**（mtime 判据）是因为它们的真实修复动作就是**改配置**：开启 `cicd.auto_trigger`、
或调整 `cicd.provider` / `cicd.pipelines` —— 两者都落在 `memory/aidp-config.yaml`，按其 mtime 判定即可。

**`stuck-phase`** 是**状态机不推进**（同一 Phase 反复进入、时长超阈），与部署无关。
`invariants.md` 早已声明它属交接类、解冻靠人工；但解冻路径①此前**无 reason 过滤**，
一次凑巧的新部署就会把它悄悄解冻 —— 真问题被盖住，随后以完全相同的形态再冻一次，循环往复。
`handoff-exhausted` 同理。故路径①显式排除这两个值。


## 冻结三件套缺一的后果

- 缺 `aiauto_frozen_at` → 解冻判据（比时间戳）恒假 = **永久冻结**。
- 缺 `aiauto_blocked_reason` → autopilot 侧只看到新鲜心跳、误判"测试链路健康"而无限暂缓 = **双链路互等**。
- 缺 `@$TARGET_VERSION` 后缀 → 本版冻结**连坐**误判其它版本。
- **冻结前必须先收口本 build 的 AI执行报告**（本命令是浏览器路径下 build 的关闭方 R-4）：
  有 `current_build` 且 `data/{BUILD}.js` 的 `testSummary.pendingBrowserTest=true` → 按 autopilot
  `phase-3-8.md`「Phase 3.4 Step 1.1→2→3」以**最后已知结论**收口 + 发 #3，**然后**才写冻结字段并 exit。
  不收口 → 该 build 永停骨架态；如实标『浏览器实测未完成 (<freeze_reason>)』，
  ⛔ 不得填 0/0/0 或标"通过"（那会撞上「报告不可变铁律」，真实结论此后永远进不了报告）。


## 只写散文的状态字段（三处，均为"配了却永不生效"）

Phase 3.3 曾用散文描述"置 baseline `versions.{V}.auto_fixable_pending=true`"这类动作，
但**全仓没有任何对应的 `baseline_edit.py set` 命令**。散文不是可执行落点，后果逐条如下：

- **`CONVERGED`** —— 算出点在 3.3，消费点在 `phase-3-4.md` / `phase-3-5.md` 多处**别的分片**。
  shell 变量不跨 Bash 调用，且该名此前**未登记进 `DERIVED_VARS`**（`set` 对未登记名直接 exit 2）。
  ⇒ `[ "$CONVERGED" = "1" ]` 在 3.5/3.7 恒假 ⇒ **#3 通知永不发、AI执行报告永停骨架态**，开发链路 Phase 2 的 0b 收敛门因此恒不过。
- **`auto_fixable_pending`** —— 是 autopilot `phase-0-6b.md` 自动修复闭环的**唯一触发信号**。
  全仓此前只有把它置 `false` 的那一处、**没有置 `true` 的**。⇒ 命令主体那整套
  「测试失败 → 自动 `/sprint-bugfix` → 重部署 → 铸新 build → 复测」每 tick 都走"什么都不做"分支，
  缺陷停在「问题汇总清单」里，版本永不收敛，最终按 `prerelease_test_hold_streak` 误冻结成"未收敛"。
- **`aiauto_test_unconverged_streak` / `aiauto_test_round` / `builds[].status="tested"`** ——
  `phase-0-6.md` 的去重门在读它们。不写 ⇒ 去重恒不命中 ⇒ **每 tick 重跑整套浏览器用例**。

`AUTO_FIXABLE_FOUND` 是「分流两类」的**语义判定结果**（哪些缺陷根因明确、无产品语义分歧），
shell 算不出来，故由 Claude 就地代入 true/false，并带 `flowvar-check: allow` 标注说明来源。


## 分流输入为何是"全部缺陷"而不是"失败用例"

把分流输入写成"失败用例"会留下一个 `fail=0` 真空：用例全绿、但用例**之外**捕获到了
console error / 未捕获异常 / 接口非预期状态码，或者人肉观察到了未被任何断言覆盖的缺陷——
这些一条都进不了闭环，于是 `auto_fixable_pending` 永远是 false，缺陷停在清单里没人修。

严重度同理不构成豁免：**严重度只决定处理顺序与紧急度，不决定走不走闭环**。
"P2 可以不铸新 build""P3 登记一下不处理"这类口子一开，未收敛的版本就会带着已知缺陷
被当成"已测通过"归档。实测事故见 `sprint-autopilot/rationale.md`。


## 报告字段门（`REPORT_ENABLED`）

`REPORT_ENABLED=0`（直接调用 / 非 autopilot 驱动，未生成 AI测试报告）时，#R / #F 通知的
「测试报告（HTML）路径」**一律省略**，替换为一行说明
「本轮为直接调用，未生成 AI测试报告（报告仅 autopilot 流水线驱动时生成）」；
测试结论 / 用例统计 / 缺陷统计等**结果字段照常播报**——测试是真跑过的，省的只是报告产物。

`REPORT_ENABLED=1` 才按模板带报告路径（仓库相对路径，带 `#/build/{BUILD}`）。


## `NOTIFY_ENABLED` 值域：统一 0/1，且判完必须落盘

`aidp_config.py get notify.enabled` 读出的是 `true`/`false`，而下游分片与 tick 变量一律按 **0/1** 判。
同一分片里此前两套写法并存（`[ "$NOTIFY_ENABLED" != "true" ]` 与 `NOTIFY_ENABLED=0`），
判据互相看不懂对方的值。

更关键的是「本轮静默跳过播报」这个结论**没有落盘**：后续分片经 `--shell` 回落时归一成 `1`，
于是收尾门照常索要通知台账 → 恒 FAIL。故这里做两件事：读出即归一成 0/1；判定为跳过后
立刻 `tick_flags set NOTIFY_ENABLED 0`。


## `SELECT_MODE` / `SKIP_REPORT` 必须落盘

两者的算出点与消费点**不在同一分片**：`SELECT_MODE` 在 Phase 0.6 判定、`phase-2-2` 等处消费；
`SKIP_REPORT` 在 3.1 判定、3.2.5 / 3.2.6 消费。shell 变量（含 `export`）**跨不过 Bash 工具调用**，
而两者此前既未落盘、也未登记进 `DERIVED_VARS`（`set` 对未登记名直接 exit 2）。

回读恒空的后果：

- `SELECT_MODE` 空 ⇒ `[ "$SELECT_MODE" != "all" ]` 为真 ⇒ 走子集分支，并把**空值**传给 `--select`
  —— "跑了 5 条 P0 全绿就当测过了"的风险复活，而无人值守路径本应强制 `all`（护栏就在同一段里，
  只是结论传不出去）。
- `SKIP_REPORT` 空 ⇒ standalone 轮次照样进截图硬核验，`SHOT_DIR` 拼出空 BUILD 段。


## 自愈式交接（2.5.1）的骨架归属与触发判据

- 骨架单一信源 = autopilot 子流程 R（3.1.5 产计划态 + 注册两页，3.4 finalize）；本命令不产骨架。铁律详见 phase-0-6b.md
- current_build 存在但 data/{BUILD}.js 缺失 == 本轮经意图路由直达 aiauto-test、绕过了 autopilot 报告流水线（3.1.5 从未跑）→ 自愈交接补齐，绝不在报告缺失下散落 AI测试报告。

## 去重门为何会锁死收口门（Phase 0.2 的第五个条件）

Phase 3 的 final 收口门失败时走的是「记账 + 让位本 tick」（`exit 0`），指望下一 tick 再来一次、
连续 3 次后冻结并发 #3。但 Phase 3.3 在此之前**已经**写下了 `aiauto_tested_at`、
`unconverged_streak=0`、`builds[].status=tested`——于是下一 tick 一进 Phase 0.2 的去重门，
「有 LAST_TST / 有 LAST_DEP / streak=0 / BUILD_TESTED=1 / 部署不晚于测试」五个条件全部满足，
直接 `exit 0`，**收口门的 streak bump 再也执行不到**。

净效果：`unconverged_streak` 永远停在 1、永不达阈、永不冻结、#3 永不发，AI执行报告永停骨架态，
而开发链路那边照常归档——一个本该被看见的失败，变成了完全静默的空转。

**定则**：去重门的前提是「这个 build 已经**测完并收口**」，而不是「测过」。故加第五个条件：
本 build 的 `ai_report_finalized` 必须为 true 才允许跳过。standalone（无 current_build）不受此约束。

## tested 写错层（aiauto_tested_at 是版本级，不是 build 级）

一条 `$BEV --build "$BUILD" set status tested aiauto_tested_at @now` 把两个字段一起写进了
`builds[]` 那条记录。但 `status` 确实是 build 级，`aiauto_tested_at` 是**版本级**——
三个读侧全在版本层：
- `sprint-autopilot/phase-2.md` 的 0b 准发布收敛门；
- `sprint-aiauto-test/phase-0-6.md` 的去重门；
- `baseline_edit.py` 的 `current-version` 选版逻辑。

写错层的净效果是三个读侧**恒取空**：去重门恒假 → 每 5 分钟重跑整套浏览器用例；
0b 收敛门恒不过 → 12 tick 后把版本误冻成 `unconverged`；`current-version` 恒返回最老那版 →
后续版本一次都测不上。而每一处单看都"逻辑正确"，只是读的地方没有值。

**定则**：写盘时先确认字段的层级归属——`--build` 只带 build 级字段，版本级字段单写一条。

## 裸退让去重门恒不命中（Phase 3.3 前的失败必须记账）

Phase 3.3 才写 `aiauto_tested_at`。位于它**之前**的门若裸 `exit 1`，去重门（Phase 0.2）永远
命中不了「本部署已测过」——于是 `/loop` 每 5 分钟把**整套浏览器用例重跑一遍**，再撞死在同一行。
这是所有空转形态里成本最高的一种（每轮都真的开浏览器跑完）。

**定则**：与 2.5.1 同口径——**发起交接那一刻就记账**，不要等"二次进入时才 +1"（那个递增条件
在这条路径上不可达）。失败分支一律 bump streak + 写盘 + `exit 0` 让位。

## 被测版本传不出去（TARGET_VERSION 必须登记 + 落盘）

测试链路 Phase 0.2 用 `baseline_edit.py current-version` **自己选**被测版本——它和 autopilot
正在开发的版本经常不是同一个（常态 tick：上版待测 + 下版已开工）。

但 `TARGET_VERSION` 此前**没登记进** `DERIVED_VARS["aiauto-test"]`，于是
`tick_flags set --command aiauto-test TARGET_VERSION` 直接 `rc=2` 写不进去；而 union 级的
`BASELINE_FALLBACK` 又指向 `autopilot.target_version`。净效果是下游分片经 `--shell` 读回的
**恒是 autopilot 的开发版本**：从下版目录找用例、报告写进下版目录、
`emit-report --build {下版}_build1001` **覆盖 autopilot 正在跑的 build**、冻结与 streak 全记到错版本上。

**定则**：谁选的版本谁登记谁落盘——选版那一步之后立刻 `set`，别指望跨分片的 shell 变量或别人的回落。

## 心跳与阻塞原因（为什么两个字段缺一不可）

`aiauto_test_heartbeat_at` 写在 baseline **顶层**（与被测版本无关），每 tick 起始、
**在任何 early-exit 之前**无条件写——它表征的是"第二条 loop 这个进程还活着"。
autopilot Phase 3.4 ③ 据它判「测试链路是否挂载」，避免把"loop 已挂但本 build 尚未出报告"
误判成"未挂载"而误冻结正确的 build。best-effort，写失败不阻塞。

⛔ **但心跳 ≠ 能干活**：正因为它在 early-exit 之前写，冻结/被去重门跳过/空转的 tick
心跳照样新鲜（5m 间隔 << 30min 判活窗口）。只看心跳会造成两条链路互等死锁——
autopilot 以为测试链路在干活、一直等；测试链路其实每 tick 直接 exit。

故必须同时维护第二个字段 `aiauto_blocked_reason`：本 tick 能正常推进 → 清空；
因冻结/阻塞 early-exit → 写 `frozen:<reason>@<version>`。**`@<version>` 后缀不可省**：
全局类原因（机器无浏览器/驱动）对任何版本成立，而版本类原因只说明"那一版"卡住——
拿它判本版会让 A 版一冻、B 版每 tick 连坐。判活的统一实现 = `autopilot-ceremony-gate.py::test_loop_alive`。

## Phase 2.0.5 为什么派子 Agent 而不 `Skill`-invoke（两条硬理由）

① `auto-test-runner` 的 SKILL.md 自述"执行子 Agent **拿不到 Skill 工具**（即便 `tools:*` 也没有）"，
所以方法论只能靠主 Agent 在 Task prompt 里点名路径、要求子 Agent 自己 `Read`；
② 在主循环里 `Skill`-invoke 会把几千行执行方法论灌进主上下文，却又不在主循环里执行
（B2 主循环禁区）——付了上下文的钱，买不到执行。

## Phase 2.2.1 浏览器等待时长两档的取值缘由

chrome-devtools-mcp 的默认等待（导航 10s / 一般 5s）对本场景偏长：被测页面常带
SSE / WebSocket / 长轮询，**网络永不 idle** → 每步都耗满默认上限，体感就是"每打开一个页面都等很久"。
故两档都改为显式传入：

- 导航类放宽到 `NAV_TIMEOUT` 是为覆盖冷启动 + 首屏接口聚合，但它仍是**上限**——页面稳定即返回、不空等满；
- 常规操作用 `OP_TIMEOUT` 短超时，页面有持续连接时"到点即返回"而非空等；
- 超时**本身也是缺陷信号**（页面卡死 / 接口 hang），所以判该步失败并记运行时错误，而不是重试到过为止。

## Phase 2.4「用例没覆盖到 → 不记 bug」为什么是错的

用例集永远无法穷举所有接口 / 页面 / 分支，漏记会让真实缺陷溜过。典型反例：某用例只断言
"列表出现即通过"，页面上另一个统计卡片的接口其实已经 500——断言通过、缺陷入库为零。
故只要页面出现运行时错误，无论它属不属于某条用例、无论关联用例断言是否通过，一律记 bug。

严重度阈值曾在命令端复述过一套，与 SKILL 判据不一致；现统一以 `auto-test-runner`
`references/execution-methodology.md` 第三节步骤 4 为唯一信源，命令端只消费 `severity` 值。

## Phase 2.1 / 2.4 自由巡检项为什么单列、且不自动升级 bug

- **不计入用例统计**：巡检项**没有断言**，混进分母会让「巡检页越多指标越好看」，方向恰好反了。
- **不自动写进「问题汇总清单」**：那会绕过 SKILL 刻意设的人工确认门，在 `/loop` 下批量灌 bug。
- **超限 block 项**（`运行时-<已达巡检上限>`）是上游为「不静默截断」特意造的一条，
  报告必须如实写出"巡检未覆盖 N 页"，别让「巡检过了」名不副实。

## 子集轮为什么不写 `aiauto_tested_at`（phase-3-3 · 3.3）

`aiauto_tested_at` 是**准发布收敛门**（`sprint-autopilot` Phase 2 0b）与
`baseline_edit.py current-version` 选版的判据——写上去等于宣告「本版已测」。
而子集轮只跑了 P0 或 `[回归]` 子集，通过率与「P0=100%」准则**仅对该子集成立**
（`tasks_state.py` 已在 tasks.md 头部写明这一点）。子集轮把它写上，
就会让「跑了 5 条 P0 全绿」直接顶替一次全量验收。故改写 `aiauto_subset_tested_at` + `aiauto_select_mode`。

## 环境阻塞项不进缺陷分流（phase-3-3 · CONVERGED=0 分流第 0 步）

漏做这步 = 把"环境没起来 / 账号失效 / 驱动缺失"当成产品缺陷：既污染缺陷清单与通过率，
又会让 `auto_fixable_pending` 被误置真，驱动 `/sprint-bugfix` 去"修"一个根本不在代码里的问题，
复测再次全阻塞，如此空转。

## PRD 缺失门（phase-0-6 · 子步骤 3）

- **为什么不裸 `exit 1`**：该分支在心跳写入之后，而心跳那步已乐观清空 `aiauto_blocked_reason`。
  净效果 =「刷新心跳 + 清空阻塞原因 + 裸退」→ autopilot 判 `TEST_LOOP_ALIVE=1` 走"暂缓"，
  熬满 12 tick 才冻结，且原因栏写成 `unconverged`——一个彻底错误的诊断。
- **为什么计数用专属 `prd_missing_streak`**：复用 `env_fail_streak` 会被 0.1.1「chrome 已装」
  与 2.1「有可用用例」每 tick 无条件清零，本门恒停在 1、阈值永不可达。
- **为什么 `freeze_reason` 用专属 `prd-missing`**：不复用 `config-missing`，理由见本文件枚举表。

## 去重门与选版的两个易错点（phase-0-6 · 子步骤 1–2）

- **时间一律 epoch 比较**：时区写法混排下做字符串比较，会把"新部署还没测"误判成已测，
  本 build 从此永不被测。去重门本身是 GAP 兜底，防 `/loop 5m` 对同一部署重复跑全套用例、
  重刷 #R/#F 通知、空烧资源。
- **选版不得在此内联 jq 复述**：Phase 0.0.5 / 0.0.6 的预解析调的是 `baseline_edit.py current-version`，
  这里再写一套一旦漂移就会"预读用 A 版本、实测用 B 版本"。

## 通知配置缺失时的兜底精神（phase-0-6 · 子步骤 4）

里程碑通知是可选增强：`memory/aidp-config.yaml` 的 `notify.enabled=false` 或 `notify.channels` 为空时，
交互式与 `/loop` 无人值守一律静默跳过播报（`notify.py` 退出码 3 同义），不弹窗收集、不阻塞测试主流程。
报告落点恒为本地 `docs/reports/{V}/`，无需询问，故不存在"报告落点未配置"的真空。


## 环境探针档案（Phase 3.2.8 / 0.0.5）为什么值得单独存一份

同一版本、同样 145 条用例、同一执行内核，下游连跑三轮的实测：

| 轮次 | 耗时 | 工具调用 | 每用例均摊 |
|---|---:|---:|---:|
| 首测 | 7.94h | 153 | 197.1s |
| 复测 1 | 2.21h | 131 | 54.8s |
| 复测 2 | 0.44h | 108 | 10.9s |

**耗时相差 18 倍，工具调用次数只相差 1.42 倍。** 三轮唯一的实质差异是：后两轮由编排器
在 prompt 里喂入了上一轮的环境结论。

⇒ 瓶颈不在"执行动作"，在**每个新 build 的执行体都要从零重新摸索环境**。而每轮摸出来的那批
事实（驱动通道限制、鉴权头形态、未登录的真实响应形态、哪类取证可用、元素定位方式）
**与用例无关、只与环境有关**，是环境常量——一次探明就该长期复用，此前却只活在当轮 notes 里。

为什么不并进 `01_测试环境与账号.md`：那份是**配置**（地址/账号/连接，人填、约定 38 归档），
本档是**行为事实**（机器实测所得、随环境演进、可被后轮推翻）。两者生命周期与写入方都不同，
合成一份会让人填的配置被机器追加内容淹没。

## `RENDER_MODE` 为何必须落 tick 命名空间

`RENDER_MODE="${TESTPLAN_RENDER_MODE:-headless}"` 是普通 shell 赋值，而它的消费点全在
**别的 Bash 调用**里（本片 0.1.4 的驱动选择表、`phase-2-1.md`、`phase-3-4.md` 两处）。
围栏之间 shell state 不共享 → 回读恒落 `FALLBACK_DEFAULT["RENDER_MODE"]="headless"`。

于是 0.0.5 明明已正确解析测试方案并落了 `TESTPLAN_RENDER_MODE=headed`，
「有头」这条**显式声明在确定性层完全失效** —— 断的不是解析，是解析之后的这一跳。
同款形态见 `DECLARED_REMOTE`（修复补上了解析、漏掉了持久化，净效果与修复前一致）。


## 禁改用户级/全局 MCP 配置的两条反模式（phase-0-4.md 的外置正文）

- ❌ **去改任何用户级 / 全局 MCP 配置来切远程地址** —— 含 0.1.1.4 禁改清单（`~/.claude.json` 的 `--scope user`/全局注册、`~/.claude/settings*.json`、历史遗留 `~/.claude/plugins/` 下 marketplace `.mcp.json` / 缓存 `.mcp.json` / `plugin.json` manifest）下任何 chrome 配置。它们 server 名往往是通用 `chrome-devtools`（不是 `chrome-{git_user}`）、用户级/全局共享，改它污染本机所有项目；远程地址**只能**写**项目根 `.mcp.json`**（`--scope project`，启动自动加载，见 0.1.1.4）

- ❌ **"用户级/全局那份看起来已经对了，那真正生效的源一定在别处" → 顺藤摸瓜去找/改用户级/全局 MCP 配置或历史插件缓存** —— 这是最隐蔽的越界：一旦发现某个用户级/全局配置 IP 不对（或"已对但运行的 server 仍连错 IP"），**禁止**沿着"找权威启动源"的思路逐个翻 `~/.claude.json` / `~/.claude/plugins/` 下的文件去改。**唯一正解**永远是：写/合并项目根 `.mcp.json`（server 名 `chrome-{git_user}`，`--scope project`）→ 重启 Claude Code（自动加载，无需 `--mcp-config`）→ 退出本命令等重启后重跑（见 0.1.5 分支 B）



## 未收敛时的重测节流（去重门第六个条件）

未收敛时 `aiauto_test_unconverged_streak ≠ 0`，且 Phase 3.7 整步跳过 ⇒ `ai_report_finalized` 不写，
于是去重门前两条判据**双重**不成立——每个 5 分钟 tick 都会对**完全没变的代码**重跑一整套用例
（1~3 小时级）。而一次修复往返（autopilot 10m tick 派 `/sprint-bugfix` → CICD → 就绪探针）
要 20~40 分钟，期间 streak 每轮 +1。新 build 铸出时 streak 若不清零，第 2 个修复轮就可能撞上
冻结阈值 10，而 `retest_auto_cap` 的自动修复配额根本没用完。

表象是报告写「连续 10 轮未收敛，请人工看测试结果」，真相是重复测了同一份未修复的代码。
故两处配套：① 去重门加「已认领待自动修复且无新部署即跳过」；
② `phase-3-4.md` 铸新 build 时 `del aiauto_test_unconverged_streak`（新 build = 新一轮）。


## 交接计数器为何只增不减（handoff_fail_streak）

`bump` 写在 `phase-0-6b.md`，而该分片**只在 `NEED_HANDOFF=1` 时才被 Read**。把清零也写在同一份
分片里，等于「交接成功后那条指令永远加载不到」——计数器只增不减，三次**成功**交接照样累到阈值，
按 `handoff-exhausted` 冻结；而该原因属 `autopilot_unfreeze.py` 的 `_HUMAN_ONLY`，永不自动解冻，
且顶层 `aiauto_blocked_reason` 非空会让 autopilot Phase 2 判「测试链路不存活」，把上一版一起冻上。

故清零落在两个**成功分支**：`phase-0-6.md` 的「✅ AI执行报告骨架就绪」与 `phase-3-3.md` 的
「✅ 完成核验」，`phase-0-6b.md` 只保留 bump。


## 解冻判据为何不得内联

此处曾内联一份 `case` 复述 `freeze_reason` 枚举，与 `autopilot_unfreeze.py` 的枚举出现 5 项差集
（内联多出 `cicd-auto-trigger-off` / `config-missing` /
`prd-missing`）——两套判据各自演进，正是「冻结分类」明令禁止的
形态；上一次内联复写直接让 `unconverged` 整类漏在 case 之外，那一档冻结永不解冻。


## DRIVER 认领即删

`DRIVER` 的唯一读回通道是 `autopilot_tick_flags.py` 对 baseline `versions.<V>.driver_actual_pending`
的回落，而 Phase 0.6 认领后会把该字段 `del`。于是 `REPORT_ENABLED=1`（**正是产官方 build 报告的那条路**）
下 0.2 之后 `${DRIVER}` 恒空、`IS_MCP=0`：远程无头轮不再拆「必须有头」延后集、3.5 切有头提醒永不触发、
收尾门 3i 的报告如实性比对一侧无源。standalone 不走 `del`，故**只在"要出官方报告"时坏**——最难发现。
修法：与 `MODE` 同款，在 0.2 就把 `DRIVER` 落进 tick 命名空间。


## 阻塞原因的清除归属

tick 起始那行 `del aiauto_blocked_reason` 执行在**版本解析之前**，无从判归属。无条件 del 会抹掉
开发链路对**别的版本**写下的阻塞标记（该值形如 `frozen:<reason>@<version>`）。

抹掉后 autopilot Phase 2 会从 `test_loop_missing_streak`（阈值 3）翻到
`prerelease_test_hold_streak`（阈值 12）——熔断从 30 分钟拖到 2 小时；且 reason 从心跳解冻类
换成部署/HEAD 解冻类，**解冻信号也跟着换错**，告警文案写「测试链路存活但未收敛」，
而真相是一次都没测过。

故只清两类：全局类原因（`chrome-unavailable`，对任何版本成立）与空值；
其余带 `@` 后缀的版本类原因原样保留，交由写它的那条链路自己清。

## 2.0.0bis 增量用例可见性 —— 为什么执行全量、报告却必须分得清

**执行全量是对的，不该改。** 每定一个新轮次，auto-test-runner 从整个用例集重建 tasks.md；
增量改动最容易打破的恰恰是既有功能，只测增量会把回归缺陷整类漏掉。约定 33 的
「跨版本回归继承」也是同一个方向——越往后越往全量走。真正按增量收敛的只有**失败复测轮**
（上一轮 `fail`/`block` 走 self-heal），那是另一条轴。

**但报告分不清增量，这是真缺口。** 约定 22 的用例增量级联之后，新用例写进 `02_*.md`，
在文件里和三个月前那批长得一模一样。于是报告说「114 条、通过率 100%」，
而看的人**无法验证本轮那 5 条新功能到底有没有对应用例、跑没跑、结果如何**。
全绿看着安心，却证明不了增量被覆盖过。

报告模板里本就有一行 `| 测试类型 | 全量 / 增量 |`，但全库**没有任何生产方**——
`gen_report.py` 对它零命中，命令端也没有谁去填。字段在、无人写，看着有其实没有，
与本仓反复栽的那类失效同族。`incremental_cases.py` 就是补上的那个生产方。

**判据为什么用 git 而不是在用例册里打标记**：打 `[增量]` 标记要改 `dev-manual-testcase`
的产出格式，且标记漏打就**永久失真**——而 git diff 是确定性的，
补不补标记都算得出来。只认**新增的用例标题行**、不认正文里的顺带提及：后者会把
"某条用例的步骤里引用了 TC-013"误算成新增，而那类误算的方向是**虚报覆盖**
（说测了其实没测），比漏报更危险。

**两条边界**：
- **无基准判 `no-anchor` + 空集**，⛔ 不拿"版本起点"顶上——那会让第一轮把全部用例都报成
  "本轮增量"，是虚假的精确，比诚实地说"没有基准"更糟。
- **锚点只在该 build 首次记录时推进**：同一 build 的复测轮若把锚点推到 HEAD，
  第二轮起增量集恒空——而复测轮恰恰最需要知道"本 build 的增量是哪几条"。


## 3.2.5 ⓪ 门的阻断白名单为什么必须写 rule 实名

`check_result.py` 的 `_issue(issues, level, rule, msg)` 往 `issues[].rule` 里写的是
**snake_case 实名**（`evidence_string_item` / `runtime_error_incomplete` / `bad_env_flag` /
`empty_target`），文档里的 `I1`/`I3`/`I4`/`I6` 只是**叙述编号、从不出现在数据里**。

白名单写成编号时的失效形态特别隐蔽：判据是 `rule in B or level == 'Critical'`，看起来有两条腿。
但这四条**全是 `Important` 级** —— 第二条腿也兜不住。于是这道门对它本该抓的四种情况
**100% 失效**：evidence 被写成字符串数组时不置 `SHAPE_BAD`，命令继续跑 artifact 兜底、
静默拷 0 张图，而轮次仍 judged 完成。这正是该门注释里点名要防的那件事，它自己却做不到。

**通则**：凡是拿脚本 `--json` 的字段做白名单，白名单的值一律从**脚本源码**取，
不从描述该脚本的文档取 —— 文档编号与数据实名是两套命名，且没有任何东西保证它们同步。

---

## yield 点的 streak 阈值在「无唤醒源」轮次里恒不可达

各阻塞处置门的统一形状是：`bump <streak>` → `if streak ≥ 3 then 冻结 fi` → 发 #4 → `exit 0` 让位。
这套设计默认"下一 tick 会来接"——streak 靠**跨 tick 累积**才够得着阈值。

`HAS_WAKE_SOURCE=0` 的轮次（交互式 `--once`、autopilot 的 P0-4 补测与 2.5.1 自愈交接反向
invoke，都是 `--once --unattended`）**没有下一 tick**。于是 streak 永远停在 1、
`[ "$N" -ge 3 ]` 恒假、**永不冻结**；`exit 0` 又被上游读成"这一步过了"。
净结果：测试半途而废、零 `needs_human`、零可见信号，上游拿到 `tested:false` 降级静态-only 收尾。
这比"每 tick 重撞同一失败"更隐蔽——后者至少每 5 分钟刷一张 #4。

**修法**：8 处带阈值的门一律改成 `[ "$N" -ge <阈值> ] || [ "${HAS_WAKE_SOURCE:-0}" = "0" ]`
——没有下一 tick 就**当场**按达阈处置（冻结 + 四件套 + #4）。宁可早冻一轮让人看见，
也不要静默退出让人以为跑过了。`phase-0-7` 那处不在此列：它**无条件**先写齐冻结四件套再退，
可见性已经建立，与"有没有下一 tick"无关，故标 `yield-guard: ignore`。

**配套的管道修复**：`HAS_WAKE_SOURCE` 此前在 `autopilot_tick_flags.py` 里
① autopilot 侧**未登记**（`set --command autopilot` 直接 rc=2）② **没有 `BASELINE_FALLBACK`**
（真源在根键 `autopilot.wake_source_this_tick`，`--shell` 读回恒空）。
判据本身读不到值时，上面这条守卫写了也等于没写——故三处（DERIVED_VARS / BASELINE_FALLBACK /
FALLBACK_DEFAULT）同时补齐，缺省取 `0`（fail-closed：判不出就按"没有下一 tick"走）。

---

## 本地无头优先：远程已配置为什么不构成抢占理由

🟢 **本地无头优先 — 远程已配置不抢占（铁律，见命令主体「核心理念要点」）**：上表自动探测本就"本地优先"（A/B 本机能起即 `cli`，仅本机起不来才落 C 远程）。**额外强制**：项目根 `.mcp.json` 已有 `chrome-{git_user}` 远程条目（常由 `/sprint-autopilot` 前置写好），**只是"具备远程能力"、绝不是把 `DRIVER` 翻成 `mcp` 的理由**——只要本机 Chrome 能起（含无头 `--headless=new`，无需 GUI），一律走本地 `cli` 无头。**唯一**能强制走远程的"明确强制要求" = 上一条三级优先级① 的测试方案「二·连接模式」显式写"远程" 或 用户显式指令；两者都缺时，配了远程 IP 也按本地无头跑（远端引导 0.1.5 / 远程 MCP 配置 0.1.1.4 此时不触发）。**跑测时远端不可达**（`rc=4`）→ 见 0.1.5 A0：非强制远程 + 本机可用时**自动降级本地无头 cli，不弹窗、不退出**。

---

## 运行时错误写入缺陷清单的列映射与 R-NNN 前缀

- 列映射：**序号 = `R-NNN`**（`R-` 前缀 = chrome 运行时错误，与 sprint-batch Step 6.5 写的失败用例 `C-NNN`、零散 bug `B-NNN`、用例 `T-NNN` 隔离，互不冲突，便于审计）；用例 ID = 触发用例 ID（自由巡检/登录流程类填 `运行时-<页面>`）；**问题描述加前缀 `[chrome运行时]`**（如 `[chrome运行时] GET /api/dashboard/stats 返回 500`）；严重程度 = skill `runtimeErrors[].severity`；复现步骤 = `角色 <role> 在 <页面URL> <触发动作>（详见 AI测试报告 {BUILD} 子页「运行时错误」R<N>）`；状态 = `待修复`

---

## 运行时错误对接：schema 侧已就绪的字段

✅ **运行时错误对接已就绪**：`result-schema.json` 的 `runtimeErrors[]` 必填 `type`/`message`/`severity`，`detail`/`artifact` 可选（⚠️ 消费点读 `message` 不读 `detail`，后者已降为可选、只读它会拿到空）。另有 `precondition_probe`（区分「数据缺位」与「探测失败」的唯一依据）等可选字段，命令端**按需消费、不重算**。形状由 skill 硬门 `scripts/check_result.py` 校验。Phase 2.4 **直接消费** `results/{TC-ID}.json` 的 `runtimeErrors[]`（不再命令端二次扫描），只做 AIDP 特有的升级 bug + 回写问题汇总清单。

---

## 0.0 拉码冲突的顶层熔断记账

**`LOOP_UNATTENDED=1`（测试链路专属顶层熔断）**：rebase 冲突发生在 `TARGET_VERSION` 解析**之前**，无版本上下文可写 `versions.{V}.*`，故走 `autopilot_fail_handle.py --preflight --command aiauto-test`，记测试链路专属顶层键 `aiauto_preflight_fail_streak` / `aiauto_preflight_frozen_at` / `aiauto_preflight_fail_reason`。与开发链路的 `preflight_*` 分键：两条链路的拉码失败是独立事件，共用计数会让一条链路的冲突把另一条链路熔断。未达阈只记账退本 tick；达阈置 `aiauto_preflight_frozen_at`、发 #4 并写本地告警台账，之后静默退出。`fetch`/`pull` 成功一次即清零三键。

---

## 「研发自测/ 配置优先」总则

★ **「研发自测/ 配置优先」总则（单一信源，下文各 Phase 引用本节，不复述）**：chrome 连接地址 / 部署 URL / 测试账号统一维护在 `docs/testing/{version}/研发自测/`（由 `/sprint-selftest` Step 3 与用例配套生成）。**字段读取成功时，对应的 Phase 0.1（chrome 地址）/ 0.3（部署 URL）/ 0.4（账号）交互收集环节自动跳过**，仅缺失或未填才回退交互式收集。开发测试环境账号明文入库（便于团队共享）；仅生产 / UAT 敏感账号用 `memory/.sprint-autopilot-credentials.json`（约定 38）。

（收口写法）

**`LOOP_UNATTENDED=1`**：见上节「0.0 拉码冲突的顶层熔断记账」（测试链路专属 `aiauto_preflight_*` 三键）。

## 冻结快照 HEAD（`unconverged` 为何必须一并写 `unconverged_frozen_head`）

`unconverged` 的解冻走「冻结后有人提交过」这条证据链，优先读 `unconverged_frozen_head`。
不在冻结那一刻快照它，解冻判定就只能顺次退到 `last_autopilot_head`（多数部署形态下恒空）、
再退到 `git log -1 -- code/` 兜底 —— 而 7×24 下 autopilot 正为**别的版本**不停提交 `code/`：
兜底判据于是把本版**误解冻**、原地重撞同一处；反过来项目进入静默期时它又永远等不到证据、
变成永久冻结。两个方向都错，且都不会报错。

所以它不是「多写一个字段」，而是这条解冻路径的**唯一可靠依据**，必须与四件套同批写入 ——
分两次写会留下「已冻结、但解冻判据缺失」的中间态，那个中间态一旦被 tick 边界切断就固化了。

## 复测轮为何必须逐条复评上一轮的 block

每轮测试各自独立跑一遍全量用例集，**没有任何东西要求它回头看上一轮标了 block 的用例**。
于是 block 会**原样沉淀**：下游实证一轮标了 13 条 `precondition-unmet`，复查发现其中 7 条
只要在相应平台造几条数据就能解锁（项目本就有三平台写权限与产品授权），而 5 条造数后当场转 pass。

要害在于 `precondition-unmet` 这个值把四种性质完全不同的情形合并了：**缺数据且执行者有权限造**
（该去造，不许标 block）、**构造需不可逆操作**（合法）、**页面形态结构性不存在**（合法，且本该在
规划期就识别出来）、**通道不可达**（合法）。只有后三类站得住，而第一类被同一个枚举值盖住之后，
「这条真的造不出」与「执行者懒得造」在机器上完全同形 —— 没有任何门能区分。

枚举拆分以 `auto-test-runner` 的 `result-schema.json` 为单一信源；能在本链路做的是
**堵住沉淀**：复测轮把上一轮每条 block 拿出来逐条判，结论写进 `note`。
三选一里「仍 block（原因不变）」是合法答案，所以判据不能要求结论必须变，只能要求**结论必须存在**：
收尾门 3q 对「整条没出现」与「仍 block 却 `note` 为空」判 FAIL，对「`note` 与上轮逐字相同」
上浮 DEGRADE 告警（可能是复评后确认不变，也可能是照抄，机器分不了，交人看一眼）。

## tick 级信号为什么必须按链路分键（`aiauto.*` vs `autopilot.*`）

`LOOP_UNATTENDED` / `HAS_WAKE_SOURCE` 这两个 tick 级信号，两条 loop 一度共写同一个
根键 `autopilot.*`。两条 loop 周期不同（开发链 10m / 测试链 5m），autopilot 的一个 tick
内必然穿插 1~2 个测试 tick —— 于是只要有人手工跑一次**交互式** `/sprint-aiauto-test`
（不带 `--unattended`），那个键就被写成 0；autopilot 后续分片读回 0，
**在无人值守 tick 内退化为交互式**，命中 `AskUserQuestion` 挂死，且每个 tick 重犯
（无人可答、也无人知道）。`usage-guard.md` 早就写过这个失效形态，只是当时以为触发源
只有 prompt 文本，没想到另一条 loop 自己就是触发源。

分键后：写方各写各的 `aiauto.*` / `autopilot.*`，读方由
`autopilot_tick_flags.BASELINE_FALLBACK_BY_COMMAND` 按 `--command` 解析。
⚠️ 根键与 tick namespace 两处都要写：`cmd_set` 落的是 namespace，
namespace 为空时 `--shell` 才回落到根键——只写一处会让断点续跑的 tick 读空。

## 「选不出被测版本」这个出口为什么也必须回写 `aiauto_blocked_reason`

本步开头会**乐观清空**阻塞原因，各门在自己的 early-exit 前负责回填 —— 这条规矩写在
`phase-0-6.md` 的注释里，但「baseline 中无当前开发版本」这个出口当初漏了。

漏写的后果不是"少一条记录"：心跳在 `phase-0-1.md` 就已经刷新过了，于是开发链路读到的是
**「心跳新鲜 + 阻塞原因为空」= 测试链路健康**，据此走 prerelease 暂缓而不是熔断。
两条 loop 都在刷屏、一条用例没跑，要等十几个 tick 后才按一个错误的原因冻结。

这正是 `phase-3-5.md` 与 `phase-3-7.md` 两处注释反复警告的双链路互等形态，
只是那两处盯的是别的出口。

## `no-testable-version` 为何必须可清

它由本链路自己在「无可测版本」分支写入，却是一个**无版本归属**的全局串：读侧 `ceremony-gate`
取不到 `@版本` 就按「整条测试链路已死」处理。

同挂两条 loop 时它**几乎必然被写一次**——测试 tick 一定早于 autopilot 跑完 Phase 3，
此刻 `current-version` 返回空。若它落进清除逻辑的 `*)` 保留分支，就再也没有人清得掉：
autopilot 每 tick 累加 `test_loop_missing_streak`，3 tick 后按 `config-missing`
冻结一个**健康**的 build，告警文案写着「测试链路未挂载(缺 /loop 5m …)」——
而那条 loop 从头到尾一直好好挂着。

铁律：**谁写的谁必须能清**。本链路自己写的阻塞原因，一律进乐观清空白名单。


## 驱动运行时记录与声明读回

- **声明读回**：`DECLARED_REMOTE` 由 Phase 0.0.5 在另一分片算出并落 tick 命名空间。分片间 shell state 不持久，只靠 `${DECLARED_REMOTE:-0}` 会恒落 0，`MODE=remote` 分支结构上不可达，「驱动由声明决定」在确定性层失效，故 0.0.7 先 `--shell` 读回。
- **为什么在选定驱动的这一刻落盘**：`driver_actual_pending` 的全部价值在于它是**独立于报告的第二信源**。若等到出报告时一并写，两者同源同刻，报告填错它也跟着错，收尾门 3i 的比对恒等式成立、失真照样放行。
- **为什么先写版本级待认领字段**：0.0.7 早于 Phase 0.6 解析 `BUILD`，此刻 build 号可能未知；`builds` 是对象数组、写不进点号路径（会造出畸形嵌套键且被 `|| true` 吞掉）。故先落版本级 `driver_actual_pending`（一定写得进），BUILD 解析后改挂 build 名下并清除。引用任何未赋值的 build 变量会让整行静默不执行，3i 永远只打印 DEGRADE。
- **驱动名探测**：`chrome-devtools-cli` 是技能名，实际命令是 `chrome-devtools`；按技能名 `command -v` 会误判 cli 不可用、静默降级到 MCP，报告 driver 与实际不符。

## Phase 0 信号派生与落盘

- **`HAS_WAKE_SOURCE` 决定 yield 合不合法**：交互式单次补测（autopilot 委派 `--once --unattended`）与 2.5.1 自愈交接反向调用都是 `LOOP_UNATTENDED=1`，但**没有下一 tick**。此时任一 `UNATTENDED_YIELD` 点直接退出会让测试半途而废且无结构级拦截（Stop 护栏只管 autopilot tick），autopilot 侧只拿到 `tested:false` 降级静态-only 收尾。故无唤醒源时不许 yield，本轮内重试 / 降级并如实回传。
- **版本号预解析**：Phase 0.2 才做完整版本解析，但 0.0.5 / 0.0.6 已要用 `$TARGET_VERSION` 拼测试方案路径，故先轻量预解析（同调 `baseline_edit.py current-version`）。`--shell` 已按 baseline 回落把 `TARGET_VERSION` 填成非空，用 `:=` 会让 `--target` 在 0.0.5/0.0.6 失效、前后半段跑在两个版本上，故显式覆盖。
- **`DECLARED_REMOTE` 由本步置位**：0.0.7 按「`HAS_OWN_REMOTE` 且 `DECLARED_REMOTE`」判远程；本步不读「二·连接模式」则该变量恒 0，驱动变成硬编码本地。
- **`REQUIRES_LOGIN` 唯一生产者**：缺它时 `--shell` 恒回落默认 `1`，无登录系统的项目在 7×24 下必被 `account-missing` 冻结。
- **`testplan_deploy_url` 必须落盘**：Phase 0.7 在另一个 Bash 调用里按第 1 优先级读取；只置 shell 变量则恒空，研发自测里归档的测试环境 URL 白归档。
- **环境探针档案**：喂给执行子 Agent 上一轮的环境结论可显著缩短逐用例耗时（首轮需从零摸索环境）。

## 0.2 取版与去重门注释

- **心跳写入点在 0.0.0**：0.0 拉码冲突 / 0.1.1 chrome 缺失 / 0.1.5 远端引导三处 early-exit 都在 0.2 之前。心跳写在 0.2 会停在最后一次进 0.2 的时刻，autopilot 判「测试链路未挂载」并冻 `config-missing`，而该 reason 的解冻判据正是心跳，双向卡死。
- **`--target` 分支同样落盘 `TARGET_VERSION`**：tick 命名空间为空时，下游 `--shell` 按回落表取到 autopilot 正在开发的版本，报告 / `aiauto_tested_at` / `builds[].status` / 冻结与 streak 全部写进错版本，「强制锁定」失效。
- **默认取版**：「当前开发版本」= `phase_beta_done_at` 非空且 `internal_released_at` 为空（autopilot 跑完部署、尚未准发布），判据单一信源 `baseline_edit.py current-version`。
- **冻结契约**：四件一次写齐、只经 `baseline_edit.py`；解冻路径见 `autopilot_unfreeze.py::aiauto_probe`；冻结前先收口本 build 的 AI执行报告（本命令是其关闭方 R-4）。

