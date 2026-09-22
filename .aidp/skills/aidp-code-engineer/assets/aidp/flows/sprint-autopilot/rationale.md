# sprint-autopilot · 理据 / 根因 / 反例（人类维护者参考 —— 执行期【不加载】）

> 本文件收纳 `/sprint-autopilot` 各条不变式与硬门背后的**为什么 / 根因 / 历史事故 / 反例**。这些对**人类维护者**理解"为何有这条规则"很有价值，但对**执行期的模型是噪音**——在命令主体里与祈使句混排会稀释"该做什么"的信号（约定 30 已把版本戳赶出执行路径，这里对"为什么"用同一纪律）。
>
> **谁读**：维护者改规则前读本文件理解意图；**执行期模型不读本文件**（命令主体只留精瘦祈使句 + 指向 flow 的指针）。
> **渐进迁移**：命令主体与 `phase-*.md` 里目前仍夹带的 `**Why**` / `根因` / `本次反馈` / 历史事故叙述，会**逐步搬来本文件**，让执行路径只剩可核验的祈使清单。本文件随迁随长。

---

## 顶层不变式的根因（速查）

- **入口级仪式不变式**（六项：不中途征询 / auto-push / 铸 build+AI执行报告 / 里程碑通知 / 委派 AI 测试 / 收尾门）——根因：这些保证此前**耦合在 Phase 2/3 内部**，任务被判"增量/小改/非版本"绕过仪式框架时被一并绕过、连告警都没有。故上提为**入口级、路径无关、结构级**（脚本兜底 + 逐项打印"应产 vs 实产"）。诚实边界：结构级兜底**收窄缝隙 ≠ 替代执行体守规**。
- **阶段推进不变式**——根因：模型跑长流程倾向"汇报进度/等确认/阶段性小结"后停手交还控制权，导致一轮只推进一个 Phase。
- **推送即监听不变式**——根因："推了就当完事"→ 部署未就绪测试链路空转。分 A/B 两路径避免主部署被双探针 / 流水线未触发时过早探针误超时。
- **绝不停下问"继续"**——根因：把"回复『继续』我接着建 XXX"当一次输出来结束轮次，把本可一次做完的工作切成逐批等人。

## Phase 0 相关根因（对应 `phase-0-*.md`）

- **0.0.0 最先派生 `LOOP_UNATTENDED`**——根因：0.7 收口钢门在 `IS_LOOP_CONTEXT`（原 Phase 1.3 才派生）之前读到的 `LOOP_UNATTENDED` 恒为 0、被当交互式，`/loop` 无人值守首跑会被 gate 误判 `exit 1` 阻断、无人可答成死结。
- **0.6 收完即禁中途阻塞**——根因：字段缺失若拖到 Phase 2/3 中途才 `AskUserQuestion`，无人值守下挂死。故一切交互前置到 Phase 0 一次性收齐。
- **0.2 test-intent 专项防绕过**——根因："识别到只做测试 → 静默跳过 Phase 0 配置收集与通道就绪打印"正是"通知渠道全就绪却整次零推送"的根因。

- **`config-missing` 必须按心跳解冻（双侧死锁）**——根因：该冻结由 Phase 3.9 / Phase 2 在「本版需实测但测试链路无心跳」达阈时写入，其 `#4` 通知明写「补挂 `/loop 5m /sprint-aiauto-test --unattended` 后自动解冻重测」。但两条既有解冻路径都够不着它：① autopilot 已把该版剔出候选 → **永不再为它部署**，"新部署"路径不可达；② 测试链路侧的配置类解冻只认 `docs/testing/**/*.md` 与 `skills/*/config.json` 的 **mtime**，而"挂 loop"这两者都不变。于是用户照着通知提示补挂了 loop 也解不开，只能人工清 baseline。

## 分片压缩后保留的判据根因

Phase 0.1 每 tick 都会检查工作区，但 `preflight_fail_streak` 还供后续 PRD、遗留 Sprint 和 0.7 收尾门复用。若工作区干净就无条件清零，后续失败永远无法累计到冻结阈值，通知可能每 tick 刷屏。因此只能按 `preflight_fail_reason` 清理本段自己的失败。

Phase 3.4 必须按 build 起始提交 `push_base_ref` 判断前端改动；回退 `HEAD~1` 会漏掉跨多个 commit 的改动，部署覆盖门可能静默放行。`DEPLOY_MODE`、`SKIP_DEPLOY` 和 `WILL_BROWSER_TEST` 必须从 baseline 回读并写回，不能依赖不同 Bash 工具调用之间的 shell 变量。`--skip-aiauto-test` 是用户显式裁剪，关闭方判定要消费该值。静态-only build 由 autopilot 关闭，必须写 `ai_report_finalized`，否则 Stop hook 与准发布门误判报告未完成。

## Phase 3 相关根因（对应 `phase-3-*.md`）

- **3.2.1 出口写 `3.2.1-probe` 而非 `3.3-audit`**——根因：Step A–C（`phase-3-6.md`，触发部署 + 等流水线）与 Step D（`phase-3-7.md`，就绪探针）分属两个分片，探针轮询可长达 `cloud_ready_timeout_seconds`。原出口直接写 `3.3-audit`、摘要还写着"探针就绪、`last_deployed_at` 已写"——tick 在探针中途中断，下一 tick 就从 `3.3-audit` 续跑，**整段就绪探针被跳过**：`last_deployed_at` 永不写入 → 测试链路无从触发；Phase 2 的 0a 门又因它为空而累计 `prerelease_deploy_block_streak`，最终把一个其实部署成功的版本误冻结成「部署就绪从未通过」。
- **Step D 必须有自己的出口**——根因：`phase-3-7.md` 原先 0 处 `run-state`，游标只能停在 `3.2.1-probe`，探针过了也推不动，下一 tick 从头重探、`last_deployed_at` 反复重写、Phase 3.3 永不开始。
- **test-only 的 `next` 写 `3.1.5-build` 而非 `3.4-finish`**——根因：铸 build 是 test-only 也不豁免的强制仪式；写 `3.4-finish` 会让崩溃/compact 后的恢复直接跳到 3.4、never mint build，`$BUILD` 为空使仪式门 `check` 缺 `--build` 返回 2，整轮收尾判死。

## Phase 3.4 收尾门相关根因（对应 `phase-3-9.md`）

- **`--stage` 分流（final vs skeleton）**——根因：收尾门若一律按 `final` 校，会在浏览器路径上**要求尚未产生的产物**（exec 交付台账 + 测试 SPA 都要等测试链路 Phase 3.7 才写）→ 时序死结、每 tick FAIL。故按 build 关闭方分流：静态-only 时 autopilot 自己就是关闭方、已在 step2 经 `emit-report` 写了交付台账 → `final`；浏览器路径下 autopilot 只产 exec 骨架 → `skeleton`，只校骨架 + 无 markdown + 终审 + 通知台账。autopilot 侧**永不产测试 SPA / test 交付**，测试产物统一归测试链路 Phase 3.7 的 `final` 门校。`--will-browser-test` 传**真实值**而非写死 0：gate 里受它门控的三项（3b 测试 SPA / 3b2 测试链路运行证据 / 3c 的 test 交付）都另有 `--stage final` 守卫，而 autopilot 在浏览器路径下恒 `skeleton`，故行为不变；传真实值只是不让参数与事实相悖，免得后来人据此以为 autopilot 从不做浏览器测试判定。
- **`EXPECT_CARDS` 必须与各通知节点实际发送条件逐条同源**——根因：期望集里只要出现一个本轮"明确不发"的通知节点，台账就恒缺 → 收尾门每 tick FAIL → `dev_fail_streak` 3 次即冻结版本。历史事故：静态-only 路径下期望集既留 `#1d`（该路径不部署、不发）又加 `#3`，必缺。**注意 `#1b` 与 `#1` 不同**：`#1` 规划开始仅在真跑规划时发，`#1b` 规划完成由 `phase-3-3.md` step 3 **无条件**发（含"复用已有规划"），故 `#1b` 恒期望——曾被误写成与 `#1` 同条件，与发送侧相反。
- **`--stage final` 的终审判据必须带 build 号**——根因：用 `version-output-audit*.md` glob 会被 `/version` 内部审计留下的 `-YYYY-MM-DD.md` 顶掉，使 autopilot 终审"没跑也能过"（`PLANNING_DONE=1` 跳过规划、上游文件早已在时尤其如此）。
- **收尾门失败禁止裸 `exit 1`**——根因：`/loop` 会每 tick 重撞同一处，零 `#4`、零 streak、零冻结，无人值守下表现为静默空转。故结构性不可自愈（SPA 模板 / `emit-report.py` 缺失、终审子 Agent 每轮失败）归口「失败处置」：`dev_fail_streak` + `dev_fail_phase="3.4-ceremony-gate"`，未达阈记账让位本 tick（不逐次发通知，免得正常重试期每 10 分钟一张红色告警）、达阈按「冻结字段写入契约」冻结并发 `#4`。**瞬态漏写**（模板齐全、只是这一轮漏产）仍走"就地补建 + 复跑直到全 ✅"，不累 streak。

- **Phase 3.2 出口游标必须按 `deployment.mode` 分流**——根因：`3.2.1-deploy` 的**唯一消费方**是 `phase-3-6.md`，而该片开头就声明 `manual-script` / `mode=local` / `mode=none` 均不进入。此前出口无条件写死 `3.2.1-deploy`，于是**所有未接入 CICD 流水线的项目**（`mode=none`/`local`，或 `git-push` 但未配置 `cicd.pipelines`）在最后一个 Sprint 关闭后都会停在一个没人消费的游标上：下 tick 被 1.3bis 续跑门强制唤起 → 又路由到不适用的分片 → 原地打转，且因通用 stuck 熔断尚未落到执行分片而**零告警**。

- **无人值守禁止"范围·进度确认门"的 catch-all**——根因：研发执行计划的全部 Sprint 是一个**不可分割、必须一次跑完**的整体，用户启动 autopilot 即等于"把全部做完"的授权。模型跑长流程时倾向以"工作量大 / 稳妥起见"为由，自发弹出「我全自主做完 N 个 Sprint，还是先做某个 Sprint 阶段确认？」这类问句——它不在任何被点名的交互门清单里，却同样会在 `/loop` tick 内挂死。故禁令必须写成 catch-all 而非枚举。**注意与"逐 tick 推进"区分**：禁的是"分阶段**征询**"，不是"分 tick **自动**推进"。
- **★ `HAS_WAKE_SOURCE` 与 `LOOP_UNATTENDED` 必须分开（yield 停摆根因）**——根因：`UNATTENDED_YIELD` 的前提是"**还有下一 tick 会来接**"，但判据一直挂在 `LOOP_UNATTENDED` 上。而后者由三路 OR 派生，其中 **`--unattended` 只表示"没人能回答弹窗"、完全不表示"有人会再叫我"**：`--once --unattended`（文档明写的"无头跑一轮"）恰好命中——跑完一个 Sprint 就 yield，然后**永远没有下一 tick**。实测事故：实际项目中跑完即退，`run_state` 停在 `next_phase=3.2-dev / next_sprint=016`，21 个 Task（约 84h）停摆；更糟的是收尾还反过来提示用户"要无人值守请挂两条 loop"——**一个自称"7×24 全自动开发编排器"的命令，把没干完的活儿丢回给了人，且看起来像正常收尾**。故拆出独立的 `HAS_WAKE_SOURCE`（只认 `/loop` 上下文 与 `--no-loop` cron 两路），**无受托人即不许 yield，改为本轮内连跑到底**。判据一句话：**"没人接的托付不叫托付，叫弃置"**。

- **★ 阶段完成判据：产物落盘 ≠ 活已派出（实际项目实跑根因）**——21:31:34 派发规划子 Agent、**7 秒后**（21:31:41）就写 `phase_completed_at` 并推进 `next_phase`，而四类文档 21:46 才成文、`version-auditor` 23:08 才判出 2 项 Critical。开发链路早已按"规划已完成"跑掉 3 笔提交，最终**「计划验收标准与已交付代码相反」**。`phase-3-3.md`「⛳ 本 Phase 出口：`run_state` 写盘」段规约本身写对了（子 Agent **回传后**才写 `run_state`），但它只是散文、拦不住"明知未完成仍推进"。连带失效：`run_state` 此后再没更新过（终态 `current_phase` 仍停在 `3.1-planning`、`phase_enter_count:1`），通用 stuck 检测因此彻底失灵；`builds[]` 空导致一切按 build 取值的门空转；`pending_actions` 挂着一项未完成动作 7 小时无人处置。**修法**：判据落在唯一写入口 `baseline_edit.py run-state`——`phase_summary` 出现进行时自述即拒写（`exit 1`）。**判据取"摘要措辞"而非"耗时"**：耗时阈值在续跑/缓存路径上会误伤（合法的秒级完成确实存在），而"执行中/已派发"是执行体自己写下的、不会假阳性。**且只收进行时信号、不收「未完成/pending」**——"无未完成动作""pending_actions 已清空"都是正常完成摘要，收进来会把合法推进拦死（假阳性卡停流水线，比漏判更贵）。
- **★ `entry_mode` 粒度错配（实际项目第二次实测）**——`autopilot_entry_mode` 是**版本级**字段（`versions.{V}.autopilot_entry_mode`），而 entry_mode 实际是 **build 级属性**：同一个版本里首轮 `full`、复验轮 `test-only` **共用一个槽位**，后写覆盖先写。于是 `{{AIDP_HOME}}/hooks/autopilot-stop-guard.py` 拿着"版本槽位的当前值"去校"另一个 build"，`_derive_expect_cards()` 算出的通知集自然错——实测表现是**要求补发两条内容必然为假的里程碑通知**（那一轮压根没发生的里程碑）。
  **这与此前那次 `--entry-mode` 死锁是同一失败形态的第二形态**：上次是"回退链缺一环"（hook 不传 → 通知集按 full 算），这次是"回退到了一个**粒度不对**的槽位"。**粒度对不上时，回退链再完整也取不到正确值**——修完回退链就以为这个字段安全了，正是本次复发的原因。
  **修法**：Phase 3.1.5 铸造时把当轮 `ENTRY_MODE` 落进 `builds[].entry_mode`；取值链改为 **显式 `--entry-mode` > `builds[].entry_mode` > 版本级 `autopilot_entry_mode` > `full`**（版本级降为老 baseline 的向后兼容回退）。**复用既有 build 时只补不覆盖**——一个 build 的应发通知集由"它是怎么开始的"决定，中途换 tick 模式不改变已经发生过的里程碑；同一段代码顺带回填没有该字段的存量 build。
- **★ 收尾门只校产物、不校义务清算（实际项目实跑根因）**——全流程跑完、AI 测试 114 用例 0 失败，但发现 4 条缺陷含 1 条 P1（金额显示放大 100 倍、余额不足拦截失真）；收尾门 1~3i 全过（它们只问"东西产出来没有"），执行体遂认为"流程已完备、剩下的该问人了"，弹窗问用户「这条缺陷怎么处置：① 现在修+复测 ② 登记下版修 ③ 只修不复测」——直接违反「修不修从来不是选项」。**三处规则缝隙叠加**才让它显得合理：① 闭环判据读 `auto_fixable_pending`，而该字段此前只在**有失败用例**时才被想起来置真，`fail=0` 时天然为假 → 判定"闭环不触发"（可"用例全通过但有运行时错误 ≠ 绿灯"这条规则同时承认该状态存在，两处规则都认它、却没一处规定它触发闭环）；② 禁令是**举例式**（列举「是否自动修复复测」等具体措辞），换个问法就绕过去了；③ 闭环触发点绑 `/loop` tick 边界，**交互式单次调用没有"下一 tick"**、闭环无处挂载——这与当初为"交互单次没有第二条 loop 跑测试"补 P0-4 是完全对称的缺口，却一直没补。**修法**：① 分流输入明确为"本轮全部缺陷"（含运行时错误/观察发现），`fail=0` 不是跳过理由；② 禁令改判定式——**判据看选项集合、不看问法**，出现"不修/延后修/下版修/只修不复测"任一项即违规；③ 补 P0-4（交互单次由本次调用自身跑完闭环）；④ 收尾门加 3j/3k/3l 三项义务清算，把纪律从自律级升到结构级。**⛔ 刻意不做的事**：下游建议按 P0/P1/P2/P3 加"严重度→处置动作"映射表（P2 可不铸新 build、P3 登记不阻塞）——那等于给"不修"发分级通行证，正是本铁律要堵的。改为明写**严重度只决定顺序与紧急度、绝不决定修不修**，归类仍走 `/sprint-bugfix` 那条唯一判据（"不做这个修复，当前行为是不是错的？"）。

## Phase 1 相关根因（对应 `phase-1.md`）

- **1.3bis 续跑短路门**——根因：默认形态是**逐 tick 单 Sprint**（`phase-3-5.md` 步骤 1），跑完 Sprint-001 即 `UNATTENDED_YIELD` 退本 tick，靠 `run_state.next_sprint` 下 tick 续跑。但 1.4 在**进 Phase 2/3 之前**就 `--commit` 回写了 `tracked_files`，于是下一 tick `autopilot-prd-watch.py` 恒返回 `no-change` → `SHOULD_RUN=0` → 按 1.3 表「立即退出」，**Sprint-002..N 永不执行**；且走的是"静默退出"，连告警都没有（会被 `--no-pipeline-reason` 归成"PRD 无变化"这一**预期内无产**，看不出异常）。`invariants.md`「阶段推进不变式」早就写了「每轮开始先读 `run_state` → 直接执行该 Phase」，只是从未落到 1.3 的退出判据里 —— 不变式与执行分片脱节，是这类停摆的典型成因。
- **短路时不回写 `tracked_files`**——根因：续跑途中若重复 `--commit`，会把**期间新到的 PRD 变更**一并推平进基线，那批变更此后永远检测不出。
- **1.3ter 通用 stuck 熔断存在的理由**——根因：既有熔断（`dev_fail_streak` / `probe_fail_streak` / `test_loop_missing_streak` / `report_gate_fail_streak`）**无一例外都要求先有一次明确失败**才计数；而真实卡死常常**没有失败**（子 Agent 每 tick 回传 partial、某 Sprint 永远 close 不掉、`pending_actions` 每 tick 补不完），表现为 `/loop` 岁月静好地空转、零告警零冻结。该检测此前只写在 `invariants.md`、10 个执行分片一处没调，正犯了那份文件自己警告过的「只描述不写盘 = 状态机不存在」。
- **1.3ter 必须按退出码分流，禁止 `|| exit 0`**——根因：`autopilot_stuck_check.py` 的 `2` 是**入参/环境错**（最常见：本 Bash 块没代入 `TARGET_VERSION`，跨块 shell 变量恒空），与 `1`（真判 stuck）语义完全不同。写成 `|| exit 0` 会把 `2` 也当 stuck，于是 autopilot **每 tick 在这一行静默退出、永不进主流程**——用一道防静默死的门制造出一个更早的静默死。同理 `1` 分支的 `#4` 通知必须在 `exit` **之前**发，否则告警不可达。

> （以上为速查；完整叙述随迁移逐步补全。新增规则时，把"为什么"写这里、把"做什么"留命令/flow。）

- **★ 收尾门读错交付台账路径 + 与 pending_actions 互锁（下游实跑根因）**——① `phase-3-9.md` 曾用 `--version "$V" get report_deliveries.exec_report.access_url` 读交付台账，而台账实际落在**顶层 `report_deliveries[{build}]`**（`emit-report.py` 写盘处）：叠加 `--version` 前缀 + 少 build 这一层 = 双重错 → 恒空 → 静态-only 路径每 tick 必 FAIL → 3 tick 冻结。② 门 FAIL 时又把门自己写进 `--pending "ceremony-gate"`，而收尾门 3k 判「`pending_actions` 非空即未完成」→ **死锁**：3k 因这一项恒 FAIL、永远走不到清空它的成功分支，**即使原本缺失的产物早已补齐也解不开**。修法：路径改顶层 + build 键；FAIL 分支不再写自己，3k 侧也显式排除本门标记（双保险）。
- **★ 准发布收敛门读版本级 `ai_report_finalized`（该键全仓无人写）**——它只写在 `builds[]` 那一层（aiauto-test R-4 + `emit-report.py`）。读版本级恒得 false → 判"未收敛"恒成立 → 即使测试真收敛、报告已 finalize，也每 tick 累计 `prerelease_test_hold_streak`，6 tick 发假告警、12 tick 按 `unconverged` 误冻结，**任何版本都归档不了**。修法：按 `current_build` 取 `builds[]` 中对应条目。
- **★ `HAS_WAKE_SOURCE` 写盘却无人读回**——`phase-0-1.md` 花 7 行论证"各分片分属不同 Bash 调用、shell state 不跨调用持久"，并据此把 `LOOP_UNATTENDED` 落盘 + 三处读回；紧邻新增的 `HAS_WAKE_SOURCE` 却只写不读，消费方全部当裸 shell 变量用。叠加"无人值守下 Phase 2/3 由独立子 Agent 执行"（它从没见过 0.0.0 的派生过程），取空必然落 `0` 分支 → `/loop` 下退化成"一 tick 跑满全部 Sprint"，防上下文破 1M 的头号手段静默失效。修法：`phase-3-5.md` 步骤 0 显式读回，并要求委派时写进子 Agent prompt。
- **运行绑定不变式（`phase-3-6.md` Step A/B/C）**——只按「时间窗 + 触发类型」匹配流水线运行会盯错对象：同一分支上他人的推送、或 CI 队列里前一次运行，都可能落进同一时间窗。于是本轮 push 明明失败却被判成功（拿到别人成功的运行），或反过来把别人的失败算到本轮头上并触发重试配额。故必须用 `GIT_PUSH_COMMIT` 与运行的 `head_sha` 强绑定。
- **逐 tick 单 Sprint 为何不违反「全部 Sprint 不可分割」**——后者禁的是『分阶段征询』（停下来问人要不要继续），不是『分 tick 自动推进』。逐 tick 零人工确认、靠 `run_state` + S 状态机 durable 续跑，用户下达一次仍把全部 Sprint 做完，只是把「1 个大上下文」换成「N 个小上下文」：单 tick 主上下文 ≈ 一次委派 + 一条通知的量，而非 N 个 Sprint 之和。
- **准发布双前置门（`phase-2.md` 步骤 0）**——准发布会把版本从候选集里摘掉、此后不再为它部署。若在『部署其实没成功』或『测试其实没收敛』时归档，该版本就永久失去被修正的机会：既不会再触发部署，测试链路也不会再选中它。故归档前必须双校验，任一门未过只让位、不静默跳过。

### 本 tick 变量必须落盘 + 读回（`autopilot_tick_flags.py` 存在的理由）

- **收尾门的跨分片变量**——`phase-3-9.md` 的 `GATE_STAGE` / `EXPECT_CARDS` 依赖 `WILL_BROWSER_TEST`（3-8 派生）、`PLANNING_DONE`（3-3）、`ENTRY_MODE`（3-2）、`FORCE_REPLAN`/`NO_PLANNING`（参数）。这些分片分属**不同 Bash 工具调用**，shell state 不跨调用持久——本文件开头就论证过这件事，`LOOP_UNATTENDED` 也正是因此才落盘 + 读回，可后来新增的这几个一个都没做。取空的后果四项叠加：`WILL_BROWSER_TEST` 空 → `GATE_STAGE=final`（本应 skeleton）→ 要求测试链路才产的 SPA 与交付台账；`PLANNING_DONE` 空 → 期望集含本轮压根没发的 #1；`ENTRY_MODE` 空 → test-only 轮落进 else 建满期望集，而 test-only 下 autopilot 一条通知都不发；再叠加读交付台账那条分支。净效果 = **默认云部署路径下收尾门恒 FAIL → 每 tick bump `dev_fail_streak` → 3 tick 后按 `handoff-exhausted` 冻结版本**，与本文件早先记录的那次事故是同一形状的复发。
- **收尾门期望集为何不写静态集合**——各通知节点的实际发送条件是条件化的（#1 只在真跑了规划时发、#1d 只在真会部署时发、#2 只在非 incremental 时发），写死集合必然恒缺 → 恒 FAIL。故期望集必须与通知节点矩阵（`phase-0-5.md` 0.1bis）逐条同源派生；而派生的前提是那几个决策变量真的取得到值。
- **裁剪 flag 从来没被解析过**——`--skip-dev` / `--skip-deploy` / `--no-planning` / `--force-replan` / `--target` / `--batch-one-tick` 在参数表里写得很完整，但 0.0.0 的 `case` 只 case 出 `--unattended`/`--once`/`--no-loop` 三个，其余**全仓零赋值点**。于是「流程裁剪的唯一来源 = 用户显式声明」这条铁律，它所依赖的"显式声明"根本没被读进来：`[ "$SKIP_DEV" = 1 ]` 恒假 → `--skip-dev` 静默失效、`ENTRY_MODE=test-only` 入口不可达。这类缺陷人读发现不了——参数表、消费方、铁律三处各自都写得对，错在**中间那一环没人写**。
- **为何收成脚本而不是在分片里补 bash**——落盘 + 读回的样板代码若散写在十几个分片里，既撑爆 20480B 的分片体积上限，又会再次滋生同类手写错误（写错键名、漏落一个、默认值取反）。`autopilot_tick_flags.py` 把它收敛成三个动作：`parse`（每 tick 整段重写，不残留上轮裁剪 flag）/ `set`（只允许写已登记的变量名，拼错即报错——防的正是 `access_url` 那类"写 A 读 B"事故）/ `--shell`（分片里一行 `eval` 取回全部）。
- **尾段孤儿（0.3.4 选版为何要先看 `run_state`）**——S1 的判据是"至少有一个未关闭 Sprint"，于是**最后一个 Sprint 一 close，版本立刻翻 S2**、随即被踢出 `{S0,S1}` 的 TARGET 候选；而它的部署 / 就绪探针 / 终审 / 收尾**还没跑**。这不是理论路径：Step D 明确设计成"本 tick 未探完 → 游标留本步、下 tick 续探"（探针超时上限默认 600s），即"tick 在尾段中途结束"是被预期的常态。孤儿之后是连锁的：`last_deployed_at` 永不写 → Phase 2 0a 累计 `prerelease_deploy_block_streak` → 3 tick 后按 `deploy-unreachable` 冻结，而诊断是错的（不是环境不可达，是自己没去跑完探针）；再叠加 Phase 2 的 0T 中间过渡版本规则——只要更新版本的研发执行计划已存在（7×24 里 autopilot 自己就会规划下一版），冻结被翻转成"照常归档准发布"，于是**一个从未部署成功、从未实测的版本被静默标记为准发布**，恰好击穿 0a/0b 双门要防的那件事。修法：选版先扫 `run_state.next_phase ∉ {"", "done"}`，不论 S 态优先续跑。
- **就绪探针出口条件（`phase-3-7.md` Step D）**——出口分支读 `${PROBE_PASSED:-0}`，而该变量全仓零赋值 → 恒取 0 → 恒走 else → 探针明明过了，游标也永远停在 `3.2.1-probe`：下 tick 从头重探、`last_deployed_at` 反复重写、`pending_actions` 的 `deploy-probe` 永不清空，于是 Phase 3.3/3.4 永不开始、build 永不收口，最后只能靠通用 stuck 熔断（8 tick + 滞留 2h）冻结待人。讽刺的是 Step D 的独立出口正是为了治"游标停在 probe"才加的——出口写了，但它的条件变量没人赋值，等价于出口不存在。现改为**判定当场落盘 + 出口读回**，并以「本 build 的 `last_deployed_at` 已写」作事实兜底（判据只认产物、不认执行体自述）。
- **规划段为何必须委派独立子 Agent**——`/version` 是全链路最重的一段：读 2000+ 行 `version.md`、4 个规划 SKILL 的生成往返、再加 version-auditor 终审。这几十万 token 的**生成过程**若落在 autopilot 主上下文里，规划 tick 就是破 1M 的头号来源。委派之后主上下文只收一份 compact JSON，过程全留在子上下文里随之释放。交互式不委派是因为 `/version` 中需要用户决策的交互门要用户在场应答，而子 Agent 不能与用户交互。
- **CICD 重试为何必须重跑锚定运行（Step C 失败重试）**——重试有两种看似等价的写法：`cicd_watch.py --mode retry --run-id <id>` 重跑**上一次失败的那条运行**（commit 由运行本身确定），`cicd_watch.py --mode trigger --ref <branch>` 则是**重新派发**、取分支**实时 HEAD**。重试期间只要有人往该分支推了代码，后一种写法下「自动重试」就悄悄变成「自动构建并部署一份从未被任何人确认过的新代码」——它已经不是重跑，而「无人值守可自动重试」赖以成立的前提「内容完全由上一次失败运行确定性推导得出」当场不成立。故 `retry` 恒走 `--mode retry`、首次派发才走 `--mode trigger`，两者语义不混用（个别平台的「重试」本身会按 Job 最新配置重建，故重试后仍要核对锁定运行的 commit）。prod 同理更敏感：同一份制品自动重部署生产三次会重启服务、覆盖当前制品，还可能与人工正在做的回滚打架——是否把 prod 纳入 `cicd.pipelines` 并由 `cicd.auto_trigger` 自动触发，应由项目显式决定，而不是默认敞开。



### 首次触发为何必须经 `cicd.auto_trigger` 显式授权（`phase-3-6.md` Step B）

`trigger`（首次主动触发）跑的是分支当前 HEAD，属「构建并部署新代码」，与「重跑失败构建」性质不同。PRD 里预声明 `deployment.cloud_deploy_trigger: cicd-provider` 表达的只是"这个项目走 CICD 流水线这条路"，**不是**"授权此后每一次真实构建部署"——**预声明 ≠ 授权**。

故无人值守下的写动作（`cicd_watch.py --mode trigger` / `--mode retry`）统一由 `memory/aidp-config.yaml` 的 `cicd.auto_trigger` 这一个显式开关授权：开着（默认）即可自动执行；关着则不执行写动作，按 `cicd-auto-trigger-off` 冻结发 #4 待人。

**场景边界**：项目配了「push 自动触发」时，正常路径是 detect 直接命中本次 push 的运行，走到 `trigger` 说明自动触发没起来、属异常，须提示；项目**未**配自动触发时，才由 autopilot 主动派发。

代价是 `auto_trigger` 关闭时遇到"自动触发没起来"会冻结待人。这是**有意的取舍**：宁可停下等人，也不替没有授权的人按下部署按钮。


### CICD 失败为何先重试而非自查（`phase-3-6.md` Step C）

重试近乎零成本；本地完整构建要跑数分钟，且**环境偶发**（缓存污染 / 配置漂移 / 构建机资源 / 依赖抖动）**本就无法在本地复现**。

关键在于：CI 失败时"环境偶发"与"自身缺陷"**表象完全相同**——都是一条红色记录。**区分它们最便宜的手段就是重试一次**：偶发会过，真缺陷会稳定复现。先自查 = 用最贵的手段，去做最便宜的手段就能做的判断。

这也是为什么「重试用满 3 次之前禁止启动本地完整构建」：不到那一步，"稳定复现"这个前提还没成立，自查缺少判断依据。

## `--entry-mode` 为何不传（phase-3-9 收尾门）

`ENTRY_MODE` 在 3.9 分片取不到值——tick 命名空间此前无该变量，而 `--skip-dev` 等裁剪 flag
在 0.0.0 的 case 里从未被解析（见本文「裁剪 flag 从来没被解析过」）。于是
`--entry-mode "${ENTRY_MODE:-full}"` 恒展开成**显式的 `full`**；而
`autopilot-ceremony-gate.py::_resolve_entry_mode()` 的口径是「显式参数 > baseline > full」——
显式传 `full` 会把 baseline 里正确写着的 `autopilot_entry_mode=test-only` **彻底旁路**，
test-only 轮次恒索要 `#1c`/`#1d`/`#2` 三条本轮压根没发生的通知 → 每 tick FAIL → 3 tick 冻结。

**不传** = 交回 gate 侧的 baseline 回退，那正是它为此专门实现的路径。
（`ENTRY_MODE` 现已补 `BASELINE_FALLBACK`，但收尾门仍不传——单一口径只留 gate 一处，避免二次旁路。）

## Sprint 三兄弟为何就地算（phase-3-5）⛔ 勿改回跨分片传递

`NEXT_SPRINT_NO` / `CURRENT_SPRINT` / `REMAINING_SPRINTS` 此前登记在 `DERIVED_VARS` 里，
但**全仓既无 `autopilot_tick_flags.py set` 落点、也无 baseline 回落** → `--shell` 读回恒空 →
`[ -n "${NEXT_SPRINT_NO:-}" ]` 恒假 → **首个 Sprint 关闭后就把 `next_sprint` 写成 `"done"`，
剩余 N-1 个 Sprint 被静默丢弃**，无告警、无痕迹，且下一 tick 直接推进到部署 Phase。

改为就地算的理由：**真源本就在磁盘上**，不需要跨分片传递——
计划文件里的全部 `Sprint-NNN` 号，减去 `memory/{V}/*/sprints/` 下已归档的，差集即剩余。
就地算天然满足「同分片赋值」原则，不依赖任何人记得在上游某处 `set`（那正是它此前失效的原因）。

机器回检 = `{{AIDP_HOME}}/scripts/check_tick_var_supply.py`（ERROR 硬门）：任何登记进 `DERIVED_VARS`
却无供给链的变量都会被拦下；这三个已加 `# supply-check: ignore` 并注明"就地算"。

## 逐 tick 单 Sprint 的三档取舍（phase-3-5）

原文（含三档完整判据与 Why）：

- **`HAS_WAKE_SOURCE=1`（`/loop` / cron）且未带 `--batch-one-tick`（★ 默认）= 逐 tick 单 Sprint**：本 tick 只跑研发执行计划里【下一个未关闭】的一个 Sprint（`/sprint-full <NNN> --unattended --from-batch`，走完整 `start→dev→test→bugfix→close`）。**★★ 优先委派【独立子 Agent】执行**，只回传 compact JSON `{sprint, closed:bool, files_changed:N, static_pass_rate, bugfix_rounds, blocking_issue?}`；主流程据此发 #2 通知 + 写 `run_state.next_sprint`。**回退**：子 Agent 不可用 → 内联跑（行为不变）；委派失败走 P0-3 C1–C3（`invariants.md`），**确定性失败**才记 `dev_fail_streak`。关闭后：① 发 #2 ② 写 `run_state.next_sprint` ③ **还有未关闭 Sprint → `UNATTENDED_YIELD` 退本 tick** ④ **本 tick 关闭最后一个 → 不 yield、继续走部署**（部署只在全部 Sprint 关闭后发生一次）。⛔ 与「全部 Sprint 不可分割」不冲突，见 `rationale.md`。



## 为什么收尾门不传 `--will-browser-test` / `--no-planning`

两个变量都**没有 baseline 回落**（不在 `autopilot_tick_flags.py` 的 `BASELINE_FALLBACK` 里）。
一旦被 tick 清空、或断点续跑直接进到 `3.4-finish`（不会重跑 3-8 的 `WILL_BROWSER_TEST` 派生），
它们必然取空，而 flow 里写的 `${WILL_BROWSER_TEST:-0}` / `${NO_PLANNING:-0}` 会把 **0 显式传进闸门** ——
闸门于是**不再走自己的 baseline 推导**（`--will-browser-test` 缺省 `-1`、`--no-planning` 缺省 `None`
正是为此设计的）。

实测对比（同一 baseline：`autopilot_no_planning=1`、build 已落 `aiauto_delegated_at`）：

- 省略两个 flag → `will_browser_test=1`（baseline 推导）→「🟡 用户显式 --no-planning、放行」
  +「✅ 测试链路运行证据」。
- 按旧写法传 0/0 → 「❌ 版本规划产物齐全 … P0-2 … exit 1」**假 FAIL**（每 tick 累计，3 tick 冻结），
  且「测试链路运行证据」整项消失 —— 唯一防「委派落空」的门被静默跳过。

与已删的 `--entry-mode` 是同一类问题、同一种处置：**能从 baseline 推的，就不要从易失的 shell 变量传**。


## `--stage` 选择必须证据化（收尾门）

`skeleton` 的语义是「把 #F/#3 与交付台账的校验**延后**交给一条**真实存在且在跑**的测试链路」。
所以它合法的前提是那条链路确实存在：① 本轮是 `/loop` 无人值守（另一条 `/loop 5m /sprint-aiauto-test --unattended`
在跑）**且** ② 本 build 已落 `aiauto_delegated_at`（确已 invoke 过、不是"我以为已委派"）。

分片一度只按 `WILL_BROWSER_TEST` 分流，与命令主体的这条判据**直接相反**：
交互式 `--once` + `deployment.mode=cloud` ⇒ `WILL_BROWSER_TEST=1` ⇒ 取到 `skeleton` ⇒
收尾门不校 AI测试报告 SPA、不校 #F 通知、不校交付台账 —— 而此时根本没有第二条链路会来收口。
两处当时都在自认正确，正是「顶层契约在下一层被重新分流」的典型形状。


## 配置类解冻为何不能只写在测试链路

配置类冻结（`account-missing` / `account-invalid` / `testplan-incomplete` /
`cicd-auto-trigger-off`）的
mtime 解冻，`/sprint-aiauto-test` 的 `phase-0-6.md` 里**本来就有一份**，看起来 autopilot 侧
再写一份是重复。不是。

那份在**首次部署之前够不着**：它跑在选版之后，而选版走 `baseline_edit.py current-version`，
判据要求 `phase_beta_done_at` 非空——那个字段只在部署完成时才写。而 `cicd-auto-trigger-off`
与 autopilot 侧的 `account-missing` 恰恰冻结在**首次部署之前**：`phase_beta_done_at` 是 null，
`current-version` 返回空，整个 shard 在解冻代码之前就 `exit 0`。

净效果：7×24 链路第一次遇到「`cicd.auto_trigger` 关闭且需主动触发」或「测试账号没填」时冻结，**此后没有任何
代码路径会来解冻它**——补好配置也没用，只能 `--reset-baseline`。
`phase-3-7.md` 那句「补好账号即自动恢复」在这个场景下是空头承诺。

所以判据一样、位置必须不一样：**autopilot 侧这份跑在选版【之前】的候选筛选阶段，
不依赖任何部署产物**。两份并存不是重复，是同一判据在状态机两个可达点上各放一次。

⛔ 别"顺手合并"掉其中一份——合并的结果一定是保留能跑通测试的那份（测试链路那份），
于是这个洞原样回来。


## Step C 的三条 RED FLAG（原在 phase-3-6.md，为体积下沉）

⛔ **RED FLAG（三条必须逐条守住）**：① **绝不**在**首次**失败就跳「失败处置」/ 跳过重试——必须先把 `cicd.max_retries` 次主动重试**用满**（首次失败 + 3 次重试 = 最多 4 次运行）；② **绝不**因平台返回的状态不是字面 `failure`（而是 `cancelled` / `timed_out` / `startup_failure` / `aborted` 等）就当"非失败"晾着不管——凡**到终态且非 `success`** 一律按 ③ 失败类重试，宁可多重试一次也不放过悬空态；③ 重试**必须 `cicd_watch.py --mode retry --run-id <run_id>`** 重跑锚定运行本身——⛔ 不得用 `--mode trigger` 重新派发（那会取分支实时 HEAD，把「重跑失败构建」悄悄变成「部署未经确认的新代码」）。

## 归档版的游标不得代写下一版的阶段

Phase 2 收尾写的是 **`PRE_RELEASE_VERSION` 自己**的 `run_state`，它的流程到归档这一步确已走完，
故 `next_phase` **恒 `done`**。

曾写成 `$([ -n "$TARGET_VERSION" ] && echo '3.0-route' || echo 'done')`——本意是"接下来该跑
Phase 3 了"，但 `3.0-route` 是**另一个版本（TARGET_VERSION）**要跑的阶段，却被盖在刚归档的旧版身上。
撞上 Phase 0.6 的「**尾段续跑优先**：`run_state.next_phase ∉ {"", "done"}` 的版本最优先作 TARGET」，
下一 tick 就会把这个已归档的旧版重新选为 TARGET，整轮 Phase 3 跑在错版本上、真正的新版被饿死。
典型触发形态就是最常见的那种 tick：一个待归档版 + 一个待开发版同时在场。

**定则**：每个版本的游标只由**它自己**的阶段出口写；跨版本的"接下来做什么"由 Phase 0.6 的选版逻辑
在下一 tick 重新判定，不靠上一版留话。

## 双 loop 下收尾门为何恒判 final（GATE_STAGE 的第二个 skeleton 条件）

标准挂法是两条 loop：`/loop 10m /sprint-autopilot --unattended` + `/loop 5m /sprint-aiauto-test --unattended`。
这个形态下 **autopilot 从不 invoke 测试链路**——`aiauto_delegated_at` 只在 test-only 子流程 R
（`phase-3-2.md`）写，full 路径压根不走那条分支，于是 `DELEGATED` 恒空、`GATE_STAGE` 恒判 `final`。

而 `final` 阶段强制校验 `exec_report` 交付台账，该台账在这条路径上**必然缺失**：
写台账的 `emit-report` 在 `WILL_BROWSER_TEST=1` 时整段跳过（报告归测试链路 finalize）。
结果是收尾门每 tick FAIL、`dev_fail_streak` 累积、3 tick 后把版本冻结——**配置完全正确的标准双 loop
反而跑不动**。

**定则**：测试链路作为独立 loop 确实在跑、报告由它 finalize 时，autopilot 就该按 `skeleton` 判。
判据必须是「**真在干活**」而不是「有心跳」：心跳由测试链路每 tick 起始无条件先写（早于任何
early-exit），冻结或被去重门跳过的空转 loop 心跳照样新鲜（5m 间隔 << 30min 窗口）。
统一实现 = `autopilot-ceremony-gate.py::test_loop_alive`（心跳新鲜 AND `aiauto_blocked_reason`
不指向本版），收尾门 3b2 与本处共用同一个函数，不再各写一套。

## 入口分流的 AskUserQuestion 为何只能有「开发范围」一个维度

Phase 3.2 那道问询严格二选一：「① 全流程（默认） ② 仅部署+测试(test-only)」，**绝不多拆第三维**。

⛔ 特别严禁把「测试失败自动修复复测闭环（最多 3 轮转人工）」拆成一个可选项（诸如
「③ 部署+测试，不自动修复」）：该闭环是 autopilot **每 tick 的默认自动仪式**，在
full / test-only / incremental 三种模式下**一律恒开**，不是用户的决策点。把它做成选项
就是把默认仪式误当 opt-in——与「铸新 build 出复测报告绝不作为问句」同一类错误。

⛔ 由此也严禁把不含自动修复的「仅部署+测试」变体标成「推荐」：两个选项都恒含自动修复复测，
标注差异会让用户以为存在"不修复"这条路。

## hold 游标会把准发布版选成 TARGET（选版必须排除 PRE_RELEASE_VERSION）

Phase 2 的「暂缓准发布」分支（0a 部署就绪 / 0b 测试收敛前置门未过）会给 `PRE_RELEASE_VERSION`
写下 `next_phase="2-prerelease"` + `pending=prerelease-hold` —— 这是**非终态**游标，而且**必须写**
（invariants 的阶段推进不变式要求每个 Phase 出口都落 run_state，"只在 invariants 里描述而分片不写盘
= 状态机不存在"）。

撞上 Phase 0.6 的「尾段续跑优先：`next_phase ∉ {"", "done"}` 的版本最优先作 TARGET」，
同一版就同时成了 PRE_RELEASE 和 TARGET，直接触发 0.3.5 的「TARGET = PRE_RELEASE 冲突」判定 →
计入 `preflight_fail_streak` → 3 tick 后**顶层**冻结（`preflight_frozen_at` 一挂，0.1 每 tick 静默
exit，**所有版本一起停**），而 #4 通知会把诊断误导成「baseline 状态机 bug，请 `--reset-baseline`」。

触发形态是**主线常态**：版本 Sprint 全关闭转 S2、等测试链路收敛期间 0b 门 hold（设计上允许挂 12 tick）。

**定则**：修在**选版**这一头（排除 `== PRE_RELEASE_VERSION`），不修在写盘那头——hold 状态本就该被记录，
它只是不该同时占着 TARGET 身位。

## 斜杠命令进围栏 / 裸退让熔断永不达阈（逐 tick 单 Sprint 分支的两个坑）

**其一**：`/sprint-start`、`/sprint-close` 这类斜杠命令是 Claude Code 的命令，**不是 shell 命令**。
把它们写进 ```bash 围栏，Bash 工具执行时必然 `command not found`（127）；围栏里又没有 `set -e`，
于是继续往下跑，随后的 close 归档检查必然判失败——整条逐 tick 单 Sprint 路径从未真正跑通过。
正确形态是**散文式委派指令**：`Agent(...)` 派子 Agent 跑 `/sprint-full`，bash 围栏只留差集计算与游标写盘。
这同时满足 IRON-8「每个 Sprint 的开发必须子 Agent 执行」——内联跑还会把整个 Sprint 的上下文灌进主对话。

**其二**：失败分支**不能裸 `exit 1`**。`phase_enter_count` 的唯一维护者是 `baseline_edit.py` 的
`run-state` 子命令（只在它被调用时自增），裸退发生在任何 `run-state` 之前 —— 于是
`dev_fail_streak` 不涨、`phase_enter_count` 永远停在 1，而 `autopilot_stuck_check.py` 要求 ≥8。
结果是**零告警零冻结的永久空转**：每 tick 进来、失败、退出，正是通用 stuck 熔断被造出来要堵的形态。
记账范式同 phase-3-9：`bump dev_fail_streak` + 写 `dev_fail_phase` + 写一次 `run-state` + `exit 0` 让位。

## 本地 dev server 幂等复用（mode=local 的无人值守铁律）

`/loop` 每 10 分钟进来一次。若每 tick 都前台起一次 dev server，会话当场被常驻进程阻塞、
`/loop` 挂死；若每 tick 都后台再起一个，端口冲突 + 进程堆积，几小时后把机器跑满。

**定则**：先探后起、探到就复用。
- **探活**：`local_ready_check_url` 可达，或前后端端口已被监听，或 PID 文件里的进程还活着 —— 任一成立即视为"已在跑"，本 tick 不再启动。
- **启动**：确认未跑才启，且必须 `nohup … &` 后台化并把 PID 写盘，**绝不前台常驻**。
- **不做的事**：不 kill 重启（会打断正在被测的实例）、不因"探不到就再起一个"（探测失败先当作已在跑，宁可少起一次）。

这条与约定 35「开发期默认只静态验证、不擅自启动服务」不矛盾：那条管的是**开发期验证**，
这里是 `mode=local` 的**部署替代动作**，由 PRD 的 `autopilot_decisions.deployment` 显式声明才走。

## Phase 2 准发布双门的形态与判据（对应 `phase-2.md`）

- **门的形态必须是跳过门（skip-gate）、不是 `exit 1`**——`PRE_RELEASE_VERSION` 与 `TARGET_VERSION`
  是**同一 tick 内两个互不相干的版本**（Phase 2 归档上版 / Phase 3 开发下版），本门只否决"上版归档"
  这一件事；在此裸 `exit 1` 会**连带掐死同 tick 的 Phase 3 下版全流程**，且 `/loop` 每 tick 重撞同一
  失败、无熔断无告警。故落地形态是 `PRERELEASE_HOLD=1` → 结束 Phase 2 → 继续同 tick 的 Phase 3。
- **0b 的时间比较必须走 epoch（`to_ts`）、不用字符串 `>`**——ISO8601 两侧时区写法（`+08:00` / `Z`）
  不一致时字符串比较会误判"已测过"而放行归档。
- **0b 必须同时校 `ai_report_finalized`**——只看 `aiauto_tested_at` + `unconverged_streak` 会漏掉
  "测完了但最终仪式门没过、`#3` 从未发出"的 build：那种 build 的 tested 标记与 streak 都已就绪，
  会被判成"已测收敛"照常归档，报告却永远停在骨架（统一处置见 aiauto-test Phase 3.7）。
- **取 `FIN` 的 jq 里 build 也必须用转义双引号插进源码、不能用 `--arg`**（此处 `--arg` 是 jq 自身的参数、不是 AIDP 命令旗标 <!-- flag-check: ignore -->）——jq 程序整体用双引号包裹
  （为插值版本号），故 `$b` 会被 **shell 先展开**成空、生成 `select(.build==)` 语法错 → `FIN` 恒空 →
  `${FIN:-false}` 恒 false → 本门物理上无法通过。写法与 `phase-3-4.md` 同款。
- **`TEST_LOOP_ALIVE` 的存活判据要两个字段缺一不可**——心跳在测试侧冻结待人时照样每 tick 刷新，
  只看心跳会造成双链路互等，故须叠加 `aiauto_blocked_reason` 对本版不成立。
- **"暂缓"必须有上限**——无 streak / 无阈值的裸暂缓 = 准发布可**永久**挂起且零告警（测试链路活着
  但永远测不收敛时无人知道）。故该分支记账 `prerelease_test_hold_streak`（6 告警 / 12 冻结）。
- **0T 中间过渡版本必须等到阈值才判、不能一进门就判**（关键，别"优化"掉）——autopilot 正常流里
  Phase 3 每轮都会规划下一版，「存在更新版本的计划」在**正常流中同样成立**：一进门就判会让 0a/0b 对
  每个 S2 版本**全面失效**，正好废掉这两道门要防的「未测 build 被静默归档」。等到阈值 = 已给足重试
  窗口、确认这一版真没人管了，才认定为过渡版。命中时「请重部署 / 请挂测试链路」本就是**假告警**
  （没人会回头部署测这一版），冻结只会让它烂在 limbo。

### Phase 2 执行片收敛时保留的根因

- 门禁围栏、步骤 2 的命令编排、步骤 3 和 5 的 Bash 围栏互不共享 shell 状态。旧版门禁设置 `PRERELEASE_HOLD/YIELD` 后，步骤 3/5 从未持久化的 tick 信号读空，`HOLD:-1` 让真正成功的归档永不写游标；同一 shell 中 `YIELD=1,HOLD=0` 又可假写 done。每 tick 先清空并显式持久化门禁放行/暂缓/让位，只有步骤 2 的本地或远端必需产物核验通过才登记归档成功；步骤 3/5 跨进程读回四信号并校游标，缺任一即不落成功态。无 Git 的 `internal_released_at` 仅表示已核验的本地归档选版游标，不是正式发布。

- `PRE_RELEASE_VERSION` 从 Phase 0.3.4 跨 Bash 调用传入，必须从 tick 状态读回；若直接用空的 shell 变量，所有 `.versions.""` 查询都落空，0a/0b 会把合法版本误判成未部署且未收敛。时间比较也必须使用 epoch：ISO8601 的 `+08:00` 与 `Z` 混排时，字符串顺序不等于时间顺序。
- 0y 尾段和自动修复闭环进行中，部署或测试未就绪是合法中间态。Phase 2 只让位，不累计冻结 streak，也不能写自己的 `run-state` 覆盖 Phase 3 的部署、探针或终审续跑游标。
- 测试链路缺失达到阈值后，冻结并不是本 build 的报告收尾。仍须执行 `phase-3-9.md` 的静态-only 三步：定稿 testSummary、产出 AI执行报告并发 #3；只打印一条冻结提示会让报告永停骨架。
- `internal_released_at` 必须由 `baseline_edit.py` 真写入。旧版只有 JSON 示例和“已写入”的 run-state 摘要，字段实际恒空，归档版持续留在 `current-version` 候选集，测试链路反复重测已归档版本。
- 0T 的版本计划要按文件名中的 `研发执行计划` 通配，不可只认 `01_研发执行计划.md`：`01_M1研发执行计划.md` 和带开发者后缀的合规拆分文件同样表示新版规划已开始。

## Phase 3.1.5 铸 build 的复用判据与出口游标（对应 `phase-3-4.md`）

- **复用判据必须与 `ENTRY_MODE` 解耦**——绑死 `test-only` 会让无人值守默认形态每 tick 都铸新 build →
  报告碎片化 + 收尾门按刚铸的 build 判必然"产物缺失"。
- **`BASELINE_FILE` 变量名统一**——本片与 `phase-2.md` / `phase-3-9.md` 曾用不同变量名，未定义时
  jq 会读 stdin 静默失败。
- **写 baseline 一律走 `baseline_edit.py` 的 flock，禁裸 `jq … > tmp && mv`**——与测试链路 `/loop 5m`
  并发写时，裸写会把对方刚落的 `ai_report_finalized` / `last_deployed_at` 整体抹掉。
- **出口 `run-state` 漏写 = 状态机不存在**——`next_phase` 恒空 → tick 中途中断后下一 tick 从 Phase 3.0
  全量重推；`next_sprint` 恒空 → Stop hook 的「中间 yield-tick 豁免」判据取不到值 → 每个中间 tick 都
  误跑一次收尾门（必 FAIL）并白烧熔断额度。故 `FIRST_SPRINT` 也不得留空。
- **出口不得硬编码 `next="3.2-dev"`**——`test-only` 整片跳过 Phase 3.2 开发循环，硬编码会把它路由进
  一个对它不适用的 Phase → 又一个无人消费的游标。而 `test-only` 的 `next` 写 `3.3-audit` 而非
  `3.4-finish`：跳过 version-auditor 终审会让收尾门每 tick FAIL、3 tick 冻结版本。

## Phase 0.3.4 选版落盘 + 冻结复探（对应 `phase-0-6.md`）

- **`TARGET_VERSION` 漏写的代价最大**——每个 Phase 出口的
  `baseline_edit.py --version "$TARGET_VERSION" run-state …` 会因缺 `--version` 全部 rc=1，
  **`run_state` 一次都不落盘** → 下一 tick 的「1.3bis 续跑短路门」取空失效 → 回落 PRD 变化检测判
  `no-change` 立即退出，**Sprint-002 起永不执行**；连通用 stuck 熔断也因传空版本返回 2 被当成
  "入参错跳过"，唯一的兜底同时失效。
- **`PRE_RELEASE_VERSION` 漏写**——Phase 2 的 jq 路径拼成 `.versions."".…` 恒取空 → 上版准发布双门
  恒判"未部署/未收敛" → 每 tick bump `prerelease_deploy_block_streak`，3 tick 后冻结，S2 版本永远
  不会被归档。
- **`autopilot.target_version` 必须持久化到 baseline 顶层**——它是 `TARGET_VERSION` 的声明真源，
  却一度**全仓零写入者**：于是下一 tick 回落取空、再落到 `current-version`（那是 Phase 2 的准发布版，
  ≠ 本轮开发版），`BUILD` / `DEPLOY_MODE` / `ENTRY_MODE` / `PLANNING_DONE` 集体取到上一版或空值。
- **环境类冻结必须有自动复探**——其宣称的解冻条件是"有新部署"，但该版本一旦被剔除出
  候选，autopilot 就再也不会去部署它，于是"新部署"永远不会发生：名为自动解冻、实为**永久停摆**。
  环境一旦真的恢复（探针通了/流水线好了/CLI 重新登录），下一次到期的复探就能自动接上，无需人工；
  遍历全部被冻版本与指数退避的理由见「环境类复探为何遍历全部被冻版本、并下沉到脚本」。
- **解冻证据判定必须下沉到 `autopilot_unfreeze.py`、禁内联复写**——内联 `case` 会漏类：`unconverged`
  （dev_fail 冻结）整类落在 `case` 之外时，本地修好并推送也不解冻，而无人值守下没有人能处理「人工回复 retry」类指引。

## Phase 1 监听与短路门的补充根因（对应 `phase-1.md`）

- **PRD 变化判据两侧必须同构后比对**——退回"`sha256sum` 文本行的哈希 vs `jq … | tostring` JSON 串的
  哈希"这种不可比写法，会让 `SHOULD_RUN` 恒 1、「无变化干净退出」路径不可达，`/loop` 每 tick 空转
  进主流程。
- **短路时重复回写 `tracked_files` 的具体后果**——下次比对的基线被提前推平，期间新到的 PRD 变更
  此后永远检测不出。
- **`LOOP_UNATTENDED=1` 绝不能落到"默认"行**——落默认行会让它跑完 Phase 0 打印一屏配置向导就退出、
  **永不进 Phase 2/3**，速查推荐的 `--unattended` 写法会彻底空转。
- **`--no-loop` 行为何要放行 `SHOULD_RUN=0` 但 `PRE_RELEASE_VERSION` 非 null**——否则 S2 待准发布
  版本在无新 PRD 时永不自动归档。
- **1.4 写盘禁裸 `jq … > tmp && mv`**——裸写会丢掉测试链路并发写刚落的字段。

## 测试链路缺失为何不能交给收尾门（根因分诊必须先于 ceremony 闸）

「本版需浏览器实测、但第二条 loop 没挂」这一场景，判据与降级动作原先都写在
`phase-3-9.md` 的 ③ 段。**它位于闸失败分支 `exit 0` 之后，而这个场景恰恰会让闸必然 FAIL**
—— 于是那段代码在它唯一该生效的场景里一次都不执行。链路：

1. `TEST_ALIVE=0` 且本 build 无 `aiauto_delegated_at` → `GATE_STAGE=final`；
2. final 的 3c 要 `report_deliveries.{build}.exec_report`，而 `WILL_BROWSER_TEST=1` 时
   autopilot **刻意跳过** phase-3-8 的 Step 2/3（那是唯一写交付台账的 `emit-report`，台账唯一产出点），
   把 R-4 留给测试链路 → 台账必空 → 3c 必 FAIL；
3. 闸 FAIL 走 `|| { … exit 0; }`，③ 的 `test_loop_missing_streak` 一次都没加；
4. 3 tick 后以 `handoff-exhausted` 冻结 —— 而真因是 `config-missing`。

第 4 步是实际损失所在：`config-missing` 属配置类，补挂第二条 loop 后由心跳自动解冻
（见「配置类解冻为何不能只写在测试链路」）；`handoff-exhausted` 属人工解冻类，**补挂也不会恢复**，
必须人工清 baseline。即"运维漏挂一条 loop"被升级成"需要人工介入 baseline"。

故把这一支提到闸之前做**根因分诊**：命中即走 `config-missing` 通道并 `exit 0`，不进闸的记账。
③ 只保留「已有报告 → 清零 streak」与纯提示两态。⛔ 别把它挪回 ③ —— 位置本身就是这个缺陷。

## 计划文件的三种解析法（为何统一到 `plan_sprints.py`）

「本版一共有哪些 Sprint」曾有三种写法散在四个分片：`find … -print -quit`（只取一份、且 find 不排序）、
硬编码 `docs/plans/$V/01_研发执行计划.md`、全量 glob。而多文件是上游 SKILL **明确支持并会产生**的
形态——多用户拆 `NN_研发执行计划-{姓名}.md`、超阈拆 `02_`…、跨 ≥3 里程碑拆 `01_M1研发执行计划.md`。

`-print -quit` 命中 M1 那份时，「全部 Sprint」就等于 M1 的 Sprint：M1 跑完 → 差集为空 →
打印「✅ 全部 Sprint 已关闭」→ 正常部署、finalize、发报告、发通知，**M2 的 Sprint 从未执行且无任何告警**。
无人值守下最坏的一类失效：不报错、不重试、结论是"成功"。

硬编码 `01_` 是同一枚硬币的另一面：拆分形态下文件不存在 → 变量取空 → 下游拿空游标做判定。
而 `printf '%s\n' "${arr[@]}"` 在**空数组**上会输出一个空行、`grep -qx ""` 恰好命中它——
于是「一个 Sprint 都没关闭 + 游标丢失」这个最坏组合**反被判成功**（已实测复现），
连带 `del dev_fail_streak` 清空熔断计数。故游标为空必须先显式 fail，不许落进那个匹配。

## 3.2 的达阈冻结（为何不能只 bump）

Phase 3.2 是 Phase 3 最频繁的失败点，原先只 `bump dev_fail_streak` 而不判阈。同一 Sprint 反复失败时
`run_state` 的 `current_phase`/`next_sprint` 都不变 → `baseline_edit` 判为「未推进」→ 只剩通用 stuck
熔断兜底，而它要 8 tick **且**滞留 > 2 小时，即 **80 分钟以上纯空转**才会有人知道。
阈值与冻结字段口径与 phase-3-9 收尾门一致（四件套一次写齐）。

## `deployment_mode` 的写入者（为何落在 Phase 3.1.5）

`versions.{V}.deployment_mode` 有两个读点，都在 `autopilot-ceremony-gate.py`：
`_derive_expect_cards()` 据它决定要不要期望 **#1d 部署通知**；`--will-browser-test` 未传时
（收尾门刻意不传）据它推 `_should_test`。

而它此前在 autopilot 链内**零写入方**——全仓唯一写入点在 `flows/sprint-batch/step-6.md`，
偏偏 autopilot 链内恒传 `--skip-aiauto-test`，Step 6 首行即整段跳过。autopilot 自己的两个
部署落盘点只写 `last_deployed_at` 与 `phase_beta_done_at`。于是恒读空 → `deployed=False` →
**部署通知漏发永远查不出**，且 `wbt=0` 时反过来期望一条 autopilot 根本不该发的 #3。
Stop hook 调 gate 时不传 `--expect-cards`、正好走这条推导，受影响的就是它。

落在 Phase 3.1.5 铸 build 处：那里已 `eval` 过 tick flags（`DEPLOY_MODE` 可用）、已在写 baseline，
且早于所有读点。

## AI执行报告的产出归属（产骨架 / finalize 解耦）

- **骨架**（`data` 计划态 + 结果态 + `testSummary` 占位）**只由 `/sprint-autopilot` 流水线产**——
  `/sprint-batch` 与直接调用子命令**均不产骨架**。
- **finalize（真实 testSummary）+ 报告本体 + #3 通知**由 **build 关闭方**在 **#F 之后**做：
  有浏览器测试 → 测试链路 `/sprint-aiauto-test` Phase 3.7；静态-only → autopilot Phase 3.4 末尾。
- Phase 3.1.5 铸的 `current_build` 是「**由 autopilot 驱动**」的信号：`/sprint-aiauto-test` 据它
  判定是否生成 AI测试报告、是否 finalize AI执行报告。**无 `current_build` = 直接调用**，
  两者都不产（见 aiauto-test Phase 0.2 步骤 2.5.1 / 3.0 / 3.7）——否则 standalone 的一次性调用
  会去覆盖一份根本不属于它的 build 报告。

## 自动触发运行的强弱绑定（对应 `phase-3-6.md` Step A「否则」分支）

「push 后自动触发」的流水线里，**认哪一条运行是本次提交起跑的**只有两档判据：

- **强绑定（首选）**：运行的 commit `== GIT_PUSH_COMMIT`（或前 8 位相等）→
  `commit_verified=true`。
- **弱信号（仅当该运行取不到 commit 时才回退）**：三个条件**同时**成立才算——
  ① `created_at` 晚于 `GIT_PUSH_AT` ② 触发类型属自动类（push 事件，非手动/API 派发）③ `status` 为 `in_progress` 或刚 `completed`+`success`；
  记 `commit_verified=false`。

⛔ **不能只看时间**：并行开发下，别人的 push、定时构建、手动重跑都会在同一时间窗里起跑运行，
只按「最近一条 + 时间晚于我」会抓到别人的运行，然后一路监听它的终态、按它的成败决定本轮部署是否就绪——
失败形态是**结论看起来完全正常**，只是评的不是这次提交。三个条件缺一都不足以排除这种混淆。

## 交互式没有下一 tick（收尾门根因分诊为何必须先分唤醒源）

「测试链路未挂载」这一支的处置是**让位本 tick、下 tick 复判**——前提是**有下一 tick**。
而交互式 `--once`（`HAS_WAKE_SOURCE=0`）没有。不做分流时，`WILL_BROWSER_TEST` 只由部署模式派生、
与是否无人值守无关，于是交互式跑云部署项目**每次都命中**，打印「请挂第二条 loop」后退出：

在**用户已用 `--once` 明确表达执行意图**的前提下，把剩余工作包装成**用户的配置缺失**退回去——
这正是本命令设计目标点名禁止的形态。连撞三次还会按 `freeze_reason=config-missing`
「测试链路未挂载」冻结，而用户压根没打算挂 loop，归因彻底错误。

正确交付分两档：
- **有唤醒源**（`/loop` / cron）→ 累计 `test_loop_missing_streak`、达阈静态-only 收敛（原逻辑）；
- **无唤醒源**（`--once`）→ autopilot **自己就地 invoke 一次** `/sprint-aiauto-test --once`，
  完成后复跑收尾门。只有子 Agent 不可用 / 回传 `tested:false` 才降级静态-only，
  且**必须把原因打印给用户**——「做不到」与「让用户去配 loop」是两回事。

## 推送围栏的三个取空（对应 `phase-3-5b.md` 步骤 2 的推送围栏）

该围栏一度同时踩中三个：

1. **`eval --shell` 排在 `git push` 之后** → push 时 `$DEV_BRANCH` 恒空，
   `git push origin ""` 直接 `fatal: invalid refspec ''`（rc=128）→ `|| exit 1` →
   按同段第 5 条要走「失败处置 #4 通知 @用户介入、暂停本轮」——**无人值守链路每轮停摆等人**。
2. **`DEV_BRANCH` 不在 tick 白名单**：它唯一的赋值（带 `$(git branch --show-current)` 自愈回落）
   在本片**另一个**围栏里，`eval --shell` 也供不了它。故本围栏必须自己再兜一次底。
3. **`BE` 在本围栏从未赋值**（前两个围栏各赋过一次，第三个漏了）→ 末行展开成
   `--version … set …` → `command not found` → `push_at` / `push_commit` **永不落盘** →
   Step D 就绪探针的兜底判据（`probe_commit == push_commit`）随之恒假，游标永远留在 `3.2.1-probe`。

三条都不报错、都只表现为「某个判据恒假」，要跑几个 tick 才显形。

## zip 交付为何不是缺陷（收尾门 ② 的内联兜底）

报告只落本地时 `emit-report.py` 的交付形态是本地文件（`delivery="zip"` / 本地路径），**`url` 恒为 `None`**
（本就没有在线链接可给，通知里放的是仓库相对路径）。内联兜底一度只认「带 `#/build/{B}` hash 的 url」，
于是**所有按默认配置本地交付的项目**每轮必 `bad` → `FAIL=1` → `bump dev_fail_streak` →
第 3 tick 以 `handoff-exhausted`（人工解冻类）冻结一个**完全健康**的版本。

而权威脚本 `autopilot-ceremony-gate.py` 3c 对同一情况判为合法：本地交付直接 `continue`。
**内联兜底比权威脚本更严，且严的那一档才是致命的** —— 兜底的定位是"脚本缺失时的弱替代"，不该比它要堵的对象更凶。

## frontend_deploy_verified 为何必须可执行地写

gate 3e「部署覆盖度」的判据是 `frontend_changed is True and frontend_deploy_verified
is not True → FAIL`。`frontend_changed` 是**真写的**（phase-3-8 收尾围栏），
而 `frontend_deploy_verified` 一度只存在于两处散文里、零可执行写入 ——
于是 gate 注释所称「信号缺失就跳过、不误判」的保护失效：**任何动过前端的 build
在 `--stage final` 恒 FAIL**。写入点落在 Step D 探针情形③通过处，与判据同源。

进一步地，后端就绪只证明后端可测，无法证明前端资源更新。Step D 以前虽要求抓首页、
下载 JS/CSS 并匹配 `must_contain[]` 每个特征串，却没有可执行检查，`FE_PROBE_OK=0`
只是提示执行体自行替换；无论取值为何，`probe_passed` 和 `last_deployed_at` 都先写了。
现在按本版 PRD 的 `deploy_ends.frontend.ready_asset_probe` 解析配置并抓部署首页引用的同源资源，
全部特征命中后才写 `frontend_deploy_verified`；缺失、取数失败均不写部署就绪证据，
空特征串只能警告跳过，不伪造前端已验证。探针判据必须先于所有成功证据执行。
当前 build 的 `frontend_deploy_verified/probe_passed/probe_at/probe_commit` 与版本级
`last_deployed_at/phase_beta_done_at` 必须同锁一次落盘；分步写时第二、三步失败会留下
误导下游的半套成功证据。无 Git 的本地部署不需要 push SHA，以同次落盘的 `probe_at`
与 `last_deployed_at` 验证出口；`last_autopilot_head` 只记录 Git push 后确有的 HEAD。

## incremental 为何必须在铸 build 出口先分流（`phase-3-4.md`）

Phase 3.3b 的硬判据③**保证** `ENTRY_MODE=incremental` 只在 `OPEN_N == 0`（无未关闭 Sprint）时成立。
于是走 `plan_sprints.py` 那一支时 `NEXT_SPRINT` 必空 → 紧随的 fail-closed **100% 命中**，
且是**裸 `exit 1`**：不 `bump dev_fail_streak`、不冻结、不发 #4 —— 熔断永不达阈、永不 @人，
7×24 表现为「挂着刷屏、什么都不推进」。这与本链路明写的「失败不能裸 exit 1」直接冲突。

增量路径本就没有 Sprint（同文件末尾自己也写着「增量路径无 Sprint 则留空」），故先分流、写 `done`。

## `$BV` 为何要在报告目录围栏里重新取回

`BV="$TARGET_VERSION"` 在铸 build 那个围栏，而 `RPT="docs/reports/$BV"` 在**下一个**围栏；
`BV` 又**不在 tick 白名单**（白名单里是 `TARGET_VERSION`），`eval --shell` 也供不了它。
取空 → `RPT="docs/reports/"` → SPA 铺到 `docs/reports/AI执行报告/`。
而 phase-3-2 的委派前硬门查的是**正确**路径 `docs/reports/$V/AI执行报告`，于是
`[ -f "$A/index.html" ] || exit 1` → **永远禁止委派 `/sprint-aiauto-test`**，
`aiauto_delegated_at` 永不落盘、测试半环永不启动。

## Step C 出口只有「成功」一种形态的后果（`phase-3-6.md` 末尾）

该出口块写在文件末尾、**没有任何守卫**，而它一度只有「流水线成功、待探针」这一种写法。
Step C 判 ③失败重试 / ④ CICD 平台不可达（提供方凭据失效 / 网络故障）/ ⑤锚定运行消失之后若仍执行它：

- 游标被写成 `3.2.1-probe`，`--summary` **谎报「流水线成功」**；
- 下 tick 从 `3.2.1-probe` 起跑 → **整段跳过触发 / 监听 / 重试**；
- 去探一个从未部署成功的环境 → 探针必然超时 → 以 `probe-timeout` 冻结，
  **原因与真因（CICD 失败）完全无关**，排查的人会顺着"环境起不来"这条错线索走下去。

紧随其后的散文本已写明「部署未就绪而本 tick 让位时 `next` 写 `3.2.1-deploy`」——
只是没有对应的分支代码。这是本仓最常见的形状：判据写对了，落不到可执行面上。

随后虽补了成功/未成功分支，出口的 `CICD_OK=0` 仍把真实 success 一律改判为待续；
且摘要含「运行中」被 `baseline_edit.py` 的进行时门拒写，连合法续轮询的游标也无法持久化。
出口须读本次 poll 的 run ID、commit 和 verdict 并与本 build push 锚一致。
`running` 与 Step D 的 `rc=4` 都只代表一次调用的时间片结束：有唤醒源才可让下一 tick 接手；
无唤醒源必须在本 tick 追加有界探测，仍无终态则按现有原因冻结并告知，不能静默等不存在的 tick。


## `builds[]` 字段表（`phase-1.md` baseline 字段清单的外置正文）

`versions.{V}.build_seq` / `current_build` / `builds[]` 的完整语义：

- build 号自增计数器(默认1000)/ 当前 build `{V}_build{N}`（aiauto-test 据此归属测试结果）/ build 数组（每条 `{build, started_at, status: running|dev_done|closed, finished_at, pass_rate, ai_report_finalized, ai_report_finalized_at, retest_of, retest_round, aiauto_delegated_at, entry_mode}`）。**`entry_mode` 是 build 级、勿退回版本级**（收尾门与 Stop hook 优先读它；理由见 `rationale.md`「entry_mode 粒度」）。**`aiauto_delegated_at`（★ 委派证据）**：真正 invoke `/sprint-aiauto-test` 时才写、内联驱动 chrome 绝不写；收尾门据它选 `--stage`。3.1.5 铸造时写 build_seq + current_build + 追加 builds 条目（复测轮带 `retest_of`/`retest_round`）；3.4 刷 `status:dev_done`；aiauto-test R-4 收尾刷 `status:closed` + `pass_rate` + **`ai_report_finalized:true` + `ai_report_finalized_at`（★ 报告冻结基准，报告不可变铁律）**。★ **build 一经 finalize 即不可复用**（3.1.5 强制铸新 build）、报告 data 不可覆盖（emit-report 拒写 + gate 校 mtime）


## 部署分支的未配置 CICD 回退与 #1d 通知模板要点（phase-3-5b.md 的外置正文）

- **未接入 CICD**（`memory/aidp-config.yaml` 的 `cicd.provider=none` / 无 `cicd.pipelines.<env>`，或 `cicd_watch.py` 退出码 3：提供方 CLI/凭据不可用）→ 无远端流水线可监控/重试；但**部署就绪仍应把关，别让测试链路对没起来的环境空跑**：若已配就绪探针字段（`cloud_ready_api_url` 等）→ push 后走 **Phase 3.2.1 Step D 部署就绪探针**（HTTP 登录后自身接口连续 2 次取数，**不依赖 CICD**）通过**才**写 `last_deployed_at`；未配就绪字段 → 保持轻量（push 后直接写 `last_deployed_at`、就绪探测留给 aiauto-test）。两种情况都在 #1d / 终端 WARN「未接入 CICD 流水线监听，部署失败不会自动重试，请自行确认部署已成功」。

- **★ 里程碑通知 #1d 部署完成-代码已推送（见 0.1bis「#1d 部署完成通知模板」）**——`deployment.mode != none` 且未带 `--skip-deploy` 时，部署动作完成（`last_deployed_at` 写入）后**立即经 `notify.py --auto` 发通知**（未配置任何渠道 = 退出码 3，静默跳过）：播报版本 / 部署模式 / 访问 URL / 代码已推 origin/`{branch}` + **接力强提示**「如未挂 `/loop 5m /sprint-aiauto-test --unattended` 则后续 AI 测试不会自动开始」。这是开发链路对测试链路的交接点，补齐部署阶段的里程碑播报。`mode=none` / `--skip-deploy` → 不发（接力提示由 Phase 3.4 #3 通知导航兜底）。


## 写本 build 执行数据文件的注册细则（phase-3-4.md 的外置正文）

3. **写本 build 执行数据文件（计划态）+ 注册到两页**：按 `{{AIDP_HOME}}/templates/reports/AI执行报告/data/示例_build1001.js` 数据契约，写 `$RPT/AI执行报告/data/${BUILD}.js`（`window.__AIRUNS__.push({...})`），**先填计划态字段**——`plan.html` 据此渲染工作流 stepper / 计划甘特 / 步骤依赖表 / 功能点比对（计划视图全部由 `plan.js` 从本数据自动渲染，无独立计划 md）；结果态字段（`overview`/`testSummary`/`defects`/`risks` 等）留待 Phase 3.4 finalize。本步填：



## 部署前安全网为何要在 autopilot 侧再跑一次

7×24 主路径逐 tick 派的是 `/sprint-full`、根本不经过 `/sprint-batch`；而链内调 `/sprint-batch`
时又恒带 `--skip-aiauto-test`——两条路都到不了 Step 6.0.5 / 6.0.6 那两道门。

漏掉的后果不是"少校一次"：本版有 SQL 却没应用时，push→CICD→就绪探针照样全绿
（探针不碰新表就照样 200），涉及新表的用例整批 500 被判成"代码缺陷"进 `auto_fixable_pending`，
自动修复反复修一个根本不是代码的问题，直到 `retest_auto_cap` 配额耗尽按 `retest-cap` 冻结。


## 未收敛计数为何要跨 build 清零

`aiauto_test_unconverged_streak` 只在 `CONVERGED=1` 时清零，而"修复 → 重部署 → 铸新 build 复测"
这条**正常**路径上从来不经过 `CONVERGED=1`。于是 streak 跨 build 单调累加：第 2 个修复轮就可能
撞上冻结阈值 10，而 `retest_auto_cap` 的自动修复配额根本没用完，报告还会写成「连续 10 轮未收敛」。
铸新 build 即清零，与测试链路侧「未收敛时的重测节流」配套。


## 全部关闭分支的 exit 0

本仓其余 12 处 `exit 0` 都带「已记账 + 已告警 → 让位本 tick」的语义，`phase-3-5.md` 的
`REMAIN_COUNT -eq 0` 那处是**唯一例外**：它只结束当前 Bash 围栏，随后要继续往下走同一分片的
「部署动作」段。被按既定口径读成"让位本 tick"的后果是——最后一个 Sprint 关闭的那个 tick 直接退出，
部署段不跑、`last_deployed_at` / `phase_beta_done_at` 永不写，测试链路 `current-version` 永远
选不出该版本；而开发链路因心跳仍在判"测试链路健康"，最终以 `unconverged` 冻结，
告警文案说"测试链路存活但未收敛"，真相是从来没部署过。故该行必须就地写明语义差别。


## 环境类复探为何遍历全部被冻版本、并下沉到脚本

被冻版本会被 0.3.4 从候选剔除，只探「本轮目标版本」时被冻版本永远不是探针的入参；
而 `autopilot.target_version` 要到 0.3.4 末尾才落盘，排在它之前读到的是上一 tick 的值。
故复探对 `needs_human=true` 的全部版本逐个调用 `autopilot_unfreeze.py --env-reprobe <V> --apply`。
环境类的类别集合直接解析冻结枚举表：flows 手抄 case 列表会漏掉新增的环境类 reason，
被漏掉的 reason 既不在复探里、也拿不到「新部署」证据（冻结版本不再部署）——一次瞬时故障就永久冻结。
复探按指数退避（20min 起、封顶 4h、最多 10 次）：瞬时故障几十分钟内自愈，持续故障不会每 tick 重试刷告警，
用尽后转人工并告警一次。


## S2 尾段孤儿（排除子句为何必须限定到 hold 游标）

「末个 Sprint 一关闭」该版当场就是 S2，也就是 `PRE_RELEASE_VERSION`。若排除子句按
`== PRE_RELEASE_VERSION` 一刀切，它**恰好只在规则 1 唯一要救的那个场景里生效**——
两条规则写在同一个 bullet 里、彼此归零。

后果链：TARGET 恒 null → 决策矩阵只跑 Phase 2 → 门 0a 因 `last_deployed_at` 为空而 hold →
3 tick 后写 `deploy-unreachable`（**诊断与事实相反**：不是环境不可达，是根本没人去跑部署那一步）
→ 环境类自动复探清冻结 → 再 3 tick 重冻。**周期永动，永不推进、永不实测、
build 永停骨架**，唯一出路是人工 `--target`，直接击穿「0 人工干预」。

故排除只在游标属 Phase 2 自己写的 hold 值（`2-prerelease`）时成立；开发尾段游标
（`3.2.1-deploy` / `3.2.1-probe` / `3.3-audit` / `3.4-finish`）下该版必须仍可作 TARGET
把部署/探针/终审/收尾跑完——本 tick 的 hold 由 Phase 2 的 `PRERELEASE_HOLD` 保证，
不需要靠剔除候选来实现。


## PRE_RELEASE_VERSION 为何必须与 TARGET_VERSION 一样落 baseline 顶层

`autopilot_tick_flags.py::BASELINE_FALLBACK` 给 `PRE_RELEASE_VERSION` 登记的真源是
`autopilot.pre_release_version`——**但此前全仓没有任何一行写它**，回落因此是条死路：
tick 命名空间每 tick 整段重写，0.3.4 那次 `tick_flags set` 只在**当轮**有效。

于是只要 Phase 2 是从 `run_state` 游标**断点续跑**进来的（不重跑 0.3.4），
`PRE_RELEASE_VERSION` 就取空，其后 Phase 2 全部 jq 查询打在 `.versions.""` 上、
无一命中：门 0a 拿不到 `last_deployed_at` → 判 `deploy-unreachable` 冻结。
诊断写的是"环境不可达"，真因是"版本号是空串"——两者毫无关系，人接手时会去查环境。

这与 `TARGET_VERSION` 那次（21 份分片读它、无一赋值 → run_state 一次都没落盘）
是同一形状的缺陷，只是当时补了 `TARGET_VERSION` 一行、漏了并列的这一行。
两行必须成对存在。

## 复测闭环为何必须给 TARGET 加第二条豁免（「进不了 Phase 3」）

自动修复复测闭环（0.3.4bis）的触发前提是「本 build 已被浏览器实测过」，而实测发生在**部署之后**、
末个 Sprint 关闭之后——此刻该版按 0.3.3 状态机**必为 S2**（计划在 + 所有 Sprint ✅ + `internal_released_at` 空）。

若 TARGET 候选只取 {S0, S1}：S2 不在其中 ⇒ TARGET 判 null，同时该版被选为 PRE_RELEASE；
首个复测 tick 的 `run_state.next_phase` 是上一轮收尾写的 `"done"`，尾段续跑那条也不命中；
此后 Phase 2 hold 把游标写成 `2-prerelease`，恰好落进尾段续跑的排除项。
**于是 TARGET 恒 null → 0.3.5 矩阵判「仅跑 Phase 2」→ Phase 3 整段不跑。**

而闭环要用的三步——**重部署（3.2）/ 铸新 build（3.1.5）/ 复测**——全在 Phase 3。
结果：`/sprint-bugfix` 可能已经改了代码，却没有部署、没有新 build、没有复测；
`auto_fixable_pending` 又已在 step 2.1 被置 false，下一 tick 落回常规分支；
Phase 2 每 tick `prerelease_test_hold_streak +1`，满阈按 `unconverged` 冻结。
表现为「改了代码、没有任何通知、两小时后冻结待人」——**设计目标里"测试失败后的自动修复与复测"整句落空**。

故补第二条豁免，并把 0.3.5 矩阵里「TARGET = PRE_RELEASE」那一格拆成两种：
带 `auto_fixable_pending` 的是**合法组合**（Phase 3 优先），不带的才是数据冲突。

## CICD 重试配额为何必须跨 build 清零

`versions.{V}.cicd_run.cicd_retry_count` 是**版本级**字段，而全仓对它只有 `get` 与 `bump`、
**没有任何 `del` / `set 0`** —— 于是 `phase-3-6b.md` 自称的「本轮重试 N 次」实际是
**版本生命周期总配额**。

一个版本内会多次部署（全量开发一次 + 自动修复复测最多 3 次 + 人工介入后若干次）。
期间累计发生 3 次偶发 CICD 失败后，第 4 次部署一失败即 `CICD_RETRY >= cicd_max_retries` →
直接走失败处置、**零重试**，与同文件「CICD 失败第一动作恒为重试」直接矛盾；
而该分支出口写回 `3.2.1-deploy`，下 tick 重入仍立刻超限 ⇒ 每 tick `dev_fail_streak +1` ⇒ 3 tick 冻结。

故在 Phase 3.1.5 铸新 build 处一并清零（与 `aiauto_test_unconverged_streak` 同款位置、同款理由：
新 build = 新一轮，旧轮次的计数不该继续计入）。

## 复测轮次为何不能按「已 finalize 的 build 数」算

`ai_report_finalized` 只在**收敛轮**（测试链路收敛）或**冻结收口**时写。
而自动修复复测闭环的每一轮都是未收敛 —— 都不 finalize。

于是 `RETEST_ROUND = 已 finalize 的 build 数 + 1` 恒等于 1，`RETEST_LABEL` 永远显示
「第 1 轮复测」，#0/#D 通知与 SPA 的复测关系失真（属「报告如实」范畴）。
改按 `builds[] | select(.retest_of != null) | length + 1` 计 —— 复测 build 一定带 `retest_of`。


## Phase 3.1.5 出口：「无未关闭 Sprint」为什么不是 fail-closed

原实现在 `ENTRY_MODE=full` 且 `NEXT_SPRINT` 为空时裸 `exit 1`。看着是保守，实际是**复测轮的必经之路**：

- 自动修复复测闭环（0.3.4bis 分支②）派完 `/sprint-bugfix` 后把游标写成 `3.1.5-build`；
- 而复测的**前提**就是「末个 Sprint 已关闭 → 部署 → 实测出缺陷」——此刻该版 Sprint **必然全关**，
  `plan_sprints.py` 的 `next_sprint` 返回空串；
- `ENTRY_MODE` 这一 tick 回落读 baseline，拿到的是 3.1.0 上一轮写的 `full`（无人值守下
  `USER_INTENT` 恒空、走不到 `incremental` 那条赋值）；
- ⇒ 每次复测重入都命中 `exit 1`，而它**不 bump `dev_fail_streak`、不写 `needs_human`、不发 #4**；
  `autopilot_stuck_check.py` 要求 `phase_enter_count ≥ 8`，可该计数的唯一维护者是
  `baseline_edit.py run-state`，本路径在写 run-state **之前**就退了 ⇒ 永远到不了阈值。
  7×24 的表现是「挂着刷屏、什么都不推进、零告警」。

同样命中的还有 step 3bis 人工解冻后的复测、以及 `--target <V>` 点名重跑一个已开发完的版本。

故判据改为：**全部 Sprint 已关闭 = 合法的复测/重跑态**，直接进 `3.2-dev`（`phase-3-5.md` step 1
已有 `REMAIN_COUNT -eq 0 → 跳过 Sprint 循环、直接进部署段` 的分支接住它），
`NEXT_SPRINT` 置 `done`。真正该 fail-closed 的是 `plan_sprints.py` 自身解析失败，
那条由它上一行的 `|| exit 1` 与 `REMAIN_COUNT:?` 守着，不受本次放宽影响。


## Phase 3.2 出口路由：两个判据为什么必须读真源而不是 baseline

出口原本按 baseline 里的流水线映射副本与 `versions.{V}.cloud_ready_api_url`
路由到 `3.2.1-deploy` / `3.2.1-probe`。这两个键**全仓只有读、没有任何写入方**：

- CICD 流水线映射的真源是 `memory/aidp-config.yaml` 的 `cicd` 段（`provider` + `pipelines`）
  （`cicd_watch.py` 读的就是它），从来没有人把它搬进 baseline；
- `cloud_ready_api_url` / `cloud_ready_page_url` 只在 PRD `autopilot_decisions.deployment`
  里声明过，同样没有搬运。

⇒ 两个判据恒假，`NEXT_PHASE_AFTER_DEV` **恒等于 `3.3-audit`**，连旗舰配置
`cloud_deploy_trigger=cicd-provider` 也不例外。而 CICD 监听（默认上限 900s）+ 就绪探针
（默认上限 600s）合计可达 25 分钟，**远超 10m 的 tick 间隔**——一旦跨 tick，
下一 tick 按游标 `3.3-audit` 恢复，**整段 3.2.1 被跳过**、`last_deployed_at` 永不写入。

后续是一条静默链：测试链路的选版判据 `phase_beta_done_at != null` 取不到 ⇒ 选不出版本 ⇒
early-exit 且不写 `aiauto_blocked_reason`；而心跳在 early-exit **之前**已无条件写入 ⇒
收尾门的 `test_loop_alive()` 判 True ⇒ autopilot 取 `GATE_STAGE=skeleton` 判骨架齐全 PASS。
**两条 loop 都在正常刷屏、什么都没测、零告警、永不冻结。**

故改由 `autopilot_tick_flags.py` 的 `CICD_PIPELINE_BOUND` / `CLOUD_READY_URL` 两个动态兜底读真源
（前者与 `cicd_watch.py` 同一处，后者复用 `_prd_deploy_field` 的按版本取值口径，
⛔ 都不要在 flow 里再硬编码一次路径，那就成了第二信源）。


## `_HUMAN_ONLY` 类冻结的逃生阀：`--target <V>` 为什么必须可执行地落盘

`--target` 有解析器（`autopilot_tick_flags.py` 把它解析成 `TARGET_FLAG_VALUE`），
但**开发链路一次都没读过它**——全部消费点都在测试链路。而 0.3.4 承诺
「显式点名即解冻该版本一次，绕过 `needs_human` 跳过」。

代价：`autopilot_unfreeze.py` 的 `_HUMAN_ONLY` 那几类冻结
（`handoff-exhausted` / `stuck-phase` / `release-blocked` / `audit-critical`）**探针一律不解冻**，
文档化的三条恢复路径里，无人值守下真正干净可用的只有一条：

| 恢复路径 | 无人值守下是否可用 |
|---|---|
| 人工清 `needs_human` | ✅（手改 baseline） |
| `--target <V>` | ❌ 曾经零消费者（本次已补可执行块） |
| `--reset-baseline` | ⚠️ 可用，但**毁掉整份 baseline**（丢掉所有版本的状态机） |

故必须在候选筛选**之前**就地消费它——这与「一个 flag 有解析器但零消费者、
而文档称它是唯一授权」是同一形态的缺陷。


## S2 判定为什么用通配而不是硬判 `01_研发执行计划.md`

硬判 `01_` 会让**拆分成多册**的版本永远判不出 S2 ⇒ Phase 2 的上版准发布对它永不触发 ⇒
`internal_released_at` 永不写入 ⇒ 该版**永远留在选版候选集里被反复选中**，
表现为「同一个版本被一轮又一轮地重新开发」。故与 S1 同用通配口径。


## test-intent 分流：裁剪之后仍必须做的事

无论最终判成 full 还是 test-only，**必须先按 Phase 0「前置硬门」跑完 Phase 0**（通知渠道检查并打印来源、`.mcp.json`、版本扫描；#0a 默认不发）**再**委派；**严禁**识别到 test-intent 就直接 invoke `/sprint-aiauto-test` / 直接驱动浏览器而跳过 Phase 0 配置收集与通道就绪打印（这是「通知渠道就绪却零推送」的根因，详见 Phase 0 开头「前置硬门」）。test-only 下 **#0 版本扫描通知不发**（开发链路节点），见 0.1bis 通知节点矩阵。

## 0.5bis 适用面 —— 为什么白名单不能挂在 `LOOP_UNATTENDED` 上

0.5bis 原本整段以「无人值守」为前提：D4 总则开头就是 `LOOP_UNATTENDED=1 / --unattended` 上下文下……，命令主体 Phase 0 骨架表那一行的触发条件也写着 `LOOP_UNATTENDED=1`。**门控写在触发条件上的后果最隐蔽**：交互式单次调用**根本不会 Read 这份分片**，于是它连"哪些门不许弹窗"这份唯一信源都看不到。

而 P0-4 / IRON-10 明确要求**交互式单次由本次调用自身跑完全流程与缺陷闭环**。两条规则叠起来，交互式单次落进一个真空：**既被要求跑满全流程，又不受任何询问约束**。实际项目实测就是从这里把 AI 测试半环丢回给人的——它跑完了版本规划增量、开发、静态验证、commit/push、CICD 部署、就绪探针，然后停下来问「需要我接着跑浏览器实测吗」。

修法不是"把交互式也按无人值守办"（那会丢掉"用户就在旁边、问清比占位更优"这个真实优势），而是**把两件事拆开**：
- **要不要遵守白名单** —— 与模式无关，都遵守；
- **命中白名单之后怎么处置** —— 这才是两种模式的唯一差别（无人值守取占位继续，交互式允许弹一次问清、**然后必须在本轮内接着跑完**）。

⛔ 特别要堵的是"问一句然后结束回合"：交互式的弹窗额度只用于**取回继续所需的信息**，不是把剩余流程的执行权交还用户。判据仍是客观状态（返回时 `run_state` 是否停在非终态、有没有人会来接），不是话术。

## 0.6bis 前置资源对账 —— 缺账号为什么会成为现成借口

0.6「字段缺失统一在 Phase 0 收集」管的是 **baseline 配置字段**（通知渠道 / deployment 各段）；批 6 又把**测试账号与 Chrome 连接信息**明确划给 `/sprint-aiauto-test` Phase 0.4（刻意的边界：autopilot 不承担测试期才需要的敏感字段）。两条加起来留下一块**没有归属的地**：**用例册声明需要哪些前置账号与前置数据**。

没有归属就没有对账。执行体于是可以在任意时刻凭感觉宣称"我需要第二个测试企业账号"而暂停——**而那个账号本来就写在约定 38 的产物 `01_测试环境与账号.md` 里**，同一会话里它还读过那个文件。整条链路上**没有任何一步**会去做这次比对。

本门刻意只做三件事、不越界：
1. **对账**：用例册里残留的 `{待用户填写: <字段>}` 占位符 = "声明了却没填"。判据取自上游 `dev-manual-testcase` 已统一的占位符格式，**不做模糊语义解析**——模糊解析的失效形态同样是"0 命中"，与通过同形。
2. **落结论**：写 baseline `versions.{V}.testdata_prereq`，让缺口成为可查事实而非某一轮的口头判断。
3. **定性**：跑过之后，"缺前置数据/账号"**永久不再是暂停理由**。真缺时的正确动作是该用例标 `block` + 写明缺什么、继续跑完其余用例（与 `dev-manual-testcase`「前置不满足记 block、不得换变体路径凑 pass」同口径）。

**凭据本身仍不在这里收**——本门只产出对账结论，不碰敏感值，0.6 批 6 的边界原样保留。

**落点必须有两处**：Phase 0 那道门在 full 模式下必然判 `no-casebook`（用例册是 Phase 3.1 的 `/version` Step 2.4.3.5 才生成的）。只放 Phase 0 等于这道门在 full 模式下从未存在——下游踩的正是 full 模式。故 Phase 3.1bis 在"用例册刚落地"那一刻补跑同一道门，两处口径完全一致、不另立一套。

## TARGET_VERSION 为什么没有动态回落

`DYNAMIC_FALLBACK` 曾把 `TARGET_VERSION` 的兜底设成 `current-version`。但 `current-version`
的定义是「`phase_beta_done_at` 非空且 `internal_released_at` 为空」——**那是 `PRE_RELEASE_VERSION`
的定义**。于是 `autopilot.target_version` 为空时两个变量读回同一个版本号，造成两件事：

1. 决策矩阵「有 PRE_RELEASE / TARGET=null → 仅跑 Phase 2」这一行**结构上不可达**，实际落进
   「TARGET == PRE_RELEASE → 数据冲突 → 纳入 `preflight_fail_streak` 熔断」。而"上一版开发完
   等准发布、产品还没提新 PRD"正是 7×24 稳态里**最常见的局面** —— 表现为版本永远归档不了，
   #4 通知却指引"人工 `--reset-baseline` 重建状态机"，而状态机根本没坏。
2. 0.3.4 末尾那道「TARGET_VERSION 落盘失败 → 中止本 tick」自检因回落恒非空而不可触发。

**复现要点（值得记下来）**：第一次尝试复现失败，构造的夹具目录里没有 `{{AIDP_HOME}}/scripts/`。
`autopilot_tick_flags.py` 的 `BASELINE_EDIT` 是**相对路径**，子进程因此直接失败、
`_cur_version()` 返回空串 —— 于是"回落没触发"与"回落不存在"在输出上完全同形。
夹具补上 `{{AIDP_HOME}}/scripts/` 后一次命中。**这正是本仓反复治理的那类失效：工具没跑起来，输出却像通过。**

测试链路要的确实是 `current-version`，那条由 `BASELINE_FALLBACK_BY_COMMAND["aiauto-test"]`
在**更早的 baseline 回落层**单独供给，与本表无关，故移除本表条目不影响它。
回归锁定见 `tests/test_guard_scripts.py::test_tick_flags_target_version_no_fallback`。

## `--target <V>` 逃生阀为什么要清一长串字段

`--target` 在文档四处被宣称为 `_HUMAN_ONLY` 冻结的恢复路径。但"解冻"不等于只清冻结四件套：
各熔断计数**跨 tick 持久**，清了 `needs_human` 却留着 `dev_fail_streak=3`，下一次任何抖动
就是 `N=4 ≥ 阈值` → 立刻重冻。更硬的一条是 `run_state.phase_enter_count` /
`phase_first_entered_at`：Phase 1.3ter 的 `autopilot_stuck_check.py` 有一条
`already-frozen` 早退，靠的正是 `needs_human`；`--target` 把它清掉之后早退失效，
脚本重新评估 `cnt >= 8 and age > 7200` —— 而这两个值的唯一维护者只在换 Phase 时重置，
本 tick 还没走到任何 run-state 写点 ⇒ 两个条件仍成立 ⇒ **同 tick 内确定性重冻 stuck-phase**。
`--target` 于是连 Phase 1 都过不去。

**通则**：任何"解冻/重置"动作，清除面必须覆盖**全部会独立触发再次冻结的状态**，
而不只是冻结标志本身。清单与解冻块同源维护，⛔ 别各写一份。

---

## `--single-sprint` 在无人值守下为何与默认收敛为同一行为

⚠️ **无人值守（`LOOP_UNATTENDED=1`）下 `--single-sprint` 与默认已【收敛为同一行为】**：无人可答"回 `continue`"，且 `HAS_WAKE_SOURCE=1` 时逐 tick 单 Sprint 本就是默认（见 step 1）——故带不带 `--single-sprint` 都走**每个 Sprint 关闭后 `UNATTENDED_YIELD` 退本 tick、下次唤起从 `run_state.next_sprint` 续跑**（绝不空等 30 分钟）。仅**交互式**下它才表示"每 Sprint 等用户回复 `continue`"。⛔ **`HAS_WAKE_SOURCE=0` 时它同样不得 yield**（无受托人），按 step 1 本轮内连跑到底。

---

## 部署动作的「已接入 CICD」判据

**已接入 CICD**（`memory/aidp-config.yaml` 的 `cicd.provider` ≠ `none`、`cicd.pipelines.<env>` 已配 **且** 提供方 CLI/凭据可用，即 `cicd_watch.py` 不返回退出码 3）→ **同样走下方 Phase 3.2.1**（Step A 检测本次 push 自动触发的运行 → Step C 监控执行 + 失败重试 ≤`cicd.max_retries` → Step D 就绪探针通过**才**写 `last_deployed_at`）。⛔ **不在 push 后立即写 `last_deployed_at`**——否则部署在 CI 侧失败也照样放行测试链路空跑，正是开发→测试断链的根因。

## Phase 2 的失败处置传哪个版本

本片全篇作用于 `PRE_RELEASE_VERSION`，失败处置也必须传它。传 `TARGET_VERSION` 有两个后果，
且都不报错：**它恒空时**（「有准发布 / 无开发目标」是决策矩阵里的常态档）`${TARGET_VERSION:?}`
会让整个围栏当场中止 —— 不 bump、不冻结、不发 #4，归档失败完全静默，下个 tick 再撞同一处，
无限空转；**它非空时**更糟 —— 冻结被写到**正在开发的那一版**头上，冻住无辜版本，而真正失败的
准发布版毫无记录，运维顺着 needs_human 查过去查的是另一件事。

reason 用 `release-blocked` 而非 `unconverged`：后者语义是「测试未收敛」、解冻走「冻结后有人
提交过」，拿它标归档失败会把人指向一份根本没跑的测试结果。

心跳时间戳解析异常时判 `alive=0`（fail-closed），与 `autopilot-ceremony-gate.py` 同口径。
判 1 会让「测试链路早已停摆」走成「存活但未收敛」的暂缓档：白等 12 tick 才冻，
而那 12 个 tick 里的告警文案全指着错误方向。

## 让位前必须断言唤醒源

Phase 3.2 的单 Sprint 分支由子 Agent Read 分片执行，**它没见过 Phase 0.0.0 的派生过程**，
只能靠分片里写着的东西判断。所以「本分支仅在 `HAS_WAKE_SOURCE=1` 时进入」不能只写在散文里 ——
散文判错一次就会在无受托人的情况下 `UNATTENDED_YIELD`，`run_state.next_sprint` 停在 NNN、
没有下一 tick 来接，整条链路永久停摆且不报错。围栏里那三行断言就是把这个前提变成可执行的。

## Phase 2 为何恒传 `--unattended`

Phase 2 是**准发布归档**语义（S2 版本，规划期的交互决策早已在 S0/S1 完成）。
真正的理由在于：归档流程内**以 `--unattended` 为条件的非阻塞降级**（典型是中途问询）不透传就仍会弹
`AskUserQuestion`，在 `/loop` 下无人可答、当场挂死。所以它恒传，
不像 Phase 3.1 的新版本规划那样按 `LOOP_UNATTENDED` 条件分流 —— 准发布没有任何需要交互式的环节。

## `--single-sprint` 怎么等 continue

交互式盯看场景：每跑完一个 Sprint 发 #2 通知后暂停，等用户在会话里回复 `continue`
才进下一个。**暂停不是退出**：状态保留在 baseline 里等用户介入（`run_state.next_sprint` 指向下一个 Sprint），
否则一次午饭时间就会把整批 Sprint 的进度丢掉。

## 部署完成 ≠ 可测

流水线成功只说明**部署动作**做完了，不说明应用起得来、更不说明能跑用例。所以 Phase 3.2.1
必须先过部署就绪探针、探针过了才写 `last_deployed_at` 放行测试链路。

判据分两档：**无登录系统**用 health 端点判 UP 即可；**有登录系统**必须以「登录成功后、
自身鉴权接口连续 2 次正常取到数据」为准。⛔ **不能用登录页可达性判就绪** —— 登录页常是
第三方 / SSO 托管的，应用自己没起来它照样返回 200，于是探针全绿、用例一跑全崩，
而失败会被记到测试链路头上。

## `autopilot_decisions` 为什么是「PRD frontmatter 赢」

两处声明位置（PRD 头部 frontmatter / `memory/aidp-config.yaml` 的 `autopilot_decisions:` 兜底段）
同名字段值不同时必须有唯一判定：否则一份长期不更新的兜底段**每轮都被读进合并**，
且因为静默取胜/静默落败，没有任何人会发现它已经过期。

判定给 PRD，依据是三条事实（不是偏好）：

- **机器读侧只认 PRD**：`autopilot_tick_flags.py` 的 `_prd_deploy_mode` / `_prd_deploy_field` /
  `_cloud_ready_url` 只扫 `产品提供/*.md` 的 frontmatter，**没有任何执行体直接读兜底段**。
  让兜底段赢 = 让一个没人读的值去覆盖唯一被真正消费的值。
- **只有 PRD 有版本维度**：读侧全部是「按本轮目标版本取值 + 版本回落」，兜底段全项目一份、
  表达不了"哪一版"；让它赢就是让上一版的口径污染本版（与 `_prd_deploy_mode` 自己论证过的
  "扫到第一个声明就返回会取到别的版本"同一类错误）。
- **写回方向也是 PRD**：0.6 步骤 5 收集完决策后写回的是 PRD 目录首份 `.md` 的头部，
  兜底段只在没有 PRD 落点时兜底 —— 它天然是快照，不是真源。

**冲突必须出声**：赢了不吭声正是陈旧副本能活三个月的原因。故合并器逐条打印
`[decisions-conflict]`，并给出「冲突 N 处 / 一致 N 处 / 单边 N 处」计数 + 两条可照抄的清理路径。
判据是**有没有冲突**、不是谁更新：新写进兜底副本的错值一样会让实际行为出错
（下游实测的两处冲突 `cloud_deploy_trigger` 与 `cloud_deploy_url` 都是直接改变行为的）。
mtime 还早于 PRD 的另判 `stale-fallback`，措辞更重、退出码同为 1。
**只旧不冲突只记 INFO、退出码 0** —— 没造成危害就不制造噪音，噪音一大这道告警就会被无视。

**⛔ 收集结果不许两处都写**：兜底副本从写下那一刻起就开始落后，而它的值永远赢不了，
只会在此后每一轮以 `[decisions-conflict]` 刷屏。有 PRD 落点就只写 PRD。

## Phase 0.1 前置熔断为什么必须走 `autopilot_fail_handle.py --preflight`

这是整条链路**最上游**的冻结点：它发生在 `TARGET_VERSION` 解析之前，冻的是**所有版本**。
而它长期一条 #4 都没发过 —— 「发 #4 通知」只存在于 `echo` 的文案与行尾注释里。

三道门恰好都盖不到它，所以这个缺口能一直留着：

| 门 | 为什么盖不到 |
| :- | :- |
| `check_freeze_contract.py` | 站点判据是 `set … needs_human true`，而本处冻结写的是**顶层** `preflight_frozen_at` |
| `autopilot-ceremony-gate.py` | `_derive_expect_cards` 的基集是 `#0/#1b/#1c`，#4 从不在期望通知集里 |
| `check_prose_vs_executable.py` | 只判「整个目录有没有」`notify.py`，同目录别处有就放行本文件 |

表现形态：feature 分支 rebase 冲突或 detached HEAD（7×24 里很常见）→ 3 个 tick 后
置 `preflight_frozen_at` → 此后每 tick 一行日志静默退出。**挂着跑、什么都没发生、零通知。**

收编进 `autopilot_fail_handle.py` 而不是在 flow 里补一段 bash，有三个理由：
① 「记账 → 判阈 → 冻结 → 发 #4」与主路径是同一套动作，两份实现必然漂移；
② 该脚本已带「写盘返回码逐条检查」——熔断标记没落盘时不再宣告已熔断；
③ flow 分片逼近 20480 硬上限时，补 bash 的第一反应是把它压成一句 echo，
   而那正是这个缺陷的由来。收成一行调用后，这片反而腾出了六百多字节。

## 无人值守未配置通知渠道时为什么必须留痕（而不只是把 `notify_enabled` 置 false）

冷启动直接挂两条 loop 是文档推荐的标准姿势。若此时 `memory/aidp-config.yaml` 的 `notify.channels` 还没配，
第一个 tick 就会落盘 `notify_enabled=false` —— 而恢复路径只有「人来跑一次交互式配置向导」，
没有任何自动复探。

后果不是"少发几条通知"：`invariants.md` 与 `phase-0-4.md` 都写着
**#4 是冻结时刻唯一对外可见的信号**，而在这条路径上它恒不成立 ——
此后所有冻结只落 baseline 与本地终端，外面一片安静，看起来和还在正常跑一模一样。

落 `notify_disabled_reason` + `notify_disabled_at` 之后，解冻复探就能按
「配置源 mtime 晚于关闭时刻」自动重开，与其它配置类冻结同一套判据 —— 不必再等人想起来。

## fetch 退出码为何不能进管道

`git fetch --all --prune 2>&1 | tail -5` 的 `$?` 是 `tail` 的退出码，恒为 0——fetch 失败
被完全吞掉。随后的 `git rev-parse "$UPSTREAM"` 读的是**本地缓存 ref**，于是恒等于
`LOCAL_HEAD`，流程打印「✅ 本地与 upstream 已同步」。

净效果：产品新推的 PRD 永远拉不下来，Phase 1 判 no-change 静默退出。**整条命令赖以立命的
监听就此死掉，而终端全是绿勾**——没有任何一处会变红。

`git-fetch-failed` / `remote-unreachable` 两个 reason 的解冻白名单一直备着，缺的是
**生产者**。现在 fetch 的退出码单独捕获后走 `_preflight_fail git-fetch-failed`，白名单
才真正接上。

## IS_LOOP_CONTEXT 为何需要第二信源

`IS_LOOP_CONTEXT` 是本架构最承重的信号，却是唯一**靠模型就地改写字面量**供给的——纯 shell
读不到"当前 prompt 里有没有 `/loop`"。它混在一段 40 行 bash 中间，没有任何机器校验。

漏改（停在默认的 `0`）不会报错，会变成：

1. `HAS_WAKE_SOURCE=0` ⇒ 逐 tick 单 Sprint 整体关闭；
2. 更要命的是 `autopilot_fail_handle.py` 的 `freeze = streak >= threshold **or** wake == "0"`
   ——**任何一次瞬态失败（529 / 网络抖动 / CICD 平台 API 超时）当场冻结版本，3 次重试配额一次都用不上**。

唯一兜底原本是写到 stderr 的几行字，而无人值守场景恰好没人读 stderr。

`LOOP_EVIDENCE` 由 `autopilot_tick_flags.py parse` 依据 **tick 历史**自动算出：窗口
（`LOOP_EVIDENCE_WINDOW_SECONDS`，默认 2400s ≈ autopilot 10m 周期的 4 倍）内出现 **≥2 次**
历史 tick 才置 1。

两条设计约束：
- **≥2 次而非 1 次**：手工连跑两遍不该被误升级成 loop；真正的 `/loop` 在一个窗口里必然留下
  远多于 2 条记录。
- **只增补、不否定**：模型已判 1 时本值无作用。反向否定会把真 loop 判死，代价比漏判大得多。

## reset 旗标为何必须有执行者

`--reset-baseline` / `--reset-unattended` 旗标在命令参数表里有定义，`invariants.md` 还把 `--reset-baseline` 称作某类冻结的
**唯一出路**，冻结 #4 通知正文更是直接把它写给用户当恢复动作。

但它们长期**没有任何实现**：`BOOL_FLAGS` 一个都没登记，全仓也搜不到对应变量。
净效果是——用户被冻结通知指引着去跑一个什么都不做的参数，然后回来发现还冻着。

现由 `autopilot_reset.py` 统一执行，接在 Phase 0.1 的**最前面**：它们要改/删的正是
baseline，必须先于任何读取。`--reset-baseline` 走 rc=10（执行完结束本 tick，语义就是
"删掉后退出、下次任意 PRD 变化再触发"），`--reset-unattended` 走 rc=11 继续本 tick。
