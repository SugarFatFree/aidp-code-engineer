<!-- flowvar-check: allow PASS_RATE 本轮通过率，由上方 gen_report 聚合后就地代入 -->
<!-- 二次切分 · phase-3 片5/6：覆盖 3.7 finalize AI执行报告+发#3-->
# /sprint-aiauto-test · 执行分片 分片 [5/6]（3.7 finalize AI执行报告+发#3）

> ⚠️ **权威性**：以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤 / 硬门。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-aiauto-test/phase-3-5.md`。理据见同目录 `rationale.md`。

### 3.7 ★ finalize AI执行报告 + 发 #3 里程碑通知（#F 之后 · 本 build 收尾 · R-4）

> **本步是 sprint-autopilot 子流程 R 的 R-4「收尾」在测试链路侧的落地**：autopilot 委派前只产了 AI执行报告**骨架**（data 计划态 + 注册两页 + `testSummary` 占位），把「用真实测试结论 finalize data 结果态 + 发报告本体 + 发 #3」解耦到本步——确保 #3 在 **#F 之后**发、且携带**真实浏览器测试结论**。整个 build 的期望最终顺序：实时回写 data steps → 部署 → 浏览器测试 → AI测试报告 + #F → **本步 finalize data 结果态 + #3（末尾，带真实结论）**。

**触发前置**（都满足才执行；任一不满足整步跳过）：
1. `REPORT_ENABLED=1`（autopilot 驱动，有 `current_build`）—— standalone 直接调用无 AI执行报告，不 finalize；
2. Phase 3.5 判定**收敛** `CONVERGED=1`（#F 已发）—— 未收敛说明本 build 还在「修复→重测」循环中，本步**不发** #3（等收敛轮再发，避免 #3 带未收敛的中间结论）；
3. AI执行报告骨架存在（`docs/reports/{V}/AI执行报告/data/{BUILD}.js` 在 + 已注册 index.html/plan.html，autopilot R-3 已产）—— 不在则 2.5.1 早已自愈交接补建，正常到此必在。

**Step 1 — finalize 执行数据 = 调 `emit-report.py --kind exec --patch`（**必须经它以写 `report_deliveries.exec_report` 台账，否则本 build 收尾钢门交付检查会误判缺失**）**：只把**变化字段**写入 `docs/reports/{V}/AI执行报告/.build-input-${BUILD}.json`（`.` 前缀隐藏 + gitignore + emit-report 用完自动删），`--patch` 对现有 `data/${BUILD}.js` 顶层浅合并，autopilot 写的 dev/部署 steps、features 原样保留：
- `testSummary` ← **从同 build 的 AI测试报告 summary 派生（`gen_report.py --json` 的 `counts`，⛔ 不手填）**：`{ total, pass, fail, block, skip, na, passRate:<0~1，分母 = total−na>, coverage:<有则填/无则 null>, browserTested:true }`（去骨架 `pendingBrowserTest`；**不写 `reportLink`**，链接由 `app.js` 运行时推导）。与 3.3b 冻结收口 ① 同一口径（后者另加 `unconverged:true`）。**★ `passRate`/`coverage` 单位 = 0~1 小数：写 `100.0` 或 `"6/6"`/`"100%"` 将被 `emit-report.py` 拒绝写盘（exit 3）**；
- `overview.testPassRate` ← 同一 passRate；`result` ← success|partial|failed；`steps` ← 完整 steps 数组中「AI 自动化测试」一步改 `actualStatus:"done"` + 耗时（数组是顶层字段，须整体传入）；`defects`/`incidents` ← 追加本轮缺陷/运行时错误后的完整数组。
- 再调（R-4 收尾）：
  ```bash
  eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"   # 取回 BUILD/NOTIFY_ENABLED（跨分片不持久）
  mkdir -p memory/.aidp
  python3 {{AIDP_HOME}}/scripts/emit-report.py --kind exec --patch --version "$TARGET_VERSION" --build "${BUILD}" \
    --data "docs/reports/${TARGET_VERSION}/AI执行报告/.build-input-${BUILD}.json" --baseline memory/.sprint-autopilot-baseline.json --json > "memory/{{AIDP_HOME}}/emit-exec-${BUILD}.json"
  AI_REPORT_URL=$(jq -r '.access_url' "memory/{{AIDP_HOME}}/emit-exec-${BUILD}.json")   # 仓库相对路径（带 #/build/<BUILD> hash）
  ```
  脚本自动：写结果态 data + 注册两页（报告只落本地 `docs/reports/`）→ 回写 baseline `report_deliveries.exec_report`；返回的 `access_url` 为仓库相对路径（带 `#/build` hash），#3 通知直接附该路径。**⛔ 不手工写 data / 注册**。

> ⛔ **本段 bash 一律用真实变量 `$TARGET_VERSION` / `$BUILD`，绝不写字面 `{V}`/`{BUILD}` 占位符**：
> 否则 ① 门指向不存在的路径恒 FAIL；② `bump`/`set` 会把 streak 与冻结字段**记进一个字面名为 `{V}` 的假版本键**，
> 真实版本的熔断永不触发。

**Step 1.5 — ★ 最终收尾钢门（`--stage final` · 发 #3 之前必过 · 本 build 唯一权威仪式门）**：此刻 exec + test 两份报告都已 finalize 落盘（交付台账 `report_deliveries.{exec_report,test_report}` 均已由 emit-report 写入），跑**全量校验**——执行报告 SPA + 测试报告 SPA + **两份交付台账** + 无 markdown + 通知台账：
   ```bash
   eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
   GATE={{AIDP_HOME}}/scripts/autopilot-ceremony-gate.py
   BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"   # ⚠️ 必须定义在 if 之外：通过分支也要用它清 streak
   if [ -f "$GATE" ]; then
     # ⛔ **必传 `--expect-cards`（本门自称"本 build 唯一权威仪式门"，就必须真的校通知台账）**：
     #   实测事故：本门不传该 flag → 落进退化分支，而退化判据当时把"规划期无 build 的
     #   #0/#1/#1b"也算进本 build，**只要跑过规划就恒真** → 一整轮测试期通知零推送照样 PASS。
     #   更糟的是 autopilot 侧 `phase-3-9.md` 明确写着「测试链路通知 #D/#R/#F/#G/#3 本门不期望，
     #   归其 Phase 3.7 final 门校」——**两条链路各自把责任推给对方，而被指定的这一方并没有真校**。
     #   期望集 = 测试链路三条**必发**通知 #D/#R/#F（⛔ 漏 #R 会让它落进校验真空：autopilot 侧
     #   明说不校它、本门又不期望它）。#3 由 build 关闭方发、在本门之后（脚本对 final 阶段已自动豁免）；
     #   #G 是条件通知，两侧均不无条件期望。
     python3 "$GATE" check --version "$TARGET_VERSION" --build "$BUILD" \
       --stage final --will-browser-test 1 --notify "${NOTIFY_ENABLED:-1}" \
       --expect-cards "#D,#R,#F" \
       --baseline memory/.sprint-autopilot-baseline.json || FINAL_GATE_BAD="最终仪式门未过（ceremony-gate --stage final）"
   else
     # ★ B4 兜底：gate 脚本缺失 → 内联校验 exec+test SPA + 两份交付台账在位，绝不静默 exit 1 阻死 #3/收尾
     # ⛔ 台账在**顶层** `report_deliveries[{build}]`，既不在 `versions.{V}` 下、也少不了 build 那一层。
     #    写成 `.versions."{V}".report_deliveries.exec_report` 会恒取空 → 恒判"交付台账缺失" →
     #    bump report_gate_fail_streak → 3 tick 后按 handoff-exhausted 冻结。正确写法见姊妹分片
     #    `sprint-autopilot/phase-3-9.md` 同名兜底段。
     EXEC_D=$(jq -r ".report_deliveries.\"${BUILD}\".exec_report // empty" memory/.sprint-autopilot-baseline.json 2>/dev/null)
     TEST_D=$(jq -r ".report_deliveries.\"${BUILD}\".test_report // empty" memory/.sprint-autopilot-baseline.json 2>/dev/null)
     if [ -f "docs/reports/${TARGET_VERSION}/AI执行报告/index.html" ] && [ -f "docs/reports/${TARGET_VERSION}/AI测试报告/index.html" ] && [ -n "$EXEC_D" ] && [ -n "$TEST_D" ]; then
       echo "⚠️ autopilot-ceremony-gate.py 缺失 → 内联兜底 final 校验通过（exec+test SPA + 两份交付台账在位）；建议重跑 aidp-code-engineer upgrade 补回 gate 脚本"
     else
       FINAL_GATE_BAD="最终仪式门未过（内联兜底：SPA / 交付台账缺失）"
     fi
   fi
   # ── 统一处置（⛔ 绝不裸 exit 1）──
   #   此刻 `aiauto_tested_at` 已写、`builds[].status` 已是 tested、未收敛 streak 已清零 →
   #   裸退后下 tick 直接命中去重门 exit 0，本 build **永远不会被重新处理**；而 autopilot 的
   #   准发布 0b 门只校 `aiauto_tested_at` + `unconverged_streak`、**不校 finalize**，会照常归档。
   #   净结果：#3 永不发、报告永远停在骨架、零告警，版本却被当成"已测收敛并归档"——
   #   比"每 tick 重撞"更隐蔽的一种永久静默死。
   if [ -n "$FINAL_GATE_BAD" ]; then
     # ⛔ **不能复用 report_gate_fail_streak**：它被前三道门（3.2.5 截图 / 3.2.6 step5 /
     #    5bis 骨架钢门）共用，且那三道**通过即 `del` 清零**。能走到本门的 tick 必然已过前三道
     #    → 三次清零都已执行 → 本处 bump 永远返回 1 → `[ "$N" -ge 3 ]` **恒假**、永不冻结，
     #    每 5 分钟从 Phase 0 重跑整轮浏览器实测。故本门用独立计数器。
     # 记账 → 判阈 → 冻结 → #4 一次做完（未达阈只记账不发通知；无唤醒源时脚本当场按达阈处置）。
     # ⛔ reason 不写 handoff-exhausted（人工专属）：真因 = 报告交付缺失，与 deploy-unreachable 同域、可自动复探。
     python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --command aiauto-test --version "$TARGET_VERSION" --build "${BUILD:-}" \
       --phase 3.7-final-gate --reason deploy-unreachable \
       --streak-key final_gate_fail_streak --threshold "${REPORT_GATE_FREEZE_THRESHOLD:-3}" \
       --why "最终仪式门未过（报告交付缺失）：$FINAL_GATE_BAD；补齐（emit-report.py 重跑）后复跑，禁止发 #3/收尾"
     exit 0   # ★ 已记账 + 已告警，让位本 tick
   fi
   $BE --version "$TARGET_VERSION" del final_gate_fail_streak || true   # 全通过 → 清零
   ```
   **这是浏览器路径的唯一 `final` 门**（autopilot Phase 3.4 对浏览器路径只跑 `skeleton`，把交付判定权交到此处，避免"要求尚未产生的交付台账"死结）；未过不发 #3、不收尾。

**Step 2 — 发里程碑通知 #3（AI执行报告里程碑，绿色 header）**：`python3 {{AIDP_HOME}}/scripts/notify.py --auto --node "#3" --header-color green --title … --section … --link-text "查看完整报告" --link-url "$AI_REPORT_URL"`（退出码 3 = 未配置渠道 → 静默跳过；1 = 全部渠道失败 → WARN 不阻塞），正文按 sprint-autopilot 0.1bis「#3 AI执行报告通知完整模板」填充——「测试结论」段填**本 build 真实浏览器测试**（`总数 $TOTAL / 通过 $PASS / 失败 $FAIL / 阻塞 $BLOCK / 忽略 $SKIP / 不适用 $THIS_ROUND_NA / 通过率 N%`（**通过率分母 = 总数−不适用**，与 SKILL `gen_report.py` 同口径））；「查看完整报告」= `$AI_REPORT_URL`（Step 1 emit-report.py 返回，禁止指向 markdown / 手搓通知）。**#3 是本 build 的末尾里程碑**（在 #F 之后），与 #F（测试报告）各司其职：#F = AI测试报告，#3 = AI执行报告（含 dev 全流程 + 真实测试结论）。

**Step 3 — baseline 收尾（★ 报告冻结）** —— ⛔ **必须是可执行语句**（同分片 3.3 的 `tested` 就是围栏；
`closed` + `finalized` 此前停在句子里，而它有 4 处可执行读侧：准发布 0b 门 / 已测去重门 /
Stop hook / emit-report 不可变锁。恒读 false 的后果是 0b 门永不通过、`prerelease_test_hold_streak`
每 tick +1，第 12 tick 冻结在 `unconverged`——**而测试其实早就跑完并通过了**）：

```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
BEV="python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version ${TARGET_VERSION:?}"
# ★ PASS_RATE **必须在本围栏现取**：它由上一步 gen_report 聚合，而那是**另一次 Bash 调用**，
#   shell 变量不存活 → `${PASS_RATE:-0}` 恒落 0 → `builds[].pass_rate` 恒记 0，
#   报告首页与准发布判据读到的通过率全是 0。故从已落盘的报告数据现取，别靠跨围栏变量。
PASS_RATE=$(grep -oE '"passRate"[[:space:]]*:[[:space:]]*[0-9.]+' \
  "docs/reports/${TARGET_VERSION}/AI执行报告/data/${BUILD}.js" 2>/dev/null \
  | head -1 | grep -oE '[0-9.]+$')
$BEV --build "${BUILD:?}" set status closed ai_report_finalized true \
  ai_report_finalized_at @now finished_at @now pass_rate "${PASS_RATE:-0}"
```
**`ai_report_finalized` / `ai_report_finalized_at` 是「报告不可变铁律」的冻结基准**：此后 `emit-report.py` 对本 build 再写 data 直接拒绝 exit 2（除非 `--force-amend` 留痕）、`autopilot-ceremony-gate.py --stage final` 校 data mtime 不得晚于 `ai_report_finalized_at`（详见两脚本 + 命令主体文首 ⛔「报告不可变铁律」）。

> ⛔ **不重发 / 不早发铁律**：#3 仅在收敛轮（`CONVERGED=1`）由本步发**一次**；未收敛轮只发 #R（见 3.4），绝不发 #3。`REPORT_ENABLED=0`（standalone）整步跳过——AI执行报告是 autopilot 流水线产物，非 autopilot 驱动不 finalize、不发 #3。

**Step 4 — ★ 数据清理文档生成（每 build 一份，落 `docs/reports/{version}/AI数据清理/`）**：本 build 的 AI 自动化测试通过浏览器造了测试数据（新增/编辑记录），会污染测试环境库，故 finalize 时**自动**生成一份**数据清理文档**供测试后清库。**非阻塞 best-effort**（无人值守自动跑、不弹确认；生成失败仅终端 WARN、不阻塞收尾）。

- **触发条件**：`REPORT_ENABLED=1`（autopilot 驱动、有 `BUILD`）→ 生成；**与 `CONVERGED` 无关**——无论本轮通过/部分通过/不通过，只要跑了测试就造了数据、就要能清（standalone 无 `BUILD` 概念 → 跳过本步）。
- **落位**：`docs/reports/{version}/AI数据清理/${BUILD}_数据清理.md`（目录不存在先 `mkdir -p`；属 `docs/reports/{version}/` 报告族、与 `AI执行报告/`·`AI测试报告/`·`版本测试报告/` 同处，遵约定 11 版本落位一致性——恒落当前被测版本目录）。
- **生成方式**：`cp {{AIDP_HOME}}/templates/reports/AI数据清理.md` 到落位路径后逐字段填充（模板即字段规范，本命令不复述）：
  - **测试执行信息**：`BUILD` / 版本 / 测试时间窗（本轮开始~结束）/ 环境名 / 被测 URL / `driver` / 测试账号（脱敏）/ 本轮结论——取自 Phase 0 已读的「测试环境与账号」配置 + baseline build 记录。
  - **需清理的数据库**：DB 连接**优先取** `docs/testing/{version}/研发自测/` 的「测试环境与账号」配置的 DB 段；缺失则回退后端 `application.yml` 生效 profile 的 datasource（host/port/库名/账号）；**两者都缺 → 填 `{待补}` 占位 + 文档标注「需人工补数据库连接」，不静默留空**。
  - **涉及写库表 + 清理 SQL**：由本 build 实际跑过的用例/模块（auto-test-runner 本轮 `results/*.json` / 覆盖的 SUITE）映射到详细设计「数据库设计」对应业务表；**优先按「测试账号 create_by + 本轮时间窗 create_time」双条件生成逐表 `DELETE`**（表含审计字段时，安全、不误删真实数据）；无审计字段的表按业务标记/主键区间并标「需人工核对」；有外键依赖按子表→父表顺序。**严禁**生成整库 `DROP`/无条件 `DELETE`（除非该库为独占测试专用库才给 `TRUNCATE` 兜底选项）。
- **报告不可变对齐**：本 build 一旦 finalize（Step 3 冻结），其数据清理文档**随之定稿**；后续测试结论变化走新 build → 另生成 `${下一 BUILD}_数据清理.md`，**绝不回改旧 build 的清理文档**。
- **提交**：本文件随 build 仪式产物一并 `git add`（与报告同批提交，autopilot 侧统一 commit；本命令只负责生成落盘）。

**Step 4.1 — ★ 主动询问是否执行数据清理（交互式问用户；无人值守默认不执行）**：数据清理文档生成后**不自动执行**其中的清理 SQL（`DELETE` 属破坏性操作），而是把「是否现在清库」的决定权交用户：

- **交互式调用**（非 `LOOP_UNATTENDED`）→ 用 `AskUserQuestion` 问：**「本 build 已生成数据清理文档 `${BUILD}_数据清理.md`，是否现在执行其中的清理 SQL？」** 选项 **[① 暂不执行（仅保留文档，默认推荐）/ ② 现在执行清理]**。
  - 选 **①** → 跳过执行，仅保留文档供人工后续手动清理。
  - 选 **②** → 按文档「二、需清理的数据库」的测试库 datasource，用对应 DB 客户端执行「五、清理 SQL」——**执行前硬校验：确认目标是测试库、非生产**（库名/host 命中生产特征或无法判定则**拒绝执行 + 提示人工**）；执行结果（各表删除行数）回显终端 + 追加到文档末尾「执行记录」段。
- **无人值守**（`LOOP_UNATTENDED` / autopilot `/loop` 驱动）→ **绝不弹问询、绝不自动执行清理 SQL**（无人值守自动跑破坏性删除有风险）；仅在终端 + `#F`/`#3` 通知正文标注一行「📄 数据清理文档已生成 `${路径}`，需人工决定是否执行」，把执行决策留给人。
- **安全铁律**：任何情形下清理 SQL 只在文档记录的**测试库**执行、**生产库严禁**；执行走「测试账号 + 时间窗」双条件精准删（见文档「六、安全铁律」）。
