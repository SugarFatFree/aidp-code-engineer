# /sprint-autopilot · 顶层执行铁律（invariants）

> 本文件承载 `/sprint-autopilot` 的**顶层执行铁律群**（原内联在命令正文，A1 瘦身下沉至此，正文只留一行一条的清单 + 本指针）。
> 各铁律**标题原样保留**，命令/flows 里"见「XXX不变式」/「委派安全铁律」/「委派职责矩阵」/「上下文管理策略」"等**按名引用一律解析到本文件对应小节**。
> ⚠️ 权威性：这些是 exit-1 级顶层铁律，与「强制仪式不可精简硬门」同级；进入 Phase 2/3 执行框架时按名遵守，不得以"交互式/省时"绕过。
> ⚠️ 维护：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-autopilot/invariants.md`。
>
> ⛔⛔ **作用域边界（本文件全部不变式共用，务必先读）**：以下铁律的作用域 = **经 `/sprint-autopilot` 入口的工作**。
> **⛔ 不适用于「链外任务」**（用户口述 → 改代码 → 直接 commit+push、全程没走任何 `/sprint-*`）——
> 链外的动作集以**约定 41**为准：约定 22/24/31.5 与静态验证照做，但**⛔ 不铸 build、⛔ 不跑浏览器实测、部署默认否**。
>
> **Why 必须写这一句**：IRON-2 的限定语本就是「向 `/sprint-autopilot` 提供的自然语言意图」，语义上只管链内；
> 而「禁无仪式的裸交付」这类措辞的强度足以让执行体把整套当全场景铁律，于是链外小改动也会被推着
> 走完部署 + CICD 监听 + 浏览器实测。**限定语不等于边界 —— 边界要正面写出来**，即上面这一句。

---

> ⚠️ **小节按「事故权重」排序、不按编号升序**（1 → 2 → 10 → 9 → 3 …）：编号是稳定锚点、供全仓交叉引用，顺序则让最常踩的铁律排在前面。按编号检索请用 `## IRON-N` 精确匹配。

## IRON-1：执行开始后绝不停下来问「继续 / 下一批」

> ⛔⛔ **执行开始后绝不停下来问「回复继续 / 要不要继续下一批 / 是否接着建下一块」（本次反馈根因，最高强制铁律）**：进入 Phase 2/3 执行后，**只要还有可执行的工作**（契约已定 / 后端已就绪 / 可直接建 / 计划里的下一批），就**一路执行到底**——把本轮所有能做的工作**一次全做完**，**绝不**把工作自行切成"一批批"再逐批停下等用户回"继续"。
> - **非阻塞的待确认 / 待办项**（跨应用契约待对方回复、上游系统待确认字段、他方接口未交付、UI 自动化环境受阻等）→ **记入「待办 / 待确认清单」并继续做能做的**：契约已定的先建表/接口/前端、第三方未交付走约定 26 Mock、字段待确认用 PRD 默认或标 TODO——**绝不因这些非阻塞项停下整个执行流去问"继续"**；它们在**本轮结束时统一汇报**，不在执行中途打断。
> - **唯一允许的暂停**：① Phase 0 一次性配置收集（0.6 收完即禁中途阻塞）② 真正的硬阻塞（push 失败 / CICD 连续失败满 3 次 / 部署就绪探针超时 / `dev_fail_streak≥3` 熔断——均走「失败处置」#4 @用户）。**除此之外一切"停下来问要不要继续"都是违规。**
> - **判据**：自问"删掉这次暂停，我还能继续做有意义的工作吗？"——能 → 就不该停、继续做；只有"不做完这个外部依赖就真的一步都动不了"才算硬阻塞。**把"回复「继续」我接着建 XXX"当作一次输出来结束轮次 = 严重违规**——那批 XXX 只要可建，就应当在本轮直接建完，而不是停下来等一个"继续"。
>
> **★★ 结构级机器门（本条已从自律级升级，⛔ 命令返回前必跑）**：
> ```bash
> V=$(python3 .aidp/scripts/baseline_edit.py get autopilot.target_version --default "")
> [ -z "$V" ] && V=$(python3 .aidp/scripts/baseline_edit.py current-version)   # 兜底
> python3 .aidp/scripts/autopilot-ceremony-gate.py handback-check --version "$V" --record
> ```
> `exit 1` = 契约违背（`wake_source_this_tick==0` 且 `run_state.next_phase`/`next_sprint` 任一非空且 ≠ `done`），**不得就此收工**。
> ⚠️ 它**刻意不并进 `ceremony-gate check`**：那道门在测试链路 Phase 3.7 / 3.4 step2 就跑，而 `run-state … done` 要到收尾才写，并进去就是每轮必 FAIL 的假阳性（与当初拆 `--stage skeleton|final` 躲的是同一类时序坑）。故 HANDBACK 的唯一落点 = **命令返回前**。
> **Why 必须有机器门**：「强制仪式产物必须齐全」早已升级为结构级（缺产物 `exit 1`，执行体绕不过），而本条一直只有文档谴责——两条规则强制度不对称，可后者失效的后果（整轮停摆）并不更轻。真实事故：规划段跑完就问"要我继续进入开发阶段吗？"，本轮 `HAS_WAKE_SOURCE=0`、没有下一 tick 会来接，Phase 3.2~3.4 连同全部 Sprint 被丢回给用户。
> **★ 判定式、不看话术**：文档一度点名禁的是"如需无人值守请挂 `/loop`"这一类**具体措辞**，而真实失效用的是**"要我继续吗 / 你想先看看吗"**这种征询式变体——措辞完全不同、实质一样，于是没被自己的禁令拦住。**枚举话术堵不住，只看客观状态才堵得住**（同 `ux-logic-extractor` 从"列举措辞"改为"看 `AskUserQuestion` 选项集合、不看问法"的同构收敛）。
> **★ 上一轮遗留自检**：Phase 0 开局读 `autopilot.last_handback`——上一轮判定为 `VIOLATION` 则打印醒目告警并**直接从 `run_state` 续跑那个未完成的 Phase**（本就是 IRON-3 的行为，现在有了显式信号，不再依赖执行体自己想起来）。

## IRON-2：入口即仪式 —— 需求/意图语义不改变产物义务

> ⛔ **需求/意图上下文语义 + autopilot 入口的产物仪式保证（强制铁律）**：
>
> - **入参语义（自然语言需求/意图上下文）**：向 `/sprint-autopilot` 提供的自然语言意图（新功能 / bug 修复 / 功能优化 / 字段对齐等增量）是**对目标版本要执行的意图上下文**——**目标版本由自动扫描 `docs/requirements/` 识别、或 `--target <版本>` 显式锁定**（位置参数 `<version>` 已移除，见 flag 表；首位位置参数是 `[PRD_root]` 需求大目录）。**有明确执行意图 = 直接进 Phase 2/3 仪式框架**，**不是**"对已交付页面做一次悄无声息的定向修正"。
> - **★ autopilot 入口 = 产物仪式保证（核心铁律）**：凡经 `/sprint-autopilot` 入口执行的任何工作——**无论被识别为新功能、还是 bug 修复 / 功能优化 / 增量**——都**必须**完成「**铸 build 号 + 产 AI 执行报告（+经测试链路出 AI 测试报告）+ 发里程碑通知**」这套强制仪式（**数据清理文档不属强制仪式**——它是测试链路的 **best-effort 附带产物**，每 build 一份落 `docs/reports/{version}/AI数据清理/`、生成失败仅 WARN 不阻塞收尾、不进 ceremony gate，见 aiauto-test Phase 3.7 Step 4/4.1）（由 Phase 3「⛔ 强制仪式不可精简硬门」+ `autopilot-ceremony-gate.py` 兜底校验）。**允许 autopilot 识别内容类型并据此选「做什么工作」**：新功能（有/需 PRD）→ Phase 3 的 `/version` + `/sprint-batch`；**bug 修复 / 功能优化增量 → Phase 3 增量模式**（铸本轮 build 号后，经 `/sprint-bugfix` 或 `/sprint-dev` 累进做实际改动，再产 AI 执行报告 + 发通知 + 触发测试链路）。**分类影响的只是"做什么工作"，绝不影响"是否产出 build/报告/通知"——这套仪式产物在任一路径下都必出。**
> ★★ **且不因"手动/交互式/大提示词/自己直接干了"而免除**：`emit-report.py`（产 HTML 报告，落本地 `docs/reports/`）/ `autopilot-ceremony-gate.py`（校验）/ 里程碑通知节点，**无论执行体逐字走 Phase 3.4 编号步骤、还是直接调 `/version`+改代码+驱动 chrome 手动完成开发测试，都必须产出**——由文末「**## 命令收尾硬门（入口级 ceremony 闸）**」作**无条件、结构级**兜底：本轮只要发生了开发/测试动作，命令返回前必跑一次 ceremony 校验（build/HTML报告/通知台账），缺失即补产、补不齐不静默收尾。**强制性是结构级、不是自律级**——不把 ceremony 闸埋在"不走就漏"的 Phase 里。
> - **⛔ 禁止的是"无仪式的裸交付"（这才是静默改道）**：绝不允许 autopilot 把需求识别为 bugfix/优化后，**在第一段回复就静默换成裸 `/sprint-bugfix` / `/sprint-dev` 直改 / 普通定向修正、跳过 build/报告/通知**让产物落空，且不告知用户。**识别为增量没问题；跳过仪式产物不行。**
> - **★ 产物缺失必须显式告知（结构级、禁止静默 · 入口级仪式不变式 ③细则）**：仅当 autopilot 因 ① 停在配置向导态（无执行意图的纯探路直接调用）② 无新需求 / baseline 无变化且无 `--once`/执行意图（Phase 1 未命中）③ 版本已全部交付且无增量诉求（S3/S4）④ 其它确实无法进入 Phase 2/3 的兜底原因 而**不产出仪式产物**时，**必须跑结构级告警脚本**（把"必须打印"从自律 prose 升级为脚本强制，堵"既不产物也不告警"黑洞）：
>   ```bash
>   python3 .aidp/scripts/autopilot-ceremony-gate.py check --version <版本> --no-pipeline-reason "<具体依据，如：无执行意图停在配置向导 / Phase 1 未检测到变化 / <版本> 已全部交付>"
>   ```
>   它会 `exit 0` 并结构级打印：`⚠️ 本轮未进入开发流水线…判定依据=<原因>` + `应产 vs 实产：build号/AI执行报告/AI测试报告/里程碑通知 均=无（属预期无产、非缺失）` + 恢复指引（`/sprint-autopilot --target <版本> --once` 或 7×24 并行挂两条 /loop）。**禁止**手写"打印一段文字"糊弄——必须走脚本，让"未进流水线"成为结构级可核验事实。
> - **★ 两条 loop 与报告归属（结尾必说清）**：**autopilot 本命令只产 AI 执行报告**（且必须 Phase 3 真正跑起来才有）；**AI 测试报告 / 测试通知由第二条 `/loop 5m /sprint-aiauto-test --unattended` 产**——**`/loop` 无人值守下只挂 autopilot 一条则测试报告 / 测试通知永不产生**。完整 7×24 = `/loop 10m /sprint-autopilot --unattended` + `/loop 5m /sprint-aiauto-test --unattended` 两条并行。**★ 例外（P0-4）：交互式【单次】调用（非 /loop）→ autopilot 在部署后自己跑一次 `/sprint-aiauto-test --once --unattended`**（无第二条 loop 承担、用户预期"全链路"含测试；除非显式 `--skip-aiauto-test`），故交互单次也能拿到测试报告 + 测试通知。
> - **增量交付的 build/报告归属（概念澄清）**：build 号 + AI 执行报告 + 里程碑通知由 **autopilot 的 Phase 3 仪式框架产出**（新功能与 bugfix/优化增量经 autopilot 入口时都产，见上）。但用户**绕过 autopilot、直接**用 `/sprint-dev` 累进 或 `/sprint-bugfix` 做口述/增量交付时**本就不产 build/报告/通知**（预期行为、非 bug，这类直连增量在报告体系"查无此 build"属正常）——**要让增量也铸 build + 出报告 + 发通知，就经 `/sprint-autopilot` 入口跑，而非直接调子命令。**

## IRON-10：缺陷复验闭环 —— 「没有下一 tick」不是把缺陷交还用户的理由

> ⛔⛔ **本轮测试产出缺陷 → 「修复 → 重部署 → 铸新 build → 复测」是【自动仪式】，不是选项**。
> **⛔ 严禁**输出「建议下一步：铸 buildNNNN 复验」「这条 P1 缺陷怎么处置」这类把既定仪式当选择项交回用户的收尾——**修不修从来不是选项**，严重度只决定顺序与紧急度、绝不决定修不修。
>
> **★ IRON-10：交互式单次调用【由本次调用自身跑完闭环】**（与 IRON-3 同源）：闭环的常规触发点是 Phase 0.3.4bis「每 tick 读 baseline 测试信号」——那是 `/loop` 语境。**交互式单次（`HAS_WAKE_SOURCE=0`）跑完一轮就结束、根本没有"下一 tick"**，闭环无处挂载；0.3.4bis 在 Phase 0，本轮早已跑过。故本轮内测出可自动修复类缺陷时，**由本次调用在本轮内接着跑完**闭环，上限仍是 `retest_auto_cap` 轮、达上限才冻结转人工。与 P0-4「交互单次自跑 AI 测试」同构：两者都在补「交互单次没有下一 tick」这一档。
>
> **★ 结构级兜底（收尾门 3m）**：`autopilot-ceremony-gate.py check --stage final` 新增「缺陷复验闭环」项——报告 `defects[]` 里存在"待复验/待验证/未复验"字样的条目，却既无后继 build 承接复测、也未 `needs_human` 冻结 → **FAIL exit 1**。
> **Why 必须有它**：3j「本轮缺陷清算」只读 `auto_fixable_pending` 布尔量，而闭环 step 2「先记账再动手」一开始就把它置 false ——于是"缺陷已登记、已修复、但从未复验"这一态**在 3j 眼里完全干净**。下游实测：`defects[]` 两条都明写「已修复，⚠️ 待 build1002 复验」，收尾门整体 PASS。「带着未复验的 P1 缺陷正常收尾」由此成为唯一没被机器门覆盖的收尾姿势。
> ⚠️ 判据按**整条缺陷序列化后**匹配、不只看 `status` 字段（`defects[]` 在报告契约里只声明为 list、元素字段自由，真实写法把"待复验"塞在 `status`/`fix`/`note` 都出现过）；且「待」与「复验」之间允许夹内容——真实写法正是「待 **build1002** 复验」，连写模式恰好匹配不到。

## IRON-9：baseline 单一写入口不变式

> ⛔⛔ **baseline 单一写入口不变式（顶层铁律 —— 两条 loop 并发写，裸写必丢更新）**：`memory/.sprint-autopilot-baseline.json` 被**开发链路（`/loop 10m /sprint-autopilot --unattended`）与测试链路（`/loop 5m /sprint-aiauto-test --unattended`）并发写**。**一切写操作必须经 `.aidp/scripts/baseline_edit.py`**（内部 `flock` 排他锁 + **锁内重读** + `os.replace` 原子替换），**⛔ 严禁**在 flow / 命令端写裸 `jq '…' f > tmp && mv tmp f` 或内联 python 直接覆盖整份 —— 那只保证"不半截"，**不保证"不丢对方的字段"**：长 tick 交叉时会把对方刚落的 `ai_report_finalized` / `last_deployed_at` / 各 streak 整体抹掉，表现为重复 finalize、门判据错乱、熔断永不达阈。
> - 常用写法：`baseline_edit.py [--version <V>] set <path> <value> …` / `del <path> …` / `bump <path>` / `touch <path>` / `run-state <cur> <next> [sprint]`；**只读查询**用 `baseline_edit.py get` 或裸 `jq -r`（读不加锁无妨）。
> - 同理适用于**脚本**：`emit-report.py` / `autopilot-deploy-watch.py` 已复用同一把锁；新增任何写 baseline 的脚本一律 `from baseline_edit import LockedBaseline`，不要另起一套写盘范式。
> - **★ 字段被当判据前，必须先回答「谁写的 / 当前路径下它会不会被写」（写入方声明义务）**：baseline 里的**跨链路交接字段**（一条链路写、另一条链路当判据读）**登记时必须在字段说明处写明两件事——「写入方」（哪个 Phase / 哪个脚本写它）与「哪些路径下它不会被写」**。⛔ 缺这两项就拿它当判据，失效形态是**永久假值**：字段恒空 → 判据恒不成立 → 门恒不放行（或恒放行），而这**不产生任何报错**。真实事故两例：① `last_autopilot_head` 只在「云端 CICD + 就绪探针」一条部署路径写，其余部署形态恒空，于是 `unconverged` 冻结在那些形态下**永远解不开**；② 同一字段是**活指针**却被当**冻结时刻快照**用，云端路径下反而在冻结瞬间就被自己解掉。**判定同源**：`check_tick_var_supply.py` 已守「有消费者、无生产者」的变量；本条把同一纪律推到 baseline 字段面上——**有读者、写者只覆盖部分路径**同样是缺陷，只是它不会被"零生产者"检出。
> - 版本号等**含点的键必须加引号**：`versions."V0.1.0".needs_human`，或直接用 `--version V0.1.0` 前缀写法。

## IRON-3：阶段推进不变式

> ⛔⛔ **阶段推进不变式（顶层铁律，与「强制仪式不可精简硬门」同级）**：一经进入 Phase 2/3 执行框架（交互式全量执行语义命中 / `--once` / `/loop` 唤起 / 任一执行意图），**任一 Phase 达成其完成判据后，必须在【同一轮回复内】直接进入下一 Phase，禁止以"汇报进度 / 等待确认 / 阶段性小结 / 先停一下看看"为由停止交还控制权**。
> - **唯一允许停止的两种情形**：① 命中文档明确定义的 `AskUserQuestion` 决策门（交互式；无人值守消费预声明不停）② 全流程终态达成（本轮无下一 Phase）。**"用户没说继续" / "改动较大稳妥起见" / "先汇报一下" 都不是停止理由**——与 `/sprint-dev`「⛔ 统一决策纪律」同源：交互式与无人值守的唯一差别仅在于枚举的结构化门，除此之外两种模式都不得自发停下征询。
> - **★ `run_state` 持久化（compact 后可恢复"我做到哪、下一步是什么"，不依赖上下文记忆）**：baseline `memory/.sprint-autopilot-baseline.json` 增设 `run_state` 段，**每个 Phase 收尾时更新**：
>   ```json
>   "run_state": {
>     "build": "V0.10.1_build1001",          // 本轮 build（未铸造前留空）
>     "current_phase": "3.2-dev",            // 当前 Phase 标识
>     "next_phase": "3.2.1-deploy",          // 下一 Phase（终态时为 "done"）
>     "next_sprint": "003",                  // ★ #1 逐 tick 单 Sprint 游标：Phase 3.2 下一个待跑的 Sprint 号（全部关闭后置 "done"，进部署）；一 tick 跑满/非 Phase 3.2 时可空
>     "phase_completed_at": "2026-07-31T..", // 本 Phase 完成时间（由 baseline_edit.py run-state 自动写，勿手填）
>     "phase_first_entered_at": "2026-07-31T..", // ★ 通用 stuck 检测：当前 current_phase **首次**进入时刻（换 Phase 时重置）
>     "phase_enter_count": 3,                // ★ 通用 stuck 检测：当前 current_phase 被连续进入的次数（换 Phase 时归 1）
>     "phase_summary": "Sprint-002 完成，2 个用例待复测",  // ★ A3：本 Phase ≤20 行结论摘要，主循环只持有它、不持有 Phase 内部往返
>     "pending_actions": ["deploy-watch", "card:#1d", "aiauto-test-trigger"]  // 本 Phase 收尾/下 Phase 入口的必做动作（含通知节点、部署监听、测试触发）
>   }
>   ```
>   - **每轮开始先读 `run_state`**：`next_phase` 非空且非 `"done"` → **直接执行该 Phase**（不询问、不复述已完成内容、不重跑已完成 Phase）；`pending_actions` 非空 → **先把这些必做动作补完**（发漏的通知 + record-card、补漏的部署监听、触发漏挂的测试）**再**进下一 Phase。**★ 逐 tick 单 Sprint 续跑（#1）**：`next_phase=="3.2-dev"` 且 `next_sprint` 非 `"done"` → 本 tick 从 `next_sprint` 号 Sprint 续跑（该 Sprint 之前的已关闭、跳过不重跑，权威仍以各 Sprint 归档/close 记录核对，见 Phase 3.2「执行粒度」）。
>   - **★★ 写盘是硬动作，不是"声明"（每个 Phase 分片末尾**必须**执行下面这一行，漏写即整套断点续跑失效）**：
>     ```bash
>     eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --shell)"   # ★ 必须在本围栏首行：
>     #   shell state 不跨 Bash 调用，漏了它 $TARGET_VERSION 取空 → run-state 报错 rc=1、一字节不写
>     #   → next_phase/next_sprint 恒空 → 每 tick 从头重推 + 中间 tick 误跑收尾门。照抄本模板时勿删。
>     python3 .aidp/scripts/baseline_edit.py --version "$TARGET_VERSION" \
>       run-state "<本 Phase 编号>" "<下一 Phase 编号 或 done>" "<next_sprint 或 done>" \
>       --summary "<本 Phase ≤20 行结论摘要>" --pending "<未完成动作,逗号分隔>"
>     ```
>     ⛔ **不要再用裸 `jq … > tmp && mv` 或内联 python 各写各的**：本脚本内部持 `flock` 并**锁内重读**，与测试链路 `/loop 5m` 的并发写互斥；裸写会把对方刚落的 `ai_report_finalized` 等字段整体覆盖丢失。
>     ⛔ **只在 `invariants` 里描述 `run_state` 而分片不写盘 = 状态机不存在**：`next_phase` 恒空 → tick 中途崩溃后下一 tick 从 Phase 3.0 全量重推；`next_sprint` 恒空 → Stop hook 的"中间 yield-tick 豁免"判据取不到值，会在每个中间 tick 误跑收尾门并白烧熔断额度。
>   - **★★ 通用 stuck 检测（"既不失败也不推进"的兜底熔断 —— 现有熔断全是"特定失败计数"式，都堵不住这一类）**：`dev_fail_streak` / `probe_fail_streak` / `test_loop_missing_streak` 等**都要求先有一次明确失败**才计数；但真实卡死往往**没有失败**——子 Agent 每 tick 回传 partial、某个 Sprint 永远 close 不掉、`pending_actions` 里某项每 tick 都补不完。表现是 `/loop` 岁月静好地空转，**零告警、零熔断、build 永不收口**。故每轮开始读 `run_state` 时先跑本检测：
>     ```bash
>     eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --shell)"   # ★ 围栏首行，取回 $TARGET_VERSION
>     BE="python3 .aidp/scripts/baseline_edit.py"
>     # ⛔ **只读不写**：`phase_enter_count` / `phase_first_entered_at` 的唯一维护者是各 Phase 出口的
>     #    `baseline_edit.py run-state`（它按「换 Phase 或 next_sprint 游标前移」判推进并重置）。
>     #    此处若再 `bump` 一次 = 每 tick 加两次、阈值提前一半到达 → 长版本正常推进中被误判 stuck。
>     CUR_PHASE=$($BE --version "$TARGET_VERSION" get run_state.next_phase --default "?")   # 仅用于告警文案
>     CNT=$($BE --version "$TARGET_VERSION" get run_state.phase_enter_count --default 1)
>     FIRST=$($BE --version "$TARGET_VERSION" get run_state.phase_first_entered_at)
>     to_ts() { date -d "$1" +%s 2>/dev/null || echo 0; }   # epoch 比较，别用字符串（+08:00 与 Z 混排会误判）
>     AGE=$(( $(date +%s) - $(to_ts "${FIRST:-}") ))
>     if [ "$CNT" -ge "${STUCK_PHASE_ENTER_THRESHOLD:-8}" ] && [ "$AGE" -gt "${STUCK_PHASE_AGE_SECONDS:-7200}" ]; then
>       # 熔断条件（次数 + 滞留时长双判据）已在上面成立 → `--freeze-now`：冻结四件套 + #4 一次做完。
>       # ⛔ 判据不是 streak，别塞计数；⛔ 「发 #4」必须由这一行真发出去，写成注释 = 停得住但停不响。
>       python3 .aidp/scripts/autopilot_fail_handle.py --version "$TARGET_VERSION" --freeze-now \
>         --phase "$CUR_PHASE" --reason stuck-phase \
>         --why "Phase $CUR_PHASE 连续进入 $CNT 次、滞留超 $((AGE/60)) 分钟且无推进（既不失败也不前进）"
>       echo "⛔ 通用 stuck 熔断：Phase $CUR_PHASE 连续 $CNT tick 原地打转（首次进入 $FIRST）→ 已冻结并发 #4"
>     fi
>     ```
>     - **判据两条同时满足才熔断**（缺一都会误伤）：① `phase_enter_count ≥ 8`（默认，可用 `STUCK_PHASE_ENTER_THRESHOLD` 覆盖）② `phase_first_entered_at` 距今 **> 2 小时**（`STUCK_PHASE_AGE_SECONDS`，默认 7200）。只看次数会误伤"逐 tick 单 Sprint"这类**正常**的同 Phase 多次进入（`3.2-dev` 本就每 tick 重入，但 `next_sprint` 在推进、耗时也远短于 2 小时）；只看时长会误伤长 Sprint。
>     - **凡"真的推进了"都要重置**：换 `current_phase`、或 `next_sprint` 游标前移、或 `pending_actions` 有项被清掉 → 视为推进，`set run_state.phase_enter_count 1 run_state.phase_first_entered_at @now`。
>     - **解冻**：`freeze_reason=stuck-phase` 属**交接类**（解冻 = 人工）——新部署不会让"原地打转"消失。人工 `--target <V>` / `--reset-baseline` / 清 `needs_human` 后恢复。
>     - 字段写入遵守「冻结字段写入契约」（`needs_human` + `aiauto_frozen_at` + `freeze_reason` + 顶层 `aiauto_blocked_reason` 一次写齐，见 `/sprint-aiauto-test` `phase-0-6.md`）。
>   - **未清空 `pending_actions` 不得宣告本 Phase "已完成" / 进下一 Phase**——这是问题 3「通知只发开头一条」与问题 2「push 后不监听部署」的结构级堵漏：发通知 / 部署监听 / 测试触发都作为 `pending_actions` 被追踪，漏做即卡在本 Phase。
>   - **★ 权威边界（防 run_state 与真实状态漂移）**：`run_state` 是**最佳努力的断点续跑提示**，用于 compact/tick 边界后快速恢复"做到哪、下一步是什么"；但**恢复的最终权威仍是「文件系统产物 + baseline S0–S4 状态机 + baseline 幂等标志」**（`current_build` / `last_deployed_at` / `aiauto_tested_at` / `ai_report_finalized` / `needs_human` 等）——`run_state` 与真实状态不一致时**以真实状态为准重推**（S0–S4 可从 `docs/requirements/` 版本目录 + baseline 确定性重算，报告 finalize 幂等防重复）。故 `run_state` 缺失/过期不阻塞、不误导，只是少一层快速提示。

## IRON-4：入口级仪式不变式（六项保证，路径无关）

> ⛔⛔ **入口级仪式不变式（顶层铁律，与「阶段推进不变式」「推送分类与监听不变式」并列 · 六项保证单一信源）**：凡经 `/sprint-autopilot` 入口且本轮**发生了代码/测试动作**，以下 6 项保证**路径无关**——`full` / `incremental` / `test-only` / 直接增量 / 走 bailout 未进 Phase 3 **一律适用**；**绝不**因任务被判增量/小改/非版本、**绝不**因是否铸 build 或是否跑 Phase 3 仪式而失效（"做什么工作/是否裁剪仪式内部动作"可随任务类型变，"是否执行下列 6 项"恒不变）：
> - **① 不中途向用户征询"继续/提交/推送"**（与顶部「执行开始后绝不停下来问『继续』」不变式同源）；
> - **② 自动 `git add`+`commit`+`push` 到部署分支**（详见 ②细则 + Phase 3.2「授权即入口」分支落地）；
> - **③ 铸 build 号 + 产 AI执行报告**（HTML SPA，经 `emit-report.py`；autopilot 自有产物永不省）；
> - **④ 发里程碑通知**（通知渠道已配置时；`NOTIFY_ENABLED=0` 才豁免，且须打印豁免原因，见 ⑤细则）；
> - **⑤ 委派/自触发 AI 自动化测试产 AI测试报告**（autopilot 只产 AI执行报告；AI测试报告 + 测试通知由第二条 `/loop /sprint-aiauto-test --unattended` 产，缺则按 ④细则自触发/提级告警）；
> - **⑥ 返回前【无条件】跑一次收尾 ceremony 闸**（`autopilot-ceremony-gate.py`，结构级、必打印"应产 vs 实产"逐项清单，见 ⑥细则 + 文末「命令收尾硬门」）。
> - **★ ②细则（auto-push）**：执行 `/sprint-autopilot` 本身 = 对"自动推到本轮解析出的部署分支（`DEV_BRANCH`）"的**显式且持久授权**（等价"提交并推送吧"）、既定职责非 destructive，**不得**因"NEVER commit unless user asks"在任何路径停下二次确认。**唯一免推送**（三者其一）：① 显式 `--skip-deploy` ② `deployment.mode=none`（命令行或 PRD）③ push 失败硬阻塞（走「失败处置」#4，绝不静默吞）；除此之外**只要产生了代码改动就必须 auto commit+push**（`mode=none`/`--skip-deploy` 时只 commit 不 push）。**交互式 `--once` 一致**（同样 auto-push、不回退"commit only when user asks"）。分支/触发细节（`DEV_BRANCH` 解析、`PENDING_MERGE_TO` 合并回部署源、绝不打 tag/不自动 merge master）见 Phase 3.2「授权即入口」。
> - **★ ⑥细则（收尾硬门：无条件 + 结构级 + 必打印，堵"既不产物也不告警"黑洞）**：命令**返回前无条件**跑一次 `python3 .aidp/scripts/autopilot-ceremony-gate.py check --version {V} --build {B} …`（**不埋在"走到才触发"的 Phase 里**）——校 build/HTML报告/通知台账/测试报告归属，缺失即补产、补不齐 `exit 1` 不静默返回；**无论过没过都打印"应产清单 vs 逐项实产核验"**（build号/AI执行报告/AI测试报告/各里程碑通知，缺项标原因 + 补产命令，脚本已内置该表头）。
> - **★ ③细则（"未进流水线"必打印，从 prose 升级为结构级）**：确实无法进入 Phase 2/3（判增量绕过/Phase 1 无变化/版本已交付/停在配置向导）而**不产 build/报告/通知**时，**必须**跑 `python3 .aidp/scripts/autopilot-ceremony-gate.py check --version {V} --no-pipeline-reason "<具体依据>"`（结构级强制打印"⚠️ 本轮未进入开发流水线…判定依据=<原因>" + 应产=无说明，`exit 0`）——堵"既不产物也不告警"黑洞。
> - **★ ④细则（AI测试报告归属 + 双链路缺失要响，运行时打印非只写文档）**：autopilot 只产 AI执行报告；AI测试报告 + 测试通知(#D/#R/#F)归第二条 `/loop 5m /sprint-aiauto-test --unattended`。本版需浏览器实测（`deployment.mode`≠none）却检测不到 `aiauto_test_heartbeat_at` 心跳且本 build 无 `aiauto_delegated_at` 委派证据时——**交互式单跑**：autopilot 必自调用一次 `/sprint-aiauto-test --once --unattended`（P0-3）；**`/loop` 无人值守**：运行时**提级打印**"⚠️ 请并行挂第二条 `/loop 5m /sprint-aiauto-test --unattended`，否则 AI测试报告/测试通知永不产生"（收尾门 3b2「测试链路运行证据」已结构级兜此判据）。
> - **★ ⑤细则（通知未发也要说清原因，禁静默）**：`NOTIFY_ENABLED=0`（`memory/aidp-config.yaml` 的 `notify.enabled=false` 或 `notify.channels` 为空 / `notify.py` 退出码 3）或因绕过框架未到通知节点而一条通知都没发时，**必须**在终端明确打印"本轮为何一条通知都没发"（未配置渠道/全部渠道失败/未进入里程碑节点）+ 恢复指引（配置 `notify` 段，见约定 32）；绝不"配过就以为发了"却静默不发。⚠️ 这是终端打印，不是弹窗——未配置渠道仍属合规降级、不阻塞。
> - ⛔ **Red-Flag 反例（与「把『回复继续我接着建 XXX』当输出结束轮次 = 严重违规」同款）**：在 `/sprint-autopilot` 入口下完成任何代码改动后，输出「要不要我提交并推送 / 你确认我就 push / 要不要继续」这类**征询 = 严重违规**——交互式与无人值守都禁止。
> - **★ 堵"增量名义免除仪式"（与 P0-1 incremental 硬判据同思路）**：执行体对任务类型的判断（新功能/bugfix/优化增量/靶场小改）**只允许影响"某段流程内部做什么工作"，绝不影响"是否 auto-push / 是否铸 build / 是否产报告 / 是否发通知 / 是否跑收尾闸"**。增量绝不能退化成"裸改代码、不铸 build、不发通知、不产报告、还停下问用户"。
> - **★ 边界（诚实，不冒充银弹）**：本不变式 + 收尾门是**结构级兜底**——把"仪式产物 + 自动推送 + 不中途征询"从 Phase 2/3 内部自律上提为入口级强制项并逐项运行时打印状态；但**收窄缝隙 ≠ 完全替代执行体守规**，执行体仍须不"把任务判增量后主动绕过框架"。二者叠加：脚本堵结构洞、执行体守本分。

## IRON-5：推送分类与监听不变式

> ⛔⛔ **推送分类与监听不变式（顶层铁律）**：每次 AIDP 代码 push 前，必须调用 `python3 .aidp/scripts/classify_push.py --root . --version "$VERSION" [--build "$BUILD"] [--base-ref "$BASE_REF"]` 并把完整结果写入当前 build（⛔ 分工别写反：**落盘的是 `classify_push.py`**，它内部调 `classify_commit_change.py` 取分类；后者只有 `--root/--base-ref/--json/paths`，**无 `--version`/`--build`、不落盘**，直接写它 = 分类结果永不进 build、下游读方按 fail-closed 白跑一轮 CICD 监听）。分类为无正式代码变更且无分类错误时，push 仍须成功校验并记录 `cicd_skipped=true`，随后完成本次 push，不触发/监听远端 CICD、不等待部署、不跑就绪探针；分类为正式代码变更、分类结果缺失或分类错误时，才进入「部署触发 → 轮询终态（失败重试 ≤3）→ 就绪探针 → 写 last_deployed_at」。
> - **★ 作用域 = 全命令，不限本流程**（单一信源 = 约定 31.5）：所有 AIDP 命令的 push 点均须执行同一分类与分流，包括 `/sprint-dev`、`/sprint-bugfix`、`/sprint-batch`、`/version` 和用户授权的直接推送。
> - 分类脚本调用失败、JSON 不完整或分类结果无法落盘时必须 fail-closed，按正式代码路径监听；不得用远端流水线状态反推分类。
> - `cicd.provider=none`、未配置 `cicd.pipelines`（或 `cicd_watch.py` 退出码 3：提供方 CLI/凭据不可用）、`manual-script`、`mode=local` 或 `mode=none` 时，分类允许监听但没有可接管的远端流水线，按对应轻量部署分支处理；明确 `cicd_skipped=true` 的 push 不进入任何部署探针。
>
> ★ 按 push 归属**分两条路径、不叠加**（避免主部署被双探针 / 在流水线尚未触发时过早探针误超时）：
> - **【路径 A】主部署 push（由 Phase 3.2.1 完整 CICD 编排接管）**——`cicd-provider` / `git-push`+已配置 `cicd.pipelines` 的**主开发分支推送**，其"查触发/主动触发/轮询/重试≤3 + 就绪探针 + 写 `last_deployed_at`"**全部由 Phase 3.2.1 Step A0–D 编排承担（权威路径）**；Step D 的就绪探针同样调用 `autopilot-deploy-watch.py`（单一实现，`push_probe_fail_streak` 熔断），⛔ 路径 A 不在 Step D 之外再叠加一次探针。
> - **【路径 B】需要独立处理的 push**——分类结果允许监听但未由 Phase 3.2.1 主部署编排接管的 push（如测试期缺陷修复后、独立 `/sprint-dev`·`/sprint-batch`、`/version` 发布期或其它非主部署编排 push）走两个确定性脚本串成完整六步；分类明确为非正式变更的 push 不进入路径 B：
>   **① ③ 流水线监听 + 失败重试（已接入 CICD 时必做）** —— `.aidp/scripts/cicd_watch.py`（平台 = `cicd.provider`，默认 GitHub Actions；差异收在 `cicd_providers.py`）：
>   ```bash
>   eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --shell)"   # ★ 围栏首行，取回 tick 变量
>   python3 .aidp/scripts/cicd_watch.py --commit "$(git rev-parse HEAD)" --env "<dev|test|prod>" \
>     --version "$TARGET_VERSION" --timeout 480   # 退出码 0=流水线成功或未终态(verdict=running) · 1=需写动作 · 2=需人工 · 3=未接入 / 提供方 CLI·凭据不可用 / 未配置流水线
>   ```
>   按其 stdout JSON 的 `next_action` 分流：`probe` → 进下面 ④⑤⑥；`poll`（`verdict=running`，单次调用时限内未终态）→ 让位下 tick 续 poll；`verdict=unreachable` / rc=3 CLI 类 → 按 streak 记账（`cicd-unreachable` / `cicd-cli-unavailable`，连续 3 次冻结，环境类自动复探）；`trigger`/`retry` → **② 由命令端显式调写模式**（见下）；`abort` → 交人工（重试用尽 / 超时 / 锚定运行消失）。`cicd_retry_count` 经 `baseline_edit.py` 累加、**上限 `cicd.max_retries`（默认 3）**。
>   - **`trigger`（首次主动触发，构建分支当前 HEAD）**：执行输出里的 `trigger_cmd`，即 `cicd_watch.py --mode trigger --env <env> [--ref <branch>]`（流水线取 `memory/aidp-config.yaml` 的 `cicd.pipelines.<env>`）→ `next_action=poll` 直接 `--mode poll --run-id <输出的 run_id>`；`next_action=detect` 先跑 `--mode detect --commit <sha> --env <env>` 锁定新 run id 再 poll。
>   - **`retry`（重跑上次失败的运行）**：执行输出里的 `retry_cmd`，即 `cicd_watch.py --mode retry --env <env> --run-id <失败运行 id>` → 按其 `next_action` 以输出的 `run_id` poll（或按 commit 再 detect）继续监听。重试针对的是**失败运行的原 commit**，不主动取分支上更新的 HEAD——"重跑"与"部署一份从未被确认的新代码"两件事不混用。
>   - **写动作闸门 = `cicd.auto_trigger`（默认 true）**：为 true 时无人值守直接执行、无需人工确认；为 false 时**不执行任何写动作** → 按「冻结字段写入契约」置 `needs_human=true` + `aiauto_frozen_at=@now` + `freeze_reason=cicd-auto-trigger-off`、发 #4 后冻结，**绝不静默跳过监听**。
>   ⛔ **场景边界**：流水线配了 push 自动触发 → 正常路径是脚本 detect 直接命中 `probe`/`poll`，出现 `trigger` 说明自动触发没起来、属异常，须在执行写动作的同时打印告警；流水线仅支持手动/API 触发时，`trigger` 是常规路径、按 `cicd.auto_trigger` 执行。
>
>   **④⑤⑥ 冷启动等待 + 就绪探针 + 写 `last_deployed_at`** —— `.aidp/scripts/autopilot-deploy-watch.py`：
>   ```bash
>   eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --shell)"   # ★ 围栏首行，取回 tick 变量
>   python3 .aidp/scripts/autopilot-deploy-watch.py \
>     --health-url "<后端 health 端点，如 http://host:8080/actuator/health>" \
>     [--auth-url "<登录后自身鉴权取数接口>" --auth-header "Cookie: <会话>"] \
>     --cold-start-seconds 55 --timeout 300 --max-seconds 480 --version "$TARGET_VERSION"
>   RC=$?; BE="python3 .aidp/scripts/baseline_edit.py"; V="$TARGET_VERSION"
>   # ⛔ 散文的「递增 +1」不是写入：全仓只有归零点、没有递增方 ⇒ 阈值永远达不到、
>   #    这道熔断门一次也不会触发（表现为每 tick 重探 300s、零通知）。
>   case "$RC" in
>     0) $BE --version "$V" del push_probe_fail_streak || true ;;
>     2) python3 .aidp/scripts/autopilot_fail_handle.py --version "$V" \
>          --phase 3.2.1-deploy-probe --reason probe-timeout \
>          --streak-key push_probe_fail_streak --threshold 3 \
>          --why "就绪探针超时，环境疑似未起来（⛔ 不重跑流水线）" ;;
>     4) echo "⏳ 单次调用时限内未探完 → 下 tick 续探，⛔ 不计 streak" ;;
>     5) echo "⚠️ 环境已就绪但写 last_deployed_at 失败 → 原地重试，⛔ 不计 streak、不冻结" ;;
>   esac
>   ```
>   脚本内置：**先 health 判 UP（⛔ 不用登录页可达性判就绪，登录页常是第三方/SSO）**、冷启动窗口内 502/503/连接拒绝属正常不判失败、`--auth-url` 给出时要求「鉴权接口连续 2 次取到非空数据」、`exit 0` 就绪并写 `versions.{version}.last_deployed_at` 放行测试链路。
>   - **★ `exit 2`（就绪探针超时）熔断落地（autopilot 自有字段，勿复用测试链路 `probe_fail_streak`）**：`autopilot_fail_handle.py` 递增 baseline `versions.{V}.push_probe_fail_streak +1` → `< 3` 只记账后退本 tick，`≥ 3` 按「冻结字段写入契约」写齐 `versions.{V}.needs_human=true` + `aiauto_frozen_at=@now` + `freeze_reason=probe-timeout` + 顶层 `aiauto_blocked_reason`、发最后一张 #4 后冻结本版（后续 tick 跳过；⛔ 别再用私有字段名 `push_probe_frozen_at`——解冻方只认 `aiauto_frozen_at`），**⛔ 不重跑流水线**；`exit 0` 清零 streak。**★ `exit 5`（已就绪、但写 `last_deployed_at` 失败）走另一条**：⛔ **不得计入 `push_probe_fail_streak`**——`probe-timeout` 的解冻证据正是 `last_deployed_at`，而这一轮失败的恰恰是写它，按超时熔断等于把恢复路径一起堵死。正确处置：发一次 #4 说明「环境已就绪但 baseline 写入失败」、原地重试写入，本 tick 不冻结、不重跑流水线。
> - **登记 `pending_actions`**：路径 B 的 push 后把 `cicd-watch`（已接入 CICD 时）与 `deploy-watch` 放进 `run_state.pending_actions`，**各自对应脚本 `exit 0` 才移除**——未移除即本 Phase 未完成（与阶段推进不变式 + 收尾门 3k 义务清算联动，堵住"推了就当完事、测试链路空转"）；路径 A 由 Step D 完成即视为已就绪、不进 `pending_actions`。
> - **同不变式下传各子命令**：`/sprint-dev` / `/sprint-bugfix` / `/sprint-batch` 在自身二级推送点（含 bugfix 修复后推送）、`/version` 在发布期推送点，同样先分类再按正式代码结果进入监听路径（见各自命令/分片的「推送分类与监听」段），autopilot 委派它们与它们独立跑时行为一致。
> - **★ 刷新 `last_autopilot_head`（配合 retest-cap 人工修复检测）**：本流程内**任何一次** autopilot 自身 push 确认完成后（路径 A/B 均含），把顶层 `last_autopilot_head` 刷新为当前 `git rev-parse HEAD`——记录"autopilot 自己推进到的最后一个 commit"，供「测试失败自动修复复测闭环」step 3bis 用双重不等区分人工新提交与 autopilot 自推、防 `retest-cap` 冻结版本被误解冻（见该段 + baseline schema `last_autopilot_head`）。

## IRON-6：上下文管理策略（防单 tick 破 1M）

> ⛔⛔ **上下文管理策略（顶层铁律 —— 防单 tick 上下文破 1M）**：完整链路【版本规划 → 全量开发 → AI 测试】若挤在同一上下文会累积到破 1M。⚠️ **#2 覆盖两条分支**：`phase-3-5.md` 的 step 1（逐 tick 单 Sprint）**与 step 2 的 `/sprint-batch` 循环体**（后者的执行形态写在 `/sprint-batch` Step 3、与 `--skip-context-check` 无关）。故 `LOOP_UNATTENDED=1` 默认四管齐下压上下文——**① 分 tick（`#1`）**：全量开发默认**逐 tick 单 Sprint 推进**（每 tick 一个 Sprint、`run_state.next_sprint` 游标续跑），把「1 个大上下文」拆成「N 个小上下文」，`--batch-one-tick` opt-out（见 Phase 3.2「执行粒度」）。**⛔⛔ 硬前置：`#1` 仅在 `HAS_WAKE_SOURCE=1`（`/loop` 上下文 或 `--no-loop` cron，Phase 0.0.0 派生）时可用**——`UNATTENDED_YIELD` 是"托付给下一 tick"，**没有受托人的 yield 不是省上下文、是停摆**（裸 `--unattended` / 交互式单次即属此类：`run_state` 停在半路、剩余 Sprint 永不执行）。无唤醒源时**只用 ②③④ 压上下文、本轮内跑满全部 Sprint**，绝不拿 yield 换上下文；根因见 `rationale.md`；**② 子 Agent 隔离（`#2`）**：最重的 `/version` 规划、每个单 Sprint 开发**优先委派独立子 Agent 执行、只回传 compact 结构化结果**，生成/SKILL/TDD 往返留在子 Agent 上下文里随其结束丢弃，autopilot 主上下文只保留 compact 结果 + 里程碑通知编排（见 Phase 3.1 step 2 + Phase 3.2 step 1）。**③ compact 读取（`#4`）**：留在主上下文内联跑的步骤（Phase 0 配置 / baseline 检查 / 部署监控）**一律走脚本 compact JSON 输出或 jq 一行 / `Read` 带 `offset+limit`**，**⛔ 绝不把已生成的研发需求/详细设计/执行计划/报告等大产物整篇 `Read` 进主上下文**——需要其内容的判定尽量下沉到子 Agent（②）或用脚本抽取，主上下文只留结论。**④ Phase 执行承载 + 结论摘要（A3）**：无人值守下，**有重执行的 Phase 2/3 的具体步骤由子 Agent `Read` 对应分片（`phase-2.md` / `phase-3-*.md`）并执行**，主 autopilot 只按 `run_state` 状态机决定下一 Phase + 持有**每 Phase ≤20 行的结论摘要**（`run_state.phase_summary`，如 `{phase, verdict, key_counts, artifacts[], next}`），**⛔ 不在主上下文保留 Phase 内部的执行往返 / 逐步日志**。★ **边界（诚实，不冒充）**：**Phase 0（前置配置收集）+ Phase 1（PRD 变化检测轻量 baseline 读）留主循环**——Phase 0 含交互式配置门（受「委派安全铁律」不可委派）、Phase 1 本就轻，故 A3 的"子 Agent 承载"只落在**重执行的 Phase 2/3**，Phase 0/1 靠 ③ compact 读取控量。**四者都【仅无人值守生效】+ 都有内联回退（子 Agent 不可用 / 交互式需弹窗时内联跑，行为与产物不变、零回退风险）**。
>
## IRON-7：委派安全铁律

> **⛔⛔ 委派安全铁律（子 Agent 不能 `AskUserQuestion`，故【只委派零交互的纯执行段】）**：`#2` 能安全委派，前提是**一切需用户配置/确认的点都不在被委派段内**——它们全部落在 **① Phase 0（前置配置，在主 autopilot 上下文跑、【绝不委派】）一次性收集**（chrome-devtools-mcp 安装预检 0.5.5/0.7 · 里程碑通知渠道检查 0.0 Step2 · 决策预声明 0.5/0.6 等），或 **② 一次性交互式 setup**（挂 `/loop` 前先跑一次 `/sprint-autopilot --once` 或 `/version`，写 baseline/config，见命令语法前置铁律）。加上 `LOOP_UNATTENDED=1` 本身的**「主流程 Phase 2/3 零 `AskUserQuestion` 铁律」**（见 0.7「零交互覆盖清单」+ Phase 0.3.4 各门：缺失即**非阻塞降级**——`notify` 渠道未配置则 `NOTIFY_ENABLED=0` 静默、CICD 提供方 CLI·凭据不可用则无远端流水线可监听、chrome-mcp 缺则占位交测试链路——**一律降级、绝不弹窗**）。**故被委派的 Phase 3.1/3.2 执行段在无人值守下天然无任何交互点**，子 Agent 只读 baseline/config/文件即可跑完、永不需要问用户。**⛔ 反过来的铁律：任何仍可能触发 `AskUserQuestion` 的动作【绝不允许委派子 Agent】**——只要某步在当前上下文还会弹窗（即 `LOOP_UNATTENDED=0` 交互式），就必须在主上下文内联跑（`#2` 已限定"交互式不委派"）；新增委派点前必须确认该段在无人值守下已被 Phase 0 前置/降级覆盖、零残留交互。**交互式单次调用**不分 tick、不委派（用户在场、需弹窗、也无 `/loop` tick 边界），如需省上下文请挂 `/loop` 无人值守跑。

## IRON-8：委派职责矩阵

> **⛔⛔ 委派职责矩阵（IRON-8 — 无人值守下【必须子 Agent 执行】，非"优先/建议"）**：以下措辞由"优先委派"升级为**硬性**——`LOOP_UNATTENDED=1` 且该段零交互（受上「委派安全铁律」约束）时，**必须**委派独立子 Agent、**不得**留在主循环内联跑（子 Agent 不可用才回退内联，回退须终端打印「⚠️ 子 Agent 不可用，降级内联」而非静默）：
>
> | 必须子 Agent 执行的段 | 委派点 | 回传 compact schema（B3） |
> |------|------|------|
> | `/version` 规划全过程（+ version-auditor 终审） | 规划 = **Phase 3.1**（分片 `phase-3-3.md`）；终审 = **Phase 3.3**（分片 `phase-3-8.md`）| `{version,planning_done,artifacts[],sprint_count,auditor_verdict,key_counts{req,design,api,db,cases},fail_reason?}` |
> | 每个 Sprint 的开发（`/sprint-dev`+TDD+bugfix+close） | **Phase 3.2**（分片 `phase-3-5.md` + `phase-3-5b.md`）| `{sprint,closed,files_changed,static_pass_rate,bugfix_rounds,blocking_issue?}` |
> | `auto-test-runner` 每个测试模块 | 测试链路 `/sprint-aiauto-test` | `{module,total,pass,fail,block,evidence_dir,defects[]}` |
> | 报告数据构造与渲染校验（`emit-report.py` 前的 payload 组装 + `verify-reports` 冒烟） | Phase 3.4 / 测试链路收尾 | `{build,kind,schema_ok,rendered_ok,data_file}` |
> | **★ 上游调研（P1-4）**：读 PDF 接口文档 / 读他方源码参考实现 / 查配置中心（本次实跑 38 页 PDF+550 行 Java 全在主上下文） | `/version` 设计期 / `/sprint-dev` | `{契约摘要, 差距清单[], 关键决策N条}`——**⛔ 不回传 PDF/源码原文** |
> | **★ 文档级联写作（P1-4）**：约定 22 四层级联的增量写作（研发需求→详细设计→执行计划→自测，本次约 700 行 md 全在主上下文） | `/version` 级联期 | `{已产出文件清单[], 关键决策≤3条}`——子 Agent 写盘、主上下文不载正文 |
> | **★ 报告数据组装（P1-4）**：扫 `results/*.json` 汇总成 build data（**已有确定性脚本 `gen_report.py`/`emit-report.py` 可做、无需模型拼 JSON**，与 BUG-4 同源） | Phase 3.4 / 测试链路 | 直接调脚本产出，主循环只收 `{data_file, ok}` |
>
> **★ B2 主循环只做四件事**（除此之外的重活一律下沉子 Agent）：① 读写 baseline / `run_state` ② 按状态机决定下一 Phase ③ 派发子 Agent ④ 发里程碑通知。**⛔ 主循环禁止直接驱动浏览器、禁止直接构造报告 payload 大对象、禁止把整篇 SKILL.md / 生成往返留在自身上下文**——这些都属"必须子 Agent 执行"。
> **★ B3 回传格式约束**：被委派子 Agent **只回传上表 compact 结构化结果（建议 JSON）**，**⛔ 禁止回传大段日志 / 文件整篇内容 / SKILL 往返**——主循环要文件内容时按路径按需 `Read`（`offset+limit`）或再派子 Agent，不让子 Agent 把大产物灌回主上下文（否则委派省下的上下文又被回传吐回来）。

---

## ★ 子 Agent 派发失败的分层重试与降级（P0-3 — 委派前置，先于命令「失败处置」熔断）

委派子 Agent（#2：`/version` 规划 / 单 Sprint 开发 / `auto-test-runner` 测试模块 / `version-auditor` 终审等）执行时，子 Agent **本身**可能被**服务端瞬时错误**（`API Error 529 Overloaded` / `503` / 网关超时）打断——这**不同于**"框架脚本调用失败 / 子 Agent 回传不合契约 / 确定性业务失败"。**⛔ 绝不把瞬时 API 错误等同于确定性失败、直接降级内联**（内联是上下文代价最高的一条路，正是单 tick 破 1M 的推手之一）。遇子 Agent 失败一律先走本节 C1–C3 分层，**穷尽 C1/C2 仍失败**才进命令「失败处置」熔断：

- **C1 先按失败类型分流（判据确定化）**：
  - **瞬时服务端错误**（`529` / `Overloaded` / `overloaded_error` / `503` / 网关 5xx / 连接中断 / 单次派发超时）→ **自动重试、指数退避（★ 跨 tick 退避，不在单 tick 内前台 `sleep`）**，**不累加 `dev_fail_streak`、不发 #4**。仅退避轮次用满仍失败才转 C2。
    - ⛔ **禁止单 tick 内前台 sleep 等退避**：部分运行环境直接禁前台 `sleep`；即便不禁，`30s+60s+120s` 也会**白吃掉 3.5 分钟 tick**（10m tick 里三分之一空转，5m tick 更离谱），且 sleep 期间 tick 可能已被判超时。
    - **落地 = 记「下次可重试时刻」，未到点直接让位本 tick**：
      ```bash
      eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --shell)"   # ★ 围栏首行，取回 tick 变量
      BE="python3 .aidp/scripts/baseline_edit.py"
      # ① 派发前先看闸门：未到点 → 本 tick 不重试、直接让位（不算失败、不记 streak）
      RETRY_AT=$($BE --version "$TARGET_VERSION" get subagent_retry_at)
      to_ts() { date -d "$1" +%s 2>/dev/null || echo 0; }
      if [ -n "$RETRY_AT" ] && [ "$(date +%s)" -lt "$(to_ts "$RETRY_AT")" ]; then
        echo "⏳ 子 Agent 退避中（下次可重试 $RETRY_AT）→ 让位本 tick，下次 /loop 唤起再派"
        exit 0
      fi
      # ② 派发命中瞬时错误 → 按退避轮次算下次可重试时刻，写盘后让位本 tick
      R=$($BE --version "$TARGET_VERSION" bump subagent_retry_round)     # 1→2→3
      case "$R" in 1) D=30;; 2) D=60;; *) D=120;; esac
      $BE --version "$TARGET_VERSION" set subagent_retry_at "$(date -d "+${D} seconds" -Iseconds)"
      echo "⏳ 子 Agent 瞬时错误（第 $R 次）→ 退避 ${D}s，本 tick 让位（不记 dev_fail_streak、不发 #4）"
      exit 0
      # ③ 派发成功 → 清闸门：$BE --version "$TARGET_VERSION" del subagent_retry_at subagent_retry_round
      # ④ subagent_retry_round > 3（退避轮次用满）→ 清闸门后转 C2 换更小粒度
      ```
    - **退避时长 < tick 间隔时**（如 30s vs 10m tick）本就等价"下个 tick 再试"，写 `subagent_retry_at` 只为让**同 tick 内的后续派发点**也遵守闸门；退避轮次与时长仅作上界，实际重试时刻由 `/loop` 节奏决定。抖动由派发序号派生，**⛔ 脚本内不得用被禁的时间/随机 API**。
  - **确定性失败**（框架脚本非零退出 / 子 Agent 回传不合 compact 契约 / 业务逻辑失败 / `version-auditor` 反复 Critical）→ **不重试**，直接进「失败处置」记 `dev_fail_streak`（同现状）。
- **★ 嵌套子 Agent 的可观测性（委派方必须定义【产物级】完成判据，不得只依赖通知）**：委派可以嵌套
  （实测已达三层：autopilot → 规划子 Agent → 2 个 auditor），而**层数越深，完成通知越不可靠** ——
  实测中后台那个 auditor 的完成通知**从未回来**，只能靠轮询产物文件才知道它其实早就跑完了。
  故铁律：**每次委派都必须同时定义"怎样算完成"的产物级判据**（该落哪个文件 / 哪个 baseline 字段
  置真），并以**该判据**作为推进依据；通知只是加速信号、**不是完成的证据**。
  - **★ 浏览器 daemon 是单实例资源，实测期必须独占。** `chrome-devtools` CLI daemon 全机一个，
    编排器在 `/sprint-aiauto-test` 运行期间**若同时派发别的会用浏览器的执行体**，三方会互相打满
    （实测：三并行执行体把单实例 daemon 打满、中途被迫重启一次，那一轮每用例均摊 197s）。
    故：**实测期不并发派发任何会占用浏览器的子 Agent**；开发链路与测试链路的子 Agent
    **不得在同一时间窗内都触碰浏览器**。二者本就分属两条 `/loop`，错开即可，无需新机制。
  - **★ 但"必须轮询产物"不等于"定间隔死等"——轮询节奏必须指数退避、且单轮上限随任务量走。**
    只说了要轮询、没说怎么轮，执行体就会挑个固定小间隔（实测有挑 20s 的），再配一个短的
    单轮上限（9 分钟）——而单 Sprint 实测可长达 61 分钟，于是**每个 Sprint 至少七轮空转日志**，
    且每次"本轮到点仍未提交"都要再起一轮，**最坏每 Sprint 多等一个轮次时长**。
    节奏定则：**间隔 20s → 40s → 80s → 160s，上限 5 min**；**单轮总时长按被委派任务的
    典型耗时取（Sprint 级 ≥ 60 min），⛔ 不用固定 9 分钟**。⛔ 同受上面「禁止单 tick 内
    前台 sleep」约束：`/loop` 场景下退避跨 tick 兑现，不在 tick 内前台 sleep 等。⛔ 绝不允许写出
  "等子 Agent 通知回来再继续"这种只有单一依赖的等待——通知不来就永久挂起，且挂起时毫无告警
  （与「阶段完成 = 产物已落盘可校验」同一条原则的另一面）。**能不嵌套就不嵌套**：三层已是实测上限，
  再深应改为同层并列委派。
- **C2 降级阶梯（显式顺序，执行体不得跳级直奔最贵档）**：① **同粒度子 Agent 重试**（C1 退避）→ ② **换更小粒度子 Agent**（按自然边界再拆：`/version` 拆成 requirements/design/plan 分段委派、测试拆成按模块委派、单 Sprint 拆成前/后端分派，各自上下文更小、更易被服务端接纳）→ ③ **主循环内联执行（最后手段）**。**⛔ 绝不因一次 529 就跳到 ③**。
- **C3 内联降级的上下文预算护栏（堵"一口气把整轮塞进主上下文"）**：真要降到 ③ 内联前，**先估算主循环剩余上下文预算**（粗估被委派段的典型注入量 vs 当前已用）——**不足以容纳整段** → **⛔ 不得一口气内联**，改为**分批内联 + 中途落盘 + 下个 tick 续跑**（按 C2② 自然边界切片，每片内联跑完即把结论/产物落 baseline `run_state` 或落盘，`UNATTENDED_YIELD` 退本 tick，下次 `/loop` 从落盘游标续跑），行为等价、只分摊上下文。**⛔ 同受"无受托人不得 yield"约束**：`HAS_WAKE_SOURCE=0` 时本条的 yield 同样禁用——改为**继续分批内联、每批落盘后在本轮内接着跑下一批**（落盘照做，它同时是崩溃续跑的保险）；确实撑不住再按失败处置显式告警交人，**绝不 yield 成停摆**。**⛔ 绝不在预算不足时硬塞整轮致触发 compact / 破 1M**。
- **C4 降级留痕（可追溯）**：任何一次降级（重试次数 / 是否换小粒度 / 是否内联 / 是否分批续跑）**必须写进本轮报告**（AI执行报告 `incidents[]` 或「遗留风险」）**+ 落 baseline** `versions.{V}.builds[].exec_path`（取值 `subagent` / `subagent→split` / `inline` / `inline-batched`）。〔`auto-test-runner` 侧 env-facts 已含 `executionPath`（字段集**判据 = 其 `assets/env-facts-schema.json` 里配了 `XSource` 的全部字段**，⛔ 别在此写死条数——字段会增，写死必腐化）——autopilot 的 `exec_path` 与之**取值域对齐**即可，不必再各留一份。〕

> **与「委派安全铁律」的关系**：本节只处理**已被合法委派的零交互执行段**遇瞬时/确定性失败的分层；哪些段可委派仍受顶层「委派安全铁律」约束（交互式段不委派）。**与下方「失败处置」的关系**：本节是委派场景的**前置分流**，瞬时错误在此消化、不进熔断；只有确定性失败或 C1/C2 穷尽才落到「失败处置」的 `dev_fail_streak` 熔断。

